#!/usr/bin/env python3
"""Print the board facts the S6 and S7 gates have to assert on.

    KPY scripts/42_board_facts.py [--json]

Read-only. Everything here is measured from the board, not carried forward from
an earlier step's log, so a gate that quotes it is quoting the board.

  npth        the six mechanical holes with their coordinates and diameters,
              which ACCEPTANCE D pins to the 2026-08-16 drill file
  counts      footprints, pads, tracks, vias, PTH and NPTH
  contract    differences between the pad->net map and contract/netlist_contract
  zones       whether every zone carries a filled polygon, i.e. whether the
              board was saved after a refill
  pad_overrides  pads whose solder mask margin differs from the board default
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import route as R                                  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--board", default=None)
    a = ap.parse_args()

    import pcbnew
    board = pcbnew.LoadBoard(a.board or P.board_path(a.root))
    idx = R.CopperIndex(pcbnew, board)

    holes = P.npth_holes(pcbnew, board)
    npth = sorted(({"ref": k, "x_mm": P.mm(v[0]), "y_mm": P.mm(v[1]),
                    "dia_mm": P.mm(2 * v[2])} for k, v in holes.items()),
                  key=lambda d: (d["x_mm"], d["y_mm"]))

    diffs, mech = P.contract_diff(board, pcbnew, a.root)

    zones = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        filled = 0
        for layer in z.GetLayerSet().CuStack():
            try:
                f = z.GetFilledPolysList(layer)
            except Exception:
                continue
            if f is not None:
                filled += f.OutlineCount()
        zones.append({"net": z.GetNetname(),
                      "layers": [board.GetLayerName(l)
                                 for l in z.GetLayerSet().CuStack()],
                      "filled_outlines": filled})

    ds = board.GetDesignSettings()
    default_margin = ds.m_SolderMaskExpansion
    overrides = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            m = pad.GetLocalSolderMaskMargin()
            if m is None or m == default_margin:
                continue
            overrides.append({"ref": fp.GetReference(),
                              "pad": pad.GetNumber(),
                              "net": pad.GetNetname(),
                              "margin_mm": P.mm(m)})

    facts = {
        "npth": npth,
        "npth_count": len(npth),
        "counts": P.counts(board, pcbnew),
        "contract_diffs": len(diffs),
        "contract_diff_detail": diffs[:20],
        "mechanical_footprints": mech,
        "unconnected": P.unconnected_count(pcbnew, board),
        "zones": zones,
        "zones_all_filled": all(z["filled_outlines"] > 0 for z in zones),
        "solder_mask_default_mm": P.mm(default_margin),
        "solder_mask_min_web_mm": P.mm(ds.m_SolderMaskMinWidth),
        "pad_mask_overrides": overrides,
        "clearance_pairs_below_rule": len(
            P.clearance_pairs(pcbnew, board, idx, P.CLEARANCE)),
        "hole_pairs_below_rule": len(
            P.hole_pairs(pcbnew, board, idx, P.HOLE_TO_HOLE)),
        "copper_inside_npth_rings": {
            k: len(P.copper_near_hole(pcbnew, board, v, P.HOLE_CLEARANCE))
            for k, v in sorted(holes.items())},
    }
    print(json.dumps(facts, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
