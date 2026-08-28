#!/usr/bin/env python3
"""Report nets whose copper is in more than one electrically separate island.

    KPY scripts/27_net_islands.py [--net GND] [--all]

This is the in-process version of DRC's unconnected-items check, and the point
of it is that a repair can consult it *before* saving. pcbnew cannot LoadBoard
twice in one process, so a repair that only finds out from DRC that it orphaned
something has to be run again from the start.

On an intact board it should report nothing, which is also how it is validated:
DRC says 0 unconnected, so this must agree. Read-only.
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--board", default=None)
    ap.add_argument("--net", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    import pcbnew
    board = pcbnew.LoadBoard(a.board or P.board_path(a.root))
    idx = R.CopperIndex(pcbnew, board)

    names = a.net
    if not names:
        names = sorted({board.FindNet(i).GetNetname()
                        for i in range(board.GetNetCount())})
        names = [n for n in names if n]
    split = []
    for name in names:
        net = board.FindNet(name)
        if net is None:
            continue
        comps = P.net_components(pcbnew, board, idx, net.GetNetCode())
        if len(comps) > 1 or a.all:
            split.append({
                "net": name,
                "islands": len(comps),
                "sizes": [len(c) for c in comps],
                "detail": [[P.describe(board, i) for i in c[:6]]
                           for c in comps[1:6]],
            })
    print(json.dumps({"checked": len(names), "split": split}, indent=1))
    return 0 if not [s for s in split if s["islands"] > 1] else 1


if __name__ == "__main__":
    sys.exit(main())
