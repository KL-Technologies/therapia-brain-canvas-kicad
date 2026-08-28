"""Shared machinery for the S5 layout repairs (L1-L5) and the S6 DRC loop.

Every repair script does the same five things: open the board, find the copper
a specific violation names, change it, prove the change is legal against the
same predicates DRC uses, and write a gate that says whether the violation went
away without taking anything else with it. That common part lives here so the
five scripts differ only in what they move.

The rule values are the ones scripts/14_make_rules.py wrote into the board, and
they are duplicated from scripts/20_apply_eco.py rather than imported so a
repair cannot silently drift from the ECO's idea of the same number. TARGET_*
are what the repairs actually aim for -- a margin above the rule, because a
repair that lands exactly on 0.2000 mm is one rounding away from failing again.

Nothing here relaxes a rule. A repair that cannot reach TARGET falls back
through smaller margins down to the rule value itself and records which one it
got; below the rule it reports failure instead.
"""

import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import route as R                                  # noqa: E402
import maze as M                                   # noqa: E402
import drc as D                                    # noqa: E402
import viol as V                                   # noqa: E402
import epro as E                                   # noqa: E402

IU = R.IU
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
BOARD_NAME = "Therapia_EEG-HRV"

# --- design rules (mirror scripts/14_make_rules.py and ACCEPTANCE C) --------
CLEARANCE = int(0.0889 * IU)
HOLE_TO_HOLE = int(0.2 * IU)
HOLE_CLEARANCE = int(0.2 * IU)
EDGE_CLEARANCE = int(0.2 * IU)
VIA_DIA = int(0.6096 * IU)
VIA_DRILL = int(0.3048 * IU)
TRACK_W = int(0.2032 * IU)
MIN_TRACK_W = int(0.0889 * IU)
BOARD_BOX_MM = (120.0, 80.0, 181.8236, 125.0088)

# What the repairs aim for, and what they will settle for, in that order.
TARGET_HOLE_MARGIN = int(0.3 * IU)
HOLE_MARGIN_STEPS = [int(v * IU) for v in (0.30, 0.25, 0.22, 0.20)]
CLEARANCE_STEPS = [int(v * IU) for v in (0.127, 0.11, 0.0889)]
# The longest route a reconnection may lay. A repair is local; when the only
# legal path is centimetres long the answer is to report the break, not to
# snake copper across the board -- the unbounded version answered one broken
# VDD_ESP link with 24.7 mm of track in 106 segments.
MAX_HEAL_MM = 8.0


def mm(v):
    return round(v / float(IU), 6)


def nm(v):
    return int(round(v * IU))


def board_path(root=None):
    return os.path.join(root or ROOT, "board", BOARD_NAME + ".kicad_pcb")


def board_box():
    lo_x, lo_y, hi_x, hi_y = BOARD_BOX_MM
    return (lo_x * IU + EDGE_CLEARANCE, lo_y * IU + EDGE_CLEARANCE,
            hi_x * IU - EDGE_CLEARANCE, hi_y * IU - EDGE_CLEARANCE)


def rules(clearance=None, hole_clearance=None, track_width=None):
    return M.Rules(CLEARANCE if clearance is None else clearance,
                   HOLE_CLEARANCE if hole_clearance is None else hole_clearance,
                   HOLE_TO_HOLE,
                   TRACK_W if track_width is None else track_width,
                   VIA_DIA, VIA_DRILL, board_box())


# --- board queries -----------------------------------------------------------
def npth_holes(pcbnew, board):
    """ref -> (x, y, radius) for every non-plated hole, in internal units."""
    out = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if int(p.GetAttribute()) != int(pcbnew.PAD_ATTRIB_NPTH):
                continue
            pos = p.GetPosition()
            d = p.GetDrillSize()
            out[fp.GetReference() or R.uid(fp)] = (pos.x, pos.y,
                                                   max(d.x, d.y) / 2.0)
    return out


def seg_point_distance(ax, ay, bx, by, px, py):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy)
                                         / L2))
    return math.hypot(ax + u * dx - px, ay + u * dy - py)


def hole_gap(pcbnew, board, item, hole):
    """Edge-to-edge distance from a piece of copper to a drilled hole.

    Negative means the copper overlaps the hole. Pads are measured against
    their real shape, not the bounding box, so a rounded pad is not reported
    as closer than it is."""
    hx, hy, hr = hole
    cls = item.GetClass()
    if cls == "PCB_VIA":
        p = item.GetPosition()
        return math.hypot(p.x - hx, p.y - hy) - hr - item.GetWidth() / 2.0
    if cls in ("PCB_TRACK", "PCB_ARC"):
        s, e = item.GetStart(), item.GetEnd()
        return (seg_point_distance(s.x, s.y, e.x, e.y, hx, hy) - hr
                - item.GetWidth() / 2.0)
    if cls == "PAD":
        best = None
        for layer in item.GetLayerSet().CuStack():
            try:
                sh = item.GetEffectiveShape(layer)
            except Exception:
                continue
            d = sh.Distance(pcbnew.VECTOR2I(int(hx), int(hy)))
            best = d if best is None else min(best, d)
        if best is None:
            return None
        return best - hr
    return None


def copper_near_hole(pcbnew, board, hole, limit, include_pads=True):
    """Everything whose edge comes within `limit` of a hole, worst first."""
    out = []
    for t in board.GetTracks():
        g = hole_gap(pcbnew, board, t, hole)
        if g is not None and g < limit:
            out.append((g, t))
    if include_pads:
        for f in board.GetFootprints():
            for p in f.Pads():
                if int(p.GetAttribute()) == int(pcbnew.PAD_ATTRIB_NPTH):
                    continue
                g = hole_gap(pcbnew, board, p, hole)
                if g is not None and g < limit:
                    out.append((g, p))
    out.sort(key=lambda r: r[0])
    return out


def describe(board, item):
    IUf = float(IU)
    cls = item.GetClass()
    if cls == "PCB_VIA":
        p = item.GetPosition()
        return {"kind": "via", "net": item.GetNetname(),
                "pos_mm": [round(p.x / IUf, 4), round(p.y / IUf, 4)],
                "dia_mm": round(item.GetWidth() / IUf, 4),
                "drill_mm": round(item.GetDrillValue() / IUf, 4),
                "uuid": R.uid(item)}
    if cls in ("PCB_TRACK", "PCB_ARC"):
        s, e = item.GetStart(), item.GetEnd()
        return {"kind": "track", "net": item.GetNetname(),
                "layer": board.GetLayerName(item.GetLayer()),
                "start_mm": [round(s.x / IUf, 4), round(s.y / IUf, 4)],
                "end_mm": [round(e.x / IUf, 4), round(e.y / IUf, 4)],
                "width_mm": round(item.GetWidth() / IUf, 4),
                "uuid": R.uid(item)}
    if cls == "PAD":
        fp = item.GetParentFootprint()
        p = item.GetPosition()
        return {"kind": "pad", "net": item.GetNetname(),
                "ref": fp.GetReference() if fp else None,
                "number": item.GetNumber(),
                "pos_mm": [round(p.x / IUf, 4), round(p.y / IUf, 4)],
                "size_mm": [round(item.GetSize().x / IUf, 4),
                            round(item.GetSize().y / IUf, 4)],
                "uuid": R.uid(item)}
    return {"kind": cls, "uuid": R.uid(item)}


