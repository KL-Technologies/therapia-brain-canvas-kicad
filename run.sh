#!/bin/bash
# Brain Canvas: EasyEDA Pro -> KiCad migration pipeline.
#
#   ./run.sh            run every step, skipping the ones whose gate already passes
#   ./run.sh --force    re-run everything from S0
#   ./run.sh --from S2  re-run from a given step
#   ./run.sh --status   print the gate table and exit
#   ./run.sh --no-commit  do not create git commits
#
# A failing gate stops the run with exit 1. S1 failing usually means "no .epro
# has been exported yet" -- that is a wait state, not a defect; see STATUS.md.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export KC="${KC:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}"
export KPY="${KPY:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"
PY3="$(command -v python3)"

STEPS=(S0 S1 S1B S2 S2B S4a S3 S4 S5_uuids S5_L1 S5_L2 S5_L3 S5_L4 S5_L5 S5_mask S6 S7a S7b S7c S7 S8)
FORCE=0; FROM=""; DO_COMMIT=1

gate_pass() {  # $1 = step id
  local f="$ROOT/gates/$1.json"
  [ -f "$f" ] || return 1
  "$PY3" -c "import json,sys; sys.exit(0 if json.load(open('$f')).get('pass') else 1)" 2>/dev/null
}

show_status() {
  "$PY3" - "$ROOT" <<'PY'
import json, os, sys
root = sys.argv[1]
print("%-5s %-6s %-19s %s" % ("STEP", "PASS", "TIMESTAMP", "CHECKS (failed)"))
for step in ("S0", "S1", "S1B", "S2", "S2B", "S4a", "S3", "S4",
             "S5_uuids", "S5_L1", "S5_L2", "S5_L3", "S5_L4", "S5_L5",
             "S5_mask", "S6", "S7a", "S7b", "S7c", "S7", "S8"):
    p = os.path.join(root, "gates", "%s.json" % step)
    if not os.path.exists(p):
        print("%-5s %-6s %-19s %s" % (step, "-", "-", "not run"))
        continue
    d = json.load(open(p))
    checks = d.get("checks", [])
    bad = [c["name"] for c in checks if not c.get("pass")]
    print("%-5s %-6s %-19s %d/%d ok%s" % (
        step, "PASS" if d.get("pass") else "FAIL", d.get("timestamp", "")[:19],
        sum(1 for c in checks if c.get("pass")), len(checks),
        ("  failed: " + ", ".join(bad)) if bad else ""))
    if d.get("notes"):
        print("      notes: %s" % d["notes"][:400])
PY
}

while [ $# -gt 0 ]; do
  case "$1" in
    --status) show_status; exit 0 ;;
    --force)  FORCE=1 ;;
    --from)   FROM="$2"; shift ;;
    --no-commit) DO_COMMIT=0 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac
  shift
done

commit() {  # $1 = step, $2 = summary, $3 = pass/fail
  [ "$DO_COMMIT" = "1" ] || return 0
  git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1 || return 0
  git -C "$ROOT" add -A >/dev/null 2>&1
  git -C "$ROOT" diff --cached --quiet 2>/dev/null && return 0
  if ! git -C "$ROOT" commit -q -m "$1: $2 gate=$3" 2>>"$ROOT/logs/git.txt"; then
    echo "  ! git commit failed (see logs/git.txt); files are on disk regardless"
  fi
}

started=0
run_step() {  # $1 = id, $2 = summary, shift 2 = command
  local id="$1" summary="$2"; shift 2
  if [ -n "$FROM" ] && [ "$started" = "0" ]; then
    if [ "$id" = "$FROM" ]; then started=1; else
      echo "== $id: skipped (--from $FROM)"; return 0; fi
  fi
  if [ "$FORCE" = "0" ] && [ -z "$FROM" ] && gate_pass "$id"; then
    echo "== $id: already passing, skipped"; return 0
  fi
  echo "== $id: $summary"
  "$@"
  local rc=$?
  if [ $rc -eq 0 ] && gate_pass "$id"; then
    commit "$id" "$summary" pass
    echo "== $id: PASS"
    return 0
  fi
  commit "$id" "$summary" fail
  echo "== $id: FAIL (rc=$rc)"
  return 1
}

mkdir -p "$ROOT/logs"
run_step S0 "environment check" bash "$ROOT/scripts/00_env_check.sh" || exit 1
run_step S1 "locate and stage the .epro export" bash "$ROOT/scripts/05_find_epro.sh" || {
  echo
  echo "S1 is waiting for input. Export the project from EasyEDA Pro and drop the"
  echo ".epro into ~/Downloads or $ROOT/import/, then re-run ./run.sh"
  exit 1
}

run_step S1B "convert EasyEDA Pro 3.2 .epro2 into the classic .epro KiCad reads" \
  "$PY3" "$ROOT/scripts/06_epro2_to_epro.py" --root "$ROOT" || exit 1

s2() {
  "$PY3" "$ROOT/scripts/10_epro_inventory.py" --root "$ROOT" || return 1
  "$KPY" "$ROOT/scripts/11_import_epro.py" --root "$ROOT" || return 1
  "$KPY" "$ROOT/scripts/12_verify_import.py" --root "$ROOT" || return 1
}
run_step S2 "import .epro and reconcile against the EasyEDA inventory" s2 || exit 1

