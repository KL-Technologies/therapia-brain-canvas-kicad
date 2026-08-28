#!/usr/bin/env python3
"""Smoke test for the pure-python half of the pipeline.

Builds a synthetic classic .epro laid out exactly like the real export
(project.json + PCB/*.epcb + FOOTPRINT/*.efoo + SHEET/*.esch + SYMBOL/*.esym),
carrying the three defects KiCad's importer trips over -- CRLF line endings,
EasyEDA 2.2+ nested RULE payloads, missing NET records -- and checks that the
patcher removes them and the inventory parser measures the board it describes.

Proves the code runs and the record layouts are wired up right. It does not
replace running against the real export.

    python3 scripts/99_selftest.py
"""

import os
import sys
import json
import shutil
import zipfile
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from lib import epro as E                      # noqa: E402

MIL = 1.0 / 0.0254   # mm -> mil
PCB_UUID = "pcb0000000000000000000000000000"
FP_UUID = "fp00000000000000000000000000000a"
SCH_UUID = "sch000000000000000000000000000a"
SYM_UUID = "sym000000000000000000000000000a"


def jl(records):
    return "\r\n".join(json.dumps(r) for r in records) + "\r\n"


def synth_epcb():
    """2 components, 3 nets, a via, a pour, 6 NPTH, a 2434x1772 mil outline."""
    recs = [
        ["DOCTYPE", "PCB", "1.8"],
        ["HEAD", {"editorVersion": "2.2.C", "importFlag": 0}],
        ["LAYER", 1, "TOP", "Top Layer", 3, "#ff0000", 1, "#7f0000", 0.5],
        ["LAYER", 2, "BOTTOM", "Bottom Layer", 3, "#0000ff", 1, "#00007f", 0.5],
        # the #24303 shape: rule payload nested one level deeper in a dict
        ["RULE", "1", "Default", 1, ["mm", {"m": [[4.0157], [5, 5]]}]],
        ["RULE", "3", "Default", 1, ["mm", {"w": [6, 10, 20]}]],
        ["COMPONENT", "c1", 0, 1, 1000.0, -500.0, 90, {"Unique ID": "gge1"}],
        ["ATTR", "a1", 0, "c1", 3, None, None, "Footprint", FP_UUID,
         0, 0, "default", 45, 6, 0, 0, 3, 0, 0, 0, 0, False],
        ["ATTR", "a2", 0, "c1", 3, 1000.0, -520.0, "Designator", "FB5",
         0, 1, "default", 45, 6, 0, 0, 3, 0, 0, 0, 0, False],
        ["COMPONENT", "c2", 0, 1, 1200.0, -600.0, 0, {"Unique ID": "gge2"}],
        ["ATTR", "a3", 0, "c2", 3, None, None, "Footprint", FP_UUID,
         0, 0, "default", 45, 6, 0, 0, 3, 0, 0, 0, 0, False],
        ["ATTR", "a4", 0, "c2", 3, 1200.0, -620.0, "Designator", "U_ADS",
         0, 1, "default", 45, 6, 0, 0, 3, 0, 0, 0, 0, False],
        # only the rows with a pad number carry a net -- the rest are noise
        ["PAD_NET", "c1", "", "", "x1", 0],
        ["PAD_NET", "c1", "1", "VDD_ESP", "x2", 0],
        ["PAD_NET", "c1", "2", "DVDD", "x3", 0],
        ["PAD_NET", "c2", "1", "DVDD", "x4", 0],
        ["PAD_NET", "c2", "2", "GND", "x5", 0],
        ["LINE", "l1", 0, "DVDD", 1, 1010.0, -500.0, 1200.0, -600.0, 8, 0],
        ["LINE", "l2", 0, "GND", 2, 1220.0, -600.0, 1300.0, -600.0, 8, 0],
        ["VIA", "v1", 0, "GND", "", 1300.0, -600.0, 12, 24, 0, None, None, 0, []],
        ["POUR", "z1", 0, "GND", 15, 0.2, "POUR1", 1,
         [[12, -12, "L", 2350, -12, 2350, -1760, 12, -1760, 12, -12]],
         ["SOLID", 8], 0, 0],
        ["POLY", "o1", 0, "", 11, 4,
         [0, 0, "L", 2434, 0, 2434, -1772, 0, -1772, 0, 0], 0],
        # the two positioning pegs, as milled circles on the multi layer
        ["REGION", "r1", 0, 12, 0, 0,
         [["CIRCLE", 56.861075 * MIL, -33.877885 * MIL, 0.35 * MIL]]],
        ["REGION", "r2", 0, 12, 0, 0,
         [["CIRCLE", 56.861075 * MIL, -28.097861 * MIL, 0.35 * MIL]]],
    ]
    for i, (name, x, y) in enumerate((("H1", 3.048, -3.048),
                                      ("H2", 56.9468, -3.048),
                                      ("H3", 3.048, -41.9608),
                                      ("H4", 56.9468, -41.9608))):
        recs.append(["PAD", "np%d" % i, 0, "", 12, name, x * MIL, y * MIL, 0,
                     ["ROUND", 2.3876 * MIL, 2.3876 * MIL],
                     ["ELLIPSE", 2.3876 * MIL, 2.3876 * MIL],
                     [], 0, 0, 0, 0, 0, None, None, None, None, 0])
    return jl(recs)