def pad_endpoints(pcbnew, board, pad, tol=None):
    """Tracks with an endpoint inside `pad`: [(track, "start"|"end")].

    This is what has to follow the pad when its footprint moves. A track that
    merely crosses the pad is not in the list -- moving one of its ends would
    drag copper that belongs to a different part of the net.
    """
    out = []
    net = pad.GetNetCode()
    shapes = {}
    for layer in pad.GetLayerSet().CuStack():
        try:
            shapes[layer] = pad.GetEffectiveShape(layer)
        except Exception:
            pass
    for t in board.GetTracks():
        if t.GetNetCode() != net or t.GetClass() == "PCB_VIA":
            continue
        sh = shapes.get(t.GetLayer())
        if sh is None:
            continue
        for which, p in (("start", t.GetStart()), ("end", t.GetEnd())):
            if sh.Collide(pcbnew.VECTOR2I(p.x, p.y), 0):
                out.append((t, which))
    return out


def vias_at(board, x, y, tol=None):
    tol = tol if tol is not None else int(0.01 * IU)
    out = []
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA":
            continue
        p = t.GetPosition()
        if math.hypot(p.x - x, p.y - y) <= tol:
            out.append(t)
    return out


def touching(pcbnew, board, item, exclude=()):
    """Same-net tracks and vias that physically meet `item`."""
    skip = {R.uid(i) for i in exclude}
    skip.add(R.uid(item))
    net = item.GetNetCode()
    return [t for t in board.GetTracks()
            if t.GetNetCode() == net and R.uid(t) not in skip
            and R.touches(pcbnew, item, t)]


