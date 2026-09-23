#!/usr/bin/env python3
"""S7_paste -- ACCEPTANCE J: every stencil opening lies on its pad's copper.

    python3 scripts/69_paste_gate.py [--root DIR]

Read from the package that is uploaded, not from the board: F_Paste against
F_Cu, both through lib/gerber_parse. The pads are the F_Cu flashes and
regions that carry a pad attribute (%TO.P%); vias and tracks do not count as
somewhere paste may go. Each paste shape is walked round its outline --
region vertices and edge midpoints, and for a flash the aperture's own edge
found along 48 rays -- and every point must lie on a pad, within TOL_MM.

S7p (scripts/68_fix_paste_graphics.py) is what makes this pass on Rev.A: the
EasyEDA import drew 168 paste shapes past their pads, up to 0.134 mm.

Negative control: a paste region moved 0.1 mm sideways is walked the same
way and must be caught, or the gate fails.
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
TOL_MM = 0.002
RAYS = 48


def check(name, expected, actual, ok=None, note=None):
    return E.gate_check(name, expected, actual, ok=ok, note=note)


def flash_outline(x, y, ap):
    """Points on a flash's edge: bisect distance_to along each ray."""
    pts = []
    R = ap.outer_radius() * 1.5 + 0.01
    for k in range(RAYS):
        t = 2 * math.pi * k / RAYS
        lo, hi = 0.0, R
        for _ in range(30):
            mid = (lo + hi) / 2
            if ap.distance_to(mid * math.cos(t), mid * math.sin(t)) <= 0:
                lo = mid
            else:
                hi = mid
        pts.append((x + lo * math.cos(t), y + lo * math.sin(t)))
    return pts


def region_outline(poly):
    pts = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        pts += [a, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)]
    return pts


class Pads(object):
    def __init__(self, cu):
        self.flashes = [(x, y, ap) for x, y, ap, dk, at in cu.flashes
                        if dk and at.get("P")]
        self.regions = [poly for poly, dk, at in cu.regions
                        if dk and at.get("P")]
        self.cell = 2.0
        self.grid = {}
        for f in self.flashes:
            h = f[2].outer_radius()
            self._put(("f", f), f[0] - h, f[1] - h, f[0] + h, f[1] + h)
        for poly in self.regions:
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            self._put(("r", poly), min(xs), min(ys), max(xs), max(ys))

    def _put(self, item, x0, y0, x1, y1):
        c = self.cell
        for gx in range(int(math.floor(x0 / c)), int(math.floor(x1 / c)) + 1):
            for gy in range(int(math.floor(y0 / c)),
                            int(math.floor(y1 / c)) + 1):
                self.grid.setdefault((gx, gy), []).append(item)

    def distance(self, x, y):
        """Signed distance to the nearest pad (negative inside)."""
        best = None
        c = self.cell
        for kind, item in self.grid.get((int(math.floor(x / c)),
                                         int(math.floor(y / c))), ()):
            if kind == "f":
                d = item[2].distance_to(x - item[0], y - item[1])
            else:
                d = G._polygon_distance(x, y, item)
            if best is None or d < best:
                best = d
        return best if best is not None else float("inf")


def walk(pads, pts):
    """Largest distance by which any point of the outline leaves the pads."""
    return max(pads.distance(x, y) for x, y in pts)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=ROOT)
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    gdir = os.path.join(root, "fab", "gerber")
    paste = G.parse_gerber(os.path.join(gdir, BOARD + "-F_Paste.gtp"))
    cu = G.parse_gerber(os.path.join(gdir, BOARD + "-F_Cu.gtl"))
    pads = Pads(cu)

    shapes = []
    for x, y, ap_, dk, _at in paste.flashes:
        if dk:
            shapes.append(("flash", (round(x, 4), round(y, 4)),
                           flash_outline(x, y, ap_)))
    for poly, dk, _at in paste.regions:
        if dk:
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            shapes.append(("region", (round((min(xs) + max(xs)) / 2, 4),
                                      round((min(ys) + max(ys)) / 2, 4)),
                           region_outline(poly)))
    off = []
    worst = 0.0
    for kind, at, pts in shapes:
        d = walk(pads, pts)
        worst = max(worst, d)
        if d > TOL_MM:
            off.append({"kind": kind, "at_gerber_mm": list(at),
                        "past_pad_mm": round(d, 4)})

    control = None
    for kind, at, pts in shapes:
        if kind == "region":
            moved = [(x + 0.1, y) for x, y in pts]
            d = walk(pads, moved)
            control = {"at_gerber_mm": list(at), "past_pad_mm": round(d, 4),
                       "caught": d > TOL_MM}
            break

    checks = [
        check("J pads read from F_Cu (pad-attributed flashes and regions)",
              "> 0", len(pads.flashes) + len(pads.regions),
              ok=len(pads.flashes) + len(pads.regions) > 0),
        check("J stencil openings read from F_Paste", "> 0", len(shapes),
              ok=len(shapes) > 0),
        check("J stencil openings reaching past their pad (> %.3f mm)"
              % TOL_MM, 0, len(off)),
        check("J negative control: an opening moved 0.1 mm off its pad is "
              "caught", True, bool(control and control["caught"])),
    ]
    E.write_gate(os.path.join(root, "gates", "S7_paste.json"), "S7_paste",
                 checks,
                 notes="ACCEPTANCE J. %d stencil openings against %d pads; "
                       "%d reach past their pad; the furthest point is "
                       "%.4f mm %s the copper."
                       % (len(shapes), len(pads.flashes) + len(pads.regions),
                          len(off), abs(worst),
                          "outside" if worst > 0 else "inside"),
                 extra={"offenders": off[:200], "control": control})
    bad = [c["name"] for c in checks if not c["pass"]]
    print("S7_paste: %s" % ("pass" if not bad else "FAIL " + ", ".join(bad)))
    print("  %d openings, %d past their pad, worst %.4f mm"
          % (len(shapes), len(off), worst))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
