#!/usr/bin/env python3
"""Headless ngspice driver built on the shared library KiCad ships.

There is no ngspice CLI, no LTspice and no PySpice on this machine, but
KiCad 10 bundles the full ngspice shared library plus its XSPICE code
models.  This module talks to it directly through ``ctypes`` using the
classic sharedspice API:

    ngSpice_Init(SendChar, SendStat, ControllerExit,
                 SendData, SendInitData, BGThreadRunning, userdata)
    ngSpice_Command("source foo.cir") / ngSpice_Command("run")
    ngSpice_CurPlot() / ngSpice_AllVecs() / ngGet_Vec_Info()

Verified working with:
    python : /usr/bin/python3                       (3.9.6, arm64)
    dylib  : /Applications/KiCad/KiCad.app/Contents/Frameworks/libngspice.0.dylib
             (ngspice-45.2 shared library)
The KiCad-bundled python at
Frameworks/Python.framework/Versions/Current/bin/python3 loads it equally
well; either is fine as both are arm64.  No codesign or Library Validation
problem appears because we dlopen a library that is already signed as part
of the KiCad bundle.

Why every simulation runs in a subprocess
-----------------------------------------
The shared library keeps global state (the circuit list, the plot list and
a fair amount of static parser state) and, on a fatal error, sharedspice
may call the ControllerExit callback with ``immediate`` set, which in
practice can tear the process down.  Running each netlist in a short-lived
child process makes a blown-up simulation a recoverable event for the
caller instead of a crash, and guarantees that circuit N+1 never inherits
anything from circuit N.  Use :func:`run_netlist` for that (the normal
entry point); :class:`NgSpiceShared` is the in-process primitive if you
really want several circuits in one interpreter.

Typical use::

    from ngspice_ctypes import run_netlist
    res = run_netlist(netlist_text, commands=["tran 10u 5m", "print all"])
    t   = res.vector("time")
    v   = res.vector("v(out)")
    print(res.log)                 # everything ngspice wrote

AC analyses come back as Python ``complex`` lists, transient/DC as floats.
"""

from __future__ import annotations

import ctypes
import json
import shutil
import os
import subprocess
import sys
import tempfile

# --------------------------------------------------------------------------
# Locations.  Both are checked at import time only when actually used, so
# that importing this module on a machine without KiCad still works (the
# error is then raised with a useful message at run time).
# --------------------------------------------------------------------------
KICAD_FRAMEWORKS = "/Applications/KiCad/KiCad.app/Contents/Frameworks"
DYLIB_CANDIDATES = [
    os.path.join(KICAD_FRAMEWORKS, "libngspice.0.dylib"),
    os.path.join(KICAD_FRAMEWORKS, "libngspice.dylib"),
    "/opt/homebrew/lib/libngspice.0.dylib",
    "/usr/local/lib/libngspice.0.dylib",
    "libngspice.so.0",
]
CODEMODEL_DIR = "/Applications/KiCad/KiCad.app/Contents/PlugIns/sim/ngspice"
CODEMODELS = ("analog", "digital", "xtradev", "xtraevt", "spice2poly", "table")

VF_COMPLEX = 1 << 1


def find_dylib():
    """Return the path of the first libngspice we can actually dlopen."""
    errors = []
    for cand in DYLIB_CANDIDATES:
        if os.sep in cand and not os.path.exists(cand):
            continue
        try:
            ctypes.CDLL(cand)
            return cand
        except OSError as exc:  # pragma: no cover - environment dependent
            errors.append("%s: %s" % (cand, exc))
    raise RuntimeError(
        "no usable libngspice found. Tried:\n  " + "\n  ".join(errors or DYLIB_CANDIDATES)
    )


# --------------------------------------------------------------------------
# ctypes declarations
# --------------------------------------------------------------------------
class ngcomplex_t(ctypes.Structure):
    _fields_ = [("cx_real", ctypes.c_double), ("cx_imag", ctypes.c_double)]


class vector_info(ctypes.Structure):
    _fields_ = [
        ("v_name", ctypes.c_char_p),
        ("v_type", ctypes.c_int),
        ("v_flags", ctypes.c_short),
        ("v_realdata", ctypes.POINTER(ctypes.c_double)),
        ("v_compdata", ctypes.POINTER(ngcomplex_t)),
        ("v_length", ctypes.c_int),
    ]


SendChar_t = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
SendStat_t = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
ControllerExit_t = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p
)
SendData_t = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p)
SendInitData_t = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p)
BGThreadRunning_t = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)


