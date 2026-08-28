#!/usr/bin/env python3
"""Look up board items by KIID, reference or net. Runs under KPY (needs pcbnew).

    KPY scripts/28_board_inspect.py --uuid a1b2... --uuid c3d4...
    KPY scripts/28_board_inspect.py --ref C_3V3_H
    KPY scripts/28_board_inspect.py --net USB_VBUS_RAW --near 176.86,108.10 --r 2

DRC reports an item's own anchor in `pos`, which for a long track is nowhere
near the violation; and it names components only for pads. The uuid is the one
field that always points at the real thing, so repairs resolve items through
this rather than through coordinates.

Read-only: it never writes the board.
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import pcbnew  # noqa: E402
import route  # noqa: E402

IU = 1000000.0


def describe(board, item, kind=None):
    cls = item.GetClass()
    d = {"class": cls, "uuid": route.uid(item)}
    try:
        d["net"] = item.GetNetname()
    except Exception:
        pass
    if cls == "PCB_TRACK" or cls == "PCB_ARC":
        d["start"] = [item.GetStart().x / IU, item.GetStart().y / IU]
        d["end"] = [item.GetEnd().x / IU, item.GetEnd().y / IU]
        d["width_mm"] = item.GetWidth() / IU
        d["layer"] = board.GetLayerName(item.GetLayer())
        d["length_mm"] = item.GetLength() / IU
    elif cls == "PCB_VIA":
        p = item.GetPosition()
        d["pos"] = [p.x / IU, p.y / IU]
        d["diameter_mm"] = item.GetWidth() / IU
        d["drill_mm"] = item.GetDrillValue() / IU
    elif cls == "PAD":
        p = item.GetPosition()
        fp = item.GetParentFootprint()
        d["pos"] = [p.x / IU, p.y / IU]
        d["ref"] = fp.GetReference() if fp else None
        d["number"] = item.GetNumber()
        d["size_mm"] = [item.GetSize().x / IU, item.GetSize().y / IU]
        d["shape"] = int(item.GetShape())
        d["attr"] = int(item.GetAttribute())
        d["drill_mm"] = [item.GetDrillSize().x / IU, item.GetDrillSize().y / IU]
        d["layers"] = [board.GetLayerName(l) for l in item.GetLayerSet().CuStack()]
        try:
            d["mask_margin_mm"] = item.GetLocalSolderMaskMargin() / IU
        except Exception:
            pass
        bb = item.GetBoundingBox()
        d["bbox_mm"] = [bb.GetLeft() / IU, bb.GetTop() / IU,
                        bb.GetRight() / IU, bb.GetBottom() / IU]
    elif cls == "FOOTPRINT":
        p = item.GetPosition()
        d["pos"] = [p.x / IU, p.y / IU]
        d["ref"] = item.GetReference()
        d["orientation_deg"] = item.GetOrientationDegrees()
        d["pads"] = len([p for p in item.Pads()])
    return d


def all_items(board):
    for t in board.GetTracks():
        yield t
    for f in board.GetFootprints():
        yield f
        for p in f.Pads():
            yield p


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=here)
    ap.add_argument("--board", default="board/Therapia_EEG-HRV.kicad_pcb")
    ap.add_argument("--uuid", action="append", default=[])
    ap.add_argument("--ref", action="append", default=[])
    ap.add_argument("--net", action="append", default=[])
    ap.add_argument("--near", default=None, help="x,y in mm")
    ap.add_argument("--r", type=float, default=1.0, help="radius in mm")
    ap.add_argument("--from-drc", default=None,
                    help="a DRC json; resolve every error item's uuid")
    ap.add_argument("--drc-type", default=None)
    a = ap.parse_args()

    bpath = a.board if os.path.isabs(a.board) else os.path.join(a.root, a.board)
    board = pcbnew.LoadBoard(bpath)

    want_uuid = set(a.uuid)
    if a.from_drc:
        p = a.from_drc if os.path.isabs(a.from_drc) else os.path.join(a.root,
                                                                     a.from_drc)
        doc = json.load(open(p))
        for v in doc.get("violations", []):
            if v.get("severity") != "error":
                continue
            if a.drc_type and v.get("type") != a.drc_type:
                continue
            for it in v.get("items", []):
                if it.get("uuid"):
                    want_uuid.add(it["uuid"])

    near = None
    if a.near:
        xs, ys = a.near.split(",")
        near = (float(xs), float(ys))

    out = []
    for item in all_items(board):
        u = route.uid(item)
        hit = False
        if u in want_uuid:
            hit = True
        if a.ref:
            cls = item.GetClass()
            ref = None
            if cls == "FOOTPRINT":
                ref = item.GetReference()
            elif cls == "PAD":
                fp = item.GetParentFootprint()
                ref = fp.GetReference() if fp else None
            if ref in a.ref:
                hit = True
        if a.net:
            try:
                if item.GetNetname() in a.net:
                    hit = True
            except Exception:
                pass
        if not hit:
            continue
        d = describe(board, item)
        if near is not None:
            pts = []
            if "pos" in d:
                pts.append(d["pos"])
            if "start" in d:
                pts += [d["start"], d["end"]]
            if pts and min(math.hypot(p[0] - near[0], p[1] - near[1])
                           for p in pts) > a.r:
                continue
        out.append(d)

    print(json.dumps(out, indent=1, sort_keys=True))
    print("# %d items" % len(out), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
