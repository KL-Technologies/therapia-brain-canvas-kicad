#!/usr/bin/env python3
"""S2a: inventory the EasyEDA Pro side of the board, straight from the .epro.

Writes gates/inventory_easyeda.json -- the reference every later step is
measured against -- plus contract/netlist_from_epro_pcb.json and
contract/netlist_from_epro_schematic.json.

Record layouts were read out of the actual export and cross-checked against
KiCad's parser (pcbnew/pcb_io/easyedapro/). Two of them differ from what the
dev-docs summary implies and matter:

  PAD_NET  ["PAD_NET", compId, padNumber, netName, elementId, flag]
           One row per footprint element, not per pad: only the rows with a
           non-empty padNumber carry a net. 2566 rows -> 425 real pad nets.
  PAD      A component's pads are NOT in the .epcb. They live in the .efoo of
           the footprint named by the component's ATTR "Footprint", in
           footprint-local mil, and have to be placed by the component's own
           position and rotation.

The placement transform below is validated against the 2026-08-16 CPL export
(Pad X / Pad Y for all 131 parts) every run -- see cpl_crosscheck in the output.

Runs under system python3; no KiCad needed.
"""

import os
import sys
import math
import json
import argparse
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import epro as E                      # noqa: E402
from lib import xlsx                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAB_REF = "/Users/dev/projects/therapia-device/cerelog_research/fab_2026-08-16"


def place(cx, cy, rot, lx, ly):
    """Footprint-local mil -> board mil for a component placed at (cx,cy,rot).

    Plain rotation, no axis flip. Verified against every one of the 131 CPL
    Pad X/Pad Y entries; the three other sign conventions do not fit.
    """
    th = math.radians(float(rot or 0))
    c, s = math.cos(th), math.sin(th)
    lx, ly = float(lx), float(ly)
    return (float(cx) + lx * c - ly * s, float(cy) + lx * s + ly * c)


