#!/usr/bin/env python3
"""S7n -- the copper this revision added keeps 0.127 mm to other nets.

    KPY scripts/74_new_copper_clearance.py [--root DIR]

ACCEPTANCE C's error rule is 0.0889 mm (3.5 mil) and the board's
recommendation 0.127 mm (5 mil). Y9's repairs (S7v, S7j) laid new tracks and
vias; QA found two of them 0.092 mm from their neighbours. This finds every
item on the board that one of those steps laid -- by its geometry, from
logs/viapad_fix.json and logs/bypass_caps.json -- plus C_VCAP4's pads, and
measures its copper gap to every other net's track, via and pad.

An item under 0.127 mm fails unless it is listed in ALLOWED with the most
the geometry allows and why.

Writes logs/new_copper_clearance.json and gates/S7n.json.
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
WANT = int(0.127 * IU)
# (kind, net, key) -> why. key is pos for a via, (start, end) for a track.
ALLOWED = {
    ("via", "GND", (173.34, 110.226)):
        "R_CC2.2's via between the resistor's own pads: 0.70 mm of copper "
        "between them holds a 0.46 via with 0.12 mm each side; 0.127 needs a "
        "0.446 via, under the 0.452 a 0.30 drill needs for the 0.076 annulus",
    ("track", "ADS_RESET_N", ((173.34, 82.032), (173.34, 105.1))):
        "Y8's own ADS_RESET_N trunk, only shortened to its new join; its "
        "0.1018 mm to an ADS_CS_N via is the imported board's, not new copper",
}


def r4(v):
    return round(v / float(IU), 4)


def logged(root):
    """Every track and via S7v and S7j say they laid."""
    out = set()
    for name in ("viapad_fix", "bypass_caps"):
        path = os.path.join(root, "logs", name + ".json")
        if not os.path.exists(path):
            continue
        stack = [E.load_json(path)]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if cur.get("kind") == "via" and "pos_mm" in cur:
                    out.add(("via", cur["net"], tuple(cur["pos_mm"])))
                elif cur.get("kind") == "track" and "start_mm" in cur:
                    out.add(("track", cur["net"], cur["layer"],
                             tuple(sorted([tuple(cur["start_mm"]),
                                           tuple(cur["end_mm"])]))))
                stack += list(cur.values())
            elif isinstance(cur, list):
                stack += cur
    return out


def key(board, t):
    if t.GetClass() == "PCB_VIA":
        return ("via", t.GetNetname(), (r4(t.GetPosition().x),
                                        r4(t.GetPosition().y)))
    return ("track", t.GetNetname(), board.GetLayerName(t.GetLayer()),
            tuple(sorted([(r4(t.GetStart().x), r4(t.GetStart().y)),
                          (r4(t.GetEnd().x), r4(t.GetEnd().y))])))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=P.ROOT)
    a = ap.parse_args()
    import pcbnew
    board = pcbnew.LoadBoard(P.board_path(a.root))
    want = logged(a.root)
    items = [t for t in board.GetTracks() if key(board, t) in want]
    fp = board.FindFootprintByReference("C_VCAP4")
    items += list(fp.Pads()) if fp else []
    others = list(board.GetTracks()) + [p for f in board.GetFootprints()
                                        for p in f.Pads()]
    rows = []
    ceiling = int(0.3 * IU)
    for it in items:
        best = None
        for layer in R.item_layers(pcbnew, it):
            sa = it.GetEffectiveShape(layer)
            bb = sa.BBox(ceiling)
            for o in others:
                if o.GetNetCode() == it.GetNetCode() or not o.IsOnLayer(layer):
                    continue
                if not bb.Intersects(o.GetBoundingBox()):
                    continue
                g = P._actual_gap(sa, o.GetEffectiveShape(layer), ceiling,
                                  steps=14)
                if g is not None and (best is None or g < best[0]):
                    best = (g, o, layer)
        if best and best[0] < WANT:
            d = P.describe(board, it)
            k = ((d["kind"], d["net"], tuple(d["pos_mm"]))
                 if d["kind"] == "via" else
                 (d["kind"], d["net"], tuple(sorted([tuple(d["start_mm"]),
                                                     tuple(d["end_mm"])])))
                 if d["kind"] == "track" else None)
            rows.append({"item": d, "gap_mm": r4(best[0]),
                         "to": P.describe(board, best[1]),
                         "layer": board.GetLayerName(best[2]),
                         "allowed": ALLOWED.get(k)})
    bad = [r for r in rows if not r["allowed"]]
    E.dump_json(os.path.join(a.root, "logs", "new_copper_clearance.json"),
                {"items_measured": len(items), "under_0.127": rows})
    checks = [
        P.check("new tracks, vias and pads measured", "> 0", len(items),
                ok=len(items) > 0),
        P.check("new copper under 0.127 mm to another net (not allowed)", 0,
                len(bad), note=str([(r["item"].get("net"), r["gap_mm"])
                                    for r in bad][:8])),
        P.check("new copper under 0.127 mm, allowed with its limit", "listed",
                [(r["item"].get("net"), r["gap_mm"]) for r in rows
                 if r["allowed"]], ok=True),
    ]
    P.gate(a.root, "S7n", checks,
           notes="%d items laid by S7v/S7j measured; %d under 0.127 mm, %d of "
                 "them allowed." % (len(items), len(rows),
                                    len(rows) - len(bad)))
    print("S7n: %s  (%d measured, %d under 0.127, %d allowed)"
          % ("pass" if not bad else "FAIL", len(items), len(rows),
             len(rows) - len(bad)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
