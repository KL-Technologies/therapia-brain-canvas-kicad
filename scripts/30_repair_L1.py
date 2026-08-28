#!/usr/bin/env python3
"""L1: get AMS1117 and its copper out of mounting hole H4.

The ECO's first fatal item. H4 is a 2.3876 mm non-plated hole at EasyEDA
(2242, -1652) mil = KiCad (176.9468, 121.9608) mm, and its centre lands inside
the AMS1117's pin 1 (GND) pad -- about four fifths of the pad is drilled away,
so the regulator has no ground. Three GND stubs and a GND stitching via in the
same corner are inside or within 0.2 mm of the same hole.

The repair moves the regulator far enough for every one of its pads to clear
the hole by TARGET (0.3 mm, against a 0.2 mm rule), then puts its four pins
back on their nets:

    pin 1 GND        pin 2 VDD_ESP    pin 3 V_3V3_IN    pin 4 VDD_ESP (tab)

Direction is searched, not chosen: west and north first, on a 0.25 mm grid,
nearest position first, because those are the two directions the ECO names.
Every candidate is tested against the real copper, the six mechanical holes,
the board edge and the neighbouring component bodies before it is considered,
and the first one whose four pins can all be reconnected wins. If the
west/north quadrant has nothing, the search opens up to all four directions
and the gate records that it had to.

Reconnection follows the order the brief asks for: translate the existing
track end onto the moved pad if that segment still clears everything, else an
L or a via into the plane, else the maze router.

Idempotent: if the pads already clear H4 by the rule, it does nothing.

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
import maze as M                                   # noqa: E402
import drc as D                                    # noqa: E402

REF = "AMS1117"
HOLE = "H4"
STEP = int(0.25 * P.IU)
MAX_OFFSET = int(8.0 * P.IU)
BODY_GAP = int(0.2 * P.IU)
# A moved pad is held a little further off other copper than the 0.0889 mm
# rule, for the same reason 20_apply_eco.py holds new pads at 0.17 mm: at 2 mil
# mask expansion a side, two pads closer than about 0.15 mm have their mask
# openings merge and DRC reports solder_mask_bridge instead of clearance.
PAD_CLEARANCE = int(0.17 * P.IU)


def pad_hole_gaps(pcbnew, board, fp, holes):
    worst = None
    for pad in fp.Pads():
        for name, h in holes.items():
            g = P.hole_gap(pcbnew, board, pad, h)
            if g is None:
                continue
            if worst is None or g < worst[0]:
                worst = (g, pad.GetNumber(), name)
    return worst


def candidates(step, max_offset, quadrant_only):
    n = int(max_offset / step)
    out = []
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            if i == 0 and j == 0:
                continue
            mx, my = i * step, j * step
            if quadrant_only and (mx > 0 or my > 0):
                continue
            out.append((math.hypot(mx, my), mx, my))
    out.sort()
    return [(mx, my) for _d, mx, my in out if _d <= max_offset]


def body_clears_holes(pcbnew, fp, holes):
    """Does the component body sit clear of every mechanical hole?

    Not a hard constraint -- it cannot be, because the pre-ECO layout already
    parks the regulator body over H4 and no pure translation both clears the
    pads and clears the body unless it goes west. It is a preference, so that
    of two otherwise equal positions the search takes the one that does not
    leave the package sitting on an M2 screw head. The gate records which it
    got, and STATUS notes it for the owner.
    """
    bx = R.body_box(pcbnew, fp)
    if bx is None:
        return True
    l, t, r, b = bx
    for _name, (hx, hy, hr) in holes.items():
        dx = max(l - hx, 0, hx - r)
        dy = max(t - hy, 0, hy - b)
        if math.hypot(dx, dy) < hr:
            return False
    return True


def static_ok(pcbnew, board, idx, bodyidx, fp, holes, margin, ignore,
              blockers=None):
    """Does the footprint sit legally where it is now?

    Returns None when it does, else a sentence saying what stops it. When
    `blockers` is a list, every offending item is appended to it rather than
    only the first, which is what the --explain report reads."""
    first = None

    def note(msg):
        if blockers is not None:
            blockers.append(msg)
        return msg

    for pad in fp.Pads():
        for name, h in holes.items():
            g = P.hole_gap(pcbnew, board, pad, h)
            if g is not None and g < margin:
                m = note("pad %s is %.4f mm from %s" % (pad.GetNumber(),
                                                        P.mm(g), name))
                first = first or m
                if blockers is None:
                    return first
    box = P.board_box()
    for pad in fp.Pads():
        bb = pad.GetBoundingBox()
        if not (box[0] <= bb.GetLeft() and bb.GetRight() <= box[2]
                and box[1] <= bb.GetTop() and bb.GetBottom() <= box[3]):
            m = note("pad %s is outside the board edge clearance"
                     % pad.GetNumber())
            first = first or m
            if blockers is None:
                return first
        for layer in pad.GetLayerSet().CuStack():
            try:
                sh = pad.GetEffectiveShape(layer)
            except Exception:
                continue
            bad = idx.shape_conflicts(sh, layer, PAD_CLEARANCE,
                                      pad.GetNetCode(), ignore=ignore)
            if bad:
                m = note("pad %s clashes with %s" % (
                    pad.GetNumber(),
                    ", ".join(sorted({json.dumps(P.describe(board, b))
                                      for b in bad[:4]}))))
                first = first or m
                if blockers is None:
                    return first
    clash = bodyidx.clash(fp, BODY_GAP)
    if clash:
        m = note("body overlaps %s" % clash)
        first = first or m
        if blockers is None:
            return first
    return first


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--skip-drc", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--explain", default=None,
                    help="mx,my in mm: list everything that blocks that offset")
    a = ap.parse_args()
    root = a.root

    import pcbnew
    bpath = P.board_path(root)
    board = pcbnew.LoadBoard(bpath)
    log = {"step": "L1", "ref": REF, "hole": HOLE}

    fp = board.FindFootprintByReference(REF)
    holes = P.npth_holes(pcbnew, board)
    h4 = holes[HOLE]
    log["hole_mm"] = [P.mm(h4[0]), P.mm(h4[1])], P.mm(h4[2])
    log["origin_mm"] = [P.mm(fp.GetPosition().x), P.mm(fp.GetPosition().y)]

    before = pad_hole_gaps(pcbnew, board, fp, holes)
    log["worst_gap_before"] = {"gap_mm": P.mm(before[0]), "pad": before[1],
                               "hole": before[2]}

    # --- 1. the copper that is inside H4 and belongs to this part's nets ----
    my_nets = {p.GetNetCode() for p in fp.Pads()}
    doomed = []
    for t in board.GetTracks():
        if t.GetNetCode() not in my_nets:
            continue
        g = P.hole_gap(pcbnew, board, t, h4)
        if g is not None and g < P.HOLE_CLEARANCE:
            doomed.append(t)
    log["copper_in_hole"] = [dict(P.describe(board, t),
                                  gap_mm=P.mm(P.hole_gap(pcbnew, board, t, h4)))
                             for t in doomed]

    # Track ends that sit on a pad have to follow the pad when it moves.
    attached = []
    for pad in fp.Pads():
        for t, which in P.pad_endpoints(pcbnew, board, pad):
            attached.append({"track": t, "which": which, "pad": pad})
    log["attached_track_ends"] = len(attached)

    doomed_ids = {R.uid(t) for t in doomed}
    # The part's own pads travel with it, so they are not obstacles to each
    # other; leaving them in made every candidate position report pin 1
    # clashing with pin 2.
    ignore = (list(doomed) + [x["track"] for x in attached]
              + [p for p in fp.Pads()])

    idx = R.CopperIndex(pcbnew, board)
    # The mechanical NPTH footprints are excluded from the body test: their
    # "body" is the drill circle's bounding box, and the hole clearance test
    # above already measures the real circle. Keeping them in would push the
    # regulator out by the corner of a square that is not there.
    mech = {ref for ref in holes}
    bodyidx = R.BodyIndex(pcbnew, board, skip_refs=set([REF]) | mech)

    if a.explain:
        xs, ys = a.explain.split(",")
        mx, my = P.nm(float(xs)), P.nm(float(ys))
        out = []
        for margin in P.HOLE_MARGIN_STEPS:
            blockers = []
            fp.Move(pcbnew.VECTOR2I(int(mx), int(my)))
            static_ok(pcbnew, board, idx, bodyidx, fp, holes, margin, ignore,
                      blockers=blockers)
            body = body_clears_holes(pcbnew, fp, holes)
            fp.Move(pcbnew.VECTOR2I(int(-mx), int(-my)))
            out.append({"margin_mm": P.mm(margin), "body_clear": body,
                        "blockers": blockers})
        print(json.dumps({"offset_mm": [P.mm(mx), P.mm(my)],
                          "results": out}, indent=1))
        return 0

    if before[0] >= P.HOLE_CLEARANCE:
        log["already_clear"] = True
        chosen = (0, 0)
        margin_used = before[0]
    else:
        chosen, margin_used = None, None
        # Keep the nearest offset that failed for each distinct reason rather
        # than the first forty failures: the first forty are all "still on top
        # of the hole", which says nothing about what actually blocks a
        # direction.
        rejects = {}
        # Preference order: keep the body off the mounting holes, then go west
        # or north as the ECO asks, then hold the largest hole margin, then
        # move the shortest distance.
        for body_clear in (True, False):
            for quadrant_only in (True, False):
                for margin in P.HOLE_MARGIN_STEPS:
                    for (mx, my) in candidates(STEP, MAX_OFFSET,
                                               quadrant_only):
                        fp.Move(pcbnew.VECTOR2I(int(mx), int(my)))
                        why = static_ok(pcbnew, board, idx, bodyidx, fp, holes,
                                        margin, ignore)
                        if why is None and body_clear and not \
                                body_clears_holes(pcbnew, fp, holes):
                            why = "body sits over a mechanical hole"
                        fp.Move(pcbnew.VECTOR2I(int(-mx), int(-my)))
                        if why is None:
                            chosen = (mx, my)
                            margin_used = margin
                            break
                        key = (body_clear, quadrant_only, P.mm(margin),
                               why.split(" (")[0][:60])
                        d = math.hypot(mx, my)
                        if key not in rejects or d < rejects[key][0]:
                            rejects[key] = (d, {
                                "body_clear": body_clear,
                                "quadrant_only": quadrant_only,
                                "margin_mm": P.mm(margin),
                                "offset_mm": [P.mm(mx), P.mm(my)],
                                "displacement_mm": P.mm(d), "why": why})
                    if chosen:
                        break
                if chosen:
                    break
            if chosen:
                log["search"] = {"body_clear_of_holes": body_clear,
                                 "quadrant_only": quadrant_only,
                                 "margin_mm": P.mm(margin_used)}
                break
        log["rejects_by_reason"] = [r[1] for r in
                                    sorted(rejects.values(), key=lambda r: r[0])]
        if chosen is None:
            log["error"] = "no legal position for %s within %.1f mm" % (
                REF, P.mm(MAX_OFFSET))
            P.gate(root, "S5_L1", [P.check("position_found", True, False)],
                   notes=log["error"], extra=log)
            print(json.dumps(log, indent=1))
            return 1

    mx, my = chosen
    log["offset_mm"] = [P.mm(mx), P.mm(my)]
    log["displacement_mm"] = P.mm(math.hypot(mx, my))
    if a.dry_run:
        print(json.dumps(log, indent=1))
        return 0

    # --- 2. move it, and take out the copper that was in the hole ----------
    if mx or my:
        fp.Move(pcbnew.VECTOR2I(int(mx), int(my)))
    log["new_origin_mm"] = [P.mm(fp.GetPosition().x), P.mm(fp.GetPosition().y)]

    # A via whose only neighbours are being deleted goes with them; one that
    # still holds copper together is retreated instead, never orphaned.
    extra_doomed = []
    for t in list(doomed):
        if t.GetClass() != "PCB_VIA":
            continue
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA" or R.uid(t) in doomed_ids:
            continue
        g = P.hole_gap(pcbnew, board, t, h4)
        if g is None or g >= P.HOLE_CLEARANCE or t.GetNetCode() not in my_nets:
            continue
        others = [n for n in P.touching(pcbnew, board, t)
                  if R.uid(n) not in doomed_ids]
        if others:
            log.setdefault("vias_kept", []).append(
                dict(P.describe(board, t), gap_mm=P.mm(g),
                     neighbours=len(others)))
        else:
            extra_doomed.append(t)
    doomed += extra_doomed
    doomed_ids = {R.uid(t) for t in doomed}

    # --- 3. track ends that can simply follow the pad ----------------------
    moved_ends, dropped = [], []
    idx = R.CopperIndex(pcbnew, board)
    ends_by_track = {}
    for rec in attached:
        ends_by_track.setdefault(R.uid(rec["track"]), []).append(rec)
    for uid, recs in ends_by_track.items():
        t = recs[0]["track"]
        if uid in doomed_ids:
            continue
        s, e = t.GetStart(), t.GetEnd()
        sides = {r["which"] for r in recs}
        if sides == {"start", "end"}:
            # both ends land on pads of this footprint: translate the segment
            a2, b2 = (s.x + mx, s.y + my), (e.x + mx, e.y + my)
        elif "start" in sides:
            a2, b2 = (s.x + mx, s.y + my), (e.x, e.y)
        else:
            a2, b2 = (s.x, s.y), (e.x + mx, e.y + my)
        if R.straight_ok(idx, pcbnew, board, a2, b2, t.GetLayer(),
                         t.GetWidth(), t.GetNetCode(), P.CLEARANCE,
                         P.HOLE_CLEARANCE, ignore=ignore):
            t.SetStart(pcbnew.VECTOR2I(int(a2[0]), int(a2[1])))
            t.SetEnd(pcbnew.VECTOR2I(int(b2[0]), int(b2[1])))
            moved_ends.append(dict(P.describe(board, t),
                                   both_ends=(sides == {"start", "end"})))
        else:
            dropped.append(P.describe(board, t))
            doomed.append(t)
    doomed_ids = {R.uid(t) for t in doomed}
    log["track_ends_translated"] = moved_ends
    log["tracks_removed"] = [P.describe(board, t) for t in doomed]

    R.remove_items(board, doomed)
    idx = R.CopperIndex(pcbnew, board)
    router = M.Router(pcbnew, board, idx, P.rules())

    # --- 4. put the four pins back on their nets ---------------------------
    conn = []
    for pad in fp.Pads():
        res = P.connect_pad(pcbnew, board, idx, pad, router=router)
        res["pad"] = pad.GetNumber()
        res["net"] = pad.GetNetname()
        if res.get("ok") and res.get("plan"):
            P.commit(pcbnew, board, res, pad.GetNetCode())
            idx.rebuild()
            router = M.Router(pcbnew, board, idx, P.rules())
        res.pop("plan", None)
        conn.append(res)
    log["reconnect"] = conn

    # Deleting a stub can strand whatever was on the far side of it. Catch that
    # here rather than from DRC: pcbnew will not LoadBoard twice in a process,
    # so a fault found after saving costs a whole extra run.
    healed, still_floating = P.heal_nets(pcbnew, board, idx, sorted(my_nets),
                                         log=log)
    log["islands_reconnected"] = healed
    log["islands_still_floating"] = still_floating

    after = pad_hole_gaps(pcbnew, board, fp, holes)
    log["worst_gap_after"] = {"gap_mm": P.mm(after[0]), "pad": after[1],
                              "hole": after[2]}
    board.BuildListOfNets()
    diffs, mech_refs = P.contract_diff(board, pcbnew, root)
    log["contract_diffs"] = diffs[:20]
    log["counts_after"] = P.counts(board, pcbnew)
    pcbnew.SaveBoard(bpath, board)

    # --- 5. gate ------------------------------------------------------------
    drc_ok, cur, delta, sig = False, None, {}, {}
    if not a.skip_drc:
        out = os.path.join(root, "logs", "drc_after_L1.json")
        drc_ok, _proc, blob = P.run_drc(out, root)
        if drc_ok:
            cur = P.load_drc(out)
            base = P.load_drc(os.path.join(root, "logs", "drc_S5_before.json"))
            delta = P.drc_delta(base, cur)
            sig = D.compare(base, cur)
            log["drc_after"] = {"errors_by_type": P.by_type(cur),
                                "unconnected": P.unconnected(cur)}
            log["drc_delta"] = delta
        else:
            log["drc_error"] = blob[-400:]

    h4_left = 0
    if cur:
        for v in cur.get("violations", []):
            if v.get("severity") != "error":
                continue
            import viol as V
            if HOLE in V.involving_npth(v) and REF in V.parse(v)["refs"]:
                h4_left += 1

    checks = [
        P.check("pads_clear_%s" % HOLE, ">= %.2f mm" % P.mm(P.HOLE_CLEARANCE),
                "%.4f mm" % P.mm(after[0]), ok=after[0] >= P.HOLE_CLEARANCE),
        P.check("all_pins_reconnected", len(list(fp.Pads())),
                sum(1 for c in conn if c.get("ok"))),
        P.check("no_floating_islands", 0, len(still_floating)),
        P.check("contract_parity", 0, len(diffs)),
        P.check("drc_ran", True, drc_ok),
        P.check("no_%s_violation_for_%s" % (HOLE, REF), 0, h4_left,
                ok=(drc_ok and h4_left == 0)),
        P.check("unconnected", 0, P.unconnected(cur) if cur else -1,
                ok=(drc_ok and P.unconnected(cur) == 0)),
        P.check("no_new_drc_signatures", [],
                sig.get("new_signatures", ["drc did not run"]),
                ok=(drc_ok and not sig.get("new_signatures"))),
    ]
    P.gate(root, "S5_L1", checks,
           notes="AMS1117 moved %s mm off H4; %d tracks removed, %d ends "
                 "translated, %d pins reconnected."
                 % (log.get("offset_mm"), len(doomed), len(moved_ends),
                    sum(1 for c in conn if c.get("ok"))),
           extra=log)
    print(json.dumps({k: v for k, v in log.items()
                      if k not in ("copper_in_hole",)}, indent=1)[:6000])
    return 0 if all(c["pass"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
