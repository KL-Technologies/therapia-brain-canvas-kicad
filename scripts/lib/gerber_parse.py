"""A second opinion on the manufacturing data: RS-274X and Excellon, by hand.

ACCEPTANCE E asks for the Gerbers to be checked by a parser of our own rather
than by handing them back to KiCad, and ACCEPTANCE D asks the "no copper inside
the mounting holes" rule to be settled from the Gerbers rather than from
pcbnew's DRC. Reading the files back with the tool that wrote them proves only
that it is self-consistent; this module is deliberately a different reader.

Scope is what this board's export actually contains, checked rather than
assumed (scripts/62_check_fab.py reports anything outside it):

  apertures   C, R, O, P and the RoundRect macro KiCad emits
  operations  D01/D02/D03, G01 linear, G02/G03 circular with G75, G36/G37
              regions, LPD/LPC polarity
  format      %FSLAX46Y46%, %MOMM%, absolute, leading zeros omitted

An unknown aperture macro degrades to its bounding circle. That is the safe
direction for the one test that must not be wrong: a hole-clearance check that
over-estimates copper can raise a false alarm, never give a false pass.

Coordinates come out in millimetres, in the Gerber's own frame -- which for a
KiCad export is the board frame with Y negated.

Standard library only.
"""

import math
import re

ARC_SEGMENTS = 24


# --- apertures ---------------------------------------------------------------
class Aperture(object):
    def __init__(self, code, kind, params, macro_body=None):
        self.code = code
        self.kind = kind                 # 'C' 'R' 'O' 'P' or a macro name
        self.params = params
        self.macro_body = macro_body
        self.known = kind in ("C", "R", "O", "P") or kind == "RoundRect"

    # Half-extents of the axis-aligned bounding box, in mm.
    def half(self):
        p = self.params
        if self.kind == "C":
            return p[0] / 2.0, p[0] / 2.0
        if self.kind in ("R", "O"):
            return p[0] / 2.0, p[1] / 2.0
        if self.kind == "P":
            return p[0] / 2.0, p[0] / 2.0
        if self.kind == "RoundRect" and len(p) >= 9:
            r = p[0]
            xs = [p[i] for i in (1, 3, 5, 7)]
            ys = [p[i] for i in (2, 4, 6, 8)]
            return max(map(abs, xs)) + r, max(map(abs, ys)) + r
        # Unknown macro: a circle big enough to contain anything it names.
        m = max([abs(v) for v in p] or [0.0])
        return m, m

    def outer_radius(self):
        hx, hy = self.half()
        return math.hypot(hx, hy)

    def distance_to(self, dx, dy):
        """Distance from a point at offset (dx, dy) to this aperture's edge.

        Negative inside. Used to decide whether copper reaches into a circle,
        so it has to be a real distance, not a bounding-box test.
        """
        p = self.params
        if self.kind == "C":
            return math.hypot(dx, dy) - p[0] / 2.0
        if self.kind == "R":
            return _box_distance(dx, dy, p[0] / 2.0, p[1] / 2.0)
        if self.kind == "O":
            w, h = p[0], p[1]
            if w >= h:                    # horizontal stadium
                r = h / 2.0
                return _segment_distance(dx, dy, -(w / 2.0 - r), 0.0,
                                         (w / 2.0 - r), 0.0) - r
            r = w / 2.0
            return _segment_distance(dx, dy, 0.0, -(h / 2.0 - r),
                                     0.0, (h / 2.0 - r)) - r
        if self.kind == "P":
            return math.hypot(dx, dy) - p[0] / 2.0      # circumscribed
        if self.kind == "RoundRect" and len(p) >= 9:
            r = p[0]
            pts = [(p[1], p[2]), (p[3], p[4]), (p[5], p[6]), (p[7], p[8])]
            return _polygon_distance(dx, dy, pts) - r
        return math.hypot(dx, dy) - self.outer_radius()


def _box_distance(px, py, hx, hy):
    dx = abs(px) - hx
    dy = abs(py) - hy
    if dx <= 0 and dy <= 0:
        return max(dx, dy)
    return math.hypot(max(dx, 0.0), max(dy, 0.0))


def _segment_distance(px, py, x1, y1, x2, y2):
    vx, vy = x2 - x1, y2 - y1
    L = vx * vx + vy * vy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x1) * vx +
                                              (py - y1) * vy) / L))
    return math.hypot(px - (x1 + t * vx), py - (y1 + t * vy))


def _point_in_polygon(px, py, pts):
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (y1 > py) != (y2 > py):
            xin = x1 + (py - y1) * (x2 - x1) / float(y2 - y1)
            if px < xin:
                inside = not inside
    return inside


