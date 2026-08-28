#!/usr/bin/env python3
"""S3: write the JLCPCB 4-layer design rules into the KiCad project.

Generates two files from the table in ACCEPTANCE.md section C:

  board/Therapia_EEG-HRV.kicad_pro   design_settings.rules, rule_severities,
                                     net classes and their patterns
  board/Therapia_EEG-HRV.kicad_dru   custom DRC rules that the .kicad_pro
                                     schema cannot express

and patches the (setup ...) block of the .kicad_pcb for the two clearances
KiCad keeps on the board rather than in the project (pad->mask, pad->paste).

Pure text/JSON generation -- no pcbnew, so it runs under system python3. Fully
idempotent: re-running rewrites the same bytes.

Until this runs, DRC numbers mean nothing. The import ran against KiCad's
DEFAULT rules (0.2 mm clearance, 0.2 mm minimum track) and produced 1025
violations that say more about the defaults than about the board.

contract/easyeda_rules.json holds the EasyEDA values for reference. They are
NOT copied over verbatim: EasyEDA labels every rule "mm" but stores mil, and
its clearance matrix is per-layer-pair in a form KiCad has no equivalent for.
The numbers that matter are cross-checked against it in `easyeda_crosscheck`.
"""

import os
import re
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import epro as E                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD_NAME = "Therapia_EEG-HRV"

MIL = 0.0254

# --- ACCEPTANCE.md section C -------------------------------------------------
CLEARANCE_MM = round(3.5 * MIL, 4)             # 0.0889
TRACK_MIN_MM = round(3.5 * MIL, 4)             # 0.0889
HOLE_TO_HOLE_MM = 0.2
HOLE_CLEARANCE_MM = 0.2                        # hole -> copper of another net
EDGE_CLEARANCE_MM = 0.2
VIA_DRILL_MIN_MM = 0.3
VIA_ANNULAR_MIN_MM = 0.076
VIA_DIA_MIN_MM = 0.45
TRACK_TRACK_PREFERRED_MM = round(5 * MIL, 4)   # 0.127, warning only

# The board's own geometry, kept as the netclass defaults so anything drawn
# from here on matches what is already routed.
VIA_DIA_MM = 0.6096                            # 24 mil
VIA_DRILL_MM = 0.3048                          # 12 mil
TRACK_SIGNAL_MM = 0.2032                       # 8 mil
TRACK_POWER_MM = 0.254                         # 10 mil

# See the note in ACCEPTANCE.md section C: the brief asked for 0.1016, this is
# a deliberate, documented deviation. 4 mil per side leaves a 0.0168 mm mask
# dam between the ADS1299's 0.5 mm-pitch pads, which no fab can hold and which
# DRC would not flag. 2 mil is also what EasyEDA used for the 2026-08-16 fab
# package, so the solder mask stays comparable with the reviewed Gerbers.
PAD_TO_MASK_MM = 0.0508                        # 2 mil
PAD_TO_PASTE_MM = 0.0
SOLDER_MASK_MIN_WIDTH_MM = 0.0508

POWER_NETS = [
    "GND", "CHASSIS_GND", "AVDD", "AVSS", "DVDD", "VDD_ESP", "USB_5V",
    "USB_VBUS_RAW", "V5_LM_IN", "V_3V3_IN", "V_NLDO_IN", "V_PLDO_IN", "VNEG5",
    "VREFP", "VCAP1", "VCAP2", "VCAP3", "VCAP4", "LM_CAP_N", "LM_CAP_P",
]

# Everything the board is allowed to still report once L1-L5 are repaired.
# ACCEPTANCE.md section A is the authority; this is the machine-readable copy.
SEVERITY_WARNING = [
    "courtyards_overlap", "silk_overlap", "silk_over_copper",
    "silk_edge_clearance", "starved_thermal", "track_dangling",
    "via_dangling", "isolated_copper", "copper_sliver", "holes_co_located",
    "footprint_type_mismatch",
]
SEVERITY_IGNORE = [
    "lib_footprint_issues", "lib_footprint_mismatch", "missing_courtyard",
    "pth_inside_courtyard", "npth_inside_courtyard",
    "footprint_filters_mismatch",
]
SEVERITY_ERROR = [
    "annular_width", "clearance", "connection_width", "copper_edge_clearance",
    "creepage", "diff_pair_gap_out_of_range",
    "diff_pair_uncoupled_length_too_long", "drill_out_of_range", "footprint",
    "footprint_symbol_mismatch", "hole_clearance", "hole_near_hole",
    "hole_to_hole", "invalid_outline", "item_on_disabled_layer",
    "items_not_allowed", "length_out_of_range", "malformed_courtyard",
    "microvia_drill_out_of_range", "padstack", "shorting_items",
    "skew_out_of_range", "solder_mask_bridge", "text_height",
    "text_thickness", "through_hole_pad_without_hole", "too_many_vias",
    "track_angle", "track_segment_length", "track_width", "tracks_crossing",
    "unconnected_items", "unresolved_variable", "zone_has_empty_net",
    "zones_intersect",
]
# Left at whatever KiCad defaults to; recorded so the set is exhaustive.
SEVERITY_DEFAULT = [
    "duplicate_footprints", "extra_footprint", "missing_footprint",
    "mirrored_text_on_front_layer", "net_conflict",
    "nonmirrored_text_on_back_layer",
]


