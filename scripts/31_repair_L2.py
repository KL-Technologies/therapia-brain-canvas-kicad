#!/usr/bin/env python3
"""L2: take CHASSIS_GND out of mounting hole H1.

The ECO's second fatal item. One bottom-layer track carries the USB-C shell
ground from J2 pin 12 down the west edge of the board:

    (140, -286) -> (140, -56) mil  =  (123.5560, 87.2645) -> (123.5560, 81.4225)

and H1's 2.3876 mm drill sits at (123.0480, 83.0480) mm, 0.508 mm from the
track's centreline. The drill takes the track out completely -- chassis ground
is cut, not merely close.

The repair deletes nothing by hand and picks no waypoint. The track is handed
to the maze router to be re-drawn between its own two endpoints, and because
the router treats an NPTH hole as an obstacle, "route from A to B" is already
"go round H1". The ECO suggests passing east at about x = 190 mil
(124.826 mm); whether the router agrees is recorded rather than assumed.

Idempotent: with nothing inside H1's ring it does nothing.

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
        "S5_L2", ["H1"], {"CHASSIS_GND"},
        "CHASSIS_GND re-routed clear of H1.",
        root=a.root, skip_drc=a.skip_drc, baseline="drc_after_L1")
    print(json.dumps({k: v for k, v in log.items()
                      if k != "contract_diffs"}, indent=1)[:5000])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
