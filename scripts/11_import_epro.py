#!/usr/bin/env python3
"""S2b: import the .epro through KiCad's own EasyEDA Pro parser, headless.

KiCad's importer has two known defects against current EasyEDA exports:
  #24303  JSON schema abort ("type must be number, but is array") from the
          v2.2+ nested RULE payloads
  #19021  every pad and track lands on one merged net because the leading NET
          records are missing
Both are worked around by patching the archive, not the importer. The patch is
applied in escalating stages and every stage is scored against
gates/inventory_easyeda.json, so the least-modified archive that reproduces the
EasyEDA net/footprint counts wins.

Each attempt runs in its own KiCad-python subprocess: a parser abort kills the
child, not the pipeline.
"""

import os
import sys
import json
import shutil
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import epro as E                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KPY_DEFAULT = ("/Applications/KiCad/KiCad.app/Contents/Frameworks/"
               "Python.framework/Versions/Current/bin/python3")
KC_DEFAULT = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
BOARD_NAME = "Therapia_EEG-HRV"

CHILD = r'''
import sys, json, collections
result = {"ok": False}
try:
    # No wx.App on purpose: headless it raises SystemExit ("This program needs
    # access to the screen") and would take the whole child down. PCB_IO_MGR
    # works without it.
    import pcbnew
    epro, out, pcb_id = sys.argv[1], sys.argv[2], sys.argv[3]
    props = None
    if pcb_id:
        props = pcbnew.str_utf8_Map()
        try:
            props["pcb_id"] = pcbnew.UTF8(pcb_id)
        except Exception:
            props["pcb_id"] = pcb_id
    board = pcbnew.PCB_IO_MGR.Load(pcbnew.PCB_IO_MGR.EASYEDAPRO, epro, None, props)

    fps = list(board.GetFootprints())
    refs = sorted(f.GetReference() for f in fps)
    pads = 0
    net_pads = collections.Counter()
    for f in fps:
        for p in f.Pads():
            pads += 1
            n = p.GetNetname()
            if n:
                net_pads[n] += 1
    tr = vi = ar = 0
    for t in board.GetTracks():
        cls = t.GetClass()
        if cls == "PCB_VIA":
            vi += 1
        elif cls == "PCB_ARC":
            ar += 1
        else:
            tr += 1
    result = {
        "ok": True,
        "footprints": len(fps), "refs": refs, "pads": pads,
        "net_count": board.GetNetCount(),
        "nets_with_pads": len(net_pads),
        "net_pad_counts": dict(net_pads),
        "tracks": tr, "arcs": ar, "vias": vi,
        "zones": board.Zones().size() if hasattr(board.Zones(), "size") else len(list(board.Zones())),
    }
    if out:
        pcbnew.PCB_IO_MGR.Save(pcbnew.PCB_IO_MGR.KICAD_SEXP, out, board)
        result["saved"] = out
except BaseException as exc:
    result = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
sys.stdout.write("<<<RESULT>>>" + json.dumps(result))
'''

REPAIR = r'''
import sys, json, collections
result = {"ok": False}
try:
    import pcbnew
    board_path, netlist_path = sys.argv[1], sys.argv[2]
    want = json.load(open(netlist_path))["by_designator"]
    board = pcbnew.LoadBoard(board_path)

    nets = {}
    def net_item(name):
        if name not in nets:
            n = board.FindNet(name)
            if n is None:
                n = pcbnew.NETINFO_ITEM(board, name)
                board.Add(n)
            nets[name] = n
        return nets[name]

    fixed, missing_fp, still = [], [], []
    for f in board.GetFootprints():
        ref = f.GetReference()
        pins = want.get(ref)
        if not pins:
            continue
        for pad in f.Pads():
            num = pad.GetNumber()
            target = pins.get(num)
            if not target:
                continue
            if pad.GetNetname() != target:
                pad.SetNet(net_item(target))
                fixed.append([ref, num, target])
    for ref in want:
        if board.FindFootprintByReference(ref) is None:
            missing_fp.append(ref)
    counts = collections.Counter()
    for f in board.GetFootprints():
        for pad in f.Pads():
            n = pad.GetNetname()
            if n:
                counts[n] += 1
    pcbnew.PCB_IO_MGR.Save(pcbnew.PCB_IO_MGR.KICAD_SEXP, board_path, board)
    result = {"ok": True, "pads_renetted": len(fixed), "detail": fixed[:80],
              "footprints_not_found": missing_fp, "net_pad_counts": dict(counts)}
except BaseException as exc:
    result = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
sys.stdout.write("<<<RESULT>>>" + json.dumps(result))
'''

