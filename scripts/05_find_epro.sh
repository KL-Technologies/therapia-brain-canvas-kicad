#!/bin/bash
# S1 gate: locate the EasyEDA Pro export and stage it under import/.
# Not finding one is a WAIT state, not an error: pass=false, exit 1, and
# STATUS.md tells the human what to drop where.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/import" "$ROOT/gates" "$ROOT/logs"
LOG="$ROOT/logs/find_epro.txt"
: > "$LOG"

SEARCH_DIRS=("$HOME/Downloads" "$HOME/Desktop" "$HOME/Documents" \
             "/Users/dev/projects/therapia-device" "$ROOT/import")

{
  echo "search dirs: ${SEARCH_DIRS[*]}"
  for d in "${SEARCH_DIRS[@]}"; do
    [ -d "$d" ] || { echo "  (missing) $d"; continue; }
    find "$d" -maxdepth 3 \
      \( -iname '*.epro' -o -iname '*.epro2' -o -iname '*.eprj' \
         -o -iname '*Therapia*EEG*.zip' \) \
      -not -path '*/Library/*' -not -path '*/.git/*' 2>/dev/null
  done
} | tee -a "$LOG" | grep -v '^ ' | grep -v '^search dirs' | sort -u > "$ROOT/logs/epro_candidates.txt"

python3 - "$ROOT" <<'PY'
import json, os, sys, zipfile, shutil, datetime
sys.path.insert(0, os.path.join(sys.argv[1], "scripts"))
from lib import epro as E
from lib import epru as U

root = sys.argv[1]
cands = []
listing = os.path.join(root, "logs", "epro_candidates.txt")
if os.path.exists(listing):
    with open(listing) as f:
        cands = [l.strip() for l in f if l.strip() and os.path.isfile(l.strip())]

def looks_like_epro(path):
    """A Gerber zip also matches *Therapia*EEG*.zip -- require real Pro documents.

    Two accepted shapes: the classic .epro (project.json + *.epcb), which KiCad
    reads directly, and the EasyEDA Pro 3.2 .epro2 (project2.json + *.epru),
    which S1B has to convert first.
    """
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
    except Exception as exc:
        return None, "not a zip: %s" % exc
    has_project = any(os.path.basename(n) == "project.json" for n in names)
    has_pcb = any(n.lower().endswith(".epcb") for n in names)
    has_sch = any(n.lower().endswith(".esch") for n in names)
    if has_pcb and (has_project or has_sch):
        return "epro", "classic .epro: project.json=%s .epcb=%d .esch=%d" % (
            has_project, sum(n.lower().endswith(".epcb") for n in names),
            sum(n.lower().endswith(".esch") for n in names))
    is2, why2 = U.looks_like_epro2(path)
    if is2:
        return "epro2", "EasyEDA Pro 3.2 .epro2: %s (needs S1B conversion)" % why2
    return None, "no EasyEDA Pro documents (project.json=%s .epcb=%s; %s)" % (
        has_project, has_pcb, why2)

scored = []
for p in cands:
    kind, why = looks_like_epro(p)
    scored.append({"path": p, "valid": bool(kind), "kind": kind, "why": why,
                   "mtime": os.path.getmtime(p), "size": os.path.getsize(p)})
# a genuine classic .epro outranks an .epro2 of any age (it needs no conversion),
# and both outrank something this pipeline produced itself
def rank(d):
    if d["path"].lower().endswith(".converted.epro"):
        return 0
    return {"epro": 2, "epro2": 1}.get(d["kind"], 0)

scored.sort(key=lambda d: (rank(d), d["mtime"]), reverse=True)
E.dump_json(os.path.join(root, "logs", "epro_candidates.json"), scored)

valid = [s for s in scored if s["valid"]]
checks = [E.gate_check("candidates_scanned", ">=0", len(scored), ok=True),
          E.gate_check("valid_epro_found", 1, len(valid), ok=bool(valid))]
notes = ""
staged = None

if valid:
    src = valid[0]["path"]
    dst = os.path.join(root, "import", os.path.basename(src))
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copy2(src, dst)
    staged = dst
    digest = E.sha256_file(dst)
    with open(os.path.join(root, "import", "SHA256SUMS"), "w") as f:
        f.write("%s  %s\n" % (digest, os.path.basename(dst)))
        f.write("# source: %s\n" % src)
        f.write("# staged: %s\n" % datetime.datetime.now().isoformat(timespec="seconds"))
    checks.append(E.gate_check("staged_into_import", os.path.basename(dst),
                               os.path.basename(dst), ok=True))
    checks.append(E.gate_check("input_kind", "epro or epro2", valid[0]["kind"],
                               ok=True))
    notes = "staged %s (%d bytes, sha256=%s) from %s; %s" % (
        os.path.basename(dst), valid[0]["size"], digest[:16], src, valid[0]["why"])
    if valid[0]["kind"] == "epro2":
        notes += (" | KiCad 10.0.5 cannot read .epro2: it returns an empty board "
                  "(0 footprints, 1 net) without erroring. S1B converts it.")
else:
    notes = ("WAITING FOR INPUT: no .epro found. Export the project from "
             "EasyEDA Pro (File > Export > EasyEDA Pro archive / .epro) and drop "
             "it in ~/Downloads or brain_canvas_kicad/import/, then re-run "
             "./run.sh. Rejected candidates: " +
             ("; ".join("%s (%s)" % (os.path.basename(s['path']), s['why'])
                        for s in scored) or "none found"))

E.write_gate(os.path.join(root, "gates", "S1.json"), "S1", checks, notes,
             extra={"candidates": scored, "staged": staged})
print("S1 pass=%s  %s" % (bool(valid), notes[:160]))
sys.exit(0 if valid else 1)
PY