# --- connectivity ------------------------------------------------------------
def net_components(pcbnew, board, idx, netcode):
    """The net's copper split into electrically separate islands.

    Needed because a repair that deletes a track can orphan whatever was on
    the far side of it, and the pad it was serving is not the only thing that
    can end up floating. Checking this before the board is saved beats waiting
    for DRC: pcbnew cannot LoadBoard twice in one process, so a fault found
    after saving costs another whole run.

    Items are joined when their shapes touch, and every item lying in a filled
    zone of the same net is joined to that zone -- which is how the planes
    actually carry GND, AVSS and the rest. Pairs are only tested when their
    bounding boxes share a 2 mm cell, or GND's several hundred pieces would be
    a quarter of a million shape collisions.

    Returns a list of lists of items, largest first.
    """
    items = [t for t in board.GetTracks() if t.GetNetCode() == netcode]
    items += [p for f in board.GetFootprints() for p in f.Pads()
              if p.GetNetCode() == netcode]
    parent = {}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    by_uid = {}
    for it in items:
        u = R.uid(it)
        parent[u] = u
        by_uid[u] = it

    cells = {}
    CELL = 2 * IU
    for it in items:
        bb = it.GetBoundingBox()
        for cx in range(bb.GetLeft() // CELL, bb.GetRight() // CELL + 1):
            for cy in range(bb.GetTop() // CELL, bb.GetBottom() // CELL + 1):
                cells.setdefault((cx, cy), []).append(it)
    tested = set()
    for bucket in cells.values():
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, b = bucket[i], bucket[j]
                ua, ub = R.uid(a), R.uid(b)
                key = (ua, ub) if ua < ub else (ub, ua)
                if key in tested:
                    continue
                tested.add(key)
                if find(ua) == find(ub):
                    continue
                if R.touches(pcbnew, a, b):
                    union(ua, ub)

    # Each filled island of each zone is its own conductor. Treating a net's
    # zones as one node says VDD_ESP is whole when it is actually three
    # separate pours -- which is exactly the split DRC found after L1 and this
    # check did not.
    islands = []
    for z in idx.zones:
        if z.GetNetCode() != netcode:
            continue
        for layer in z.GetLayerSet().CuStack():
            try:
                fill = z.GetFilledPolysList(layer)
            except Exception:
                continue
            if fill is None:
                continue
            for i in range(fill.OutlineCount()):
                ps = pcbnew.SHAPE_POLY_SET()
                ps.AddOutline(fill.Outline(i))
                # The holes matter. A plane is one outline with a hole punched
                # round every foreign pad and via; rebuilt without them it is
                # a solid rectangle, and then every item over the plane looks
                # connected to every other one.
                for j in range(fill.HoleCount(i)):
                    ps.AddHole(fill.Hole(i, j), 0)
                bb = ps.BBox(0)
                key = "Z:%s:%d:%d" % (R.uid(z), int(layer), i)
                parent[key] = key
                islands.append((key, layer, ps, bb))
    # Two zones of the same net can overlap -- the board has three VDD_ESP
    # pours -- and where they do they are one conductor. Without this the
    # check reported VDD_ESP split on a board DRC calls whole.
    for i in range(len(islands)):
        for j in range(i + 1, len(islands)):
            ka, la, pa, ba = islands[i]
            kb, lb, pb, bb2 = islands[j]
            if la != lb or find(ka) == find(kb):
                continue
            if (ba.GetRight() < bb2.GetLeft() or ba.GetLeft() > bb2.GetRight()
                    or ba.GetBottom() < bb2.GetTop()
                    or ba.GetTop() > bb2.GetBottom()):
                continue
            if pa.Collide(pb, 0):
                union(ka, kb)

    for it in items:
        ibb = it.GetBoundingBox()
        for key, layer, ps, bb in islands:
            if (bb.GetRight() < ibb.GetLeft() or bb.GetLeft() > ibb.GetRight()
                    or bb.GetBottom() < ibb.GetTop()
                    or bb.GetTop() > ibb.GetBottom()):
                continue
            if layer not in R.item_layers(pcbnew, it):
                continue
            if find(R.uid(it)) == find(key):
                continue
            try:
                sh = it.GetEffectiveShape(layer)
            except Exception:
                continue
            if ps.Collide(sh, 0):
                union(R.uid(it), key)

    groups = {}
    for u, it in by_uid.items():
        groups.setdefault(find(u), []).append(it)
    out = sorted(groups.values(), key=len, reverse=True)
    return out


def floating_items(pcbnew, board, idx, netcodes):
    """Items that are no longer joined to the largest island of their net."""
    out = []
    for nc in netcodes:
        comps = net_components(pcbnew, board, idx, nc)
        if len(comps) <= 1:
            continue
        for comp in comps[1:]:
            out.append({"net": board.FindNet(nc).GetNetname(),
                        "items": comp,
                        "size": len(comp)})
    return out


# --- reconnecting a pad ------------------------------------------------------
def pad_on_own_zone(pcbnew, board, idx, pad):
    """Is the pad already sitting in a filled zone of its own net?

    Only zones on a layer the pad is actually on count. An SMD pad on F.Cu
    over the In1 GND plane is NOT connected -- it needs a via -- and treating
    it as connected is how a pad ends up floating with DRC none the wiser.
    """
    name = pad.GetNetname()
    p = pad.GetPosition()
    for layer in pad.GetLayerSet().CuStack():
        if name in idx.zone_nets_at(p.x, p.y, layer):
            return board.GetLayerName(layer)
    return None


def connect_pad(pcbnew, board, idx, pad, rules_obj=None, ignore=(),
                width=None, max_via_reach_mm=3.0, router=None,
                margin_mm=3.5, max_nodes=250000):
    """Join `pad` back to its net, and say how.

    Order: already touching copper -> already on its own plane -> a via down
    into its own plane (short, and the usual answer for GND/AVSS/AVDD) -> the
    maze router to whatever copper the net already has. Each step is checked
    against the design rules before anything is placed; if none works the pad
    is reported unconnected rather than left with copper that does not reach.
    """
    rl = rules_obj or rules()
    width = int(width or rl.track_width)
    net = pad.GetNetCode()
    name = pad.GetNetname()
    p = pad.GetPosition()
    start = (p.x, p.y)

    already = touching(pcbnew, board, pad, exclude=ignore)
    already = [t for t in already if R.uid(t) not in {R.uid(i) for i in ignore}]
    if already:
        return {"ok": True, "method": "already touching copper",
                "items": len(already)}
    z = pad_on_own_zone(pcbnew, board, idx, pad)
    if z:
        return {"ok": True, "method": "already inside its own zone on %s" % z}

    # a via into the net's own plane
    if any(zz.GetNetname() == name for zz in idx.zones):
        r_min = rl.via_dia / 2.0 + rl.clearance
        for q in R.ring_points(start[0], start[1], r_min,
                               max_via_reach_mm * IU, int(0.127 * IU)):
            if not R.via_site_ok(idx, pcbnew, q[0], q[1], net, rl.via_dia,
                                 rl.via_drill, rl.clearance, rl.hole_to_hole,
                                 rl.hole_clearance, rl.edge_box, ignore=ignore):
                continue
            hit = [l for l in R.copper_layers(pcbnew, board)
                   if name in idx.zone_nets_at(q[0], q[1], l)]
            if not hit:
                continue
            if not R.straight_ok(idx, pcbnew, board, start, q, pcbnew.F_Cu,
                                 width, net, rl.clearance, rl.hole_clearance,
                                 ignore=ignore):
                continue
            return {"ok": True, "method": "via into the %s plane" % name,
                    "plan": {"ok": True, "tracks": [(start, q, pcbnew.F_Cu)],
                             "vias": [q]},
                    "via_mm": [mm(q[0]), mm(q[1])],
                    "length_mm": mm(math.hypot(q[0] - start[0],
                                               q[1] - start[1])),
                    "zone_layers": [board.GetLayerName(l) for l in hit]}

    rt = router or M.Router(pcbnew, board, idx, rl)
    layers = [l for l in pad.GetLayerSet().CuStack() if l in rt.layers]
    plan = rt.route([(start[0], start[1], l) for l in layers], net,
                    goal_net_copper=True, width=width, ignore=ignore,
                    margin_mm=margin_mm, max_nodes=max_nodes)
    if plan.get("ok"):
        return {"ok": True, "method": "maze route", "plan": plan,
                "length_mm": plan.get("length_mm"),
                "vias": len(plan.get("vias", []))}
    return {"ok": False, "reason": plan.get("reason"),
            "detail": {k: plan[k] for k in ("window_mm", "verify_failures")
                       if k in plan}}


def reconnect_island(pcbnew, board, idx, island, netcode, router=None,
                     rules_obj=None, width=None, margin_mm=4.0):
    """Route an orphaned island of copper back to the rest of its net.

    The island's own items go in `ignore` so the router does not decide it has
    arrived the moment it starts -- every node of the island is copper of the
    right net, and without this `goal_net_copper` succeeds at step zero.
    """
    rl = rules_obj or rules()
    width = int(width or rl.track_width)
    rt = router or M.Router(pcbnew, board, idx, rl)

    starts = []
    for it in island:
        cls = it.GetClass()
        if cls in ("PCB_TRACK", "PCB_ARC"):
            for p in (it.GetStart(), it.GetEnd()):
                starts.append((p.x, p.y, it.GetLayer()))
        else:
            p = it.GetPosition()
            for l in R.item_layers(pcbnew, it):
                if l in rt.layers:
                    starts.append((p.x, p.y, l))
    if not starts:
        return {"ok": False, "reason": "island has no routable point"}

    # A via straight down into the net's own plane, if it has one.
    if any(z.GetNetname() == board.FindNet(netcode).GetNetname()
           for z in idx.zones):
        name = board.FindNet(netcode).GetNetname()
        for (sx, sy, layer) in starts:
            r_min = rl.via_dia / 2.0 + rl.clearance
            for q in R.ring_points(sx, sy, r_min, 2.5 * IU, int(0.127 * IU)):
                if not R.via_site_ok(idx, pcbnew, q[0], q[1], netcode,
                                     rl.via_dia, rl.via_drill, rl.clearance,
                                     rl.hole_to_hole, rl.hole_clearance,
                                     rl.edge_box, ignore=island):
                    continue
                if not [l for l in R.copper_layers(pcbnew, board)
                        if name in idx.zone_nets_at(q[0], q[1], l)]:
                    continue
                if not R.straight_ok(idx, pcbnew, board, (sx, sy), q, layer,
                                     width, netcode, rl.clearance,
                                     rl.hole_clearance, ignore=island):
                    continue
                return {"ok": True,
                        "method": "via into the %s plane" % name,
                        "plan": {"ok": True,
                                 "tracks": [((sx, sy), q, layer)],
                                 "vias": [q]},
                        "from_mm": [mm(sx), mm(sy)], "via_mm": [mm(q[0]),
                                                                mm(q[1])]}

    plan = rt.route(starts, netcode, goal_net_copper=True, width=width,
                    ignore=list(island), margin_mm=margin_mm,
                    max_length_mm=MAX_HEAL_MM)
    if plan.get("ok"):
        return {"ok": True, "method": "maze route", "plan": plan,
                "length_mm": plan.get("length_mm")}
    return {"ok": False, "reason": plan.get("reason"),
            "island_size": len(island)}


def heal_nets(pcbnew, board, idx, netcodes, rules_obj=None, log=None,
              rounds=3):
    """Reconnect every island that is not joined to its net's main body.

    Returns (fixed, still_floating). Repeats because reconnecting one island
    can merge two others, and because laying copper changes what the next
    route may use."""
    rl = rules_obj or rules()
    fixed, left = [], []
    for _round in range(rounds):
        left = []
        floats = floating_items(pcbnew, board, idx, netcodes)
        if not floats:
            break
        progress = False
        for f in floats:
            nc = board.FindNet(f["net"]).GetNetCode()
            router = M.Router(pcbnew, board, idx, rl)
            res = reconnect_island(pcbnew, board, idx, f["items"], nc,
                                   router=router, rules_obj=rl)
            res["net"] = f["net"]
            res["island_size"] = f["size"]
            res["island"] = [describe(board, i) for i in f["items"][:4]]
            if res.get("ok"):
                commit(pcbnew, board, res, nc, rules_obj=rl)
                idx.rebuild()
                progress = True
                res.pop("plan", None)
                fixed.append(res)
            else:
                left.append(res)
        if log is not None:
            log.setdefault("heal_rounds", []).append(
                {"round": _round, "floating": len(floats),
                 "fixed": len(fixed), "left": len(left)})
        if not progress:
            break
    return fixed, left


def commit(pcbnew, board, result, net, width=None, rules_obj=None):
    """Lay the copper a connect_pad result planned. Returns the new items."""
    rl = rules_obj or rules()
    plan = result.get("plan")
    if not plan:
        return []
    return R.commit_route(pcbnew, board, plan, net,
                          int(width or rl.track_width), rl.via_dia,
                          rl.via_drill)


# --- moving copper away from a hole ------------------------------------------
def split_track_around(pcbnew, board, track, hole, reach, pad_mm=0.5,
                       min_keep_mm=0.3):
    """Cut a long track down to just the piece that is near a hole.

    L3's ESP_TXD track is 11.68 mm long and clips H4 by 76 um in the middle.
    Re-routing the whole thing would redraw eleven millimetres of working
    copper to fix a tenth of one, and hand the reviewer a diff that hides the
    actual repair. This replaces the track with up to three: the part before,
    the part near the hole, and the part after. Only the middle one is then
    detoured.

    Returns the middle track, or the original if it is near the hole
    end-to-end.
    """
    s, e = track.GetStart(), track.GetEnd()
    hx, hy, hr = hole
    dx, dy = e.x - s.x, e.y - s.y
    L2 = float(dx * dx + dy * dy)
    if L2 == 0:
        return track, []
    # where the centreline enters and leaves a circle of radius `reach`
    R2 = float(reach) ** 2
    fx, fy = s.x - hx, s.y - hy
    a = L2
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - R2
    disc = b * b - 4 * a * c
    if disc <= 0:
        return track, []
    root = math.sqrt(disc)
    t0 = (-b - root) / (2 * a)
    t1 = (-b + root) / (2 * a)
    pad = pad_mm * IU / math.sqrt(L2)
    t0 = max(0.0, t0 - pad)
    t1 = min(1.0, t1 + pad)
    length = math.sqrt(L2)
    if t0 * length < min_keep_mm * IU and (1 - t1) * length < min_keep_mm * IU:
        return track, []

    def at(t):
        return (int(s.x + dx * t), int(s.y + dy * t))

    p0, p1 = at(t0), at(t1)
    layer, width, net = track.GetLayer(), track.GetWidth(), track.GetNetCode()
    kept = []
    if t0 * length >= min_keep_mm * IU:
        kept.append(R.add_track(pcbnew, board, (s.x, s.y), p0, layer, width,
                                net))
    if (1 - t1) * length >= min_keep_mm * IU:
        kept.append(R.add_track(pcbnew, board, p1, (e.x, e.y), layer, width,
                                net))
    middle = R.add_track(pcbnew, board, p0, p1, layer, width, net)
    R.remove_items(board, [track])
    return middle, kept


def detour_track(pcbnew, board, idx, track, router=None, rules_obj=None,
                 ignore=(), max_factor=3.0, min_extra_mm=2.0):
    """Replace a track with a routed path between the same two endpoints.

    This is how L2 and L3 are done, and it is why the router was written: the
    hole is an obstacle to the router (`straight_ok` and the grid both test
    NPTH clearance), so "route from A to B" *is* "go round the hole", and the
    detour comes out of the same collision tests as everything else rather
    than out of a hand-picked waypoint.

    The track is not removed until a legal replacement exists.
    """
    rl = rules_obj or rules()
    a = (track.GetStart().x, track.GetStart().y)
    b = (track.GetEnd().x, track.GetEnd().y)
    layer = track.GetLayer()
    width = track.GetWidth()
    net = track.GetNetCode()
    direct = math.hypot(b[0] - a[0], b[1] - a[1]) / float(IU)
    limit = max(direct + min_extra_mm, direct * max_factor)
    rt = router or M.Router(pcbnew, board, idx, rl)
    ig = list(ignore) + [track]
    plan = rt.route([(a[0], a[1], layer)], net, goals=[(b[0], b[1], layer)],
                    width=width, ignore=ig, margin_mm=4.0,
                    max_length_mm=limit, max_nodes=120000)
    if not plan.get("ok"):
        return {"ok": False, "reason": plan.get("reason"),
                "track": describe(board, track), "direct_mm": round(direct, 4),
                "limit_mm": round(limit, 4)}
    R.remove_items(board, [track])
    made = R.commit_route(pcbnew, board, plan, net, width, rl.via_dia,
                          rl.via_drill)
    idx.rebuild()
    return {"ok": True, "method": "detour", "was": describe(board, track),
            "direct_mm": round(direct, 4), "length_mm": plan.get("length_mm"),
            "vias": [[mm(v[0]), mm(v[1])] for v in plan.get("vias", ())],
            "segments": len(made)}


def retreat_via(pcbnew, board, idx, via, holes, margin, rules_obj=None,
                ignore=(), max_move_mm=2.5, step_mm=0.127):
    """Slide a via clear of the holes, dragging the track ends that meet it.

    A via that sits in a mounting hole cannot simply be deleted -- it is what
    joins the two layers -- so it is moved, and every track that ended on it is
    moved with it. The move is only taken if all of those tracks still clear
    everything afterwards; a via that lands somewhere legal while stranding a
    track it was holding would trade one fault for a worse one.
    """
    rl = rules_obj or rules()
    pos = via.GetPosition()
    net = via.GetNetCode()
    attached = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA" or t.GetNetCode() != net:
            continue
        for which, p in (("start", t.GetStart()), ("end", t.GetEnd())):
            if math.hypot(p.x - pos.x, p.y - pos.y) <= via.GetWidth() / 2.0:
                attached.append((t, which))
    ig = list(ignore) + [via] + [t for t, _w in attached]

    for q in R.ring_points(pos.x, pos.y, step_mm * IU, max_move_mm * IU,
                           int(step_mm * IU)):
        ok = True
        for _name, h in holes.items():
            d = math.hypot(q[0] - h[0], q[1] - h[1])
            if d - h[2] - via.GetWidth() / 2.0 < margin:
                ok = False
                break
            if d - h[2] - via.GetDrillValue() / 2.0 < rl.hole_to_hole:
                ok = False
                break
        if not ok:
            continue
        if not R.via_site_ok(idx, pcbnew, q[0], q[1], net, via.GetWidth(),
                             via.GetDrillValue(), rl.clearance,
                             rl.hole_to_hole, rl.hole_clearance, rl.edge_box,
                             ignore=ig):
            continue
        moved_ok = True
        for t, which in attached:
            s, e = t.GetStart(), t.GetEnd()
            a2 = (q[0], q[1]) if which == "start" else (s.x, s.y)
            b2 = (e.x, e.y) if which == "start" else (q[0], q[1])
            if not R.straight_ok(idx, pcbnew, board, a2, b2, t.GetLayer(),
                                 t.GetWidth(), net, rl.clearance,
                                 rl.hole_clearance, ignore=ig):
                moved_ok = False
                break
        if not moved_ok:
            continue
        was = describe(board, via)
        via.SetPosition(pcbnew.VECTOR2I(int(q[0]), int(q[1])))
        for t, which in attached:
            if which == "start":
                t.SetStart(pcbnew.VECTOR2I(int(q[0]), int(q[1])))
            else:
                t.SetEnd(pcbnew.VECTOR2I(int(q[0]), int(q[1])))
        idx.rebuild()
        return {"ok": True, "method": "via retreat", "was": was,
                "now_mm": [mm(q[0]), mm(q[1])],
                "moved_mm": mm(math.hypot(q[0] - pos.x, q[1] - pos.y)),
                "tracks_followed": len(attached)}
    return {"ok": False, "reason": "no legal position within %.2f mm"
                                   % max_move_mm,
            "via": describe(board, via), "tracks_attached": len(attached)}


def _spread(pcbnew, item):
    """A radius that covers the item, for sizing a split window."""
    cls = item.GetClass()
    if cls == "PCB_VIA":
        return item.GetWidth() / 2.0
    if cls in ("PCB_TRACK", "PCB_ARC"):
        return item.GetWidth() / 2.0
    bb = item.GetBoundingBox()
    return math.hypot(bb.GetWidth(), bb.GetHeight()) / 2.0


def _centre(pcbnew, item, near=None):
    cls = item.GetClass()
    if cls in ("PCB_TRACK", "PCB_ARC") and near is not None:
        s, e = item.GetStart(), item.GetEnd()
        dx, dy = e.x - s.x, e.y - s.y
        L2 = float(dx * dx + dy * dy)
        u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((near[0] - s.x) * dx
                                                   + (near[1] - s.y) * dy)
                                             / L2))
        return (s.x + dx * u, s.y + dy * u)
    p = item.GetPosition()
    return (p.x, p.y)


