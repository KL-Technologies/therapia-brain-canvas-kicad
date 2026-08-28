#!/usr/bin/env python3
"""S8 -- read the manufacturing package back with our own parser.

    python3 scripts/62_check_fab.py [--json]

ACCEPTANCE D and E both turn on this: the Gerbers must be readable by something
other than KiCad, and the "no copper inside a mounting hole" rule must be
settled from the plotted data rather than from pcbnew's DRC. Handing the files
back to the program that wrote them would only show it agrees with itself.

Plain python3 -- no pcbnew, no kicad-cli. That is the point.
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import gerber_parse as G                           # noqa: E402
import ipcd356 as IPC                              # noqa: E402
import epro as E                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ACCEPTANCE E: 4 copper + 2 mask + 2 silk + 2 paste + 1 outline + job + 2 drill
EXPECTED = {
    "gtl": "F.Cu", "g1": "In1.Cu", "g2": "In2.Cu", "gbl": "B.Cu",
    "gts": "F.Mask", "gbs": "B.Mask", "gtp": "F.Paste", "gbp": "B.Paste",
    "gto": "F.SilkS", "gbo": "B.SilkS", "gm1": "Edge.Cuts",
}
COPPER = ("gtl", "g1", "g2", "gbl")

OUTLINE_MM = (61.8236, 45.0088)
OUTLINE_TOL = 0.01

# ACCEPTANCE D. Gerber Y is the board frame with Y negated, so these are the
# KiCad coordinates with y flipped.
NPTH = [
    ("PEG2", 176.861075, -108.097861, 0.700),
    ("PEG1", 176.861075, -113.877885, 0.700),
    ("H1", 123.048, -83.048, 2.3876),
    ("H2", 176.9468, -83.048, 2.3876),
    ("H3", 123.048, -121.9608, 2.3876),
    ("H4", 176.9468, -121.9608, 2.3876),
]
HOLE_MARGIN = 0.2


def load(fabdir):
    layers, extra = {}, []
    for path in sorted(glob.glob(os.path.join(fabdir, "*"))):
        ext = path.rsplit(".", 1)[-1].lower()
        if ext in EXPECTED:
            layers[ext] = G.parse_gerber(path)
        elif ext not in ("drl", "gbrjob", "pdf"):
            extra.append(os.path.basename(path))
    return layers, extra


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    fabdir = os.path.join(a.root, "fab", "gerber")
    out = {"dir": fabdir}

    layers, extra = load(fabdir)
    out["layers_found"] = sorted(layers)
    out["unexpected_files"] = extra
    out["missing_layers"] = sorted(set(EXPECTED) - set(layers))

    drills = {}
    for path in sorted(glob.glob(os.path.join(fabdir, "*.drl"))):
        tag = "NPTH" if "NPTH" in os.path.basename(path) else "PTH"
        drills[tag] = G.parse_excellon(path)
    out["drill_files"] = sorted(drills)

    # --- E: outline -------------------------------------------------------
    edge = layers.get("gm1")
    if edge:
        box = edge.centreline_bbox()
        out["outline"] = {
            "bbox": [round(v, 4) for v in box],
            "width_mm": round(box[2] - box[0], 4),
            "height_mm": round(box[3] - box[1], 4),
            "expected": list(OUTLINE_MM),
            "ok": (abs((box[2] - box[0]) - OUTLINE_MM[0]) <= OUTLINE_TOL
                   and abs((box[3] - box[1]) - OUTLINE_MM[1]) <= OUTLINE_TOL)}

    # --- E: every layer parsed, and nothing exotic in it ------------------
    stats = {}
    for ext, lay in sorted(layers.items()):
        c = lay.counts()
        stats[EXPECTED[ext]] = dict(
            c,
            file=os.path.basename(lay.path),
            format="%d.%d" % (lay.int_digits or 0, lay.dec_digits or 0),
            unit=lay.unit,
            file_function=lay.file_function,
            apertures=len(lay.apertures),
            clear_polarity_ops=lay.clear_ops,
            unparsed_apertures=lay.unknown,
            empty=not (c["flashes"] or c["draws"] or c["regions"]))
    out["layers"] = stats
    # "Parsed" means the file was understood, not that it has content: B.Paste
    # is legitimately empty because nothing is fitted on the back, and requiring
    # content would fail the package for being correct.
    out["all_parsed"] = all(
        s["format"] == "4.6" and s["unit"] == "MM"
        and not s["unparsed_apertures"] for s in stats.values())
    out["empty_layers"] = sorted(n for n, s in stats.items() if s["empty"])
    # The copper layers must be additive only; a clear-polarity op there would
    # mean the coverage and hole-clearance answers below are subtractive and
    # this parser is not modelling them.
    out["copper_all_dark"] = all(
        stats[EXPECTED[e]]["clear_polarity_ops"] == 0
        for e in COPPER if EXPECTED[e] in stats)

    # --- D: the six NPTH holes, and no copper inside them -----------------
    npth = drills.get("NPTH")
    holes = []
    if npth:
        for name, hx, hy, dia in NPTH:
            best = None
            for h in npth["hits"]:
                d = ((h["x"] - hx) ** 2 + (h["y"] - hy) ** 2) ** 0.5
                if best is None or d < best[0]:
                    best = (d, h)
            holes.append({"hole": name, "expected": [hx, hy, dia],
                          "found": None if best is None else
                          [best[1]["x"], best[1]["y"], best[1]["dia"]],
                          "offset_mm": None if best is None else round(best[0], 6),
                          "within_2um": bool(best and best[0] <= 0.002),
                          "dia_ok": bool(best and
                                         abs((best[1]["dia"] or 0) - dia)
                                         <= 0.002)})
    out["npth"] = {"count": 0 if not npth else len(npth["hits"]),
                   "tools": {} if not npth else npth["tools"],
                   "holes": holes,
                   "ok": len(holes) == 6 and all(h["within_2um"] and h["dia_ok"]
                                                 for h in holes)}

    clear = []
    for name, hx, hy, dia in NPTH:
        r = dia / 2.0 + HOLE_MARGIN
        for ext in COPPER:
            lay = layers.get(ext)
            if lay is None:
                continue
            hits = lay.copper_within(hx, hy, r)
            if hits:
                clear.append({"hole": name, "layer": EXPECTED[ext],
                              "radius_mm": round(r, 4),
                              "offenders": hits[:5],
                              "count": len(hits)})
    out["copper_in_npth_rings"] = clear
    out["npth_clear"] = not clear

    # --- E: plane fill ----------------------------------------------------
    if edge:
        box = edge.centreline_bbox()
        inset = (box[0] + 1.0, box[1] + 1.0, box[2] - 1.0, box[3] - 1.0)
        cov = {}
        for ext in COPPER:
            lay = layers.get(ext)
            if lay is not None:
                cov[EXPECTED[ext]] = round(lay.coverage(inset, 0.3), 4)
        out["copper_coverage"] = cov
        out["planes_filled"] = (cov.get("In1.Cu", 0) >= 0.60
                                and cov.get("In2.Cu", 0) >= 0.50)

    # --- F: paste apertures vs the pads that get paste --------------------
    gtp = layers.get("gtp")
    if gtp:
        c = gtp.counts()
        out["paste"] = {"flashes": c["flashes"], "regions": c["regions"],
                        "openings": c["flashes"] + c["regions"]}

    # --- a second and third opinion: IPC-D-356 and the .gbrjob ------------
    out["ipc_d356"] = check_ipc(a.root, layers)
    out["gbrjob"] = check_gbrjob(fabdir, out.get("outline", {}))
    out["odb"] = check_odb(a.root)

    pth = drills.get("PTH")
    if pth:
        out["pth"] = {"hits": len(pth["hits"]),
                      "tools": pth["tools"],
                      "slots": sum(1 for h in pth["hits"] if h["slot"])}

    # --- comparison with the package JLC has already seen ------------------
    old = compare_old(a.root)
    if old:
        out["vs_2026_08_16"] = old

    if a.json:
        print(json.dumps(out, indent=1))
    else:
        report(out)
    ok = (not out["missing_layers"] and out.get("all_parsed")
          and out.get("outline", {}).get("ok") and out["npth"]["ok"]
          and out["npth_clear"] and out.get("planes_filled")
          and out["ipc_d356"].get("npth_ok")
          and out["ipc_d356"].get("nets", {}).get("match")
          and out["ipc_d356"].get("gerber_x2_agreement", {}).get("ok")
          and out["gbrjob"].get("ok"))
    return 0 if ok else 1


def check_ipc(root, layers):
    """IPC-D-356: the net of every feature, stated as data rather than drawn.

    KiCad writes this through a different code path than the Gerbers, so where
    the two agree the agreement means something. What it can and cannot settle
    is measured here rather than assumed -- in particular the reference
    designator field is six characters and this board has twelve-character
    designators, so the designator map is NOT recoverable and ACCEPTANCE B
    stays with pcbnew. The net field is fourteen and the longest net name here
    is exactly fourteen, so the net set is complete.
    """
    path = os.path.join(root, "fab", "board.d356")
    if not os.path.exists(path):
        return {"present": False}
    doc = IPC.parse(path)
    feats = doc["features"]
    out = {"present": True, "features": len(feats),
           "unparsed_lines": len(doc["unknown"]), "header": doc["header"],
           "vias": len(IPC.vias(feats)),
           "smd": sum(1 for f in feats if f.kind == "smd"),
           "through_pads": sum(1 for f in feats
                               if f.kind == "through" and not f.is_via),
           "npth": len(IPC.npth(feats))}

    # net set against the contract, with the ECO-5 override applied
    contract = E.load_json(os.path.join(root, "contract",
                                        "netlist_contract.json"))
    over = {}
    opath = os.path.join(root, "contract", "contract_overrides.json")
    if os.path.exists(opath):
        for o in E.load_json(opath).get("overrides", ()):
            over[(o["designator"], str(o["pad"]))] = o["override_net"]
    want = set()
    for ref, pads in contract["by_designator"].items():
        for num, info in pads.items():
            net = over.get((ref, num), info.get("net", ""))
            if net and net != "NC":
                want.add(net)
    got = IPC.nets(feats)
    out["nets"] = {"in_d356": len(got), "in_contract": len(want),
                   "only_in_d356": sorted(got - want),
                   "only_in_contract": sorted(want - got),
                   "match": got == want,
                   "longest_name": max((len(n) for n in want), default=0),
                   "field_width": 14}

    # the six holes, at this file's own resolution
    holes = []
    for name, hx, hy, dia in NPTH:
        f = next((f for f in IPC.npth(feats) if f.ref == name), None)
        if f is None:
            holes.append({"hole": name, "found": False})
            continue
        bx, by = f.to_board()
        holes.append({"hole": name, "found": True,
                      "board_mm": [round(bx, 4), round(by, 4)],
                      "offset_mm": round(((bx - hx) ** 2
                                          + (by + hy) ** 2) ** 0.5, 6),
                      "drill_mm": round(f.drill_mm, 4),
                      "unplated": f.plated is False})
    out["npth_holes"] = holes
    out["npth_ok"] = (len(holes) == 6
                      and all(h.get("found") and h["unplated"]
                              and h["offset_mm"] <= 0.003 for h in holes))
    out["resolution_mm"] = IPC.MIL10
    out["origin_mm"] = list(IPC.ORIGIN_MM)

    # what the six-character designator field costs
    import collections
    coll = collections.Counter(r[:6] for r in contract["by_designator"])
    out["designator_field"] = {
        "width": 6,
        "longest_designator": max(len(r) for r in contract["by_designator"]),
        "designators": len(contract["by_designator"]),
        "distinct_after_truncation": len(coll),
        "colliding_prefixes": {k: v for k, v in sorted(coll.items())
                               if v > 1},
        "usable_for_acceptance_b": len(coll) == len(contract["by_designator"])}

    # the three-way check: does the Gerber's own X2 net agree with this file?
    fc = layers.get("gtl")
    if fc is not None:
        flashes = fc.flash_nets()
        agree = miss = wrong = 0
        bad = []
        for f in feats:
            if f.kind != "smd":
                continue
            bx, by = f.to_board()
            gy = -by
            best = None
            for x, y, n in flashes:
                d = abs(x - bx) + abs(y - gy)
                if best is None or d < best[0]:
                    best = (d, n)
            if best is None or best[0] > 0.006:
                miss += 1
                bad.append({"ref": f.ref, "pin": f.pin, "net": f.net,
                            "issue": "no F.Cu flash within 6 um"})
            elif best[1] != f.net:
                wrong += 1
                bad.append({"ref": f.ref, "pin": f.pin, "d356": f.net,
                            "gerber": best[1]})
            else:
                agree += 1
        out["gerber_x2_agreement"] = {
            "smd_pads": agree + miss + wrong, "agree": agree,
            "no_flash": miss, "net_differs": wrong,
            "disagreements": bad[:10],
            "ok": miss == 0 and wrong == 0,
            "gerber_attr_sets": fc.attr_sets,
            "gerber_attr_deletes": fc.attr_deletes,
            "flashes_carrying_a_net": len(flashes),
            "flashes": len(fc.flashes)}
    return out


def check_gbrjob(fabdir, outline):
    """The .gbrjob is JSON, and a second statement of the same facts."""
    paths = glob.glob(os.path.join(fabdir, "*.gbrjob"))
    if not paths:
        return {"present": False}
    doc = json.load(open(paths[0]))
    gs = doc.get("GeneralSpecs", {})
    stack = doc.get("MaterialStackup", [])
    copper = [e for e in stack if e.get("Type") == "Copper"]
    rules = doc.get("DesignRules", [])
    size = gs.get("Size", {})
    # Size is the plotted extent, so it is the profile plus one pen width; the
    # Edge.Cuts stroke is 0.1016 mm, which is exactly the difference.
    pen = 0.1016
    exp = outline.get("expected") or [0, 0]
    out = {"present": True, "file": os.path.basename(paths[0]),
           "layer_number": gs.get("LayerNumber"),
           "board_thickness_mm": gs.get("BoardThickness"),
           "size_mm": size,
           "size_matches_outline_plus_pen": (
               abs(size.get("X", 0) - (exp[0] + pen)) < 0.002
               and abs(size.get("Y", 0) - (exp[1] + pen)) < 0.002),
           "copper_layers_in_stackup": len(copper),
           "stackup_entries": len(stack),
           "files_attributes": len(doc.get("FilesAttributes", [])),
           "design_rules": rules,
           "clearance_mm": min((r.get("TrackToTrack") for r in rules
                                if r.get("TrackToTrack") is not None),
                               default=None)}
    out["ok"] = (out["layer_number"] == 4
                 and abs((out["board_thickness_mm"] or 0) - 1.6) < 1e-9
                 and out["copper_layers_in_stackup"] == 4
                 and out["size_matches_outline_plus_pen"]
                 and abs((out["clearance_mm"] or 0) - 0.0889) < 1e-9)
    return out


def check_odb(root):
    """ODB++ carries its own netlist -- a third statement of the net set."""
    path = os.path.join(root, "fab", "odb", "steps", "pcb", "netlists",
                        "cadnet", "netlist")
    if not os.path.exists(path):
        return {"present": False}
    names, points = set(), 0
    for line in open(path, errors="replace"):
        s = line.strip()
        if s.startswith("$"):
            parts = s.split(None, 1)
            if len(parts) == 2 and parts[1] != "$NONE$":
                names.add(parts[1])
        elif s and s[0].isdigit():
            points += 1
    return {"present": True, "nets": len(names), "netlist_points": points,
            "names": sorted(names)}


def compare_old(root):
    """The 2026-08-16 EasyEDA package: same outline, same holes, same layers?"""
    import tempfile
    import zipfile
    zpath = os.path.join(os.path.dirname(root), "cerelog_research",
                         "fab_2026-08-16", "Therapia_EEG-HRV_Gerber.zip")
    if not os.path.exists(zpath):
        return None
    tmp = tempfile.mkdtemp(prefix="oldgerber")
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        for n in names:
            if n.endswith(("GKO", "DRL")):
                z.extract(n, tmp)
    res = {"archive": zpath, "files": len(names)}
    gko = glob.glob(os.path.join(tmp, "*.GKO"))
    if gko:
        lay = G.parse_gerber(gko[0])
        box = lay.centreline_bbox()
        if box:
            res["outline_mm"] = [round(box[2] - box[0], 4),
                                 round(box[3] - box[1], 4)]
    npth = glob.glob(os.path.join(tmp, "*NPTH*.DRL"))
    if npth:
        d = G.parse_excellon(npth[0])
        res["npth_hits"] = len(d["hits"])
        res["npth_tools"] = d["tools"]
        res["npth_xy"] = sorted([round(h["x"], 4), round(h["y"], 4)]
                                for h in d["hits"])
    return res


def report(o):
    print("fab package: %s" % o["dir"])
    print("  layers %s   drill %s" % (",".join(o["layers_found"]),
                                      ",".join(o["drill_files"])))
    if o["missing_layers"]:
        print("  MISSING: %s" % ", ".join(o["missing_layers"]))
    if o["unexpected_files"]:
        print("  unexpected: %s" % ", ".join(o["unexpected_files"]))
    ol = o.get("outline", {})
    print("  outline %.4f x %.4f mm  %s"
          % (ol.get("width_mm", 0), ol.get("height_mm", 0),
             "ok" if ol.get("ok") else "OUT OF TOLERANCE"))
    print("  every layer parsed at 4.6 mm with no unknown aperture: %s"
          % o.get("all_parsed"))
    for name, s in sorted(o["layers"].items()):
        print("    %-10s ap %-3d flash %-5d draw %-6d region %-4d"
              " clear %-4d %s%s"
              % (name, s["apertures"], s["flashes"], s["draws"],
                 s["regions"],
                 s["clear_flashes"] + s["clear_draws"] + s["clear_regions"],
                 s["file_function"] or "",
                 "  (empty)" if s["empty"] else ""))
    print("  copper layers additive only (no clear polarity): %s"
          % o.get("copper_all_dark"))
    if o.get("empty_layers"):
        print("  empty by design: %s" % ", ".join(o["empty_layers"]))
    print("  NPTH %d holes, all within 2 um of ACCEPTANCE D: %s"
          % (o["npth"]["count"], o["npth"]["ok"]))
    for h in o["npth"]["holes"]:
        print("    %-5s %s off %s mm dia %s"
              % (h["hole"], h["found"], h["offset_mm"],
                 "ok" if h["dia_ok"] else "WRONG"))
    print("  copper inside hole+0.2 mm: %s"
          % ("none" if o["npth_clear"] else o["copper_in_npth_rings"]))
    if "copper_coverage" in o:
        print("  copper coverage %s -> planes filled: %s"
              % (o["copper_coverage"], o["planes_filled"]))
    if "pth" in o:
        print("  PTH %d hits, %d slots, %d tools"
              % (o["pth"]["hits"], o["pth"]["slots"], len(o["pth"]["tools"])))
    if "paste" in o:
        print("  F.Paste openings %d (%d flashes + %d regions)"
              % (o["paste"]["openings"], o["paste"]["flashes"],
                 o["paste"]["regions"]))
    ipc = o.get("ipc_d356", {})
    if ipc.get("present"):
        n = ipc["nets"]
        x2 = ipc.get("gerber_x2_agreement", {})
        d = ipc["designator_field"]
        print("  IPC-D-356: %d features (%d via / %d smd / %d PTH pad / %d NPTH)"
              % (ipc["features"], ipc["vias"], ipc["smd"],
                 ipc["through_pads"], ipc["npth"]))
        print("    nets %d vs contract %d -> match %s"
              % (n["in_d356"], n["in_contract"], n["match"]))
        print("    NPTH 6 unplated, within %.1f um: %s"
              % (ipc["resolution_mm"] * 1000, ipc["npth_ok"]))
        print("    Gerber X2 net agrees on %d/%d top pads (%d TO sets, %d TD)"
              % (x2.get("agree", 0), x2.get("smd_pads", 0),
                 x2.get("gerber_attr_sets", 0),
                 x2.get("gerber_attr_deletes", 0)))
        print("    designator field is %d chars, longest here %d -> %d of %d "
              "survive; NOT usable for ACCEPTANCE B"
              % (d["width"], d["longest_designator"],
                 d["distinct_after_truncation"], d["designators"]))
    gj = o.get("gbrjob", {})
    if gj.get("present"):
        print("  .gbrjob: %s layers, %s mm thick, %d copper in stackup, "
              "clearance %s -> %s"
              % (gj["layer_number"], gj["board_thickness_mm"],
                 gj["copper_layers_in_stackup"], gj["clearance_mm"],
                 gj["ok"]))
    odb = o.get("odb", {})
    if odb.get("present"):
        print("  ODB++: %d nets, %d netlist points" % (odb["nets"],
                                                       odb["netlist_points"]))
    if "vs_2026_08_16" in o:
        v = o["vs_2026_08_16"]
        print("  vs 2026-08-16: outline %s, NPTH %s hits %s"
              % (v.get("outline_mm"), v.get("npth_hits"),
                 v.get("npth_tools")))


if __name__ == "__main__":
    sys.exit(main())
