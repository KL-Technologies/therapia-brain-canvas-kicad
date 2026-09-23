#!/usr/bin/env python3
"""Run every simulation case and write the S3_sim gate.

    python3 sim/run_all.py [--root DIR] [--only CASE ...]

Each case under ``sim/cases/`` is a standalone script that writes its own
JSON to ``sim/out/``; this collects them into ``gates/S3_sim.json`` in the
same shape the rest of the pipeline's gates use (pass, timestamp, checks,
notes) plus a ``models`` section.

That models section is not decoration.  Some devices carry TI's own vendor
model and some carry a behavioural one written for this board, and a gate
that says "pass" without saying which is which would be worse than no gate at
all.  Every case declares its own model provenance and this script carries it
up into the gate, scoped by case so nothing is overwritten.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CASES = ["power_tree_startup", "ldo_stability", "drl_loop", "esp32_autoreset"]
# The number of checks the four cases make when every one of them runs. A case
# that loses a row (a model that failed and was left out) must not leave the
# gate green on fewer: the count is a check of its own.
EXPECTED_CHECKS = 29


def run_case(name, python):
    """Run one case script; return (returncode, parsed result or None)."""
    script = os.path.join(HERE, "cases", "%s.py" % name)
    out = os.path.join(HERE, "out", "%s.json" % name)
    if os.path.exists(out):
        os.remove(out)
    t0 = time.time()
    proc = subprocess.run([python, script], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    dt = time.time() - t0
    doc = None
    if os.path.exists(out):
        with open(out) as fh:
            doc = json.load(fh)
    return proc.returncode, doc, proc.stdout.decode("utf-8", "replace"), dt


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()

    names = args.only or CASES
    checks, results, models, notes = [], {}, {}, []
    for name in names:
        rc, doc, log, dt = run_case(name, args.python)
        if doc is None:
            checks.append({"name": name, "pass": False,
                           "detail": "case produced no result (rc=%d): %s" % (rc, log[-300:])})
            continue
        results[name] = doc
        # Scoped by case: two cases may legitimately model the same part
        # differently, and an unscoped update would let the later one
        # silently overwrite the earlier claim in the gate.
        for dev, how in doc.get("models", {}).items():
            models["%s / %s" % (name, dev)] = how
        for c in doc.get("checks", []):
            checks.append({"name": "%s / %s" % (name, c["name"]),
                           "pass": bool(c.get("pass")),
                           "detail": c.get("detail", "")})
        print("%-22s %-4s  %5.1fs  %d/%d checks"
              % (name, "PASS" if doc["pass"] else "FAIL", dt,
                 sum(1 for c in doc["checks"] if c.get("pass")), len(doc["checks"])))

    # headline numbers worth having in the gate without opening sim/out/
    key = {}
    if "power_tree_startup" in results:
        n = results["power_tree_startup"]["numbers"]
        key["TPS72325_EN_asserted"] = n.get("tps72325_en", {}).get("asserted")
        key["AVSS_ripple_pp_V"] = n.get("AVSS_ripple_pp_V")
        key["AVSS_ripple_datasheet_PSRR_bound_V"] = n.get("AVSS_ripple_datasheet_PSRR_bound_V")
        key["VDD_ESP_after_300mA_step_V"] = n.get("VDD_ESP_after_step_V")
    if "ldo_stability" in results:
        n = results["ldo_stability"]["numbers"]
        for k in ("AVDD_Cout_derated_F", "AVSS_Cout_derated_F",
                  "TLV70025_phase_margin_deg", "TPS72325_phase_margin_deg"):
            key[k] = n.get(k)
    if "drl_loop" in results:
        n = results["drl_loop"]["numbers"]
        key["DRL_worst_phase_margin_deg"] = n.get("post_eco_worst_pm_deg")
        eco = n.get("eco5_comparison", {})
        key["DRL_pm_pre_ECO5_deg"] = eco.get("pre_eco", {}).get("pm_deg")
        key["DRL_pm_post_ECO5_deg"] = eco.get("post_eco", {}).get("pm_deg")
        key["DRL_50Hz_suppression_dB"] = eco.get("post_eco", {}).get("drl_suppression_dB")
    if "esp32_autoreset" in results:
        n = results["esp32_autoreset"]["numbers"]
        key["EN_delay_derated_s"] = n.get("en_delay", {}).get("derated", {}).get("delay_s")
        key["EN_delay_nominal_s"] = n.get("en_delay", {}).get("nominal", {}).get("delay_s")
        key["worst_ESP32_pin_V"] = max(
            (max(r["EN_V"], r["IO0_V"]) for r in n.get("truth_table", [])), default=None)

    for name, doc in results.items():
        if doc.get("notes"):
            notes.append("[%s] %s" % (name, doc["notes"]))

    if not args.only:
        checks.append({"name": "all %d expected checks were made"
                               % EXPECTED_CHECKS,
                       "pass": len(checks) == EXPECTED_CHECKS,
                       "detail": "%d made" % len(checks)})
    passed = bool(checks) and all(c["pass"] for c in checks)
    gate = {
        "pass": passed,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "step": "S3_sim",
        "summary": "headless ngspice simulation of the Rev.A power tree, LDO "
                   "stability, DRL loop and ESP32 auto-reset",
        "engine": {
            "library": "/Applications/KiCad/KiCad.app/Contents/Frameworks/libngspice.0.dylib",
            "version": "ngspice-45.2 shared library (bundled with KiCad 10.0.5)",
            "driver": "sim/lib/ngspice_ctypes.py (ctypes, one subprocess per netlist)",
            "python": sys.version.split()[0],
        },
        "checks": checks,
        "key_numbers": key,
        "models": models,
        "model_provenance": "sim/models/PROVENANCE.md",
        "cases": {k: {"pass": v["pass"], "result": "sim/out/%s.json" % k}
                  for k, v in results.items()},
        "notes": "\n".join(notes),
    }
    path = os.path.join(args.root, "gates", "S3_sim.json")
    with open(path, "w") as fh:
        json.dump(gate, fh, indent=2, default=str)

    nfail = sum(1 for c in checks if not c["pass"])
    print("\n%s : %d/%d checks pass -> %s"
          % ("S3_sim", len(checks) - nfail, len(checks), "PASS" if passed else "FAIL"))
    if nfail:
        print("failed checks:")
        for c in checks:
            if not c["pass"]:
                print("  - %s\n      %s" % (c["name"], c["detail"]))
    print("gate written to %s" % path)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