class NgSpiceShared(object):
    """Thin in-process wrapper around libngspice.

    Only one instance may exist per process: the library is a singleton
    with global state and ``ngSpice_Init`` may be called only once.
    """

    _instance = None

    def __init__(self, dylib=None, load_codemodels=True):
        if NgSpiceShared._instance is not None:
            raise RuntimeError("libngspice is a process singleton; reuse the existing instance")
        self.path = dylib or find_dylib()
        self.lib = ctypes.CDLL(self.path)
        self.output = []          # every line ngspice emitted (stdout+stderr)
        self.exit_status = None   # set if ngspice asked the controller to quit

        lib = self.lib
        lib.ngSpice_Init.restype = ctypes.c_int
        lib.ngSpice_Command.argtypes = [ctypes.c_char_p]
        lib.ngSpice_Command.restype = ctypes.c_int
        lib.ngGet_Vec_Info.argtypes = [ctypes.c_char_p]
        lib.ngGet_Vec_Info.restype = ctypes.POINTER(vector_info)
        lib.ngSpice_CurPlot.restype = ctypes.c_char_p
        lib.ngSpice_AllPlots.restype = ctypes.POINTER(ctypes.c_char_p)
        lib.ngSpice_AllVecs.argtypes = [ctypes.c_char_p]
        lib.ngSpice_AllVecs.restype = ctypes.POINTER(ctypes.c_char_p)

        # The callbacks must stay referenced for the lifetime of the object,
        # otherwise ctypes garbage-collects the trampolines and ngspice
        # calls into freed memory.
        @SendChar_t
        def _send_char(msg, _id, _user):
            self.output.append(msg.decode("utf-8", "replace"))
            return 0

        @SendStat_t
        def _send_stat(_msg, _id, _user):
            return 0

        @ControllerExit_t
        def _controller_exit(status, immediate, quitexit, _id, _user):
            self.exit_status = (int(status), bool(immediate), bool(quitexit))
            return 0

        @SendData_t
        def _send_data(_data, _n, _id, _user):
            return 0

        @SendInitData_t
        def _send_init(_data, _id, _user):
            return 0

        @BGThreadRunning_t
        def _bg(_running, _id, _user):
            return 0

        self._cbs = (_send_char, _send_stat, _controller_exit, _send_data, _send_init, _bg)
        rc = lib.ngSpice_Init(*(self._cbs + (None,)))
        if rc != 0:
            raise RuntimeError("ngSpice_Init failed with rc=%d" % rc)
        NgSpiceShared._instance = self

        # Loading the XSPICE code models also, as a side effect, makes
        # ngspice's PSpice compatibility mode far more likely to survive its
        # own helper-definition injection.  Measured on an identical vendor
        # deck: roughly 1 failure in 3 with them loaded, 6 in 6 without.  The
        # retry in run_netlist covers the remainder.
        if load_codemodels and os.path.isdir(CODEMODEL_DIR):
            for name in CODEMODELS:
                p = os.path.join(CODEMODEL_DIR, "%s.cm" % name)
                if os.path.exists(p):
                    self.command("codemodel %s" % p)

    # -- low level ---------------------------------------------------------
    def command(self, cmd):
        """Send one ngspice command; return its integer status."""
        return self.lib.ngSpice_Command(cmd.encode("utf-8"))

    @property
    def log(self):
        """Everything ngspice printed, as one string with real newlines.

        sharedspice prefixes each line with ``stdout `` or ``stderr `` and
        strips the newline, so we put the structure back.
        """
        lines = []
        for raw in self.output:
            for prefix in ("stdout ", "stderr "):
                if raw.startswith(prefix):
                    raw = raw[len(prefix):]
                    break
            lines.append(raw)
        return "\n".join(lines)

    def cur_plot(self):
        p = self.lib.ngSpice_CurPlot()
        return p.decode() if p else None

    def all_vectors(self, plot=None):
        plot = plot or self.cur_plot()
        if not plot:
            return []
        arr = self.lib.ngSpice_AllVecs(plot.encode())
        names, i = [], 0
        while arr and arr[i]:
            names.append(arr[i].decode())
            i += 1
        return names

    def vector(self, name, plot=None):
        """Return one vector as a list of float (or complex for AC)."""
        full = name if (plot is None or "." in name) else "%s.%s" % (plot, name)
        vi = self.lib.ngGet_Vec_Info(full.encode())
        if not vi:
            return None
        v = vi.contents
        n = int(v.v_length)
        if n <= 0:
            return []
        if v.v_flags & VF_COMPLEX:
            if not v.v_compdata:
                return []
            return [complex(v.v_compdata[i].cx_real, v.v_compdata[i].cx_imag) for i in range(n)]
        if not v.v_realdata:
            return []
        return [float(v.v_realdata[i]) for i in range(n)]

    def source_and_run(self, netlist_text, commands=None, workdir=None, pre_commands=None):
        """Write ``netlist_text`` to a file, source it, then run ``commands``.

        If the netlist carries its own ``.control`` block, ``source`` already
        executes it and no extra commands are needed.
        """
        workdir = workdir or tempfile.mkdtemp(prefix="ngsim_")
        cir = os.path.join(workdir, "deck.cir")
        with open(cir, "w") as fh:
            fh.write(netlist_text)
        self.command("cd %s" % workdir)
        # Anything that has to be set BEFORE the deck is parsed goes here.
        # `set ngbehavior=psa` is the important one: it puts ngspice into
        # PSpice compatibility mode, which is what makes a TI vendor model
        # (E/G ... VALUE {}, IF(), PARAMS:, VSWITCH) parse at all.  A
        # `.options` line inside the deck is too late -- by then the
        # expressions have already failed to parse.
        for cmd in pre_commands or []:
            self.command(cmd)
        self.command("source %s" % cir)
        for cmd in commands or []:
            self.command(cmd)
        return cir


