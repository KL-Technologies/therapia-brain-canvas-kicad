#!/usr/bin/env python3
"""Build data/parts_lcsc.csv -- the designator -> value / MPN / LCSC table.

Three sources, none of them the KiCad board:

  cerelog_research/fab_2026-08-16/Therapia_EEG-HRV_BOM.xlsx
      designator -> manufacturer part -> footprint, for the 131 parts that
      already exist. EasyEDA's "Supplier Part" column is a device name with a
      ".1" suffix, not an LCSC number, which is why the mapping below exists.
  cerelog_research/fab_tools/make_jlc_bom.py
      MPN_TO_LCSC (27 rows) and DESIGNATOR_OVERRIDE (ECO-2 and ECO-3), copied
      here rather than imported so this pipeline does not reach into another
      project's module. 21_verify_parts_table.py re-reads that file and fails
      if the two ever drift apart.
  11_rev_a_eco_2026-08-16.md
      the four parts ECO-1 adds, which are in no BOM yet.

Values are written out human-readably ("10uF 0603") because the board carries
none: every imported footprint has an empty Value field, and a BOM whose rows
say nothing but a C-number is not reviewable.

Standard library only; no pcbnew.
"""

import os
import sys
import csv
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import epro as E                      # noqa: E402
from lib import xlsx                           # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESEARCH = os.path.join(os.path.dirname(ROOT), "cerelog_research")
OLD_BOM = os.path.join(RESEARCH, "fab_2026-08-16", "Therapia_EEG-HRV_BOM.xlsx")

# --- from fab_tools/make_jlc_bom.py -----------------------------------------
MPN_TO_LCSC = {
    "AMS1117-3.3": "C6186",
    "CL10A105KB8NNNC": "C15849",            # 1uF 0603 (NOT 10uF -- see ECO-2)
    "CL05B104KO5NNNC": "C1525",             # 100nF 0402
    "CL05A105KA5NQNC": "C52923",            # 1uF 0402
    "0402CG101J500NT": "C1546",             # 100pF 0402 C0G
    "CL10B102KB8NNNC": "C1588",             # 1nF 0603 X7R
    "CL21F104ZBCNNNC": "C1760",             # 100nF 0805 Y5V, stock 0
    "USBLC6-2SC6": "C7519",
    "19-217/GHC-YR1S2/3T": "C72043",
    "JK-NSMD050-13.2V": "C369159",
    "GZ2012D601TF": "C94221",
    "TYPE-C 16PIN 2MD(073)": "C2765186",
    "PZ254V-11-12P": "C2840012",
    "LM2664M6X/NOPB": "C108573",
    "S8050 J3Y(RANGE:200-350)": "C2146",
    "0805W8F1004T5E": "C17514",             # 1M 0805
    "0603WAF5101T5E": "C23186",             # 5.1k 0603
    "0603WAF1002T5E": "C25804",             # 10k 0603
    "0402WGF1002TCE": "C25744",             # 10k 0402
    "0805W8F0000T5E": "C17477",             # 0R 0805
    "TLV70025DDCR": "C19619",
    "TPS72325DBVR": "C69932",
    "ADS1299IPAGR": "C476817",
    "ESP32-WROOM-32E-N4": "C701341",
    "CH340C": "C84681",
}

DESIGNATOR_OVERRIDE = {}
DESIGNATOR_OVERRIDE.update(
    {"C_DIF%d" % i: ("C237168", "ECO-2#6") for i in range(1, 9)})
DESIGNATOR_OVERRIDE["C_NR"] = ("C15195", "ECO-2#7")
DESIGNATOR_OVERRIDE["C_NLDO_OUT"] = ("C12530", "ECO-2#8")
DESIGNATOR_OVERRIDE["R_LED"] = ("C23138", "ECO-2#9")
DESIGNATOR_OVERRIDE.update({d: ("C19702", "ECO-2#10") for d in (
    "C_3V3_B", "C_3V3_B2", "C_3V3_OUT", "C_AVDD1_10u", "C_AVDD_B",
    "C_AVSS_B", "C_BULK", "C_DVDD_10u", "C_DVDD_B", "C_LM_FLY",
    "C_LM_OUT", "C_USB5V_B")})
DESIGNATOR_OVERRIDE["C_VCAP1"] = ("C15008", "ECO-3#11")
DESIGNATOR_OVERRIDE["C_VREFP_10u"] = ("C13585", "ECO-3#12")

