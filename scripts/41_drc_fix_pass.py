#!/usr/bin/env python3
"""One pass of automatic fixes over the board, driven by a DRC report.

    KPY scripts/41_drc_fix_pass.py --drc logs/drc_iter_03.json [--limit 25]

Called by 40_drc_loop.py, once per iteration, as its own process: pcbnew will
not LoadBoard twice in one process, so the loop cannot hold the board open
across the DRC runs between passes.

What it acts on is taken from the report only as a *list of kinds*. Where the
violations actually are is measured here, against the board, because a DRC
report gives an item's own anchor rather than the place two things come close
-- for an 11 mm track those are millimetres apart. The one exception is
solder_mask_bridge, where the pair itself is what matters and the report names
it correctly.

Fix order per kind:

    hole_clearance   copper out of every NPTH ring: vias retreat, tracks are
                     split and re-routed round the hole
    hole_to_hole     retreat one of the two vias
    clearance        via first, then track, then a bounded footprint nudge
    mask bridge      shrink the local mask margin on the pads involved

Nothing is relaxed and nothing is deleted. A violation this cannot fix is
returned in `unresolved` for the loop to escalate.
"""

import argparse
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import route as R                                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def load_sibling(name):
    """Import a sibling script whose filename starts with a digit."""
    spec = importlib.util.spec_from_file_location(
        name.replace(".py", ""), os.path.join(HERE, name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def nudge(pcbnew, board, idx, pad, holes, target):
    l5 = load_sibling("34_repair_L5.py")
    return l5.nudge_footprint(pcbnew, board, idx, pad, None, holes, target)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--drc", required=True)
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--no-nudge", action="store_true")
    a = ap.parse_args()
    root = a.root

    import pcbnew
    bpath = P.board_path(root)
    board = pcbnew.LoadBoard(bpath)
    idx = R.CopperIndex(pcbnew, board)
    holes = P.npth_holes(pcbnew, board)
    doc = P.load_drc(a.drc if os.path.isabs(a.drc)
                     else os.path.join(root, a.drc))
    kinds = P.by_type(doc)
    log = {"kinds_in_report": kinds, "fixed": [], "unresolved": [],
           "budget": a.limit}
    before = P.unconnected_count(pcbnew, board)
    log["unconnected_before"] = before
    budget = a.limit

    # --- copper inside a mechanical hole ---------------------------------
    if budget > 0 and kinds.get("hole_clearance"):
        for name, hole in sorted(holes.items()):
            if budget <= 0:
                break
            inside = P.copper_near_hole(pcbnew, board, hole, P.HOLE_CLEARANCE,
                                        include_pads=False)
            if not inside:
                continue
            res = P.clear_hole(pcbnew, board, idx, name, hole,
                               P.TARGET_HOLE_MARGIN)
            for r in res:
                (log["fixed"] if r.get("ok") else log["unresolved"]).append(
                    dict(r, kind="hole_clearance"))
                budget -= 1

    # --- two holes too close ---------------------------------------------
    if budget > 0 and kinds.get("hole_to_hole"):
        for pair in P.hole_pairs(pcbnew, board, idx, P.HOLE_TO_HOLE):
            if budget <= 0:
                break
            moved = False
            for first in (pair["a"], pair["b"]):
                if first.GetClass() != "PCB_VIA":
                    continue
                res = P.retreat_via(pcbnew, board, idx, first, holes,
                                    P.HOLE_CLEARANCE)
                res["kind"] = "hole_to_hole"
                res["gap_before_mm"] = P.mm(pair["gap"])
                if res.get("ok"):
                    log["fixed"].append(res)
                    moved = True
                    break
            budget -= 1
            if not moved:
                log["unresolved"].append(
                    {"kind": "hole_to_hole", "gap_mm": P.mm(pair["gap"]),
                     "a": P.describe(board, pair["a"]),
                     "b": P.describe(board, pair["b"]),
                     "reason": "neither hole belongs to a via that can move"})

    # --- copper too close to copper ---------------------------------------
    if budget > 0 and kinds.get("clearance"):
        seen = set()
        for _round in range(3):
            if budget <= 0:
                break
            pairs = [p for p in P.clearance_pairs(pcbnew, board, idx,
                                                  P.CLEARANCE)
                     if (min(R.uid(p["a"]), R.uid(p["b"])),
                         max(R.uid(p["a"]), R.uid(p["b"]))) not in seen]
            if not pairs:
                break
            for pair in pairs:
                if budget <= 0:
                    break
                seen.add((min(R.uid(pair["a"]), R.uid(pair["b"])),
                          max(R.uid(pair["a"]), R.uid(pair["b"]))))
                res = None
                for target in P.CLEARANCE_STEPS:
                    res = P.fix_clearance_pair(pcbnew, board, idx, pair, holes,
                                               target=target)
                    if res.get("ok"):
                        break
                if not res.get("ok") and not a.no_nudge:
                    for which in (pair["a"], pair["b"]):
                        if which.GetClass() != "PAD":
                            continue
                        nud = nudge(pcbnew, board, idx, which, holes,
                                    P.CLEARANCE)
                        if nud.get("ok"):
                            res.update(nud)
                            break
                res["kind"] = "clearance"
                (log["fixed"] if res.get("ok")
                 else log["unresolved"]).append(res)
                budget -= 1

    # --- merged solder mask openings --------------------------------------
    if budget > 0 and kinds.get("solder_mask_bridge"):
        mb = load_sibling("35_mask_bridges.py")
        ds = board.GetDesignSettings()
        web, default_margin = ds.m_SolderMaskMinWidth, ds.m_SolderMaskExpansion
        allowed, pads = {}, {}
        for v in doc.get("violations", []):
            if v.get("type") != "solder_mask_bridge":
                continue
            its = v.get("items", [])
            if len(its) < 2:
                continue
            a_it = mb.resolve(pcbnew, board, its[0])
            b_it = mb.resolve(pcbnew, board, its[1])
            if a_it is None or b_it is None:
                log["unresolved"].append(
                    {"kind": "solder_mask_bridge",
                     "reason": "an item named in the report is not on the "
                               "board", "a": its[0].get("description"),
                     "b": its[1].get("description")})
                continue
            ceiling = int(2 * default_margin + web + int(0.05 * P.IU))
            g = mb.copper_gap(pcbnew, a_it, b_it, ceiling)
            openers = [it for it in (a_it, b_it)
                       if mb.has_aperture(pcbnew, board, it)]
            if g is None or not openers or g - web - mb.SAFETY < 0:
                log["unresolved"].append(
                    {"kind": "solder_mask_bridge",
                     "copper_gap_mm": P.mm(g) if g is not None else None,
                     "min_web_mm": P.mm(web),
                     "a": its[0].get("description"),
                     "b": its[1].get("description"),
                     "reason": "the copper gap is below the minimum web; no "
                               "mask margin can separate these"})
                continue
            each = int((g - web - mb.SAFETY) // len(openers))
            for it in openers:
                k = R.uid(it)
                pads[k] = it
                allowed[k] = each if k not in allowed else min(allowed[k], each)
        for k, it in pads.items():
            if budget <= 0:
                break
            want = max(0, min(allowed[k], default_margin))
            cur = it.GetLocalSolderMaskMargin()
            cur_val = default_margin if cur is None else cur
            if want >= cur_val:
                continue
            it.SetLocalSolderMaskMargin(int(want))
            fp = it.GetParentFootprint()
            log["fixed"].append({"kind": "solder_mask_bridge",
                                 "ok": True, "method": "mask margin",
                                 "ref": fp.GetReference() if fp else None,
                                 "pad": it.GetNumber(),
                                 "margin_before_mm": P.mm(cur_val),
                                 "margin_after_mm": P.mm(want)})
            budget -= 1

    # --- reconnect anything the pass stranded ------------------------------
    nets = set()
    for r in log["fixed"]:
        for side in ("a", "b", "was", "item"):
            d = r.get(side)
            if isinstance(d, dict) and d.get("net"):
                nets.add(d["net"])
    netcodes = sorted({board.FindNet(n).GetNetCode() for n in nets
                       if board.FindNet(n) is not None})
    healed, floating = P.heal_nets(pcbnew, board, idx, netcodes, log=log)
    log["islands_reconnected"] = healed
    log["islands_still_floating"] = floating

    board.BuildListOfNets()
    diffs, _mech = P.contract_diff(board, pcbnew, root)
    log["contract_diffs"] = len(diffs)
    log["counts"] = P.counts(board, pcbnew)
    log["unconnected_after"] = P.unconnected_count(pcbnew, board)
    if log["fixed"]:
        pcbnew.SaveBoard(bpath, board)
        log["saved"] = True
    print(json.dumps(log, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
