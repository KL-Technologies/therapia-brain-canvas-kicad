#!/usr/bin/env python3
"""S3 gate: freeze the acceptance criteria and prove the rules can see the bugs.

A design-rule set is only worth anything if it fires on the defects that are
known to be there. This step therefore does not just check that the rules were
written -- it runs DRC and insists that L1..L4 from
cerelog_research/11_rev_a_eco_2026-08-16.md come back out of it:

  L1  mounting hole H4 passes through the AMS1117 GND pad
  L2  the CHASSIS_GND bottom track runs through mounting hole H1
  L3  the ESP_TXD bottom track clips mounting hole H4
  L4  the USB-C peg holes cut the USB_VBUS_RAW routing, and one via's drill
      overlaps a peg drill so its barrel cannot form

If any of them stops being reported, either the rules got loosened or someone
repaired the board -- both need looking at before trusting a later "DRC clean".

Runs 13_fix_import.py's output, so the order is 13 -> 14 -> this. The NPTH pads
must exist first: as long as the six holes are PTH pads and Edge.Cuts polygons,
L1/L2/L4 are invisible to a hole-clearance check.

kicad-cli pcb drc dies inside the command sandbox (see README). Run this from a
normal shell.
"""

import os
import re
import sys
import json
import argparse
import subprocess
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import epro as E                      # noqa: E402
from lib import drc as D                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD_NAME = "Therapia_EEG-HRV"

# Each entry: (id, description, predicate over the item description strings of
# one violation, plus the violation type it has to come back as).
LAYOUT_DEFECTS = [
    ("L1", "mounting hole H4 through the AMS1117 GND pad",
     ("hole_clearance",), ("NPTH pad of H4", "of AMS1117")),
    ("L2", "CHASSIS_GND bottom track through mounting hole H1",
     ("hole_clearance",), ("NPTH pad of H1", "[CHASSIS_GND]")),
    ("L3", "ESP_TXD bottom track clipping mounting hole H4",
     ("hole_clearance",), ("NPTH pad of H4", "[ESP_TXD]")),
    ("L4a", "USB_VBUS_RAW routing inside a USB-C peg hole",
     ("hole_clearance",), ("NPTH pad of PEG", "[USB_VBUS_RAW]")),
    ("L4b", "a via drill overlapping a USB-C peg drill",
     ("hole_to_hole",), ("NPTH pad of PEG", "Via [USB_VBUS_RAW]")),
]


def item_texts(violation):
    return [i.get("description", "") for i in violation.get("items", [])]


def actual_mm(violation):
    m = re.search(r"actual ([\d.]+) mm", violation.get("description", ""))
    return float(m.group(1)) if m else None


def find_defect(violations, types, needles):
    """A violation counts if it is one of `types` and its item descriptions
    contain every needle (each in some item, not necessarily the same one)."""
    hits = []
    for v in violations:
        if v.get("type") not in types:
            continue
        texts = item_texts(v)
        if all(any(n in t for t in texts) for n in needles):
            hits.append({"type": v["type"], "actual_mm": actual_mm(v),
                         "items": texts})
    return hits


def run_drc(kc, board_path, out_path):
    cmd = [kc, "pcb", "drc", "--format", "json", "--severity-all",
           "-o", out_path, board_path]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p


