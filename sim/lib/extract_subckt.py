#!/usr/bin/env python3
"""Turn the Brain Canvas schematic contract into SPICE sub-circuits.

Inputs (both are the project's own contract data, never guessed):
  contract/netlist_easyeda_api_2026-08-28.tsv
        designator <TAB> pin <TAB> pinName <TAB> net <TAB> ggeId
  data/parts_lcsc.csv
        designator, value, mpn, lcsc, package, ..., dnp, ...

What it gives you
-----------------
* :class:`Design` - a queryable model of the board: ``pins_of(ref)``,
  ``nets_of(ref)``, ``refs_on(net)``, ``value_of(ref)``, ``dnp``.
* :meth:`Design.spice` - emit SPICE element lines for a chosen set of
  designators (or for everything touching a set of nets).  Passives become
  R/C/L elements with values parsed from the BOM value strings; ferrite
  beads become the usual small series R + L pair; ICs become ``X`` calls on
  a sub-circuit name so a behavioural or vendor model can be dropped in.
* :func:`effective_cap` - MLCC DC-bias derating from
  ``sim/data/cap_derating.json``.  Simulating an EEG front end with the
  nominal printed value of a 6.3 V 0402 X5R would be self-deception: at
  2.5 V those parts keep well under half their marked capacitance, and the
  LDO stability question turns on exactly that number.

Units are always emitted in explicit scientific notation.  SPICE's ``M``
means *milli*, not mega, and "R_BIAS_FB = 1M" in a BOM means one megohm;
writing ``1e6`` removes the ambiguity entirely.

Run as a script for a quick dump::

    python3 sim/lib/extract_subckt.py --refs TPS72325 C_NLDO_OUT C_NR
    python3 sim/lib/extract_subckt.py --nets AVSS --bias AVSS=-2.5
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
NETLIST_TSV = os.path.join(ROOT, "contract", "netlist_easyeda_api_2026-08-28.tsv")
PARTS_CSV = os.path.join(ROOT, "data", "parts_lcsc.csv")
DERATING_JSON = os.path.join(ROOT, "sim", "data", "cap_derating.json")

# ---------------------------------------------------------------------------
# Value parsing
# ---------------------------------------------------------------------------
_SUFFIX = {
    "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3,
    "k": 1e3, "meg": 1e6, "g": 1e9,
}
# "10uF", "1.5nF", "100nF", "4k7", "5.1k", "330R", "0R", "1M", "600R@100MHz"
_NUM_RE = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)\s*(?P<suf>meg|[fpnuµmkgR]|)\s*(?P<unit>F|H|R|ohm|Ω|)",
    re.IGNORECASE,
)
_RN_RE = re.compile(r"^(\d+)([RkKmM])(\d+)$")   # 4k7 / 1R5 style


def parse_value(text, kind):
    """Parse a BOM value string into base SI units (ohm / farad / henry).

    ``kind`` is one of ``"R"``, ``"C"``, ``"L"``.  It disambiguates the
    bare ``M`` suffix (mega for resistors, and there are no bare-M
    capacitors in this BOM) and lets us reject the wrong unit letter.
    Returns ``None`` when the string carries no number we trust.
    """
    if not text:
        return None
    s = str(text).strip()

    m = _RN_RE.match(s)
    if m and kind == "R":
        mult = {"R": 1.0, "k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6}[m.group(2)]
        return (float(m.group(1)) + float(m.group(3)) / 10.0 ** len(m.group(3))) * mult

    # A ferrite is spelled "600R@100MHz 0805" -- take the part before '@'.
    head = s.split("@")[0]
    for m in _NUM_RE.finditer(head):
        num = float(m.group("num"))
        suf = (m.group("suf") or "").lower()
        unit = (m.group("unit") or "").upper()
        if kind == "C":
            if unit not in ("F", ""):
                continue
            if unit == "" and suf not in ("p", "n", "u", "µ"):
                continue          # "0402", "50V" and friends
            mult = _SUFFIX.get(suf, 1.0)
            return num * mult
        if kind in ("R", "L"):
            if unit in ("F",):
                continue
            if suf == "r" or unit in ("R", "OHM", "Ω"):
                # "330R" -> 330; "0R" -> 0
                return num * (1.0 if suf in ("r", "") else _SUFFIX.get(suf, 1.0))
            if suf:
                mult = 1e6 if suf == "m" and kind == "R" else _SUFFIX.get(suf, 1.0)
                return num * mult
            if unit == "":
                continue
    return None


def fmt(x):
    """SPICE-safe number: always scientific, never an ambiguous suffix."""
    return "%.6g" % float(x)


# ---------------------------------------------------------------------------
# Capacitor DC-bias derating
# ---------------------------------------------------------------------------
_DERATING = None


def load_derating(path=DERATING_JSON):
    global _DERATING
    if _DERATING is None:
        with open(path) as fh:
            _DERATING = json.load(fh)
    return _DERATING


WORST_CASE = os.environ.get("SIM_CAP_WORST_CASE", "") not in ("", "0", "false")


def effective_cap(lcsc, vbias, nominal=None, path=DERATING_JSON, worst_case=None):
    """Effective capacitance of an MLCC at ``vbias`` volts of DC bias.

    Returns ``(C_eff_farad, info_dict)``.  ``info_dict`` carries the
    retention factor actually used, the data source and a ``trusted``
    flag that is False for rows the derating table marks as an engineering
    estimate rather than a fetched manufacturer curve -- the case scripts
    propagate that flag into the gate JSON so nobody mistakes an estimate
    for a measurement.
    """
    table = load_derating(path)
    row = table.get(lcsc)
    v = abs(float(vbias))
    wc = WORST_CASE if worst_case is None else worst_case
    if not row:
        c = nominal if nominal is not None else 0.0
        return c, {"factor": 1.0, "source": "no derating data", "trusted": False,
                   "lcsc": lcsc, "bias_V": v}
    cnom = float(row.get("nominal_F", nominal or 0.0))
    curve = row.get("bias_retention_worst_case") if wc else None
    curve = curve or row["bias_retention"]
    pts = sorted((float(k), float(x)) for k, x in curve.items())
    if v <= pts[0][0]:
        f = pts[0][1]
    elif v >= pts[-1][0]:
        f = pts[-1][1]
    else:
        f = pts[-1][1]
        for (v0, f0), (v1, f1) in zip(pts, pts[1:]):
            if v0 <= v <= v1:
                f = f0 + (f1 - f0) * (v - v0) / (v1 - v0) if v1 > v0 else f0
                break
    return cnom * f, {
        "factor": f, "bias_V": v, "lcsc": lcsc, "mpn": row.get("mpn"),
        "nominal_F": cnom, "rated_V": row.get("rated_V"),
        "esr_ohm": row.get("esr_100k_ohm"), "esl_H": row.get("esl_H"),
        "source": row.get("source", "?"),
        "trusted": bool(row.get("trusted", False)),
        "corner": "worst-case (tolerance + temperature)" if wc else "typical 25 C",
    }


# ---------------------------------------------------------------------------
# Component classification
# ---------------------------------------------------------------------------
IC_SUBCKT = {
    "TPS72325": "TPS72325",
    "TLV70025": "TLV70025",
    "LM2664": "LM2664",
    "AMS1117": "AMS1117_33",
    "U_ADS": "ADS1299",
    "U_MCU": "ESP32",
    "U_USB": "CH340C",
}


def kind_of(ref):
    """R / C / L(ferrite) / F(fuse) / D / Q / J / IC, from the designator."""
    if ref.startswith("C_") or re.match(r"^C\d", ref):
        return "C"
    if ref.startswith("R_") or re.match(r"^R\d", ref):
        return "R"
    if ref.startswith("FB"):
        return "L"
    if re.match(r"^F\d", ref):
        return "F"
    if ref.startswith("D_"):
        return "D"
    if ref.startswith("Q_"):
        return "Q"
    if re.match(r"^J\d", ref):
        return "J"
    return "IC"


# Datasheet-ish parameters for parts whose BOM value string is descriptive
# rather than numeric.  Each carries its own provenance note.
FERRITE = {
    # Sunlord GZ2012D601TF, 0805, 600 ohm @ 100 MHz, Idc 2 A.
    # Rdc is the datasheet max for this part family; L is derived from the
    # rated impedance:  L = Z / (2*pi*f) = 600 / (2*pi*100e6) = 955 nH.
    "GZ2012D601TF": {"rdc_ohm": 0.20, "l_h": 955e-9,
                     "note": "Rdc 0.20 ohm = Sunlord GZ2012D series max; "
                             "L from Z=600R@100MHz"},
}
PTC = {
    # Sunlord/Jinrui SMD1206P050TF/13.2: Ihold 0.5 A, Itrip 1.0 A,
    # Rmin 0.35 ohm / R1max 1.20 ohm.  We simulate the "as fitted, warm"
    # resistance, which is the pessimistic end for a startup droop check.
    "SMD1206P050TF/13.2": {"r_ohm": 0.55,
                           "note": "between Rmin 0.35 and R1max 1.20 (datasheet)"},
}


# ---------------------------------------------------------------------------
# The design model
# ---------------------------------------------------------------------------
class Pin(object):
    __slots__ = ("ref", "pin", "name", "net", "gge")

    def __init__(self, ref, pin, name, net, gge):
        self.ref, self.pin, self.name, self.net, self.gge = ref, pin, name, net, gge

    def __repr__(self):
        return "Pin(%s.%s %s -> %s)" % (self.ref, self.pin, self.name, self.net)


class Part(object):
    __slots__ = ("ref", "value", "mpn", "lcsc", "package", "dnp")

    def __init__(self, ref, value, mpn, lcsc, package, dnp):
        self.ref, self.value, self.mpn = ref, value, mpn
        self.lcsc, self.package, self.dnp = lcsc, package, dnp

    def __repr__(self):
        return "Part(%s %s %s dnp=%s)" % (self.ref, self.value, self.lcsc, self.dnp)


OVERRIDES_JSON = os.path.join(ROOT, "contract", "contract_overrides.json")


class Design(object):
    """The board as the contract netlist and the BOM describe it.

    ``apply_overrides`` decides which revision you get.  The TSV is the
    EasyEDA schematic netlist as exported on 2026-08-28, i.e. *before*
    ECO-5; ``contract/contract_overrides.json`` holds the deltas that have
    already been applied to the PCB and are still to be back-annotated into
    the schematic.  Default True gives the as-built board.  Pass False to
    reproduce the pre-ECO wiring, which is how ``drl_loop.py`` shows what
    ECO-5 actually bought.
    """

    def __init__(self, tsv=NETLIST_TSV, parts_csv=PARTS_CSV,
                 apply_overrides=True, overrides_json=OVERRIDES_JSON,
                 part_swaps=None):
        self.pins = []
        with open(tsv) as fh:
            for line in fh:
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 4 or not cols[0]:
                    continue
                self.pins.append(Pin(cols[0], cols[1], cols[2], cols[3],
                                     cols[4] if len(cols) > 4 else ""))
        self.overrides_applied = []
        if apply_overrides and os.path.exists(overrides_json):
            with open(overrides_json) as fh:
                ov = json.load(fh)
            for item in ov.get("overrides", []):
                ref, pad = item["designator"], str(item["pad"])
                for p in self.pins:
                    if p.ref == ref and p.pin == pad:
                        p.net = item["override_net"]
                        self.overrides_applied.append(
                            "%s: %s.%s %s -> %s" % (item.get("eco", "?"), ref, pad,
                                                    item.get("contract_net"),
                                                    item["override_net"]))
        self.parts = {}
        with open(parts_csv) as fh:
            for row in csv.DictReader(fh):
                ref = (row.get("designator") or "").strip()
                if not ref:
                    continue
                self.parts[ref] = Part(ref, (row.get("value") or "").strip(),
                                       (row.get("mpn") or "").strip(),
                                       (row.get("lcsc") or "").strip(),
                                       (row.get("package") or "").strip(),
                                       (row.get("dnp") or "").strip() not in ("", "0"))
        # A BOM change still in flight can be tried without editing the CSV:
        # {designator: (lcsc, value)}.  Used to run a case against both the
        # current and the proposed bill of materials.
        self.part_swaps = dict(part_swaps or {})
        for ref, (lcsc, value) in self.part_swaps.items():
            if ref in self.parts:
                self.parts[ref].lcsc = lcsc
                self.parts[ref].value = value

        self._by_ref = {}
        self._by_net = {}
        for p in self.pins:
            self._by_ref.setdefault(p.ref, []).append(p)
            self._by_net.setdefault(p.net, []).append(p)

    # -- queries ----------------------------------------------------------
    def pins_of(self, ref):
        return sorted(self._by_ref.get(ref, []), key=lambda p: (len(p.pin), p.pin))

    def refs_on(self, net):
        return sorted(set(p.ref for p in self._by_net.get(net, [])))

    def pins_on(self, net):
        return list(self._by_net.get(net, []))

    def net_of(self, ref, pin):
        for p in self._by_ref.get(ref, []):
            if p.pin == str(pin) or p.name == str(pin):
                return p.net
        return None

    def nets_of(self, ref):
        return [p.net for p in self.pins_of(ref)]

    def value_of(self, ref):
        part = self.parts.get(ref)
        return part.value if part else None

    def numeric_value(self, ref):
        """Parsed value in SI units, using the designator to pick the unit."""
        part = self.parts.get(ref)
        if not part:
            return None
        k = kind_of(ref)
        if k == "F":
            return PTC.get(part.mpn, {}).get("r_ohm")
        if k == "L":
            return FERRITE.get(part.mpn, {}).get("l_h")
        return parse_value(part.value, k if k in ("R", "C") else "R")

    def two_terminal_nets(self, ref):
        """(net_pin1, net_pin2) for a two-pin part, in pin order."""
        ps = [p for p in self.pins_of(ref)]
        ps.sort(key=lambda p: int(p.pin) if p.pin.isdigit() else 99)
        if len(ps) < 2:
            return None
        return ps[0].net, ps[1].net

    def caps_between(self, net_a, net_b=None):
        """Every capacitor with one pin on ``net_a`` (and optionally the
        other on ``net_b``).  Returns a list of (ref, other_net)."""
        found = []
        for ref, part in self.parts.items():
            if kind_of(ref) != "C" or part.dnp:
                continue
            tn = self.two_terminal_nets(ref)
            if not tn:
                continue
            a, b = tn
            if a == net_a:
                other = b
            elif b == net_a:
                other = a
            else:
                continue
            if net_b is None or other == net_b:
                found.append((ref, other))
        return sorted(found)

    # -- emission ---------------------------------------------------------
    def cap_line(self, ref, node_a=None, node_b=None, bias=None, derate=True,
                 with_esr=True, prefix=""):
        """One capacitor as R(ESR) + C in series, DC-bias derated.

        Returns ``(spice_text, info)``.  ESR matters for the LDO stability
        cases, so the default is a series ESR resistor and an intermediate
        node; pass ``with_esr=False`` for an ideal cap.
        """
        part = self.parts[ref]
        nom = parse_value(part.value, "C")
        a, b = self.two_terminal_nets(ref)
        a = node_a if node_a is not None else a
        b = node_b if node_b is not None else b
        if derate and bias is not None:
            ceff, info = effective_cap(part.lcsc, bias, nominal=nom)
        else:
            ceff, info = nom, {"factor": 1.0, "source": "nominal (no derating applied)",
                               "trusted": False, "lcsc": part.lcsc, "bias_V": bias}
        info.update({"ref": ref, "nominal_F": nom, "eff_F": ceff})
        esr = info.get("esr_ohm") or 0.02
        nm = prefix + ref
        if with_esr and esr > 0:
            mid = "%s_x" % nm
            txt = ("R%s_esr %s %s %s\nC%s %s %s %s\n"
                   % (nm, a, mid, fmt(esr), nm, mid, b, fmt(ceff)))
        else:
            txt = "C%s %s %s %s\n" % (nm, a, b, fmt(ceff))
        return txt, info

    def spice(self, refs=None, nets=None, bias=None, derate=True, with_esr=True,
              skip=(), prefix="", node_map=None, subckt_map=None):
        """Emit SPICE element lines for part of the board.

        ``refs``    designators to emit (default: everything touching ``nets``)
        ``nets``    emit every non-DNP part with a pin on one of these nets
        ``bias``    {net: dc_volts} used to derate capacitors; the bias of a
                    capacitor is |V(net_a) - V(net_b)|
        ``node_map`` rename nets on the way out (e.g. {"GND": "0"})
        ``subckt_map`` override which sub-circuit an IC instantiates, e.g.
                    {"LM2664": "LM2664_TI"} to swap a behavioural model for
                    a vendor one without touching the netlist

        Returns ``(text, report)`` where report lists every emitted part and
        every part that was skipped and why -- so a case can prove it did
        not silently drop something.
        """
        bias = bias or {}
        node_map = node_map or {}
        subckt_map = subckt_map or {}
        chosen = set(refs or [])
        if nets:
            for n in nets:
                chosen.update(self.refs_on(n))
        chosen -= set(skip)

        def nm(n):
            return node_map.get(n, n)

        lines, emitted, skipped = [], [], []
        for ref in sorted(chosen):
            part = self.parts.get(ref)
            k = kind_of(ref)
            if part is None:
                skipped.append((ref, "not in BOM"))
                continue
            if part.dnp:
                skipped.append((ref, "DNP in BOM"))
                continue
            if k == "C":
                tn = self.two_terminal_nets(ref)
                if not tn:
                    skipped.append((ref, "not two-terminal"))
                    continue
                va, vb = bias.get(tn[0], 0.0), bias.get(tn[1], 0.0)
                txt, info = self.cap_line(ref, nm(tn[0]), nm(tn[1]),
                                          bias=abs(va - vb) if derate else None,
                                          derate=derate, with_esr=with_esr, prefix=prefix)
                lines.append(txt.rstrip("\n"))
                emitted.append(info)
            elif k == "R":
                tn = self.two_terminal_nets(ref)
                val = parse_value(part.value, "R")
                if tn is None or val is None:
                    skipped.append((ref, "no parseable resistance (%r)" % part.value))
                    continue
                # A 0 ohm link is a link; SPICE prefers a tiny real number.
                val = val if val > 0 else 1e-3
                lines.append("R%s%s %s %s %s" % (prefix, ref, nm(tn[0]), nm(tn[1]), fmt(val)))
                emitted.append({"ref": ref, "kind": "R", "ohm": val})
            elif k == "L":
                tn = self.two_terminal_nets(ref)
                fb = FERRITE.get(part.mpn)
                if tn is None or fb is None:
                    skipped.append((ref, "unknown ferrite %r" % part.mpn))
                    continue
                mid = "%s%s_m" % (prefix, ref)
                lines.append("R%s%s %s %s %s" % (prefix, ref, nm(tn[0]), mid, fmt(fb["rdc_ohm"])))
                lines.append("L%s%s %s %s %s" % (prefix, ref, mid, nm(tn[1]), fmt(fb["l_h"])))
                emitted.append({"ref": ref, "kind": "ferrite", "rdc_ohm": fb["rdc_ohm"],
                                "l_h": fb["l_h"], "note": fb["note"]})
            elif k == "F":
                tn = self.two_terminal_nets(ref)
                pt = PTC.get(part.mpn)
                if tn is None or pt is None:
                    skipped.append((ref, "unknown PTC %r" % part.mpn))
                    continue
                lines.append("R%s%s %s %s %s" % (prefix, ref, nm(tn[0]), nm(tn[1]), fmt(pt["r_ohm"])))
                emitted.append({"ref": ref, "kind": "ptc", "ohm": pt["r_ohm"], "note": pt["note"]})
            elif k == "IC":
                sub = subckt_map.get(ref, IC_SUBCKT.get(ref))
                if not sub:
                    skipped.append((ref, "no sub-circuit mapped"))
                    continue
                nodes = " ".join(nm(p.net) for p in self.pins_of(ref))
                lines.append("X%s%s %s %s" % (prefix, ref, nodes, sub))
                emitted.append({"ref": ref, "kind": "subckt", "subckt": sub})
            else:
                skipped.append((ref, "kind %s has no generic model" % k))
        return "\n".join(lines) + "\n", {"emitted": emitted, "skipped": skipped}


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refs", nargs="*", default=[])
    ap.add_argument("--nets", nargs="*", default=[])
    ap.add_argument("--bias", nargs="*", default=[], help="NET=VOLTS")
    ap.add_argument("--no-derate", action="store_true")
    args = ap.parse_args()
    bias = {}
    for b in args.bias:
        k, _, v = b.partition("=")
        bias[k] = float(v)
    d = Design()
    txt, rep = d.spice(refs=args.refs, nets=args.nets, bias=bias, derate=not args.no_derate)
    print(txt)
    for info in rep["emitted"]:
        if "eff_F" in info:
            print("* %-14s %s -> %s F (x%.2f @ %.1f V, %s)"
                  % (info["ref"], fmt(info["nominal_F"]), fmt(info["eff_F"]),
                     info["factor"], info.get("bias_V") or 0.0,
                     "curve" if info.get("trusted") else "ESTIMATE"))
    for ref, why in rep["skipped"]:
        print("* skipped %-14s %s" % (ref, why))


if __name__ == "__main__":
    main()
