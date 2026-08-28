#!/usr/bin/env python3
"""Route back whatever a repair left unconnected, using DRC's own list.

    KPY scripts/39_fix_unconnected.py --drc logs/drc_after_L1.json

lib/repair.net_components catches the obvious breaks before the board is saved,
but it is a model of KiCad's connectivity rather than the thing itself. This
step takes the answer from the DRC report instead: it names both ends of every
ratsnest line that is still open, and this routes between them.

Both ends are resolved by description and position, never by the uuid the
report also carries -- see resolve_item.

It has to be a separate process: pcbnew cannot LoadBoard twice in one, so the
script that saved the board cannot re-open it to act on the DRC that followed.

The caller re-runs DRC afterwards; this script does not, so it stays usable
inside the command sandbox.
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
import maze as M                                   # noqa: E402
import viol as V                                   # noqa: E402

TOL = int(0.005 * P.IU)
# How far a healing route may wander. A reconnection is a local repair; when
# the shortest legal path is several times the direct distance the break is
# not something to paper over with copper, it is something to report.
MIN_HEAL_MM = 6.0
DETOUR_FACTOR = 3.0


def resolve_item(pcbnew, board, entry):
    """Find the board item a DRC report entry names.

    Deliberately not by uuid. The EasyEDA importer duplicated KIIDs across
    every instance of a library footprint, so "Pad 1 [VDD_ESP] of C_3V3_B2"
    and 27 other pads carry the same one; looking it up by uuid returned a
    USB_5V pad and the healer cheerfully routed to it. The description and the
    position together are unambiguous.
    """
    info = V.parse_item(entry)
    x = P.nm(info["x"]) if info["x"] is not None else None
    y = P.nm(info["y"]) if info["y"] is not None else None

    def near(p):
        return x is None or (abs(p.x - x) <= TOL and abs(p.y - y) <= TOL)

    if info["class"] in ("Pad", "NPTH", "PTH"):
        fp = board.FindFootprintByReference(info["ref"] or "")
        if fp is None:
            return None
        best = None
        for p in fp.Pads():
            if info["pad"] is not None and p.GetNumber() != info["pad"]:
                continue
            if near(p.GetPosition()):
                return p
            best = best or p
        return best
    if info["class"] == "Via":
        for t in board.GetTracks():
            if t.GetClass() != "PCB_VIA":
                continue
            if info["net"] and t.GetNetname() != info["net"]:
                continue
            if near(t.GetPosition()):
                return t
        return None
    if info["class"] in ("Track", "Arc"):
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                continue
            if info["net"] and t.GetNetname() != info["net"]:
                continue
            if near(t.GetStart()) or near(t.GetEnd()):
                return t
        return None
    return None


def anchors(pcbnew, item, layers):
    """Points the router may start or finish on for this item."""
    cls = item.GetClass()
    out = []
    if cls in ("PCB_TRACK", "PCB_ARC"):
        for p in (item.GetStart(), item.GetEnd()):
            if item.GetLayer() in layers:
                out.append((p.x, p.y, item.GetLayer()))
    elif cls == "ZONE":
        return []
    else:
        p = item.GetPosition()
        for l in R.item_layers(pcbnew, item):
            if l in layers:
                out.append((p.x, p.y, l))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--drc", required=True)
    ap.add_argument("--log", default=None)
    a = ap.parse_args()
    root = a.root

    import pcbnew
    bpath = P.board_path(root)
    board = pcbnew.LoadBoard(bpath)
    doc = P.load_drc(a.drc if os.path.isabs(a.drc)
                     else os.path.join(root, a.drc))
    todo = doc.get("unconnected_items", [])
    log = {"unconnected_in_report": len(todo), "fixed": [], "failed": []}
    if not todo:
        print(json.dumps(log, indent=1))
        return 0

    idx = R.CopperIndex(pcbnew, board)
    rl = P.rules()
    log["unconnected_before"] = P.unconnected_count(pcbnew, board)
    for u in todo:
        its = u.get("items", [])
        if len(its) < 2:
            log["failed"].append({"why": "report names fewer than two items",
                                  "raw": its})
            continue
        a_item = resolve_item(pcbnew, board, its[0])
        b_item = resolve_item(pcbnew, board, its[1])
        rec = {"a": its[0].get("description"), "b": its[1].get("description")}
        if a_item is None or b_item is None:
            rec["why"] = "an item named in the report is no longer on the board"
            log["failed"].append(rec)
            continue
        if a_item.GetNetCode() != b_item.GetNetCode():
            rec["why"] = ("the two items resolved to different nets (%s / %s)"
                          % (a_item.GetNetname(), b_item.GetNetname()))
            log["failed"].append(rec)
            continue
        net = a_item.GetNetCode()
        rec["net"] = a_item.GetNetname()
        router = M.Router(pcbnew, board, idx, rl)
        starts = anchors(pcbnew, a_item, router.layers)
        goals = anchors(pcbnew, b_item, router.layers)
        if not starts or not goals:
            rec["why"] = "no routable anchor on one of the two items"
            log["failed"].append(rec)
            continue
        direct = min(math.hypot(s[0] - g[0], s[1] - g[1])
                     for s in starts for g in goals) / float(P.IU)
        limit = max(MIN_HEAL_MM, DETOUR_FACTOR * direct)
        rec["direct_mm"] = round(direct, 4)
        rec["limit_mm"] = round(limit, 4)
        plan = router.route(starts, net, goals=goals, width=rl.track_width,
                            margin_mm=6.0, max_nodes=600000,
                            max_length_mm=limit)
        if not plan.get("ok"):
            rec["why"] = plan.get("reason")
            rec["detail"] = {k: plan[k] for k in ("window_mm", "length_mm",
                                                  "verify_failures")
                             if k in plan}
            log["failed"].append(rec)
            continue
        made = R.commit_route(pcbnew, board, plan, net, rl.track_width,
                              rl.via_dia, rl.via_drill)
        idx.rebuild()
        rec["method"] = plan["method"]
        rec["length_mm"] = plan.get("length_mm")
        rec["vias"] = [[P.mm(v[0]), P.mm(v[1])] for v in plan.get("vias", ())]
        rec["items_added"] = len(made)
        log["fixed"].append(rec)
        log["added"] = log.get("added", []) + [made]

    # KiCad's own connectivity decides whether this helped, not our model of
    # it -- and copper that did not help does not get written.
    log["unconnected_after"] = P.unconnected_count(pcbnew, board)
    if log["fixed"] and log["unconnected_after"] < log["unconnected_before"]:
        pcbnew.SaveBoard(bpath, board)
        log["saved"] = True
    elif log["fixed"]:
        log["saved"] = False
        log["rolled_back"] = ("the routes did not reduce the unconnected "
                              "count (%d -> %d), so nothing was written"
                              % (log["unconnected_before"],
                                 log["unconnected_after"]))
    log.pop("added", None)
    if a.log:
        with open(a.log if os.path.isabs(a.log)
                  else os.path.join(root, a.log), "w") as f:
            json.dump(log, f, indent=2)
    print(json.dumps(log, indent=1))
    return 0 if not log["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
