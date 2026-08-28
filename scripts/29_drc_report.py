#!/usr/bin/env python3
"""Print a DRC report grouped the way the repairs are organised.

    python3 scripts/29_drc_report.py [--log logs/drc_after_eco.json]
                                     [--type hole_clearance] [--severity error]
                                     [--json]

Read-only. Runs on a saved report; it does not invoke kicad-cli (DRC does not
work inside the command sandbox -- see README).
"""

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import viol  # noqa: E402


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=here)
    ap.add_argument("--log", default="logs/drc_after_eco.json")
    ap.add_argument("--type", default=None)
    ap.add_argument("--severity", default="error")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    path = a.log if os.path.isabs(a.log) else os.path.join(a.root, a.log)
    with open(path) as f:
        doc = json.load(f)

    sel = [v for v in doc.get("violations", [])
           if (not a.severity or a.severity == "all"
               or v.get("severity") == a.severity)
           and (not a.type or v.get("type") == a.type)]

    if a.json:
        print(json.dumps([dict(viol.parse(v), key=viol.key_text(viol.key(v)))
                          for v in sel], indent=1))
        return 0

    print("%s: %d violations (%d unconnected), showing %d" % (
        os.path.relpath(path, a.root), len(doc.get("violations", [])),
        len(doc.get("unconnected_items", [])), len(sel)))
    print("severity counts: %s" % dict(collections.Counter(
        v.get("severity") for v in doc.get("violations", []))))
    print()

    for kind, group in viol.group_by_type(sel).items():
        print("=== %s  (%d) ===" % (kind, len(group)))
        for v in group:
            p = viol.parse(v)
            head = "  [%s] actual=%s req=%s" % (
                p["rule"] or "-",
                "%.4f" % p["actual_mm"] if p["actual_mm"] is not None else "-",
                "%.4f" % p["required_mm"] if p["required_mm"] is not None
                else "-")
            print(head)
            for i in p["items"]:
                print("      %-5s %-16s %-8s (%9.4f, %9.4f)  %s" % (
                    i["class"], i["net"] or "-", i["ref"] or "-",
                    i["x"] or 0.0, i["y"] or 0.0,
                    ", ".join(i["layers"]) or "-"))
        print()

    npth = collections.Counter()
    for v in sel:
        for ref in viol.involving_npth(v):
            npth[ref] += 1
    if npth:
        print("violations involving an NPTH hole: %s" % dict(npth))
    nets = collections.Counter()
    for v in sel:
        for n in viol.parse(v)["nets"]:
            nets[n] += 1
    print("nets involved: %s" % dict(nets.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