# --------------------------------------------------------------------------
# Result object + subprocess front end
# --------------------------------------------------------------------------
class SimResult(object):
    """Vectors and log of one completed (or failed) simulation run."""

    def __init__(self, ok, log, plots, error=None, returncode=0):
        self.ok = ok
        self.log = log
        self.plots = plots            # {plotname: {vecname: [values]}}
        self.error = error
        self.returncode = returncode

    # `plots` values arrive from JSON, so complex numbers are [re, im] pairs.
    def vector(self, name, plot=None):
        """Fetch a vector by name.  ``plot`` defaults to the last plot."""
        cands = [plot] if plot else list(self.plots.keys())[::-1]
        low = name.lower()
        alt = None
        if low.startswith("v(") and low.endswith(")"):
            alt = low[2:-1]
        for pl in cands:
            vecs = self.plots.get(pl) or {}
            lut = dict((k.lower(), v) for k, v in vecs.items())
            for key in (low, alt):
                if key and key in lut:
                    return lut[key]
        return None

    def names(self, plot=None):
        pl = plot or (list(self.plots.keys())[-1] if self.plots else None)
        return sorted((self.plots.get(pl) or {}).keys())

    def __repr__(self):
        return "<SimResult ok=%s plots=%s>" % (self.ok, list(self.plots.keys()))


def _decode(value):
    """JSON [re, im] pairs back into complex; plain numbers stay floats."""
    if value and isinstance(value[0], list):
        return [complex(a, b) for a, b in value]
    return value


# A measured ngspice 45.2 defect, not a fault in any deck here.
#
# When PSpice compatibility mode is on, ngspice injects its own helper
# definitions at start-up and sometimes fails to parse one of them:
#     ERROR: failed to parse .func in: .func pwr(x a) { pow(x,a)}
#     Error: ngspice.dll cannot recover and awaits to be reset or detached
# The identical deck run again usually succeeds, so it is a start-up race.
# Measured failure rate on one vendor deck, 6 runs each:
#     XSPICE code models loaded    3 of 6 failed
#     code models not loaded       6 of 6 failed
#     mode set from a spinit file  5 of 5 failed
# So the code models are loaded (see NgSpiceShared.__init__) and the rest is
# covered by retrying.  Every run is already its own subprocess, so a retry
# costs only time and cannot corrupt anything.  Eight attempts at a 50 %
# per-attempt failure rate leaves well under 1 % residual risk, and a case
# that still fails reports the error rather than silently losing a result.
_FLAKY = "failed to parse .func"
# 2026-09-23: that was the only deck family that needed compatibility mode,
# and sim/lib/pspice_native.py now gives it ngspice-native models, so nothing
# here runs in PSpice mode any more. `retries` defaults to 1: a failure is
# reported, not retried away. The retry stays available for a caller that
# must knowingly run a PSpice-mode deck.


