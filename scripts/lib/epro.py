"""EasyEDA Pro (.epro) archive parsing + patching helpers.

Format reference:
  https://dev-docs.kicad.org/en/import-formats/easyeda/index.html
Patch technique transcribed from (not depended on):
  https://github.com/enkhbold470/epro2kicad

Standard library only. Must import under both system python3 (3.9.6) and the
KiCad-bundled python3 (3.9.13).
"""

import hashlib
import json
import os
import re
import zipfile

MIL_TO_MM = 0.0254

# --- expected values for Brain Canvas Rev.A (independent reference data) ------
# Source: team brief + cerelog_research/11_rev_a_eco_2026-08-16.md
EXPECTED_FOOTPRINT_COUNT = 131
EXPECTED_OUTLINE_MM = (61.8236, 45.0088)  # 2434 x 1772 mil
EXPECTED_ROTATIONS = {0.0, 90.0, 180.0, 270.0}

# (name, x_mm, y_mm, diameter_mm) -- EasyEDA coordinates, y negative downward
EXPECTED_NPTH = [
    ("PEG1", 56.861075, -33.877885, 0.700),
    ("PEG2", 56.861075, -28.097861, 0.700),
    ("M2_NW", 3.048, -3.048, 2.3876),
    ("M2_NE", 56.9468, -3.048, 2.3876),
    ("M2_SW", 3.048, -41.9608, 2.3876),
    ("M2_SE", 56.9468, -41.9608, 2.3876),
]

# --- EasyEDA Pro -> KiCad layer mapping (dev-docs table) ---------------------
LAYER_MAP = {
    1: "F.Cu", 2: "B.Cu", 3: "F.SilkS", 4: "B.SilkS",
    5: "F.Mask", 6: "B.Mask", 7: "F.Paste", 8: "B.Paste",
    9: "F.Fab", 10: "B.Fab", 11: "Edge.Cuts", 12: "Multi(Edge.Cuts)",
    13: "Dwgs.User", 14: "Eco2.User",
    48: "F.Fab(compShape)", 49: "F.Fab(compMarking)",
    53: "User.4", 54: "User.5", 55: "User.6", 56: "User.7",
}
for _i in range(15, 45):
    LAYER_MAP[_i] = "In%d.Cu" % (_i - 14)


def layer_name(lid):
    try:
        lid = int(lid)
    except (TypeError, ValueError):
        return "layer:%r" % (lid,)
    return LAYER_MAP.get(lid, "layer:%d" % lid)


# --- patch constants (epro2kicad) -------------------------------------------
# record type -> index of the net-name field inside an .epcb record
EPCB_NET_FIELD = {
    "VIA": 3, "LINE": 3, "ARC": 3, "POLY": 3, "FILL": 3, "POUR": 3,
    "PAD": 3, "PAD_NET": 3, "TEARDROP": 2,
}
EPCB_HEADER_TYPES = ("DOCTYPE", "HEAD", "CANVAS", "LAYER", "ACTIVE_LAYER", "RULE")

DOC_SUFFIXES = (".esch", ".epcb", ".esym", ".efoo", ".ecop")
TEXT_SUFFIXES = DOC_SUFFIXES + (".json",)


# --- generic helpers ---------------------------------------------------------
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def mil2mm(v):
    return round(float(v) * MIL_TO_MM, 6)


def approx(a, b, tol):
    return abs(float(a) - float(b)) <= tol


def parse_jsonl(text):
    """Parse a JSON-Lines document. Returns (records, errors).

    Blank lines are section separators and are preserved as the sentinel None so
    callers that care (.efoo) can split on them.
    """
    records, errors = [], []
    for lineno, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            records.append(None)
            continue
        try:
            records.append(json.loads(s))
        except ValueError as exc:
            errors.append({"line": lineno, "error": str(exc), "text": s[:200]})
    return records, errors


def rtype(rec):
    if isinstance(rec, list) and rec and isinstance(rec[0], str):
        return rec[0]
    return None


def get(rec, idx, default=None):
    if isinstance(rec, list) and -len(rec) <= idx < len(rec):
        return rec[idx]
    return default


def attr_kv(rec):
    """Return (key, value) from an ATTR record, tolerating layout drift.

    PCB ATTR: ["ATTR", id, unk, parentId, layer, x, y, key, value, ...]
    SCH ATTR: ["ATTR", id, parentId, key, value, ...]
    Both are handled by trying the documented indices and then falling back to a
    scan for a known attribute key.
    """
    known = ("Designator", "Name", "Value", "Device", "Manufacturer Part",
             "Supplier Part", "Footprint", "Symbol", "Unique ID", "Comment")
    for ki in (7, 3):
        k = get(rec, ki)
        if isinstance(k, str) and k in known:
            return k, get(rec, ki + 1)
    for i, v in enumerate(rec if isinstance(rec, list) else []):
        if isinstance(v, str) and v in known:
            return v, get(rec, i + 1)
    # last resort: first string that looks like a key followed by a value
    for ki in (7, 3):
        k = get(rec, ki)
        if isinstance(k, str):
            return k, get(rec, ki + 1)
    return None, None


