#!/usr/bin/env python3
"""L7: get R_CC1 out from under the USB-C shell and put its two pins back.

Found after the JLC cart was filled, from the connector's mechanical drawing.
R_CC1 (0603, the 5.1 k CC1 pull-down) sat at (178.166, 109.464) rot 90, body
(F.Fab) 177.7405..178.6214 x 108.6385..110.3194 -- entirely inside J1's body,
175.7915..183.1925 x 106.5125..115.4635. A 0.45 mm tall part under a receptacle
whose shell lands flat on the board means the connector cannot seat: the board
is unassemblable, not merely ugly. R_CC2, at (173.34, 110.226) west of the
connector, is fine and is not touched.

Where it went, and why not exactly where the brief asked
--------------------------------------------------------
The brief asked for the pocket behind J1 pad 4, about (173.44, 112.00) rot 0,
with "the shortest F.Cu track" to the pad. The pocket is right; that point and
that connection are not, and both reasons are measured rather than argued:

1. That exact point is not free copper. At rot 0 the part's pad 1 lands on the
   GND track at x 172.1715 and the GND stitching via at (172.9335, 112.1055),
   and pad 2 lands on the USB_VBUS_RAW run that climbs (173.6955, 111.191) ->
   (174.2545, 112.207) -> (174.2545, 112.766). The pocket is 3.04 mm of
   courtyard against 3.08 mm of gap, as the brief says, but it is the copper
   crossing it that decides, not the courtyard.

2. **J1 pad 4 cannot be entered from the west at all.** Its neighbours are
   pad 3 at 0.2002 mm, pad 5 at 0.2002 mm and the USB_DM via
   (174.7625, 112.1055) at 0.1738 mm. The narrowest legal corridor on this
   board is min_track_width 0.0889 + 2 x clearance 0.0889 = **0.2667 mm**, so
   no track of any width fits through any of the three. Every route to pad 4
   has to leave it eastward, under the shell, exactly as the original did --
   and to reach anything west of the connector it then has to cross back under
   the pad column, which only B.Cu can do. Staying on F.Cu from the pocket
   means going the long way round the whole connector: 12.35 mm.

So R_CC1 goes 1.90 mm north-east of the brief's point, to

    (173.40, 113.90) rot 180     body 172.5745..174.2554 x 113.4446..114.3255

1.206 mm clear of J1's body (the brief asks for 0.2), 0.961 mm from its
nearest neighbour (C_USB_V3), no courtyard overlap at all, worst pad-to-copper
gap 0.3785 mm against the 0.0889 mm rule. It sits beside R_CC2, which is where
the CC network belongs. USB_CC1 becomes 4.14 mm in three segments: 0.78 mm of
F.Cu to a via at (174.879, 114.173), a B.Cu diagonal under J1's pad column to
a via at (176.5935, 112.268), and 0.80 mm of F.Cu back into pad 4 from the
east. GND leaves pin 2 on 0.51 mm of F.Cu into a via at (172.6465, 114.408)
and the In1 plane.

Why not the band south of the connector
---------------------------------------
It is the obvious via-neutral answer -- (176.55, 116.90) rot 180 reaches pad 4
in 5.85 mm of F.Cu alone, no B.Cu, no extra via -- and it was tried and
rejected on the board, not on paper. **It cuts the chassis ground.** The
CHASSIS_GND pour wraps J1 on F.Cu over 174.864..181.163 x 104.384..116.703,
and both J1 shell-leg lands on the west side sit inside it. Running USB_CC1
south through the corridor between the two leg lands leaves a 0.103 mm strip
between pad 13 and the new track -- thinner than the zone's minimum web, so
the filler drops it. Measured: the pour went from 2 filled islands to 4, and
DRC reported `unconnected_items` between J1 pad 13 [CHASSIS_GND] and its own
zone. Any south placement also puts the resistor's own pads and its ground via
inside that pour. The two vias the pocket costs are the cheaper defect.

The one thing the two vias do cost is the via tally: 239 -> **241**. ACCEPTANCE
D allows a recorded increment, and this is the record; but
`50_final_check.py`'s "D IPC-D-356 feature counts" == [239, 417, 16, 6] reads
that number out of the exported package, so **when S8 is next re-exported that
constant has to become 241**. It is left at 239 here on purpose: fab/ is not
re-exported by this repair, so ACCEPTANCE A-G still measures the package that
exists.

A router defect found on the way
--------------------------------
lib/maze's open-node cache was keyed on (ix, iy, layer) with no width, so
`_via_open` inherited the answer given for a 0.2032 mm track when asking about
a 0.6095 mm via. It placed a via 0.1930 mm from J1 pad 3 -- legal for the
track, a short for the via -- and, in the other direction, poisoned track nodes
with a via's answer, which is why this route first looked impossible and the
repair nearly settled for the south band. Fixed in lib/maze.py; the board as
committed never carried an illegal via (DRC was clean), so nothing earlier has
to be redone.

What it removes and what it lays
--------------------------------
USB_CC1 has exactly two pads, J1.4 and R_CC1.1, so all seven of its F.Cu
tracks served only the old position and all seven come out. R_CC1's ground was
a stub of its own -- one F.Cu track (178.166, 107.432) -> (178.166, 108.7145)
and the via at its far end into the In1 GND plane -- and `route.trace_island`
confirms no other pad hangs off it before it is deleted.

Idempotent: if R_CC1's body already clears J1's by the margin, the script
re-measures and re-gates without touching the board.

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

REF = "R_CC1"
CONN = "J1"
CC_PAD = "4"                                    # J1's USB_CC1 pin
NET = "USB_CC1"

# Where the part goes. See the docstring for how it was chosen; the search
# below re-derives it if the board has moved under us.
CHOSEN = (173.40, 113.90, 180.0)
# What the brief asked for, kept so the gate can say why it was not used.
BRIEF_TARGET = (173.44, 112.00, 0.0)
# The via-neutral answer south of the connector, measured every run and
# reported. Not taken: its route severs the CHASSIS_GND pour (see docstring).
SOUTH_ALT = (176.55, 116.90, 180.0)
SOUTH_ALT_NOTE = (
    "reaches J1 pad 4 in 5.85 mm of F.Cu with no extra via, but the route "
    "leaves a 0.103 mm web between J1 pad 13 [CHASSIS_GND] and the new track: "
    "measured on the board, the CHASSIS_GND pour broke from 2 filled islands "
    "into 4 and DRC reported unconnected_items between pad 13 and its own "
    "zone. The resistor's pads and ground via would sit inside that pour too.")

# What the board must hold when this repair is done. It had 239 vias; the
# B.Cu hop under J1's pad column adds two and the old ground stub takes one
# away, and the stub's replacement puts one back. Asserted rather than
# "unchanged" so a different number is still a failure.
EXPECTED_VIAS = 241

# J1's body has to stay this clear of R_CC1's body.
SHELL_MARGIN = int(0.2 * P.IU)
# Same 0.17 mm the other repairs hold new pads at: at 2 mil mask expansion a
# side, two pads closer than about 0.15 mm have their mask openings merge and
# DRC reports solder_mask_bridge instead of clearance.
PAD_CLEARANCE = int(0.17 * P.IU)
BODY_GAP = int(0.2 * P.IU)
# The pocket west of the connector, for the fallback search: outside the shell
# and outside the CHASSIS_GND pour that wraps J1 (which starts at x 174.864).
SEARCH_BOX = (172.6, 112.4, 174.6, 114.8)
SEARCH_STEP = 0.05
MAX_CC1_MM = 8.0


def body(pcbnew, fp):
    return [P.mm(v) for v in R.body_box(pcbnew, fp)]


def box_gap(a, b):
    """Separation between two axis-aligned boxes; negative when they overlap."""
    dx = max(a[0] - b[2], b[0] - a[2])
    dy = max(a[1] - b[3], b[1] - a[3])
    if dx >= 0 and dy >= 0:
        return math.hypot(dx, dy)
    return max(dx, dy)


def place(pcbnew, fp, x, y, rot):
    fp.SetOrientationDegrees(rot)
    fp.SetPosition(pcbnew.VECTOR2I(int(round(x * P.IU)), int(round(y * P.IU))))


def blockers(pcbnew, board, idx, bodyidx, fp, holes, shell, own):
    """Everything that stops the footprint sitting where it is now."""
    out = []
    bx = body(pcbnew, fp)
    if box_gap(bx, shell) < P.mm(SHELL_MARGIN):
        out.append("body is %.4f mm from %s's body, under the %.2f mm margin"
                   % (box_gap(bx, shell), CONN, P.mm(SHELL_MARGIN)))
    edge = P.board_box()
    for pad in fp.Pads():
        for name, h in holes.items():
            g = P.hole_gap(pcbnew, board, pad, h)
            if g is not None and g < P.HOLE_CLEARANCE:
                out.append("pad %s is %.4f mm from %s"
                           % (pad.GetNumber(), P.mm(g), name))
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
            bad = idx.shape_conflicts(sh, layer, PAD_CLEARANCE,
                                      pad.GetNetCode(), ignore=own)
            if bad:
                out.append("pad %s clashes with %s" % (
                    pad.GetNumber(),
                    ", ".join(sorted({"%s %s" % (P.describe(board, b)["kind"],
                                                 P.describe(board, b)["net"])
                                      for b in bad[:4]}))))
    clash = bodyidx.clash(fp, BODY_GAP)
    if clash:
        out.append("body is within %.2f mm of %s" % (P.mm(BODY_GAP), clash))
    return out


def worst_pad_gap(pcbnew, board, idx, fp, own):
    """The tightest gap from any of this part's pads to copper of another net."""
    worst = None
    ceiling = int(0.6 * P.IU)
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
                             P.describe(board, item).get("net"))
    if worst is None:
        return None
    return {"gap_mm": P.mm(worst[0]), "pad": worst[1], "against": worst[2]}