# --- LCSC -> what it actually is --------------------------------------------
# value is what goes in the KiCad Value field and the BOM Comment column.
LCSC_PART = {
    "C6186":    ("AMS1117-3.3", "AMS1117-3.3", "SOT-223"),
    "C15849":   ("1uF", "CL10A105KB8NNNC", "0603"),
    "C1525":    ("100nF", "CL05B104KO5NNNC", "0402"),
    "C52923":   ("1uF", "CL05A105KA5NQNC", "0402"),
    "C1546":    ("100pF", "0402CG101J500NT", "0402"),
    "C1588":    ("1nF", "CL10B102KB8NNNC", "0603"),
    "C1760":    ("100nF", "CL21F104ZBCNNNC", "0805"),
    "C7519":    ("USBLC6-2SC6", "USBLC6-2SC6", "SOT-23-6"),
    "C72043":   ("LED_Y", "19-217/GHC-YR1S2/3T", "0805"),
    "C369159":  ("PTC_500mA", "JK-NSMD050-13.2V", "1206"),
    "C94221":   ("FB_600R", "GZ2012D601TF", "0805"),
    "C2765186": ("USB-C_16P", "TYPE-C 16PIN 2MD(073)", "USB-C-SMD"),
    "C2840012": ("Header_2x6", "PZ254V-11-12P", "HDR-2.54-2x6"),
    "C108573":  ("LM2664", "LM2664M6X/NOPB", "SOT-23-6"),
    "C2146":    ("S8050", "S8050 J3Y(RANGE:200-350)", "SOT-23-3"),
    "C17514":   ("1M", "0805W8F1004T5E", "0805"),
    "C23186":   ("5.1k", "0603WAF5101T5E", "0603"),
    "C25804":   ("10k", "0603WAF1002T5E", "0603"),
    "C25744":   ("10k", "0402WGF1002TCE", "0402"),
    "C17477":   ("0R", "0805W8F0000T5E", "0805"),
    "C19619":   ("TLV70025", "TLV70025DDCR", "SOT-353"),
    "C69932":   ("TPS72325", "TPS72325DBVR", "SOT-23-5"),
    "C476817":  ("ADS1299", "ADS1299IPAGR", "TQFP-64"),
    "C701341":  ("ESP32-WROOM-32E-N4", "ESP32-WROOM-32E-N4", "MODULE"),
    "C84681":   ("CH340C", "CH340C", "SOP-16"),
    # ECO-2 / ECO-3 replacements
    "C237168":  ("10nF_NP0_50V", "0805N103J500CT", "0805"),
    "C15195":   ("10nF", "CL05B103KB5NNNC", "0402"),
    "C12530":   ("2.2uF", "CL05A225MQ5NSNC", "0402"),
    "C23138":   ("330R", "0603WAF3300T5E", "0603"),
    "C19702":   ("10uF", "CL10A106KP8NNNC", "0603"),
    "C15008":   ("100uF", "CL31A107MQHNNNE", "1206"),
    "C13585":   ("10uF_25V", "CL31A106KAHNNNE", "1206"),
}

# --- ECO-1: the four parts that exist only in the schematic ------------------
# (designator, lcsc, kicad footprint library id, note)
NEW_PARTS = [
    ("C_VCAP2",   "C52923", "ProPrj_The-easyedapro:C0402", "ECO-1#4"),
    ("C_VCAP3",   "C52923", "ProPrj_The-easyedapro:C0402", "ECO-1#5"),
    ("C_VCAP3_H", "C1525",  "ProPrj_The-easyedapro:C0402", "ECO-1#5"),
    ("C_VCAP1_H", "C1525",  "ProPrj_The-easyedapro:C0402", "ECO-3#11"),
]

# ECO-3 swaps two 0603 capacitors for 1206 parts; the board has to follow.
FOOTPRINT_CHANGES = {
    "C_VCAP1": "Capacitor_SMD:C_1206_3216Metric",
    "C_VREFP_10u": "Capacitor_SMD:C_1206_3216Metric",
}

UNVERIFIED = {
    "C13585": "ECO-3#12 says this C-number must be confirmed against the JLC "
              "part API before ordering; if it cannot be, substitute C15008.",
}

# --- the lead's pre-order corrections ----------------------------------------
BOM_FIXES = os.path.join("data", "bom_fixes_2026-08-28.json")