def run_netlist(netlist_text, commands=None, timeout=300, keep_dir=None, python=None,
                pre_commands=None, retries=1):
    """Run one netlist in a fresh ngspice subprocess and return a SimResult.

    ``netlist_text``  full SPICE deck.  A ``.control``/``.endc`` block inside
                      it is executed by ``source``, which is the most reliable
                      way to drive batch analyses and ``meas`` statements.
    ``commands``      extra interactive commands issued after sourcing.
    ``keep_dir``      write the deck and the raw log here instead of a temp
                      dir (useful for debugging a failing case).
    ``pre_commands``  commands issued BEFORE the deck is sourced, e.g.
                      ``["set ngbehavior=psa"]`` for a PSpice vendor model.
    """
    last = None
    for attempt in range(max(1, retries)):
        last = _run_once(netlist_text, commands, timeout, keep_dir, python, pre_commands)
        if last.ok or _FLAKY not in (last.log or ""):
            return last
    return last


def _run_once(netlist_text, commands, timeout, keep_dir, python, pre_commands):
    workdir = keep_dir or tempfile.mkdtemp(prefix="ngsim_")
    if not os.path.isdir(workdir):
        os.makedirs(workdir)
    req = os.path.join(workdir, "request.json")
    out = os.path.join(workdir, "result.json")
    with open(req, "w") as fh:
        json.dump({"netlist": netlist_text, "commands": commands or [],
                   "pre_commands": pre_commands or [], "workdir": workdir}, fh)

    argv = [python or sys.executable, os.path.abspath(__file__), "--worker", req, out]
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        rc, tail = proc.returncode, proc.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return SimResult(False, "", {}, error="timeout after %ss" % timeout, returncode=-1)

    if not os.path.exists(out):
        return SimResult(False, tail, {}, error="worker produced no result (rc=%d)" % rc, returncode=rc)
    with open(out) as fh:
        data = json.load(fh)
    if not keep_dir:
        # Each run's result.json carries every vector; left behind they filled
        # the disk after a few hundred runs (2026-09-23).
        shutil.rmtree(workdir, ignore_errors=True)
    plots = dict(
        (pl, dict((k, _decode(v)) for k, v in vecs.items()))
        for pl, vecs in data.get("plots", {}).items()
    )
    return SimResult(data.get("ok", False), data.get("log", ""), plots,
                     error=data.get("error"), returncode=rc)


def _worker(req_path, out_path):
    """Child-process entry point: load libngspice, run, dump JSON."""
    with open(req_path) as fh:
        req = json.load(fh)
    result = {"ok": False, "log": "", "plots": {}, "error": None}
    ng = None
    try:
        ng = NgSpiceShared()
        ng.source_and_run(req["netlist"], req.get("commands"), req.get("workdir"),
                          pre_commands=req.get("pre_commands"))
        plots = {}
        arr = ng.lib.ngSpice_AllPlots()
        i, names = 0, []
        while arr and arr[i]:
            names.append(arr[i].decode())
            i += 1
        for pl in names:
            if pl == "const":
                continue
            vecs = {}
            for vn in ng.all_vectors(pl):
                data = ng.vector("%s.%s" % (pl, vn))
                if data is None:
                    continue
                if data and isinstance(data[0], complex):
                    vecs[vn] = [[z.real, z.imag] for z in data]
                else:
                    vecs[vn] = data
            if vecs:
                plots[pl] = vecs
        result["plots"] = plots
        result["ok"] = bool(plots)
    except Exception as exc:  # noqa: BLE001 - report anything to the parent
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        if ng is not None:
            result["log"] = ng.log
            if ng.exit_status:
                result["error"] = (result["error"] or "") + " ngspice controller exit %r" % (ng.exit_status,)
        with open(out_path, "w") as fh:
            json.dump(result, fh)


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--worker":
        _worker(sys.argv[2], sys.argv[3])
    else:
        # Self-test: an RC low-pass whose -3 dB point we know analytically.
        deck = (
            "selftest rc\n"
            "V1 a 0 AC 1 DC 0\n"
            "R1 a b 1k\n"
            "C1 b 0 1n\n"
            ".control\n"
            "ac dec 50 100 10meg\n"
            ".endc\n"
            ".end\n"
        )
        r = run_netlist(deck)
        print("dylib :", find_dylib())
        print("ok    :", r.ok, "plots:", list(r.plots.keys()))
        f = r.vector("frequency")
        vb = r.vector("v(b)")
        if f and vb:
            import math
            mags = [20 * math.log10(abs(z)) for z in vb]
            idx = min(range(len(mags)), key=lambda i: abs(mags[i] + 3.01))
            print("f-3dB : %.1f Hz (expected 159155 Hz)" % abs(f[idx]))
        else:
            print("FAILED\n", r.log)