KICAD_PRO = {
    "board": {"design_settings": {}},
    "boards": [],
    "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
    "meta": {"filename": BOARD_NAME + ".kicad_pro", "version": 3},
    "net_settings": {"classes": [{"name": "Default", "clearance": 0.2,
                                  "track_width": 0.2, "via_diameter": 0.6,
                                  "via_drill": 0.3}]},
    "pcbnew": {"page_layout_descr_file": ""},
    "sheets": [], "text_variables": {},
}

STAGES = [
    ("raw", dict(newlines=False, do_flatten=False, do_inject=False)),
    ("newlines", dict(newlines=True, do_flatten=False, do_inject=False)),
    ("newlines+rules", dict(newlines=True, do_flatten=True, do_inject=False)),
    ("newlines+rules+nets", dict(newlines=True, do_flatten=True, do_inject=True)),
]


def run_child(kpy, *argv, **kw):
    snippet = kw.pop("snippet", CHILD)
    timeout = kw.pop("timeout", 900)
    proc = subprocess.run([kpy, "-c", snippet] + [a or "" for a in argv],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout)
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    marker = "<<<RESULT>>>"
    if marker in out:
        res = json.loads(out.split(marker, 1)[1])
    else:
        res = {"ok": False,
               "error": "child produced no result (rc=%d); the importer most "
                        "likely aborted" % proc.returncode}
    res["returncode"] = proc.returncode
    res["stderr"] = err[-4000:]
    res["stdout"] = out.split(marker)[0][-2000:]
    return res