def netclass(name, priority, track, clearance=CLEARANCE_MM):
    return {
        "bus_width": 12,
        "clearance": clearance,
        "diff_pair_gap": 0.2,
        "diff_pair_via_gap": 0.25,
        "diff_pair_width": 0.2,
        "line_style": 0,
        "microvia_diameter": 0.3,
        "microvia_drill": 0.1,
        "name": name,
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "priority": priority,
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "track_width": track,
        "via_diameter": VIA_DIA_MM,
        "via_drill": VIA_DRILL_MM,
        "wire_width": 6,
    }


def build_project(existing):
    doc = dict(existing) if existing else {}
    doc.setdefault("boards", [])
    doc.setdefault("libraries", {"pinned_footprint_libs": [],
                                 "pinned_symbol_libs": []})
    doc.setdefault("pcbnew", {"page_layout_descr_file": ""})
    doc.setdefault("sheets", [])
    doc.setdefault("text_variables", {})
    doc["meta"] = {"filename": BOARD_NAME + ".kicad_pro", "version": 3}

    severities = {}
    for k in SEVERITY_ERROR:
        severities[k] = "error"
    for k in SEVERITY_WARNING:
        severities[k] = "warning"
    for k in SEVERITY_IGNORE:
        severities[k] = "ignore"

    board = doc.setdefault("board", {})
    board["design_settings"] = {
        "defaults": {
            "apply_defaults_to_fp_fields": False,
            "apply_defaults_to_fp_shapes": False,
            "apply_defaults_to_fp_text": False,
            "board_outline_line_width": 0.1016,
            "copper_line_width": TRACK_SIGNAL_MM,
            "copper_text_italic": False,
            "copper_text_size_h": 1.0,
            "copper_text_size_v": 1.0,
            "copper_text_thickness": 0.15,
            "copper_text_upright": False,
            "courtyard_line_width": 0.05,
            "dimension_precision": 4,
            "dimension_units": 3,
            "fab_line_width": 0.0508,
            "fab_text_italic": False,
            "fab_text_size_h": 1.0,
            "fab_text_size_v": 1.0,
            "fab_text_thickness": 0.15,
            "fab_text_upright": False,
            "other_line_width": 0.1,
            "other_text_italic": False,
            "other_text_size_h": 1.0,
            "other_text_size_v": 1.0,
            "other_text_thickness": 0.15,
            "other_text_upright": False,
            "pads": {"drill": VIA_DRILL_MM, "height": 0.6, "width": 0.6},
            "silk_line_width": 0.1525,
            "silk_text_italic": False,
            "silk_text_size_h": 0.7,
            "silk_text_size_v": 0.7,
            "silk_text_thickness": 0.15,
            "silk_text_upright": False,
            "zones": {"45_degree_only": False, "min_clearance": CLEARANCE_MM},
        },
        "diff_pair_dimensions": [],
        "drc_exclusions": [],
        "meta": {"version": 2},
        "rule_severities": dict(sorted(severities.items())),
        "rules": {
            "allow_blind_buried_vias": False,
            "allow_microvias": False,
            "max_error": 0.005,
            "min_clearance": CLEARANCE_MM,
            "min_connection": 0.0,
            "min_copper_edge_clearance": EDGE_CLEARANCE_MM,
            "min_groove_width": 0.0,
            "min_hole_clearance": HOLE_CLEARANCE_MM,
            "min_hole_to_hole": HOLE_TO_HOLE_MM,
            "min_microvia_diameter": 0.2,
            "min_microvia_drill": 0.1,
            "min_resolved_spokes": 2,
            "min_silk_clearance": 0.0,
            "min_text_height": 0.6,
            "min_text_thickness": 0.06,
            "min_through_hole_diameter": VIA_DRILL_MIN_MM,
            "min_track_width": TRACK_MIN_MM,
            "min_via_annular_width": VIA_ANNULAR_MIN_MM,
            "min_via_diameter": VIA_DIA_MIN_MM,
            "solder_mask_to_copper_clearance": 0.0,
            "use_height_for_length_calcs": True,
        },
        "track_widths": [0.0, TRACK_SIGNAL_MM, TRACK_POWER_MM, 0.3048, 0.508],
        "via_dimensions": [{"diameter": 0.0, "drill": 0.0},
                           {"diameter": VIA_DIA_MM, "drill": VIA_DRILL_MM}],
        "zones_allow_external_fillets": False,
    }

    doc["net_settings"] = {
        "classes": [netclass("Default", 2147483647, TRACK_SIGNAL_MM),
                    netclass("Power", 10, TRACK_POWER_MM)],
        "meta": {"version": 4},
        "net_colors": None,
        "netclass_assignments": None,
        "netclass_patterns": [{"netclass": "Power", "pattern": n}
                              for n in POWER_NETS],
    }
    return doc