def attr_parent(rec):
    """Parent primitive id referenced by an ATTR record."""
    for ki in (7, 3):
        k = get(rec, ki)
        if isinstance(k, str):
            pi = 3 if ki == 7 else 2
            p = get(rec, pi)
            if isinstance(p, str):
                return p
    return None


# --- archive -----------------------------------------------------------------
class Epro(object):
    """Read-only view of an .epro / .epro2 / .eprj zip archive."""

    def __init__(self, path):
        self.path = path
        self.zf = zipfile.ZipFile(path)
        self.names = [n for n in self.zf.namelist() if not n.endswith("/")]

    def close(self):
        self.zf.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def read_text(self, name):
        return self.zf.read(name).decode("utf-8", errors="replace")

    def by_suffix(self, suffix):
        return [n for n in self.names if n.lower().endswith(suffix)]

    def project(self):
        for n in self.names:
            if os.path.basename(n) == "project.json":
                try:
                    return json.loads(self.read_text(n))
                except ValueError:
                    return {}
        return {}

    def pcb_documents(self):
        return self.by_suffix(".epcb")

    def schematic_documents(self):
        return self.by_suffix(".esch")

    def footprint_documents(self):
        return self.by_suffix(".efoo")

    def symbol_documents(self):
        return self.by_suffix(".esym")

    def inventory_files(self):
        out = []
        for n in self.names:
            info = self.zf.getinfo(n)
            out.append({"name": n, "size": info.file_size,
                        "crlf": b"\r\n" in self.zf.read(n)[:1 << 20]})
        return out


# --- patching ----------------------------------------------------------------
def flatten_rules(records):
    """KiCad issue #24303: EasyEDA >=2.2 nests rule payloads one level deeper,
    which trips the schema check ("type must be number, but is array").

    RULE layout: ["RULE", ruleType, ruleName, isDefault, ruleData]
    """
    n = 0
    for rec in records:
        if rtype(rec) != "RULE":
            continue
        data = get(rec, 4)
        if not (isinstance(data, list) and len(data) > 1 and isinstance(data[1], dict)):
            continue
        sub = next(iter(data[1].values()), None)
        if sub is None:
            continue
        if rec[1] == "1":            # clearance matrix -> table at index 1
            rec[4] = [data[0], sub]
            n += 1
        elif rec[1] == "3":          # track width -> [units, min, opt, max]
            rec[4] = [data[0], sub] if not isinstance(sub, list) else [data[0]] + list(sub)
            n += 1
    return n


def inject_nets(records):
    """KiCad issue #19021: newer exports drop the leading NET records, after
    which every pad/track lands on one merged net. Re-declare every net name
    referenced by a primitive, inserted right after the header run."""
    seen = set()
    for rec in records:
        if rtype(rec) == "NET":
            v = get(rec, 1)
            if isinstance(v, str):
                seen.add(v)
    declared_before = len(seen)

    missing = []
    for rec in records:
        idx = EPCB_NET_FIELD.get(rtype(rec))
        if idx is None:
            continue
        v = get(rec, idx)
        if isinstance(v, str) and v and v not in seen:
            seen.add(v)
            missing.append(v)

    if missing:
        split = 0
        while split < len(records) and rtype(records[split]) in EPCB_HEADER_TYPES:
            split += 1
        records[split:split] = [["NET", n] for n in missing]
    return {"declared_before": declared_before, "injected": len(missing),
            "injected_names": missing}


def fix_epcb_text(text, do_flatten=True, do_inject=True):
    """Apply the .epcb patches. Returns (new_text, report)."""
    recs = [json.loads(l) for l in text.splitlines() if l.strip()]
    report = {"records": len(recs), "rules_flattened": 0}
    if do_flatten:
        report["rules_flattened"] = flatten_rules(recs)
    if do_inject:
        report["nets"] = inject_nets(recs)
    out = "\n".join(json.dumps(r, separators=(",", ":"), ensure_ascii=False)
                    for r in recs)
    return out, report