def score(res, inv):
    """Higher is better. Net count is weighted hardest: that is the #19021 tell."""
    if not res.get("ok"):
        return -1, []
    want_fp = inv["footprints"]["count"]
    want_pads = inv["pads"]["total"]
    want_nets = inv["nets"]["with_pads_count"]
    want_tracks = inv["tracks"]["total"] + inv["arcs"]["total"]
    got_tracks = res["tracks"] + res["arcs"]
    detail, s = [], 0
    for name, want, got, weight in (
            ("nets", want_nets, res["nets_with_pads"], 5),
            ("footprints", want_fp, res["footprints"], 3),
            ("pads", want_pads, res["pads"], 2),
            ("tracks+arcs", want_tracks, got_tracks, 1)):
        hit = (want == got)
        near = want and abs(want - got) <= max(1, want * 0.02)
        s += weight if hit else (weight - 1 if near else 0)
        detail.append({"metric": name, "expected": want, "actual": got,
                       "exact": hit, "within_2pct": bool(near)})
    return s, detail


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--epro")
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--kpy", default=os.environ.get("KPY", KPY_DEFAULT))
    ap.add_argument("--kc", default=os.environ.get("KC", KC_DEFAULT))
    ap.add_argument("--skip-drc", action="store_true")
    args = ap.parse_args()
    root = args.root

    src = args.epro or E.find_staged_epro(root)
    if not src:
        print("no .epro staged in import/")
        return 2

    inv_path = os.path.join(root, "gates", "inventory_easyeda.json")
    if not os.path.exists(inv_path):
        print("run 10_epro_inventory.py first (%s missing)" % inv_path)
        return 2
    inv = E.load_json(inv_path)
    pcb_id = inv.get("source", {}).get("pcb_id") or ""

    work = os.path.join(root, "logs", "patch_variants")
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)

    attempts = []
    for i, (label, kw) in enumerate(STAGES):
        if label == "raw":
            variant = src
            rep = {"stages": {"raw": True}}
        else:
            variant = os.path.join(work, "v%d_%s.epro" % (i, label.replace("+", "_")))
            rep = E.patch_epro(src, variant, **kw)
        out = os.path.join(work, "v%d.kicad_pcb" % i)
        try:
            res = run_child(args.kpy, variant, out, pcb_id)
        except subprocess.TimeoutExpired:
            res = {"ok": False, "error": "timeout"}
        sc, detail = score(res, inv)
        attempts.append({"stage": label, "index": i, "variant": variant,
                         "patch_report": rep, "score": sc, "detail": detail,
                         "result": {k: v for k, v in res.items()
                                    if k not in ("refs", "net_pad_counts")},
                         "ok": bool(res.get("ok"))})
        print("  [%s] ok=%s score=%s %s" % (
            label, res.get("ok"), sc,
            "" if res.get("ok") else (res.get("error") or "")[:120]))
        if res.get("ok"):
            attempts[-1]["refs"] = res.get("refs")
            attempts[-1]["net_pad_counts"] = res.get("net_pad_counts")

    E.dump_json(os.path.join(root, "logs", "import_attempts.json"),
                {"source": src, "pcb_id": pcb_id, "attempts": attempts})

    good = [a for a in attempts if a["ok"]]
    if not good:
        msg = "\n\n".join("== stage %s ==\n%s\n%s" % (
            a["stage"], a["result"].get("error", ""), a["result"].get("stderr", ""))
            for a in attempts)
        with open(os.path.join(root, "logs", "import_error.txt"), "w") as f:
            f.write("every patch stage failed to load\n\n" + msg + "\n")
        print("IMPORT FAILED -- see logs/import_error.txt")
        return 1

    best = max(good, key=lambda a: (a["score"], -a["index"]))
    patched = os.path.join(root, "import", "patched.epro")
    if os.path.abspath(best["variant"]) != os.path.abspath(src):
        shutil.copy2(best["variant"], patched)
    else:
        shutil.copy2(src, patched)
    board_path = os.path.join(root, "board", BOARD_NAME + ".kicad_pcb")
    shutil.copy2(os.path.join(work, "v%d.kicad_pcb" % best["index"]), board_path)

    pro_path = os.path.join(root, "board", BOARD_NAME + ".kicad_pro")
    if not os.path.exists(pro_path):
        E.dump_json(pro_path, KICAD_PRO)

    print("chosen stage: %s (score %d) -> %s" % (best["stage"], best["score"], board_path))

    # KiCad applies each PAD_NET row with FindPadByNumber(), which returns only
    # the FIRST pad carrying that number. Footprints that repeat a number -- the
    # ESP32 thermal pad (39 x9) and the USB-C shell legs (13/14 x2) -- therefore
    # come in with all but one of those pads unconnected. Re-apply the EasyEDA
    # table to every pad that shares the number.
    repair = {"skipped": True}
    netlist = os.path.join(root, "contract", "netlist_from_epro_pcb.json")
    if os.path.exists(netlist):
        try:
            repair = run_child(args.kpy, board_path, netlist, snippet=REPAIR)
        except subprocess.TimeoutExpired:
            repair = {"ok": False, "error": "timeout"}
        if repair.get("ok"):
            print("pad-net repair: %d pads re-netted%s"
                  % (repair["pads_renetted"],
                     ("; footprints not found: %s" % repair["footprints_not_found"])
                     if repair.get("footprints_not_found") else ""))
        else:
            print("pad-net repair FAILED: %s" % repair.get("error"))
    E.dump_json(os.path.join(root, "logs", "pad_net_repair.json"), repair)

    drc = {"skipped": True}
    if not args.skip_drc:
        drc_out = os.path.join(root, "logs", "drc_import.json")
        cmd = [args.kc, "pcb", "drc", "--refill-zones", "--save-board",
               "--format", "json", "--output", drc_out, board_path]
        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=1800)
            with open(os.path.join(root, "logs", "drc_import.txt"), "wb") as f:
                f.write(p.stdout)
            if os.path.exists(drc_out):
                d = E.load_json(drc_out)
                drc = {"skipped": False, "returncode": p.returncode,
                       "violations": len(d.get("violations", [])),
                       "unconnected": len(d.get("unconnected_items", [])),
                       "schematic_parity": len(d.get("schematic_parity", []))}
            else:
                out = p.stdout.decode("utf-8", "replace")
                drc = {"skipped": False, "returncode": p.returncode,
                       "error": "no json produced", "output": out[-500:]}
                if "SwiftNativeNSArray" in out:
                    drc["hint"] = ("`kicad-cli pcb drc` needs macOS services a "
                                   "command sandbox blocks, and dies with a Swift "
                                   "'Array index out of range' when denied. Other "
                                   "kicad-cli subcommands are unaffected. Re-run "
                                   "this step outside the sandbox.")
        except subprocess.TimeoutExpired:
            drc = {"skipped": False, "error": "drc timeout"}
        print("DRC (informational): %s" % json.dumps(drc))

    E.dump_json(os.path.join(root, "logs", "import_summary.json"),
                {"source": src, "patched": patched, "board": board_path,
                 "chosen_stage": best["stage"], "score": best["score"],
                 "detail": best["detail"], "drc": drc,
                 "pad_net_repair": {k: v for k, v in repair.items()
                                    if k not in ("detail", "net_pad_counts")},
                 "stages_tried": [a["stage"] for a in attempts],
                 "stages_ok": [a["stage"] for a in good]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