def route_cc1(pcbnew, board, idx, fp, conn_pad, f_cu_only=True):
    """Plan USB_CC1 from R_CC1 pin 1 to J1 pad 4. F.Cu only unless told else.

    The index is rebuilt first. It caches one SHAPE per item at build time, so
    after the footprint has been moved it still holds R_CC1's pads where they
    used to be; the placement tests can live with that because they pass the
    part's own pads in `ignore`, but the router has to see the board as it now
    is.
    """
    idx.rebuild()
    pad1 = [p for p in fp.Pads() if p.GetNumber() == "1"][0]
    s = pad1.GetPosition()
    g = conn_pad.GetPosition()
    layers = [pcbnew.F_Cu] if f_cu_only else [pcbnew.F_Cu, pcbnew.B_Cu]
    rt = M.Router(pcbnew, board, idx, P.rules(), layers=layers)
    return rt.route([(s.x, s.y, pcbnew.F_Cu)], pad1.GetNetCode(),
                    goals=[(g.x, g.y, pcbnew.F_Cu)], ignore=[pad1, conn_pad],
                    margin_mm=5.0, max_nodes=400000,
                    max_length_mm=MAX_CC1_MM)


def best_route(pcbnew, board, idx, fp, conn_pad):
    """F.Cu if it can be done in the budget, otherwise one hop through B.Cu."""
    plan = route_cc1(pcbnew, board, idx, fp, conn_pad, f_cu_only=True)
    if plan.get("ok"):
        return plan
    two = route_cc1(pcbnew, board, idx, fp, conn_pad, f_cu_only=False)
    if two.get("ok"):
        two["f_cu_only_reason"] = plan.get("reason")
        return two
    return plan