def synth_efoo():
    return jl([
        ["DOCTYPE", "FOOTPRINT", "1.8"],
        ["HEAD", {"editorVersion": "2.2.C", "uuid": FP_UUID, "title": "R0603"}],
        ["PAD", "p1", 0, "", 1, "1", -10.0, 0.0, 0, ["ROUND", 0, 0],
         ["RECT", 20, 20, 0], [], 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
        ["PAD", "p2", 0, "", 1, "2", 10.0, 0.0, 0, ["ROUND", 0, 0],
         ["RECT", 20, 20, 0], [], 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
    ])


def synth_esym():
    return jl([
        ["DOCTYPE", "SYMBOL", "1.1"],
        ["HEAD", {"originX": 0, "originY": 0, "version": "2", "symbolType": 2}],
        ["PART", "", {"BBOX": [0, -5, 40, 5]}],
        ["PIN", "pn1", 1, None, 0, 0, 10, 180, None, 0, 0],
        ["ATTR", "s1", "pn1", "NAME", "A", 0, 0, None, None, 360, "st1", 0],
        ["ATTR", "s2", "pn1", "NUMBER", "1", 0, 0, None, None, 360, "st1", 0],
        ["PIN", "pn2", 1, None, 40, 0, 10, 0, None, 0, 0],
        ["ATTR", "s3", "pn2", "NAME", "B", 0, 0, None, None, 360, "st1", 0],
        ["ATTR", "s4", "pn2", "NUMBER", "2", 0, 0, None, None, 360, "st1", 0],
    ])


def synth_esch():
    return jl([
        ["DOCTYPE", "SCH", "1.1"],
        ["HEAD", {"originX": 0, "originY": 0, "version": "2"}],
        ["COMPONENT", "e1", "R.1", 100, 100, 0, 0, {}, 0],
        ["ATTR", "e2", "e1", "Designator", "FB5", 0, 1, 0, 0, 0, "st1", 0],
        ["ATTR", "e3", "e1", "Symbol", SYM_UUID, 0, 0, 0, 0, 0, "st1", 0],
        # pin 1 sits at (90,100) once placed; pin 2 at (150,100)
        ["WIRE", "w1", [[50, 100, 90, 100]], "st10", 0],
        ["ATTR", "e4", "w1", "NET", "VDD_ESP", 0, 0, 0, 0, 0, "st1", 0],
        ["WIRE", "w2", [[150, 100, 200, 100]], "st10", 0],
        ["ATTR", "e5", "w2", "NET", "DVDD", 0, 0, 0, 0, 0, "st1", 0],
    ])


def synth_epro(path):
    project = {
        "pcbs": {PCB_UUID: {"title": "PCB1"}},
        "boards": {"b1": {"schematic": SCH_UUID, "pcb": PCB_UUID}},
        "schematics": {SCH_UUID: {"name": "Schematic1",
                                  "sheets": [{"name": "s1", "uuid": "p1", "id": 1}]}},
        "footprints": {FP_UUID: {"title": "R0603"}},
        "symbols": {SYM_UUID: {"title": "R"}},
        "devices": {},
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.json", json.dumps(project))
        z.writestr("PCB/%s.epcb" % PCB_UUID, synth_epcb())
        z.writestr("FOOTPRINT/%s.efoo" % FP_UUID, synth_efoo())
        z.writestr("SYMBOL/%s.esym" % SYM_UUID, synth_esym())
        z.writestr("SHEET/%s/1.esch" % SCH_UUID, synth_esch())


def main():
    fails = []

    def check(name, cond, detail=""):
        print("  %-42s %s %s" % (name, "ok" if cond else "FAIL", detail))
        if not cond:
            fails.append(name)

    tmp = tempfile.mkdtemp(prefix="epro_selftest_")
    try:
        src = os.path.join(tmp, "synth.epro")
        synth_epro(src)

        # --- patcher
        with zipfile.ZipFile(src) as z:
            raw = z.read("PCB/%s.epcb" % PCB_UUID)
        check("source has CRLF", b"\r\n" in raw)
        check("source has no NET records", b'["NET"' not in raw)

        dst = os.path.join(tmp, "patched.epro")
        E.patch_epro(src, dst)
        with zipfile.ZipFile(dst) as z:
            fixed = z.read("PCB/%s.epcb" % PCB_UUID).decode()
        recs = [json.loads(l) for l in fixed.splitlines() if l.strip()]
        nets = [r[1] for r in recs if r[0] == "NET"]
        rules = [r for r in recs if r[0] == "RULE"]
        check("CRLF normalised", "\r" not in fixed)
        check("NET records injected", set(nets) == {"VDD_ESP", "DVDD", "GND"},
              str(sorted(nets)))
        check("NETs precede first use",
              min(i for i, r in enumerate(recs) if r[0] == "NET")
              < min(i for i, r in enumerate(recs) if r[0] == "PAD_NET"))
        check("RULE payloads flattened",
              all(not (isinstance(r[4], list) and len(r[4]) > 1
                       and isinstance(r[4][1], dict)) for r in rules),
              json.dumps([r[4] for r in rules]))
        check("patch is idempotent",
              E.patch_epro(dst, os.path.join(tmp, "p2.epro"))["documents"]
              ["PCB/%s.epcb" % PCB_UUID]["nets"]["injected"] == 0)

        # --- inventory
        work = os.path.join(tmp, "root")
        for d in ("import", "gates", "contract", "logs", "board"):
            os.makedirs(os.path.join(work, d))
        shutil.copy2(src, os.path.join(work, "import", "synth.epro"))
        r = subprocess.run([sys.executable, os.path.join(HERE, "10_epro_inventory.py"),
                            "--root", work],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = r.stdout.decode()
        check("10_epro_inventory.py runs", r.returncode == 0, out.strip()[-400:])
        if r.returncode != 0:
            return 1
        inv = E.load_json(os.path.join(work, "gates", "inventory_easyeda.json"))
        check("footprints counted", inv["footprints"]["count"] == 2,
              str(inv["footprints"]["count"]))
        check("designators read from ATTR",
              inv["footprints"]["designators"] == ["FB5", "U_ADS"],
              str(inv["footprints"]["designators"]))
        check("footprint library resolved",
              not inv["footprints"]["unresolved_footprints"]
              and inv["footprints"]["library"][FP_UUID]["pads"] == 2,
              json.dumps(inv["footprints"]["library"]))
        check("pads split component/standalone",
              (inv["pads"]["in_components"], inv["pads"]["standalone"]) == (4, 4),
              json.dumps(inv["pads"]))
        check("PAD_NET applied to footprint pads",
              inv["nets"]["pad_counts"] == {"DVDD": 2, "GND": 1, "VDD_ESP": 1},
              json.dumps(inv["nets"]["pad_counts"]))
        check("tracks per layer",
              inv["tracks"]["by_layer"].get("F.Cu") == 1
              and inv["tracks"]["by_layer"].get("B.Cu") == 1,
              json.dumps(inv["tracks"]["by_layer"]))
        check("vias counted", inv["vias"]["total"] == 1)
        check("pour counted", inv["zones"]["pour_count"] == 1)
        check("all 6 NPTH matched", inv["npth"]["all_expected_found"],
              json.dumps([m["name"] for m in inv["npth"]["expected_match"]
                          if not m["found"]]))
        check("NPTH diameters matched",
              all(m["dia_ok"] for m in inv["npth"]["expected_match"]),
              json.dumps([m["name"] for m in inv["npth"]["expected_match"]
                          if not m["dia_ok"]]))
        ob = inv["outline_bbox_mm"]
        check("outline 61.8236 x 45.0088",
              E.approx(ob["width_mm"], 61.8236, 0.01)
              and E.approx(ob["height_mm"], 45.0088, 0.01),
              "%.4f x %.4f" % (ob["width_mm"], ob["height_mm"]))
        check("rotations collected", set(inv["rotations"]) == {"0.0", "90.0"},
              json.dumps(inv["rotations"]))
        pcbnl = E.load_json(os.path.join(work, "contract",
                                         "netlist_from_epro_pcb.json"))
        check("pcb netlist by designator",
              pcbnl["by_designator"]["U_ADS"] == {"1": "DVDD", "2": "GND"},
              json.dumps(pcbnl["by_designator"]))
        check("placement transform applied",
              E.approx(pcbnl["by_designator"] and
                       next(p["y_mm"] for p in pcbnl["pads"]
                            if p["ref"] == "FB5" and p["pad"] == "1"),
                       (-500.0 - 10.0) * 0.0254, 1e-6),
              "FB5 pad1 y after 90deg rotation")
        schnl = E.load_json(os.path.join(work, "contract",
                                         "netlist_from_epro_schematic.json"))
        check("schematic netlist solved",
              schnl["by_designator"].get("FB5") == {"1": "VDD_ESP", "2": "DVDD"},
              json.dumps(schnl.get("by_designator")))
        check("easyeda rules captured",
              len(E.load_json(os.path.join(work, "contract",
                                           "easyeda_rules.json"))["rules"]) == 2)
        check("no unhandled record types", not inv["unhandled_record_types"],
              json.dumps(inv["unhandled_record_types"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nselftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