run_step S2B "build the contract netlist and diff the PCB against the schematic" \
  "$PY3" "$ROOT/scripts/20_netlist_contract.py" --root "$ROOT" || {
  echo
  echo "S2B needs the EasyEDA schematic netlist. In the EasyEDA Pro editor run"
  echo "sch_ManufactureData.getNetlistFile() and save its pinInfoMap as"
  echo "contract/netlist_easyeda_api_<date>.tsv, then re-run ./run.sh"
  exit 1
}

# S4a before S3 on purpose: until the six mounting holes are real NPTH pads,
# a hole-clearance rule has nothing to fire on and the S3 gate cannot prove
# that the rules detect L1, L2 and L4.
run_step S4a "synthesise the NPTH holes and close the board outline" \
  "$KPY" "$ROOT/scripts/13_fix_import.py" --root "$ROOT" || exit 1

s3() {
  "$PY3" "$ROOT/scripts/14_make_rules.py" --root "$ROOT" || return 1
  "$PY3" "$ROOT/scripts/15_gate_s3.py" --root "$ROOT" || return 1
}
run_step S3 "write the JLC design rules and take the DRC baseline" s3 || exit 1

s4() {
  "$PY3" "$ROOT/scripts/19_make_parts_table.py" --root "$ROOT" || return 1
  "$KPY" "$ROOT/scripts/20_apply_eco.py" --root "$ROOT" || return 1
}
run_step S4 "apply ECO-1/2/3 to the PCB" s4 || exit 1

# --- S5: the layout repairs L1-L5 -------------------------------------------
# The KIID fix comes first. DRC resolves the items in a violation by uuid, and
# the importer gave 231 uuids to more than one item, so until this runs the
# report names the wrong things and every repair that reads it is guessing.
run_step S5_uuids "give every board item its own KIID" \
  "$PY3" "$ROOT/scripts/26_fix_uuids.py" --root "$ROOT" || exit 1

run_step S5_L1 "move AMS1117 out of mounting hole H4" \
  "$KPY" "$ROOT/scripts/30_repair_L1.py" --root "$ROOT" || exit 1
run_step S5_L2 "route CHASSIS_GND around mounting hole H1" \
  "$KPY" "$ROOT/scripts/31_repair_L2.py" --root "$ROOT" || exit 1
run_step S5_L3 "move the ESP_TXD track clear of H4" \
  "$KPY" "$ROOT/scripts/32_repair_L3.py" --root "$ROOT" || exit 1
run_step S5_L4 "clear the USB-C peg holes PEG1 and PEG2" \
  "$KPY" "$ROOT/scripts/33_repair_L4.py" --root "$ROOT" || exit 1
run_step S5_L5 "pull apart the remaining clearance pinches" \
  "$KPY" "$ROOT/scripts/34_repair_L5.py" --root "$ROOT" || exit 1

s5_mask() {
  "$KC" pcb drc --format json --severity-all --units mm --refill-zones \
    --save-board -o "$ROOT/logs/drc_before_mask.json" \
    "$ROOT/board/Therapia_EEG-HRV.kicad_pcb" >/dev/null 2>&1
  "$KPY" "$ROOT/scripts/35_mask_bridges.py" --root "$ROOT" \
    --drc logs/drc_before_mask.json
}
run_step S5_mask "close the merged solder mask openings" s5_mask || exit 1

# --- S6: iterate DRC and repair until it is clean ----------------------------
run_step S6 "run the DRC repair loop to convergence" \
  "$PY3" "$ROOT/scripts/40_drc_loop.py" --root "$ROOT" --no-commit || exit 1

# --- S7: the ECO, the reviews and the acceptance gate -----------------------
run_step S7a "apply ECO-5 and the BOM corrections" \
  "$KPY" "$ROOT/scripts/45_apply_eco5_and_bom.py" --root "$ROOT" || exit 1

run_step S7b "prove the analog signal path was never touched" \
  "$KPY" "$ROOT/scripts/46_analog_untouched.py" --root "$ROOT" || exit 1

# 48 moves a capacitor only if it finds a position that is both nearer and
# free of vias, and saves nothing otherwise, so it is safe to re-run: on a
# board already improved it reports "no improvement available" and stops.
s7c() {
  "$KPY" "$ROOT/scripts/48_improve_vcap3.py" --root "$ROOT" || return 1
  "$KPY" "$ROOT/scripts/47_layout_quality.py" --root "$ROOT" || return 1
}
run_step S7c "measure the layout against the ADS1299 checklist" s7c || exit 1

# --- S8: the manufacturing package ------------------------------------------
# The mask fix and the layer rename both change the board, so they run before
# the export rather than after it.
s8() {
  "$KPY" "$ROOT/scripts/43_fix_pth_mask.py" --root "$ROOT" || return 1
  "$KPY" "$ROOT/scripts/49_normalize_layer_names.py" --root "$ROOT" || return 1
  bash "$ROOT/scripts/60_export_fab.sh" || return 1
  "$KPY" "$ROOT/scripts/61_make_bom_cpl.py" --root "$ROOT" || return 1
  "$PY3" "$ROOT/scripts/63_gate_s8.py" --root "$ROOT" || return 1
}
run_step S8 "export the manufacturing package and check it independently" s8 \
  || exit 1

# S7 last: ACCEPTANCE D-G read the package S8 produces.
run_step S7 "ACCEPTANCE A-G" \
  "$KPY" "$ROOT/scripts/50_final_check.py" --root "$ROOT" || exit 1

echo
show_status
