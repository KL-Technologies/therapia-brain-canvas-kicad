#!/bin/bash
# S0 gate: the toolchain this pipeline depends on is present and capable.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KC="${KC:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}"
KPY="${KPY:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"
LOG="$ROOT/logs/env_check.txt"
mkdir -p "$ROOT/logs" "$ROOT/gates"
: > "$LOG"

names=(); expected=(); actual=(); passed=()
add() { names+=("$1"); expected+=("$2"); actual+=("$3"); passed+=("$4"); }

say() { echo "$@" | tee -a "$LOG"; }

# 1. kicad-cli present, version >= 10
KC_VER="$("$KC" version 2>>"$LOG")" || KC_VER="MISSING"
say "kicad-cli: $KC_VER ($KC)"
KC_MAJOR="${KC_VER%%.*}"
if [ "${KC_MAJOR:-0}" -ge 10 ] 2>/dev/null; then ok=true; else ok=false; fi
add "kicad_cli_version" ">=10" "$KC_VER" "$ok"

# 2. bundled python + pcbnew
PY_VER="$("$KPY" -V 2>&1)" || PY_VER="MISSING"
say "kicad python: $PY_VER ($KPY)"
add "kicad_python" "Python 3.9.x" "$PY_VER" "$([ "${PY_VER#Python 3.9}" != "$PY_VER" ] && echo true || echo false)"

PROBE="$("$KPY" - <<'PY' 2>>"$LOG"
import json
r = {}
try:
    import pcbnew
    r["import_pcbnew"] = True
    r["build_version"] = pcbnew.GetBuildVersion()
    r["EASYEDAPRO"] = hasattr(pcbnew.PCB_IO_MGR, "EASYEDAPRO")
    r["KICAD_SEXP"] = hasattr(pcbnew.PCB_IO_MGR, "KICAD_SEXP")
    r["ZONE_FILLER"] = hasattr(pcbnew, "ZONE_FILLER")
    r["str_utf8_Map"] = hasattr(pcbnew, "str_utf8_Map")
except Exception as exc:
    r["import_pcbnew"] = False
    r["error"] = str(exc)
print(json.dumps(r))
PY
)" || PROBE='{"import_pcbnew": false}'
say "pcbnew probe: $PROBE"
jget() { python3 -c "import json,sys; print(json.loads(sys.argv[1]).get(sys.argv[2], False))" "$PROBE" "$1" 2>/dev/null || echo False; }

for k in import_pcbnew EASYEDAPRO KICAD_SEXP ZONE_FILLER str_utf8_Map; do
  v="$(jget "$k")"
  add "pcbnew_$k" "True" "$v" "$([ "$v" = "True" ] && echo true || echo false)"
done

# 3. drc supports --refill-zones (needed before any DRC count is meaningful)
DRC_HELP="$("$KC" pcb drc --help 2>&1)"
echo "$DRC_HELP" >> "$LOG"
if echo "$DRC_HELP" | grep -q -- "--refill-zones"; then r=true; else r=false; fi
add "drc_refill_zones_flag" "present" "$r" "$r"
if echo "$DRC_HELP" | grep -q -- "--save"; then s=true; else s=false; fi
add "drc_save_flag" "present" "$s" "$s"

# 4. system python3 (pure-JSON steps)
SYS_PY="$(python3 -V 2>&1)"
say "system python: $SYS_PY"
add "system_python3" "Python 3.x" "$SYS_PY" "$([ "${SYS_PY#Python 3}" != "$SYS_PY" ] && echo true || echo false)"

# 5. repo layout
missing=""
for d in import board scripts scripts/lib gates fab contract logs; do
  [ -d "$ROOT/$d" ] || missing="$missing $d"
done
add "repo_layout" "all dirs present" "${missing:-ok}" "$([ -z "$missing" ] && echo true || echo false)"

python3 - "$ROOT/gates/S0.json" "$KC" "$KPY" "$KC_VER" "$PY_VER" <<'PY' \
  "${names[@]}" --SEP-- "${expected[@]}" --SEP-- "${actual[@]}" --SEP-- "${passed[@]}"
import sys, json, datetime
out, kc, kpy, kcver, pyver = sys.argv[1:6]
rest = sys.argv[6:]
parts, cur = [], []
for a in rest:
    if a == "--SEP--":
        parts.append(cur); cur = []
    else:
        cur.append(a)
parts.append(cur)
names, expected, actual, passed = parts
checks = [{"name": n, "expected": e, "actual": a, "pass": p == "true"}
          for n, e, a, p in zip(names, expected, actual, passed)]
doc = {"step": "S0", "pass": all(c["pass"] for c in checks), "checks": checks,
       "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
       "notes": "kicad-cli=%s (%s); kicad python=%s (%s)" % (kcver, kc, pyver, kpy)}
json.dump(doc, open(out, "w"), indent=2, ensure_ascii=False)
open(out, "a").write("\n")
print("S0 pass=%s (%d checks)" % (doc["pass"], len(checks)))
PY

python3 -c "import json,sys; sys.exit(0 if json.load(open('$ROOT/gates/S0.json'))['pass'] else 1)"
