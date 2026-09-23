#!/usr/bin/env python3
"""S7d -- ACCEPTANCE.md A to G, mechanised.

    KPY scripts/50_final_check.py        (run OUTSIDE the command sandbox)

ACCEPTANCE.md is frozen and this is its implementation. Nothing here relaxes a
criterion; where the document names a number, that number is written out below
next to the measurement, so a reader can check the code against the document
rather than trusting that it was read correctly.

Run after 60_export_fab.sh and 61_make_bom_cpl.py -- D, E, F and G all read the
package those produce.

Result: gates/S7.json.
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import drc as D                                    # noqa: E402
import epro as E                                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# ACCEPTANCE A: types allowed to remain, at warning severity.
ALLOWED_WARNINGS = {
    "courtyards_overlap", "silk_overlap", "silk_over_copper",
    "silk_edge_clearance", "starved_thermal", "track_dangling", "via_dangling",
    "isolated_copper", "copper_sliver", "holes_co_located",
    "footprint_type_mismatch",
    # ACCEPTANCE C makes the 5 mil track-to-track recommendation a warning; the
    # error-level 0.0889 mm rule stays an error and is counted as one.
    "clearance",
}
# ACCEPTANCE A: must still be errors. If any of these appears at warning
# severity the rules have been relaxed and the document is void.
MUST_BE_ERRORS = {
    "clearance", "hole_clearance", "hole_to_hole", "hole_near_hole",
    "copper_edge_clearance", "shorting_items", "tracks_crossing",
    "unconnected_items", "track_width", "annular_width",
    "drill_out_of_range", "invalid_outline", "items_not_allowed", "padstack",
    "solder_mask_bridge", "zone_has_empty_net", "zones_intersect",
    "malformed_courtyard", "through_hole_pad_without_hole",
    "connection_width", "creepage",
}

# ACCEPTANCE C, verbatim.
RULES_MM = {
    "min_clearance": 0.0889,
    "min_track_width": 0.0889,
    "min_hole_to_hole": 0.2,
    "min_hole_clearance": 0.2,
    "min_copper_edge_clearance": 0.2,
    "min_through_hole_diameter": 0.3,
    "min_via_annular_width": 0.076,
    "min_via_diameter": 0.45,
}
PAD_TO_MASK_MM = 0.0508
PAD_TO_PASTE_MM = 0.0

CONTRACT_PARTS = 135
FITTED_PARTS = 133                      # 135 minus the two DNP
MECHANICAL = ["H1", "H2", "H3", "H4", "PEG1", "PEG2"]
PTH_PADS = 16


def board_side(root, log):
    """A, B and the board half of C and D, measured in this process."""
    import pcbnew
    board = pcbnew.LoadBoard(P.board_path(root))
    diffs, mech = P.contract_diff(board, pcbnew, root)
    facts = {
        "counts": P.counts(board, pcbnew),
        "contract_diffs": diffs,
        "mechanical": mech,
        "unconnected": P.unconnected_count(pcbnew, board),
        "npth": sorted(({"ref": k, "x_mm": P.mm(v[0]), "y_mm": P.mm(v[1]),
                         "dia_mm": P.mm(2 * v[2])}
                        for k, v in P.npth_holes(pcbnew, board).items()),
                       key=lambda d: d["ref"]),
    }
    zones = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        filled = 0
        for layer in z.GetLayerSet().CuStack():
            try:
                f = z.GetFilledPolysList(layer)
            except Exception:
                continue
            if f is not None:
                filled += f.OutlineCount()
        zones.append({"net": z.GetNetname(), "filled_outlines": filled})
    facts["zones"] = zones
    facts["zones_all_filled"] = all(z["filled_outlines"] > 0 for z in zones)

    ds = board.GetDesignSettings()
    facts["pad_to_mask_mm"] = P.mm(ds.m_SolderMaskExpansion)
    facts["solder_mask_min_width_mm"] = P.mm(ds.m_SolderMaskMinWidth)
    facts["pad_to_paste_mm"] = P.mm(ds.m_SolderPasteMargin)

    dnp = sorted(fp.GetReference() for fp in board.GetFootprints()
                 if fp.IsDNP())
    facts["dnp"] = dnp
    # ACCEPTANCE B, as the handover words it: a DNP part is still a component
    # and its pads still have to match the contract.
    have, _m = P.pad_net_map(board, pcbnew)
    facts["dnp_pads_checked"] = sorted(d for d in dnp if d in have)
    log["board"] = facts
    return facts


def rules_idempotent(root, log):
    """ACCEPTANCE C: regenerating the rules must change nothing.

    Done on a copy so a generator that is NOT idempotent cannot damage the real
    board on the way to reporting that it is not idempotent.
    """
    tmp = tempfile.mkdtemp(prefix="rulecheck")
    try:
        for d in ("board", "contract", "logs"):
            src = os.path.join(root, d)
            if os.path.isdir(src):
                shutil.copytree(src, os.path.join(tmp, d))
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "14_make_rules.py"),
             "--root", tmp], capture_output=True, text=True)
        out = {"ran": proc.returncode == 0,
               "stderr": (proc.stderr or "")[-400:]}
        for ext in ("kicad_pro", "kicad_dru"):
            a = os.path.join(root, "board", "%s.%s" % (P.BOARD_NAME, ext))
            b = os.path.join(tmp, "board", "%s.%s" % (P.BOARD_NAME, ext))
            same = (os.path.exists(b)
                    and open(a, "rb").read() == open(b, "rb").read())
            out[ext] = {"identical": bool(same)}
        out["identical"] = all(out[e]["identical"]
                               for e in ("kicad_pro", "kicad_dru"))
        log["rules_regenerated"] = out
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def rule_values(root, log):
    pro = E.load_json(os.path.join(root, "board",
                                   P.BOARD_NAME + ".kicad_pro"))
    rules = pro.get("board", {}).get("design_settings", {}).get("rules", {})
    got = {k: rules.get(k) for k in RULES_MM}
    log["rule_values"] = {"wanted": RULES_MM, "got": got}
    return all(abs((got.get(k) or -1) - v) < 1e-9 for k, v in RULES_MM.items())


def fab_side(root, log):
    """D, E, F, G -- read back from the exported package."""
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "62_check_fab.py"),
         "--root", root, "--json"], capture_output=True, text=True)
    try:
        fab = json.loads(proc.stdout)
    except ValueError:
        fab = {"error": (proc.stderr or proc.stdout)[-800:]}
    log["fab"] = fab

    bom_path = os.path.join(root, "fab", "BOM_JLCPCB.csv")
    cpl_path = os.path.join(root, "fab", "CPL_JLCPCB.csv")
    bom = {"exists": os.path.exists(bom_path)}
    if bom["exists"]:
        with open(bom_path) as f:
            rows = list(csv.DictReader(f))
        refs = []
        for r in rows:
            refs += [x.strip() for x in r["Designator"].split(",") if x.strip()]
        bom.update(rows=len(rows), parts=len(refs),
                   duplicate_designators=sorted(
                       {x for x in refs if refs.count(x) > 1}),
                   without_lcsc=[r["Designator"] for r in rows
                                 if not r["LCSC Part #"].strip()],
                   designators=sorted(refs))
    cpl = {"exists": os.path.exists(cpl_path)}
    if cpl["exists"]:
        with open(cpl_path) as f:
            rows = list(csv.DictReader(f))
        cpl.update(rows=len(rows),
                   designators=sorted(r["Designator"] for r in rows),
                   sides=sorted({r["Layer"] for r in rows}))
    log["bom"] = {k: v for k, v in bom.items() if k != "designators"}
    log["cpl"] = {k: v for k, v in cpl.items() if k != "designators"}
    if bom.get("designators") and cpl.get("designators"):
        log["bom_cpl_match"] = bom["designators"] == cpl["designators"]
        log["bom_only"] = sorted(set(bom["designators"])
                                 - set(cpl["designators"]))
        log["cpl_only"] = sorted(set(cpl["designators"])
                                 - set(bom["designators"]))
    previews = {n: os.path.join(root, "fab", n)
                for n in ("preview_top.png", "preview_bottom.png")}
    log["previews"] = {n: {"exists": os.path.exists(p),
                           "bytes": os.path.getsize(p)
                           if os.path.exists(p) else 0}
                       for n, p in previews.items()}
    return fab, bom, cpl


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--no-drc", action="store_true")
    a = ap.parse_args()
    root = a.root
    log = {}

    # --- A ----------------------------------------------------------------
    drc = {}
    if not a.no_drc:
        out = os.path.join(root, "logs", "drc_final.json")
        got, _proc, blob = P.run_drc(out, root)
        if not got:
            print("DRC produced no report -- run outside the sandbox")
            print(blob[-1200:])
            return 2
        doc = P.load_drc(out)
        drc = D.summarize(doc, "error")
        drc["types_at_warning"] = sorted(
            {v["type"] for v in doc.get("violations", ())
             if v.get("severity") == "warning"})
        drc["disallowed_warning_types"] = sorted(
            set(drc["types_at_warning"]) - ALLOWED_WARNINGS)
        # A type on the must-stay-error list appearing only as a warning would
        # mean the severity was relaxed. `clearance` is on both lists by
        # design: ACCEPTANCE C creates a second, advisory 5 mil rule.
        drc["relaxed_error_types"] = sorted(
            (set(drc["types_at_warning"]) & MUST_BE_ERRORS) - {"clearance"})
        log["drc"] = drc

    facts = board_side(root, log)
    idem = rules_idempotent(root, log)
    values_ok = rule_values(root, log)
    fab, bom, cpl = fab_side(root, log)

    npth_ok = fab.get("npth", {}).get("ok")
    ipc = fab.get("ipc_d356", {})
    gj = fab.get("gbrjob", {})
    odb = fab.get("odb", {})
    checks = [
        # A
        P.check("A DRC errors", 0, drc.get("errors"), ok=drc.get("errors") == 0
                if drc else None),
        P.check("A unconnected items", 0, drc.get("unconnected"),
                ok=drc.get("unconnected") == 0 if drc else None),
        P.check("A warning types all on the allowed list", [],
                drc.get("disallowed_warning_types", [])),
        P.check("A no must-be-error type demoted to warning", [],
                drc.get("relaxed_error_types", [])),
        P.check("A zones refilled and saved", True, facts["zones_all_filled"]),
        # B
        P.check("B contract parity (overrides applied)", 0,
                len(facts["contract_diffs"])),
        P.check("B components on the contract", CONTRACT_PARTS,
                facts["counts"]["footprints"] - len(MECHANICAL)),
        P.check("B mechanical footprints excluded", MECHANICAL,
                facts["mechanical"]),
        P.check("B DNP parts still checked against the contract",
                ["R_IO15_DN", "R_RST_UP"], facts["dnp_pads_checked"]),
        P.check("B net set agrees in IPC-D-356", True,
                ipc.get("nets", {}).get("match"),
                note="the d356 designator field is 6 characters and this "
                     "board has 12-character designators, so the pad map is "
                     "not recoverable from it -- the net set is, because the "
                     "net field is 14 and the longest name here is 14"),
        P.check("B net set agrees in ODB++", ipc.get("nets", {}).get(
            "in_contract"), odb.get("nets")),
        P.check("B Gerber X2 names the same net on every top pad", True,
                ipc.get("gerber_x2_agreement", {}).get("ok"),
                note="read through the sticky-attribute state machine: KiCad "
                     "emits %TO.N% only on a change, so most flashes inherit"),
        # C
        P.check("C rules regenerate identically", True, idem["identical"]),
        P.check("C rule values match ACCEPTANCE C", True, values_ok),
        P.check("C pad to mask clearance", PAD_TO_MASK_MM,
                facts["pad_to_mask_mm"]),
        P.check("C pad to paste clearance", PAD_TO_PASTE_MM,
                facts["pad_to_paste_mm"]),
        P.check("C solder mask minimum web", PAD_TO_MASK_MM,
                facts["solder_mask_min_width_mm"]),
        # D
        P.check("D NPTH holes on the board", 6, len(facts["npth"])),
        P.check("D NPTH in the drill file, within 2 um of the table", True,
                npth_ok),
        P.check("D no copper inside hole + 0.2 mm (from the Gerbers)", True,
                fab.get("npth_clear")),
        P.check("D PTH pads unchanged", PTH_PADS,
                facts["counts"]["pth_pads"]),
        P.check("D IPC-D-356 agrees: 6 unplated holes in the right places",
                True, ipc.get("npth_ok"),
                note="at the d356 resolution of 2.54 um; the 2 um assertion "
                     "stays with the Excellon file, which is metric"),
        P.check("D IPC-D-356 feature counts", [232, 417, 16, 6],
                [ipc.get("vias"), ipc.get("smd"), ipc.get("through_pads"),
                 ipc.get("npth")],
                note="vias were 239 until L7 moved R_CC1 out of the USB-C "
                     "shell; USB_CC1 has to cross J1's pad column on B.Cu, "
                     "which costs two (gates/S5_L7.json). S7v then took out "
                     "two AVSS vias in the C_VREFP_10n / C_VREFP_100n pads "
                     "that reached no layer but F.Cu -- each sat in a 0.5 mm "
                     "AVSS fill island of its own inside the In2 AVDD pour -- "
                     "241 -> 239 (logs/viapad_fix.json, 'removed'), and "
                     "the C_LM_FLY.1 room edit replaced a two-via B.Cu hop "
                     "with the straight F.Cu line, 239 -> 237; S7d "
                     "removed five vias that touched one layer only, the "
                     "ends of dangling stubs, 237 -> 232 (logs/"
                     "dangling_prune.json). ACCEPTANCE D allows a recorded "
                     "change"),
        # E
        P.check("E gerber set complete", [], fab.get("missing_layers", ["?"])),
        P.check("E four copper layers", 4,
                len([k for k in fab.get("layers", {})
                     if k.endswith(".Cu")])),
        P.check("E outline 61.8236 x 45.0088 mm +/- 0.01", True,
                fab.get("outline", {}).get("ok")),
        P.check("E every file read by our own parser", True,
                fab.get("all_parsed")),
        P.check("E copper layers additive only", True,
                fab.get("copper_all_dark")),
        P.check("E .gbrjob agrees on layers, thickness, stackup and rules",
                True, gj.get("ok")),
        P.check("E .gbrjob layer count", 4, gj.get("layer_number")),
        P.check("E .gbrjob board thickness mm", 1.6,
                gj.get("board_thickness_mm")),
        # F
        P.check("F BOM exists", True, bom.get("exists")),
        P.check("F every BOM row has an LCSC number", [],
                bom.get("without_lcsc", ["?"])),
        P.check("F no designator on two BOM rows", [],
                bom.get("duplicate_designators", ["?"])),
        P.check("F fitted parts in the BOM", FITTED_PARTS, bom.get("parts")),
        P.check("F CPL exists", True, cpl.get("exists")),
        P.check("F CPL rows", FITTED_PARTS, cpl.get("rows")),
        P.check("F BOM and CPL name the same parts", True,
                log.get("bom_cpl_match")),
        # G
        P.check("G top preview rendered", True,
                log["previews"]["preview_top.png"]["exists"]),
        P.check("G bottom preview rendered", True,
                log["previews"]["preview_bottom.png"]["exists"]),
    ]
    P.gate(root, "S7", checks,
           notes="ACCEPTANCE.md A-G. The document is frozen; this is its "
                 "implementation. D and E are settled by lib/gerber_parse.py "
                 "reading the plotted files, not by KiCad reading its own "
                 "output.",
           extra=log)

    bad = [c for c in checks if not c["pass"]]
    print("ACCEPTANCE A-G: %s" % ("PASS" if not bad else
                                  "FAIL (%d)" % len(bad)))
    for c in checks:
        print("  %-1s %-52s %s"
              % ("" if c["pass"] else "!", c["name"],
                 "ok" if c["pass"] else "expected %r got %r"
                 % (c["expected"], c["actual"])))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
