#!/usr/bin/env python3
"""S7p -- clip the footprints' own F.Paste drawings back inside their pads.

    KPY scripts/68_fix_paste_graphics.py [--root DIR] [--dry-run]

The EasyEDA import gave 50 footprints F.Paste polygons of their own, drawn
beside the pads (178 shapes: every 0805, the C_DIF 1206s, the ferrites, the
ADS1299's 64 lands, J1). KiCad plots them into the stencil together with each
pad's own paste, so the stencil opening is the union -- and 168 of the 178
reach past the copper: 0.134 mm on six 0805s (R_BIAS_SER, R_SRB_SER, R_SCLK,
R_MISO, R_MOSI, R_BIAS_FB), 0.088 mm on sixteen more, 0.076 mm on each side of
every ADS1299 land, where the gap between lands is 0.22 mm. Paste printed on
bare mask beads into solder balls or bridges to the next land.

Each such shape is replaced by its intersection with the union of its own
footprint's F.Cu pads; a shape with nothing left inside a pad is deleted.
Shapes already inside a pad are left exactly as they are. Every pad here is on
F.Paste itself with a 0 mm paste margin, so after this the stencil opening is
the pad and nothing more.

Writes logs/paste_fix.json and gates/S7p.json.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import epro as E                                   # noqa: E402

IU = 1000000
TOL_MM2 = 1e-4                  # area outside the pads that counts as none


def pad_union(pcbnew, fp):
    u = pcbnew.SHAPE_POLY_SET()
    for p in fp.Pads():
        if p.IsOnLayer(pcbnew.F_Cu):
            s = pcbnew.SHAPE_POLY_SET()
            p.TransformShapeToPolygon(s, pcbnew.F_Cu, 0, 1000,
                                      pcbnew.ERROR_INSIDE)
            u.BooleanAdd(s)
    return u


def shape_poly(pcbnew, g):
    s = pcbnew.SHAPE_POLY_SET()
    g.TransformShapeToPolygon(s, g.GetLayer(), 0, 1000, pcbnew.ERROR_INSIDE)
    return s


def outside(pcbnew, poly, pads):
    """(area mm2, largest distance mm) of `poly` lying outside `pads`."""
    rest = pcbnew.SHAPE_POLY_SET(poly)
    rest.BooleanSubtract(pads)
    worst = 0.0
    for i in range(poly.OutlineCount()):
        o = poly.Outline(i)
        for k in range(o.PointCount()):
            pt = o.CPoint(k)
            if not pads.Contains(pt):
                worst = max(worst, pads.SquaredDistance(pt) ** 0.5 / IU)
    return rest.Area() / float(IU) ** 2, worst


def census(pcbnew, board):
    rows = []
    for fp in board.GetFootprints():
        pads = None
        for g in fp.GraphicalItems():
            if g.GetLayer() not in (pcbnew.F_Paste, pcbnew.B_Paste):
                continue
            pads = pads or pad_union(pcbnew, fp)
            a, d = outside(pcbnew, shape_poly(pcbnew, g), pads)
            rows.append((fp, g, a, d))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    root = a.root

    import pcbnew
    bpath = P.board_path(root)
    board = pcbnew.LoadBoard(bpath)
    before = census(pcbnew, board)
    bad = [r for r in before if r[2] > TOL_MM2]
    log = {"step": "S7p", "shapes": len(before), "protruding_before": len(bad),
           "worst_before_mm": round(max([r[3] for r in bad] + [0]), 4),
           "clipped": [], "deleted": []}

    for fp, g, area, dist in bad:
        pads = pad_union(pcbnew, fp)
        keep = shape_poly(pcbnew, g)
        keep.BooleanIntersection(pads)
        rec = {"ref": fp.GetReference(),
               "layer": board.GetLayerName(g.GetLayer()),
               "outside_mm2": round(area, 4), "reach_mm": round(dist, 4)}
        layer = g.GetLayer()
        fp.Remove(g)
        if keep.OutlineCount() == 0 or keep.Area() <= 0:
            log["deleted"].append(rec)
            continue
        for i in range(keep.OutlineCount()):
            one = pcbnew.SHAPE_POLY_SET()
            one.AddOutline(keep.Outline(i))
            for h in range(keep.HoleCount(i)):
                one.AddHole(keep.Hole(i, h))
            s = pcbnew.PCB_SHAPE(fp)
            s.SetShape(pcbnew.SHAPE_T_POLY)
            s.SetPolyShape(one)
            s.SetLayer(layer)
            s.SetWidth(0)
            s.SetFilled(True)
            fp.Add(s)
        rec["outlines"] = keep.OutlineCount()
        log["clipped"].append(rec)

    after = census(pcbnew, board)
    left = [r for r in after if r[2] > TOL_MM2]
    log.update({"shapes_after": len(after), "protruding_after": len(left),
                "worst_after_mm": round(max([r[3] for r in left] + [0]), 4)})
    if not a.dry_run and bad:
        board.Save(bpath)
    E.dump_json(os.path.join(root, "logs", "paste_fix.json"), log)

    # negative control: a copy of a pad's paste nudged 0.1 mm off it is caught
    control = None
    for fp in board.GetFootprints():
        pads = [p for p in fp.Pads() if p.IsOnLayer(pcbnew.F_Paste)]
        if pads:
            s = pcbnew.SHAPE_POLY_SET()
            pads[0].TransformShapeToPolygon(s, pcbnew.F_Cu, 0, 1000,
                                            pcbnew.ERROR_INSIDE)
            s.Move(pcbnew.VECTOR2I(int(0.1 * IU), 0))
            ar, d = outside(pcbnew, s, pad_union(pcbnew, fp))
            control = {"ref": fp.GetReference(), "reach_mm": round(d, 4),
                       "caught": ar > TOL_MM2}
            break
    checks = [
        P.check("J footprint paste shapes measured", "> 0", len(before),
                ok=len(before) > 0),
        P.check("J paste shapes reaching past their pads", 0, len(left)),
        P.check("J negative control: paste moved 0.1 mm off its pad is "
                "caught", True, bool(control and control["caught"])),
    ]
    P.gate(root, "S7p", checks,
           notes="%d footprint paste shapes, %d reached past their pads "
                 "(worst %.4f mm); %d clipped, %d deleted; %d left."
                 % (len(before), len(bad), log["worst_before_mm"],
                    len(log["clipped"]), len(log["deleted"]), len(left)),
           extra={"control": control})
    fails = [c["name"] for c in checks if not c["pass"]]
    print("S7p: %s" % ("pass" if not fails else "FAIL " + ", ".join(fails)))
    print("  %d shapes, %d protruding -> %d (clipped %d, deleted %d)"
          % (len(before), len(bad), len(left), len(log["clipped"]),
             len(log["deleted"])))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
