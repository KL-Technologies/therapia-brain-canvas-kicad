#!/usr/bin/env python3
"""L4: clear the USB-C positioning-peg holes PEG1 and PEG2.

The ECO's third fatal item, and the one it got half wrong. It blames "Slot
Region e54/e55"; the real objects are two FILL circles of radius 13.78 mil on
EasyEDA's layer 12, ids e36/e37, which S4a turned into NPTH pads at

    PEG1 (176.8611, 113.8779)   PEG2 (176.8611, 108.0979)   both 0.700 mm

So the targets are taken from the board and from DRC, not from the ECO's ids.
Measured before this step:

    PEG2  via  [USB_VBUS_RAW] (177.2010, 108.1430)  copper -0.3119  hole -0.1596
          six USB_VBUS_RAW tracks from -0.1086 to -0.3711
          pad  [GND] J1 pin 12                       +0.1712
    PEG1  via  [USB_VBUS_RAW] (176.6930, 113.2230)  copper +0.0213  hole +0.1736
          pad  [GND] J1 pin 1                        +0.1712

The via at PEG2 is the fatal one: its drill and the peg's overlap by 0.16 mm,
so the barrel cannot form and VBUS never reaches the board.

Two different repairs are needed.

The copper is moved by the usual means -- vias retreat, tracks are re-routed
round the hole -- through the margin ladder, because the corridor between the
peg and the ESP32 UART pair on the back side is narrow and 0.3 mm may not fit
where 0.22 mm does.

The two J1 pads cannot be moved: they are the connector's own ground pins and
they sit 0.5213 mm from the connector's own peg hole, which is the vendor
footprint's geometry, not a routing mistake. They are 0.0288 mm short of the
rule. Rather than record that as an accepted defect, the pads are shortened
along x by PAD_TRIM so the copper retreats and the land keeps its width; a USB-C
signal pad losing 0.1 mm of a 1.1 mm length is a change of no consequence to
the joint, and it makes the board pass the rule as written instead of asking
for an exemption from it. The trim is recorded in the gate.

Runs under the KiCad python; the DRC at the end needs a normal shell.
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import route as R                                  # noqa: E402

PEGS = ["PEG1", "PEG2"]
# Nets whose copper this step is allowed to move. The pegs also have ESP_RXD
# and USB_DM nearby, both already clear of the rule; they are included so the
# step can improve them if there is room, and neither is required to move.
NETS = {"USB_VBUS_RAW", "USB_DM", "ESP_RXD"}
# How much to take off the length of a J1 ground pad, per side. 0.0288 mm is
# what the rule needs; 0.05 leaves margin and stays a rounding error against a
# 1.1 mm pad.
PAD_TRIM = int(0.05 * P.IU)
TRIM_PADS = [("J1", "1"), ("J1", "12")]


def trim_pads(ctx):
    """Shorten the connector's own ground pads away from its own peg holes."""
    pcbnew, board, log = ctx["pcbnew"], ctx["board"], ctx["log"]
    holes = ctx["holes"]
    done = []
    for ref, number in TRIM_PADS:
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            continue
        for pad in fp.Pads():
            if pad.GetNumber() != number:
                continue
            worst = min((P.hole_gap(pcbnew, board, pad, h), n)
                        for n, h in holes.items())
            if worst[0] >= P.HOLE_CLEARANCE:
                done.append({"ref": ref, "pad": number, "action": "none",
                             "gap_mm": P.mm(worst[0]), "hole": worst[1]})
                continue
            size = pad.GetSize()
            before = [P.mm(size.x), P.mm(size.y)]
            pad.SetSize(pcbnew.VECTOR2I(int(size.x - 2 * PAD_TRIM),
                                        int(size.y)))
            after = min((P.hole_gap(pcbnew, board, pad, h), n)
                        for n, h in holes.items())
            done.append({"ref": ref, "pad": number, "action": "trimmed",
                         "size_before_mm": before,
                         "size_after_mm": [P.mm(pad.GetSize().x),
                                           P.mm(pad.GetSize().y)],
                         "gap_before_mm": P.mm(worst[0]),
                         "gap_after_mm": P.mm(after[0]), "hole": after[1]})
    log["pad_trims"] = done


def peg_checks(log):
    """Nothing of any net may still sit inside either peg's clearance ring."""
    left = sum(len(v) for v in log.get("inside_ring_after_any_net", {}).values())
    return [P.check("pegs_clear_of_all_copper", 0, left)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--skip-drc", action="store_true")
    a = ap.parse_args()

    ok, log = P.run_hole_step(
        "S5_L4", PEGS, NETS,
        "USB_VBUS_RAW moved clear of the USB-C peg holes; J1 ground pads "
        "trimmed %.3f mm a side." % P.mm(PAD_TRIM),
        root=a.root, skip_drc=a.skip_drc, baseline="drc_s5_l3",
        after_clear=trim_pads, extra_checks=peg_checks)
    print(json.dumps({k: v for k, v in log.items()
                      if k != "contract_diffs"}, indent=1)[:6000])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