# ---------------------------------------------------------------- PCB parsing
def parse_pcb(records):
    hist = collections.Counter()
    comps, board_pads, vias, tracks, arcs = {}, [], [], [], []
    pours, regions, fills, poured = [], [], [], []
    nets_declared, rules, layers, pad_nets = [], [], [], []
    attrs = collections.defaultdict(dict)
    outline_pts = []
    unhandled = collections.Counter()

    for rec in records:
        t = E.rtype(rec)
        if t is None:
            continue
        hist[t] += 1

        if t == "LAYER":
            layers.append({"id": E.get(rec, 1), "type": E.get(rec, 2),
                           "name": E.get(rec, 3), "flag": E.get(rec, 4)})
        elif t == "NET":
            if isinstance(E.get(rec, 1), str):
                nets_declared.append(rec[1])
        elif t == "RULE":
            rules.append({"rule_type": E.get(rec, 1), "name": E.get(rec, 2),
                          "is_default": E.get(rec, 3), "data": E.get(rec, 4)})
        elif t == "COMPONENT":
            comps[E.get(rec, 1)] = {"id": E.get(rec, 1), "layer": E.get(rec, 3),
                                    "x": E.get(rec, 4), "y": E.get(rec, 5),
                                    "rotation": E.get(rec, 6),
                                    "props": E.get(rec, 7)}
        elif t == "ATTR":
            parent, key, val = E.get(rec, 3), E.get(rec, 7), E.get(rec, 8)
            if isinstance(parent, str) and isinstance(key, str):
                attrs[parent][key] = val
        elif t == "PAD":
            board_pads.append(pad_dict(rec, parent=""))
        elif t == "PAD_NET":
            num, net = E.get(rec, 2), E.get(rec, 3)
            if num not in ("", None):
                pad_nets.append((E.get(rec, 1), str(num), net or ""))
        elif t == "VIA":
            vias.append({"id": E.get(rec, 1), "net": E.get(rec, 3),
                         "x": E.get(rec, 5), "y": E.get(rec, 6),
                         "drill": E.get(rec, 7), "diameter": E.get(rec, 8)})
        elif t == "LINE":
            tracks.append({"net": E.get(rec, 3), "layer": E.get(rec, 4),
                           "x1": E.get(rec, 5), "y1": E.get(rec, 6),
                           "x2": E.get(rec, 7), "y2": E.get(rec, 8),
                           "width": E.get(rec, 9)})
        elif t == "ARC":
            arcs.append({"net": E.get(rec, 3), "layer": E.get(rec, 4),
                         "x1": E.get(rec, 5), "y1": E.get(rec, 6),
                         "x2": E.get(rec, 7), "y2": E.get(rec, 8),
                         "angle": E.get(rec, 9), "width": E.get(rec, 10)})
        elif t == "POUR":
            pts, _ = poly_all(E.get(rec, 8))
            pours.append({"id": E.get(rec, 1), "net": E.get(rec, 3),
                          "layer": E.get(rec, 4), "name": E.get(rec, 6),
                          "fill_order": E.get(rec, 7), "style": E.get(rec, 9),
                          "bbox": E.bbox(pts)})
        elif t == "POURED":
            poured.append({"id": E.get(rec, 1), "parent": E.get(rec, 2)})
        elif t == "REGION":
            pts, shapes = poly_all(E.get(rec, 6))
            regions.append({"id": E.get(rec, 1), "layer": E.get(rec, 3),
                            "bbox": E.bbox(pts), "shapes": shapes})
        elif t == "FILL":
            pts, _ = poly_all(E.get(rec, 7))
            fills.append({"id": E.get(rec, 1), "net": E.get(rec, 3),
                          "layer": E.get(rec, 4), "bbox": E.bbox(pts)})
        elif t == "POLY":
            pts, shapes = poly_all(E.get(rec, 6))
            if E.get(rec, 4) in (11, "11"):
                outline_pts.extend(pts)
        elif t in ("DOCTYPE", "HEAD", "CANVAS", "ACTIVE_LAYER", "PRIMITIVE",
                   "LAYER_PHYS", "SILK_OPTS", "PREFERENCE", "PANELIZE",
                   "PANELIZE_STAMP", "PANELIZE_SIDE", "STRING", "IMAGE", "OBJ",
                   "TEARDROP", "RULE_SELECTOR", "RULE_TEMPLATE", "META"):
            pass
        else:
            unhandled[t] += 1

    for it in tracks + arcs:
        if it["layer"] in (11, "11"):
            outline_pts.append((float(it["x1"]), float(it["y1"])))
            outline_pts.append((float(it["x2"]), float(it["y2"])))

    return dict(hist=hist, comps=comps, board_pads=board_pads, vias=vias,
                tracks=tracks, arcs=arcs, pours=pours, regions=regions,
                fills=fills, poured=poured, nets_declared=nets_declared,
                rules=rules, layers=layers, attrs=attrs, pad_nets=pad_nets,
                outline_pts=outline_pts, unhandled=unhandled)


def poly_all(data):
    """Decode one path or a list of paths."""
    if isinstance(data, list) and data and isinstance(data[0], list):
        pts, shapes = [], []
        for sub in data:
            p, s = E.poly_points(sub)
            pts.extend(p)
            shapes.extend(s)
        return pts, shapes
    return E.poly_points(data)


def pad_dict(rec, parent):
    return {"id": E.get(rec, 1), "parent": parent, "net": E.get(rec, 3) or "",
            "layer": E.get(rec, 4), "number": str(E.get(rec, 5)),
            "x": E.get(rec, 6), "y": E.get(rec, 7), "rotation": E.get(rec, 8),
            "hole": E.get(rec, 9), "shape": E.get(rec, 10)}


