#!/usr/bin/env python3
"""S7_maskweb -- ACCEPTANCE L: a 0.1 mm solder-mask dam between two nets.

    python3 scripts/72_mask_web_gate.py [--root DIR]

Read from the uploaded package. Each opening of F_Mask and B_Mask (KiCad
plots them as G36/G37 regions) is given the nets of the pads under it, from
the pad flashes and regions of F_Cu / B_Cu and their %TO.N% attributes. The
dam between two openings is the smallest distance between their outlines.
Two openings that carry different nets must be at least WEB_MM apart; JLC
removes a narrower green dam and the openings print as one. Openings of one
net are reported and not judged.

S7m (scripts/71_mask_webs.py) is what makes this pass on Rev.A: 22 pad pairs
of different nets were under 0.1 mm with the board-wide 0.0508 mm expansion.

Negative control: two openings of different nets are moved together until
their dam is 0.05 mm and the same measurement must catch it.
"""

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import gerber_parse as G                           # noqa: E402
import epro as E                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = "Therapia_EEG-HRV"
WEB_MM = 0.10                   # ACCEPTANCE L: JLC's floor
TARGET_MM = 0.105               # S7m's design target, 0.005 of margin
TOL_MM = 0.0005                 # coordinate rounding in the Gerber, no more


def check(name, expected, actual, ok=None, note=None):
    return E.gate_check(name, expected, actual, ok=ok, note=note)


def bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def poly_gap(a, b):
    """Smallest distance between two non-overlapping polygon outlines."""
    d1 = min(G._polygon_distance(x, y, b) for x, y in a)
    d2 = min(G._polygon_distance(x, y, a) for x, y in b)
    return min(d1, d2)


def openings(mask, cu):
    """[(poly, bbox, nets)] -- each opening and the nets of the pads in it."""
    pads = [(x, y, at.get("N")) for x, y, _ap, dk, at in cu.flashes
            if dk and at.get("P")]
    for poly, dk, at in cu.regions:
        if dk and at.get("P"):
            bx = bbox(poly)
            pads.append(((bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2, at.get("N")))
    out = []
    for poly, dk, _at in mask.regions:
        if not dk:
            continue
        bx = bbox(poly)
        nets = set()
        for x, y, n in pads:
            if bx[0] <= x <= bx[2] and bx[1] <= y <= bx[3] \
                    and G._point_in_polygon(x, y, poly):
                nets.add(n or "")
        out.append((poly, bx, nets))
    return out


def judge(ops, web=WEB_MM):
    bad, same, worst = [], 0, None
    reach = web + 0.05
    for i, (pa, ba, na) in enumerate(ops):
        for pb, bb, nb in ops[i + 1:]:
            if (bb[0] > ba[2] + reach or ba[0] > bb[2] + reach
                    or bb[1] > ba[3] + reach or ba[1] > bb[3] + reach):
                continue
            g = poly_gap(pa, pb)
            if g >= web - TOL_MM:
                continue
            if na and nb and na == nb and len(na) == 1:
                same += 1
                continue
            worst = g if worst is None else min(worst, g)
            bad.append({"nets": [sorted(na), sorted(nb)],
                        "at_gerber_mm": [round((ba[0] + ba[2]) / 2, 4),
                                         round((ba[1] + ba[3]) / 2, 4)],
                        "dam_mm": round(g, 4)})
    return bad, same, worst


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=ROOT)
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    g = os.path.join(root, "fab", "gerber", BOARD)
    sides = {}
    for side, m, c in (("F", "-F_Mask.gts", "-F_Cu.gtl"),
                       ("B", "-B_Mask.gbs", "-B_Cu.gbl")):
        sides[side] = openings(G.parse_gerber(g + m), G.parse_gerber(g + c))
    result, off, under_target = {}, [], []
    for side, ops in sides.items():
        bad, same, worst = judge(ops)
        result[side] = {"openings": len(ops), "different_net_under": len(bad),
                        "same_net_under": same, "worst_mm": worst}
        off += [dict(r, side=side) for r in bad]
        tbad, _s, tworst = judge(ops, TARGET_MM)
        result[side]["under_target"] = len(tbad)
        result[side]["worst_under_target_mm"] = tworst
        under_target += [dict(r, side=side) for r in tbad]
    # an opening with no pad under it must be a bare hole (an NPTH), nothing else
    npth = G.parse_excellon(g + "-NPTH.drl")["hits"]
    unnetted = [(round((b[0] + b[2]) / 2, 3), round((b[1] + b[3]) / 2, 3))
                for ops in sides.values() for p, b, n in ops
                if not n and not any(G._point_in_polygon(h["x"], h["y"], p)
                                     for h in npth)]

    # negative control: the nearest different-net pair on F, pushed together
    control = None
    ops = sides["F"]
    best = None
    for i, (pa, ba, na) in enumerate(ops):
        for pb, bb, nb in ops[i + 1:]:
            if not na or not nb or na == nb:
                continue
            if bb[0] > ba[2] + 0.5 or ba[0] > bb[2] + 0.5 \
                    or bb[1] > ba[3] + 0.5 or ba[1] > bb[3] + 0.5:
                continue
            gap = poly_gap(pa, pb)
            if best is None or gap < best[0]:
                best = (gap, pa, pb, ba, bb)
    if best:
        gap, pa, pb, ba, bb = best
        ca = ((ba[0] + ba[2]) / 2, (ba[1] + ba[3]) / 2)
        cb = ((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2)
        d = math.hypot(cb[0] - ca[0], cb[1] - ca[1]) or 1.0
        shift = gap - 0.05
        moved = [(x - (cb[0] - ca[0]) / d * shift,
                  y - (cb[1] - ca[1]) / d * shift) for x, y in pb]
        g2 = poly_gap(pa, moved)
        control = {"dam_before_mm": round(gap, 4), "dam_planted_mm": round(g2, 4),
                   "caught": g2 < WEB_MM - TOL_MM}

    checks = [
        check("L solder-mask openings read and given their pads' nets", 0,
              len(unnetted), note="%d F / %d B openings; the count is "
                                  "openings with neither a pad nor an NPTH "
                                  "under them: %s" % (len(sides["F"]),
                                                      len(sides["B"]),
                                                      unnetted[:5])),
        check("L dams under %.2f mm between openings of different nets"
              % WEB_MM, 0, len(off)),
        check("L dams under the %.3f mm design target between openings of "
              "different nets" % TARGET_MM, 0, len(under_target),
              note=str(under_target[:5])),
        check("L negative control: two different-net openings pushed to a "
              "0.05 mm dam are caught", True,
              bool(control and control["caught"])),
    ]
    E.write_gate(os.path.join(root, "gates", "S7_maskweb.json"), "S7_maskweb",
                 checks,
                 notes="ACCEPTANCE L. F: %s. B: %s."
                       % (result["F"], result["B"]),
                 extra={"sides": result, "offenders": off[:100],
                        "control": control})
    bad = [c["name"] for c in checks if not c["pass"]]
    print("S7_maskweb: %s" % ("pass" if not bad else "FAIL " + ", ".join(bad)))
    print("  F %s  B %s" % (result["F"], result["B"]))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