def apply_bom_fixes(parts, root, problems):
    """Overlay data/bom_fixes_2026-08-28.json onto the table just built.

    That file is where the BOM verification landed: five part numbers that were
    wrong or unbuildable, two parts that must not be fitted on Rev.A, and
    ECO-5's capacitor. It is read here rather than patched into the CSV by hand
    so that regenerating the table cannot quietly drop any of it.

    Every fix declares footprint_change: false, so package, footprint and
    designator carry through untouched and only value / MPN / LCSC move. A DNP
    part keeps its row -- it is still on the board and still on the netlist --
    and is marked for the BOM and CPL writers to skip.
    """
    path = os.path.join(root, BOM_FIXES)
    if not os.path.exists(path):
        problems.append({"file": BOM_FIXES, "reason": "BOM fixes file missing"})
        return {}
    doc = E.load_json(path)
    applied = {}
    for group, entries in (("fixes", doc.get("fixes", ())),
                           ("bringup_review_fixes",
                            doc.get("bringup_review_fixes", ()))):
        for fix in entries:
            if fix.get("footprint_change"):
                problems.append({"fix": fix.get("id") or fix["designators"],
                                 "reason": "footprint_change is not supported "
                                           "here -- the board would have to "
                                           "move too"})
                continue
            dnp = str(fix.get("action", "")).startswith("DNP")
            for ref in fix["designators"]:
                row = parts.get(ref)
                if row is None:
                    problems.append({"designator": ref,
                                     "reason": "named by a BOM fix but not in "
                                               "the parts table"})
                    continue
                before = dict(row)
                if fix.get("new_lcsc"):
                    row["lcsc"] = fix["new_lcsc"]
                if fix.get("new_mpn"):
                    row["mpn"] = fix["new_mpn"]
                elif fix.get("new_lcsc") in LCSC_PART:
                    # B2 changes C_EN_DLY's C-number without naming a part, and
                    # leaving the old MPN in place would ship a row saying
                    # 1 uF against the 100 nF part number it replaced.
                    row["mpn"] = LCSC_PART[fix["new_lcsc"]][1]
                if fix.get("new_value"):
                    row["value"] = fix["new_value"]
                if dnp:
                    row["dnp"] = "1"
                tag = fix.get("id") or "bom-verify"
                row["fix"] = (row.get("fix") + ";" + tag).strip(";") \
                    if row.get("fix") else tag
                changed = {k: [before.get(k), row.get(k)]
                           for k in ("value", "mpn", "lcsc", "dnp")
                           if before.get(k) != row.get(k)}
                if changed:
                    applied.setdefault(ref, {}).update(changed)
    return applied


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=ROOT)
    args = ap.parse_args()
    root = args.root
    out_csv = os.path.join(root, "data", "parts_lcsc.csv")

    if not os.path.exists(OLD_BOM):
        print("old BOM not found: %s" % OLD_BOM)
        return 2
    _hdr, rows = xlsx.read_table(OLD_BOM)

    parts, problems = {}, []
    for r in rows:
        mpn = (r.get("Manufacturer Part") or "").strip()
        fp = (r.get("Footprint") or "").strip()
        base = MPN_TO_LCSC.get(mpn)
        for d in [x.strip() for x in (r.get("Designator") or "").split(",")
                  if x.strip()]:
            if d in DESIGNATOR_OVERRIDE:
                lcsc, why = DESIGNATOR_OVERRIDE[d]
            elif base:
                lcsc, why = base, ""
            else:
                problems.append({"designator": d, "mpn": mpn,
                                 "reason": "no LCSC number for this MPN"})
                continue
            info = LCSC_PART.get(lcsc)
            if not info:
                problems.append({"designator": d, "lcsc": lcsc,
                                 "reason": "LCSC number has no part record"})
                continue
            parts[d] = {"designator": d, "value": info[0], "mpn": info[1],
                        "lcsc": lcsc, "package": info[2],
                        "easyeda_footprint": fp, "eco": why,
                        "kicad_footprint": FOOTPRINT_CHANGES.get(d, ""),
                        "source": "fab_2026-08-16 BOM"}

    for d, lcsc, fpid, why in NEW_PARTS:
        info = LCSC_PART[lcsc]
        parts[d] = {"designator": d, "value": info[0], "mpn": info[1],
                    "lcsc": lcsc, "package": info[2], "easyeda_footprint": "",
                    "eco": why, "kicad_footprint": fpid,
                    "source": "ECO-1 (new part)"}

    contract = E.load_json(os.path.join(root, "contract",
                                        "netlist_contract.json"))
    want = set(contract["by_designator"])
    missing = sorted(want - set(parts))
    extra = sorted(set(parts) - want)
    for d in missing:
        problems.append({"designator": d,
                         "reason": "in the contract netlist but not in the "
                                   "BOM sources"})
    for d in extra:
        problems.append({"designator": d,
                         "reason": "in the BOM sources but not in the "
                                   "contract netlist"})

    fixes_applied = apply_bom_fixes(parts, root, problems)

    cols = ["designator", "value", "mpn", "lcsc", "package",
            "easyeda_footprint", "kicad_footprint", "eco", "source",
            "dnp", "fix"]
    d = os.path.dirname(out_csv)
    if not os.path.isdir(d):
        os.makedirs(d)
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for name in sorted(parts):
            w.writerow(parts[name])

    E.dump_json(os.path.join(root, "logs", "parts_table.json"),
                {"csv": os.path.abspath(out_csv),
                 "count": len(parts),
                 "contract_count": len(want),
                 "missing_from_table": missing,
                 "not_in_contract": extra,
                 "problems": problems,
                 "eco_applied": sorted({p["eco"] for p in parts.values()
                                        if p["eco"]}),
                 "footprint_changes": FOOTPRINT_CHANGES,
                 "unverified_lcsc": UNVERIFIED,
                 "bom_fixes_applied": fixes_applied,
                 "dnp": sorted(d for d, p in parts.items() if p.get("dnp"))})

    ok = not problems
    print("parts table: %d rows (contract wants %d)  fixes %d  dnp %s%s"
          % (len(parts), len(want), len(fixes_applied),
             sorted(d for d, p in parts.items() if p.get("dnp")),
             "" if ok else "  PROBLEMS:"))
    for p in problems[:20]:
        print("  %s" % p)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
