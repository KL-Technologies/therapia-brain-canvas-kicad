#!/usr/bin/env python3
"""S7_viapad -- ACCEPTANCE I: no via drill opens inside a solder-mask opening.

    python3 scripts/67_viapad_gate.py [--root DIR] [--harness DIR]

The board is ordered Via Covering = Tented on a 4-layer JLC process
(product.yaml fab.via.covering: none): nothing plugs a barrel. A via whose
drill lies in a pad's mask opening takes the paste printed on that pad down
the hole in reflow. Rev.A as first put in the cart had 106 such vias and
A-H had no clause that looked (STATUS.md, 2026-09-23); this is the clause.

Two readers, and both must say 0:

1. **This script, from the package that is uploaded.** Vias are the PTH
   Excellon hits of at most VIA_DRILL_MAX_MM; openings are the dark shapes
   of F_Mask, B_Mask and F_Paste as lib/gerber_parse reads them (KiCad plots
   mask openings as G36/G37 regions). A via counts when its drill circle
   comes within RASTER_TOL_MM of an opening -- the harness's verdict margin.
   Openings that hold a component hole (a THT pad) are not SMD openings and
   are reported apart. A planted via at the centre of an SMD opening must be
   counted, or the gate fails: an empty count from a reader that sees
   nothing is not a pass.

2. **The harness's S7_viapad** (therapia-pcb-harness, pcbharness.gates.
   s7_viapad), run on this repo: its board half reads the .kicad_pcb as text,
   its fab half reads fab/gerber. Its verdict and its count are copied into
   this gate. The harness is found at --harness, $PCB_HARNESS, or
   ../pcb-harness; if it is not there the gate fails rather than pass on one
   reader.
"""

import argparse
import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import gerber_parse as G                           # noqa: E402
import epro as E                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = "Therapia_EEG-HRV"
VIA_DRILL_MAX_MM = 0.5          # vias are 0.305; the smallest component hole 0.6
RASTER_TOL_MM = 0.005           # harness core.viapad.J_RASTER_TOL_MM


def check(name, expected, actual, ok=None, note=None):
    return E.gate_check(name, expected, actual, ok=ok, note=note)


def opening_gap(layer, x, y, r):
    """Smallest (signed distance to an opening) - r over the dark shapes."""
    best = None
    for kind, item in layer._near(x, y, r + 1.0):
        if kind == "f":
            fx, fy, ap = item[0], item[1], item[2]
            d = ap.distance_to(x - fx, y - fy)
            shape = ("flash", round(fx, 4), round(fy, 4))
        elif kind == "r":
            d = G._polygon_distance(x, y, item)
            xs = [p[0] for p in item]
            ys = [p[1] for p in item]
            shape = ("region", round((min(xs) + max(xs)) / 2, 4),
                     round((min(ys) + max(ys)) / 2, 4))
        else:
            continue
        g = d - r
        if best is None or g < best[0]:
            best = (g, shape, item, kind)
    return best


def holds_hole(kind, item, holes):
    """Does this opening contain a component hole (so it is a THT pad)?"""
    for hx, hy in holes:
        if kind == "f":
            if item[2].distance_to(hx - item[0], hy - item[1]) <= 0:
                return True
        elif kind == "r":
            if G._point_in_polygon(hx, hy, item):
                return True
    return False


def gerber_count(fab):
    gdir = os.path.join(fab, "gerber")
    layers = {}
    for name, suffix in (("F.Mask", "-F_Mask.gts"), ("B.Mask", "-B_Mask.gbs"),
                         ("F.Paste", "-F_Paste.gtp")):
        layers[name] = G.parse_gerber(os.path.join(gdir, BOARD + suffix))
    drill = G.parse_excellon(os.path.join(gdir, BOARD + "-PTH.drl"))
    vias, comp = [], []
    for h in drill["hits"]:
        (vias if h["dia"] is not None and h["dia"] <= VIA_DRILL_MAX_MM
         else comp).append(h)
    npth = G.parse_excellon(os.path.join(gdir, BOARD + "-NPTH.drl"))
    holes = [(h["x"], h["y"]) for h in comp + npth["hits"]]

    rows, tht, gaps = [], [], []
    for v in vias:
        r = v["dia"] / 2.0
        worst = None
        for lname, layer in layers.items():
            got = opening_gap(layer, v["x"], v["y"], r)
            if got is None:
                continue
            if worst is None or got[0] < worst[0]:
                worst = got + (lname,)
        if worst is None:
            continue
        g, shape, item, kind, lname = worst
        gaps.append(g)
        if g < RASTER_TOL_MM:
            rec = {"at_gerber_mm": [v["x"], v["y"]], "drill_mm": v["dia"],
                   "layer": lname, "opening": shape, "gap_mm": round(g, 4),
                   "relation": "inside" if g <= -2 * r else "crossing"}
            (tht if holds_hole(kind, item, holes) else rows).append(rec)

    # negative control: a via at the centre of the first SMD opening on F.Mask
    control = None
    f_mask = layers["F.Mask"]
    for poly, dark, _at in f_mask.regions:
        if not dark:
            continue
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        if holds_hole("r", poly, holes):
            continue
        got = opening_gap(f_mask, cx, cy, 0.1524)
        control = {"at_gerber_mm": [round(cx, 4), round(cy, 4)],
                   "gap_mm": round(got[0], 4) if got else None,
                   "counted": bool(got and got[0] < RASTER_TOL_MM)}
        break
    return {"vias": len(vias), "component_holes": len(comp),
            "openings": {k: l.counts() for k, l in layers.items()},
            "in_smd_opening": rows, "in_tht_opening": tht,
            "min_gap_mm": round(min(gaps), 4) if gaps else None,
            "control": control}