def _polygon_distance(px, py, pts):
    d = min(_segment_distance(px, py, pts[i][0], pts[i][1],
                              pts[(i + 1) % len(pts)][0],
                              pts[(i + 1) % len(pts)][1])
            for i in range(len(pts)))
    return -d if _point_in_polygon(px, py, pts) else d


# --- the layer ---------------------------------------------------------------
class Layer(object):
    def __init__(self, path):
        self.path = path
        self.unit = None
        self.int_digits = None
        self.dec_digits = None
        self.apertures = {}
        self.macros = {}
        # Each primitive carries the polarity in force when it was emitted.
        # --subtract-soldermask makes KiCad emit %LPC% clear regions that erase
        # silkscreen where the mask opens; counting those as painted would
        # report 22 shapes on a bottom silkscreen that is in fact blank.
        self.flashes = []                # (x, y, aperture, dark)
        self.draws = []                  # (x1, y1, x2, y2, aperture, dark)
        self.regions = []                # ([(x, y), ...], dark)
        self.file_function = None
        self.polarity = "D"
        self.clear_ops = 0
        self.unknown = []
        self._grid = None

    # -- geometry queries ----------------------------------------------------
    def dark(self):
        return ([f for f in self.flashes if f[3]],
                [d for d in self.draws if d[5]],
                [r for r in self.regions if r[1]])

    def counts(self):
        f, d, r = self.dark()
        return {"flashes": len(f), "draws": len(d), "regions": len(r),
                "clear_flashes": len(self.flashes) - len(f),
                "clear_draws": len(self.draws) - len(d),
                "clear_regions": len(self.regions) - len(r)}

    def bbox(self):
        xs, ys = [], []
        for x, y, ap, dk in self.flashes:
            if not dk:
                continue
            hx, hy = ap.half()
            xs += [x - hx, x + hx]
            ys += [y - hy, y + hy]
        for x1, y1, x2, y2, ap, dk in self.draws:
            if not dk:
                continue
            hx, hy = ap.half()
            xs += [x1 - hx, x1 + hx, x2 - hx, x2 + hx]
            ys += [y1 - hy, y1 + hy, y2 - hy, y2 + hy]
        for poly, dk in self.regions:
            if not dk:
                continue
            xs += [p[0] for p in poly]
            ys += [p[1] for p in poly]
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    def centreline_bbox(self):
        """The bbox of the path centres, ignoring stroke width.

        The board outline is a 0.1 mm pen tracing the profile, so its painted
        bbox is one pen width larger than the board. ACCEPTANCE E's 61.8236 x
        45.0088 mm is the profile itself, which is the centreline.
        """
        xs, ys = [], []
        for x1, y1, x2, y2, _ap, dk in self.draws:
            if not dk:
                continue
            xs += [x1, x2]
            ys += [y1, y2]
        for poly, dk in self.regions:
            if not dk:
                continue
            xs += [p[0] for p in poly]
            ys += [p[1] for p in poly]
        if not xs:
            return None
        return (min(xs), min(ys), max(xs), max(ys))

    def _build_grid(self, cell=2.0):
        """Bucket every primitive so a disc query does not scan the layer."""
        grid = {}
        def put(key, item, x0, y0, x1, y1):
            for gx in range(int(math.floor(x0 / cell)),
                            int(math.floor(x1 / cell)) + 1):
                for gy in range(int(math.floor(y0 / cell)),
                                int(math.floor(y1 / cell)) + 1):
                    grid.setdefault((gx, gy), []).append((key, item))
        flashes, draws, regions = self.dark()
        for f in flashes:
            hx, hy = f[2].half()
            put("f", f, f[0] - hx, f[1] - hy, f[0] + hx, f[1] + hy)
        for d in draws:
            hx, hy = d[4].half()
            put("d", d, min(d[0], d[2]) - hx, min(d[1], d[3]) - hy,
                max(d[0], d[2]) + hx, max(d[1], d[3]) + hy)
        for poly, _dk in regions:
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            put("r", poly, min(xs), min(ys), max(xs), max(ys))
        self._grid = (cell, grid)
        return self._grid

    def _near(self, x, y, r):
        cell, grid = self._grid or self._build_grid()
        out = []
        for gx in range(int(math.floor((x - r) / cell)),
                        int(math.floor((x + r) / cell)) + 1):
            for gy in range(int(math.floor((y - r) / cell)),
                            int(math.floor((y + r) / cell)) + 1):
                out += grid.get((gx, gy), ())
        return out

    def copper_within(self, cx, cy, r):
        """Everything on this layer that reaches inside the circle (cx, cy, r).

        This is the ACCEPTANCE D test. It answers with the offending primitives
        rather than a boolean so a failure can be pointed at.
        """
        hits = []
        for kind, item in self._near(cx, cy, r):
            if kind == "f":
                x, y, ap, _dk = item
                if ap.distance_to(cx - x, cy - y) < r:
                    hits.append({"kind": "flash", "at": [x, y],
                                 "aperture": ap.code,
                                 "gap_mm": round(ap.distance_to(cx - x,
                                                                cy - y), 6)})
            elif kind == "d":
                x1, y1, x2, y2, ap, _dk = item
                w = ap.params[0] if ap.kind == "C" else max(ap.half()) * 2
                d = _segment_distance(cx, cy, x1, y1, x2, y2) - w / 2.0
                if d < r:
                    hits.append({"kind": "draw", "from": [x1, y1],
                                 "to": [x2, y2], "aperture": ap.code,
                                 "gap_mm": round(d, 6)})
            else:
                d = _polygon_distance(cx, cy, item)
                if d < r:
                    hits.append({"kind": "region", "vertices": len(item),
                                 "gap_mm": round(d, 6)})
        return hits

    def coverage(self, box, step=0.25):
        """Fraction of `box` this layer paints, by sampling on a grid.

        A copper area computed from the polygons would have to resolve the
        overlaps between fills, flashes and strokes. Sampling sidesteps that and
        is accurate enough for the question being asked, which is whether a
        plane filled at all.
        """
        x0, y0, x1, y1 = box
        nx = max(1, int((x1 - x0) / step))
        ny = max(1, int((y1 - y0) / step))
        hit = 0
        for i in range(nx):
            px = x0 + (i + 0.5) * (x1 - x0) / nx
            for j in range(ny):
                py = y0 + (j + 0.5) * (y1 - y0) / ny
                if self._painted(px, py):
                    hit += 1
        return hit / float(nx * ny)

    def _painted(self, x, y):
        for kind, item in self._near(x, y, 0.0):
            if kind == "r":
                if _point_in_polygon(x, y, item):
                    return True
            elif kind == "f":
                fx, fy, ap, _dk = item
                if ap.distance_to(x - fx, y - fy) <= 0:
                    return True
            else:
                x1, y1, x2, y2, ap, _dk = item
                w = ap.params[0] if ap.kind == "C" else max(ap.half()) * 2
                if _segment_distance(x, y, x1, y1, x2, y2) <= w / 2.0:
                    return True
        return False