def patch_epro(src, dst, newlines=True, do_flatten=True, do_inject=True):
    """Repack an .epro applying the selected patch stages. Idempotent."""
    report = {"stages": {"newlines": bool(newlines), "flatten_rules": bool(do_flatten),
                         "inject_nets": bool(do_inject)},
              "documents": {}}
    with zipfile.ZipFile(src) as zin, \
            zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            low = item.filename.lower()
            if low.endswith(TEXT_SUFFIXES):
                text = data.decode("utf-8", errors="replace")
                if newlines:
                    text = "\n".join(text.splitlines())
                if low.endswith(".epcb") and (do_flatten or do_inject):
                    text, rep = fix_epcb_text(text, do_flatten, do_inject)
                    report["documents"][item.filename] = rep
                data = text.encode("utf-8")
            zi = zipfile.ZipInfo(item.filename, date_time=item.date_time)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = item.external_attr
            zout.writestr(zi, data)
    return report


# --- Pro polygon decoding ----------------------------------------------------
_NUM = (int, float)


def poly_points(data):
    """Decode an EasyEDA Pro polygon path into a list of (x, y) plus a list of
    primitive shapes (circles / rects) that carry their own geometry.

    Commands: L x y..., ARC/CARC angle x y, C cx1 cy1 cx2 cy2 x y,
              CIRCLE cx cy r, R x y w h angle [r]
    """
    pts, shapes = [], []
    if not isinstance(data, list):
        return pts, shapes
    i, cur = 0, None
    while i < len(data):
        tok = data[i]
        if isinstance(tok, _NUM):
            if i + 1 < len(data) and isinstance(data[i + 1], _NUM):
                cur = (float(tok), float(data[i + 1]))
                pts.append(cur)
                i += 2
                continue
            i += 1
            continue
        if not isinstance(tok, str):
            i += 1
            continue
        cmd = tok.upper()
        if cmd == "L":
            i += 1
            while i + 1 < len(data) and isinstance(data[i], _NUM) and isinstance(data[i + 1], _NUM):
                cur = (float(data[i]), float(data[i + 1]))
                pts.append(cur)
                i += 2
        elif cmd in ("ARC", "CARC"):
            if i + 3 < len(data):
                cur = (float(data[i + 2]), float(data[i + 3]))
                pts.append(cur)
            i += 4
        elif cmd == "C":
            if i + 6 < len(data):
                cur = (float(data[i + 5]), float(data[i + 6]))
                pts.append(cur)
            i += 7
        elif cmd == "CIRCLE":
            if i + 3 < len(data):
                cx, cy, r = float(data[i + 1]), float(data[i + 2]), float(data[i + 3])
                shapes.append({"kind": "circle", "cx": cx, "cy": cy, "r": r})
                pts.extend([(cx - r, cy - r), (cx + r, cy + r)])
            i += 4
        elif cmd == "R":
            if i + 4 < len(data):
                x, y, w, h = (float(data[i + 1]), float(data[i + 2]),
                              float(data[i + 3]), float(data[i + 4]))
                shapes.append({"kind": "rect", "x": x, "y": y, "w": w, "h": h})
                pts.extend([(x, y), (x + w, y + h)])
            i += 6 if (i + 5 < len(data) and isinstance(data[i + 5], _NUM)) else 5
        else:
            i += 1
    return pts, shapes


def bbox(points):
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return {"min_x": min(xs), "max_x": max(xs), "min_y": min(ys), "max_y": max(ys)}


# --- gate files --------------------------------------------------------------
def gate_check(name, expected, actual, ok=None, note=None):
    if ok is None:
        ok = (expected == actual)
    c = {"name": name, "expected": expected, "actual": actual, "pass": bool(ok)}
    if note:
        c["note"] = note
    return c


def write_gate(path, step, checks, notes=None, extra=None):
    import datetime
    passed = all(c.get("pass") for c in checks) if checks else False
    doc = {
        "step": step,
        "pass": bool(passed),
        "checks": checks,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "notes": notes or "",
    }
    if extra:
        doc.update(extra)
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")
    return doc


def find_staged_epro(root):
    """The archive later steps should read out of import/, in priority order:

    1. a genuine classic .epro exported by EasyEDA -- authoritative
    2. one converted from .epro2 by scripts/06_epro2_to_epro.py

    A raw .epro2 is never returned: KiCad loads it as an empty board without
    erroring, so picking it by mtime would silently produce nothing.
    """
    d = os.path.join(root, "import")
    files = sorted(os.listdir(d)) if os.path.isdir(d) else []

    def newest(pred):
        c = [os.path.join(d, f) for f in files if pred(f)]
        return max(c, key=os.path.getmtime) if c else None

    low = lambda f: f.lower()                                   # noqa: E731
    return (newest(lambda f: low(f).endswith((".epro", ".eprj"))
                   and not low(f).endswith(".converted.epro")
                   and not f.startswith("patched"))
            or newest(lambda f: low(f).endswith(".converted.epro")))


def dump_json(path, obj):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")


def load_json(path):
    with open(path) as f:
        return json.load(f)


UUID_RE = re.compile(r"^[0-9a-fA-F]{20,40}$")