def load_footprints(ep):
    """uuid -> {title, pads, counts}. .efoo blocks are split on blank lines."""
    out = {}
    for name in ep.footprint_documents():
        uuid = os.path.splitext(os.path.basename(name))[0]
        recs, _ = E.parse_jsonl(ep.read_text(name))
        title, pads, counts = "", [], collections.Counter()
        for rec in recs:
            t = E.rtype(rec)
            if t is None:
                continue
            counts[t] += 1
            if t == "HEAD" and isinstance(E.get(rec, 1), dict):
                head = rec[1]
                title = head.get("title") or title
                uuid = head.get("uuid") or uuid
            elif t == "PAD":
                pads.append(pad_dict(rec, parent=uuid))
        out[uuid] = {"title": title, "pads": pads, "records": dict(counts),
                     "document": name}
    return out


def hole_size(hole):
    """["ROUND"|"SLOT", w, h] -> (shape, w, h) in mil, or None."""
    if not (isinstance(hole, list) and len(hole) >= 3):
        return None
    try:
        w, h = float(hole[1] or 0), float(hole[2] or 0)
    except (TypeError, ValueError):
        return None
    if w <= 0 and h <= 0:
        return None
    return (str(hole[0]), w, h)


def build_inventory(p, fps):
    comps, attrs = p["comps"], p["attrs"]
    designators = {cid: (attrs.get(cid, {}).get("Designator") or cid)
                   for cid in comps}
    fp_of = {cid: attrs.get(cid, {}).get("Footprint") for cid in comps}

    net_of = {}
    for cid, num, net in p["pad_nets"]:
        net_of[(cid, num)] = net

    pad_rows, missing_fp = [], []
    for cid, c in comps.items():
        ref = designators[cid]
        fu = fp_of.get(cid)
        fp = fps.get(fu)
        if not fp:
            missing_fp.append({"ref": ref, "footprint_uuid": fu})
            continue
        for pd in fp["pads"]:
            bx, by = place(c["x"], c["y"], c["rotation"], pd["x"], pd["y"])
            pad_rows.append({
                "ref": ref, "pad": pd["number"],
                "net": net_of.get((cid, pd["number"]), "") or "",
                "x_mm": E.mil2mm(bx), "y_mm": E.mil2mm(by),
                "layer": pd["layer"], "hole": pd["hole"], "shape": pd["shape"],
                "standalone": False, "footprint": fp["title"]})
    for pd in p["board_pads"]:
        pad_rows.append({
            "ref": "", "pad": pd["number"], "net": pd["net"],
            "x_mm": E.mil2mm(pd["x"]), "y_mm": E.mil2mm(pd["y"]),
            "layer": pd["layer"], "hole": pd["hole"], "shape": pd["shape"],
            "standalone": True, "footprint": ""})

    net_pads = collections.Counter(r["net"] for r in pad_rows if r["net"])

    holes = []
    for r in pad_rows:
        hs = hole_size(r["hole"])
        if not hs:
            continue
        holes.append({"source": "PAD", "ref": r["ref"], "pad": r["pad"],
                      "net": r["net"], "x_mm": r["x_mm"], "y_mm": r["y_mm"],
                      "hole_shape": hs[0], "dia_mm": E.mil2mm(max(hs[1], hs[2])),
                      "size_mm": [E.mil2mm(hs[1]), E.mil2mm(hs[2])],
                      "standalone": r["standalone"], "footprint": r["footprint"]})
    for reg in p["regions"]:
        for s in reg["shapes"]:
            if s.get("kind") == "circle":
                holes.append({"source": "REGION", "ref": "", "pad": "", "net": "",
                              "x_mm": E.mil2mm(s["cx"]), "y_mm": E.mil2mm(s["cy"]),
                              "hole_shape": "CIRCLE",
                              "dia_mm": E.mil2mm(s["r"] * 2),
                              "size_mm": [E.mil2mm(s["r"] * 2)] * 2,
                              "standalone": True, "footprint": ""})

    matched = []
    for name, ex, ey, ed in E.EXPECTED_NPTH:
        hit = next((h for h in holes
                    if h["x_mm"] is not None
                    and E.approx(h["x_mm"], ex, 0.01)
                    and E.approx(h["y_mm"], ey, 0.01)), None)
        matched.append({"name": name,
                        "expected": {"x_mm": ex, "y_mm": ey, "dia_mm": ed},
                        "found": hit,
                        "dia_ok": bool(hit) and E.approx(hit["dia_mm"], ed, 0.02)})

    bb = E.bbox(p["outline_pts"])
    outline = None
    if bb:
        outline = {"min_x_mm": E.mil2mm(bb["min_x"]), "max_x_mm": E.mil2mm(bb["max_x"]),
                   "min_y_mm": E.mil2mm(bb["min_y"]), "max_y_mm": E.mil2mm(bb["max_y"]),
                   "width_mm": E.mil2mm(bb["max_x"] - bb["min_x"]),
                   "height_mm": E.mil2mm(bb["max_y"] - bb["min_y"])}

    def by_layer(items):
        c = collections.Counter(E.layer_name(i["layer"]) for i in items)
        return dict(sorted(c.items()))

    rots = collections.Counter()
    for c in comps.values():
        try:
            rots[round(float(c["rotation"]) % 360.0, 3)] += 1
        except (TypeError, ValueError):
            rots["?"] += 1

    comp_rows = {}
    for cid, c in comps.items():
        fu = fp_of.get(cid)
        comp_rows[designators[cid]] = {
            "id": cid, "x_mm": E.mil2mm(c["x"]), "y_mm": E.mil2mm(c["y"]),
            "rotation": c["rotation"], "layer": E.layer_name(c["layer"]),
            "footprint_uuid": fu,
            "footprint": (fps.get(fu) or {}).get("title", ""),
            "pads": len((fps.get(fu) or {}).get("pads", [])),
            "device": attrs.get(cid, {}).get("Device"),
            "unique_id": (c.get("props") or {}).get("Unique ID")
            if isinstance(c.get("props"), dict) else None,
        }

    return {
        "record_histogram": dict(sorted(p["hist"].items())),
        "unhandled_record_types": dict(p["unhandled"]),
        "layers": [l for l in p["layers"] if l["id"] in
                   (1, 2, 11, 12, 15, 16, 3, 4, 5, 6, 7, 8)],
        "footprints": {
            "count": len(comps),
            "designators": sorted(designators.values()),
            "duplicate_designators": sorted(
                d for d, n in collections.Counter(designators.values()).items()
                if n > 1),
            "unresolved_footprints": missing_fp,
            "library": {u: {"title": f["title"], "pads": len(f["pads"])}
                        for u, f in sorted(fps.items())},
            "by_designator": comp_rows,
        },
        "pads": {
            "total": len(pad_rows),
            "in_components": sum(1 for r in pad_rows if not r["standalone"]),
            "standalone": sum(1 for r in pad_rows if r["standalone"]),
            "with_net": sum(1 for r in pad_rows if r["net"]),
            "pad_net_rows": len(p["pad_nets"]),
        },
        "nets": {
            "declared_count": len(set(p["nets_declared"])),
            "declared": sorted(set(p["nets_declared"])),
            "with_pads_count": len(net_pads),
            "pad_counts": dict(sorted(net_pads.items())),
        },
        "tracks": {"total": len(p["tracks"]), "by_layer": by_layer(p["tracks"])},
        "arcs": {"total": len(p["arcs"]), "by_layer": by_layer(p["arcs"])},
        "vias": {"total": len(p["vias"])},
        "zones": {
            "pour_count": len(p["pours"]),
            "pours": [{"net": z["net"], "layer": E.layer_name(z["layer"]),
                       "name": z["name"], "fill_order": z["fill_order"],
                       "style": z["style"]} for z in p["pours"]],
            "poured_count": len(p["poured"]),
            "fill_count": len(p["fills"]),
            "region_count": len(p["regions"]),
        },
        "npth": {"holes_found": holes, "expected_match": matched,
                 "all_expected_found": all(m["found"] for m in matched)},
        "outline_bbox_mm": outline,
        "rotations": {str(k): v for k, v in sorted(rots.items(),
                                                   key=lambda kv: str(kv[0]))},
        "rules": p["rules"],
        "_pad_rows": pad_rows,
    }


