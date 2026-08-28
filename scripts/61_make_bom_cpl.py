#!/usr/bin/env python3
"""S8 -- the BOM and the placement file, in JLCPCB's format.

    KPY scripts/61_make_bom_cpl.py

BOM   Comment,Designator,Footprint,LCSC Part #  plus MPN, Manufacturer, Qty.
      Rows are grouped by part number, the way JLC's own export does it and the
      way the ganglion_clone BOM JLC accepted is laid out.
CPL   Designator,Mid X,Mid Y,Layer,Rotation from `kicad-cli pcb export pos`,
      renamed. Ganglion went through with negative Y and untranslated rotation,
      so neither is touched here.

Excluded from both, and the exclusions have to agree or the pair is rejected:

  H1-H4, PEG1, PEG2   mechanical, not components
  R_RST_UP            DNP -- pulls GPIO12 up, violating the ESP32 boot strap
  R_IO15_DN           DNP -- would silence the ROM boot log on Rev.A

The Footprint column is taken from the board, not from the package label in
data/parts_lcsc.csv. That label is wrong in three known places (D_LED reads
0805 for a part on an 0603 land; C2840012 and C19619 are noted in the fixes
file) and the board is the thing being built.
"""

import argparse
import collections
import csv
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import epro as E                                   # noqa: E402

MECHANICAL = ("H1", "H2", "H3", "H4", "PEG1", "PEG2")
BOM_COLUMNS = ["Comment", "Designator", "Footprint", "LCSC Part #",
               "MPN", "Manufacturer", "Qty"]
CPL_COLUMNS = ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"]

# LCSC number -> manufacturer, for the optional column. Absent is not an error.
MAKER = {
    "C1017": "Sunlord", "C15195": "Samsung", "C13585": "Samsung",
    "C72044": "Everlight", "C52923": "Samsung", "C23967": "Samsung",
    "C1525": "Samsung", "C19702": "Samsung", "C1588": "Samsung",
    "C1546": "Fenghua", "C12530": "Samsung", "C15008": "Samsung",
    "C15849": "Samsung", "C237168": "Fenghua", "C1760": "Samsung",
    "C6186": "AMS", "C476817": "Texas Instruments", "C69932": "Texas Instruments",
    "C19619": "Texas Instruments", "C108573": "Texas Instruments",
    "C701341": "Espressif", "C84681": "WCH", "C7519": "STMicroelectronics",
    "C2765186": "SHOU HAN", "C2840012": "Ckmtw", "C369159": "Jinrui",
    "C2146": "Jiangsu Changjing", "C17514": "UNI-ROYAL", "C23186": "UNI-ROYAL",
    "C25804": "UNI-ROYAL", "C25744": "UNI-ROYAL", "C17477": "UNI-ROYAL",
    "C23138": "UNI-ROYAL",
}


def board_footprints(root):
    """designator -> the footprint name actually on the board, plus DNP."""
    import pcbnew
    board = pcbnew.LoadBoard(P.board_path(root))
    out = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref:
            continue
        name = fp.GetFPIDAsString()
        out[ref] = {
            "footprint": name.split(":")[-1],
            "dnp": bool(fp.IsDNP()),
            "excluded_from_bom": bool(int(fp.GetAttributes())
                                      & int(pcbnew.FP_EXCLUDE_FROM_BOM)),
            "value": fp.GetValue(),
        }
    return out


