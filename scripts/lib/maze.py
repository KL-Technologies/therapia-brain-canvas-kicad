"""A two-layer maze router for the L1-L5 repairs.

`lib/route.plan_route` tries three fixed shapes -- a straight, an L, and a via
hop -- which is all the ECO needed, because it was placing new parts in open
space and could move the part until one of the three fitted. The repairs cannot
do that. They have to get an existing pad out from under a mounting hole and
back to its net through whatever gap the 2026 layout left, and around the USB-C
peg holes there is no straight, no L and no two-via hop: every one of them is
blocked by the connector's own pad column on one side and the ESP32 UART pair
on the other. The path that exists is five segments long and changes layer
twice, and nothing that enumerates shapes will find it.

So: A* over a grid, on F.Cu and B.Cu, with layer changes costing a via.

    r = Router(pcbnew, board, idx, RULES)
    plan = r.route(starts=[(x, y, pcbnew.F_Cu)], net=netcode,
                   goal_net_copper=True)
    route.commit_route(pcbnew, board, plan, netcode, w, via_dia, via_drill)

The plan it returns has the same shape as `plan_route`'s, so `commit_route`
takes it unchanged.

Two things make the result trustworthy rather than plausible:

  * Legality is asked of the same predicate DRC uses. A node is open when a
    track of the routed width, centred there, collides with nothing of another
    net (SHAPE::Collide at the rule clearance), sits clear of every NPTH hole,
    and is inside the board. Zones are not obstacles -- they are refilled after
    the edit and pull back around new copper -- exactly as in lib/route.
  * The grid is a search device, not the answer. Grid legality samples points,
    so the merged path is re-checked segment by segment with
    route.straight_ok; any segment that fails has its nodes barred and the
    search runs again. A plan is returned only when every segment of it passes
    the continuous test, so "ok" means the copper is placeable, not that the
    grid thought so.

The grid pitch defaults to 0.0635 mm (2.5 mil), half the board's 5 mil design
grid and below the 0.0889 mm clearance, so a step cannot hop over an obstacle
that the two end nodes both clear.
"""

import heapq
import math

IU = 1000000
SQRT2 = math.sqrt(2.0)

# 8-way. Diagonals give 45 degree routing, which is what the rest of the board
# uses; a 4-way grid would produce staircases that no reviewer would accept.
STEPS = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
         (1, 1, SQRT2), (1, -1, SQRT2), (-1, 1, SQRT2), (-1, -1, SQRT2))


class Rules(object):
    """The design-rule numbers a route has to satisfy, in internal units."""

    def __init__(self, clearance, hole_clearance, hole_to_hole, track_width,
                 via_dia, via_drill, edge_box):
        self.clearance = int(clearance)
        self.hole_clearance = int(hole_clearance)
        self.hole_to_hole = int(hole_to_hole)
        self.track_width = int(track_width)
        self.via_dia = int(via_dia)
        self.via_drill = int(via_drill)
        self.edge_box = edge_box


