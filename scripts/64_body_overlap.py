#!/usr/bin/env python3
"""ACCEPTANCE H -- no two component bodies may occupy the same place.

    KPY scripts/64_body_overlap.py [--root .] [--gap 0.15]

Why this exists
---------------
The board reached a filled JLC cart with R_CC1 -- a 0.45 mm tall 0603 --
sitting entirely inside the USB-C receptacle's body outline. The connector's
shell lands flat on the board, so J1 could not have seated: the assembly was
impossible, and nothing in the pipeline said so.

Nothing said so because DRC's only opinion about this is `courtyards_overlap`,
and ACCEPTANCE A demotes that to a warning -- deliberately and with reason.
The courtyards this board inherited from EasyEDA are far larger than the
parts (1.93 x 1.17 mm around a 1.0 x 0.5 mm 0402), 69 pairs of existing parts
already overlap them, and holding new work to a standard the board itself does
not meet would have blocked every repair. So the one signal that could have
caught R_CC1 was, correctly, ignored -- and the real question was never asked
instead.

The real question is about **bodies**, not courtyards: the F.Fab outline is
the part as the vendor draws it, and two of those may not intersect. That is a
much tighter, much more meaningful test than a courtyard, and it is the one
this file asks.

How a body box is decided, in order:

    1. PCB_SHAPE items on F.Fab or B.Fab -- the fabrication outline
    2. failing that, PCB_SHAPE items on F.SilkS or B.SilkS
    3. failing that, the pad extents

Text is excluded at every stage. A reference designator drawn on F.Fab is not
part of the body, and including it makes a 0603 look 3 mm wide -- the whole
check turns into noise.

Reported, with the gap in mm (negative means the boxes intersect and the
number is how deep):

    overlaps    gap < 0                    -- ACCEPTANCE H fails on these
    contained   one box wholly inside      -- the R_CC1 case; a subset of above
    tight       0 <= gap < --gap (0.15)    -- reported, does not fail

`data/body_overlap_allow.json` lists pairs that are accepted mechanical
decisions. It starts with one: AMS1117 over the H4 mounting hole (decision M1
-- the regulator body overhangs an M2 screw hole, which is a clearance
question for the enclosure, not an assembly one).

Known and expected to fail right now
------------------------------------
`U_ADS` x `U_MCU` at -2.81 mm, and the three capacitors `C_AVDD1_100n`,
`C_AVDD1_10n`, `C_DVDD_P40` under `U_MCU`. All four are the ESP32-WROOM-32E
module's 25.5 mm outline reaching across the ADC. The fix is the part swap to
ESP32-WROOM-32UE (19.2 mm long), which is a separate decision; this check
reports them and does not touch them.

Read-only: it never writes the board.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import epro as E                                   # noqa: E402

IU = 1000000.0
BOARD_NAME = "Therapia_EEG-HRV"
DEFAULT_GAP_MM = 0.15


def shape_box(pcbnew, fp, layers):
    """Bounding box of the footprint's PCB_SHAPE items on `layers`, or None.

    PCB_SHAPE only. `GraphicalItems()` also hands back PCB_TEXT and
    PCB_TEXTBOX, and a value or reference drawn on the fab layer would make
    the body several times its real size.
    """
    xs, ys = [], []
    for d in fp.GraphicalItems():
        if d.GetClass() != "PCB_SHAPE":
            continue
        if d.GetLayer() not in layers:
            continue
        bb = d.GetBoundingBox()
        xs += [bb.GetLeft(), bb.GetRight()]
        ys += [bb.GetTop(), bb.GetBottom()]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def pad_box(fp):
    xs, ys = [], []
    for p in fp.Pads():
        bb = p.GetBoundingBox()
        xs += [bb.GetLeft(), bb.GetRight()]
        ys += [bb.GetTop(), bb.GetBottom()]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def is_mechanical(pcbnew, fp):
    """A bare drilled feature -- H1-H4, PEG1/PEG2 -- rather than a part.

    Worth separating in the report: these have no body at all, so their box is
    the pad fallback (the drill circle), and "the peg hole is inside the
    connector" is true by construction rather than a collision. They are still
    measured and still counted, because a real part sitting on a screw hole is
    a real problem -- that is what the AMS1117/H4 allow-list entry is about.
    """
    pads = list(fp.Pads())
    if not pads:
        return False
    return all(int(p.GetAttribute()) == int(pcbnew.PAD_ATTRIB_NPTH)
               for p in pads)


def body_of(pcbnew, fp):
    """(box, source) for one footprint, or (None, "none")."""
    box = shape_box(pcbnew, fp, (pcbnew.F_Fab, pcbnew.B_Fab))
    if box:
        return box, "fab"
    box = shape_box(pcbnew, fp, (pcbnew.F_SilkS, pcbnew.B_SilkS))
    if box:
        return box, "silk"
    box = pad_box(fp)
    if box:
        return box, "pads"
    return None, "none"


def gap(a, b):
    """Separation of two boxes in nm. Negative = they intersect, by that much.

    Positive is the straight-line distance between the boxes; negative is the
    smaller of the two overlaps, which is how far one would have to move to
    clear the other.
    """
    import math
    dx = max(a[0] - b[2], b[0] - a[2])
    dy = max(a[1] - b[3], b[1] - a[3])
    if dx >= 0 and dy >= 0:
        return math.hypot(dx, dy)
    return max(dx, dy)


def contains(outer, inner):
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and outer[2] >= inner[2] and outer[3] >= inner[3])


def load_allow(root):
    path = os.path.join(root, "data", "body_overlap_allow.json")
    if not os.path.exists(path):
        return set(), []
    doc = E.load_json(path)
    pairs = set()
    for entry in doc.get("allow", ()):
        p = entry["pair"] if isinstance(entry, dict) else entry
        pairs.add(tuple(sorted(p)))
    return pairs, doc.get("allow", [])


def mm(v):
    return round(v / IU, 4)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--root", default=here)
    ap.add_argument("--board", default=None)
    ap.add_argument("--gap", type=float, default=DEFAULT_GAP_MM,
                    help="report pairs closer than this many mm (default 0.15)")
    a = ap.parse_args()
    root = a.root

    import pcbnew
    bpath = a.board or os.path.join(root, "board", BOARD_NAME + ".kicad_pcb")
    board = pcbnew.LoadBoard(bpath)

    parts = []
    no_body = []
    for fp in board.GetFootprints():
        ref = fp.GetReference() or "(anon)"
        box, src = body_of(pcbnew, fp)
        if box is None:
            no_body.append(ref)
            continue
        parts.append({"ref": ref, "box": box, "source": src,
                      "mechanical": is_mechanical(pcbnew, fp),
                      "value": fp.GetValue()})
    parts.sort(key=lambda p: p["ref"])

    allow, allow_doc = load_allow(root)
    limit = int(a.gap * IU)

    overlaps, tight, contained = [], [], []
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            p, q = parts[i], parts[j]
            g = gap(p["box"], q["box"])
            if g >= limit:
                continue
            key = tuple(sorted((p["ref"], q["ref"])))
            rec = {"pair": list(key), "gap_mm": mm(g),
                   "source": [p["source"], q["source"]],
                   "box_mm": [[mm(v) for v in p["box"]],
                              [mm(v) for v in q["box"]]],
                   "mechanical": sorted(x["ref"] for x in (p, q)
                                        if x["mechanical"]),
                   "allowed": key in allow}
            if g < 0:
                if contains(p["box"], q["box"]):
                    rec["contained"] = "%s is wholly inside %s" % (q["ref"],
                                                                   p["ref"])
                elif contains(q["box"], p["box"]):
                    rec["contained"] = "%s is wholly inside %s" % (p["ref"],
                                                                   q["ref"])
                overlaps.append(rec)
                if "contained" in rec:
                    contained.append(rec)
            else:
                tight.append(rec)
    overlaps.sort(key=lambda r: r["gap_mm"])
    tight.sort(key=lambda r: r["gap_mm"])

    failing = [r for r in overlaps if not r["allowed"]]
    # Split the report: a part on a part is an assembly defect, a part on a
    # bare drilled feature is a mechanical question about the enclosure.
    failing_parts = [r for r in failing if not r["mechanical"]]
    failing_mech = [r for r in failing if r["mechanical"]]
    by_source = {}
    for p in parts:
        by_source[p["source"]] = by_source.get(p["source"], 0) + 1

    checks = [
        E.gate_check("H component bodies do not overlap", [],
                     [r["pair"] for r in failing]),
        E.gate_check("H every footprint has a body box", 0, len(no_body)),
        E.gate_check("H allow-list entries all still overlap", [],
                     sorted(set(allow) - {tuple(r["pair"]) for r in overlaps}),
                     note="an allow-list entry that no longer overlaps is dead "
                          "weight and should be deleted"),
    ]
    notes = ("%d footprints measured (%s). %d overlapping pairs, %d of them "
             "allowed, %d containments; %d further pairs inside %.2f mm. "
             "%d of the failures are part-on-part, %d are part-on-hole. "
             "ACCEPTANCE H: %s"
             % (len(parts),
                ", ".join("%s=%d" % kv for kv in sorted(by_source.items())),
                len(overlaps), len(overlaps) - len(failing), len(contained),
                len(tight), a.gap, len(failing_parts), len(failing_mech),
                "pass" if not failing else
                "FAIL on " + ", ".join("%s/%s" % tuple(r["pair"])
                                       for r in failing)))
    E.write_gate(os.path.join(root, "gates", "S7_body.json"), "S7_body",
                 checks, notes=notes,
                 extra={"board": os.path.relpath(bpath, root),
                        "gap_threshold_mm": a.gap,
                        "footprints": len(parts),
                        "body_source_counts": by_source,
                        "no_body": no_body,
                        "overlaps": overlaps,
                        "failing_part_on_part": failing_parts,
                        "failing_part_on_hole": failing_mech,
                        "contained": contained,
                        "tight_pairs": tight,
                        "allow_list": allow_doc,
                        "parts": [{"ref": p["ref"], "source": p["source"],
                                   "box_mm": [mm(v) for v in p["box"]]}
                                  for p in parts]})
    print(notes)
    for r in overlaps:
        print("  %-9s %-13s %-13s %8.4f mm  %s%s%s"
              % ("ALLOWED" if r["allowed"] else
                 ("on-hole" if r["mechanical"] else "OVERLAP"),
                 r["pair"][0], r["pair"][1], r["gap_mm"],
                 "/".join(r["source"]),
                 "  -- " + r["contained"] if r.get("contained") else "",
                 "  [%s is a drilled feature, not a part]"
                 % ",".join(r["mechanical"]) if r["mechanical"] else ""))
    for r in tight:
        print("  %-9s %-13s %-13s %8.4f mm  %s"
              % ("tight", r["pair"][0], r["pair"][1], r["gap_mm"],
                 "/".join(r["source"])))
    return 0 if all(c["pass"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
