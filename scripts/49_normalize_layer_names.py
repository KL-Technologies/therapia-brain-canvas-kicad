#!/usr/bin/env python3
"""S8 prep -- give the layers their KiCad names back, so the Gerbers are named.

    KPY scripts/49_normalize_layer_names.py [--dry-run]

The EasyEDA importer carries EasyEDA's own layer names across as the user-facing
name of each KiCad layer, and kicad-cli names the Gerber files after those. The
export came out as:

    Therapia_EEG-HRV-Multi-Layer.gm1            <- the board outline
    Therapia_EEG-HRV-Top Solder Mask Layer.gts
    Therapia_EEG-HRV-Bottom Layer.gbl

The extensions and the X2 %TF.FileFunction% attributes are right, so a CAM tool
reads the set correctly either way. A person does not: "Multi-Layer" is
EasyEDA's word for "every layer at once", and that file is the profile that
decides where the router cuts. Filenames with spaces are also a needless
liability going through someone else's intake.

This is cosmetic and provably so -- the board body references layers only by
their canonical names (1079 `(layer "F.Cu")`, zero `(layer "Top Layer")`), and
neither the .kicad_pro nor the .kicad_dru mentions a user name. Nothing about
the copper changes; the check below re-measures the board to say so.
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
    renames = []
    for layer in board.GetEnabledLayers().Seq():
        have = board.GetLayerName(layer)
        want = board.GetStandardLayerName(layer)
        if have != want:
            renames.append({"id": int(layer), "from": have, "to": want})
            if not a.dry_run:
                board.SetLayerName(layer, want)

    diffs, mech = P.contract_diff(board, pcbnew, a.root)
    after = P.counts(board, pcbnew)
    log = {"renamed": renames, "counts_before": before, "counts_after": after,
           "contract_diffs": len(diffs), "mechanical": mech,
           "unconnected": P.unconnected_count(pcbnew, board)}
    if a.dry_run:
        print(json.dumps(log, indent=1))
        return 0

    ok = (before == after and not diffs and log["unconnected"] == 0)
    if not ok:
        print("renaming changed something it should not have:")
        print(json.dumps(log, indent=1))
        return 1
    pcbnew.SaveBoard(P.board_path(a.root), board)
    E.dump_json(os.path.join(a.root, "logs", "layer_names.json"), log)
    print("renamed %d layers; footprints/tracks/vias/pads unchanged, "
          "parity %d, unconnected %d"
          % (len(renames), log["contract_diffs"], log["unconnected"]))
    for r in renames:
        print("  %-28s -> %s" % (r["from"], r["to"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