def rules_are_current(root):
    """Re-run the generator into a scratch copy and diff. The rules are only
    frozen if the files on disk are what 14_make_rules.py produces today."""
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="rulecheck")
    try:
        os.makedirs(os.path.join(tmp, "board"))
        os.makedirs(os.path.join(tmp, "contract"))
        os.makedirs(os.path.join(tmp, "logs"))
        for name in (".kicad_pro", ".kicad_dru"):
            src = os.path.join(root, "board", BOARD_NAME + name)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(tmp, "board", BOARD_NAME + name))
        src = os.path.join(root, "contract", "easyeda_rules.json")
        if os.path.exists(src):
            shutil.copy(src, os.path.join(tmp, "contract", "easyeda_rules.json"))
        gen = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "14_make_rules.py")
        p = subprocess.run([sys.executable, gen, "--root", tmp],
                           capture_output=True, text=True)
        if p.returncode != 0:
            return {"ok": False, "reason": p.stderr[-400:]}
        diffs = []
        for name in (".kicad_pro", ".kicad_dru"):
            a = os.path.join(root, "board", BOARD_NAME + name)
            b = os.path.join(tmp, "board", BOARD_NAME + name)
            if not os.path.exists(a):
                diffs.append(name + " missing")
            elif open(a).read() != open(b).read():
                diffs.append(name + " differs from a fresh generation")
        return {"ok": not diffs, "diffs": diffs}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--force-baseline", action="store_true",
                    help="regenerate the baseline even though the ECO has "
                         "already been applied to the board")
    args = ap.parse_args()
    root = args.root

    # The baseline describes the board BEFORE the ECO, and S4 compares against
    # it. Re-running this step after S4 would quietly overwrite it with the
    # post-ECO board, after which S4 could never detect a regression again.
    s4 = os.path.join(root, "gates", "S4.json")
    if os.path.exists(s4) and not args.force_baseline:
        try:
            done = E.load_json(s4).get("pass")
        except ValueError:
            done = False
        if done:
            print("S3: refusing to re-measure the DRC baseline -- S4 has "
                  "already applied the ECO to this board, so the result would "
                  "no longer be a pre-ECO reference. Pass --force-baseline if "
                  "that is really what you want.")
            return 0
    board_path = os.path.join(root, "board", BOARD_NAME + ".kicad_pcb")
    pro = os.path.join(root, "board", BOARD_NAME + ".kicad_pro")
    dru = os.path.join(root, "board", BOARD_NAME + ".kicad_dru")
    acc = os.path.join(root, "ACCEPTANCE.md")
    drc_path = os.path.join(root, "logs", "drc_baseline_rules.json")
    kc = os.environ.get("KC", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")

    checks, notes = [], []
    checks.append(E.gate_check("acceptance_md_exists", True, os.path.exists(acc)))
    checks.append(E.gate_check("kicad_pro_generated", True, os.path.exists(pro)))
    checks.append(E.gate_check("kicad_dru_generated", True, os.path.exists(dru)))

    fresh = rules_are_current(root)
    checks.append(E.gate_check("rules_match_generator", {"ok": True},
                               fresh, ok=fresh.get("ok")))

    # DRC without --refill-zones: the baseline has to describe the board as it
    # stands, not as a refill would leave it.
    proc = run_drc(kc, board_path, drc_path)
    ran = proc.returncode is not None and os.path.exists(drc_path)
    if "Fatal error" in (proc.stdout or "") + (proc.stderr or ""):
        ran = False
        notes.append("kicad-cli died -- this is the sandbox failure mode "
                     "documented in README; re-run from a normal shell.")
    checks.append(E.gate_check("drc_ran", True, bool(ran),
                               note=(proc.stdout or "")[-200:]))

    summary = {}
    defects = {}
    if ran:
        doc = E.load_json(drc_path)
        viol = doc.get("violations", [])
        errors = [v for v in viol if v.get("severity") == "error"]
        # summarize() also records the signature set, which is what S4 and the
        # final check compare against -- kicad-cli's raw counts wobble by a
        # couple of violations between identical runs (see scripts/lib/drc.py).
        summary = D.summarize(doc)
        for did, desc, types, needles in LAYOUT_DEFECTS:
            hits = find_defect(errors, types, needles)
            defects[did] = {"description": desc, "detected": bool(hits),
                            "count": len(hits),
                            "worst_actual_mm": min(
                                [h["actual_mm"] for h in hits
                                 if h["actual_mm"] is not None] or [None])
                            if hits else None,
                            "sample": hits[:3]}
            checks.append(E.gate_check(
                "detects_" + did, "reported", "%d violations" % len(hits),
                ok=bool(hits), note=desc))
        # A hole-clearance map per hole, so S5 has the work list in one place.
        per_hole = collections.defaultdict(list)
        for v in errors:
            if v.get("type") not in ("hole_clearance", "hole_to_hole"):
                continue
            texts = item_texts(v)
            hole = next((t for t in texts if "NPTH pad of" in t), None)
            if not hole:
                continue
            other = [t for t in texts if t != hole]
            per_hole[hole.replace("NPTH pad of ", "")].append(
                {"type": v["type"], "actual_mm": actual_mm(v),
                 "against": "; ".join(other)})
        summary["npth_hole_violations"] = {
            k: sorted(vs, key=lambda r: (r["actual_mm"] is None, r["actual_mm"]))
            for k, vs in sorted(per_hole.items())}
        notes.append("DRC baseline with JLC rules: %d violations "
                     "(%d error / %d warning), unconnected %d"
                     % (summary["violations"], summary["errors"],
                        summary["warnings"], summary["unconnected"]))

    E.write_gate(os.path.join(root, "gates", "S3.json"), "S3", checks,
                 notes=" | ".join(notes),
                 extra={"acceptance": "ACCEPTANCE.md",
                        "drc_baseline": "logs/drc_baseline_rules.json",
                        "drc_summary": summary,
                        "known_defects": defects,
                        "rules_generator": "scripts/14_make_rules.py"})

    ok = all(c["pass"] for c in checks)
    print("S3 pass=%s (%d/%d checks)" % (ok, sum(c["pass"] for c in checks),
                                         len(checks)))
    if summary:
        print("  DRC baseline: %d violations = %d error + %d warning, "
              "unconnected %d" % (summary["violations"], summary["errors"],
                                  summary["warnings"], summary["unconnected"]))
        print("  errors by type: %s" % json.dumps(summary["errors_by_type"]))
    for did in defects:
        d = defects[did]
        print("  %-4s %-8s %2d violations  worst %s mm  %s"
              % (did, "DETECTED" if d["detected"] else "MISSING", d["count"],
                 d["worst_actual_mm"], d["description"]))
    for c in checks:
        if not c["pass"]:
            print("  FAIL %s: expected=%s actual=%s"
                  % (c["name"], json.dumps(c["expected"])[:80],
                     json.dumps(c["actual"])[:200]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