# --- the reader --------------------------------------------------------------
_FS = re.compile(r"^FSLAX(\d)(\d)Y(\d)(\d)$")
_AD = re.compile(r"^ADD(\d+)([A-Za-z_$][A-Za-z0-9_$.\-]*),?(.*)$")
_COORD = re.compile(r"([XYIJ])(-?\d+)")


def parse_gerber(path):
    with open(path, "r", errors="replace") as f:
        text = f.read()
    lay = Layer(path)
    scale = 1.0
    x = y = 0.0
    interp = 1                            # 1 linear, 2 CW, 3 CCW
    quadrant = "multi"
    cur = None
    region = None
    contour = []
    in_macro = None
    macro_lines = []

    for raw in _statements(text):
        s = raw.strip()
        if not s or s.startswith("G04"):
            continue

        if in_macro is not None:
            if s.endswith("%"):
                macro_lines.append(s[:-1])
                lay.macros[in_macro] = macro_lines
                in_macro = None
            else:
                macro_lines.append(s)
            continue

        if s.startswith("%"):
            body = s.strip("%")
            if body.startswith("AM"):
                in_macro = body[2:].split("*")[0]
                macro_lines = []
                continue
            for part in body.split("*"):
                part = part.strip()
                if not part:
                    continue
                m = _FS.match(part)
                if m:
                    lay.int_digits = int(m.group(1))
                    lay.dec_digits = int(m.group(2))
                    scale = 10.0 ** -lay.dec_digits
                    continue
                if part.startswith("MO"):
                    lay.unit = part[2:]
                    continue
                if part.startswith("TF.FileFunction"):
                    lay.file_function = part.split(",", 1)[1]
                    continue
                if part.startswith("LP"):
                    lay.polarity = part[2:]
                    if lay.polarity == "C":
                        lay.clear_ops += 1
                    continue
                m = _AD.match(part)
                if m:
                    code = int(m.group(1))
                    kind = m.group(2)
                    args = [float(v) for v in m.group(3).split("X")
                            if v.strip()] if m.group(3) else []
                    ap = Aperture(code, kind, args,
                                  lay.macros.get(kind))
                    lay.apertures[code] = ap
                    if not ap.known:
                        lay.unknown.append(part)
            continue

        # non-extended: G-codes, D-codes, coordinates
        for gm in re.findall(r"G(\d+)", s):
            g = int(gm)
            if g in (1, 2, 3):
                interp = g
            elif g == 36:
                region = []
                contour = []
            elif g == 37:
                if contour:
                    region.append(contour)
                for c in region or ():
                    if len(c) >= 3:
                        lay.regions.append((c, lay.polarity != "C"))
                region, contour = None, []
            elif g == 74:
                quadrant = "single"
            elif g == 75:
                quadrant = "multi"

        dm = re.search(r"D(\d+)\*?$", s)
        coords = dict((k, int(v) * scale) for k, v in _COORD.findall(s))
        nx = coords.get("X", x)
        ny = coords.get("Y", y)
        if dm is None:
            if coords:
                x, y = nx, ny
            continue
        d = int(dm.group(1))
        if d >= 10:
            cur = lay.apertures.get(d)
            if coords:
                x, y = nx, ny
            continue
        if d == 2:                                   # move
            if region is not None:
                if contour and len(contour) >= 3:
                    region.append(contour)
                contour = [(nx, ny)]
            x, y = nx, ny
        elif d == 1:                                 # draw
            pts = [(nx, ny)]
            if interp in (2, 3):
                pts = _arc(x, y, nx, ny, coords.get("I", 0.0),
                           coords.get("J", 0.0), interp, quadrant)
            if region is not None:
                contour += pts
            else:
                px, py = x, y
                for qx, qy in pts:
                    if cur is not None:
                        lay.draws.append((px, py, qx, qy, cur,
                                          lay.polarity != "C"))
                    px, py = qx, qy
            x, y = nx, ny
        elif d == 3:                                 # flash
            if cur is not None:
                lay.flashes.append((nx, ny, cur, lay.polarity != "C"))
            x, y = nx, ny
    return lay