def harness_dir(arg):
    for cand in (arg, os.environ.get("PCB_HARNESS"),
                 os.path.join(os.path.dirname(ROOT), "pcb-harness")):
        if cand and os.path.isfile(os.path.join(cand, "pcbharness", "gates",
                                                "s7_viapad.py")):
            return os.path.abspath(cand)
    return None


def run_harness(root, hdir):
    out = os.path.join(root, "logs", "harness_S7_viapad.json")
    log = os.path.join(root, "logs", "harness_S7_viapad.log")
    if os.path.exists(out):
        os.remove(out)
    proc = subprocess.run(
        [sys.executable, "-m", "pcbharness.gates.s7_viapad", "--root", root,
         "--out", out, "--log", log],
        cwd=hdir, capture_output=True, text=True)
    doc = None
    if os.path.exists(out):
        with open(out) as f:
            doc = json.load(f)
    return proc, doc


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--harness", default=None)
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    fab = os.path.join(root, "fab")

    g = gerber_count(fab)
    hdir = harness_dir(a.harness)
    h_doc, h_rc, h_tail = None, None, ""
    if hdir:
        proc, h_doc = run_harness(root, hdir)
        h_rc = proc.returncode
        h_tail = ((proc.stdout or "") + (proc.stderr or ""))[-800:]
    h_board = None
    if h_doc:
        for c in h_doc.get("checks", ()):
            if c.get("name") == "J_via_in_an_smd_opening_on_the_board":
                h_board = c.get("actual")

    checks = [
        check("I vias read from the PTH drill file", "> 0", g["vias"],
              ok=g["vias"] > 0),
        check("I solder-mask openings read (F.Mask regions)", "> 0",
              g["openings"]["F.Mask"]["regions"],
              ok=g["openings"]["F.Mask"]["regions"] > 0),
        check("I vias whose drill crosses an SMD opening (Gerber)", 0,
              len(g["in_smd_opening"])),
        check("I negative control: a via planted in an SMD opening is "
              "counted", True, bool(g["control"] and g["control"]["counted"])),
        check("I harness found", True, bool(hdir),
              note="--harness, $PCB_HARNESS or ../pcb-harness"),
        check("I harness S7_viapad passes (board and fab halves)", True,
              bool(h_doc and h_doc.get("pass")),
              note="exit %s" % h_rc),
        check("I harness board census: vias in an SMD opening", 0,
              (h_board or {}).get("in_opening") if isinstance(h_board, dict)
              else h_board),
    ]
    E.write_gate(os.path.join(root, "gates", "S7_viapad.json"), "S7_viapad",
                 checks,
                 notes="ACCEPTANCE I. Vias %d, openings F.Mask %d / B.Mask %d "
                       "regions; %d vias in an SMD opening, %d in a THT "
                       "opening; nearest drill-to-opening gap %s mm. Harness "
                       "S7_viapad: %s."
                       % (g["vias"], g["openings"]["F.Mask"]["regions"],
                          g["openings"]["B.Mask"]["regions"],
                          len(g["in_smd_opening"]), len(g["in_tht_opening"]),
                          g["min_gap_mm"],
                          "pass" if h_doc and h_doc.get("pass") else "FAIL"),
                 extra={"gerber": g, "harness_dir": hdir,
                        "harness_exit": h_rc, "harness_tail": h_tail,
                        "harness_checks": (h_doc or {}).get("checks")})
    bad = [c["name"] for c in checks if not c["pass"]]
    print("S7_viapad: %s" % ("pass" if not bad else "FAIL " + ", ".join(bad)))
    print("  vias %d, in SMD opening %d, in THT opening %d, min gap %s mm"
          % (g["vias"], len(g["in_smd_opening"]), len(g["in_tht_opening"]),
             g["min_gap_mm"]))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
