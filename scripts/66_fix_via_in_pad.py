#!/usr/bin/env python3
"""S7v -- take every via out of the SMD pads it was sitting in.

    KPY scripts/66_fix_via_in_pad.py [--root DIR] [--dry-run]

Why
---
The board as imported from EasyEDA carried a via at (or near) the centre of
~100 SMD pads -- 0402 decoupling caps, the sixteen 0603 CM caps on the ADC
inputs, one TQFP-64 pin of the ADS1299, ESP32 lands. On the order this board
is built to (4 layers, Via Covering = Tented, product.yaml fab.via.covering:
none) nothing plugs those barrels, so in reflow the paste printed on the pad
runs down the 0.305 mm hole and the joint starves: opens, and tombstones on
the 0402s whose pad is narrower than the via itself. None of A-H looked, so
the board went to the cart with them (harness open question Q460). ECO-5 had
already moved one such via out by hand for exactly this reason
(STATUS.md, "0402 のパッド下 via はリフローではんだを吸う"); this does the rest.

What it does, per via
---------------------
A via is an offender when its drill comes within J_MARGIN (0.10 mm, JLC's
guidance; the harness places at 0.03) of any SMD pad's solder-mask opening. The opening
is the pad's bounding box grown by its mask expansion -- the same conservative
rectangle the harness census uses, so a via this script leaves alone is one
the census leaves alone too.

Each offender is moved to the cheapest legal site nearby and tied back in:

* along a track it already carries (the dogbone falls out of the existing
  route: on B.Cu the track is shortened to the new site, on F.Cu it is split
  there, so no copper is added);
* otherwise anywhere on rings round the old site, with a new stub from the old
  site (inside the pad) to the via on F.Cu, and on any other layer that had a
  track ending at the via.

A site is legal when the via clears every other net by the clearance of the
tier, holes by 0.2 mm, NPTH by 0.2 mm, the board edge by 0.2 mm, every pad's
mask opening (SMD and PTH, both sides) by the tier's drill margin, and every
new track clears every other net. A via that fed an inner plane only through
the plane must land inside that same plane's fill again. Tiers are tried in
order and the first tier with any legal site wins, cheapest site first:

    1  clearance 0.127, drill >= 0.10 from any opening, ring outside it
    2  clearance 0.127, drill >= 0.10 from any opening
    (tiers 3 and 4, at 0.100 and 0.0889 mm, were removed 2026-09-23: new
    copper keeps 0.127 mm to other nets)

Nothing here is a DRC substitute. The board is saved, and run.sh's next
steps refill the zones and DRC it; this script also asks KiCad's connectivity
engine for the unconnected count before saving and refuses to save a board
that lost a connection.

Writes logs/viapad_fix.json (every item removed and laid, with net and
coordinates -- S7b reads it to attribute its differences) and gates/S7v.json.
"""

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import route as R                                  # noqa: E402
import epro as E                                   # noqa: E402

IU = R.IU
# The drill must stay this far from any SMD mask opening. The harness places
# at 0.03 mm (core.viapad.J_MARGIN_MM); JLC's guidance is 0.1 mm between a
# via's drill and a pad opening, and ACCEPTANCE I holds that (QA MINOR-1,
# 2026-09-23: 20 vias between 0.0327 and 0.1 mm at 0.03).
J_MARGIN = 0.10 * IU
# A site this close to a track's centre line is taken as on it: the track is
# split (or shortened) there and bends by at most this much, which is checked
# like any new copper. 0.05 mm lets the via sit just off a track that runs
# along the edge of a pad opening (the IN*N runs past C_DIF, 0.0125 mm short
# of 0.1 mm from its opening) without adding copper to the signal path.
ON_TRACK_TOL = int(0.05 * IU) + 1000
EXACT_TOL = 2000

TIERS = [
    # (name, clearance, drill margin to any opening,
    #  ring must clear other nets' openings, penalty added to the cost)
    ("1", int(0.127 * IU), int(0.10 * IU), True, 0),
    ("2", int(0.127 * IU), int(0.10 * IU), False, int(0.25 * IU)),
]
# Every tier keeps the board's recommended 0.127 mm (5 mil) to other nets.
# Tiers at 0.100 and at the 0.0889 rule used to exist; QA found the copper
# they placed 0.092 mm from its neighbours (2026-09-23), so new copper is
# held to the recommendation, not the floor.
NEW_COPPER_CLEARANCE = int(0.127 * IU)
# From 0.025 mm: a via that sits just outside its pad's opening (C_VCAP3.1,
# 0.0555 mm) only has to step 0.045 mm to clear 0.10.
RADII = [int(r * IU) for r in [0.025 + 0.025 * i for i in range(0, 80)]]
ANGLES = [math.radians(a) for a in range(0, 360, 12)]
POWER_W = [int(0.3048 * IU), int(0.254 * IU), int(0.2032 * IU)]
SIGNAL_W = [int(0.2032 * IU), int(0.1524 * IU)]


def power_nets(root):
    """product.yaml nets.power_nets -- which stubs get power width."""
    out, on = set(), False
    for line in open(os.path.join(root, "product.yaml")):
        s = line.rstrip()
        if s.strip() == "power_nets:":
            on = True
            continue
        if on:
            if s.strip().startswith("- "):
                out.add(s.strip()[2:].strip())
            else:
                break
    return out


# --- geometry ----------------------------------------------------------------
def seg_dist(ax, ay, bx, by, px, py):
    return P.seg_point_distance(ax, ay, bx, by, px, py)


def rect_gap(box, x, y, r):
    """Edge-to-edge gap from a circle to an axis-aligned box (negative inside)."""
    l, t, rt, b = box
    dx = max(l - x, 0, x - rt)
    dy = max(t - y, 0, y - b)
    if dx == 0 and dy == 0:
        return -min(x - l, rt - x, y - t, b - y) - r
    return math.hypot(dx, dy) - r


class GraphicOpening(object):
    """A paste or mask shape drawn in a footprint rather than a pad.

    The EasyEDA import carried its own F.Paste polygons on 50 footprints
    (every 0805 and the ADC and USB-C lands); they are plotted as stencil
    openings next to the pads' own, and R_BIAS_SER's reaches 0.134 mm past its
    pad. A via has to keep clear of those too."""

    def __init__(self, fp, net):
        self.ref, self.net = fp.GetReference(), net

    def GetNetCode(self):
        return self.net

    def GetParentFootprint(self):
        return None

    def GetNumber(self):
        return "paste"


def mask_openings(pcbnew, board):
    """(box, is_smd, pad) for every pad that opens the mask on either side,
    and every paste/mask shape a footprint draws for itself."""
    out = []
    for fp in board.GetFootprints():
        for g in fp.GraphicalItems():
            if g.GetLayer() not in (pcbnew.F_Paste, pcbnew.F_Mask,
                                    pcbnew.B_Mask, pcbnew.B_Paste):
                continue
            bb = g.GetBoundingBox()
            c = bb.GetCenter()
            net = 0
            for p in fp.Pads():
                if p.GetEffectiveShape(pcbnew.F_Cu).Collide(c, 0):
                    net = p.GetNetCode()
            out.append(((bb.GetLeft(), bb.GetTop(), bb.GetRight(),
                         bb.GetBottom()), True, GraphicOpening(fp, net)))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            smd = int(p.GetAttribute()) == int(pcbnew.PAD_ATTRIB_SMD)
            for ml in (pcbnew.F_Mask, pcbnew.B_Mask):
                if not p.IsOnLayer(ml):
                    continue
                cu = pcbnew.F_Cu if ml == pcbnew.F_Mask else pcbnew.B_Cu
                try:
                    exp = p.GetSolderMaskExpansion(cu)
                except Exception:
                    exp = int(0.0508 * IU)
                bb = p.GetBoundingBox()
                out.append(((bb.GetLeft() - exp, bb.GetTop() - exp,
                             bb.GetRight() + exp, bb.GetBottom() + exp),
                            smd, p))
                break
    return out


