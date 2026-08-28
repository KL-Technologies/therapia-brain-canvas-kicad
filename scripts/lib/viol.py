"""Turning a kicad-cli DRC report into a work list.

`lib/drc.py` answers "did the board get worse?" -- a signature-level question
that deliberately throws away positions so DRC's jitter cannot flip the gate.
Repair needs the opposite: the actual item, on the actual layer, at the actual
coordinate, so a script can go and move it.

The two are not in conflict. Signatures gate; keys locate. A `key` here is
(type, layer, nets, position rounded to 1 um) and it is stable enough to tell
"the violation I just fixed" from "a violation I just created", which is all
the repair loop needs of it. It is NOT stable enough to gate on -- the same
physical problem can be reported at either of two positions -- so nothing in
this module is used for pass/fail.

Item descriptions are parsed rather than looked up by uuid because the uuids in
a DRC report refer to items that a repair may have already deleted, while the
description carries what the repair actually needs: the class (Track / Via /
Pad / Zone), the net, the layer, and for pads the component reference.
"""

import re
import collections

# "Track [ESP_TXD] on Bottom Layer, length 11.6840 mm"
# "Pad 1 [GND] of AMS1117 on F.Cu, Inner Layer 1, ..."
# "NPTH pad of H4"
# "Via [USB_VBUS_RAW] on F.Cu - B.Cu"
# "Zone [GND] on Inner Layer 1"
_NET_RE = re.compile(r"\[([^\]]+)\]")
_ACTUAL_RE = re.compile(r"actual ([\d.]+) mm")
_RULE_RE = re.compile(r"rule '([^']+)'")
_CONSTRAINT_RE = re.compile(r"clearance ([\d.]+) mm")
_PAD_RE = re.compile(r"^Pad (\S+) \[[^\]]*\] of (\S+)")
_NPTH_RE = re.compile(r"^NPTH pad of (\S+)")
_PTH_RE = re.compile(r"^PTH pad of (\S+)")
_ON_RE = re.compile(r" on (.+?)(?:, length|$)")

CLASSES = ("Track", "Via", "Pad", "Zone", "NPTH", "PTH", "Arc", "Text", "Other")


def item_class(desc):
    d = desc.strip()
    if d.startswith("Track"):
        return "Track"
    if d.startswith("Via") or d.startswith("Micro Via") or d.startswith("Blind"):
        return "Via"
    if d.startswith("NPTH pad"):
        return "NPTH"
    if d.startswith("PTH pad"):
        return "PTH"
    if d.startswith("Pad"):
        return "Pad"
    if d.startswith("Zone") or d.startswith("Rule Area"):
        return "Zone"
    if d.startswith("Arc"):
        return "Arc"
    if d.startswith("Text") or d.startswith("Footprint Text"):
        return "Text"
    return "Other"


def item_net(desc):
    m = _NET_RE.search(desc)
    return m.group(1) if m else None


def item_ref(desc):
    """Component reference, for the item kinds that name one."""
    for rx in (_PAD_RE, _NPTH_RE, _PTH_RE):
        m = rx.match(desc.strip())
        if m:
            return m.group(m.lastindex)
    return None


def item_pad_number(desc):
    m = _PAD_RE.match(desc.strip())
    return m.group(1) if m else None


def item_layers(desc):
    m = _ON_RE.search(desc)
    if not m:
        return []
    return [s.strip() for s in m.group(1).split(",") if s.strip()]


def parse_item(it):
    desc = it.get("description", "")
    pos = it.get("pos") or {}
    return {
        "class": item_class(desc),
        "net": item_net(desc),
        "ref": item_ref(desc),
        "pad": item_pad_number(desc),
        "layers": item_layers(desc),
        "x": pos.get("x"),
        "y": pos.get("y"),
        "uuid": it.get("uuid"),
        "desc": desc,
    }


def parse(violation):
    d = violation.get("description", "")
    m = _ACTUAL_RE.search(d)
    c = _CONSTRAINT_RE.search(d)
    r = _RULE_RE.search(d)
    items = [parse_item(i) for i in violation.get("items", [])]
    return {
        "type": violation.get("type"),
        "severity": violation.get("severity"),
        "rule": r.group(1) if r else None,
        "actual_mm": float(m.group(1)) if m else None,
        "required_mm": float(c.group(1)) if c else None,
        "items": items,
        "nets": sorted({i["net"] for i in items if i["net"]}),
        "refs": sorted({i["ref"] for i in items if i["ref"]}),
        "classes": sorted({i["class"] for i in items}),
        "desc": d,
    }


def key(violation):
    """(type, classes, nets, rounded positions) -- locates a violation.

    Positions are rounded to 1 um and sorted so the two items may be reported
    in either order. Good enough to tell an old violation from a new one
    inside one repair loop; NOT a gate key (use lib/drc.signature for that).
    """
    p = parse(violation)
    pts = tuple(sorted(
        (round(i["x"] or 0.0, 3), round(i["y"] or 0.0, 3)) for i in p["items"]))
    return (p["type"], tuple(p["classes"]), tuple(p["nets"]), pts)


def key_text(k):
    kind, classes, nets, pts = k
    return "%s %s nets=%s at %s" % (
        kind, "+".join(classes), ",".join(nets),
        " ".join("(%.3f,%.3f)" % p for p in pts))


def errors(doc):
    return [v for v in doc.get("violations", []) if v.get("severity") == "error"]


def group_by_type(viols):
    out = collections.OrderedDict()
    for v in viols:
        out.setdefault(v.get("type"), []).append(v)
    return out


def involving_npth(violation):
    """The NPTH references this violation touches, if any."""
    p = parse(violation)
    return sorted({i["ref"] for i in p["items"]
                   if i["class"] == "NPTH" and i["ref"]})


def movable_items(violation):
    """The items a repair is allowed to move: tracks and vias, never pads.

    Pads move only with their footprint, which is a placement decision (L1),
    not something the generic loop may do. NPTH holes are fixed mechanical
    features and never move.
    """
    p = parse(violation)
    return [i for i in p["items"] if i["class"] in ("Track", "Via")]
