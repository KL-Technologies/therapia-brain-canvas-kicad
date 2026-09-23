#!/usr/bin/env python3
"""S7j -- the ADS1299's VCAP bypass capacitors on the same layer as their pins.

    KPY scripts/73_bypass_caps.py [--root DIR] [--dry-run]

SBAS499C 12.1: "Do not place vias between bypass capacitors and the active
device." The harness's afe-adc S5_layout J1 found three that did, each
reaching its pin through two vias and a B.Cu run:

  C_VCAP4 (1 uF, pin 26)   sat 5.1 mm south of the pin
  C_VCAP3 (1 uF, pin 55)   sat 3.3 mm north-west of the pin
  C_VCAP1 (100 uF, pin 28) sits 7.7 mm south-east of the pin

What this does, measured on the board and nothing else:

* C_VCAP4 moves to directly under pin 26, turned to match C_VCAP1_H under
  pin 28 one pitch east (pad 1 at the pin, pad 2 below). Pad 1 lands on the
  pin's existing 1.36 mm F.Cu stub; pad 2 lands on the F.Cu AVSS bus at
  y 109.769 that every capacitor of this cluster returns to. The via in the
  stub, the B.Cu run and the old tie-in come out; S7d removes the old pad 2's
  AVSS via and its stub once they end in nothing.

* C_VCAP3 and C_VCAP3_H trade places. Both are 0402 on the same footprint
  with the same pad nets (1 = VCAP3, 2 = AVSS), so no copper moves: the 1 uF
  the datasheet asks for takes the spot 2.1 mm from pin 55 on a straight F.Cu
  line, and the 100 nF helper goes to the far spot. product.yaml names the
  1 uF as the one J1 judges (packs.afe-adc.ds_required_cap).

* C_VCAP1 is not moved. Its pin is walled in on F.Cu: pins 27 and 29 are
  0.22 mm away, C_VCAP1_H and C_VCAP2 sit 0.21 and 0.31 mm below and beside
  the pad, and south of them the AVSS bus (y 109.769, x 146.92-151.29) and
  the VREFP bus (y 111.496, x 145.92-151.75) run the full width of the
  cluster. A 0.2 mm track needs 0.378 mm between other nets and a 1206
  needs 1.8 x 3.2 mm. Recorded, not forced (logs/bypass_caps.json).

Writes logs/bypass_caps.json and gates/S7j.json.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import route as R                                  # noqa: E402
import epro as E                                   # noqa: E402

IU = R.IU

# C_VCAP4: footprint position/orientation; pad 1 must land at the pin stub end
VCAP4_AT = (146.912, 109.426, -90.0)
VCAP4_PAD1 = (146.912, 109.006)
VCAP4_REMOVE_TRACKS = [
    ("B.Cu", (146.9115, 109.0070), (148.0670, 111.7500)),
    ("B.Cu", (148.0670, 111.7500), (147.3685, 114.0360)),
    ("B.Cu", (147.3810, 114.0360), (147.5845, 114.2900)),
    ("B.Cu", (147.5845, 114.2900), (147.6860, 114.4425)),
    ("F.Cu", (147.6860, 114.4425), (147.5845, 113.2740)),
    ("F.Cu", (147.5845, 113.2740), (147.3810, 113.1725)),
    ("F.Cu", (147.3685, 113.1725), (148.0290, 112.7660)),
]
VCAP4_REMOVE_VIAS = [(146.9115, 109.0070), (147.6860, 114.4425)]

VCAP1_WALLS = {
    "pin_pitch_gap_mm": 0.22,
    "C_VCAP1_H_gap_below_pin_mm": 0.208,
    "C_VCAP1_H_to_C_VCAP2_gap_mm": 0.314,
    "track_needs_mm": round(0.2032 + 2 * 0.0889, 4),
    "AVSS_bus_F": "y 109.769, x 146.924..151.293",
    "VREFP_bus_F": "y 111.496, x 145.921..151.750",
    "C_VCAP1_body_mm": [3.2, 1.6],
}


def mm2(v):
    return round(v / float(IU), 4)


def find_track(board, net, lname, a, b):
    layer = board.GetLayerID(lname)
    want = {(round(a[0], 4), round(a[1], 4)), (round(b[0], 4), round(b[1], 4))}
    hits = [t for t in board.GetTracks()
            if t.GetClass() == "PCB_TRACK" and t.GetNetname() == net
            and t.GetLayer() == layer
            and {(mm2(t.GetStart().x), mm2(t.GetStart().y)),
                 (mm2(t.GetEnd().x), mm2(t.GetEnd().y))} == want]
    return hits


def find_via(board, net, at):
    return [t for t in board.GetTracks()
            if t.GetClass() == "PCB_VIA" and t.GetNetname() == net
            and (mm2(t.GetPosition().x), mm2(t.GetPosition().y))
            == (round(at[0], 4), round(at[1], 4))]


def pads_clear(pcbnew, board, idx, fp, clr):
    """Other-net copper within `clr` of any of the footprint's pads."""
    bad = []
    for p in fp.Pads():
        for layer in R.item_layers(pcbnew, p):
            sh = p.GetEffectiveShape(layer)
            for it in idx.shape_conflicts(sh, layer, clr, p.GetNetCode(),
                                          ignore=list(fp.Pads())):
                bad.append((p.GetNumber(), P.describe(board, it)))
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    root = a.root

    import pcbnew
    bpath = P.board_path(root)
    board = pcbnew.LoadBoard(bpath)
    log = {"step": "S7j", "moved": [], "removed": [], "not_done": {}}
    unc_before = P.unconnected_count(pcbnew, board)
    nets_before = P.pad_net_map(board, pcbnew)

    def place(ref, x, y, rot):
        fp = board.FindFootprintByReference(ref)
        before = {"ref": ref, "at_mm": [mm2(fp.GetPosition().x),
                                        mm2(fp.GetPosition().y)],
                  "rot": fp.GetOrientationDegrees(),
                  "pads": [{"pad": p.GetNumber(), "net": p.GetNetname(),
                            "at_mm": [mm2(p.GetPosition().x),
                                      mm2(p.GetPosition().y)]}
                           for p in fp.Pads()]}
        fp.SetPosition(pcbnew.VECTOR2I(P.nm(x), P.nm(y)))
        fp.SetOrientationDegrees(rot)
        after = {"at_mm": [mm2(fp.GetPosition().x), mm2(fp.GetPosition().y)],
                 "rot": fp.GetOrientationDegrees(),
                 "pads": [{"pad": p.GetNumber(), "net": p.GetNetname(),
                           "at_mm": [mm2(p.GetPosition().x),
                                     mm2(p.GetPosition().y)]}
                          for p in fp.Pads()]}
        log["moved"].append({"ref": ref, "before": before, "after": after})
        return fp

    done_vcap4 = False
    fp4 = board.FindFootprintByReference("C_VCAP4")
    if (mm2(fp4.GetPosition().x), mm2(fp4.GetPosition().y)) != VCAP4_AT[:2]:
        items = []
        for lname, s, e in VCAP4_REMOVE_TRACKS:
            h = find_track(board, "VCAP4", lname, s, e)
            if len(h) != 1:
                raise SystemExit("S7j: VCAP4 %s %s-%s found %d times -- this "
                                 "is not the board the edit was measured on"
                                 % (lname, s, e, len(h)))
            items += h
        for at in VCAP4_REMOVE_VIAS:
            h = find_via(board, "VCAP4", at)
            if len(h) != 1:
                raise SystemExit("S7j: VCAP4 via %s found %d times" % (at, len(h)))
            items += h
        log["removed"] += [P.describe(board, t) for t in items]
        for t in items:
            board.RemoveNative(t)
        fp4 = place("C_VCAP4", *VCAP4_AT)
        p1 = [p for p in fp4.Pads() if p.GetNumber() == "1"][0]
        if (mm2(p1.GetPosition().x), mm2(p1.GetPosition().y)) != VCAP4_PAD1:
            raise SystemExit("S7j: C_VCAP4 pad 1 landed at %s" %
                             [mm2(p1.GetPosition().x), mm2(p1.GetPosition().y)])
        done_vcap4 = True

    swapped = False
    f3 = board.FindFootprintByReference("C_VCAP3")
    f3h = board.FindFootprintByReference("C_VCAP3_H")
    if (mm2(f3.GetPosition().x), mm2(f3.GetPosition().y)) == (144.118, 94.262):
        p3 = (f3.GetPosition().x, f3.GetPosition().y, f3.GetOrientationDegrees())
        p3h = (f3h.GetPosition().x, f3h.GetPosition().y,
               f3h.GetOrientationDegrees())
        place("C_VCAP3", p3h[0] / float(IU), p3h[1] / float(IU), p3h[2])
        place("C_VCAP3_H", p3[0] / float(IU), p3[1] / float(IU), p3[2])
        swapped = True

    idx = R.CopperIndex(pcbnew, board)
    clash = []
    for ref in ("C_VCAP4", "C_VCAP3", "C_VCAP3_H"):
        clash += [(ref,) + c for c in pads_clear(
            pcbnew, board, idx, board.FindFootprintByReference(ref),
            P.CLEARANCE)]
    unc_after = P.unconnected_count(pcbnew, board)
    same_nets = P.pad_net_map(board, pcbnew) == nets_before
    log["not_done"]["C_VCAP1"] = VCAP1_WALLS
    log.update({"vcap4_moved": done_vcap4, "vcap3_swapped": swapped,
                "pad_clashes": clash, "unconnected": [unc_before, unc_after],
                "pad_nets_unchanged": same_nets})
    ok = not clash and unc_after <= unc_before and same_nets
    if ok and (done_vcap4 or swapped) and not a.dry_run:
        board.Save(bpath)
    E.dump_json(os.path.join(root, "logs", "bypass_caps.json"), log)
    checks = [
        P.check("new pads clear other nets by the rule", 0, len(clash),
                note=str(clash[:3])),
        P.check("unconnected items", unc_before, unc_after,
                ok=unc_after <= unc_before),
        P.check("every pad on the net it had", True, same_nets),
    ]
    P.gate(root, "S7j", checks,
           notes="C_VCAP4 under pin 26 (%s), C_VCAP3 <-> C_VCAP3_H swapped "
                 "(%s); C_VCAP1 not moved -- walled in on F.Cu, see "
                 "logs/bypass_caps.json." % (done_vcap4, swapped))
    bad = [c["name"] for c in checks if not c["pass"]]
    print("S7j: %s" % ("pass" if not bad else "FAIL " + ", ".join(bad)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