def fix_clearance_pair(pcbnew, board, idx, pair, holes, target=None,
                       exclude=()):
    """Push two pieces of copper of different nets apart.

    A via is moved in preference to a track -- moving it costs one position
    and drags its own track ends with it, while re-routing a track rewrites a
    length of the layout. Two pads are reported, never moved: a pad only moves
    with its footprint, and that is a placement decision.
    """
    target = int(target or CLEARANCE)
    rl = rules(clearance=target)
    a, b = pair["a"], pair["b"]
    rec = {"gap_mm": mm(pair["gap"]) if pair["gap"] is not None else None,
           "target_mm": mm(target),
           "a": describe(board, a), "b": describe(board, b),
           "layer": board.GetLayerName(pair["layer"])}

    for first, second in ((a, b), (b, a)):
        if first.GetClass() != "PCB_VIA":
            continue
        res = retreat_via(pcbnew, board, idx, first, holes, HOLE_CLEARANCE,
                          rules_obj=rl, ignore=exclude)
        if res.get("ok"):
            rec.update(res)
            rec["moved"] = "via"
            return rec
        rec.setdefault("via_attempts", []).append(res.get("reason"))

    # A corner is cheaper to move than a length of track, and it is the only
    # thing that works when the pinch is at the endpoint itself.
    for first, second in ((a, b), (b, a)):
        if first.GetClass() not in ("PCB_TRACK", "PCB_ARC"):
            continue
        res = retreat_track_end(pcbnew, board, idx, first, second, target,
                                holes, exclude=exclude)
        if res.get("ok"):
            rec.update(res)
            rec["moved"] = "track end"
            return rec
        rec.setdefault("end_attempts", []).append(res.get("reason"))

    for first, second in ((a, b), (b, a)):
        if first.GetClass() not in ("PCB_TRACK", "PCB_ARC"):
            continue
        c = _centre(pcbnew, second, near=_centre(pcbnew, first))
        reach = (target + first.GetWidth() / 2.0 + _spread(pcbnew, second))
        middle, kept = split_track_around(pcbnew, board, first, (c[0], c[1], 0),
                                          reach)
        if kept:
            idx.rebuild()
        res = detour_track(pcbnew, board, idx, middle, rules_obj=rl,
                           ignore=exclude)
        if res.get("ok"):
            rec.update(res)
            rec["moved"] = "track"
            rec["split_kept_segments"] = len(kept)
            return rec
        rec.setdefault("track_attempts", []).append(res.get("reason"))

    rec["ok"] = False
    rec["reason"] = ("neither item can be moved: %s"
                     % " and ".join(sorted({a.GetClass(), b.GetClass()})))
    return rec