# --------------------------------------------------------- schematic netlist
def esym_pins(text):
    """symbol -> [{id,x,y,length,rotation,name,number}] (PIN + its ATTRs)."""
    recs, _ = E.parse_jsonl(text)
    pins, attrs, sym_type = {}, collections.defaultdict(dict), None
    for rec in recs:
        t = E.rtype(rec)
        if t == "HEAD" and isinstance(E.get(rec, 1), dict):
            sym_type = rec[1].get("symbolType")
        elif t == "PIN":
            pins[E.get(rec, 1)] = {"id": E.get(rec, 1), "x": E.get(rec, 4),
                                   "y": E.get(rec, 5), "length": E.get(rec, 6),
                                   "rotation": E.get(rec, 7)}
        elif t == "ATTR":
            parent, key, val = E.get(rec, 2), E.get(rec, 3), E.get(rec, 4)
            if isinstance(parent, str) and isinstance(key, str):
                attrs[parent][key] = val
    for pid, p in pins.items():
        a = attrs.get(pid, {})
        p["name"] = a.get("NAME") or ""
        p["number"] = str(a.get("NUMBER") or "")
    return {"type": sym_type, "pins": list(pins.values())}


def wire_segments(geometry):
    """WIRE geometry is a list of flat coordinate runs: [[x1,y1,x2,y2,...], ...]"""
    segs = []
    if not isinstance(geometry, list):
        return segs
    runs = geometry if geometry and isinstance(geometry[0], list) else [geometry]
    for run in runs:
        nums = [v for v in run if isinstance(v, (int, float))]
        pts = list(zip(nums[0::2], nums[1::2]))
        segs.extend(zip(pts, pts[1:]))
    return segs