class Router(object):
    def __init__(self, pcbnew, board, idx, rules, pitch=None,
                 via_cost_mm=1.2, layers=None):
        self.pcbnew = pcbnew
        self.board = board
        self.idx = idx
        self.rules = rules
        self.pitch = int(pitch if pitch else 0.0635 * IU)
        self.via_cost = int(via_cost_mm * IU)
        self.layers = list(layers) if layers else [pcbnew.F_Cu, pcbnew.B_Cu]

    # --- grid helpers ----------------------------------------------------
    def _cell(self, x, y):
        return (int(round(x / float(self.pitch))),
                int(round(y / float(self.pitch))))

    def _xy(self, ix, iy):
        return (ix * self.pitch, iy * self.pitch)

    # --- legality --------------------------------------------------------
    def _open(self, ix, iy, li, net, width, ignore_ids, cache, barred):
        """Can a track of `width` be centred on this node?"""
        k = (ix, iy, li)
        if k in barred:
            return False
        v = cache.get(k)
        if v is not None:
            return v
        x, y = self._xy(ix, iy)
        r = self.rules
        layer = self.layers[li]
        ok = True
        if r.edge_box is not None:
            lo_x, lo_y, hi_x, hi_y = r.edge_box
            half = width / 2.0
            if not (lo_x + half <= x <= hi_x - half
                    and lo_y + half <= y <= hi_y - half):
                ok = False
        if ok and self.idx.npth_conflicts(x, y, width / 2.0, r.hole_clearance,
                                          ignore=ignore_ids):
            ok = False
        if ok and self.idx.point_conflicts(x, y, layer, width / 2.0,
                                           r.clearance, net,
                                           ignore=ignore_ids):
            ok = False
        cache[k] = ok
        return ok

    def _via_open(self, ix, iy, net, ignore_ids, cache, barred):
        k = ("v", ix, iy)
        if k in barred:
            return False
        v = cache.get(k)
        if v is not None:
            return v
        x, y = self._xy(ix, iy)
        r = self.rules
        ok = True
        for li in range(len(self.layers)):
            if not self._open(ix, iy, li, net, r.via_dia, ignore_ids, cache,
                              barred):
                ok = False
                break
        if ok and self.idx.hole_conflicts(x, y, r.via_drill / 2.0,
                                          r.hole_to_hole, ignore=ignore_ids):
            ok = False
        cache[k] = ok
        return ok

    def _same_net_here(self, ix, iy, li, net, width, ignore_ids):
        """Does this node already sit on copper of its own net?"""
        x, y = self._xy(ix, iy)
        layer = self.layers[li]
        reach = int(width / 2.0)
        skip = set(ignore_ids)
        from route import uid as _uid
        for item, inet, sh in self.idx._query(layer, x - reach, y - reach,
                                              x + reach, y + reach):
            if inet != net or _uid(item) in skip:
                continue
            if sh.Collide(self.pcbnew.VECTOR2I(int(x), int(y)), reach):
                return True
        return False

    # --- the search ------------------------------------------------------
    def _astar(self, starts, goals, net, width, ignore_ids, window, barred,
               goal_net_copper, max_nodes):
        """starts/goals: sets of (ix, iy, li). Returns a node list or None."""
        lo_x, lo_y, hi_x, hi_y = window
        min_ix, min_iy = self._cell(lo_x, lo_y)
        max_ix, max_iy = self._cell(hi_x, hi_y)
        cache = {}

        goal_cells = set(goals)

        def h(n):
            if not goal_cells:
                return 0
            x, y = self._xy(n[0], n[1])
            best = None
            for g in goal_cells:
                gx, gy = self._xy(g[0], g[1])
                d = math.hypot(x - gx, y - gy)
                if best is None or d < best:
                    best = d
            return best

        def is_goal(n):
            if n in goal_cells:
                return True
            if goal_net_copper and self._same_net_here(n[0], n[1], n[2], net,
                                                       width, ignore_ids):
                return True
            return False

        openq = []
        gscore = {}
        came = {}
        for s in starts:
            if not (min_ix <= s[0] <= max_ix and min_iy <= s[1] <= max_iy):
                continue
            gscore[s] = 0
            heapq.heappush(openq, (h(s), 0, s))
        visited = 0
        while openq:
            _f, g, n = heapq.heappop(openq)
            if g > gscore.get(n, g):
                continue
            visited += 1
            if visited > max_nodes:
                return None
            if is_goal(n) and n not in starts:
                path = [n]
                while path[-1] in came:
                    path.append(came[path[-1]])
                path.reverse()
                return path
            ix, iy, li = n
            for dx, dy, cost in STEPS:
                nx, ny = ix + dx, iy + dy
                if not (min_ix <= nx <= max_ix and min_iy <= ny <= max_iy):
                    continue
                m = (nx, ny, li)
                ng = g + int(cost * self.pitch)
                if ng >= gscore.get(m, ng + 1):
                    continue
                if not self._open(nx, ny, li, net, width, ignore_ids, cache,
                                  barred):
                    continue
                gscore[m] = ng
                came[m] = n
                heapq.heappush(openq, (ng + h(m), ng, m))
            # layer change
            for lj in range(len(self.layers)):
                if lj == li:
                    continue
                m = (ix, iy, lj)
                ng = g + self.via_cost
                if ng >= gscore.get(m, ng + 1):
                    continue
                if not self._via_open(ix, iy, net, ignore_ids, cache, barred):
                    continue
                if not self._open(ix, iy, lj, net, width, ignore_ids, cache,
                                  barred):
                    continue
                gscore[m] = ng
                came[m] = n
                heapq.heappush(openq, (ng + h(m), ng, m))
        return None

    # --- path -> plan ----------------------------------------------------
    def _to_plan(self, path, tail_points):
        """Merge collinear grid steps into segments and collect the vias."""
        tracks, vias = [], []
        run = [path[0]]
        for n in path[1:]:
            if n[2] != run[-1][2]:                       # layer change = via
                tracks += self._emit(run)
                vias.append(self._xy(n[0], n[1]))
                run = [n]
                continue
            run.append(n)
        tracks += self._emit(run)
        for a, b, layer in tail_points:
            tracks.append((a, b, layer))
        return {"ok": True, "method": "maze", "tracks": tracks, "vias": vias}

    def _emit(self, run):
        if len(run) < 2:
            return []
        layer = self.layers[run[0][2]]
        out = []
        a = run[0]
        d = (run[1][0] - run[0][0], run[1][1] - run[0][1])
        for i in range(1, len(run)):
            if i + 1 < len(run):
                e = (run[i + 1][0] - run[i][0], run[i + 1][1] - run[i][1])
                if e == d:
                    continue
                d = e
            out.append((self._xy(a[0], a[1]), self._xy(run[i][0], run[i][1]),
                        layer))
            a = run[i]
        return out

    # --- public ----------------------------------------------------------
    def route(self, starts, net, goals=(), goal_net_copper=False, width=None,
              ignore=(), window=None, margin_mm=3.0, max_nodes=250000,
              verify_passes=4):
        """Route from `starts` to `goals` (and/or to any copper of `net`).

        starts/goals are (x, y, layer) in internal units. The first and last
        grid node are joined back to the exact given points with a short
        segment, so the route lands on the pad centre rather than on the grid.

        Returns a plan dict for route.commit_route, or {"ok": False, ...}.
        """
        import route as R
        width = int(width if width else self.rules.track_width)
        ignore_ids = list(ignore)
        li_of = {l: i for i, l in enumerate(self.layers)}

        start_nodes, start_tails = [], {}
        for (x, y, layer) in starts:
            if layer not in li_of:
                continue
            ix, iy = self._cell(x, y)
            n = (ix, iy, li_of[layer])
            start_nodes.append(n)
            start_tails[n] = (x, y, layer)
        goal_nodes, goal_tails = [], {}
        for (x, y, layer) in goals:
            if layer not in li_of:
                continue
            ix, iy = self._cell(x, y)
            n = (ix, iy, li_of[layer])
            goal_nodes.append(n)
            goal_tails[n] = (x, y, layer)
        if not start_nodes:
            return {"ok": False, "reason": "no start node on a routed layer"}

        if window is None:
            xs = [p[0] for p in starts] + [p[0] for p in goals]
            ys = [p[1] for p in starts] + [p[1] for p in goals]
            if goal_net_copper:
                for item in self.idx.tracks + self.idx.pads:
                    if item.GetNetCode() != net:
                        continue
                    bb = item.GetBoundingBox()
                    xs += [bb.GetLeft(), bb.GetRight()]
                    ys += [bb.GetTop(), bb.GetBottom()]
            m = int(margin_mm * IU)
            window = (min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m)
            if self.rules.edge_box is not None:
                e = self.rules.edge_box
                window = (max(window[0], e[0]), max(window[1], e[1]),
                          min(window[2], e[2]), min(window[3], e[3]))

        barred = set()
        tried = []
        for _p in range(verify_passes):
            path = self._astar(start_nodes, goal_nodes, net, width, ignore_ids,
                               window, barred, goal_net_copper, max_nodes)
            if path is None:
                return {"ok": False, "reason": "no path on the grid",
                        "verify_failures": tried,
                        "window_mm": [round(v / float(IU), 3) for v in window]}
            tails = []
            head = start_tails.get(path[0])
            if head:
                p = self._xy(path[0][0], path[0][1])
                if head[0] != p[0] or head[1] != p[1]:
                    tails.append(((head[0], head[1]), p, head[2]))
            foot = goal_tails.get(path[-1])
            if foot:
                p = self._xy(path[-1][0], path[-1][1])
                if foot[0] != p[0] or foot[1] != p[1]:
                    tails.append((p, (foot[0], foot[1]), foot[2]))
            plan = self._to_plan(path, tails)

            bad = None
            for (a, b, layer) in plan["tracks"]:
                if a == b:
                    continue
                if not R.straight_ok(self.idx, self.pcbnew, self.board, a, b,
                                     layer, width, net, self.rules.clearance,
                                     self.rules.hole_clearance,
                                     ignore=ignore_ids):
                    bad = (a, b, layer)
                    break
            if bad is None:
                plan["length_mm"] = round(sum(
                    math.hypot(b[0] - a[0], b[1] - a[1])
                    for a, b, _l in plan["tracks"]) / float(IU), 4)
                return plan
            tried.append({"segment_mm": [round(bad[0][0] / float(IU), 4),
                                         round(bad[0][1] / float(IU), 4),
                                         round(bad[1][0] / float(IU), 4),
                                         round(bad[1][1] / float(IU), 4)]})
            # Bar the grid nodes the failing segment passed through and search
            # again: the point test cleared them but the swept track does not.
            li = li_of[bad[2]]
            n = max(2, int(math.hypot(bad[1][0] - bad[0][0],
                                      bad[1][1] - bad[0][1]) / self.pitch))
            for k in range(n + 1):
                x = bad[0][0] + (bad[1][0] - bad[0][0]) * k / float(n)
                y = bad[0][1] + (bad[1][1] - bad[0][1]) * k / float(n)
                ix, iy = self._cell(x, y)
                barred.add((ix, iy, li))
        return {"ok": False, "reason": "every path found failed the continuous "
                                       "clearance check",
                "verify_failures": tried}
