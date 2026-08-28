#!/usr/bin/env python3
"""S6: run DRC and repair, over and over, until the board is clean or stuck.

    python3 scripts/40_drc_loop.py [--max-iters 20] [--limit 25] [--no-commit]

Each iteration is: run DRC on the board (refilling the zones and saving), look
at what is left, hand it to 41_drc_fix_pass in its own process, commit, and go
round again. The fix pass is a subprocess because pcbnew refuses a second
LoadBoard in one process, so nothing that runs DRC can also hold the board.

It stops for four reasons, and says which:

    clean         no error-severity violations and nothing unconnected
    exhausted     20 iterations
    stalled       two iterations in a row that resolved nothing
    oscillating   a set of violations that has been seen before, which means
                  the repairs are moving the same problem around

The last three are failures, and each unresolved violation is written to
escalations/NNN.md with its items, nets, coordinates, measured value and what
was tried, so a person has the whole case rather than a count.

Counts are never the test. `kicad-cli pcb drc` returns 525 to 531 violations
for a byte-identical board (README), so an iteration is judged by the set of
violation signatures (lib/drc) and by whether the specific things it acted on
are gone -- not by whether the number went down.

Rollback: if an iteration increases the unconnected count, its board is thrown
away with `git checkout -- board/` and the loop stops. Copper that breaks a
connection is worse than the violation it was fixing.

Runs outside the command sandbox (DRC does not work inside it -- see README).
"""

import argparse
import collections
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import drc as D                                    # noqa: E402
import viol as V                                   # noqa: E402
import epro as E                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = "board/Therapia_EEG-HRV.kicad_pcb"

# Violation kinds ACCEPTANCE A allows to remain as warnings. Anything of error
# severity outside this list has to go; this list is not consulted to *demote*
# anything, only to describe the gate.
ALLOWED_WARNING_KINDS = (
    "courtyards_overlap", "silk_overlap", "silk_over_copper",
    "silk_edge_clearance", "starved_thermal", "track_dangling", "via_dangling",
    "isolated_copper", "copper_sliver", "holes_co_located",
    "footprint_type_mismatch", "lib_footprint_issues", "lib_footprint_mismatch",
    "missing_courtyard", "pth_inside_courtyard", "npth_inside_courtyard",
)