def _on_seg(px, py, a, b, tol):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return abs(px - ax) <= tol and abs(py - ay) <= tol
    t = ((px - ax) * dx + (py - ay) * dy) / L2
    if t < -1e-9 or t > 1 + 1e-9:
        return False
    cx, cy = ax + t * dx, ay + t * dy
    return (cx - px) ** 2 + (cy - py) ** 2 <= tol * tol


def schematic_netlist(ep, log, tol=1.0):
    """designator -> pin -> net, solved from .esch geometry.

    Every WIRE carries its net name in an ATTR "NET", so this only has to place
    each symbol pin and find the wire under it -- no label propagation, and no
    guessing at junction semantics.
    """
    sheets = ep.schematic_documents()
    if not sheets:
        return {"status": "no_schematic_documents"}, False

    symbols = {}
    for name in ep.symbol_documents():
        uuid = os.path.splitext(os.path.basename(name))[0]
        try:
            symbols[uuid] = esym_pins(ep.read_text(name))
        except Exception as exc:                          # noqa: BLE001
            log.append("esym parse failed %s: %s" % (name, exc))

    sheet_data = []
    for name in sorted(sheets):
        recs, errs = E.parse_jsonl(ep.read_text(name))
        if errs:
            log.append("%s: %d unparsable lines" % (name, len(errs)))
        comps, attrs, wires = {}, collections.defaultdict(dict), {}
        for rec in recs:
            t = E.rtype(rec)
            if t == "COMPONENT":
                comps[E.get(rec, 1)] = {"x": E.get(rec, 3), "y": E.get(rec, 4),
                                        "rot": E.get(rec, 5),
                                        "mirror": E.get(rec, 6)}
            elif t == "ATTR":
                parent, key, val = E.get(rec, 2), E.get(rec, 3), E.get(rec, 4)
                if isinstance(parent, str) and isinstance(key, str):
                    attrs[parent][key] = val
            elif t == "WIRE":
                wires[E.get(rec, 1)] = wire_segments(E.get(rec, 2))
        nets = {wid: attrs.get(wid, {}).get("NET") for wid in wires}
        sheet_data.append({"name": name, "comps": comps, "attrs": attrs,
                           "wires": wires, "nets": nets})

    def solve(use_pin_end):
        merged = collections.defaultdict(dict)
        hit = miss = 0
        for sd in sheet_data:
            segs = [(s, sd["nets"].get(wid)) for wid, ss in sd["wires"].items()
                    for s in ss]
            for cid, c in sd["comps"].items():
                a = sd["attrs"].get(cid, {})
                ref = a.get("Designator")
                sym = symbols.get(str(a.get("Symbol")))
                if not ref or not sym:
                    continue
                for pin in sym["pins"]:
                    px, py = float(pin["x"] or 0), float(pin["y"] or 0)
                    if use_pin_end:
                        pr = math.radians(float(pin["rotation"] or 0))
                        ln = float(pin["length"] or 0)
                        px, py = px + ln * math.cos(pr), py + ln * math.sin(pr)
                    bx, by = place(c["x"], c["y"], c["rot"], px, py)
                    net = None
                    for seg, nm in segs:
                        if nm and _on_seg(bx, by, seg[0], seg[1], tol):
                            net = nm
                            break
                    key = pin["number"] or pin["name"]
                    if net:
                        merged[ref][str(key)] = net
                        hit += 1
                    else:
                        merged[ref].setdefault(str(key), "")
                        miss += 1
        return merged, hit, miss

    best = None
    for use_end in (False, True):
        merged, hit, miss = solve(use_end)
        if best is None or hit > best[1]:
            best = (merged, hit, miss, use_end)
    merged, hit, miss, use_end = best

    total = hit + miss
    ok = bool(total) and hit >= total * 0.9 and len(merged) >= 100
    counts = collections.Counter(n for pins in merged.values()
                                 for n in pins.values() if n)
    return ({"status": "ok" if ok else "unreliable",
             "method": "pin position vs WIRE geometry; net name from each "
                       "wire's ATTR \"NET\". pin_point=%s"
                       % ("lead end" if use_end else "origin"),
             "pins_resolved": hit, "pins_unresolved": miss,
             "components": len(merged),
             "sheets": [os.path.basename(s["name"]) for s in sheet_data],
             "net_pin_counts": dict(sorted(counts.items())),
             "by_designator": {k: merged[k] for k in sorted(merged)},
             "log": log}, ok)