def offenders(pcbnew, board, openings):
    rows = []
    for v in board.GetTracks():
        if v.GetClass() != "PCB_VIA":
            continue
        p = v.GetPosition()
        r = v.GetDrillValue() / 2.0
        worst = None
        for box, smd, pad in openings:
            if not smd:
                continue
            g = rect_gap(box, p.x, p.y, r)
            if g < J_MARGIN and (worst is None or g < worst[0]):
                worst = (g, pad)
        if worst:
            rows.append((v, worst[1], worst[0]))
    return rows


def pad_name(pad):
    if isinstance(pad, GraphicOpening):
        return "%s.paste" % pad.ref
    fp = pad.GetParentFootprint()
    return "%s.%s" % (fp.GetReference() if fp else "?", pad.GetNumber())


# --- one via -----------------------------------------------------------------
class Site(object):
    def __init__(self, q, tier, clearance, cost, ops, width):
        self.q, self.tier, self.clearance = q, tier, clearance
        self.cost, self.ops, self.width = cost, ops, width


def attached(pcbnew, board, via):
    """Tracks with an endpoint on the via, by layer: {layer: [(t, end)]}."""
    p = via.GetPosition()
    r = via.GetWidth(pcbnew.F_Cu) / 2.0
    out = {}
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA" or t.GetNetCode() != via.GetNetCode():
            continue
        for which, e in (("start", t.GetStart()), ("end", t.GetEnd())):
            if math.hypot(e.x - p.x, e.y - p.y) <= r:
                out.setdefault(t.GetLayer(), []).append((t, which))
    return out


def host_pads(pcbnew, board, via):
    p = via.GetPosition()
    out = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() != via.GetNetCode() \
                    or not pad.IsOnLayer(pcbnew.F_Cu):
                continue
            # the via's ring touching the pad is a connection, not only its
            # centre sitting in it
            if pad.GetEffectiveShape(pcbnew.F_Cu).Collide(
                    pcbnew.VECTOR2I(p.x, p.y),
                    int(via.GetWidth(pcbnew.F_Cu) / 2)):
                out.append(pad)
    return out


def stub_start(pcbnew, via, host):
    """The old site when it is inside a host pad, else the nearest pad centre."""
    p = via.GetPosition()
    for h in host:
        if h.GetEffectiveShape(pcbnew.F_Cu).Collide(
                pcbnew.VECTOR2I(p.x, p.y), 0):
            return (p.x, p.y)
    h = min(host, key=lambda h: (h.GetPosition() - p).EuclideanNorm())
    return (h.GetPosition().x, h.GetPosition().y)


PLANE_MIN_MM2 = 2.0             # a fill island smaller than this is the via's own


def fill_island_mm2(pcbnew, zone, layer, x, y):
    """Area of the filled polygon of `zone` on `layer` that contains (x, y)."""
    polys = zone.GetFilledPolysList(layer)
    pt = pcbnew.VECTOR2I(int(x), int(y))
    for i in range(polys.OutlineCount()):
        if not (polys.Outline(i).PointInside(pt)
                or polys.Outline(i).PointOnEdge(pt)):
            continue
        if any(polys.Hole(i, h).PointInside(pt)
               for h in range(polys.HoleCount(i))):
            continue
        if True:
            one = pcbnew.SHAPE_POLY_SET()
            one.AddOutline(polys.Outline(i))
            for h in range(polys.HoleCount(i)):
                one.AddHole(polys.Hole(i, h))
            return one.Area() / float(IU) ** 2
    return 0.0


def plane_layers(pcbnew, board, via, att):
    """Inner layers where the via reaches its net through a real plane.

    A via always sits in a fill island of its own net if the zone's outline
    covers it -- under the ADC the In2 AVSS zone yields one 0.5 mm blob per
    AVSS via inside the AVDD pour. Such a blob connects the via to nothing,
    so only an island larger than PLANE_MIN_MM2 counts as a plane."""
    p = via.GetPosition()
    out = []
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetCode() != via.GetNetCode():
            continue
        for layer in z.GetLayerSet().CuStack():
            if layer in att or layer in out:
                continue
            if fill_island_mm2(pcbnew, z, layer, p.x, p.y) >= PLANE_MIN_MM2:
                out.append(layer)
    return out


def functionless(pcbnew, board, via, att, planes):
    """A via that reaches nothing but F.Cu: no track on another layer and no
    plane. Moving it would only move a dead end; it is removed instead."""
    return not planes and all(l == pcbnew.F_Cu for l in att)


def in_plane(pcbnew, board, netcode, layer, x, y):
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetCode() != netcode:
            continue
        if z.GetLayerSet().Contains(layer) and fill_island_mm2(
                pcbnew, z, layer, x, y) >= PLANE_MIN_MM2:
            return True
    return False


def candidates(pcbnew, via, att):
    p = via.GetPosition()
    pts = []
    for layer, ends in att.items():
        for t, which in ends:
            s, e = t.GetStart(), t.GetEnd()
            far = e if which == "start" else s
            L = math.hypot(far.x - p.x, far.y - p.y)
            if L <= 0:
                continue
            ux, uy = (far.x - p.x) / L, (far.y - p.y) / L
            for d in RADII:
                if d >= L - int(0.05 * IU):
                    break
                for off in (0, 25000, -25000, 50000, -50000):
                    pts.append((int(round(p.x + ux * d - uy * off)),
                                int(round(p.y + uy * d + ux * off))))
    for d in RADII:
        for a in ANGLES:
            pts.append((int(round(p.x + d * math.cos(a))),
                        int(round(p.y + d * math.sin(a)))))
    return pts


def site_ok(pcbnew, board, idx, via, planes, openings, q, tier, edge):
    """Can `via` itself stand at q under `tier`? (Its tie-in is separate.)"""
    _name, clr, drill_margin, ring_clear, _pen = tier
    qx, qy = q
    net = via.GetNetCode()
    vr = via.GetWidth(pcbnew.F_Cu) / 2.0
    dr = via.GetDrillValue() / 2.0
    lo_x, lo_y, hi_x, hi_y = edge
    if not (lo_x + vr <= qx <= hi_x - vr and lo_y + vr <= qy <= hi_y - vr):
        return False
    for box, _smd, pad in openings:
        if rect_gap(box, qx, qy, dr) < drill_margin:
            return False
        # a ring in a same-net opening only widens that pad; in another
        # net's opening it is exposed copper beside someone else's joint
        if ring_clear and pad.GetNetCode() != net \
                and rect_gap(box, qx, qy, vr) < 0:
            return False
    if idx.hole_conflicts(qx, qy, dr, P.HOLE_TO_HOLE, ignore=[via]):
        return False
    if idx.npth_conflicts(qx, qy, vr, P.HOLE_CLEARANCE, ignore=[via]):
        return False
    for layer in R.copper_layers(pcbnew, board):
        if idx.point_conflicts(qx, qy, layer, vr, clr, net, ignore=[via]):
            return False
    for layer in planes:
        if not in_plane(pcbnew, board, net, layer, qx, qy):
            return False
    return True