def shared_ends(pcbnew, board, point, netcode, tol=None):
    """Tracks with an endpoint at `point`, as [(track, "start"|"end")]."""
    tol = tol if tol is not None else int(0.001 * IU)
    out = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA" or t.GetNetCode() != netcode:
            continue
        for which, p in (("start", t.GetStart()), ("end", t.GetEnd())):
            if math.hypot(p.x - point[0], p.y - point[1]) <= tol:
                out.append((t, which))
    return out


def retreat_track_end(pcbnew, board, idx, track, other, target, holes,
                      max_move_mm=0.8, step_mm=0.0254, exclude=()):
    """Move the corner a track ends on, taking every track that meets it.

    Needed for the case a detour cannot touch: when the closest point to the
    offending item is the track's own *endpoint*, re-routing between the same
    two endpoints cannot help, because one of them is the violation. The
    ADS_RESET_N track leaving C_RST_DLY pin 1 is exactly that -- it turns west
    0.0685 mm from the capacitor's own ground pad, and every path between its
    fixed ends passes through that corner.

    Both tracks that meet at the corner move with it, and the result is
    verified against the whole board before it is kept.
    """
    rl = rules(clearance=target)
    s, e = track.GetStart(), track.GetEnd()
    oc = _centre(pcbnew, other)
    ends = [((s.x, s.y), "start"), ((e.x, e.y), "end")]
    ends.sort(key=lambda p: math.hypot(p[0][0] - oc[0], p[0][1] - oc[1]))
    point = ends[0][0]
    net = track.GetNetCode()
    group = shared_ends(pcbnew, board, point, net)
    if not group:
        return {"ok": False, "reason": "no track endpoint at the pinch"}
    ig = list(exclude) + [t for t, _w in group]

    for q in R.ring_points(point[0], point[1], step_mm * IU,
                           max_move_mm * IU, int(step_mm * IU)):
        good = True
        for t, which in group:
            ts, te = t.GetStart(), t.GetEnd()
            a2 = (q[0], q[1]) if which == "start" else (ts.x, ts.y)
            b2 = (te.x, te.y) if which == "start" else (q[0], q[1])
            if a2 == b2:
                good = False
                break
            if not R.straight_ok(idx, pcbnew, board, a2, b2, t.GetLayer(),
                                 t.GetWidth(), net, rl.clearance,
                                 rl.hole_clearance, ignore=ig):
                good = False
                break
        if not good:
            continue
        was = [describe(board, t) for t, _w in group]
        for t, which in group:
            if which == "start":
                t.SetStart(pcbnew.VECTOR2I(int(q[0]), int(q[1])))
            else:
                t.SetEnd(pcbnew.VECTOR2I(int(q[0]), int(q[1])))
        idx.rebuild()
        return {"ok": True, "method": "track end retreat",
                "from_mm": [mm(point[0]), mm(point[1])],
                "to_mm": [mm(q[0]), mm(q[1])],
                "moved_mm": mm(math.hypot(q[0] - point[0], q[1] - point[1])),
                "tracks_moved": len(group), "was": was}
    return {"ok": False,
            "reason": "no position for the corner within %.2f mm" % max_move_mm}