# ------------------------------------------------------------------ reference
def cpl_reference():
    path = os.path.join(FAB_REF, "Therapia_EEG-HRV_CPL.xlsx")
    if not os.path.exists(path):
        return None
    try:
        header, rows = xlsx.read_table(path)
    except Exception as exc:                              # noqa: BLE001
        return {"error": str(exc)}
    out = {}
    for r in rows:
        ref = (r.get("Designator") or "").strip()
        if not ref:
            continue
        out[ref] = {"x_mm": xlsx.to_mm(r.get("Mid X")),
                    "y_mm": xlsx.to_mm(r.get("Mid Y")),
                    "pad_x_mm": xlsx.to_mm(r.get("Pad X")),
                    "pad_y_mm": xlsx.to_mm(r.get("Pad Y")),
                    "rotation": (r.get("Rotation") or "").strip(),
                    "layer": (r.get("Layer") or "").strip()}
    return {"file": path, "header": header, "count": len(out), "rows": out,
            "rotations": dict(collections.Counter(v["rotation"]
                                                  for v in out.values()))}


def cpl_crosscheck(inv, pad_rows, cpl):
    by_des = inv["footprints"]["by_designator"]
    inv_des, cpl_des = set(by_des), set(cpl["rows"])
    pos_bad, rot_bad, pad1_bad = [], [], []
    pad1 = {}
    for r in pad_rows:
        if r["ref"] and r["pad"] == "1":
            pad1.setdefault(r["ref"], r)
    for ref in sorted(inv_des & cpl_des):
        a, b = by_des[ref], cpl["rows"][ref]
        if b["x_mm"] is not None and not (
                E.approx(a["x_mm"], b["x_mm"], 0.01)
                and E.approx(a["y_mm"], b["y_mm"], 0.01)):
            pos_bad.append({"ref": ref, "epro": [a["x_mm"], a["y_mm"]],
                            "cpl": [b["x_mm"], b["y_mm"]]})
        try:
            if round(float(a["rotation"]) % 360) != round(float(b["rotation"]) % 360):
                rot_bad.append({"ref": ref, "epro": a["rotation"],
                                "cpl": b["rotation"]})
        except (TypeError, ValueError):
            pass
        p = pad1.get(ref)
        if p and b["pad_x_mm"] is not None and not (
                E.approx(p["x_mm"], b["pad_x_mm"], 0.01)
                and E.approx(p["y_mm"], b["pad_y_mm"], 0.01)):
            pad1_bad.append({"ref": ref, "epro": [p["x_mm"], p["y_mm"]],
                             "cpl": [b["pad_x_mm"], b["pad_y_mm"]]})
    return {"cpl_file": cpl["file"], "cpl_count": cpl["count"],
            "only_in_epro": sorted(inv_des - cpl_des),
            "only_in_cpl": sorted(cpl_des - inv_des),
            "cpl_rotations": cpl["rotations"],
            "position_mismatches": pos_bad[:40],
            "rotation_mismatches": rot_bad[:40],
            "pad1_placement_mismatches": pad1_bad[:40],
            "placement_transform_verified": not pad1_bad and not pos_bad,
            "note": "pad1_placement_mismatches empty means the footprint-local "
                    "-> board transform in place() reproduces the fab CPL"}


