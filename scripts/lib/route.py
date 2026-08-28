"""Editing copper on a loaded board: collision queries, stub removal, routing.

Written for 20_apply_eco.py, but the L1-L5 repairs in S5 need exactly the same
primitives, so it lives here rather than inside that script.

Everything is geometric and checked before it is placed. `CopperIndex` caches
one SHAPE per (item, copper layer) and buckets them into a 2 mm grid; a
candidate position is then tested with SHAPE::Collide(point, clearance), which
is the same predicate KiCad's own DRC uses. Nothing here writes a track or via
without first proving it clears every other net by the design rule -- if no
position works, the caller is told so rather than handed a guess.

Zones are deliberately NOT in the index. They are refilled after every edit, so
they pull back around whatever gets placed; treating them as obstacles would
make the whole inner-layer area unusable. Their nets still matter for
connectivity, which `zone_nets_at` answers.

Needs pcbnew; the module is passed in rather than imported so this file can be
read by tooling that does not have it.
"""

import math

IU = 1000000                                   # nm per mm
CELL = 2 * IU                                  # spatial bucket, 2 mm


def uid(item):
    """A stable key for a board item.

    id() is useless here: pcbnew hands out a fresh SWIG proxy every time an
    item is reached through the board, so `pad is pad` is False for the same
    pad fetched twice. The KIID survives that."""
    return item.m_Uuid.AsString()


def mm(v):
    return v / float(IU)


def nm(v):
    return int(round(v * IU))


def copper_layers(pcbnew, board):
    """F.Cu, the enabled inner layers, B.Cu -- in stack order."""
    return list(board.GetEnabledLayers().CuStack())


def item_layers(pcbnew, item):
    cls = item.GetClass()
    if cls == "PCB_VIA":
        return [l for l in item.GetLayerSet().CuStack()]
    if cls == "PAD":
        return [l for l in item.GetLayerSet().CuStack()]
    return [item.GetLayer()]


def drill_radius(pcbnew, item):
    """Half the drilled hole, or 0 for anything that is not drilled."""
    cls = item.GetClass()
    if cls == "PCB_VIA":
        return item.GetDrillValue() / 2.0
    if cls == "PAD":
        d = item.GetDrillSize()
        return max(d.x, d.y) / 2.0
    return 0.0


