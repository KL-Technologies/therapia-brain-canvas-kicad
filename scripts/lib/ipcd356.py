"""IPC-D-356 netlist reader -- 80-column fixed-width ASCII, stdlib slices.

The reason this exists rather than another Gerber query: IPC-D-356 states the
net of every pad, via and hole *as data*, one record per feature, with no
graphics to interpret. ACCEPTANCE B (every pad's net matches the contract) and
half of ACCEPTANCE D (which holes are non-plated) are set-membership questions,
and this file answers them directly, from a third file format that KiCad wrote
through a different code path than the Gerbers.

Record types this board's export uses:

    317   through feature -- via or plated through-hole pad
    327   surface feature -- SMD pad
    367   unsupported hole -- NPTH, net "N/C"

Column layout, 0-based, verified against the actual export rather than assumed:

    [ 0: 3]  record type
    [ 3:17]  net name, 14 chars, "N/C" for no net
    [20:26]  reference designator ("VIA" for a via)
    [26:31]  pin, written "-<n>"
    [31]     'M' midpoint indicator
    [32]     'D' if a drill follows
    [33:37]  drill diameter, 0.0001 inch
    [37]     'P' plated / 'U' unplated
    [38]     'A' access flag
    [39:41]  access code (00 = both sides, 01 = top, 03 = bottom)
    [41]     'X'  [42] sign  [43:49] X, 0.0001 inch
    [49]     'Y'  [50] sign  [51:57] Y, 0.0001 inch
    [57]     'X'  [58:62] feature width, 0.0001 inch
    [62]     'Y'  [63:67] feature height
    [67]     'R'  [68:71] rotation, degrees
    [71]     'S'  [72]    solder mask code

**Two things to get right, both of which will silently produce wrong answers.**

Origin: the coordinates are relative to the drill/place origin, which on this
board is (120, 80) mm, and Y runs the other way. Gerber is in absolute board
coordinates with Y negated, and the board itself is in absolute with Y up. So
comparing a d356 coordinate with a Gerber one without the shift compares two
different points. `to_board()` does the conversion and `ORIGIN_MM` is checked
against the six mounting holes by scripts/62_check_fab.py.

Resolution: 0.0001 inch is 2.54 um, so this file cannot settle ACCEPTANCE D's
"within 2 um" -- that stays with the Excellon drill file, which is metric to
the micron. What this is good for is the set-level questions and a geometric
cross-check at its own resolution.
"""

MIL10 = 0.00254                      # 0.0001 inch, in mm
ORIGIN_MM = (120.0, 80.0)            # the drill/place origin, in board coords

VIA = "VIA"
NO_NET = "N/C"

TYPES = {"317": "through", "327": "smd", "367": "npth"}


class Feature(object):
    __slots__ = ("record", "kind", "net", "ref", "pin", "x_mm", "y_mm",
                 "drill_mm", "plated", "access", "w_mm", "h_mm", "rot",
                 "is_via", "line")

    def __init__(self, line):
        self.line = line.rstrip("\n")
        t = self.line
        self.record = t[0:3]
        self.kind = TYPES.get(self.record, "other")
        self.net = t[3:17].strip()
        self.ref = t[20:26].strip()
        self.pin = t[26:31].strip().lstrip("-")
        self.is_via = self.ref == VIA
        self.drill_mm = (_num(t[33:37]) * MIL10) if t[32:33] == "D" else None
        self.plated = None if t[37:38] not in ("P", "U") else t[37:38] == "P"
        self.access = t[39:41].strip()
        self.x_mm = _signed(t[42:49])
        self.y_mm = _signed(t[50:57])
        self.w_mm = _num(t[58:62]) * MIL10 if t[57:58] == "X" else None
        self.h_mm = _num(t[63:67]) * MIL10 if t[62:63] == "Y" else None
        self.rot = _num(t[68:71]) if t[67:68] == "R" else None

    def to_board(self):
        """(x, y) in the board's own frame -- what pcbnew and the Gerbers use."""
        return (ORIGIN_MM[0] + self.x_mm, ORIGIN_MM[1] - self.y_mm)

    def has_net(self):
        return bool(self.net) and self.net != NO_NET

    def __repr__(self):
        return "<%s %s %s.%s at %.4f,%.4f>" % (
            self.kind, self.net, self.ref, self.pin, self.x_mm, self.y_mm)


def _num(text):
    text = text.strip()
    return int(text) if text.isdigit() else 0


def _signed(text):
    """'+005875' -> 0.5875 inch in mm. The sign is the first character."""
    text = text.strip()
    if not text:
        return 0.0
    sign = -1.0 if text[0] == "-" else 1.0
    digits = text.lstrip("+-").strip()
    return sign * (int(digits) if digits.isdigit() else 0) * MIL10


def parse(path):
    """Every feature, plus the header lines and anything not understood."""
    features, header, unknown = [], [], []
    with open(path, "r", errors="replace") as f:
        for line in f:
            s = line.rstrip("\n")
            if not s.strip():
                continue
            if s.startswith("P "):
                header.append(s.strip())
                continue
            if s.startswith("999") or s.strip() == "999":
                continue
            if s[0:3] in TYPES:
                features.append(Feature(s))
            elif s[0:1] == "C":                    # continuation
                continue
            else:
                unknown.append(s)
    return {"path": path, "header": header, "features": features,
            "unknown": unknown}


def pad_net_map(features):
    """designator -> pad number -> set of nets, matching repair.pad_net_map.

    Vias are excluded: they are not pads and the contract has nothing to say
    about them. NPTH records are excluded too -- they are holes, and the six of
    them are the mechanical footprints the contract also leaves out.
    """
    import collections
    out = collections.defaultdict(lambda: collections.defaultdict(set))
    for f in features:
        if f.is_via or f.kind == "npth" or not f.ref:
            continue
        out[f.ref][f.pin].add(f.net if f.has_net() else "")
    return out


def npth(features):
    return [f for f in features if f.kind == "npth"]


def vias(features):
    return [f for f in features if f.is_via]


def nets(features):
    return {f.net for f in features if f.has_net()}