def clear_hole(pcbnew, board, idx, name, hole, margin, nets=None,
               rules_obj=None, log=None, skip_pads=True, exclude=()):
    """Get every piece of copper out of one hole's clearance ring.

    Vias are retreated, tracks are re-routed between their own endpoints, and
    pads are reported -- a pad only moves with its footprint, which is a
    placement decision and belongs to a named repair (L1), not to a sweep.
    """
    rl = rules_obj or rules()
    skip = {R.uid(i) for i in exclude}
    results = []
    for _round in range(4):
        bad = [(g, it) for g, it in copper_near_hole(pcbnew, board, hole,
                                                     margin,
                                                     include_pads=not skip_pads)
               if R.uid(it) not in skip]
        if nets is not None:
            bad = [(g, it) for g, it in bad if it.GetNetname() in nets]
        bad = [(g, it) for g, it in bad
               if not any(r.get("uid") == R.uid(it) and r.get("ok")
                          for r in results)]
        if not bad:
            break
        progress = False
        for g, it in bad:
            cls = it.GetClass()
            item_uid = R.uid(it)          # before any edit can remove it
            if cls == "PAD":
                results.append({"ok": False, "kind": "pad",
                                "reason": "a pad only moves with its "
                                          "footprint",
                                "gap_mm": mm(g), "uid": item_uid,
                                "item": describe(board, it)})
                continue
            # Try for the target margin, then settle for less, never below the
            # rule. A via wedged between the USB-C peg and the ESP32 UART pair
            # has room for 0.22 mm and not for 0.30, and refusing the 0.22 mm
            # answer would leave a real violation standing.
            ladder = [m for m in HOLE_MARGIN_STEPS if m <= margin] or [margin]
            res = None
            for attempt in ladder:
                if g >= attempt:
                    # Already clear at this rung, so the ones below it are met
                    # too. Without this the sweep spends a router run per rung
                    # moving copper that was never in the way.
                    res = {"ok": True, "method": "already clear at %.2f mm"
                                                 % mm(attempt),
                           "item": describe(board, it)}
                    res["margin_mm"] = mm(attempt)
                    break
                rl_m = rules(hole_clearance=attempt)
                if cls == "PCB_VIA":
                    res = retreat_via(pcbnew, board, idx, it, {name: hole},
                                      attempt, rules_obj=rl_m, ignore=exclude)
                else:
                    reach = hole[2] + attempt + it.GetWidth() / 2.0
                    target, kept = split_track_around(pcbnew, board, it, hole,
                                                      reach)
                    if kept:
                        idx.rebuild()
                    router = M.Router(pcbnew, board, idx, rl_m)
                    res = detour_track(pcbnew, board, idx, target,
                                       router=router, rules_obj=rl_m,
                                       ignore=exclude)
                    res["split_kept_segments"] = len(kept)
                    if not res.get("ok") and kept:
                        # the split stands even when the detour fails; the next
                        # margin works on the shorter middle piece
                        it = target
                res["margin_mm"] = mm(attempt)
                if res.get("ok"):
                    break
            res["gap_before_mm"] = mm(g)
            res["uid"] = item_uid
            res["hole"] = name
            results.append(res)
            if res.get("ok"):
                progress = True
        if not progress:
            break
    if log is not None:
        log.setdefault("clear_hole", {})[name] = results
    return results


# --- finding violations ourselves --------------------------------------------
def _actual_gap(sh_a, sh_b, ceiling, steps=9):
    """How far apart two shapes are, by bisection on Collide.

    SHAPE::Collide's out-parameter for the actual distance is not exposed
    through SWIG, and the value is wanted only for the report, so a handful of
    boolean tests is enough: nine of them pin a 0.2 mm ceiling to 0.4 um.
    """
    lo, hi = 0, int(ceiling)
    if not sh_a.Collide(sh_b, hi):
        return None
    for _ in range(steps):
        mid = (lo + hi) // 2
        if sh_a.Collide(sh_b, mid):
            hi = mid
        else:
            lo = mid
    return hi


def clearance_pairs(pcbnew, board, idx, clearance):
    """Every pair of different-net copper closer than `clearance`.

    Found from the geometry rather than read out of the DRC report, for two
    reasons. The report names items by KIID, and until 26_fix_uuids has run
    those are not unique, so the names can be wrong. And the report gives an
    item's own anchor, which for a long track is nowhere near the violation,
    while a repair needs the place where the two actually come close.

    Zones are excluded: they are refilled after every edit and pull back around
    whatever is placed, exactly as in lib/route's index.
    """
    out, seen = [], set()
    items = idx.tracks + idx.pads
    for item in items:
        net = item.GetNetCode()
        for layer in R.item_layers(pcbnew, item):
            try:
                sh = item.GetEffectiveShape(layer)
            except Exception:
                continue
            bb = sh.BBox(int(clearance))
            for other, onet, osh in idx._query(layer, bb.GetLeft(), bb.GetTop(),
                                               bb.GetRight(), bb.GetBottom()):
                if onet == net and net != 0:
                    continue
                ka, kb = R.uid(item), R.uid(other)
                if ka == kb:
                    continue
                key = (min(ka, kb), max(ka, kb))
                if key in seen:
                    continue
                seen.add(key)
                if not sh.Collide(osh, int(clearance)):
                    continue
                out.append({"gap": _actual_gap(sh, osh, clearance),
                            "a": item, "b": other, "layer": layer})
    out.sort(key=lambda r: (r["gap"] if r["gap"] is not None else 0))
    return out