def plan_site(pcbnew, board, idx, via, att, host, planes, openings, q, tier,
              widths, edge):
    """The ops that put `via` at q, or None when q is not legal for `tier`."""
    name, clr, _dm, _rc, _pen = tier
    if not site_ok(pcbnew, board, idx, via, planes, openings, q, tier, edge):
        return None
    p = via.GetPosition()
    qx, qy = q
    net = via.GetNetCode()

    ops = []          # ("split"|"shorten", track, which) | ("add", a, b, layer, w)
    added = 0.0

    def inside_host(pt):
        v = pcbnew.VECTOR2I(int(pt[0]), int(pt[1]))
        return any(h.GetEffectiveShape(pcbnew.F_Cu).Collide(v, 0)
                   for h in host)

    def widest_clear(a, b, layer, choices):
        for w in choices:
            if check_track(pcbnew, board, idx, a, b, layer, w, net, clr, via):
                return w
        return None

    stub_w = None
    for layer, ends in att.items():
        on = [(t, w) for t, w in ends
              if seg_dist(t.GetStart().x, t.GetStart().y, t.GetEnd().x,
                          t.GetEnd().y, qx, qy) <= ON_TRACK_TOL]
        # The ring was what joined ends that stop short of its centre; with
        # the via gone they are brought to the centre, where they meet.
        # (On F.Cu an end inside the pad is joined by the pad.)
        for t, w in ends:
            e = t.GetStart() if w == "start" else t.GetEnd()
            if math.hypot(e.x - p.x, e.y - p.y) <= 1000:
                continue
            if layer == pcbnew.F_Cu and inside_host((e.x, e.y)):
                continue
            if on and t is on[0][0] and len(ends) == 1:
                continue
            if any(o[0] == "add" and o[1] == (e.x, e.y) and o[3] == layer
                   for o in ops):
                continue                # three tracks ending on one point
            ops.append(("add", (e.x, e.y), (p.x, p.y), layer, t.GetWidth()))
            added += math.hypot(p.x - e.x, p.y - e.y)
        if on:
            t0 = on[0][0]
            if seg_dist(t0.GetStart().x, t0.GetStart().y, t0.GetEnd().x,
                        t0.GetEnd().y, qx, qy) > EXACT_TOL:
                # the track bends to reach the site: both halves are new
                for end in (t0.GetStart(), t0.GetEnd()):
                    if not check_track(pcbnew, board, idx, (end.x, end.y),
                                       (qx, qy), layer, t0.GetWidth(), net,
                                       clr, via):
                        return None
        if on and len(ends) == 1 and layer != pcbnew.F_Cu:
            ops.append(("shorten", on[0][0], on[0][1]))
        elif on:
            ops.append(("split", on[0][0], on[0][1]))
        else:
            if layer == pcbnew.F_Cu:
                w = widest_clear((p.x, p.y), (qx, qy), layer, widths)
                if w is None:
                    return None
                stub_w = w
            else:
                w = max(t.GetWidth() for t, _ in ends)
            ops.append(("add", (p.x, p.y), (qx, qy), layer, w))
            added += math.hypot(qx - p.x, qy - p.y)
    for op in ops:
        if op[0] == "add" and not check_track(pcbnew, board, idx, op[1],
                                              op[2], op[3], op[4], net, clr,
                                              via):
            return None
    # the host pad itself: joined at the old centre if that lies in it, or
    # through an F.Cu track that touches it; otherwise a stub of its own
    linked = inside_host((p.x, p.y)) or any(
        any(h.GetEffectiveShape(pcbnew.F_Cu).Collide(
            t.GetEffectiveShape(pcbnew.F_Cu), 0) for h in host)
        for t, _w in att.get(pcbnew.F_Cu, ()))
    if host and (not linked or pcbnew.F_Cu not in att):
        a = stub_start(pcbnew, via, host)
        w = widest_clear(a, (qx, qy), pcbnew.F_Cu, widths)
        if w is None:
            return None
        stub_w = w
        ops.append(("add", a, (qx, qy), pcbnew.F_Cu, w))
        added += math.hypot(qx - a[0], qy - a[1])
    return Site((qx, qy), name, clr, added, ops, stub_w)


def check_track(pcbnew, board, idx, a, b, layer, width, net, clr, via):
    if math.hypot(b[0] - a[0], b[1] - a[1]) < 1:
        return True
    return R.straight_ok(idx, pcbnew, board, a, b, layer, width, net, clr,
                         P.HOLE_CLEARANCE, ignore=[via])


def best_site(pcbnew, board, idx, via, openings, edge, pnets):
    att = attached(pcbnew, board, via)
    host = host_pads(pcbnew, board, via)
    planes = plane_layers(pcbnew, board, via, att)
    widths = POWER_W if via.GetNetname() in pnets else SIGNAL_W
    if host:
        m = min(min(h.GetSize().x, h.GetSize().y) for h in host)
        widths = [w for w in widths if w <= m] or [min(widths)]
    p = via.GetPosition()
    near = [o for o in openings
            if abs(o[0][0] - p.x) < 5 * IU and abs(o[0][1] - p.y) < 5 * IU]
    best = None
    for q in candidates(pcbnew, via, att):
        # each site at the strictest tier it meets; a looser tier costs its
        # penalty, so 0.25 mm less copper does not buy a tighter clearance
        for tier in TIERS:
            s = plan_site(pcbnew, board, idx, via, att, host, planes, near, q,
                          tier, widths, edge)
            if s is None:
                continue
            key = (s.cost + tier[4], math.hypot(q[0] - p.x, q[1] - p.y))
            if best is None or key < best[0]:
                best = (key, s)
            break
    return (best[1] if best else None), att, host, planes


