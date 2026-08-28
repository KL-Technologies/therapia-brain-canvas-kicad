#!/usr/bin/env python3
"""S2B: turn the EasyEDA schematic netlist into the contract S3 works against,
and list every place the imported PCB disagrees with it.

Input is the netlist EasyEDA's own API produces --
`sch_ManufactureData.getNetlistFile()` exported as TSV:

    designator <TAB> pin number <TAB> pin name <TAB> net <TAB> unique id

That file is authoritative for what the schematic intends; the .epcb is
authoritative for what the board currently is. Everything ECO-1 still owes the
PCB shows up as the difference between the two, which is what this writes out.

Runs under system python3; no KiCad needed.
"""

import os
import sys
import glob
import json
import argparse
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import epro as E                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NC_NETS = {"NC", ""}


def read_tsv(path):
    rows = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            ref, num, name, net = parts[0], parts[1], parts[2], parts[3]
            uid = parts[4] if len(parts) > 4 else ""
            rows.append({"ref": ref.strip(), "pin": str(num).strip(),
                         "pin_name": name.strip(), "net": net.strip(),
                         "unique_id": uid.strip(), "line": lineno})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--tsv", help="default: newest contract/netlist_easyeda_api_*.tsv")
    args = ap.parse_args()
    root = args.root

    tsv = args.tsv
    if not tsv:
        cands = sorted(glob.glob(os.path.join(root, "contract",
                                              "netlist_easyeda_api_*.tsv")))
        tsv = max(cands, key=os.path.getmtime) if cands else None
    if not tsv or not os.path.exists(tsv):
        E.write_gate(os.path.join(root, "gates", "S2B.json"), "S2B",
                     [E.gate_check("netlist_tsv_present", "contract/"
                                   "netlist_easyeda_api_*.tsv", "missing",
                                   ok=False)],
                     notes="WAITING FOR INPUT: export the schematic netlist from "
                           "EasyEDA Pro (Run Script: "
                           "sch_ManufactureData.getNetlistFile(), save the "
                           "pinInfoMap as TSV 'designator<TAB>pin<TAB>pin "
                           "name<TAB>net<TAB>unique id') into contract/ and "
                           "re-run. Until then S3 has no authoritative schematic "
                           "netlist -- the geometric solve in "
                           "netlist_from_epro_schematic.json is a cross-check "
                           "only.")
        print("S2B: no netlist TSV in contract/ -- see gates/S2B.json")
        return 1

    rows = read_tsv(tsv)
    sch = collections.defaultdict(dict)
    for r in rows:
        sch[r["ref"]][r["pin"]] = {"name": r["pin_name"], "net": r["net"]}
    contract = {
        "source": {"file": os.path.abspath(tsv), "sha256": E.sha256_file(tsv),
                   "rows": len(rows)},
        "origin": "EasyEDA Pro sch_ManufactureData.getNetlistFile() (pinInfoMap)",
        "note": "Authoritative for what the SCHEMATIC intends. Pin names come "
                "from here; the PCB only carries pad numbers.",
        "components": len(sch),
        "net_pin_counts": dict(sorted(collections.Counter(
            r["net"] for r in rows if r["net"] not in NC_NETS).items())),
        "by_designator": {k: sch[k] for k in sorted(sch)},
    }
    E.dump_json(os.path.join(root, "contract", "netlist_contract.json"), contract)

    pcb_path = os.path.join(root, "contract", "netlist_from_epro_pcb.json")
    if not os.path.exists(pcb_path):
        print("run 10_epro_inventory.py first (%s missing)" % pcb_path)
        return 2
    pcb = E.load_json(pcb_path)["by_designator"]

    only_sch = sorted(set(sch) - set(pcb))
    only_pcb = sorted(set(pcb) - set(sch))
    pin_diff, pin_missing = [], []
    for ref in sorted(set(sch) & set(pcb)):
        for pin, info in sorted(sch[ref].items(), key=lambda kv: kv[0]):
            want = info["net"]
            got = pcb[ref].get(pin)
            if got is None:
                pin_missing.append({"ref": ref, "pin": pin,
                                    "pin_name": info["name"], "schematic": want})
            elif (want in NC_NETS) != (got in NC_NETS) or (
                    want not in NC_NETS and want != got):
                pin_diff.append({"ref": ref, "pin": pin, "pin_name": info["name"],
                                 "schematic": want, "pcb": got})

    diff = {
        "schematic": contract["source"],
        "pcb": E.load_json(pcb_path)["source"],
        "components_only_in_schematic": only_sch,
        "components_only_in_pcb": only_pcb,
        "pins_only_in_schematic": pin_missing,
        "net_differences": pin_diff,
        "summary": {"components_only_in_schematic": len(only_sch),
                    "components_only_in_pcb": len(only_pcb),
                    "pins_missing_on_pcb": len(pin_missing),
                    "pins_with_different_net": len(pin_diff)},
        "reading": "Every entry here is work ECO-1 still owes the PCB: the "
                   "schematic was updated on 2026-08-16 and Import Changes was "
                   "never run. S3 has to reproduce these in KiCad by hand, "
                   "since there is no schematic on the KiCad side to pull from.",
    }
    E.dump_json(os.path.join(root, "gates", "netlist_diff.json"), diff)

    # How good was the geometric solve of the .esch? Only meaningful against the
    # contract, and the answer decides whether anyone may rely on it.
    geo_path = os.path.join(root, "contract", "netlist_from_epro_schematic.json")
    geo_report = None
    if os.path.exists(geo_path):
        geo = E.load_json(geo_path).get("by_designator", {})
        tsv_nc = {(r["ref"], r["pin"]) for r in rows if r["net"] in NC_NETS}
        geo_unres = {(ref, pin) for ref, pins in geo.items()
                     for pin, net in pins.items() if not net}
        agree, wrong = 0, []
        want = {(r["ref"], r["pin"]): r["net"] for r in rows}
        for ref, pins in geo.items():
            for pin, net in pins.items():
                if not net:
                    continue
                w = want.get((ref, pin))
                if w is None:
                    continue
                if w == net:
                    agree += 1
                else:
                    wrong.append({"ref": ref, "pin": pin, "geometric": net,
                                  "contract": w})
        geo_report = {
            "components_missed": sorted(set(sch) - set(geo)),
            "nc_pins_identified_correctly": len(tsv_nc & geo_unres),
            "nc_pins_in_contract": len(tsv_nc),
            "resolved_pins_agreeing": agree,
            "resolved_pins_disagreeing": len(wrong),
            "disagreements": wrong,
            "verdict": "cross-check only -- never use as the contract",
        }
        E.dump_json(os.path.join(root, "gates", "schematic_solver_accuracy.json"),
                    geo_report)

    nets_sch = {n for n in contract["net_pin_counts"]}
    nets_pcb = {n for n, c in E.load_json(pcb_path)["net_pad_counts"].items()}
    checks = [
        E.gate_check("netlist_tsv_present", "present", os.path.basename(tsv),
                     ok=True),
        E.gate_check("netlist_rows", ">=400", len(rows), ok=len(rows) >= 400),
        E.gate_check("pin_names_present", "every row has a pin name",
                     sum(1 for r in rows if not r["pin_name"]),
                     ok=all(r["pin_name"] for r in rows)),
        E.gate_check("every_pcb_component_in_schematic", "0 missing",
                     only_pcb, ok=not only_pcb),
        E.gate_check("diff_written", "gates/netlist_diff.json",
                     "gates/netlist_diff.json", ok=True),
    ]
    new_pads = sum(len(sch[r]) for r in only_sch)
    notes = ("schematic %d components / %d pins vs PCB %d components. "
             "ECO-1 delta = %d pin-level changes: %d nets to change on existing "
             "pins + %d pads on %d new components (%s). %d pins absent from the "
             "PCB. Nets only in the schematic: %s"
             % (len(sch), len(rows), len(pcb),
                len(pin_diff) + new_pads, len(pin_diff), new_pads, len(only_sch),
                ", ".join(only_sch), len(pin_missing),
                ", ".join(sorted(nets_sch - nets_pcb - NC_NETS)) or "none"))
    if geo_report:
        notes += ("; geometric .esch solve: %d/%d NC pins identified, %d agree, "
                  "%d disagree, %d components missed -- cross-check only"
                  % (geo_report["nc_pins_identified_correctly"],
                     geo_report["nc_pins_in_contract"],
                     geo_report["resolved_pins_agreeing"],
                     geo_report["resolved_pins_disagreeing"],
                     len(geo_report["components_missed"])))
    E.write_gate(os.path.join(root, "gates", "S2B.json"), "S2B", checks,
                 notes=notes, extra={"diff": "gates/netlist_diff.json",
                                     "contract": "contract/netlist_contract.json"})

    print("contract netlist: %d components, %d pins (%s)"
          % (len(sch), len(rows), os.path.basename(tsv)))
    print("ECO-1 delta vs PCB: +%d components %s | %d pins re-netted | %d pins absent"
          % (len(only_sch), only_sch, len(pin_diff), len(pin_missing)))
    for d in pin_diff[:20]:
        print("   %-10s pin %-3s %-10s  schematic=%-12s pcb=%s"
              % (d["ref"], d["pin"], d["pin_name"], d["schematic"], d["pcb"] or "(none)"))
    if len(pin_diff) > 20:
        print("   ... +%d more (gates/netlist_diff.json)" % (len(pin_diff) - 20))
    return 0 if all(c["pass"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
