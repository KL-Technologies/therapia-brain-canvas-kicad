"""Minimal .xlsx reader (zipfile + xml.etree). No openpyxl on this machine.

Only what the EasyEDA-exported BOM/CPL sheets need: the first worksheet, shared
strings, inline strings, and cell values as text.

Inputs are locally exported spreadsheets, and stdlib ElementTree refuses
undefined/external entities, so defusedxml is not pulled in (stdlib-only rule).
"""

import re
import zipfile
import xml.etree.ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
_CELL_RE = re.compile(r"^([A-Z]+)(\d+)$")


def _col_index(ref):
    m = _CELL_RE.match(ref or "")
    if not m:
        return 0
    col, n = m.group(1), 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _shared_strings(zf):
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    out = []
    for si in root.findall("m:si", NS):
        out.append("".join(t.text or "" for t in si.iter(
            "{%s}t" % NS["m"])))
    return out


def read_sheet(path, sheet="xl/worksheets/sheet1.xml"):
    """Return the sheet as a list of rows, each row a list of cell strings."""
    with zipfile.ZipFile(path) as zf:
        shared = _shared_strings(zf)
        root = ET.fromstring(zf.read(sheet))
    rows = []
    for row in root.iter("{%s}row" % NS["m"]):
        cells = {}
        for c in row.findall("m:c", NS):
            idx = _col_index(c.get("r"))
            t = c.get("t")
            if t == "s":
                v = c.find("m:v", NS)
                text = shared[int(v.text)] if v is not None and v.text else ""
            elif t == "inlineStr":
                is_ = c.find("m:is", NS)
                text = "".join(x.text or "" for x in is_.iter("{%s}t" % NS["m"])) if is_ is not None else ""
            else:
                v = c.find("m:v", NS)
                text = v.text if v is not None and v.text is not None else ""
            cells[idx] = text
        width = (max(cells) + 1) if cells else 0
        rows.append([cells.get(i, "") for i in range(width)])
    return rows


def read_table(path, sheet="xl/worksheets/sheet1.xml"):
    """Return (header, [dict per row]) using the first non-empty row as header."""
    rows = read_sheet(path, sheet)
    header, start = None, 0
    for i, r in enumerate(rows):
        if any(c.strip() for c in r):
            header, start = [c.strip() for c in r], i + 1
            break
    if header is None:
        return [], []
    out = []
    for r in rows[start:]:
        if not any(c.strip() for c in r):
            continue
        out.append({header[i]: (r[i] if i < len(r) else "")
                    for i in range(len(header))})
    return header, out


def to_mm(text):
    """'53.594mm' / '2110mil' / '53.594' -> float mm."""
    if text is None:
        return None
    s = str(text).strip().lower().replace(" ", "")
    if not s:
        return None
    mult = 1.0
    if s.endswith("mm"):
        s = s[:-2]
    elif s.endswith("mil"):
        s, mult = s[:-3], 0.0254
    elif s.endswith("in"):
        s, mult = s[:-2], 25.4
    try:
        return float(s) * mult
    except ValueError:
        return None