def kicad_cli():
    return os.environ.get(
        "KC", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")


def kicad_python():
    return os.environ.get(
        "KPY", "/Applications/KiCad/KiCad.app/Contents/Frameworks/"
               "Python.framework/Versions/Current/bin/python3")


def run_drc(root, out):
    cmd = [kicad_cli(), "pcb", "drc", "--format", "json", "--severity-all",
           "--units", "mm", "--refill-zones", "--save-board",
           "--exit-code-violations", "-o", out, os.path.join(root, BOARD)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    blob = (proc.stdout or "") + (proc.stderr or "")
    if not os.path.exists(out) or "Fatal error" in blob:
        return None, blob
    with open(out) as f:
        return json.load(f), blob


def errors_of(doc):
    return [v for v in doc.get("violations", []) if v.get("severity") == "error"]


def signature_hash(doc):
    sigs = sorted(D.sig_text(D.signature(v)) for v in errors_of(doc))
    return hashlib.sha256("\n".join(sigs).encode()).hexdigest()[:16], sigs


def git(root, *args):
    return subprocess.run(["git", "-C", root] + list(args),
                          capture_output=True, text=True)


def write_escalation(root, n, item):
    d = os.path.join(root, "escalations")
    if not os.path.isdir(d):
        os.makedirs(d)
    path = os.path.join(d, "%03d.md" % n)
    kind = item.get("kind") or item.get("type") or "violation"
    lines = ["# Escalation %03d -- %s" % (n, kind), ""]
    lines.append("The DRC loop could not fix this automatically. It is left on")
    lines.append("the board; the board does not pass ACCEPTANCE A until it is")
    lines.append("resolved.")
    lines.append("")
    lines.append("## What it is")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(item, indent=1)[:6000])
    lines.append("```")
    lines.append("")
    lines.append("## What was tried")
    lines.append("")
    tried = item.get("via_attempts", []) + item.get("track_attempts", [])
    if item.get("reason"):
        tried.append(item["reason"])
    if not tried:
        tried = ["(the pass recorded no attempt detail)"]
    for t in tried:
        lines.append("- %s" % t)
    lines.append("")
    lines.append("## What a person can do")
    lines.append("")
    lines.append("- move one of the two parts by hand and re-run"
                 " `python3 scripts/40_drc_loop.py`")
    lines.append("- or re-route the net through a different layer")
    lines.append("- do not widen the design rule: ACCEPTANCE C is frozen and"
                 " the rule values are what make this a defect")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return os.path.relpath(path, root)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--max-iters", type=int, default=20)
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--no-commit", action="store_true")
    a = ap.parse_args()
    root = a.root
    logs = os.path.join(root, "logs")

    history, seen_hashes = [], {}
    stop, no_progress = None, 0
    prev_unconnected = None
    prev_sigs = None
    doc = None

    for it in range(1, a.max_iters + 1):
        out = os.path.join(logs, "drc_loop_%02d.json" % it)
        doc, blob = run_drc(root, out)
        if doc is None:
            stop = "drc did not run: %s" % blob[-300:]
            break
        errs = errors_of(doc)
        unconn = len(doc.get("unconnected_items", []))
        h, sigs = signature_hash(doc)
        rec = {"iteration": it, "errors": len(errs), "unconnected": unconn,
               "by_type": dict(collections.Counter(v.get("type")
                                                   for v in errs).most_common()),
               "signature_hash": h, "report": os.path.relpath(out, root)}

        if prev_unconnected is not None and unconn > prev_unconnected:
            rec["rolled_back"] = ("unconnected rose %d -> %d; the previous "
                                  "board is restored"
                                  % (prev_unconnected, unconn))
            git(root, "checkout", "--", "board/")
            history.append(rec)
            stop = "a pass broke a connection"
            break

        if not errs and unconn == 0:
            history.append(rec)
            stop = "clean"
            break

        if h in seen_hashes:
            rec["oscillation_with_iteration"] = seen_hashes[h]
            history.append(rec)
            stop = "oscillating"
            break
        seen_hashes[h] = it

        if prev_sigs is not None:
            resolved = len(set(prev_sigs) - set(sigs))
            rec["signatures_resolved_since_last"] = resolved
            no_progress = no_progress + 1 if resolved == 0 else 0
            if no_progress >= 2:
                history.append(rec)
                stop = "stalled"
                break
        prev_sigs = sigs
        prev_unconnected = unconn

        proc = subprocess.run(
            [kicad_python(), os.path.join(root, "scripts",
                                          "41_drc_fix_pass.py"),
             "--root", root, "--drc", out, "--limit", str(a.limit)],
            capture_output=True, text=True)
        try:
            fix = json.loads(proc.stdout)
        except ValueError:
            fix = {"error": "fix pass produced no json",
                   "stderr": proc.stderr[-400:]}
        rec["fix_pass"] = {
            "fixed": len(fix.get("fixed", [])),
            "unresolved": len(fix.get("unresolved", [])),
            "contract_diffs": fix.get("contract_diffs"),
            "islands_reconnected": len(fix.get("islands_reconnected", [])),
            "counts": fix.get("counts"),
        }
        rec["unresolved_detail"] = fix.get("unresolved", [])[:10]
        history.append(rec)

        if not a.no_commit:
            git(root, "add", "board", "logs", "gates")
            git(root, "commit", "-q", "-m",
                "S6 iteration %d: %d errors, %d fixed, %d unresolved"
                % (it, len(errs), len(fix.get("fixed", [])),
                   len(fix.get("unresolved", []))))
        if not fix.get("fixed"):
            no_progress += 1
            if no_progress >= 2:
                stop = "stalled"
                break
    else:
        stop = "exhausted"

    # ---- final measurement -------------------------------------------------
    final_path = os.path.join(logs, "drc_s6_final.json")
    final, blob = run_drc(root, final_path)
    if final is None:
        final = doc or {"violations": [], "unconnected_items": []}
    errs = errors_of(final)
    unconn = len(final.get("unconnected_items", []))

    escalated = []
    n = 1
    for rec in history:
        for item in rec.get("unresolved_detail", []):
            escalated.append(write_escalation(root, n, item))
            n += 1
    if errs and not escalated:
        for v in errs[:20]:
            escalated.append(write_escalation(
                root, n, dict(V.parse(v), kind=v.get("type"),
                              note="left standing at the end of the loop")))
            n += 1

    # counts that the gate reports rather than tests
    counts = history[-1].get("fix_pass", {}).get("counts") if history else None
    checks = [
        E.gate_check("drc_errors", 0, len(errs)),
        E.gate_check("unconnected", 0, unconn),
        E.gate_check("stopped_because", "clean", stop),
        E.gate_check("no_escalations", 0, len(escalated)),
    ]
    E.write_gate(os.path.join(root, "gates", "S6.json"), "S6", checks,
                 notes="%d iterations; stopped: %s. Final DRC: %d errors, "
                       "%d unconnected."
                       % (len(history), stop, len(errs), unconn),
                 extra={"history": history, "stop": stop,
                        "final_by_type": dict(collections.Counter(
                            v.get("type") for v in errs).most_common()),
                        "final_report": os.path.relpath(final_path, root),
                        "escalations": escalated,
                        "counts_at_end": counts,
                        "allowed_warning_kinds": list(ALLOWED_WARNING_KINDS)})
    if not a.no_commit:
        git(root, "add", "board", "logs", "gates", "escalations")
        git(root, "commit", "-q", "-m",
            "S6: DRC loop stopped '%s' -- %d errors, %d unconnected"
            % (stop, len(errs), unconn))

    print(json.dumps({"stop": stop, "iterations": len(history),
                      "errors": len(errs), "unconnected": unconn,
                      "escalations": escalated,
                      "history": [{k: v for k, v in r.items()
                                   if k != "unresolved_detail"}
                                  for r in history]}, indent=1))
    return 0 if (not errs and unconn == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