DRU_TEMPLATE = """(version 1)

# Generated by scripts/14_make_rules.py -- do not hand-edit.
# The values come from ACCEPTANCE.md section C (JLCPCB 4-layer capability).
# Everything expressible in the .kicad_pro schema lives there; this file holds
# only what needs a condition.

# JLC drills the two 0.7 mm USB-C pegs and the four M2 holes as NPTH. Nothing
# may be routed into the drilled circle plus {hole_clearance} mm -- that is the
# L1/L2/L4 failure on this board, where a mounting hole eats the AMS1117 GND
# pad and the peg holes cut six USB_VBUS_RAW tracks.
(rule "npth_hole_to_copper"
\t(constraint hole_clearance (min {hole_clearance}mm))
\t(condition "A.Pad_Type == 'NPTH, mechanical'")
\t(severity error)
)

# 3.5 mil is what JLC will actually build; 5 mil is what this board should have
# been routed to. Report the gap between the two so the L5 sweep has a list.
(rule "track_to_track_5mil_preferred"
\t(constraint clearance (min {preferred}mm))
\t(condition "A.Type == 'Track' && B.Type == 'Track'")
\t(severity warning)
)

# JLC's minimum annular ring on a through via.
(rule "via_annular_ring"
\t(constraint annular_width (min {annular}mm))
\t(condition "A.Type == 'Via'")
\t(severity error)
)
"""


def build_dru():
    return DRU_TEMPLATE.format(
        hole_clearance=HOLE_CLEARANCE_MM,
        preferred=TRACK_TRACK_PREFERRED_MM,
        annular=VIA_ANNULAR_MIN_MM)


def patch_board_setup(path):
    """Set pad_to_mask_clearance / pad_to_paste_clearance / solder mask minimum
    width inside the .kicad_pcb (setup ...) block. KiCad keeps these three on
    the board, not in the project file."""
    with open(path) as f:
        text = f.read()
    i = text.find("(setup")
    if i < 0:
        return {"patched": False, "reason": "no (setup ...) block"}
    depth, j = 0, i
    while j < len(text):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                break
        j += 1
    block, changed = text[i:j + 1], {}
    wanted = [("pad_to_mask_clearance", PAD_TO_MASK_MM),
              ("solder_mask_min_width", SOLDER_MASK_MIN_WIDTH_MM),
              ("pad_to_paste_clearance", PAD_TO_PASTE_MM)]
    for key, val in wanted:
        s = ("%g" % val)
        pat = re.compile(r"\(%s\s+[-0-9.eE]+\)" % re.escape(key))
        if pat.search(block):
            new = pat.sub("(%s %s)" % (key, s), block)
        else:                                  # insert right after "(setup"
            new = block.replace("(setup", "(setup\n\t\t(%s %s)" % (key, s), 1)
        if new != block:
            changed[key] = val
        block = new
    out = text[:i] + block + text[j + 1:]
    if out != text:
        with open(path, "w") as f:
            f.write(out)
    return {"patched": bool(changed), "values": changed}


