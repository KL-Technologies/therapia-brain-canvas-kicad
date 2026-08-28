#!/usr/bin/env python3
"""L5: pull apart every remaining pair of copper that is too close.

The ECO's fifth item -- "the rest of the sub-3.5 mil gaps, 27 of them, taken to
3.5 mil or better". After L1 to L4 the board has 20 clearance errors and one
hole clearance error left.

Violations are found from the geometry, not read out of the DRC report. Two
reasons, both measured. DRC reports an item's own anchor, which for an 11 mm
track is nowhere near the violation, so it cannot say *where* two things come
close. And until 26_fix_uuids ran, the report named the wrong items entirely.
lib/repair.clearance_pairs asks the same question of the same SHAPE::Collide
predicate DRC uses, and hands back the actual items and the actual gap.

What moves, in order of preference:

  a via     one position change, and its own track ends follow it
  a track   split at the pinch point and the middle re-routed
  a part    a bounded nudge on a 0.05 mm grid, only when both items are pads
            and nothing else will do -- a pad moves with its footprint, so
            this is a placement change and is recorded as one

Nothing is relaxed. The target is the 0.0889 mm rule with the 0.127 mm
recommendation tried first, and a repair that cannot reach the rule is reported
rather than accepted.

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
import drc as D                                    # noqa: E402

ROUNDS = 6
# How far a part may be nudged to open a pad-to-pad gap, and on what grid.
NUDGE_STEP = int(0.05 * P.IU)
NUDGE_MAX = int(0.6 * P.IU)
BODY_GAP = int(0.15 * P.IU)


def gap_between(pcbnew, a, b, target):
    """Copper gap between two items on a layer they share, or None."""
    import route as _R
    for layer in set(_R.item_layers(pcbnew, a)) & set(_R.item_layers(pcbnew, b)):
        try:
            return P._actual_gap(a.GetEffectiveShape(layer),
                                 b.GetEffectiveShape(layer), int(target * 2))
        except Exception:
            continue
    return None


def nudge_footprint(pcbnew, board, idx, pad, other, holes, target):
    """Move a pad's footprint just far enough to open the gap.

    Only for pad-to-pad pinches, where there is nothing else to move. The part
    keeps its rotation, every one of its pads has to end up legal, its body has
    to stay clear of its neighbours, and each pad has to stay connected --
    tracks that ended on a pad follow it, and are verified afterwards.
    """
    fp = pad.GetParentFootprint()
    if fp is None:
        return {"ok": False, "reason": "pad has no footprint"}
    ref = fp.GetReference()
    own = [p for p in fp.Pads()]
    attached = []
    for p in own:
        for t, which in P.pad_endpoints(pcbnew, board, p):
            attached.append((t, which, p))
    ignore = own + [t for t, _w, _p in attached]
    bodyidx = R.BodyIndex(pcbnew, board,
                          skip_refs=set([ref]) | set(holes.keys()))
    box = P.board_box()

    cands = []
    n = int(NUDGE_MAX / NUDGE_STEP)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            if i == 0 and j == 0:
                continue
            d = math.hypot(i * NUDGE_STEP, j * NUDGE_STEP)
            if d <= NUDGE_MAX:
                cands.append((d, i * NUDGE_STEP, j * NUDGE_STEP))
    cands.sort()

    for _d, mx, my in cands:
        fp.Move(pcbnew.VECTOR2I(int(mx), int(my)))
        ok = True
        for p in own:
            for name, h in holes.items():
                g = P.hole_gap(pcbnew, board, p, h)
                if g is not None and g < P.HOLE_CLEARANCE:
                    ok = False
                    break
            if not ok:
                break
            bb = p.GetBoundingBox()
            if not (box[0] <= bb.GetLeft() and bb.GetRight() <= box[2]
                    and box[1] <= bb.GetTop() and bb.GetBottom() <= box[3]):
                ok = False
                break
            for layer in p.GetLayerSet().CuStack():
                try:
                    sh = p.GetEffectiveShape(layer)
                except Exception:
                    continue
                if idx.shape_conflicts(sh, layer, target, p.GetNetCode(),
                                       ignore=ignore):
                    ok = False
                    break
            if not ok:
                break
        if ok and bodyidx.clash(fp, BODY_GAP):
            ok = False
        if not ok:
            fp.Move(pcbnew.VECTOR2I(int(-mx), int(-my)))
            continue

        # the tracks that ended on its pads have to follow, and still be legal
        moves, good = [], True
        for t, which, _p in attached:
            s, e = t.GetStart(), t.GetEnd()
            a2 = (s.x + mx, s.y + my) if which == "start" else (s.x, s.y)
            b2 = (e.x, e.y) if which == "start" else (e.x + mx, e.y + my)
            if not R.straight_ok(idx, pcbnew, board, a2, b2, t.GetLayer(),
                                 t.GetWidth(), t.GetNetCode(), P.CLEARANCE,
                                 P.HOLE_CLEARANCE, ignore=ignore):
                good = False
                break
            moves.append((t, a2, b2))
        if not good:
            fp.Move(pcbnew.VECTOR2I(int(-mx), int(-my)))
            continue
        undo = [(t, (t.GetStart().x, t.GetStart().y),
                 (t.GetEnd().x, t.GetEnd().y)) for t, _a, _b in moves]
        for t, a2, b2 in moves:
            t.SetStart(pcbnew.VECTOR2I(int(a2[0]), int(a2[1])))
            t.SetEnd(pcbnew.VECTOR2I(int(b2[0]), int(b2[1])))
        # The legality sweep above ignores the part's own pads and its own
        # attached tracks, so it cannot see a pinch between the two -- which is
        # what C_RST_DLY had, its ADS_RESET_N track 0.0685 mm from its own
        # ground pad. Confirm the actual pair opened up, or put the part back;
        # a nudge that reports success without moving the violation is how the
        # DRC loop ended up shuffling one part back and forth.
        g = None if other is None else gap_between(pcbnew, pad, other, target)
        if g is not None and g < target:
            for t, s0, e0 in undo:
                t.SetStart(pcbnew.VECTOR2I(int(s0[0]), int(s0[1])))
                t.SetEnd(pcbnew.VECTOR2I(int(e0[0]), int(e0[1])))
            fp.Move(pcbnew.VECTOR2I(int(-mx), int(-my)))
            continue
        idx.rebuild()
        return {"ok": True, "method": "footprint nudge", "ref": ref,
                "offset_mm": [P.mm(mx), P.mm(my)],
                "displacement_mm": P.mm(math.hypot(mx, my)),
                "track_ends_followed": len(moves)}
    return {"ok": False, "reason": "no nudge up to %.2f mm works" %
                                   P.mm(NUDGE_MAX), "ref": ref}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--skip-drc", action="store_true")
    ap.add_argument("--no-nudge", action="store_true",
                    help="report pad-to-pad pinches instead of moving a part")
    a = ap.parse_args()
    root = a.root

    import pcbnew
    bpath = P.board_path(root)
    board = pcbnew.LoadBoard(bpath)
    idx = R.CopperIndex(pcbnew, board)
    holes = P.npth_holes(pcbnew, board)
    log = {"step": "L5"}

    log["pairs_before"] = [
        {"gap_mm": P.mm(p["gap"]) if p["gap"] is not None else None,
         "a": P.describe(board, p["a"]), "b": P.describe(board, p["b"]),
         "layer": board.GetLayerName(p["layer"])}
        for p in P.clearance_pairs(pcbnew, board, idx, P.CLEARANCE)]
    log["hole_pairs_before"] = [
        {"gap_mm": P.mm(p["gap"]), "a": P.describe(board, p["a"]),
         "b": P.describe(board, p["b"])}
        for p in P.hole_pairs(pcbnew, board, idx, P.HOLE_TO_HOLE)]

    fixes, unresolved = [], []
    done = set()
    for _round in range(ROUNDS):
        pairs = P.clearance_pairs(pcbnew, board, idx, P.CLEARANCE)
        pairs = [p for p in pairs
                 if (min(R.uid(p["a"]), R.uid(p["b"])),
                     max(R.uid(p["a"]), R.uid(p["b"]))) not in done]
        if not pairs:
            break
        progress = False
        for pair in pairs:
            key = (min(R.uid(pair["a"]), R.uid(pair["b"])),
                   max(R.uid(pair["a"]), R.uid(pair["b"])))
            res = None
            for target in P.CLEARANCE_STEPS:
                res = P.fix_clearance_pair(pcbnew, board, idx, pair, holes,
                                           target=target)
                if res.get("ok"):
                    break
            if not res.get("ok") and not a.no_nudge:
                for which, other in ((pair["a"], pair["b"]),
                                     (pair["b"], pair["a"])):
                    if which.GetClass() != "PAD":
                        continue
                    nud = nudge_footprint(pcbnew, board, idx, which, other,
                                          holes, P.CLEARANCE)
                    if nud.get("ok"):
                        res.update(nud)
                        break
            if res.get("ok"):
                fixes.append(res)
                progress = True
                done.add(key)
            else:
                unresolved.append(res)
                done.add(key)
        if not progress:
            break

    hole_fixes = []
    for pair in P.hole_pairs(pcbnew, board, idx, P.HOLE_TO_HOLE):
        for first in (pair["a"], pair["b"]):
            if first.GetClass() != "PCB_VIA":
                continue
            res = P.retreat_via(pcbnew, board, idx, first, holes,
                                P.HOLE_CLEARANCE)
            res["gap_before_mm"] = P.mm(pair["gap"])
            hole_fixes.append(res)
            if res.get("ok"):
                break
    log["hole_to_hole_fixes"] = hole_fixes
    log["fixes"] = fixes
    log["unresolved"] = unresolved

    nets = set()
    for p in log["pairs_before"]:
        nets.update({p["a"].get("net"), p["b"].get("net")})
    netcodes = sorted({board.FindNet(n).GetNetCode() for n in nets
                       if n and board.FindNet(n) is not None})
    healed, floating = P.heal_nets(pcbnew, board, idx, netcodes, log=log)
    log["islands_reconnected"] = healed
    log["islands_still_floating"] = floating

    idx.rebuild()
    left = P.clearance_pairs(pcbnew, board, idx, P.CLEARANCE)
    log["pairs_after"] = [
        {"gap_mm": P.mm(p["gap"]) if p["gap"] is not None else None,
         "a": P.describe(board, p["a"]), "b": P.describe(board, p["b"]),
         "layer": board.GetLayerName(p["layer"])} for p in left]
    log["hole_pairs_after"] = [
        {"gap_mm": P.mm(p["gap"]), "a": P.describe(board, p["a"]),
         "b": P.describe(board, p["b"])}
        for p in P.hole_pairs(pcbnew, board, idx, P.HOLE_TO_HOLE)]

    board.BuildListOfNets()
    diffs, _mech = P.contract_diff(board, pcbnew, root)
    log["contract_diffs"] = diffs[:20]
    log["counts_after"] = P.counts(board, pcbnew)
    log["unconnected_before_save"] = P.unconnected_count(pcbnew, board)
    pcbnew.SaveBoard(bpath, board)

    drc_ok, cur, delta, sig = False, None, {}, {}
    if not a.skip_drc:
        drc_ok, cur, _p = P.drc_with_healing(root, "s5_l5", log=log)
        if drc_ok:
            base = P.load_drc(os.path.join(root, "logs",
                                           "drc_after_uuidfix.json"))
            delta = P.drc_delta(base, cur)
            sig = D.compare(base, cur)
            log["drc_after"] = {"errors_by_type": P.by_type(cur),
                                "unconnected": P.unconnected(cur)}
            log["drc_delta"] = delta

    checks = [
        P.check("clearance_pairs_left", 0, len(left)),
        P.check("hole_to_hole_pairs_left", 0, len(log["hole_pairs_after"])),
        P.check("no_floating_islands", 0, len(floating)),
        P.check("contract_parity", 0, len(diffs)),
        P.check("drc_ran", True, drc_ok),
        P.check("unconnected", 0, P.unconnected(cur) if cur else -1,
                ok=(drc_ok and P.unconnected(cur) == 0)),
        P.check("no_new_drc_signatures", [],
                sig.get("new_signatures", ["drc did not run"]),
                ok=(drc_ok and not sig.get("new_signatures"))),
    ]
    P.gate(root, "S5_L5", checks,
           notes="%d clearance pinches fixed, %d unresolved; %d hole-to-hole."
                 % (len(fixes), len(unresolved), len(hole_fixes)),
           extra=log)
    print(json.dumps({k: v for k, v in log.items()
                      if k not in ("contract_diffs",)}, indent=1)[:6000])
    return 0 if all(c["pass"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
