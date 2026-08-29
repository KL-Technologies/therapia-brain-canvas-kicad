#!/usr/bin/env python3
"""Measurement helpers shared by the sim cases, plus the result-file format.

Nothing here talks to ngspice; these are pure post-processing functions on
the vectors :mod:`ngspice_ctypes` hands back.  Keeping them separate means a
case script reads as "build a deck, run it, measure it, judge it", and the
judging is done by code that can be reasoned about on its own.
"""

from __future__ import annotations

import cmath
import json
import math
import os
import time

RESULT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")


# ---------------------------------------------------------------------------
# transient measurements
# ---------------------------------------------------------------------------
def window(t, v, t0, t1):
    """The (t, v) samples with t0 <= t <= t1."""
    return [(a, b) for a, b in zip(t, v) if t0 <= a <= t1]


def final_value(t, v, frac=0.05):
    """Mean of the last ``frac`` of the record - the settled rail value."""
    if not t:
        return float("nan")
    t0 = t[-1] - frac * (t[-1] - t[0])
    seg = [b for a, b in zip(t, v) if a >= t0]
    return sum(seg) / len(seg) if seg else float("nan")


def ripple_pp(t, v, t0, t1):
    """Peak-to-peak excursion inside a time window."""
    seg = [b for a, b in window(t, v, t0, t1)]
    return (max(seg) - min(seg)) if seg else float("nan")


def rise_time(t, v, lo=0.1, hi=0.9, target=None):
    """Time from ``lo`` to ``hi`` of the final value (works for negative rails)."""
    if not t:
        return float("nan")
    vf = target if target is not None else final_value(t, v)
    if vf == 0:
        return float("nan")
    a = b = None
    for tt, vv in zip(t, v):
        f = vv / vf
        if a is None and f >= lo:
            a = tt
        if a is not None and f >= hi:
            b = tt
            break
    return (b - a) if (a is not None and b is not None) else float("nan")


def time_to_reach(t, v, level, rising=True):
    """First instant the waveform crosses ``level``."""
    for tt, vv in zip(t, v):
        if (rising and vv >= level) or (not rising and vv <= level):
            return tt
    return float("nan")


def overshoot_pct(t, v, target=None):
    """Peak overshoot beyond the settled value, in percent of it."""
    if not t:
        return float("nan")
    vf = target if target is not None else final_value(t, v)
    if vf == 0:
        return float("nan")
    peak = max(v) if vf > 0 else min(v)
    return (peak - vf) / abs(vf) * 100.0


def sustained_ring(t, v, t_start, threshold):
    """Largest peak-to-peak excursion in any 1 ms window after ``t_start``.

    "No sustained ringing above X mV pp after 5 ms" is exactly this measure:
    a decaying transient shrinks window by window, an oscillation does not.
    Returns (worst_pp, is_sustained).
    """
    seg = window(t, v, t_start, t[-1] if t else t_start)
    if len(seg) < 4:
        return float("nan"), False
    span = seg[-1][0] - seg[0][0]
    nwin = max(1, int(span / 1e-3))
    worst = 0.0
    for k in range(nwin):
        a = seg[0][0] + k * span / nwin
        b = a + span / nwin
        w = [y for x, y in seg if a <= x <= b]
        if len(w) > 2:
            worst = max(worst, max(w) - min(w))
    # sustained = the LAST window is still above threshold
    a = seg[0][0] + (nwin - 1) * span / nwin
    tail = [y for x, y in seg if x >= a]
    last_pp = (max(tail) - min(tail)) if len(tail) > 2 else 0.0
    return worst, bool(last_pp > threshold)


def settles(t, v, t_step, threshold, settle_window=2e-3):
    """True if the waveform is quiet (< threshold pp) in the last window."""
    if not t:
        return False, float("nan")
    tail = [y for x, y in zip(t, v) if x >= t[-1] - settle_window]
    pp = (max(tail) - min(tail)) if len(tail) > 2 else float("nan")
    return bool(pp < threshold), pp


# ---------------------------------------------------------------------------
# AC / loop-gain measurements
# ---------------------------------------------------------------------------
def db(z):
    m = abs(z)
    return 20 * math.log10(m) if m > 0 else -400.0


def unwrapped_phase(vec):
    """Phase in degrees, unwrapped so a loop that rolls past -180 reads so."""
    out, off = [], 0.0
    prev = None
    for z in vec:
        ph = math.degrees(cmath.phase(z))
        if prev is not None:
            while ph + off - prev > 180:
                off -= 360
            while ph + off - prev < -180:
                off += 360
        val = ph + off
        out.append(val)
        prev = val
    return out


def crossover_and_pm(freq, loop):
    """Gain crossover frequency and phase margin of an open-loop response.

    ``loop`` is T(jw) as a list of complex numbers on the ``freq`` grid.
    Phase margin = 180 + angle(T) at |T| = 1.  Returns
    (f_cross_Hz, phase_margin_deg, dc_gain_dB) with NaN if it never crosses.
    """
    if not freq or not loop:
        return float("nan"), float("nan"), float("nan")
    mags = [db(z) for z in loop]
    phs = unwrapped_phase(loop)
    dc = mags[0]
    fc = pm = float("nan")
    for i in range(1, len(mags)):
        if mags[i - 1] >= 0 > mags[i]:
            # log-linear interpolation onto 0 dB
            m0, m1 = mags[i - 1], mags[i]
            w = m0 / (m0 - m1)
            f0, f1 = abs(freq[i - 1]), abs(freq[i])
            fc = math.exp(math.log(f0) + w * (math.log(f1) - math.log(f0)))
            pm = 180.0 + (phs[i - 1] + w * (phs[i] - phs[i - 1]))
            break
    return fc, pm, dc


def gain_at(freq, vec, f_target):
    """|H| in dB at the grid point nearest ``f_target``."""
    if not freq:
        return float("nan")
    i = min(range(len(freq)), key=lambda k: abs(abs(freq[k]) - f_target))
    return db(vec[i])


# ---------------------------------------------------------------------------
# result files
# ---------------------------------------------------------------------------
def write_result(name, passed, checks, numbers, notes=None, models=None, path=None):
    """Write one case's JSON result under sim/out/<name>.json.

    ``checks``  [{name, pass, detail}]  - the individual criteria
    ``numbers`` {key: value}            - everything measured, pass or fail
    ``models``  {device: "vendor"|"behavioural"} - provenance, carried into
                the S3_sim gate so the gate never implies more rigour than
                the models actually have.
    """
    if not os.path.isdir(RESULT_DIR):
        os.makedirs(RESULT_DIR)
    doc = {
        "case": name,
        "pass": bool(passed),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checks": checks,
        "numbers": numbers,
        "models": models or {},
        "notes": notes or "",
    }
    p = path or os.path.join(RESULT_DIR, "%s.json" % name)
    with open(p, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=False, default=str)
    return doc


def report(doc):
    """Human-readable one-screen summary for the terminal."""
    print("=" * 74)
    print("%s : %s" % (doc["case"], "PASS" if doc["pass"] else "FAIL"))
    print("=" * 74)
    for c in doc["checks"]:
        print("  [%s] %-42s %s" % ("ok" if c.get("pass") else "XX", c["name"], c.get("detail", "")))
    if doc["numbers"]:
        print("  --- numbers ---")
        for k, v in doc["numbers"].items():
            if isinstance(v, float):
                print("      %-40s %.6g" % (k, v))
            else:
                print("      %-40s %s" % (k, v))
    if doc.get("notes"):
        print("  --- notes ---")
        for line in str(doc["notes"]).splitlines():
            print("      " + line)