def plan_summary(board, pcbnew, plan):
    if not plan.get("ok"):
        return {"ok": False, "reason": plan.get("reason")}
    return {"ok": True, "length_mm": plan.get("length_mm"),
            "segments": len(plan.get("tracks", [])),
            "vias": len(plan.get("vias", [])),
            "tracks": [[P.mm(a[0]), P.mm(a[1]), P.mm(b[0]), P.mm(b[1]),
                        board.GetLayerName(l)] for a, b, l in plan["tracks"]],
            "via_mm": [[P.mm(v[0]), P.mm(v[1])] for v in plan.get("vias", ())]}


def candidates():
    """Positions in the south band, nearest to J1 pad 4 first, on a fixed grid.

    Only used when CHOSEN does not fit -- which would mean the board changed
    since this repair was written. Deterministic so a rerun picks the same one.
    """
    x0, y0, x1, y1 = SEARCH_BOX
    out = []
    nx = int(round((x1 - x0) / SEARCH_STEP))
    ny = int(round((y1 - y0) / SEARCH_STEP))
    for i in range(nx + 1):
        for j in range(ny + 1):
            for rot in (180.0, 0.0):
                out.append((round(x0 + i * SEARCH_STEP, 3),
                            round(y0 + j * SEARCH_STEP, 3), rot))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--skip-drc", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--baseline", default="drc_final",
                    help="logs/<name>.json to compare the DRC signatures with")
    a = ap.parse_args()
    root = a.root

    import pcbnew
    bpath = P.board_path(root)
    board = pcbnew.LoadBoard(bpath)
    log = {"step": "L7", "ref": REF, "connector": CONN, "net": NET}

    fp = board.FindFootprintByReference(REF)
    conn = board.FindFootprintByReference(CONN)
    conn_pad = [p for p in conn.Pads() if p.GetNumber() == CC_PAD][0]
    holes = P.npth_holes(pcbnew, board)
    shell = body(pcbnew, conn)
    own = list(fp.Pads())

    log["shell_fab_mm"] = [round(v, 4) for v in shell]
    log["before"] = {
        "pos_mm": [P.mm(fp.GetPosition().x), P.mm(fp.GetPosition().y)],
        "rot_deg": fp.GetOrientationDegrees(),
        "body_mm": [round(v, 4) for v in body(pcbnew, fp)],
        "shell_gap_mm": round(box_gap(body(pcbnew, fp), shell), 4),
        "pads": [{"number": p.GetNumber(), "net": p.GetNetname(),
                  "pos_mm": [P.mm(p.GetPosition().x), P.mm(p.GetPosition().y)]}
                 for p in fp.Pads()],
    }
    log["connector_pad_mm"] = [P.mm(conn_pad.GetPosition().x),
                               P.mm(conn_pad.GetPosition().y)]

    # --- why the connector's pad column has only one way in ------------------
    # Measured, not assumed: the narrowest legal corridor on this board is one
    # minimum-width track with clearance on both sides.
    corridor = P.MIN_TRACK_W + 2 * P.CLEARANCE
    neighbours = []
    for other in conn.Pads():
        if R.uid(other) == R.uid(conn_pad):
            continue
        try:
            g = P._actual_gap(conn_pad.GetEffectiveShape(pcbnew.F_Cu),
                              other.GetEffectiveShape(pcbnew.F_Cu),
                              int(0.5 * P.IU))
        except Exception:
            continue
        if g is not None:
            neighbours.append({"what": "%s pad %s" % (CONN, other.GetNumber()),
                               "gap_mm": P.mm(g)})
    for t in board.GetTracks():
        # Same-net copper is the connection, not an obstacle. Without this the
        # measurement reads 0.0010 mm on a re-run, because by then USB_CC1's
        # own via is sitting next to the pad.
        if t.GetClass() != "PCB_VIA" or t.GetNetCode() == conn_pad.GetNetCode():
            continue
        g = P._actual_gap(conn_pad.GetEffectiveShape(pcbnew.F_Cu),
                          t.GetEffectiveShape(pcbnew.F_Cu), int(0.5 * P.IU))
        if g is not None:
            p = t.GetPosition()
            neighbours.append({"what": "via [%s] at (%.4f, %.4f)"
                                       % (t.GetNetname(), P.mm(p.x), P.mm(p.y)),
                               "gap_mm": P.mm(g)})
    log["pad4_access"] = {
        "min_legal_corridor_mm": P.mm(corridor),
        "note": "min_track_width + 2 x clearance; nothing narrower may pass",
        "neighbours_within_0.5mm": sorted(neighbours,
                                          key=lambda r: r["gap_mm"]),
        "west_entry_possible": all(n["gap_mm"] >= P.mm(corridor)
                                   for n in neighbours),
    }

    already = box_gap(body(pcbnew, fp), shell) >= P.mm(SHELL_MARGIN)
    log["already_clear"] = already

    # --- the copper that only served the old position -----------------------
    net = board.FindNet(NET)
    net_pads = [(f.GetReference(), p.GetNumber())
                for f in board.GetFootprints() for p in f.Pads()
                if p.GetNetname() == NET]
    log["net_pads"] = sorted(net_pads)
    pad1 = [p for p in fp.Pads() if p.GetNumber() == "1"][0]
    pad2 = [p for p in fp.Pads() if p.GetNumber() == "2"][0]

    doomed = []
    if not already:
        if sorted(net_pads) != sorted([(CONN, CC_PAD), (REF, "1")]):
            log["error"] = ("%s does not have exactly the two pads this repair "
                            "knows about: %s" % (NET, sorted(net_pads)))
            P.gate(root, "S5_L7", [P.check("net_shape_known", True, False)],
                   notes=log["error"], extra=log)
            print(json.dumps(log, indent=1))
            return 1
        doomed += [t for t in board.GetTracks() if t.GetNetname() == NET]
        gnd_island, gnd_shared = R.trace_island(pcbnew, board, pad2)
        log["gnd_stub"] = {
            "items": [P.describe(board, i) for i in gnd_island],
            "shared_with_pads": [P.describe(board, p) for p in gnd_shared]}
        if gnd_shared:
            log["error"] = ("the GND copper on %s pin 2 also serves %d other "
                            "pad(s); it is not a stub and is not deleted"
                            % (REF, len(gnd_shared)))
            P.gate(root, "S5_L7", [P.check("gnd_stub_is_private", True, False)],
                   notes=log["error"], extra=log)
            print(json.dumps(log, indent=1))
            return 1
        doomed += gnd_island
    log["removed"] = [P.describe(board, t) for t in doomed]
    log["removed_vias"] = sum(1 for t in doomed if t.GetClass() == "PCB_VIA")

    if doomed:
        R.remove_items(board, doomed)
    idx = R.CopperIndex(pcbnew, board)
    bodyidx = R.BodyIndex(pcbnew, board, skip_refs={REF} | set(holes))
    courtidx = R.CourtyardIndex(pcbnew, board, skip_refs={REF})

    # --- record what the brief asked for, and the south alternative ---------
    if not already:
        origin = (P.mm(fp.GetPosition().x), P.mm(fp.GetPosition().y),
                  fp.GetOrientationDegrees())
        for tag, (x, y, rot) in (("brief_target", BRIEF_TARGET),
                                 ("south_alternative", SOUTH_ALT)):
            place(pcbnew, fp, x, y, rot)
            why = blockers(pcbnew, board, idx, bodyidx, fp, holes, shell, own)
            rec = {"pos_mm": [x, y], "rot_deg": rot, "blockers": why}
            if tag == "south_alternative":
                rec["rejected_because"] = SOUTH_ALT_NOTE
            if not why:
                rec["f_cu_only"] = plan_summary(
                    board, pcbnew,
                    route_cc1(pcbnew, board, idx, fp, conn_pad, True))
                rec["with_vias"] = plan_summary(
                    board, pcbnew,
                    route_cc1(pcbnew, board, idx, fp, conn_pad, False))
                rec["worst_pad_gap"] = worst_pad_gap(pcbnew, board, idx, fp,
                                                     own)
            log[tag] = rec
        place(pcbnew, fp, *origin)

    # --- choose the position ------------------------------------------------
    chosen, plan = None, None
    if already:
        chosen = (P.mm(fp.GetPosition().x), P.mm(fp.GetPosition().y),
                  fp.GetOrientationDegrees())
    else:
        place(pcbnew, fp, *CHOSEN)
        why = blockers(pcbnew, board, idx, bodyidx, fp, holes, shell, own)
        if not why:
            plan = best_route(pcbnew, board, idx, fp, conn_pad)
            if plan.get("ok"):
                chosen = CHOSEN
            else:
                why = ["USB_CC1 does not route: %s" % plan.get("reason")]
        log["chosen_verified"] = {"pos_mm": list(CHOSEN[:2]),
                                  "rot_deg": CHOSEN[2], "blockers": why}
        if chosen is None:
            # The board moved under this repair. Re-derive a position rather
            # than fail: same predicates, same grid, nearest to J1 pad 4 first.
            log["fallback_search"] = {"reason": why}
            g = conn_pad.GetPosition()
            ranked = []
            for (x, y, rot) in candidates():
                place(pcbnew, fp, x, y, rot)
                if blockers(pcbnew, board, idx, bodyidx, fp, holes, shell, own):
                    continue
                p1 = [p for p in fp.Pads() if p.GetNumber() == "1"][0]
                d = math.hypot(p1.GetPosition().x - g.x,
                               p1.GetPosition().y - g.y)
                ranked.append((round(P.mm(d), 2), -1.0, x, y, rot))
            ranked.sort()
            for _d, _s, x, y, rot in ranked[:12]:
                place(pcbnew, fp, x, y, rot)
                pl = best_route(pcbnew, board, idx, fp, conn_pad)
                if pl.get("ok"):
                    chosen, plan = (x, y, rot), pl
                    break
            log["fallback_search"]["legal_positions"] = len(ranked)
            log["fallback_search"]["taken"] = chosen
        if chosen is None:
            log["error"] = "no legal position for %s in the band south of %s" \
                           % (REF, CONN)
            P.gate(root, "S5_L7", [P.check("position_found", True, False)],
                   notes=log["error"], extra=log)
            print(json.dumps(log, indent=1))
            return 1
        place(pcbnew, fp, *chosen)

    log["after"] = {
        "pos_mm": [P.mm(fp.GetPosition().x), P.mm(fp.GetPosition().y)],
        "rot_deg": fp.GetOrientationDegrees(),
        "body_mm": [round(v, 4) for v in body(pcbnew, fp)],
        "shell_gap_mm": round(box_gap(body(pcbnew, fp), shell), 4),
        "moved_mm": round(math.hypot(
            P.mm(fp.GetPosition().x) - log["before"]["pos_mm"][0],
            P.mm(fp.GetPosition().y) - log["before"]["pos_mm"][1]), 4),
    }
    log["after"]["pads"] = [
        {"number": p.GetNumber(), "net": p.GetNetname(),
         "pos_mm": [P.mm(p.GetPosition().x), P.mm(p.GetPosition().y)]}
        for p in fp.Pads()]
    log["after"]["nearest_body"] = None
    bx = body(pcbnew, fp)
    near = None
    for ref, obox in bodyidx.entries:
        d = box_gap(bx, [P.mm(v) for v in obox])
        if near is None or d < near[1]:
            near = (ref, round(d, 4))
    log["after"]["nearest_body"] = {"ref": near[0], "gap_mm": near[1]}
    log["after"]["courtyard_overlap"] = courtidx.overlap(fp)

    if a.dry_run:
        print(json.dumps(log, indent=1))
        return 0

    # --- lay the copper -----------------------------------------------------
    made = []
    conn_res = {}
    if plan is not None:
        made += R.commit_route(pcbnew, board, plan, pad1.GetNetCode(),
                               P.TRACK_W, P.VIA_DIA, P.VIA_DRILL)
        idx.rebuild()
        conn_res[NET] = plan_summary(board, pcbnew, plan)
    else:
        conn_res[NET] = {"ok": True, "method": "already routed"}

    gnd = P.connect_pad(pcbnew, board, idx, pad2, rules_obj=P.rules())
    if gnd.get("ok") and gnd.get("plan"):
        made += P.commit(pcbnew, board, gnd, pad2.GetNetCode())
        idx.rebuild()
    gnd.pop("plan", None)
    conn_res["GND"] = gnd
    log["reconnect"] = conn_res
    log["added"] = [P.describe(board, t) for t in made]
    log["added_vias"] = sum(1 for t in made if t.GetClass() == "PCB_VIA")

    netcodes = sorted({pad1.GetNetCode(), pad2.GetNetCode()})
    healed, floating = P.heal_nets(pcbnew, board, idx, netcodes, log=log)
    log["islands_reconnected"] = healed
    log["islands_still_floating"] = floating

    log["worst_pad_gap_after"] = worst_pad_gap(pcbnew, board, idx, fp, own)
    board.BuildListOfNets()
    diffs, _mech = P.contract_diff(board, pcbnew, root)
    log["contract_diffs"] = diffs[:20]
    log["counts_after"] = P.counts(board, pcbnew)
    log["via_delta"] = log["added_vias"] - log["removed_vias"]
    log["unconnected_before_save"] = P.unconnected_count(pcbnew, board)
    pcbnew.SaveBoard(bpath, board)

    # --- gate ---------------------------------------------------------------
    drc_ok, cur, sig = False, None, {}
    if not a.skip_drc:
        drc_ok, cur, _p = P.drc_with_healing(root, "s5_l7", log=log)
        if drc_ok:
            base = P.load_baseline(root, a.baseline)
            if base is not None:
                sig = D.compare(base, cur)
                log["drc_signature"] = sig
            log["drc_after"] = {"errors_by_type": P.by_type(cur),
                                "unconnected": P.unconnected(cur)}

    after_gap = log["after"]["shell_gap_mm"]
    checks = [
        P.check("body_clear_of_%s" % CONN, ">= %.2f mm" % P.mm(SHELL_MARGIN),
                "%.4f mm" % after_gap, ok=after_gap >= P.mm(SHELL_MARGIN)),
        P.check("both_pins_connected", 2,
                sum(1 for r in conn_res.values() if r.get("ok"))),
        P.check("no_floating_islands", 0, len(floating)),
        P.check("contract_parity", 0, len(diffs)),
        P.check("via_count", EXPECTED_VIAS, log["counts_after"]["vias"],
                note="239 before L7; the B.Cu hop under J1's pad column adds "
                     "two. ACCEPTANCE D allows a recorded increment -- but "
                     "50_final_check's 'D IPC-D-356 feature counts' constant "
                     "has to become 241 when fab/ is next re-exported"),
        P.check("pth_pads_unchanged", 16, log["counts_after"]["pth_pads"]),
        P.check("drc_ran", True, drc_ok),
        P.check("unconnected", 0, P.unconnected(cur) if cur else -1,
                ok=(drc_ok and P.unconnected(cur) == 0)),
        P.check("drc_errors", 0,
                sum(P.by_type(cur).values()) if cur else -1,
                ok=(drc_ok and not P.by_type(cur))),
        P.check("no_new_drc_signatures", [],
                sig.get("new_signatures", ["drc did not run"]),
                ok=(drc_ok and not sig.get("new_signatures"))),
    ]
    if already:
        head = ("%s already sits clear of %s's shell at (%.3f, %.3f) rot %.0f, "
                "%.3f mm from the body; nothing to move."
                % (REF, CONN, log["after"]["pos_mm"][0],
                   log["after"]["pos_mm"][1], log["after"]["rot_deg"],
                   log["after"]["shell_gap_mm"]))
    else:
        head = ("%s moved %.3f mm out from under %s's shell to (%.3f, %.3f) "
                "rot %.0f, %.3f mm clear of the shell body; %d items removed, "
                "%d laid, vias %d -> %d."
                % (REF, log["after"]["moved_mm"], CONN,
                   log["after"]["pos_mm"][0], log["after"]["pos_mm"][1],
                   log["after"]["rot_deg"], log["after"]["shell_gap_mm"],
                   len(doomed), len(made),
                   log["counts_after"]["vias"] - log["via_delta"],
                   log["counts_after"]["vias"]))
    P.gate(root, "S5_L7", checks,
           notes="%s %s pad %s cannot be entered from the west (%.4f mm to the "
                 "USB_DM via, %.4f mm to its own neighbours, against a %.4f mm "
                 "minimum corridor), so USB_CC1 crosses the pad column on "
                 "B.Cu. The via-neutral position south of the connector was "
                 "tried and rejected: it severs the CHASSIS_GND pour at "
                 "%s pad 13."
                 % (head, CONN, CC_PAD,
                    min([n["gap_mm"] for n in neighbours
                         if n["what"].startswith("via")] or [0]),
                    min([n["gap_mm"] for n in neighbours
                         if not n["what"].startswith("via")] or [0]),
                    P.mm(corridor), CONN),
           extra=log)
    print(json.dumps({k: v for k, v in log.items()
                      if k not in ("contract_diffs",)}, indent=1)[:6000])
    return 0 if all(c["pass"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
