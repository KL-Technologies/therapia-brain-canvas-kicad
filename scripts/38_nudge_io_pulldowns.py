#!/usr/bin/env python3
"""S5_L9: R_IO2_DN and R_IO15_DN against the 32UE body's east edge.

    KPY scripts/38_nudge_io_pulldowns.py [--root .] [--nudge 0.30] [--dry-run]

The question
------------
37_umcu_32ue.py put U_MCU's body edge at board x = 174.213. The two GPIO
pull-downs sit immediately east of it and their pad 1 starts at x = 174.2152 --
**0.0022 mm** clear. The lead asked for a +0.30 mm nudge east so that the pad
copper stands 0.2 mm off the module body, if and only if DRC stays clean and
the parts stay 0.2 mm clear of F1 / D_LED / R_LED.

The answer, measured rather than argued
---------------------------------------
It cannot be done, and this script proves it every run rather than asserting
it: **ESP_RXD runs north-south at x = 175.2195 on F.Cu, 0.1525 mm wide, from
y 91.2775 to y 103.165** -- straight past both resistors, in the 0.71 mm
corridor between the module's castellations (east edge 175.0105) and the
pull-downs' pad 2 (west edge 175.7223). Pad 1's east edge is at 175.0217, so
the track is 0.1216 mm away. Moving the part 0.30 mm east puts pad 1 *on top
of* it: ESP_IO2 (and ESP_IO15) shorted to ESP_RXD. Measured, the largest
eastward shift that still holds the 0.0889 mm clearance rule is
**0.030 mm** against the 0.198 mm the target asks for -- and even that eats
into a gap the board already reports as one of its five `clearance` warnings
(pad 1 to ESP_RXD, 0.1219 mm, against a 0.127 mm recommendation).

So the parts stay where they are. What makes that safe is the thing the raw
number hides: **R_IO2_DN pad 1 already shares copper with U_MCU pad 24**, and
both are ESP_IO2. The land the module's castellated pin 24 solders to and the
land this resistor's pin 1 solders to are one piece of copper -- by EasyEDA's
original layout, not by accident -- so there is no independent solder joint
under the module edge to lift it. Same for R_IO15_DN pad 1 and U_MCU pad 23 on
ESP_IO15. The module's own pads run from x 172.9105 (well under the body) out
to 175.0105, which is 0.8 mm beyond the body edge: a pad near that edge is how
the part is built, not a defect.

Note also that 174.213 is the pessimistic of the two defensible placements of
the 19.2 mm body (see 37_umcu_32ue.py). Placed the other way -- the 32E
outline minus its 6.3 mm keep-out -- the body edge lands at 173.9305 and these
pads clear it by 0.2847 mm with nothing moved at all.

Read-mostly: it writes the board only if a nudge is both legal and needed.
Idempotent either way.
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

REFS = ("R_IO2_DN", "R_IO15_DN")
MODULE = "U_MCU"
NUDGE_MM = 0.30                       # what the lead asked for
TARGET_CLEAR_MM = 0.20                # pad copper to the module body edge
# Same margin the other placement repairs hold new pads at: at 2 mil mask
# expansion a side, two pads closer than about 0.15 mm merge their mask
# openings and DRC reports solder_mask_bridge instead of clearance.
PAD_CLEARANCE = int(0.17 * P.IU)
BODY_GAP = int(0.2 * P.IU)
# Reported explicitly because the lead named them.
WATCH = ("F1", "D_LED", "R_LED", "U_MCU")
SWEEP_STEP_MM = 0.005


def box_gap(a, b):
    dx = max(a[0] - b[2], b[0] - a[2])
    dy = max(a[1] - b[3], b[1] - a[3])
    if dx >= 0 and dy >= 0:
        return math.hypot(dx, dy)
    return max(dx, dy)


def outline_rect(pcbnew, fp):
    """The body rectangle from the F.Fab lines' endpoints, ignoring stroke."""
    xs, ys = [], []
    for d in fp.GraphicalItems():
        if d.GetClass() != "PCB_SHAPE" or d.GetLayer() != pcbnew.F_Fab:
            continue
        if d.ShowShape() == "Polygon":
            continue
        for pt in (d.GetStart(), d.GetEnd()):
            xs.append(pt.x)
            ys.append(pt.y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def pad_rows(fp):
    return [(p, p.GetBoundingBox()) for p in fp.Pads()]


def overlapping_pad(module, pad):
    """The module pad whose copper this pad's copper touches, if any."""
    bb = pad.GetBoundingBox()
    for mp in module.Pads():
        mb = mp.GetBoundingBox()
        if (mb.GetLeft() <= bb.GetRight() and bb.GetLeft() <= mb.GetRight()
                and mb.GetTop() <= bb.GetBottom()
                and bb.GetTop() <= mb.GetBottom()):
            return mp
    return None


def measure_pads(pcbnew, fp, edge_x, fab_box):
    """Every pad of `fp` against the module's body edge and its F.Fab box."""
    out = []
    for pad, bb in pad_rows(fp):
        out.append({
            "pad": pad.GetNumber(), "net": pad.GetNetname(),
            "bbox_mm": [P.mm(bb.GetLeft()), P.mm(bb.GetTop()),
                        P.mm(bb.GetRight()), P.mm(bb.GetBottom())],
            "to_body_edge_mm": round(P.mm(bb.GetLeft() - edge_x), 4),
            "to_fab_box_mm": round(P.mm(box_gap(
                [bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()],
                fab_box)), 4)})
    return out


def blockers(pcbnew, board, idx, bodyidx, fp, own, clearance=PAD_CLEARANCE):
    """Everything that stops the footprint sitting where it is now."""
    out = []
    edge = P.board_box()
    for pad in fp.Pads():
        bb = pad.GetBoundingBox()
        if not (edge[0] <= bb.GetLeft() and bb.GetRight() <= edge[2]
                and edge[1] <= bb.GetTop() and bb.GetBottom() <= edge[3]):
            out.append("pad %s is outside the board edge clearance"
                       % pad.GetNumber())
        for layer in pad.GetLayerSet().CuStack():
            try:
                sh = pad.GetEffectiveShape(layer)
            except Exception:
                continue
            bad = idx.shape_conflicts(sh, layer, clearance,
                                      pad.GetNetCode(), ignore=own)
            if bad:
                out.append("pad %s [%s] clashes with %s"
                           % (pad.GetNumber(), pad.GetNetname(),
                              ", ".join(sorted({
                                  "%s [%s]"
                                  % (P.describe(board, b)["kind"],
                                     P.describe(board, b)["net"])
                                  for b in bad[:4]}))))
    clash = bodyidx.clash(fp, BODY_GAP)
    if clash:
        out.append("body is within %.2f mm of %s" % (P.mm(BODY_GAP), clash))
    return out


def clearance_to_others(pcbnew, board, idx, fp, own, ceiling_mm=0.8):
    """Tightest gap from this part's pads to copper of any other net."""
    worst = None
    ceiling = int(ceiling_mm * P.IU)
    skip = {R.uid(i) for i in own}
    for pad in fp.Pads():
        for layer in pad.GetLayerSet().CuStack():
            try:
                sh = pad.GetEffectiveShape(layer)
            except Exception:
                continue
            bb = sh.BBox(ceiling)
            for item, inet, osh in idx._query(layer, bb.GetLeft(), bb.GetTop(),
                                              bb.GetRight(), bb.GetBottom()):
                if inet == pad.GetNetCode() and inet != 0:
                    continue
                if R.uid(item) in skip:
                    continue
                g = P._actual_gap(sh, osh, ceiling)
                if g is None:
                    continue
                if worst is None or g < worst[0]:
                    worst = (g, pad.GetNumber(),
                             P.describe(board, item).get("net"),
                             P.describe(board, item).get("kind"))
    if worst is None:
        return None
    return {"gap_mm": P.mm(worst[0]), "pad": worst[1], "against_net": worst[2],
            "against_kind": worst[3]}


def own_copper(board, fp):
    """The part's pads and the tracks that terminate on them."""
    own = list(fp.Pads())
    pts = [(p.GetPosition().x, p.GetPosition().y) for p in fp.Pads()]
    tol = int(0.001 * P.IU)
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            continue
        for end in (t.GetStart(), t.GetEnd()):
            if any(abs(end.x - x) <= tol and abs(end.y - y) <= tol
                   for x, y in pts):
                own.append(t)
                break
    return own


def retarget(pcbnew, board, tracks, old_pt, new_pt):
    """Follow a track end that used to sit on a pad centre to its new one."""
    tol = int(0.001 * P.IU)
    moved = []
    for t in tracks:
        if t.GetClass() == "PCB_VIA":
            continue
        for getter, setter in ((t.GetStart, t.SetStart), (t.GetEnd, t.SetEnd)):
            pt = getter()
            if abs(pt.x - old_pt[0]) <= tol and abs(pt.y - old_pt[1]) <= tol:
                setter(pcbnew.VECTOR2I(int(new_pt[0]), int(new_pt[1])))
                moved.append(P.describe(board, t))
    return moved


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--nudge", type=float, default=NUDGE_MM)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-drc", action="store_true")
    ap.add_argument("--baseline", default="drc_s5_l8")
    a = ap.parse_args()
    root = a.root

    import pcbnew
    bpath = P.board_path(root)
    board = pcbnew.LoadBoard(bpath)
    log = {"step": "L9", "refs": list(REFS), "module": MODULE,
           "nudge_asked_mm": a.nudge, "target_clear_mm": TARGET_CLEAR_MM}

    module = board.FindFootprintByReference(MODULE)
    fab = outline_rect(pcbnew, module)
    fab_box = R.body_box(pcbnew, module)
    edge_x = fab[2]
    log["module_body"] = {
        "outline_rect_mm": [P.mm(v) for v in fab],
        "fab_bbox_mm": [P.mm(v) for v in fab_box],
        "east_edge_mm": P.mm(edge_x),
        "pad_extent_east_mm": P.mm(max(p.GetBoundingBox().GetRight()
                                       for p in module.Pads())),
        "note": "the module's own castellated pads reach 0.7975 mm east of "
                "its body edge -- pads outside the body are how the part is "
                "built"}

    idx = R.CopperIndex(pcbnew, board)
    counts_before = P.counts(board, pcbnew)
    results = {}
    applied = []
    for ref in REFS:
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            results[ref] = {"error": "not on the board"}
            continue
        origin = fp.GetPosition()
        own = own_copper(board, fp)
        bodyidx = R.BodyIndex(pcbnew, board, skip_refs={ref})
        rec = {
            "pos_mm": [P.mm(origin.x), P.mm(origin.y)],
            "rot_deg": fp.GetOrientationDegrees(),
            "body_mm": [P.mm(v) for v in R.body_box(pcbnew, fp)],
            "pads": measure_pads(pcbnew, fp, edge_x, fab_box),
            "worst_pad_gap": clearance_to_others(pcbnew, board, idx, fp, own),
        }
        rec["body_to_module_mm"] = round(
            P.mm(box_gap(R.body_box(pcbnew, fp), fab_box)), 4)
        rec["body_to_watched_mm"] = {}
        for other in WATCH:
            of = board.FindFootprintByReference(other)
            if of is None or other == ref:
                continue
            rec["body_to_watched_mm"][other] = round(
                P.mm(box_gap(R.body_box(pcbnew, fp), R.body_box(pcbnew, of))),
                4)
        # Which module pad this part's pad 1 is welded to, and on what net.
        pad1 = [p for p in fp.Pads() if p.GetNumber() == "1"][0]
        mp = overlapping_pad(module, pad1)
        rec["pad1_shares_land_with"] = None if mp is None else {
            "module_pad": mp.GetNumber(), "module_net": mp.GetNetname(),
            "pad_net": pad1.GetNetname(),
            "same_net": mp.GetNetname() == pad1.GetNetname(),
            "overlap_x_mm": round(P.mm(
                min(mp.GetBoundingBox().GetRight(),
                    pad1.GetBoundingBox().GetRight())
                - max(mp.GetBoundingBox().GetLeft(),
                      pad1.GetBoundingBox().GetLeft())), 4)}
        need = TARGET_CLEAR_MM - min(p["to_body_edge_mm"] for p in rec["pads"]
                                     if p["to_body_edge_mm"] < 1.0)
        rec["shift_needed_mm"] = round(need, 4)

        # --- sweep east, largest shift first ---------------------------------
        # Twice, against two different bars. PAD_CLEARANCE (0.17 mm) is the
        # margin the placement repairs hold new pads at; P.CLEARANCE
        # (0.0889 mm) is the rule DRC actually enforces. Reporting both keeps
        # "no room by our own standard" apart from "no room at all" -- here
        # the answer is the same either way, but only the second one is a
        # statement about the board rather than about this pipeline.
        rec["blockers_at_current_position"] = blockers(
            pcbnew, board, idx, bodyidx, fp, own)
        steps = int(round(a.nudge / SWEEP_STEP_MM))
        tried, legal, legal_drc = [], None, None
        for i in range(steps, 0, -1):
            dx = i * SWEEP_STEP_MM
            fp.SetPosition(pcbnew.VECTOR2I(int(round(origin.x + dx * P.IU)),
                                           origin.y))
            why = blockers(pcbnew, board, idx, bodyidx, fp, own)
            why_drc = blockers(pcbnew, board, idx, bodyidx, fp, own,
                               clearance=P.CLEARANCE)
            if abs(dx - a.nudge) < 1e-9 or (legal is None and not why) \
                    or (legal_drc is None and not why_drc):
                tried.append({"dx_mm": round(dx, 4), "blockers": why,
                              "blockers_at_drc_clearance": why_drc,
                              "worst_pad_gap": clearance_to_others(
                                  pcbnew, board, idx, fp, own)})
            if not why and legal is None:
                legal = dx
            if not why_drc and legal_drc is None:
                legal_drc = dx
        fp.SetPosition(origin)
        rec["sweep"] = tried
        rec["largest_legal_shift_mm"] = legal
        rec["largest_shift_at_drc_clearance_mm"] = legal_drc
        rec["asked_shift_legal"] = bool(
            legal is not None and legal >= a.nudge - 1e-9)
        rec["enough"] = bool(legal is not None and legal >= need - 1e-9)

        if rec["asked_shift_legal"] and rec["enough"] and need > 0:
            dx = int(round(a.nudge * P.IU))
            old_centres = [(p.GetNumber(),
                            (p.GetPosition().x, p.GetPosition().y))
                           for p in fp.Pads()]
            fp.SetPosition(pcbnew.VECTOR2I(origin.x + dx, origin.y))
            moved_tracks = []
            for num, old in old_centres:
                pad = [p for p in fp.Pads() if p.GetNumber() == num][0]
                moved_tracks += retarget(
                    pcbnew, board, own,
                    old, (pad.GetPosition().x, pad.GetPosition().y))
            idx.rebuild()
            rec["applied"] = {
                "dx_mm": a.nudge,
                "pos_mm": [P.mm(fp.GetPosition().x), P.mm(fp.GetPosition().y)],
                "tracks_retargeted": moved_tracks,
                "pads": measure_pads(pcbnew, fp, edge_x, fab_box),
                "worst_pad_gap": clearance_to_others(pcbnew, board, idx, fp,
                                                     own)}
            applied.append(ref)
        else:
            rec["applied"] = None
        results[ref] = rec

    log["parts"] = results
    log["applied"] = applied
    counts_after = P.counts(board, pcbnew)
    log["counts_before"] = counts_before
    log["counts_after"] = counts_after
    diffs, _mech = P.contract_diff(board, pcbnew, root)
    log["contract_diffs"] = diffs[:20]
    log["unconnected_before_save"] = P.unconnected_count(pcbnew, board)

    if a.dry_run:
        print(json.dumps(log, indent=1))
        return 0
    if applied:
        pcbnew.SaveBoard(bpath, board)
    log["board_written"] = bool(applied)

    drc_ok, cur, sig = None, None, {}
    if applied and not a.skip_drc:
        drc_ok, cur, _p = P.drc_with_healing(root, "s5_l9", log=log)
        if drc_ok:
            base = P.load_baseline(root, a.baseline)
            if base is not None:
                sig = D.compare(base, cur)
                log["drc_signature"] = sig
            log["drc_after"] = {"errors_by_type": P.by_type(cur),
                                "unconnected": P.unconnected(cur)}

    checks = []
    for ref in REFS:
        rec = results.get(ref, {})
        pads = rec.get("applied", {}).get("pads") if rec.get("applied") \
            else rec.get("pads", [])
        worst = min((p["to_body_edge_mm"] for p in pads), default=None)
        checks.append(P.check(
            "%s pad copper is outside the %s body outline" % (ref, MODULE),
            ">= 0 mm", "%.4f mm" % worst if worst is not None else None,
            ok=(worst is not None and worst >= 0),
            note="measured to the F.Fab outline centre line at x %.3f"
                 % P.mm(edge_x)))
        share = rec.get("pad1_shares_land_with") or {}
        checks.append(P.check(
            "%s pad 1 and the %s pad it lands on are the same net"
            % (ref, MODULE), True, share.get("same_net"),
            note="module pad %s [%s], %s mm of shared copper -- the two pins "
                 "solder to one land, so there is no separate joint under the "
                 "module edge" % (share.get("module_pad"),
                                  share.get("module_net"),
                                  share.get("overlap_x_mm"))))
        gaps = rec.get("body_to_watched_mm", {})
        tight = sorted(k for k, v in gaps.items() if v < 0.2)
        checks.append(P.check(
            "%s body stays 0.2 mm clear of %s" % (ref, ", ".join(WATCH)),
            [], tight, note=json.dumps(gaps, sort_keys=True)))
    checks.append(P.check("contract parity", 0, len(diffs)))
    checks.append(P.check(
        "copper unchanged unless a nudge was applied",
        counts_before, counts_after,
        note="applied: %s" % (applied or "none -- see the sweep in this "
                              "gate for what blocked it")))
    checks.append(P.check("unconnected", 0, log["unconnected_before_save"]))
    if applied and not a.skip_drc:
        checks += [
            P.check("drc ran", True, drc_ok),
            P.check("drc errors", 0,
                    sum(P.by_type(cur).values()) if cur else -1,
                    ok=(drc_ok and not P.by_type(cur))),
            P.check("drc unconnected", 0, P.unconnected(cur) if cur else -1,
                    ok=(drc_ok and P.unconnected(cur) == 0)),
            P.check("no new drc signatures", [],
                    sig.get("new_signatures", ["drc did not run"]),
                    ok=(drc_ok and not sig.get("new_signatures"))),
        ]

    if applied:
        head = "nudged %s east by %.2f mm." % (", ".join(applied), a.nudge)
    else:
        head = ("the +%.2f mm nudge is not available: %s. The board is "
                "unchanged."
                % (a.nudge,
                   "; ".join(
                       "%s blocked by %s"
                       % (ref, "; ".join(
                           results[ref]["sweep"][0]
                           ["blockers_at_drc_clearance"]
                           or results[ref]["sweep"][0]["blockers"]
                           or ["nothing -- it was not needed"]))
                       for ref in REFS if results.get(ref, {}).get("sweep"))))
    P.gate(root, "S5_L9", checks,
           notes="%s Pad-1 copper clears the %s body outline by %s mm and "
                 "shares its land with the module pin of the same net; the "
                 "largest eastward shift that still meets the 0.0889 mm "
                 "clearance rule is %s mm."
                 % (head, MODULE,
                    ", ".join("%s %.4f" % (
                        ref, min(p["to_body_edge_mm"]
                                 for p in results[ref]["pads"]))
                        for ref in REFS if ref in results and "pads" in
                        results[ref]),
                    ", ".join(
                        "%s %s" % (ref, results[ref].get(
                            "largest_shift_at_drc_clearance_mm"))
                        for ref in REFS if ref in results)),
           extra=log)
    bad = [c["name"] for c in checks if not c["pass"]]
    print("S5_L9: %s" % ("pass" if not bad else "FAIL " + ", ".join(bad)))
    for c in checks:
        print("  %-1s %-58s %s" % ("" if c["pass"] else "!", c["name"],
                                   "ok" if c["pass"] else
                                   "expected %r got %r" % (c["expected"],
                                                           c["actual"])))
    for ref in REFS:
        rec = results.get(ref, {})
        if "pads" not in rec:
            continue
        print("  %s at %s: pad gaps to the module body edge %s; needed "
              "%s mm; largest shift legal at 0.17 mm margin %s / at the "
              "0.0889 mm rule %s"
              % (ref, rec["pos_mm"],
                 ["%.4f" % p["to_body_edge_mm"] for p in rec["pads"]],
                 rec["shift_needed_mm"], rec["largest_legal_shift_mm"],
                 rec["largest_shift_at_drc_clearance_mm"]))
        print("     worst gap to other-net copper now: %s"
              % rec.get("worst_pad_gap"))
        for t in rec.get("sweep", []):
            print("     dx %.3f -> at the 0.0889 rule: %s | at the 0.17 "
                  "margin: %s"
                  % (t["dx_mm"],
                     t["blockers_at_drc_clearance"] or "legal",
                     t["blockers"] or "legal"))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
