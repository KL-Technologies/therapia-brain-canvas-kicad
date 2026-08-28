#!/usr/bin/env python3
"""Give the through-hole pads their solder mask openings back.

    KPY scripts/43_fix_pth_mask.py [--dry-run]

Found by 62_check_fab.py, which parses the plotted Gerbers rather than asking
KiCad about the board: the bottom solder mask came out **empty** -- 466 bytes,
no apertures, no flashes, no regions.

The cause is in the import, not the plot. Every PTH and NPTH pad arrived from
EasyEDA with a layer set of copper only:

    J2 x12, J1 x4 (PTH)   F.Cu B.Cu In1.Cu ... In30.Cu
    H1-H4, PEG1/2 (NPTH)  the same

with no F.Mask and no B.Mask. The 417 SMD pads are fine (F.Cu, F.Mask,
F.Paste), which is why this hid until the mask layers were read back: the front
mask still had 403 openings and looked healthy.

What it would have meant: the twelve pins of the electrode header J2 and the
four USB-C shell legs would have come back **covered in solder mask on both
faces** and could not have been soldered at all. The 2026-08-16 EasyEDA package
has openings over every one of them, on both sides -- so this is a regression
introduced by the KiCad import, not a property of the design.

NPTH gets openings too, matching what the 2026-08-16 bottom mask does at the M2
holes (a 2.4892 mm circle against a 2.3876 mm drill): mask pulled back from a
drilled edge rather than left sitting on it, where it chips.

Copper is not touched. Only the mask layer sets change.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import epro as E                                   # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    import pcbnew
    board = pcbnew.LoadBoard(P.board_path(a.root))
    before = P.counts(board, pcbnew)

    fixed = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            attr = int(pad.GetAttribute())
            if attr not in (int(pcbnew.PAD_ATTRIB_PTH),
                            int(pcbnew.PAD_ATTRIB_NPTH)):
                continue
            ls = pad.GetLayerSet()
            missing = [n for n, l in (("F.Mask", pcbnew.F_Mask),
                                      ("B.Mask", pcbnew.B_Mask))
                       if not ls.Contains(l)]
            if not missing:
                continue
            fixed.append({
                "ref": fp.GetReference(), "pad": pad.GetNumber(),
                "attr": "PTH" if attr == int(pcbnew.PAD_ATTRIB_PTH)
                        else "NPTH",
                "added": missing,
                "at_mm": [P.mm(pad.GetPosition().x),
                          P.mm(pad.GetPosition().y)],
                "size_mm": [P.mm(pad.GetSize().x), P.mm(pad.GetSize().y)],
                "drill_mm": P.mm(pad.GetDrillSizeX()),
                "mask_margin_mm": P.mm(pad.GetLocalSolderMaskMargin() or 0)})
            if not a.dry_run:
                ls.AddLayer(pcbnew.F_Mask)
                ls.AddLayer(pcbnew.B_Mask)
                pad.SetLayerSet(ls)

    diffs, mech = P.contract_diff(board, pcbnew, a.root)
    after = P.counts(board, pcbnew)
    log = {"pads_fixed": fixed, "count": len(fixed),
           "counts_before": before, "counts_after": after,
           "contract_diffs": len(diffs), "mechanical": mech,
           "unconnected": P.unconnected_count(pcbnew, board)}
    by_ref = {}
    for f in fixed:
        by_ref[f["ref"]] = by_ref.get(f["ref"], 0) + 1
    log["by_reference"] = by_ref

    if a.dry_run:
        print(json.dumps(log, indent=1))
        return 0
    if before != after or diffs or log["unconnected"]:
        print("the mask fix changed something it should not have:")
        print(json.dumps({k: log[k] for k in
                          ("counts_before", "counts_after", "contract_diffs",
                           "unconnected")}, indent=1))
        return 1
    pcbnew.SaveBoard(P.board_path(a.root), board)
    E.dump_json(os.path.join(a.root, "logs", "pth_mask_fix.json"), log)
    print("mask openings restored on %d pads: %s"
          % (len(fixed), ", ".join("%s x%d" % (k, v)
                                   for k, v in sorted(by_ref.items()))))
    print("copper unchanged (%s), parity %d, unconnected %d"
          % (after, log["contract_diffs"], log["unconnected"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