def maze_site(pcbnew, board, idx, via, openings, edge, pnets,
              reach_mm=4.0, sites_max=80):
    """Second stage, for vias with no straight tie-in: route the tie-in.

    The first stage only lays straight stubs, and where a pad sits in a
    column of other nets' pads (the ESP32 edge, the USB-C row, the VCAP
    cluster north of the ADC) no straight line reaches a legal site. Here the
    via sites are the same legal points, further out, and the tie-in on each
    layer the via served is found by lib/maze on that one layer -- no extra
    via, and every segment re-checked by route.straight_ok.
    """
    import maze as M
    att = attached(pcbnew, board, via)
    host = host_pads(pcbnew, board, via)
    planes = plane_layers(pcbnew, board, via, att)
    p = via.GetPosition()
    net = via.GetNetCode()
    reach = int(reach_mm * IU)
    near = [o for o in openings
            if abs(o[0][0] - p.x) < reach + 2 * IU
            and abs(o[0][1] - p.y) < reach + 2 * IU]
    widths = SIGNAL_W if via.GetNetname() not in pnets else \
        [int(0.254 * IU), int(0.2032 * IU), int(0.1524 * IU)]
    step = int(0.05 * IU)
    for tier in TIERS:
        pts = []
        n = reach // step
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                d = math.hypot(i * step, j * step)
                if d < 0.3 * IU or d > reach:
                    continue
                pts.append((d, p.x + i * step, p.y + j * step))
        pts.sort()
        sites = []
        for _d, x, y in pts:
            # spread the sites out: forty neighbours of one blocked pocket
            # are one site tried forty times
            if any(math.hypot(x - a, y - b) < 0.25 * IU for a, b in sites):
                continue
            if site_ok(pcbnew, board, idx, via, planes, near, (x, y), tier,
                       edge):
                sites.append((x, y))
                if len(sites) >= sites_max:
                    break
        found = []
        for q in sites:
            legs = []
            if host:
                legs.append((stub_start(pcbnew, via, host), pcbnew.F_Cu))
            for layer, ends in att.items():
                if layer == pcbnew.F_Cu:
                    for t, w in ends:
                        e = t.GetStart() if w == "start" else t.GetEnd()
                        if any(h.GetEffectiveShape(pcbnew.F_Cu).Collide(
                                pcbnew.VECTOR2I(e.x, e.y), 0) for h in host):
                            continue
                        legs.append(((e.x, e.y), layer))
                else:
                    legs.append(((p.x, p.y), layer))
            plans = []
            for a, layer in legs:
                got = None
                # Off F.Cu the tie-in may land on any copper of the net on
                # that layer rather than back at the old site -- but only when
                # the tracks there meet end to end, so that they still meet
                # once the via has gone.
                hub = layer != pcbnew.F_Cu and len({
                    ((t.GetStart() if w_ == "start" else t.GetEnd()).x,
                     (t.GetStart() if w_ == "start" else t.GetEnd()).y)
                    for t, w_ in att.get(layer, ())}) == 1
                for w in widths:
                    rules = M.Rules(tier[1], P.HOLE_CLEARANCE, P.HOLE_TO_HOLE,
                                    w, via.GetWidth(pcbnew.F_Cu),
                                    via.GetDrillValue(), edge)
                    r = M.Router(pcbnew, board, idx, rules, layers=[layer])
                    plan = r.route(starts=[(a[0], a[1], layer)], net=net,
                                   goals=[(q[0], q[1], layer)], width=w,
                                   ignore=[via], margin_mm=1.5,
                                   max_nodes=60000,
                                   max_length_mm=2.5 * reach_mm)
                    if not plan.get("ok") and hub:
                        plan = r.route(starts=[(q[0], q[1], layer)], net=net,
                                       goal_net_copper=True, width=w,
                                       ignore=[via], margin_mm=1.5,
                                       max_nodes=60000,
                                       max_length_mm=2.5 * reach_mm)
                        if plan.get("ok"):
                            j = plan["tracks"][-1][1] if plan["tracks"] \
                                else q
                            plan["join"] = (layer, (p.x, p.y), j)
                    if plan.get("ok"):
                        got = (plan, w)
                        break
                if got is None:
                    plans = None
                    break
                plans.append(got)
            if plans is None:
                continue
            ops = []
            cost = 0
            for plan, w in plans:
                for a, b, layer in plan["tracks"]:
                    ops.append(("seg", a, b, layer, w))
                    cost += math.hypot(b[0] - a[0], b[1] - a[1])
                if plan.get("join"):
                    ops.append(("prune",) + plan["join"])
            found.append(Site(q, tier[0], tier[1], cost, ops,
                              plans[0][1] if host else None))
            if len(found) >= 4:
                break
        if found:
            # the nearest legal site is not always the one with the
            # shortest tie-in; take the cheapest of the first few
            return min(found, key=lambda st: st.cost)
    return None


