#!/usr/bin/env python3
"""L3: move the ESP_TXD track out of mounting hole H4.

The ECO calls this a break risk rather than a certain break: the bottom-layer
UART transmit line

    (2330, -1604) -> (1870, -1604) mil  =  (179.1820, 120.7415) -> (167.4980, ...)

runs 1.2193 mm from H4's centre, and H4's drill radius plus half the track is
1.2953 mm, so the hole bites 76 um into the copper. Enough metal is left that
the board might work; enough is missing that it might not.

The track is 11.68 mm long and only its middle is at risk, so it is cut into
three -- before, at the hole, after -- and only the middle piece is re-routed.
Redrawing all eleven millimetres would work too, and would bury the actual
repair in a diff nobody can check.

Idempotent: with nothing inside H4's ring it does nothing.

Runs under the KiCad python; the DRC at the end needs a normal shell.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--skip-drc", action="store_true")
    a = ap.parse_args()

    ok, log = P.run_hole_step(
        "S5_L3", ["H4"], {"ESP_TXD"},
        "ESP_TXD split and its middle re-routed clear of H4.",
        root=a.root, skip_drc=a.skip_drc, baseline="drc_s5_l2")
    print(json.dumps({k: v for k, v in log.items()
                      if k != "contract_diffs"}, indent=1)[:5000])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