def _statements(text):
    """Split into statements, keeping %...% blocks whole."""
    out = []
    buf = ""
    in_ext = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if in_ext:
            buf += line
            if line.endswith("%"):
                out.append(buf)
                buf, in_ext = "", False
            continue
        if line.startswith("%") and not line.endswith("%"):
            buf, in_ext = line, True
            continue
        out.append(line)
    if buf:
        out.append(buf)
    return out


def _arc(x0, y0, x1, y1, i, j, interp, quadrant):
    cx, cy = x0 + i, y0 + j
    r0 = math.hypot(x0 - cx, y0 - cy)
    a0 = math.atan2(y0 - cy, x0 - cx)
    a1 = math.atan2(y1 - cy, x1 - cx)
    if interp == 2:                                  # clockwise
        while a1 > a0:
            a1 -= 2 * math.pi
    else:
        while a1 < a0:
            a1 += 2 * math.pi
    if quadrant == "multi" and abs(a1 - a0) < 1e-9 and \
            math.hypot(x1 - x0, y1 - y0) < 1e-9:
        a1 = a0 + (2 * math.pi if interp == 3 else -2 * math.pi)
    pts = []
    for k in range(1, ARC_SEGMENTS + 1):
        a = a0 + (a1 - a0) * k / float(ARC_SEGMENTS)
        pts.append((cx + r0 * math.cos(a), cy + r0 * math.sin(a)))
    pts[-1] = (x1, y1)
    return pts


# --- Excellon ----------------------------------------------------------------
def parse_excellon(path):
    """Tools and hits. Returns {'metric':bool, 'tools':{n:dia}, 'hits':[...]}"""
    with open(path, "r", errors="replace") as f:
        lines = [l.strip() for l in f if l.strip()]
    tools = {}
    hits = []
    metric = True
    decimal = True
    in_header = False
    cur = None
    fmt_int, fmt_dec = 3, 3
    for line in lines:
        if line == "M48":
            in_header = True
            continue
        if line == "%":
            in_header = False
            continue
        if line.startswith(";"):
            if "FORMAT" in line and "decimal" not in line:
                decimal = False
            continue
        if line in ("METRIC", "M71"):
            metric = True
            continue
        if line in ("INCH", "M72"):
            metric = False
            fmt_int, fmt_dec = 2, 4
            continue
        m = re.match(r"^T(\d+)C([\d.]+)", line)
        if m:
            tools[int(m.group(1))] = float(m.group(2))
            continue
        m = re.match(r"^T(\d+)$", line)
        if m and not in_header:
            cur = int(m.group(1))
            continue
        if line.startswith("X") or line.startswith("Y"):
            got = re.findall(r"([XY])(-?[\d.]+)", line)
            slot = "G85" in line
            vals = []
            for _k, v in got:
                vals.append(float(v) if decimal
                            else int(v) / 10.0 ** fmt_dec)
            pairs = [vals[i:i + 2] for i in range(0, len(vals), 2)]
            for p in pairs:
                if len(p) == 2:
                    hits.append({"tool": cur, "dia": tools.get(cur),
                                 "x": p[0], "y": p[1], "slot": slot})
    return {"metric": metric, "decimal": decimal, "tools": tools,
            "hits": hits, "path": path}
