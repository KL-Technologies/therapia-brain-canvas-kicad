#!/usr/bin/env python3
"""S2c: read the imported board back with pcbnew and prove nothing was lost.

Produces gates/inventory_kicad.json (the same measurements taken on the KiCad
side) and gates/S2.json (the reconciliation). The net-membership comparison is
the one that matters most: KiCad #19021 collapses every pad onto a single net,
and it is silent -- the import "succeeds" and the board looks right on screen.

Two things are compared separately on purpose:
  import fidelity   EasyEDA inventory vs KiCad board. These checks gate S2.
  design expectation the values the team brief carries over from the
                    2026-08-16 analysis. Recorded, never gated here: a
                    disagreement means the design moved, not that the import
                    broke, and S3 needs to see it rather than have it hidden.

Must run under the KiCad-bundled python (needs pcbnew).
"""

import os
import re
import sys
import json
import argparse
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import epro as E                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD_NAME = "Therapia_EEG-HRV"
IU_PER_MM = 1e6


def mm(v):
    return round(float(v) / IU_PER_MM, 6)


def board_inventory(board, pcbnew):
    fps = list(board.GetFootprints())
    comps, net_pads, pad_rows = {}, collections.Counter(), []
    rot = collections.Counter()
    pads_total = 0
    anonymous = []

    for f in fps:
        ref = f.GetReference()
        pos = f.GetPosition()
        r = round(f.GetOrientationDegrees() % 360.0, 3)
        pads = list(f.Pads())
        pads_total += len(pads)
        entry = {"x_mm": mm(pos.x), "y_mm": mm(pos.y), "rotation": r,
                 "layer": board.GetStandardLayerName(f.GetLayer()),
                 "on_front": f.GetLayer() == pcbnew.F_Cu,
                 "pads": len(pads), "value": f.GetValue()}
        if ref:
            rot[r] += 1
            comps[ref] = entry
        else:
            anonymous.append(dict(entry, pad_numbers=[p.GetNumber() for p in pads]))
        for p in pads:
            n = p.GetNetname()
            if n:
                net_pads[n] += 1
            pp = p.GetPosition()
            drill = p.GetDrillSize()
            pad_rows.append({
                "ref": ref, "pad": p.GetNumber(), "net": n,
                "x_mm": mm(pp.x), "y_mm": mm(pp.y),
                "attr": int(p.GetAttribute()),
                "npth": int(p.GetAttribute()) == int(pcbnew.PAD_ATTRIB_NPTH),
                "drill_mm": [mm(drill.x), mm(drill.y)]})

    # The import keeps EasyEDA's layer captions ("Top Layer"), so compare on the
    # canonical KiCad names instead -- the EasyEDA inventory is keyed that way.
    def lname(item):
        return board.GetStandardLayerName(item.GetLayer())

    tracks_by_layer, arcs_by_layer = collections.Counter(), collections.Counter()
    vias = 0
    for t in board.GetTracks():
        cls = t.GetClass()
        if cls == "PCB_VIA":
            vias += 1
        elif cls == "PCB_ARC":
            arcs_by_layer[lname(t)] += 1
        else:
            tracks_by_layer[lname(t)] += 1

    zones = [{"net": z.GetNetname(), "layer": board.GetStandardLayerName(z.GetLayer()),
              "priority": z.GetAssignedPriority(),
              "is_rule_area": bool(z.GetIsRuleArea()),
              "filled": bool(z.IsFilled())} for z in board.Zones()]

    holes = [{"source": "PAD", "ref": r["ref"], "pad": r["pad"], "net": r["net"],
              "x_mm": r["x_mm"], "y_mm": r["y_mm"],
              "dia_mm": max(r["drill_mm"]), "size_mm": r["drill_mm"],
              "npth": r["npth"]}
             for r in pad_rows if max(r["drill_mm"]) > 0]
    # Milled shapes reach KiCad as Edge.Cuts drawings -- board-level for the
    # outline, and INSIDE the footprint for anything the footprint owned. The
    # USB-C pegs are footprint-level polygons on Edge.Cuts, so scanning only
    # board drawings would report them missing.
    edge_shapes, edge_pts = [], []

    def scan_shape(d, owner):
        if d.GetClass() != "PCB_SHAPE":
            return
        st = int(d.GetShape())
        on_edge = d.GetLayer() == pcbnew.Edge_Cuts
        entry = {"owner": owner, "layer": board.GetStandardLayerName(d.GetLayer()),
                 "shape": st}
        c = d.GetCenter()
        entry.update({"cx_mm": mm(c.x), "cy_mm": mm(c.y)})
        bb = d.GetBoundingBox()
        dia = round(min(mm(bb.GetWidth()), mm(bb.GetHeight())), 6)
        if st == pcbnew.SHAPE_T_CIRCLE:
            dia = round(mm(d.GetRadius()) * 2, 6)
        entry["dia_mm"] = dia
        edge_shapes.append(entry)
        if not on_edge:
            return
        if owner:                      # footprint-owned: a milled feature
            holes.append({"source": "EdgeCuts.shape%d" % st, "ref": owner,
                          "pad": "", "net": "", "x_mm": entry["cx_mm"],
                          "y_mm": entry["cy_mm"], "dia_mm": dia,
                          "size_mm": [dia, dia], "npth": False,
                          "note": "milled outline, not a drilled NPTH pad"})
            return                     # board outline comes from board level only
        if st == pcbnew.SHAPE_T_CIRCLE:
            r = round(dia / 2, 6)
            holes.append({"source": "EdgeCuts.circle", "ref": "", "pad": "",
                          "net": "", "x_mm": entry["cx_mm"], "y_mm": entry["cy_mm"],
                          "dia_mm": dia, "size_mm": [dia, dia], "npth": False})
            edge_pts.extend([(entry["cx_mm"] - r, entry["cy_mm"] - r),
                             (entry["cx_mm"] + r, entry["cy_mm"] + r)])
        else:
            edge_pts.append((mm(d.GetStart().x), mm(d.GetStart().y)))
            edge_pts.append((mm(d.GetEnd().x), mm(d.GetEnd().y)))

    for d in board.GetDrawings():
        scan_shape(d, "")
    for f in fps:
        for d in f.GraphicalItems():
            scan_shape(d, f.GetReference() or "(anon)")

    # GetBoardEdgesBoundingBox() pads the box by the outline's line width
    # (4 mil here), which would read 61.925 x 45.111 instead of the drawn size.
    xs = [p[0] for p in edge_pts] or [0.0]
    ys = [p[1] for p in edge_pts] or [0.0]
    copper = board.GetCopperLayerCount()

    return {
        "footprints": {"count": len(fps), "named_count": len(comps),
                       "anonymous_count": len(anonymous),
                       "designators": sorted(comps),
                       "anonymous": anonymous,
                       "by_designator": comps},
        "pads": {"total": pads_total},
        "nets": {"board_net_count": board.GetNetCount(),
                 "with_pads_count": len(net_pads),
                 "pad_counts": dict(sorted(net_pads.items()))},
        "tracks": {"total": sum(tracks_by_layer.values()),
                   "by_layer": dict(sorted(tracks_by_layer.items()))},
        "arcs": {"total": sum(arcs_by_layer.values()),
                 "by_layer": dict(sorted(arcs_by_layer.items()))},
        "vias": {"total": vias},
        "zones": {"count": len(zones), "list": zones},
        "holes": holes,
        "edge_shapes": edge_shapes,
        "copper_layers": copper,
        "outline_bbox_mm": {"min_x_mm": min(xs), "max_x_mm": max(xs),
                            "min_y_mm": min(ys), "max_y_mm": max(ys),
                            "width_mm": round(max(xs) - min(xs), 4),
                            "height_mm": round(max(ys) - min(ys), 4),
                            "basis": "Edge.Cuts centrelines"},
        "rotations": {str(k): v for k, v in sorted(rot.items(), key=lambda kv: kv[0])},
        "_pad_rows": pad_rows,
    }