# ----------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--epro")
    ap.add_argument("--root", default=ROOT)
    args = ap.parse_args()
    root = args.root

    src = args.epro or E.find_staged_epro(root)
    if not src:
        print("no .epro staged in import/ -- run scripts/05_find_epro.sh "
              "and scripts/06_epro2_to_epro.py first")
        return 2

    log = []
    with E.Epro(src) as ep:
        project = ep.project()
        pcbs = project.get("pcbs", {}) or {}
        boards = project.get("boards", {}) or {}
        docs = ep.pcb_documents()
        if not docs:
            print("no .epcb document in %s" % src)
            return 2
        main_pcb_id = (next(iter(boards.values()), {}) or {}).get("pcb") \
            or (next(iter(pcbs), None))
        chosen = next((d for d in docs if main_pcb_id and main_pcb_id in d), docs[0])
        log.append("pcb document %s (pcb_id=%s of %d)" % (chosen, main_pcb_id, len(docs)))

        records, errors = E.parse_jsonl(ep.read_text(chosen))
        records = [r for r in records if r is not None]
        if errors:
            log.append("%s: %d unparsable lines" % (chosen, len(errors)))

        fps = load_footprints(ep)
        log.append("footprint documents: %d, pads: %d"
                   % (len(fps), sum(len(f["pads"]) for f in fps.values())))
        parsed = parse_pcb(records)
        inv = build_inventory(parsed, fps)
        pad_rows = inv.pop("_pad_rows")

        inv["source"] = {"file": os.path.abspath(src), "sha256": E.sha256_file(src),
                         "pcb_document": chosen, "pcb_id": main_pcb_id,
                         "parse_errors": len(errors),
                         "editor": next((r[1] for r in records
                                         if E.rtype(r) == "HEAD"
                                         and isinstance(E.get(r, 1), dict)), {})}
        inv["project"] = {"pcbs": pcbs, "boards": boards,
                          "schematics": list((project.get("schematics") or {}).keys()),
                          "documents": len(ep.names)}
        inv["log"] = log

        cpl = cpl_reference()
        if cpl and "rows" in cpl:
            inv["cpl_crosscheck"] = cpl_crosscheck(inv, pad_rows, cpl)
        elif cpl:
            inv["cpl_crosscheck"] = cpl

        E.dump_json(os.path.join(root, "gates", "inventory_easyeda.json"), inv)

        by_ref = collections.defaultdict(dict)
        for r in pad_rows:
            if r["ref"]:
                by_ref[r["ref"]][r["pad"]] = r["net"]
        E.dump_json(os.path.join(root, "contract", "netlist_from_epro_pcb.json"), {
            "source": inv["source"],
            "note": "designator -> pad number -> net, from the .epcb PAD_NET "
                    "records with footprint pads resolved from the .efoo "
                    "documents. Authoritative for what the PCB currently is, "
                    "NOT for what the schematic intends.",
            "net_pad_counts": inv["nets"]["pad_counts"],
            "by_designator": {k: by_ref[k] for k in sorted(by_ref)},
            "pads": pad_rows})

        # Design rules stay EasyEDA's: nothing here writes them into the KiCad
        # board, so S3 has to transcribe the ones it wants deliberately.
        E.dump_json(os.path.join(root, "contract", "easyeda_rules.json"), {
            "source": inv["source"],
            "note": "EasyEDA Pro design rules, verbatim from the .epcb RULE "
                    "records. NOT transferred to board/*.kicad_pcb -- the KiCad "
                    "DRC in logs/drc_import.json therefore runs on KiCad "
                    "DEFAULTS and its counts are not comparable to the EasyEDA "
                    "DRC. S3 must set net classes and custom rules in "
                    "board/*.kicad_pro before any DRC number means anything.",
            "rules": inv["rules"]})

        sch, sch_ok = schematic_netlist(ep, log)
        sch["source"] = inv["source"]
        if not sch_ok:
            sch["fallback"] = ("Run sch_ManufactureData.getNetlistFile() in the "
                               "EasyEDA Pro editor (Run Script) and save its "
                               "pinInfoMap here instead.")
        E.dump_json(os.path.join(root, "contract",
                                 "netlist_from_epro_schematic.json"), sch)

    E.dump_json(os.path.join(root, "logs", "inventory_parse_errors.json"),
                {"errors": errors[:200], "log": log})

    print("source: %s" % os.path.basename(src))
    print("inventory: %d footprints, %d pads (%d with net), %d nets, "
          "%d tracks, %d vias, %d pours"
          % (inv["footprints"]["count"], inv["pads"]["total"],
             inv["pads"]["with_net"], inv["nets"]["with_pads_count"],
             inv["tracks"]["total"], inv["vias"]["total"],
             inv["zones"]["pour_count"]))
    cc = inv.get("cpl_crosscheck", {})
    if "placement_transform_verified" in cc:
        print("CPL cross-check: transform_verified=%s pos_mismatch=%d "
              "rot_mismatch=%d only_in_epro=%d only_in_cpl=%d"
              % (cc["placement_transform_verified"], len(cc["position_mismatches"]),
                 len(cc["rotation_mismatches"]), len(cc["only_in_epro"]),
                 len(cc["only_in_cpl"])))
    print("NPTH expected found: %d/6" % sum(1 for m in inv["npth"]["expected_match"]
                                            if m["found"]))
    print("schematic netlist: %s (%d components, %d pins resolved, %d unresolved)"
          % (sch.get("status"), sch.get("components", 0),
             sch.get("pins_resolved", 0), sch.get("pins_unresolved", 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
