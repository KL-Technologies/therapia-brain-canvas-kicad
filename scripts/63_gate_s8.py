#!/usr/bin/env python3
"""S8 gate -- is the manufacturing package complete and self-consistent?

    python3 scripts/63_gate_s8.py

S7 (50_final_check.py) decides whether the board may be ordered; this decides
whether the package that would be uploaded is the one that was checked. It
reads the files rather than the logs, so a stale export cannot pass by quoting
a fresh log.

Plain python3.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import epro as E                                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ARCHIVE = "Therapia_EEG-HRV_Rev.A.zip"
ZIP_CONTENTS = 14
FITTED = 133
DNP = ["R_IO15_DN", "R_RST_UP"]
MECHANICAL = ["H1", "H2", "H3", "H4", "PEG1", "PEG2"]


def check(name, expected, actual, ok=None, note=None):
    return E.gate_check(name, expected, actual, ok=ok, note=note)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=ROOT)
    a = ap.parse_args()
    root = a.root
    fab = os.path.join(root, "fab")
    log = {}

    zpath = os.path.join(fab, ARCHIVE)
    names = []
    if os.path.exists(zpath):
        with zipfile.ZipFile(zpath) as z:
            names = sorted(z.namelist())
    log["archive"] = {"path": zpath, "files": names,
                      "bytes": os.path.getsize(zpath)
                      if os.path.exists(zpath) else 0}

    fabcheck = json.loads(subprocess.run(
        [sys.executable, os.path.join(HERE, "62_check_fab.py"),
         "--root", root, "--json"], capture_output=True, text=True).stdout)
    log["independent_parse"] = {
        k: fabcheck.get(k) for k in
        ("missing_layers", "unexpected_files", "all_parsed", "copper_all_dark",
         "empty_layers", "npth_clear", "planes_filled", "copper_coverage",
         "outline", "vs_2026_08_16")}
    log["ipc_d356"] = fabcheck.get("ipc_d356", {})
    log["gbrjob"] = fabcheck.get("gbrjob", {})
    log["odb"] = fabcheck.get("odb", {})

    bom_path = os.path.join(fab, "BOM_JLCPCB.csv")
    cpl_path = os.path.join(fab, "CPL_JLCPCB.csv")
    with open(bom_path) as f:
        bom = list(csv.DictReader(f))
    with open(cpl_path) as f:
        cpl = list(csv.DictReader(f))
    bom_refs = []
    for r in bom:
        bom_refs += [x.strip() for x in r["Designator"].split(",") if x.strip()]
    cpl_refs = [r["Designator"] for r in cpl]
    log["bom"] = {"rows": len(bom), "parts": len(bom_refs),
                  "columns": list(bom[0].keys()) if bom else []}
    log["cpl"] = {"rows": len(cpl),
                  "columns": list(cpl[0].keys()) if cpl else [],
                  "sides": sorted({r["Layer"] for r in cpl})}

    prev = {n: os.path.exists(os.path.join(fab, n))
            for n in ("preview_top.png", "preview_bottom.png",
                      "assembly_top.pdf", "README_発注手順.md")}
    log["human_facing"] = prev

    placement = {}
    overrides = {}
    p = os.path.join(root, "logs", "bom_cpl.json")
    if os.path.exists(p):
        doc = E.load_json(p)
        placement = doc.get("vs_2026_08_16") or {}
        overrides = doc.get("cpl_overrides") or {}
    log["vs_august_placement"] = placement
    # A hand-corrected number in the file that goes to the assembler has to be
    # visible in the gate, not only in a log: it is the one field in the
    # package that the board itself cannot vouch for.
    log["cpl_overrides"] = overrides

    excluded = set(DNP) | set(MECHANICAL)
    checks = [
        check("archive present", True, os.path.exists(zpath)),
        check("archive holds the 14 files ACCEPTANCE E counts",
              ZIP_CONTENTS, len(names)),
        check("archive holds no drill map or stray file", [],
              [n for n in names if n.endswith((".pdf", ".png", ".csv"))]),
        check("every expected gerber layer present", [],
              fabcheck.get("missing_layers", ["?"])),
        check("all files read by our own parser", True,
              fabcheck.get("all_parsed")),
        check("copper layers additive only", True,
              fabcheck.get("copper_all_dark")),
        check("outline within 0.01 mm", True,
              fabcheck.get("outline", {}).get("ok")),
        check("no copper inside any NPTH ring", True,
              fabcheck.get("npth_clear")),
        check("inner planes actually filled", True,
              fabcheck.get("planes_filled")),
        check("outline matches the 2026-08-16 package", [61.8236, 45.0088],
              (fabcheck.get("vs_2026_08_16") or {}).get("outline_mm")),
        check("NPTH count matches the 2026-08-16 package", 6,
              (fabcheck.get("vs_2026_08_16") or {}).get("npth_hits")),
        check("BOM rows carry the JLC columns",
              True, log["bom"]["columns"][:4] ==
              ["Comment", "Designator", "Footprint", "LCSC Part #"]),
        check("BOM parts", FITTED, len(bom_refs)),
        check("BOM has no repeated designator", [],
              sorted({x for x in bom_refs if bom_refs.count(x) > 1})),
        check("CPL columns", ["Designator", "Mid X", "Mid Y", "Layer",
                              "Rotation"], log["cpl"]["columns"]),
        check("CPL rows", FITTED, len(cpl)),
        check("CPL is top side only", ["Top"], log["cpl"]["sides"]),
        check("BOM and CPL name the same parts", True,
              sorted(bom_refs) == sorted(cpl_refs)),
        check("DNP and mechanical parts in neither file", [],
              sorted(excluded & (set(bom_refs) | set(cpl_refs)))),
        check("placements unchanged since 2026-08-16", 120,
              placement.get("unchanged"),
              note="129 parts existed in August; the 9 that differ are the L1 "
                   "repair (AMS1117), four S5 nudges (C_3V3_H, C_AVSS_B, "
                   "C_RST_DLY, C_VREFP_10n), the two ECO-3 1206 swaps "
                   "(C_VCAP1, C_VREFP_10u), the L7 move of R_CC1 out of the "
                   "USB-C shell, and U_MCU -- which did not move at all: only "
                   "its CPL rotation did, 0 -> 90, because the 32UE's JLC "
                   "footprint is drawn along Y (data/cpl_overrides.json). "
                   "Each is listed in vs_august_placement"),
        check("parts moved since August are all accounted for", 9,
              len(placement.get("moved", []))),
        check("parts new since August", ["C_VCAP1_H", "C_VCAP2", "C_VCAP3",
                                         "C_VCAP3_H"],
              placement.get("new_since_august")),
        check("every CPL override was applied and named a real part", [],
              overrides.get("named_but_not_in_the_cpl", ["log missing"]),
              note="applied: %s" % json.dumps(
                  [{k: o[k] for k in ("designator", "field", "from", "to")}
                   for o in overrides.get("applied", [])])),
        check("previews and assembly drawing written", True,
              all(prev.values())),
        # Three files, three code paths inside KiCad, one answer. Gerber says
        # it in graphics plus X2 attributes, IPC-D-356 says it as data, ODB++
        # says it in its own netlist. Agreement across them is worth more than
        # any one of them being self-consistent.
        check("IPC-D-356 exported and fully parsed", 0,
              log["ipc_d356"].get("unparsed_lines", -1)),
        check("IPC-D-356 net set matches the contract", True,
              log["ipc_d356"].get("nets", {}).get("match")),
        check("IPC-D-356 finds 6 unplated holes in the right places", True,
              log["ipc_d356"].get("npth_ok")),
        check("Gerber X2 and IPC-D-356 agree on every top pad's net", True,
              log["ipc_d356"].get("gerber_x2_agreement", {}).get("ok"),
              note="read through the sticky TO.N state machine cleared by "
                   "TD -- KiCad emits the attribute only on a change, so "
                   "taking the line above each flash would mis-net most of "
                   "them ({} sets, {} deletes on F.Cu)".format(
                       log["ipc_d356"].get("gerber_x2_agreement", {})
                       .get("gerber_attr_sets", 0),
                       log["ipc_d356"].get("gerber_x2_agreement", {})
                       .get("gerber_attr_deletes", 0))),
        check("ODB++ netlist names the same nets", 79,
              log["odb"].get("nets")),
        check("ODB++ point count = pads + vias", 678,
              log["odb"].get("netlist_points"),
              note="678 until L7: USB_CC1 cannot enter J1 pad 4 from the "
                   "west, so it crosses the pad column on B.Cu and the board "
                   "gained two vias (gates/S5_L7.json), 680; S7v removed two "
                   "AVSS vias that reached nothing but F.Cu (logs/"
                   "viapad_fix.json), 678 again. The same counts show in "
                   "ACCEPTANCE D's IPC-D-356 check"),
        check(".gbrjob agrees on layers, thickness, stackup and rules", True,
              log["gbrjob"].get("ok")),
    ]
    E.write_gate(os.path.join(root, "gates", "S8.json"), "S8", checks,
                 notes="The uploadable package, read back from the files. "
                       "Geometry and drill are checked by "
                       "lib/gerber_parse.py, not by KiCad.",
                 extra=log)
    bad = [c["name"] for c in checks if not c["pass"]]
    print("S8: %s" % ("pass" if not bad else "FAIL"))
    for c in checks:
        print("  %-1s %-52s %s"
              % ("" if c["pass"] else "!", c["name"],
                 "ok" if c["pass"] else "expected %r got %r"
                 % (c["expected"], c["actual"])))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