# --- the two places a via cannot leave without another net moving ----------
# Measured on the board, not argued: in both, no legal via site exists that
# the pad can reach, on any layer, until a neighbouring net moves. Each is a
# fixed edit -- tracks and vias removed by their exact coordinates, new ones
# laid -- checked against the index before it is committed and skipped
# (and logged) if the board is not the one it was measured on.
#
# U_MCU.16 (ADS_PWDN_N). ESP_RXD runs down the inner side of the module's pad
# column at x 172.629 and back up the outer side at x 175.2195, 0.20 mm and
# 0.13 mm from the pad, with pads 15 and 17 0.32 mm above and below: the pad
# is walled in on F.Cu and the via at its centre was its only way out. The
# inner leg is pulled 0.629 mm west over the 1.8 mm beside pad 16 and rejoins
# its y 102.7585 run 0.635 mm early. That opens room for the via at the pad's
# inner end, under the module, which the search below then finds by itself.
#
# D_ESD.3 (USB_DM). F.Cu: ESP_TXD wraps the pad's north and east sides and
# pads 2 and 3 are 0.42 mm apart, so the pad can only be left southwards. B.Cu:
# ESP_RXD drops through a via 1 mm east of the pad and runs west right under
# it, so everything south of the pad is cut off from the USB_DM tracks the
# via fed. The two UART tracks between the ESD part's pad rows are narrowed
# to 0.1016 mm over the 3.4 mm between the rows (UART, 115 kbaud) and moved
# 0.178 / 0.355 mm north, ESP_RXD's via 0.381 mm north with them, and USB_DM's
# via goes to the freed spot north of pad 3 -- straight onto the end of its
# own B.Cu track, its drill 0.1225 mm from pad 3's opening. At 0.1016 mm the
# tracks keep 0.127 mm to the pad row, each other and both vias; at 0.1524
# they could not (0.092 mm, QA 2026-09-23).
ROOM_EDITS = [
    {"id": "U_MCU.16", "remove": [
        ("ESP_RXD", "F.Cu", (172.6290, 102.6060), (172.6290, 91.1760)),
        ("ESP_RXD", "F.Cu", (172.4765, 102.7585), (172.6290, 102.6060)),
        ("ESP_RXD", "F.Cu", (161.0465, 102.7585), (172.4765, 102.7585))],
     "add": [
        ("ESP_RXD", "F.Cu", (172.6290, 91.1760), (172.6290, 100.9500), 0.1525),
        ("ESP_RXD", "F.Cu", (172.6290, 100.9500), (172.0000, 101.5790), 0.1525),
        ("ESP_RXD", "F.Cu", (172.0000, 101.5790), (172.0000, 102.6000), 0.1525),
        ("ESP_RXD", "F.Cu", (172.0000, 102.6000), (171.8415, 102.7585), 0.1525),
        ("ESP_RXD", "F.Cu", (161.0465, 102.7585), (171.8415, 102.7585), 0.2032),
        # the via at the pad's inner end, and ADS_PWDN_N's B.Cu run from it
        # west of the two GND vias and round ADS_DRDY_N's via to the trunk at
        # y 108.8545 (the corridor between ADS_DRDY_N at x 171.74 and
        # ADS_RESET_N at x 173.34 is the only way south)
        ("ADS_PWDN_N", "F.Cu", (174.3560, 101.9710), (172.5500, 101.9500), 0.2032),
        ("ADS_PWDN_N", "B.Cu", (172.5500, 101.9500), (171.5770, 101.9500), 0.2032),
        ("ADS_PWDN_N", "B.Cu", (171.5770, 101.9500), (171.5770, 104.0130), 0.2032),
        ("ADS_PWDN_N", "B.Cu", (171.5770, 104.0130), (172.2755, 104.7115), 0.2032),
        ("ADS_PWDN_N", "B.Cu", (172.2755, 104.7115), (172.2755, 108.8545), 0.2032),
        ("ADS_PWDN_N", "B.Cu", (172.2755, 108.8545), (156.9315, 108.8545), 0.2032),
        # U_MCU.14 (ADS_RESET_N) sits in that corridor with its own via in
        # its pad. It moves to the pad's inner end, under the module, and
        # joins its B.Cu trunk at x 173.34 there instead of at the pad.
        ("ADS_RESET_N", "F.Cu", (172.4635, 106.7970), (173.0000, 105.1000), 0.2032),
        ("ADS_RESET_N", "B.Cu", (173.0000, 105.1000), (173.3400, 105.1000), 0.2032)],
     # the trunk now ends at the join; its last 1.42 mm would dangle. It is
     # shortened in place: Y8's copper, not new copper.
     "shorten": [
        ("ADS_RESET_N", "B.Cu", (173.3400, 82.0320), (173.3400, 106.5175),
         (173.3400, 105.1000))],
     # the old run from the pad's centre via down x 174.0005 is what the new
     # one replaces; left, it would be a 8.6 mm stub
     "remove_more": [
        ("ADS_PWDN_N", "B.Cu", (174.3560, 101.9710), (174.0005, 102.2505)),
        ("ADS_PWDN_N", "B.Cu", (174.0005, 102.2505), (174.0005, 108.8545)),
        ("ADS_PWDN_N", "B.Cu", (174.0005, 108.8545), (156.9315, 108.8545)),
        ("ADS_RESET_N", "B.Cu", (172.8320, 106.6700), (172.4765, 106.7970)),
        ("ADS_RESET_N", "B.Cu", (173.3400, 106.5175), (172.8320, 106.6700))],
     "vias_remove": [("ADS_PWDN_N", (174.3560, 101.9710)),
                     ("ADS_RESET_N", (172.4635, 106.7970))],
     "vias_add": [("ADS_PWDN_N", (172.5500, 101.9500)),
                  ("ADS_RESET_N", (173.0000, 105.1000))]},
    {"id": "D_ESD.3", "remove": [
        ("ESP_RXD", "F.Cu", (175.4230, 103.3680), (175.2195, 103.1650)),
        ("ESP_RXD", "F.Cu", (175.4230, 103.3680), (178.6740, 103.3680)),
        ("ESP_RXD", "F.Cu", (178.6740, 103.3680), (179.1820, 103.5710)),
        ("ESP_RXD", "B.Cu", (179.1820, 103.5710), (179.1820, 104.6890)),
        ("ESP_TXD", "F.Cu", (175.4735, 104.3330), (175.4735, 103.7745)),
        ("ESP_TXD", "F.Cu", (175.4735, 103.7745), (178.6230, 103.7745)),
        ("ESP_TXD", "F.Cu", (178.6230, 103.7745), (179.0805, 104.2315)),
        ("ESP_TXD", "F.Cu", (179.0805, 104.2315), (179.0805, 105.2985)),
        # the stub from the old via centre to pad 3's centre: with the via
        # gone it is copper lying in the pad (QA MINOR-5)
        ("USB_DM", "F.Cu", (178.1660, 104.3585), (178.3540, 104.7700))],
     "add": [
        ("ESP_RXD", "F.Cu", (175.2195, 103.1650), (175.2445, 103.1900), 0.1016),
        ("ESP_RXD", "F.Cu", (175.2445, 103.1900), (179.1820, 103.1900), 0.1016),
        ("ESP_RXD", "B.Cu", (179.1820, 103.1900), (179.1820, 104.6890), 0.2032),
        ("ESP_TXD", "F.Cu", (175.4735, 104.3330), (175.4735, 103.4200), 0.1016),
        ("ESP_TXD", "F.Cu", (175.4735, 103.4200), (178.6400, 103.4200), 0.1016),
        ("ESP_TXD", "F.Cu", (178.6400, 103.4200), (179.0805, 103.8605), 0.1016),
        ("ESP_TXD", "F.Cu", (179.0805, 103.8605), (179.0805, 105.2985), 0.2032),
        ("USB_DM", "F.Cu", (178.3540, 104.7710), (178.3540, 103.9100), 0.2032)],
     # the old via hid six zero-length USB_DM tracks on its centre; with it
     # gone they would be dots of copper dangling in the pad
     "zero_length_at": [("USB_DM", (178.1660, 104.3585))],
     "vias_remove": [("ESP_RXD", (179.1820, 103.5710)),
                     ("USB_DM", (178.1660, 104.3585))],
     "vias_add": [("ESP_RXD", (179.1820, 103.1900)),
                  ("USB_DM", (178.3540, 103.9100))]},
    # C_LM_FLY.1 (LM_CAP_P). The net hopped to B.Cu and back for 0.76 mm
    # through two vias, one of them 0.06 mm from the pad's opening, where the
    # same straight line on F.Cu is clear. The hop becomes that line.
    {"id": "C_LM_FLY.1", "remove": [
        ("LM_CAP_P", "B.Cu", (146.4670, 123.2310), (146.4670, 122.4690))],
     "add": [
        ("LM_CAP_P", "F.Cu", (146.4670, 122.4690), (146.4670, 123.2310), 0.2032)],
     "vias_remove": [("LM_CAP_P", (146.4670, 122.4690)),
                     ("LM_CAP_P", (146.4670, 123.2310))],
     "vias_add": []},
    # FB4.2 (V_NLDO_IN). The pad is ringed on F.Cu by V5_LM_IN (north, west
    # and south) and the LM2664 pins (east); the one pocket south of it is
    # floored on B.Cu by VNEG5's run at y 123.942. That run steps 0.358 mm
    # south under the pocket and the via goes in it.
    {"id": "FB4.2", "remove": [
        ("VNEG5", "B.Cu", (143.5710, 123.9420), (139.6595, 123.9420))],
     "add": [
        ("VNEG5", "B.Cu", (139.6595, 123.9420), (140.0175, 124.3000), 0.2032),
        ("VNEG5", "B.Cu", (140.0175, 124.3000), (142.4000, 124.3000), 0.2032),
        ("VNEG5", "B.Cu", (142.4000, 124.3000), (142.7580, 123.9420), 0.2032),
        ("VNEG5", "B.Cu", (142.7580, 123.9420), (143.5710, 123.9420), 0.2032),
        ("V_NLDO_IN", "F.Cu", (141.0310, 122.6720), (141.0300, 123.7200), 0.2540),
        ("V_NLDO_IN", "B.Cu", (141.0310, 122.6720), (141.0300, 123.7200), 0.2032)],
     "vias_remove": [("V_NLDO_IN", (141.0310, 122.6720))],
     "vias_add": [("V_NLDO_IN", (141.0300, 123.7200))]},
    # J1.4 (USB_CC1). L7's via beside the USB-C pad column sat 0.05 mm from
    # pad 4's opening. Clear of the opening by 0.10 mm, a standard via cannot
    # keep 0.127 mm from both USB_DM's jog (0.534 mm away) and the
    # USB_VBUS_RAW via (0.72 mm): the two constraints miss by 0.016 mm. A
    # 0.46 / 0.30 mm via (annular 0.08, ACCEPTANCE C allows 0.45 / 0.30) fits
    # with 0.19 mm to both.
    {"id": "J1.4", "remove": [
        ("USB_CC1", "F.Cu", (176.5935, 112.2680), (175.7910, 112.2380)),
        ("USB_CC1", "B.Cu", (174.8790, 114.1730), (176.5935, 112.2680))],
     "add": [
        ("USB_CC1", "F.Cu", (175.7910, 112.2380), (176.6450, 112.2600), 0.2032),
        ("USB_CC1", "B.Cu", (174.8790, 114.1730), (176.6450, 112.2600), 0.2032)],
     "vias_remove": [("USB_CC1", (176.5935, 112.2680))],
     "vias_add": [("USB_CC1", (176.6450, 112.2600), 0.46, 0.30)]},
    # R_CC2.2 (GND). The pad sits in a ring of USB_CC2, USB_DP and the
    # USB_VBUS_RAW / USB_DP vias; no standard via fits anywhere it can reach.
    # A 0.46 / 0.30 mm via (annular 0.08, ACCEPTANCE C allows 0.45 / 0.30)
    # fits between the resistor's own pads, under its body, 0.15 mm from both
    # openings and 0.12 mm from pad 1's copper, straight onto the In1 plane.
    {"id": "R_CC2.2", "remove": [
        ("GND", "F.Cu", (174.0945, 110.2260), (174.2035, 110.3785))],
     "add": [
        ("GND", "F.Cu", (174.0935, 110.2260), (173.3400, 110.2260), 0.2032)],
     "vias_remove": [("GND", (174.2035, 110.3785))],
     "vias_add": [("GND", (173.3400, 110.2260), 0.46, 0.30)],
     # 0.70 mm of copper between the two pads holds a 0.46 via with 0.12 mm
     # each side; 0.127 would need a 0.446 via, under the 0.452 that a 0.30
     # drill needs for ACCEPTANCE C's 0.076 annulus. 0.12 is the most there is.
     "clearance_mm": 0.118},
]