class CopperIndex(object):
    """Every piece of copper on the board, bucketed by layer and 2 mm cell."""

    def __init__(self, pcbnew, board):
        self.pcbnew = pcbnew
        self.board = board
        self.rebuild()

    def rebuild(self):
        pcbnew = self.pcbnew
        self.cells = {}
        self.shapes = []                       # keeps the SHAPE proxies alive
        self.drills = []                       # (item, x, y, radius, is_npth)
        self.tracks = [t for t in self.board.GetTracks()]
        self.pads = [p for f in self.board.GetFootprints() for p in f.Pads()]
        for item in self.tracks + self.pads:
            net = item.GetNetCode()
            for layer in item_layers(pcbnew, item):
                try:
                    sh = item.GetEffectiveShape(layer)
                except Exception:
                    continue
                self.shapes.append(sh)
                bb = sh.BBox(0)
                self._put(layer, bb, (item, net, sh))
            r = drill_radius(pcbnew, item)
            if r > 0:
                p = item.GetPosition()
                npth = (item.GetClass() == "PAD"
                        and int(item.GetAttribute())
                        == int(pcbnew.PAD_ATTRIB_NPTH))
                self.drills.append((item, p.x, p.y, r, npth))
        self.zones = [z for z in self.board.Zones() if not z.GetIsRuleArea()]

    def _put(self, layer, bb, entry):
        for cx in range(bb.GetLeft() // CELL, bb.GetRight() // CELL + 1):
            for cy in range(bb.GetTop() // CELL, bb.GetBottom() // CELL + 1):
                self.cells.setdefault((layer, cx, cy), []).append(entry)

    def _query(self, layer, left, top, right, bottom):
        seen, out = set(), []
        left, top = int(math.floor(left)), int(math.floor(top))
        right, bottom = int(math.ceil(right)), int(math.ceil(bottom))
        for cx in range(left // CELL, right // CELL + 1):
            for cy in range(top // CELL, bottom // CELL + 1):
                for entry in self.cells.get((layer, cx, cy), ()):
                    key = uid(entry[0])
                    if key not in seen:
                        seen.add(key)
                        out.append(entry)
        return out

    # --- queries ---------------------------------------------------------
    def point_conflicts(self, x, y, layer, radius, clearance, net,
                        ignore=()):
        """Copper of another net within `radius + clearance` of (x, y)."""
        reach = int(radius + clearance)
        skip = {uid(i) for i in ignore}
        bad = []
        for item, inet, sh in self._query(layer, x - reach, y - reach,
                                          x + reach, y + reach):
            if inet == net and net != 0:
                continue
            if uid(item) in skip:
                continue
            if sh.Collide(self.pcbnew.VECTOR2I(int(x), int(y)), reach):
                bad.append(item)
        return bad

    def shape_conflicts(self, shape, layer, clearance, net, ignore=()):
        """Copper of another net within `clearance` of an arbitrary shape."""
        bb = shape.BBox(int(clearance))
        skip = {uid(i) for i in ignore}
        bad = []
        for item, inet, sh in self._query(layer, bb.GetLeft(), bb.GetTop(),
                                          bb.GetRight(), bb.GetBottom()):
            if inet == net and net != 0:
                continue
            if uid(item) in skip:
                continue
            if shape.Collide(sh, int(clearance)):
                bad.append(item)
        return bad

    def hole_conflicts(self, x, y, radius, hole_to_hole, ignore=()):
        """Drilled holes whose edge comes within `hole_to_hole` of this one."""
        skip = {uid(i) for i in ignore}
        bad = []
        for item, hx, hy, r, _npth in self.drills:
            if uid(item) in skip:
                continue
            if math.hypot(hx - x, hy - y) < radius + r + hole_to_hole:
                bad.append(item)
        return bad

    def npth_conflicts(self, x, y, radius, hole_clearance, ignore=()):
        """NPTH holes this piece of copper would sit inside (or too near)."""
        skip = {uid(i) for i in ignore}
        bad = []
        for item, hx, hy, r, npth in self.drills:
            if not npth or uid(item) in skip:
                continue
            if math.hypot(hx - x, hy - y) < radius + r + hole_clearance:
                bad.append(item)
        return bad

    def zone_nets_at(self, x, y, layer):
        p = self.pcbnew.VECTOR2I(int(x), int(y))
        out = []
        for z in self.zones:
            if z.GetLayerSet().Contains(layer) and z.HitTestFilledArea(layer, p):
                out.append(z.GetNetname())
        return out


# --- board edits -------------------------------------------------------------
def get_or_create_net(pcbnew, board, name):
    net = board.FindNet(name)
    if net is not None and net.GetNetCode() >= 0:
        return net
    net = pcbnew.NETINFO_ITEM(board, name)
    board.Add(net)
    return board.FindNet(name)


def add_track(pcbnew, board, a, b, layer, width, netcode):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(int(a[0]), int(a[1])))
    t.SetEnd(pcbnew.VECTOR2I(int(b[0]), int(b[1])))
    t.SetWidth(int(width))
    t.SetLayer(layer)
    t.SetNetCode(netcode)
    board.Add(t)
    return t


def add_via(pcbnew, board, pos, netcode, diameter, drill):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(int(pos[0]), int(pos[1])))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetWidth(int(diameter))
    v.SetDrill(int(drill))
    v.SetNetCode(netcode)
    board.Add(v)
    return v


def touches(pcbnew, a, b):
    """Do two copper items actually meet, on some layer they share?"""
    la, lb = set(item_layers(pcbnew, a)), set(item_layers(pcbnew, b))
    for layer in la & lb:
        try:
            if a.GetEffectiveShape(layer).Collide(b.GetEffectiveShape(layer), 0):
                return True
        except Exception:
            continue
    return False


def trace_island(pcbnew, board, pad):
    """Tracks and vias reachable from `pad` through same-net copper.

    Walks track/via adjacency only -- it does not step through zones, and it
    does not step through other pads. The result is the little island of
    routing that exists solely to serve this pad, which is what has to come out
    when the pad changes net.

    Returns (items, other_pads_touched). A non-empty second element means the
    island is shared and must NOT simply be deleted.
    """
    net = pad.GetNetCode()
    candidates = [t for t in board.GetTracks() if t.GetNetCode() == net]
    other_pads = [p for f in board.GetFootprints() for p in f.Pads()
                  if p.GetNetCode() == net and uid(p) != uid(pad)]
    island, frontier = [], [pad]
    seen = {uid(pad)}
    while frontier:
        cur = frontier.pop()
        for c in candidates:
            if uid(c) in seen:
                continue
            if touches(pcbnew, cur, c):
                seen.add(uid(c))
                island.append(c)
                frontier.append(c)
    shared = [p for p in other_pads
              if any(touches(pcbnew, p, i) for i in island)]
    return island, shared


def remove_items(board, items):
    for it in items:
        board.RemoveNative(it)


# --- placement search --------------------------------------------------------
def ring_points(cx, cy, r_min, r_max, step):
    """Candidate points in an annulus, nearest first."""
    pts = []
    n = int(math.ceil(r_max / step))
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            x, y = cx + i * step, cy + j * step
            d = math.hypot(x - cx, y - cy)
            if r_min <= d <= r_max:
                pts.append((d, x, y))
    pts.sort()
    return [(x, y) for _d, x, y in pts]


def via_site_ok(idx, pcbnew, x, y, netcode, dia, drill, clearance,
                hole_to_hole, hole_clearance, edge_box, ignore=()):
    r = dia / 2.0
    if edge_box is not None:
        lo_x, lo_y, hi_x, hi_y = edge_box
        if not (lo_x + r <= x <= hi_x - r and lo_y + r <= y <= hi_y - r):
            return False
    if idx.hole_conflicts(x, y, drill / 2.0, hole_to_hole, ignore=ignore):
        return False
    if idx.npth_conflicts(x, y, r, hole_clearance, ignore=ignore):
        return False
    for layer in copper_layers(pcbnew, idx.board):
        if idx.point_conflicts(x, y, layer, r, clearance, netcode,
                               ignore=ignore):
            return False
    return True


def body_box(pcbnew, fp):
    """The component body as an axis-aligned box, from its F.Fab outline.

    Falls back to the pad extents when a footprint has no F.Fab graphics.
    This, not the courtyard, is what decides whether two parts physically fit
    next to each other."""
    xs, ys = [], []
    for d in fp.GraphicalItems():
        if d.GetClass() == "PCB_SHAPE" and d.GetLayer() == pcbnew.F_Fab:
            bb = d.GetBoundingBox()
            xs += [bb.GetLeft(), bb.GetRight()]
            ys += [bb.GetTop(), bb.GetBottom()]
    if not xs:
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            xs += [bb.GetLeft(), bb.GetRight()]
            ys += [bb.GetTop(), bb.GetBottom()]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


class BodyIndex(object):
    """Component body boxes, for "does this part physically fit here".

    Used instead of a courtyard test. The EasyEDA courtyards on this board are
    generous -- 1.93 x 1.17 mm around a 1.0 x 0.5 mm 0402 body -- and 69 pairs
    of existing parts already overlap them, so refusing any courtyard contact
    holds new parts to a standard the board itself does not meet, and on this
    layout it rules out every position near the ADS1299. Measured body gaps
    between the existing parts run 0.001 / 0.135 / 0.181 / 0.227 / 0.262 mm at
    the tight end, median 1.21 mm; requiring 0.2 mm of a new part is therefore
    stricter than several pairs already on the board.
    """

    def __init__(self, pcbnew, board, skip_refs=()):
        self.pcbnew = pcbnew
        self.skip = set(skip_refs)
        self.entries = []
        for fp in board.GetFootprints():
            ref = fp.GetReference() or "(anon)"
            if ref in self.skip:
                continue
            bx = body_box(pcbnew, fp)
            if bx:
                self.entries.append((ref, bx))

    def clash(self, fp, gap):
        bx = body_box(self.pcbnew, fp)
        if bx is None:
            return None
        l, t, r, b = bx[0] - gap, bx[1] - gap, bx[2] + gap, bx[3] + gap
        for ref, (ol, ot, orr, ob) in self.entries:
            if orr <= l or ol >= r or ob <= t or ot >= b:
                continue
            return ref
        return None


class CourtyardIndex(object):
    """Every footprint's front courtyard, with a bounding box for fast reject.

    Testing a candidate position against all 137 footprints with
    SHAPE_POLY_SET::Collide costs about a millisecond, and the placement search
    runs it tens of thousands of times -- that alone took the ECO script past
    ten minutes. Bounding boxes cut it to the two or three neighbours that can
    possibly matter.
    """

    def __init__(self, pcbnew, board, skip_refs=()):
        self.pcbnew = pcbnew
        self.board = board
        self.skip = set(skip_refs)
        self.entries = []                      # (ref, bbox, poly)
        for fp in board.GetFootprints():
            ref = fp.GetReference() or "(anon)"
            if ref in self.skip:
                continue
            fp.BuildCourtyardCaches()
            cy = fp.GetCourtyard(pcbnew.F_Cu)
            if cy is None or cy.OutlineCount() == 0:
                continue
            bb = cy.BBox(0)
            self.entries.append(
                (ref, (bb.GetLeft(), bb.GetTop(), bb.GetRight(),
                       bb.GetBottom()), cy))

    def overlap(self, fp, eps_mm2=0.001):
        """The footprint whose courtyard `fp` genuinely overlaps, if any.

        SHAPE_POLY_SET::Collide is true for polygons that merely touch, and on
        this board courtyards abut constantly -- the parts sit on a 5 mil grid
        with no slack, and 69 of them already overlap each other. Touching is
        not a clash; overlapping is. So the area of the intersection decides,
        not Collide alone.

        Returns (reference, area_mm2) or None."""
        pcbnew = self.pcbnew
        fp.BuildCourtyardCaches()
        cy = fp.GetCourtyard(pcbnew.F_Cu)
        if cy is None or cy.OutlineCount() == 0:
            return None
        bb = cy.BBox(0)
        l, t, r, b = bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()
        worst = None
        for ref, (ol, ot, orr, ob), other in self.entries:
            if orr < l or ol > r or ob < t or ot > b:
                continue
            try:
                if not cy.Collide(other, 0):
                    continue
                inter = pcbnew.SHAPE_POLY_SET(cy)
                inter.BooleanIntersection(other)
                area = inter.Area() / 1e12
            except Exception:
                continue
            if area > eps_mm2 and (worst is None or area > worst[1]):
                worst = (ref, round(area, 5))
        return worst


def plan_route(idx, pcbnew, board, a, b, netcode, track_w, clearance,
               hole_clearance, hole_to_hole, via_dia, via_drill, edge_box,
               ignore=(), via_reach=2.5 * IU, via_tries=6,
               allow_via_hop=True, via_scan_limit=140):
    """Work out how to connect point a to point b, without changing anything.

    Three shapes are tried, cheapest first:
      1. one straight segment on F.Cu
      2. an L on F.Cu -- both corner orders
      3. a via hop: short F.Cu stub at each end, B.Cu between them. B.Cu on
         this board carries 294 tracks against F.Cu's 897, so the back side is
         usually open where the front is not.

    Returns a plan dict; `commit_route` turns it into copper. `ok` False means
    no shape worked, and the caller should move on rather than force one."""
    def seg_ok(p, q, layer):
        return straight_ok(idx, pcbnew, board, p, q, layer, track_w, netcode,
                           clearance, hole_clearance, ignore=ignore)

    if seg_ok(a, b, pcbnew.F_Cu):
        return {"ok": True, "method": "straight", "layer": "F.Cu",
                "tracks": [(a, b, pcbnew.F_Cu)], "vias": []}

    for corner in ((a[0], b[1]), (b[0], a[1])):
        if seg_ok(a, corner, pcbnew.F_Cu) and seg_ok(corner, b, pcbnew.F_Cu):
            return {"ok": True, "method": "L on F.Cu", "layer": "F.Cu",
                    "tracks": [(a, corner, pcbnew.F_Cu),
                               (corner, b, pcbnew.F_Cu)], "vias": []}

    if not allow_via_hop:
        return {"ok": False, "reason": "no straight or L path on F.Cu"}

    # Bounded on purpose: an unbounded scan of both rings costs 276 ms a call
    # and the placement search makes thousands of them. The step is coarse so
    # that the scan limit still reaches the full radius -- at a 10 mil step the
    # cap was being hit 0.6 mm out, which is inside the ring of copper around
    # any pad and so found nothing.
    r_min = via_dia / 2.0 + clearance
    step = 20 * 0.0254 * IU
    ends = []
    for end in (a, b):
        sites = []
        for n, p in enumerate(ring_points(end[0], end[1], r_min, via_reach,
                                          step)):
            if len(sites) >= via_tries or n >= via_scan_limit:
                break
            if not via_site_ok(idx, pcbnew, p[0], p[1], netcode, via_dia,
                               via_drill, clearance, hole_to_hole,
                               hole_clearance, edge_box, ignore=ignore):
                continue
            if not seg_ok(end, p, pcbnew.F_Cu):
                continue
            sites.append(p)
        ends.append(sites)
    for v1 in ends[0]:
        for v2 in ends[1]:
            if math.hypot(v1[0] - v2[0], v1[1] - v2[1]) < \
                    via_dia + hole_to_hole:
                continue
            if seg_ok(v1, v2, pcbnew.B_Cu):
                return {"ok": True, "method": "via hop", "layer": "B.Cu",
                        "tracks": [(a, v1, pcbnew.F_Cu),
                                   (v1, v2, pcbnew.B_Cu),
                                   (v2, b, pcbnew.F_Cu)],
                        "vias": [v1, v2]}
    return {"ok": False,
            "reason": "no straight, L or via-hop path clears the other nets",
            "via_sites_at_a": len(ends[0]), "via_sites_at_b": len(ends[1])}


def commit_route(pcbnew, board, plan, netcode, track_w, via_dia, via_drill):
    if not plan.get("ok"):
        return []
    made = []
    for pos in plan.get("vias", ()):
        made.append(add_via(pcbnew, board, pos, netcode, via_dia, via_drill))
    for p, q, layer in plan.get("tracks", ()):
        made.append(add_track(pcbnew, board, p, q, layer, track_w, netcode))
    return made


def straight_ok(idx, pcbnew, board, a, b, layer, width, netcode, clearance,
                hole_clearance, ignore=()):
    """Would a straight track from a to b clear everything of another net?"""
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(int(a[0]), int(a[1])))
    t.SetEnd(pcbnew.VECTOR2I(int(b[0]), int(b[1])))
    t.SetWidth(int(width))
    t.SetLayer(layer)
    sh = t.GetEffectiveShape(layer)
    if idx.shape_conflicts(sh, layer, clearance, netcode, ignore=ignore):
        return False
    # A track may not be routed through a mechanical hole either.
    steps = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / (0.1 * IU)))
    for k in range(steps + 1):
        x = a[0] + (b[0] - a[0]) * k / float(steps)
        y = a[1] + (b[1] - a[1]) * k / float(steps)
        if idx.npth_conflicts(x, y, width / 2.0, hole_clearance, ignore=ignore):
            return False
    return True