def rigid_offset(easyeda_pts, kicad_pts, tol=0.01):
    """EasyEDA y is negative-downward, KiCad y positive-downward: expected KiCad
    position of EasyEDA (x, y) is (x, -y). Recover any additional whole-board
    translation the importer applied, by majority vote over hole positions."""
    votes = collections.Counter()
    for ex, ey in easyeda_pts:
        for kx, ky in kicad_pts:
            votes[(round(kx - ex, 3), round(ky + ey, 3))] += 1
    if not votes:
        return (0.0, 0.0)
    if votes.get((0.0, 0.0), 0) == len(easyeda_pts):
        return (0.0, 0.0)
    return max(votes.items(), key=lambda kv: kv[1])[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--board")
    args = ap.parse_args()
    root = args.root
    board_path = args.board or os.path.join(root, "board", BOARD_NAME + ".kicad_pcb")

    try:
        import pcbnew
    except ImportError:
        print("pcbnew unavailable -- run this with the KiCad-bundled python (KPY)")
        return 2
    if not os.path.exists(board_path):
        print("board not found: %s (run 11_import_epro.py first)" % board_path)
        return 2

    inv_e = E.load_json(os.path.join(root, "gates", "inventory_easyeda.json"))
    board = pcbnew.LoadBoard(board_path)
    inv_k = board_inventory(board, pcbnew)
    pad_rows = inv_k.pop("_pad_rows")
    inv_k["source"] = {"board": os.path.abspath(board_path),
                       "kicad": pcbnew.GetBuildVersion()}
    E.dump_json(os.path.join(root, "gates", "inventory_kicad.json"), inv_k)
    E.dump_json(os.path.join(root, "contract", "netlist_from_kicad_pcb.json"),
                {"source": inv_k["source"],
                 "note": "designator -> pad -> net as KiCad now holds it",
                 "pads": pad_rows})

    checks, notes, observations = [], [], {}

    # ---- footprints -------------------------------------------------------
    e_des = set(inv_e["footprints"]["designators"])
    k_des = set(inv_k["footprints"]["designators"])
    only_e, only_k = sorted(e_des - k_des), sorted(k_des - e_des)
    n_standalone = inv_e["pads"]["standalone"]
    checks.append(E.gate_check("component_count", len(e_des),
                               inv_k["footprints"]["named_count"]))
    checks.append(E.gate_check("designator_set_identical", "no difference",
                               {"only_in_easyeda": only_e[:40],
                                "only_in_kicad": only_k[:40]},
                               ok=(not only_e and not only_k)))
    checks.append(E.gate_check(
        "standalone_pads_became_footprints", n_standalone,
        inv_k["footprints"]["anonymous_count"],
        note="EasyEDA's board-level pads (the M2 mounting holes) have no "
             "designator, so KiCad wraps each in its own unnamed footprint. "
             "Total KiCad footprints = %d components + %d = %d."
             % (len(e_des), n_standalone, inv_k["footprints"]["count"])))
    checks.append(E.gate_check("pad_total", inv_e["pads"]["total"],
                               inv_k["pads"]["total"]))

    # ---- nets -------------------------------------------------------------
    ep, kp = inv_e["nets"]["pad_counts"], inv_k["nets"]["pad_counts"]
    net_diff = [{"net": n, "easyeda": ep.get(n, 0), "kicad": kp.get(n, 0)}
                for n in sorted(set(ep) | set(kp)) if ep.get(n, 0) != kp.get(n, 0)]
    checks.append(E.gate_check("net_count", len(ep), len(kp)))
    checks.append(E.gate_check("net_membership_identical", "0 differing nets",
                               {"differing": len(net_diff), "detail": net_diff[:60]},
                               ok=(not net_diff)))
    biggest = max(kp.items(), key=lambda kv: kv[1]) if kp else ("", 0)
    merged = bool(kp) and biggest[1] >= inv_k["pads"]["total"] * 0.9 and len(kp) <= 3
    checks.append(E.gate_check(
        "issue_19021_nets_not_merged", "not merged",
        "MERGED onto '%s' (%d/%d pads)" % (biggest[0], biggest[1], inv_k["pads"]["total"])
        if merged else "ok (%d nets, largest '%s'=%d pads)"
        % (len(kp), biggest[0], biggest[1]),
        ok=(not merged)))

    # ---- copper -----------------------------------------------------------
    e_tot = collections.Counter(inv_e["tracks"]["by_layer"])
    e_tot.update(inv_e["arcs"]["by_layer"])
    k_tot = collections.Counter(inv_k["tracks"]["by_layer"])
    k_tot.update(inv_k["arcs"]["by_layer"])
    lay_diff = {l: {"easyeda": e_tot.get(l, 0), "kicad": k_tot.get(l, 0)}
                for l in sorted(set(e_tot) | set(k_tot))
                if e_tot.get(l, 0) != k_tot.get(l, 0)}
    checks.append(E.gate_check("tracks_arcs_per_layer", "identical",
                               lay_diff or "identical", ok=(not lay_diff)))
    if lay_diff:
        notes.append("track/arc per-layer differences %s -- most likely arc-to-"
                     "segment splitting; S3 must confirm copper length per net "
                     "is unchanged before trusting it." % json.dumps(lay_diff))
    checks.append(E.gate_check("vias", inv_e["vias"]["total"], inv_k["vias"]["total"]))
    checks.append(E.gate_check("zone_count", inv_e["zones"]["pour_count"],
                               inv_k["zones"]["count"]))
    checks.append(E.gate_check("copper_layers", 4, inv_k["copper_layers"]))

    # ---- geometry ---------------------------------------------------------
    e_holes = [h for h in inv_e["npth"]["holes_found"] if h["x_mm"] is not None]
    off = rigid_offset([(h["x_mm"], h["y_mm"]) for h in e_holes],
                       [(h["x_mm"], h["y_mm"]) for h in inv_k["holes"]])
    hole_rows, found = [], 0
    for h in e_holes:
        tx, ty = h["x_mm"] + off[0], -h["y_mm"] + off[1]
        hit = next((k for k in inv_k["holes"]
                    if E.approx(k["x_mm"], tx, 0.01) and E.approx(k["y_mm"], ty, 0.01)), None)
        if hit:
            found += 1
        hole_rows.append({"ref": h["ref"], "pad": h["pad"],
                          "easyeda_mm": [h["x_mm"], h["y_mm"]],
                          "expected_kicad_mm": [round(tx, 6), round(ty, 6)],
                          "dia_mm": h["dia_mm"], "found": hit})
    checks.append(E.gate_check(
        "all_easyeda_holes_present", "%d/%d within 0.01mm" % (len(e_holes), len(e_holes)),
        "%d/%d (board offset %s mm)" % (found, len(e_holes), list(off)),
        ok=(found == len(e_holes))))
    if off != (0.0, 0.0):
        notes.append("KiCad relocated the board origin by %s mm. Geometry is "
                     "intact, but every EasyEDA-derived coordinate in the ECO "
                     "notes must be shifted by this before use in KiCad."
                     % (list(off),))

    ow = inv_k["outline_bbox_mm"]["width_mm"]
    oh = inv_k["outline_bbox_mm"]["height_mm"]
    checks.append(E.gate_check(
        "outline_size_mm", list(E.EXPECTED_OUTLINE_MM), [ow, oh],
        ok=(E.approx(ow, E.EXPECTED_OUTLINE_MM[0], 0.01)
            and E.approx(oh, E.EXPECTED_OUTLINE_MM[1], 0.01))))

    krots = set()
    for k in inv_k["rotations"]:
        try:
            krots.add(round(float(k) % 360.0, 3))
        except ValueError:
            krots.add(k)
    checks.append(E.gate_check("rotations_subset_of_0_90_180_270", "subset",
                               sorted(map(str, krots)),
                               ok=krots.issubset(E.EXPECTED_ROTATIONS)))
    rot_bad = []
    for ref, kc in inv_k["footprints"]["by_designator"].items():
        ec = inv_e["footprints"]["by_designator"].get(ref)
        if not ec:
            continue
        try:
            if round(float(ec["rotation"]) % 360.0, 1) != round(float(kc["rotation"]) % 360.0, 1):
                rot_bad.append({"ref": ref, "easyeda": ec["rotation"],
                                "kicad": kc["rotation"]})
        except (TypeError, ValueError):
            pass
    checks.append(E.gate_check("rotation_per_component", "identical",
                               {"mismatched": len(rot_bad), "detail": rot_bad[:30]},
                               ok=(not rot_bad)))
    bottom = [r for r, v in inv_k["footprints"]["by_designator"].items()
              if not v["on_front"]]
    checks.append(E.gate_check("all_components_on_top", "0 on bottom",
                               bottom[:20], ok=(not bottom)))

    # ---- design observations (recorded, not gated) ------------------------
    by_ref = collections.defaultdict(dict)
    for r in pad_rows:
        if r["ref"]:
            by_ref[r["ref"]][r["pad"]] = r["net"]

    brief_npth = []
    for name, ex, ey, ed in E.EXPECTED_NPTH:
        tx, ty = ex + off[0], -ey + off[1]
        hit = next((k for k in inv_k["holes"]
                    if E.approx(k["x_mm"], tx, 0.01) and E.approx(k["y_mm"], ty, 0.01)), None)
        brief_npth.append({"name": name, "expected_easyeda_mm": [ex, ey],
                           "expected_kicad_mm": [round(tx, 6), round(ty, 6)],
                           "expected_dia_mm": ed, "found": hit,
                           "is_npth": bool(hit) and hit.get("npth")})
    observations["brief_npth_expectation"] = {
        "geometry_present": sum(1 for b in brief_npth if b["found"]),
        "actually_npth": sum(1 for b in brief_npth if b["is_npth"]),
        "of": len(brief_npth), "detail": brief_npth}

    # ---- known import defects (expected failures, owned by 13_fix_import.py)
    npth_pads = [h for h in inv_k["holes"] if h.get("npth")]
    m2 = [h for h in inv_k["holes"]
          if h["source"] == "PAD" and not h["ref"] and h["dia_mm"] > 2.0]
    pegs = [h for h in inv_k["holes"] if h["source"].startswith("EdgeCuts.shape")]
    observations["known_import_defects"] = {
        "note": "As-imported state. Each of these is a KiCad EasyEDA-importer "
                "behaviour, not lost data -- the geometry is all present. "
                "13_fix_import.py is expected to correct them.",
        "npth_pad_count": {"expected_after_fix": 6, "as_imported": len(npth_pads),
                           "expected_fail": True},
        "mounting_holes_are_PTH": {
            "expected_fail": True,
            "detail": [{"footprint": h["ref"] or "(anon)", "pad": h["pad"],
                        "dia_mm": h["dia_mm"], "npth": h["npth"]} for h in m2],
            "note": "The importer makes every pad with drill>0 a PTH. The four "
                    "M2 holes arrive as single-pad footprints Pad_<uuid> with "
                    "drill == pad size. Fix: SetAttribute(PAD_ATTRIB_NPTH), no "
                    "copper."},
        "usb_pegs_are_edge_cuts_shapes": {
            "expected_fail": True,
            "detail": pegs,
            "note": "The two 0.7mm positioning pegs are FILL records with a "
                    "CIRCLE path on EasyEDA layer 12 (Multi) inside the USB-C "
                    "footprint. Layer 12 maps to Edge.Cuts, so they arrive as "
                    "Edge.Cuts polygons owned by J1 -- correct position and "
                    "size, but they will not appear in the NPTH drill file. "
                    "Fix: replace with NPTH pads at the coordinates above."},
        "no_kicad_pro_design_rules": {
            "expected_fail": True,
            "note": "board/*.kicad_pro is a minimal stub. JLC 4-layer rules "
                    "(clearance 0.0889mm, hole-to-hole 0.2, edge 0.2, via drill "
                    ">=0.3, annular >=0.076 ...) still have to be written, with "
                    "the EasyEDA values in contract/easyeda_rules.json as the "
                    "reference."},
    }

    fb5 = by_ref.get("FB5", {})
    observations["FB5"] = {"pads": fb5,
                           "reading": "FB5 pin1=%s pin2=%s"
                                      % (fb5.get("1"), fb5.get("2"))}
    notes.append("FB5 pin1=%s pin2=%s" % (fb5.get("1"), fb5.get("2")))
    checks.append(E.gate_check("FB5_present", "present", fb5 or "missing",
                               ok=bool(fb5)))

    ads_ref = next((r for r in by_ref if re.search(r"ADS", r, re.I)), None)
    if not ads_ref:
        ads_ref = next((r for r, p in by_ref.items() if len(p) >= 60), None)
    observations["ADS1299"] = {"ref": ads_ref,
                               "pads": by_ref.get(ads_ref, {}) if ads_ref else {}}
    for ref in ("TPS72325", "U_NLDO", "U_TPS"):
        if ref in by_ref:
            observations["TPS72325"] = {"ref": ref, "pads": by_ref[ref]}
            break
    else:
        cand = [r for r in by_ref if re.search(r"NLDO|TPS", r, re.I)]
        if cand:
            observations["TPS72325"] = {"ref": cand[0], "pads": by_ref[cand[0]]}

    key_nets = ("GND", "AVDD", "AVSS", "DVDD", "VDD_ESP", "USB_5V",
                "CHASSIS_GND", "V_NLDO_IN", "VNEG5")
    observations["net_pad_counts"] = {n: kp.get(n, 0) for n in key_nets}

    tps = (observations.get("TPS72325") or {}).get("pads", {})
    ads_pads = (observations.get("ADS1299") or {}).get("pads", {})
    unnetted = sorted((p for p, n in ads_pads.items() if not n), key=int)
    observations["eco1_state"] = {
        "AVDD_pads": kp.get("AVDD", 0),
        "TPS72325_pin3_EN": tps.get("3"),
        "ADS1299_pads_with_no_net": unnetted,
        "verdict": "NOT APPLIED" if tps.get("3") == "GND" else "check manually",
        "reading":
            "ECO-1 item 1 requires TPS72325 pin3 (EN) to move from GND to "
            "V_NLDO_IN; it currently reads %r, so the fatal B1 condition is "
            "still on this board. PROJECT_STATUS records AVDD=21 before ECO-1 "
            "and 20 after, and this board has %d. Both say the same thing: the "
            "schematic-side ECO-1 was never pushed into the PCB (Import "
            "Changes was not run), so the KiCad board S3 receives is the "
            "PRE-ECO layout and must take ECO-1 as well as L1-L6."
            % (tps.get("3"), kp.get("AVDD", 0)),
        "caveat": "Pin functions (RESV1, GPIO1-4, VCAP2/3) cannot be read off "
                  "the PCB -- only pad numbers exist there. The unconnected "
                  "ADS1299 pads are listed above; map them to pin names via the "
                  "schematic symbol before acting."}
    notes.append("ECO-1 %s on the PCB: TPS72325 pin3(EN)=%r, AVDD pads=%d"
                 % (observations["eco1_state"]["verdict"], tps.get("3"),
                    kp.get("AVDD", 0)))

    drc_path = os.path.join(root, "logs", "drc_import.json")
    if os.path.exists(drc_path):
        d = E.load_json(drc_path)
        by_type = collections.Counter(v.get("type") for v in d.get("violations", []))
        by_sev = collections.Counter(v.get("severity") for v in d.get("violations", []))
        observations["drc_at_import"] = {
            "violations": len(d.get("violations", [])),
            "unconnected": len(d.get("unconnected_items", [])),
            "by_type": dict(by_type.most_common()),
            "by_severity": dict(by_sev),
            "note": "Informational only. Run against KiCad DEFAULT design rules "
                    "-- the EasyEDA constraints were not transferred (see "
                    "contract/easyeda_rules.json). Counts are not comparable to "
                    "the EasyEDA DRC until S3 sets the rules up."}

    E.dump_json(os.path.join(root, "gates", "design_observations.json"), observations)

    E.write_gate(os.path.join(root, "gates", "S2.json"), "S2", checks,
                 notes=" | ".join(notes),
                 extra={"hole_detail": hole_rows, "net_differences": net_diff[:200],
                        "layer_differences": lay_diff,
                        "board_offset_mm": list(off),
                        "design_observations": "gates/design_observations.json"})
    ok = all(c["pass"] for c in checks)
    print("S2 pass=%s (%d/%d checks)"
          % (ok, sum(c["pass"] for c in checks), len(checks)))
    for c in checks:
        if not c["pass"]:
            print("  FAIL %s: expected=%s actual=%s"
                  % (c["name"], json.dumps(c["expected"])[:90],
                     json.dumps(c["actual"])[:160]))
    b = observations["brief_npth_expectation"]
    print("FB5 pin1=%s pin2=%s | AVDD pads=%d | 6 mounting holes: %d/6 present as "
          "geometry, %d/6 actually NPTH (known defect, 13_fix_import.py)"
          % (fb5.get("1"), fb5.get("2"), kp.get("AVDD", 0),
             b["geometry_present"], b["actually_npth"]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