def _mm2(pt):
    return (round(pt[0], 4), round(pt[1], 4))


def room_edit(pcbnew, board, idx, spec, log):
    """Apply one ROOM_EDITS entry, or leave the board alone and say why."""
    rec = {"id": spec["id"], "applied": False}
    clr = P.nm(spec.get("clearance_mm", 0.127))
    log.setdefault("room_edits", []).append(rec)
    old = []
    for net, lname, a, b in spec["remove"] + spec.get("remove_more", []):
        layer = board.GetLayerID(lname)
        hit = [t for t in board.GetTracks()
               if t.GetClass() != "PCB_VIA" and t.GetNetname() == net
               and t.GetLayer() == layer
               and {_mm2((P.mm(t.GetStart().x), P.mm(t.GetStart().y))),
                    _mm2((P.mm(t.GetEnd().x), P.mm(t.GetEnd().y)))}
               == {_mm2(a), _mm2(b)}]
        if len(hit) != 1:
            rec["why"] = "track %s %s %s-%s found %d times" % (
                net, lname, a, b, len(hit))
            return False
        old.append(hit[0])
    for net, at, *_size in spec["vias_remove"]:
        hit = [t for t in board.GetTracks()
               if t.GetClass() == "PCB_VIA" and t.GetNetname() == net
               and _mm2((P.mm(t.GetPosition().x), P.mm(t.GetPosition().y)))
               == _mm2(at)]
        if len(hit) != 1:
            rec["why"] = "via %s %s found %d times" % (net, at, len(hit))
            return False
        old.append(hit[0])
    for net, at in spec.get("zero_length_at", ()):
        old += [t for t in board.GetTracks()
                if t.GetClass() != "PCB_VIA" and t.GetNetname() == net
                and t.GetLength() == 0
                and _mm2((P.mm(t.GetStart().x), P.mm(t.GetStart().y)))
                == _mm2(at)]
    removed = [P.describe(board, t) for t in old]
    for t in old:
        board.RemoveNative(t)
    shortened = []
    for net, lname, a, b, nb in spec.get("shorten", ()):
        layer = board.GetLayerID(lname)
        hit = [t for t in board.GetTracks()
               if t.GetClass() != "PCB_VIA" and t.GetNetname() == net
               and t.GetLayer() == layer
               and {_mm2((P.mm(t.GetStart().x), P.mm(t.GetStart().y))),
                    _mm2((P.mm(t.GetEnd().x), P.mm(t.GetEnd().y)))}
               == {_mm2(a), _mm2(b)}]
        if len(hit) != 1:
            raise SystemExit("S7v: room edit %s: track %s %s-%s found %d "
                             "times" % (spec["id"], net, a, b, len(hit)))
        t = hit[0]
        removed.append(P.describe(board, t))
        nv = pcbnew.VECTOR2I(P.nm(nb[0]), P.nm(nb[1]))
        if _mm2((P.mm(t.GetEnd().x), P.mm(t.GetEnd().y))) == _mm2(b):
            t.SetEnd(nv)
        else:
            t.SetStart(nv)
        shortened.append(t)
    idx.rebuild()
    laid, made, bad = [], [], None
    for net, at, *size in spec["vias_add"]:
        code = board.FindNet(net).GetNetCode()
        q = (P.nm(at[0]), P.nm(at[1]))
        dia, drill = ((P.nm(size[0]), P.nm(size[1])) if size
                      else (P.VIA_DIA, P.VIA_DRILL))
        if not R.via_site_ok(idx, pcbnew, q[0], q[1], code, dia, drill,
                             clr, P.HOLE_TO_HOLE,
                             P.HOLE_CLEARANCE,
                             None):
            bad = "via %s %s not clear" % (net, at)
            break
        made.append(R.add_via(pcbnew, board, q, code, dia, drill))
        idx.rebuild()
    for net, lname, a, b, w in ([] if bad else spec["add"]):
        code = board.FindNet(net).GetNetCode()
        layer = board.GetLayerID(lname)
        pa, pb = (P.nm(a[0]), P.nm(a[1])), (P.nm(b[0]), P.nm(b[1]))
        if not R.straight_ok(idx, pcbnew, board, pa, pb, layer, P.nm(w),
                             code, clr, P.HOLE_CLEARANCE):
            bad = "%s %s %s-%s not clear" % (net, lname, a, b)
            break
        made.append(R.add_track(pcbnew, board, pa, pb, layer, P.nm(w), code))
        idx.rebuild()
    if bad:
        # Putting the board back item by item is not safe through SWIG (a
        # removed item's proxy can already be gone); the edit was measured on
        # this board, so its failing means the board is not that board. Stop
        # without saving and say which edit and why.
        rec["why"] = bad
        raise SystemExit("S7v: room edit %s failed: %s -- nothing saved"
                         % (spec["id"], bad))
    laid = [P.describe(board, t) for t in made + shortened]
    rec.update({"applied": True, "removed": removed, "laid": laid})
    return True


def apply_site(pcbnew, board, via, site):
    """Commit a site. Returns (removed, laid) as describe() records."""
    removed, laid = [], []
    qx, qy = int(round(site.q[0])), int(round(site.q[1]))
    q = pcbnew.VECTOR2I(qx, qy)
    for op in site.ops:
        if op[0] == "shorten":
            t, which = op[1], op[2]
            removed.append(P.describe(board, t))
            if which == "start":
                t.SetStart(q)
            else:
                t.SetEnd(q)
            laid.append(P.describe(board, t))
        elif op[0] == "split":
            t, which = op[1], op[2]
            removed.append(P.describe(board, t))
            # copies: GetEnd() hands back a reference SetEnd() then rewrites
            ex, ey = int(t.GetEnd().x), int(t.GetEnd().y)
            t.SetEnd(q)
            laid.append(P.describe(board, t))
            t2 = R.add_track(pcbnew, board, (qx, qy), (ex, ey), t.GetLayer(),
                             t.GetWidth(), t.GetNetCode())
            laid.append(P.describe(board, t2))
        elif op[0] == "prune":
            continue            # after the via is gone, below
        elif op[0] == "seg":
            _k, a, b, layer, w = op
            if a != b:
                t = R.add_track(pcbnew, board, a, b, layer, w,
                                via.GetNetCode())
                laid.append(P.describe(board, t))
        else:
            _k, a, b, layer, w = op
            t = R.add_track(pcbnew, board, a, b, layer, w, via.GetNetCode())
            laid.append(P.describe(board, t))
    nv = R.add_via(pcbnew, board, (qx, qy), via.GetNetCode(),
                   via.GetWidth(pcbnew.F_Cu), via.GetDrillValue())
    removed.append(P.describe(board, via))
    laid.append(P.describe(board, nv))
    board.RemoveNative(via)
    for op in site.ops:
        if op[0] == "prune":
            prune_dead_chain(pcbnew, board, via.GetNetCode(), op[1], op[2],
                             op[3], removed, laid)
    return removed, laid