def hole_pairs(pcbnew, board, idx, hole_to_hole):
    """Every pair of drilled holes whose edges come within `hole_to_hole`."""
    out, seen = [], set()
    for i, (a, ax, ay, ar, _an) in enumerate(idx.drills):
        for (b, bx, by, br, _bn) in idx.drills[i + 1:]:
            ka, kb = R.uid(a), R.uid(b)
            key = (min(ka, kb), max(ka, kb))
            if key in seen:
                continue
            seen.add(key)
            gap = math.hypot(ax - bx, ay - by) - ar - br
            if gap < hole_to_hole:
                out.append({"gap": gap, "a": a, "b": b})
    out.sort(key=lambda r: r["gap"])
    return out


# --- contract parity ---------------------------------------------------------
def pad_net_map(board, pcbnew):
    """designator -> pad number -> set of nets, plus the mechanical references.

    Mechanical means H1-H4 and PEG1/PEG2: no net, no BOM line, nothing the
    contract knows about. A DNP part is excluded from the BOM too but is still
    a real component with real pads on real nets, so it stays in the map and
    the contract still has to match it -- ECO B1/B4 leave the footprint, the
    copper and the netlist alone and only stop the part being fitted.
    """
    import collections
    out = collections.defaultdict(lambda: collections.defaultdict(set))
    mech = set()
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref:
            continue
        if (int(fp.GetAttributes()) & int(pcbnew.FP_EXCLUDE_FROM_BOM)
                and not fp.IsDNP()):
            mech.add(ref)
            continue
        for p in fp.Pads():
            out[ref][p.GetNumber()].add(p.GetNetname())
    return out, mech


def load_overrides(root=None):
    """contract/contract_overrides.json as {(designator, pad): net}.

    The overrides are the differences the board is meant to carry ahead of the
    schematic -- ECO-5 so far. Parity is checked against the contract with
    these applied, so an override is a decision recorded once rather than an
    exception each caller has to remember.
    """
    path = os.path.join(root or ROOT, "contract", "contract_overrides.json")
    if not os.path.exists(path):
        return {}
    doc = E.load_json(path)
    return {(o["designator"], str(o["pad"])): o["override_net"]
            for o in doc.get("overrides", ())}


def contract_net_counts(root=None, apply_overrides=True):
    """net name -> how many contract pins sit on it, overrides applied.

    Counts pins, not pads: the ESP32 thermal pad is nine physical pads sharing
    one number, so the board's pad tally for GND runs eight ahead of this.
    """
    import collections
    contract = E.load_json(os.path.join(root or ROOT, "contract",
                                        "netlist_contract.json"))
    over = load_overrides(root) if apply_overrides else {}
    cnt = collections.Counter()
    for ref, pads in contract["by_designator"].items():
        for num, info in pads.items():
            net = over.get((ref, num), info.get("net", ""))
            if net and net != "NC":
                cnt[net] += 1
    return cnt


def contract_diff(board, pcbnew, root=None, apply_overrides=True):
    """Differences between the board's pad->net map and the contract."""
    contract = E.load_json(os.path.join(root or ROOT, "contract",
                                        "netlist_contract.json"))
    have, mech = pad_net_map(board, pcbnew)
    want = contract["by_designator"]
    if apply_overrides:
        import copy
        want = copy.deepcopy(want)
        for (ref, num), net in load_overrides(root).items():
            if ref in want and num in want[ref]:
                want[ref][num] = dict(want[ref][num], net=net)
    diffs = []
    for ref in sorted(set(want) | set(have)):
        if ref not in want:
            diffs.append({"ref": ref, "issue": "on the board, not in the "
                                               "contract"})
            continue
        if ref not in have:
            diffs.append({"ref": ref, "issue": "in the contract, not on the "
                                               "board"})
            continue
        for num in sorted(set(want[ref]) | set(have[ref])):
            wnet = (want[ref].get(num) or {}).get("net", "")
            if wnet == "NC":
                wnet = ""
            hnets = have[ref].get(num)
            if hnets is None:
                diffs.append({"ref": ref, "pad": num, "want": wnet,
                              "have": None, "issue": "pad missing"})
                continue
            if hnets != {wnet}:
                diffs.append({"ref": ref, "pad": num, "want": wnet,
                              "have": sorted(hnets), "issue": "net mismatch"})
    return diffs, sorted(mech)


def counts(board, pcbnew):
    npth = 0
    pth = 0
    for f in board.GetFootprints():
        for p in f.Pads():
            a = int(p.GetAttribute())
            if a == int(pcbnew.PAD_ATTRIB_NPTH):
                npth += 1
            elif a == int(pcbnew.PAD_ATTRIB_PTH):
                pth += 1
    return {
        "footprints": len(list(board.GetFootprints())),
        "tracks": sum(1 for t in board.GetTracks()
                      if t.GetClass() != "PCB_VIA"),
        "vias": sum(1 for t in board.GetTracks() if t.GetClass() == "PCB_VIA"),
        "npth_pads": npth,
        "pth_pads": pth,
    }