def run_pos(root, out_path):
    cmd = [P.kicad_cli(), "pcb", "export", "pos", "--format", "csv",
           "--units", "mm", "--side", "front", "-o", out_path,
           P.board_path(root)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return os.path.exists(out_path), (proc.stdout or "") + (proc.stderr or "")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    a = ap.parse_args()
    root = a.root
    fab = os.path.join(root, "fab")
    if not os.path.isdir(fab):
        os.makedirs(fab)

    with open(os.path.join(root, "data", "parts_lcsc.csv")) as f:
        parts = {r["designator"]: r for r in csv.DictReader(f)}
    board = board_footprints(root)
    log = {"table_rows": len(parts), "board_footprints": len(board)}

    dnp = sorted(d for d, r in parts.items() if r.get("dnp"))
    board_dnp = sorted(d for d, r in board.items() if r["dnp"])
    fitted = sorted(d for d in parts if d not in dnp)
    log["dnp_in_table"] = dnp
    log["dnp_on_board"] = board_dnp
    log["dnp_agree"] = dnp == board_dnp

    # --- BOM ---------------------------------------------------------------
    groups = collections.OrderedDict()
    missing_fp, no_lcsc = [], []
    for d in fitted:
        r = parts[d]
        if not r["lcsc"]:
            no_lcsc.append(d)
        b = board.get(d)
        if b is None:
            missing_fp.append(d)
            fpname = r["package"]
        else:
            fpname = b["footprint"]
        # Grouped by part number and land, not by the value text: C15195 was
        # coming out as two rows ("10nF" for C_NR, "10nF 50V X7R 0402" for the
        # two the BOM fixes relabelled) for one part. Keeping the footprint in
        # the key means one C-number on two different lands would still show up
        # as two rows, which is a thing worth seeing.
        groups.setdefault((r["lcsc"], fpname), []).append(d)

    bom_path = os.path.join(fab, "BOM_JLCPCB.csv")
    with open(bom_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(BOM_COLUMNS)
        for (lcsc, fpname), refs in sorted(
                groups.items(), key=lambda kv: (-len(kv[1]), kv[0][0])):
            values = collections.Counter(parts[d]["value"] for d in refs)
            comment = max(values, key=lambda v: (values[v], len(v)))
            mpn = parts[refs[0]]["mpn"]
            w.writerow([comment, ",".join(sorted(refs, key=natural)), fpname,
                        lcsc, mpn, MAKER.get(lcsc, ""), len(refs)])
    log["bom"] = {"path": bom_path, "rows": len(groups),
                  "parts": sum(len(v) for v in groups.values()),
                  "designators_missing_from_board": missing_fp,
                  "rows_without_lcsc": no_lcsc}

    # --- CPL ---------------------------------------------------------------
    raw = os.path.join(root, "logs", "pos_front.csv")
    ok, blob = run_pos(root, raw)
    if not ok:
        print("kicad-cli export pos failed (run outside the sandbox):")
        print(blob[-1200:])
        return 2
    with open(raw) as f:
        rows = list(csv.DictReader(f))
    cpl_path = os.path.join(fab, "CPL_JLCPCB.csv")
    skipped = []
    kept = []
    with open(cpl_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CPL_COLUMNS)
        for r in rows:
            ref = r.get("Ref") or r.get("Designator")
            if ref in MECHANICAL or ref in dnp:
                skipped.append(ref)
                continue
            kept.append(ref)
            w.writerow([ref, r["PosX"], r["PosY"],
                        "Top" if r["Side"] == "top" else "Bottom",
                        r["Rot"]])
    log["cpl"] = {"path": cpl_path, "rows": len(kept),
                  "excluded": sorted(set(skipped), key=natural),
                  "source_rows": len(rows)}

    # --- the two must name the same parts -----------------------------------
    bom_set = set(fitted)
    cpl_set = set(kept)
    log["bom_only"] = sorted(bom_set - cpl_set, key=natural)
    log["cpl_only"] = sorted(cpl_set - bom_set, key=natural)
    log["sets_match"] = not log["bom_only"] and not log["cpl_only"]

    log["vs_2026_08_16"] = compare_old_cpl(root, cpl_path)
    E.dump_json(os.path.join(root, "logs", "bom_cpl.json"), log)
    print("BOM  %s  %d rows, %d parts%s"
          % (bom_path, log["bom"]["rows"], log["bom"]["parts"],
             "" if not no_lcsc else "  MISSING LCSC: %s" % no_lcsc))
    print("CPL  %s  %d rows (excluded %s)"
          % (cpl_path, log["cpl"]["rows"], ", ".join(log["cpl"]["excluded"])))
    print("designator sets agree: %s%s"
          % (log["sets_match"],
             "" if log["sets_match"] else
             "  bom_only=%s cpl_only=%s" % (log["bom_only"], log["cpl_only"])))
    print("DNP: table %s / board %s -> agree %s"
          % (dnp, board_dnp, log["dnp_agree"]))
    return 0 if (log["sets_match"] and not no_lcsc and log["dnp_agree"]) else 1


def _mm(text):
    return float(str(text).strip().replace("mm", ""))


def compare_old_cpl(root, cpl_path):
    """Every part that did not move should still be where it was in August.

    S2 matched all 131 placements against the 2026-08-16 CPL. Since then the
    ECOs added four capacitors, turned two into 1206s, and the repairs nudged
    six parts. Anything else differing would be a part that drifted without
    anyone deciding it should.
    """
    from lib import xlsx
    old = os.path.join(os.path.dirname(root), "cerelog_research",
                       "fab_2026-08-16", "Therapia_EEG-HRV_CPL.xlsx")
    if not os.path.exists(old):
        return None
    _hdr, rows = xlsx.read_table(old)
    was = {}
    for r in rows:
        ref = (r.get("Designator") or "").strip()
        if not ref:
            continue
        try:
            # EasyEDA writes the unit into the cell: "53.594mm".
            was[ref] = (_mm(r["Mid X"]), _mm(r["Mid Y"]),
                        float(r.get("Rotation") or 0))
        except (KeyError, ValueError, TypeError):
            continue
    with open(cpl_path) as f:
        now = {r["Designator"]: (float(r["Mid X"]), float(r["Mid Y"]),
                                 float(r["Rotation"])) for r in csv.DictReader(f)}
    # The old file is in the EasyEDA frame; KiCad's is offset by (120, 80) with
    # Y negated, which is the same shift S2 measured.
    moved, same, new = [], 0, []
    for ref, (nx, ny, nr) in sorted(now.items()):
        if ref not in was:
            new.append(ref)
            continue
        ox, oy, orot = was[ref]
        dx = round(nx - (ox + 120.0), 4)
        dy = round(ny - (oy - 80.0), 4)
        drot = round(((nr - orot) + 180) % 360 - 180, 3)
        if abs(dx) > 0.0011 or abs(dy) > 0.0011 or abs(drot) > 0.01:
            moved.append({"ref": ref, "dx_mm": dx, "dy_mm": dy,
                          "drot_deg": drot})
        else:
            same += 1
    return {"file": old, "unchanged": same, "moved": moved,
            "new_since_august": sorted(new, key=natural),
            "gone_since_august": sorted(set(was) - set(now), key=natural)}


def natural(ref):
    import re
    return [int(t) if t.isdigit() else t
            for t in re.split(r"(\d+)", ref or "")]


if __name__ == "__main__":
    sys.exit(main())