def prune_dead_chain(pcbnew, board, net, layer, p, j, removed, laid):
    """Take out the copper that only led to the old site.

    When a tie-in off F.Cu lands on the net somewhere else, the tracks that
    ran from the old site to that spot now serve nothing: a stub hanging off
    the net. They are removed back to the join, walking from the old site
    one track at a time, and only while every node on the way is a plain
    two-track bend -- a node with a pad, a via, a branch or a track passing
    through stops the walk and nothing is removed."""
    tol = 1000

    def ends_at(pt, skip):
        out = []
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA" or t.GetNetCode() != net \
                    or t.GetLayer() != layer or t in skip:
                continue
            for which, e in (("start", t.GetStart()), ("end", t.GetEnd())):
                if math.hypot(e.x - pt[0], e.y - pt[1]) <= tol:
                    out.append((t, which))
        return out

    def other_copper(pt, chain):
        v = pcbnew.VECTOR2I(int(pt[0]), int(pt[1]))
        for t in board.GetTracks():
            if t.GetNetCode() != net or t in chain:
                continue
            if t.GetClass() == "PCB_VIA":
                if t.GetEffectiveShape(layer).Collide(v, 0):
                    return True
            elif t.GetLayer() == layer and \
                    t.GetEffectiveShape(layer).Collide(v, 0):
                return True
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetCode() == net and pad.IsOnLayer(layer) and \
                        pad.GetEffectiveShape(layer).Collide(v, 0):
                    return True
        return False

    node, chain, trim = p, [], None
    for _step in range(200):
        at = [(t, w) for t, w in ends_at(node, chain)
              if t.GetLength() > 0]
        if len(at) != 1 or other_copper(node, chain + [t for t, _ in at]):
            return False
        t, which = at[0]
        s, e = t.GetStart(), t.GetEnd()
        far = (e.x, e.y) if which == "start" else (s.x, s.y)
        # the router stops as soon as its track touches the net, so the join
        # sits up to a track width off this one's centre line
        if seg_dist(s.x, s.y, e.x, e.y, j[0], j[1]) <= \
                t.GetWidth() / 2 + int(0.16 * IU):
            trim = (t, which)
            break
        chain.append(t)
        node = far
    if trim is None:
        return False
    for t in chain:
        removed.append(P.describe(board, t))
        board.Remove(t)
    t, which = trim
    removed.append(P.describe(board, t))
    # the join, projected onto the kept track's centre line; the new leg is
    # pulled onto it so the two meet end to end
    s, e = t.GetStart(), t.GetEnd()
    dx, dy = e.x - s.x, e.y - s.y
    L2 = float(dx * dx + dy * dy) or 1.0
    u = max(0.0, min(1.0, ((j[0] - s.x) * dx + (j[1] - s.y) * dy) / L2))
    jp = (int(round(s.x + u * dx)), int(round(s.y + u * dy)))
    jv = pcbnew.VECTOR2I(jp[0], jp[1])
    for leg in board.GetTracks():
        if leg.GetClass() == "PCB_VIA" or leg.GetNetCode() != net \
                or leg.GetLayer() != layer or leg is t:
            continue
        for w_, pt in (("start", leg.GetStart()), ("end", leg.GetEnd())):
            if math.hypot(pt.x - j[0], pt.y - j[1]) <= tol:
                if w_ == "start":
                    leg.SetStart(jv)
                else:
                    leg.SetEnd(jv)
                for rec in laid:
                    if rec.get("uuid") == R.uid(leg):
                        rec.update(P.describe(board, leg))
    if which == "start":
        t.SetStart(jv)
    else:
        t.SetEnd(jv)
    if t.GetLength() == 0:
        board.Remove(t)
    else:
        laid.append(P.describe(board, t))
    return True


def path_lengths(pcbnew, board, names, anchor_ref="U_ADS"):
    """Copper path length from the ADC pin to the farthest pad of each net.

    Total copper on a net is the wrong measure here: a CM capacitor's pad
    hangs off the input path, and moving a via onto its stub changes the
    stub, not the path from the electrode resistor to the ADC. So this walks
    the net as a graph -- track ends, joined through vias and pads -- and
    reports the shortest route from the ADC pin to each other pad, keeping
    the longest (the electrode side)."""
    import heapq
    out = {}
    for name in names:
        net = board.FindNet(name)
        if net is None:
            continue
        code = net.GetNetCode()
        tracks = [t for t in board.GetTracks() if t.GetNetCode() == code]
        pads = [(fp.GetReference(), p) for fp in board.GetFootprints()
                for p in fp.Pads() if p.GetNetCode() == code]
        nodes, adj = [], {}

        def node(key):
            if key not in adj:
                adj[key] = []
                nodes.append(key)
            return key

        def link(a, b, w):
            adj[node(a)].append((b, w))
            adj[node(b)].append((a, w))

        ends = []
        for t in tracks:
            if t.GetClass() == "PCB_VIA":
                continue
            a = ("e", t.GetStart().x, t.GetStart().y, t.GetLayer())
            b = ("e", t.GetEnd().x, t.GetEnd().y, t.GetLayer())
            link(a, b, t.GetLength())
            ends += [a, b]
        # ends that touch: the same point, a via, or a pad
        by_pt = {}
        for e in ends:
            by_pt.setdefault((e[1], e[2], e[3]), []).append(e)
        for group in by_pt.values():
            for e in group[1:]:
                link(group[0], e, 0)
        for t in tracks:
            if t.GetClass() != "PCB_VIA":
                continue
            v = ("v", t.GetPosition().x, t.GetPosition().y)
            node(v)
            r = t.GetWidth(pcbnew.F_Cu) / 2.0
            for e in ends:
                if math.hypot(e[1] - v[1], e[2] - v[2]) <= r:
                    link(v, e, 0)
        for ref, p in pads:
            k = ("p", ref, p.GetNumber())
            node(k)
            for e in ends:
                if p.IsOnLayer(e[3]) and p.GetEffectiveShape(e[3]).Collide(
                        pcbnew.VECTOR2I(e[1], e[2]), 0):
                    link(k, e, 0)
            for t in tracks:
                if t.GetClass() == "PCB_VIA" and p.GetEffectiveShape(
                        pcbnew.F_Cu).Collide(t.GetPosition(), 0):
                    link(k, ("v", t.GetPosition().x, t.GetPosition().y), 0)
        starts = [("p", ref, p.GetNumber()) for ref, p in pads
                  if ref == anchor_ref]
        if not starts:
            continue
        dist = {starts[0]: 0}
        q = [(0, starts[0])]
        while q:
            d, n = heapq.heappop(q)
            if d > dist.get(n, d):
                continue
            for m, w in adj.get(n, ()):
                nd = d + w
                if nd < dist.get(m, nd + 1):
                    dist[m] = nd
                    heapq.heappush(q, (nd, m))
        far = [(dist.get(("p", ref, p.GetNumber())), ref, p.GetNumber())
               for ref, p in pads if ref != anchor_ref]
        far = [f for f in far if f[0] is not None]
        if far:
            d, ref, num = max(far)
            out[name] = {"to": "%s.%s" % (ref, num),
                         "mm": round(d / float(IU), 4)}
    return out