# --- DRC ---------------------------------------------------------------------
def kicad_cli():
    return os.environ.get(
        "KC", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")


def run_drc(out_path, root=None, refill=True, board=None):
    """kicad-cli pcb drc. Must run outside the command sandbox (see README)."""
    cmd = [kicad_cli(), "pcb", "drc", "--format", "json", "--severity-all",
           "--units", "mm"]
    if refill:
        cmd += ["--refill-zones", "--save-board"]
    cmd += ["-o", out_path, board or board_path(root)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    blob = (proc.stdout or "") + (proc.stderr or "")
    ok = os.path.exists(out_path) and "Fatal error" not in blob
    return ok, proc, blob


def load_drc(path):
    with open(path) as f:
        return json.load(f)


def load_baseline(root, name):
    """The DRC report a step compares itself against, or None.

    Each repair names the report of the step before it, so a run in a different
    order -- or a first run of one step on its own -- would otherwise die on a
    missing file. Falling back to the pre-repair baseline keeps the regression
    check meaningful; dropping it entirely only loses the comparison, and the
    step's own before/after measurements still stand.
    """
    for candidate in (name, "drc_S5_before", "drc_after_eco"):
        p = os.path.join(root or ROOT, "logs", candidate + ".json")
        if os.path.exists(p):
            return load_drc(p)
    return None


def unconnected_count(pcbnew, board):
    """KiCad's own answer, in-process. Matches DRC's unconnected_items count.

    `net_components` above is a locator, not an oracle -- it was measured
    calling VDD_ESP whole while DRC drew a ratsnest line across it. This is the
    connectivity engine itself, so it is what the repairs check before saving.
    """
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    conn.RecalculateRatsnest()
    return conn.GetUnconnectedCount(True)


def kicad_python():
    return os.environ.get(
        "KPY", "/Applications/KiCad/KiCad.app/Contents/Frameworks/"
               "Python.framework/Versions/Current/bin/python3")


def drc_with_healing(root, tag, rounds=2, log=None):
    """DRC, then route back anything it says is unconnected, then DRC again.

    Returns (ok, doc, path). The healing runs as a subprocess because pcbnew
    refuses a second LoadBoard in the process that saved the board.
    """
    root = root or ROOT
    path = os.path.join(root, "logs", "drc_%s.json" % tag)
    ok, _proc, blob = run_drc(path, root)
    if not ok:
        if log is not None:
            log["drc_error"] = blob[-400:]
        return False, None, path
    doc = load_drc(path)
    for r in range(rounds):
        if not doc.get("unconnected_items"):
            break
        script = os.path.join(root, "scripts", "39_fix_unconnected.py")
        proc = subprocess.run([kicad_python(), script, "--root", root,
                               "--drc", path], capture_output=True, text=True)
        try:
            heal = json.loads(proc.stdout)
        except ValueError:
            heal = {"stdout": proc.stdout[-400:],
                    "stderr": proc.stderr[-400:]}
        if log is not None:
            log.setdefault("unconnected_healing", []).append(heal)
        if not heal.get("fixed"):
            break
        ok, _proc, blob = run_drc(path, root)
        if not ok:
            if log is not None:
                log["drc_error"] = blob[-400:]
            return False, doc, path
        doc = load_drc(path)
    return True, doc, path


def error_keys(doc):
    return {V.key(v) for v in V.errors(doc)}


def drc_delta(before_doc, after_doc):
    """What the edit did to the error set, located rather than signature-level.

    lib/drc.compare answers the gate question ("did anything regress") on
    signatures, which are immune to DRC's jitter but cannot say which
    violation. This says which -- and jitter can make a fixed violation
    reappear at a neighbouring coordinate, so the caller checks both.
    """
    b, a = error_keys(before_doc), error_keys(after_doc)
    return {
        "resolved": sorted(V.key_text(k) for k in b - a),
        "new": sorted(V.key_text(k) for k in a - b),
        "before": len(b),
        "after": len(a),
    }


def by_type(doc, severity="error"):
    import collections
    return dict(collections.Counter(
        v.get("type") for v in doc.get("violations", [])
        if not severity or v.get("severity") == severity).most_common())


def unconnected(doc):
    return len(doc.get("unconnected_items", []))


def run_hole_step(step, hole_names, nets, notes, root=None, skip_drc=False,
                  baseline="drc_S5_before", margin=None, before_save=None,
                  after_clear=None, extra_checks=None):
    """The whole of an L2/L3/L4-shaped repair: clear holes, heal, gate.

    L2 and L3 differ from each other only in which hole and which net, and L4
    adds one footprint edit, so the body of the step lives here and the scripts
    stay a docstring, a net list and a hook.

    `after_clear(ctx)` runs with the board open after the copper has been
    moved; `before_save(ctx)` just before it is written. Both get a dict with
    pcbnew, board, idx, log and the rules.
    """
    import pcbnew
    root = root or ROOT
    rl = rules()
    margin = TARGET_HOLE_MARGIN if margin is None else margin
    bpath = board_path(root)
    board = pcbnew.LoadBoard(bpath)
    idx = R.CopperIndex(pcbnew, board)
    holes = npth_holes(pcbnew, board)
    log = {"step": step, "holes": hole_names, "nets": sorted(nets or [])}
    ctx = {"pcbnew": pcbnew, "board": board, "idx": idx, "log": log,
           "rules": rl, "holes": holes, "root": root}

    before = {}
    for name in hole_names:
        before[name] = [dict(describe(board, it), gap_mm=mm(g))
                        for g, it in copper_near_hole(pcbnew, board,
                                                      holes[name],
                                                      HOLE_CLEARANCE)
                        if nets is None or it.GetNetname() in nets]
    log["violating_before"] = before

    for name in hole_names:
        clear_hole(pcbnew, board, idx, name, holes[name], margin, nets=nets,
                   rules_obj=rl, log=log)
    if after_clear:
        after_clear(ctx)

    netcodes = sorted({board.FindNet(n).GetNetCode() for n in (nets or [])
                       if board.FindNet(n) is not None})
    healed, floating = heal_nets(pcbnew, board, idx, netcodes, log=log)
    log["islands_reconnected"] = healed
    log["islands_still_floating"] = floating

    after, after_all = {}, {}
    for name in hole_names:
        rows = [dict(describe(board, it), gap_mm=mm(g))
                for g, it in copper_near_hole(pcbnew, board, holes[name],
                                              HOLE_CLEARANCE)]
        after_all[name] = rows
        after[name] = [r for r in rows
                       if nets is None or r.get("net") in nets]
    log["violating_after"] = after
    # Everything still inside the ring, whatever its net -- the step gates on
    # the nets it was asked to move, but a reader needs to see the rest.
    log["inside_ring_after_any_net"] = after_all

    if before_save:
        before_save(ctx)
    board.BuildListOfNets()
    diffs, _mech = contract_diff(board, pcbnew, root)
    log["contract_diffs"] = diffs[:20]
    log["counts_after"] = counts(board, pcbnew)
    log["unconnected_before_save"] = unconnected_count(pcbnew, board)
    pcbnew.SaveBoard(bpath, board)

    drc_ok, cur, _p = (False, None, None)
    delta, sig = {}, {}
    if not skip_drc:
        drc_ok, cur, _p = drc_with_healing(root, step.lower(), log=log)
        if drc_ok:
            base = load_baseline(root, baseline)
            if base is not None:
                delta = drc_delta(base, cur)
                sig = D.compare(base, cur)
                log["drc_delta"] = delta
            log["drc_after"] = {"errors_by_type": by_type(cur),
                                "unconnected": unconnected(cur)}

    left = sum(len(v) for v in after.values())
    checks = [
        check("target_copper_cleared", 0, left),
        check("no_floating_islands", 0, len(floating)),
        check("contract_parity", 0, len(diffs)),
        check("drc_ran", True, drc_ok),
        check("unconnected", 0, unconnected(cur) if cur else -1,
              ok=(drc_ok and unconnected(cur) == 0)),
        check("no_new_drc_signatures", [],
              sig.get("new_signatures", ["drc did not run"]),
              ok=(drc_ok and not sig.get("new_signatures"))),
    ]
    if extra_checks:
        checks += extra_checks(log)
    gate(root, step, checks, notes=notes, extra=log)
    return all(c["pass"] for c in checks), log


def gate(root, name, checks, notes="", extra=None):
    return E.write_gate(os.path.join(root or ROOT, "gates", name + ".json"),
                        name, checks, notes=notes, extra=extra)


def check(name, expected, actual, ok=None, note=None):
    return E.gate_check(name, expected, actual, ok=ok, note=note)