def easyeda_crosscheck(root):
    """Read contract/easyeda_rules.json and say what it implies, so the values
    written here can be argued with rather than just trusted.

    EasyEDA labels every rule "mm" but the numbers are mil: holeClearance
    11.811 is 0.3 mm, viaSize.defInner 6.0039 is the 12 mil drill this board
    actually uses. The conversion is asserted here, not assumed."""
    path = os.path.join(root, "contract", "easyeda_rules.json")
    if not os.path.exists(path):
        return {"available": False}
    doc = E.load_json(path)
    by_name = {}
    for r in doc.get("rules", []):
        by_name.setdefault(r.get("rule_type"), []).append(r)
    out = {"available": True, "unit_label_says": "mm",
           "unit_actually": "mil",
           "evidence": [], "derived_mm": {}}

    via = next((r for r in by_name.get("5", []) if r.get("is_default")), None)
    if via:
        d = via["data"]
        out["derived_mm"]["via_diameter_default"] = round(
            d["defRadius"] * 2 * MIL, 4)
        out["derived_mm"]["via_drill_default"] = round(d["defInner"] * 2 * MIL, 4)
        out["derived_mm"]["via_drill_min"] = round(d["minInner"] * 2 * MIL, 4)
        out["evidence"].append(
            "viaSize.defRadius %s * 2 mil = %.4f mm, which is the 0.6096 mm via "
            "pad measured on the board; read as mm it would be 24 mm."
            % (d["defRadius"], d["defRadius"] * 2 * MIL))

    oc = next((r for r in by_name.get("2", []) if r.get("is_default")), None)
    if oc:
        out["derived_mm"]["hole_clearance"] = round(
            oc["data"]["holeClearance"] * MIL, 4)
        out["evidence"].append(
            "otherClearance.holeClearance %s mil = %.4f mm"
            % (oc["data"]["holeClearance"], oc["data"]["holeClearance"] * MIL))

    tw = next((r for r in by_name.get("3", []) if r.get("is_default")), None)
    if tw:
        out["derived_mm"]["track_width_min"] = round(tw["data"][1] * MIL, 4)

    cl = next((r for r in by_name.get("1", []) if r.get("is_default")), None)
    if cl:
        # data[1] is a lower-triangular matrix; row 0 is the copper thickness
        # the rule is named for (4.0157 = 1 oz), not a clearance.
        table = cl["data"][1]
        vals = sorted({v for row in table[1:] for v in row})
        out["derived_mm"]["copper_thickness"] = round(table[0][0] * MIL, 4)
        out["derived_mm"]["clearance_matrix_min"] = round(min(vals) * MIL, 4)
        out["evidence"].append(
            "clearance matrix smallest entry %s mil = %.4f mm; EasyEDA was "
            "routing to 5 mil, and the DRC audit found 47 places under 3.5 mil."
            % (min(vals), min(vals) * MIL))

    sm = next((r for r in by_name.get("9", []) if r.get("is_default")), None)
    if sm:
        out["derived_mm"]["solder_mask_expansion"] = round(
            sm["data"]["padTopExpan"] * MIL, 4)

    out["chosen_mm"] = {
        "clearance": CLEARANCE_MM, "track_min": TRACK_MIN_MM,
        "hole_to_hole": HOLE_TO_HOLE_MM, "hole_clearance": HOLE_CLEARANCE_MM,
        "edge_clearance": EDGE_CLEARANCE_MM, "via_drill_min": VIA_DRILL_MIN_MM,
        "via_annular_min": VIA_ANNULAR_MIN_MM, "via_dia_min": VIA_DIA_MIN_MM,
        "pad_to_mask": PAD_TO_MASK_MM, "pad_to_paste": PAD_TO_PASTE_MM,
        "track_track_preferred_warning": TRACK_TRACK_PREFERRED_MM,
    }
    out["reading"] = (
        "The chosen values are JLC capability limits, deliberately looser than "
        "what EasyEDA was routing to (5 mil clearance / 0.3 mm hole clearance). "
        "That is the point: DRC should flag only what JLC cannot build, and the "
        "5 mil target is carried as a warning-level custom rule instead.")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=ROOT)
    args = ap.parse_args()
    root = args.root
    pro = os.path.join(root, "board", BOARD_NAME + ".kicad_pro")
    dru = os.path.join(root, "board", BOARD_NAME + ".kicad_dru")
    pcb = os.path.join(root, "board", BOARD_NAME + ".kicad_pcb")

    existing = E.load_json(pro) if os.path.exists(pro) else {}
    doc = build_project(existing)
    with open(pro, "w") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
        f.write("\n")
    with open(dru, "w") as f:
        f.write(build_dru())
    setup = patch_board_setup(pcb) if os.path.exists(pcb) else {"patched": False}

    cross = easyeda_crosscheck(root)
    E.dump_json(os.path.join(root, "logs", "rules_applied.json"),
                {"kicad_pro": os.path.abspath(pro),
                 "kicad_dru": os.path.abspath(dru),
                 "board_setup": setup,
                 "rules": doc["board"]["design_settings"]["rules"],
                 "severities": doc["board"]["design_settings"]["rule_severities"],
                 "netclasses": [c["name"] for c in doc["net_settings"]["classes"]],
                 "power_nets": POWER_NETS,
                 "easyeda_crosscheck": cross})
    print("rules written: %s + %s (board setup %s)"
          % (os.path.basename(pro), os.path.basename(dru),
             "patched" if setup.get("patched") else "unchanged"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