INPUT_PAIRS = [("IN%dP" % i, "IN%dN" % i) for i in range(1, 9)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-save", action="store_true",
                    help="save even when a check fails (use on a copy only)")
    a = ap.parse_args()
    root = a.root

    import pcbnew
    bpath = P.board_path(root)
    board = pcbnew.LoadBoard(bpath)
    pnets = power_nets(root)
    inputs = [n for pr in INPUT_PAIRS for n in pr] + ["SRB1"]
    len_before = path_lengths(pcbnew, board, inputs)
    unconnected_before = P.unconnected_count(pcbnew, board)
    vias_before = sum(1 for t in board.GetTracks() if t.GetClass() == "PCB_VIA")
    bb = board.GetBoardEdgesBoundingBox()
    edge = (bb.GetLeft() + P.EDGE_CLEARANCE, bb.GetTop() + P.EDGE_CLEARANCE,
            bb.GetRight() - P.EDGE_CLEARANCE, bb.GetBottom() - P.EDGE_CLEARANCE)

    openings = mask_openings(pcbnew, board)
    found = offenders(pcbnew, board, openings)
    log = {"step": "S7v", "offenders_before": len(found), "moved": [],
           "removed": [], "unresolved": []}
    idx = R.CopperIndex(pcbnew, board)

    for spec in ROOM_EDITS:
        if any(pad_name(pad) == spec["id"] for _v, pad, _g in found):
            room_edit(pcbnew, board, idx, spec, log)
    # an edit may itself have moved an offender (D_ESD.3's via): count again
    found = offenders(pcbnew, board, openings)
    pending = [v for v, _pad, _g in found]
    names = {R.uid(v): (pad_name(pad), round(g / IU, 4))
             for v, pad, g in found}
    # two straight passes (the first frees room for the second), then the
    # routed tie-in for whatever is left
    for stage in ("straight", "straight", "maze"):
        left = []
        for via in pending:
            att = attached(pcbnew, board, via)
            if functionless(pcbnew, board, via, att,
                            plane_layers(pcbnew, board, via, att)):
                old = via.GetPosition()
                rec = P.describe(board, via)
                board.Remove(via)
                if P.unconnected_count(pcbnew, board) <= unconnected_before:
                    log["removed"].append({
                        "net": rec["net"], "pad": names[R.uid(via)][0],
                        "at_mm": rec["pos_mm"], "removed": [rec],
                        "why": "reaches no other layer and no plane"})
                    idx.rebuild()
                    continue
                board.Add(via)          # it was carrying a connection after all
            site, att, host, planes = best_site(pcbnew, board, idx, via,
                                                openings, edge, pnets)
            if site is None and stage == "maze":
                site = maze_site(pcbnew, board, idx, via, openings, edge,
                                 pnets)
            if site is None:
                left.append(via)
                continue
            old = via.GetPosition()
            pad, gap = names[R.uid(via)]
            removed, laid = apply_site(pcbnew, board, via, site)
            log["moved"].append({
                "net": removed[-1]["net"], "pad": pad, "gap_before_mm": gap,
                "from_mm": [P.mm(old.x), P.mm(old.y)],
                "to_mm": [round(site.q[0] / IU, 4), round(site.q[1] / IU, 4)],
                "moved_mm": round(math.hypot(site.q[0] - old.x,
                                             site.q[1] - old.y) / IU, 4),
                "stage": "maze" if any(o[0] == "seg" for o in site.ops)
                         else "straight",
                "tier": site.tier, "clearance_mm": P.mm(site.clearance),
                "new_copper_mm": round(site.cost / IU, 4),
                "stub_width_mm": P.mm(site.width) if site.width else None,
                "planes": [board.GetLayerName(l) for l in planes],
                "removed": removed, "laid": laid})
            idx.rebuild()
        pending = left
        if not pending:
            break
    for via in pending:
        p = via.GetPosition()
        log["unresolved"].append({"net": via.GetNetname(),
                                  "pad": names[R.uid(via)][0],
                                  "at_mm": [P.mm(p.x), P.mm(p.y)]})

    after = offenders(pcbnew, board, mask_openings(pcbnew, board))
    room_via_delta = sum(
        sum(1 for x in r.get("laid", ()) if x.get("kind") == "via")
        - sum(1 for x in r.get("removed", ()) if x.get("kind") == "via")
        for r in log.get("room_edits", ()) if r.get("applied"))
    unconnected_after = P.unconnected_count(pcbnew, board)
    vias_after = sum(1 for t in board.GetTracks() if t.GetClass() == "PCB_VIA")
    len_after = path_lengths(pcbnew, board, inputs)
    pairs = []
    for pn, nn in INPUT_PAIRS:
        pairs.append({"pair": "%s/%s" % (pn, nn),
                      "skew_before_mm": round(abs(len_before[pn]["mm"]
                                                  - len_before[nn]["mm"]), 4),
                      "skew_after_mm": round(abs(len_after[pn]["mm"]
                                                 - len_after[nn]["mm"]), 4)})
    log.update({"offenders_after": len(after),
                "offenders_after_list": [
                    {"net": v.GetNetname(), "pad": pad_name(pad),
                     "gap_mm": round(g / IU, 4)} for v, pad, g in after],
                "tiers": {t[0]: sum(1 for m in log["moved"]
                                    if m["tier"] == t[0]) for t in TIERS},
                "vias": [vias_before, vias_after],
                "unconnected": [unconnected_before, unconnected_after],
                "input_lengths_mm": {"before": len_before,
                                     "after": len_after},
                "input_pair_skew": pairs})

    saved = False
    if not a.dry_run and log["moved"] and (
            unconnected_after <= unconnected_before or a.force_save):
        board.Save(bpath)
        saved = True
    log["saved"] = saved
    E.dump_json(os.path.join(root, "logs", "viapad_fix.json"), log)

    worst_len = max([abs(len_after[n]["mm"] - len_before[n]["mm"])
                     for n in inputs if n != "SRB1"
                     and n in len_before and n in len_after] + [0])
    srb_len = (round(len_after["SRB1"]["mm"] - len_before["SRB1"]["mm"], 4)
               if "SRB1" in len_before and "SRB1" in len_after else None)
    worse_skew = [p for p in pairs
                  if p["skew_after_mm"] > p["skew_before_mm"] + 0.05]
    checks = [
        P.check("vias within 0.10 mm of an SMD mask opening", 0,
                len(after)),
        P.check("offenders left unresolved", 0, len(log["unresolved"])),
        P.check("via count = before - functionless removed + room edits",
                vias_before - len(log["removed"]) + room_via_delta,
                vias_after),
        P.check("unconnected items (KiCad connectivity)", unconnected_before,
                unconnected_after, ok=unconnected_after <= unconnected_before),
        P.check("largest ADC-to-electrode path change on IN1P-IN8N [mm]",
                "<= 0.1", round(worst_len, 4), ok=worst_len <= 0.1),
        # SRB1 ends in R_SRB_SER pad 1, where its via was: any via outside
        # the pad adds the stub back to it to the path. Bounded, not zero.
        P.check("SRB1 ADC-to-resistor path change [mm]", "<= 1.0",
                srb_len, ok=srb_len is not None and abs(srb_len) <= 1.0),
        P.check("input pairs whose P/N length skew grew > 0.05 mm", 0,
                len(worse_skew)),
        P.check("board saved", True, saved or a.dry_run),
    ]
    P.gate(root, "S7v", checks,
           notes="%d vias found in SMD mask openings, %d moved out "
                 "(tiers %s), %d unresolved; vias %d -> %d, unconnected "
                 "%d -> %d." % (len(found), len(log["moved"]),
                                log["tiers"], len(log["unresolved"]),
                                vias_before, vias_after, unconnected_before,
                                unconnected_after))
    bad = [c["name"] for c in checks if not c["pass"]]
    print("S7v: %s" % ("pass" if not bad else "FAIL " + ", ".join(bad)))
    print("  offenders %d -> %d, moved %d, unresolved %d, tiers %s"
          % (len(found), len(after), len(log["moved"]),
             len(log["unresolved"]), log["tiers"]))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
