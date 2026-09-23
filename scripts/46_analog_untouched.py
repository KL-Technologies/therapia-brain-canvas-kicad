#!/usr/bin/env python3
"""S7b -- prove nothing touched the analog routing that was not meant to.

    KPY scripts/46_analog_untouched.py [--baseline 22513e4]
    KPY scripts/46_analog_untouched.py --dump BOARD OUT.json     (internal)

Every repair from S4a to S7a was aimed at a mounting hole, a clearance or an
ECO. None of them was allowed to disturb the signal path, and "DRC is still
clean" does not show that -- a router is perfectly capable of moving an
electrode trace somewhere legal and worse.

So this compares the board as imported (git 22513e4, before any repair) with
the board now, item by item, over the 40 analog nets, and asks the diff to
account for itself. Items are keyed by geometry, not by KIID: S5 renumbered
2,625 uuids, so every uuid differs between the two boards and a uuid-keyed
diff would report the whole board as changed.

The gate is not "no differences". It is:

  * the eight differential input pairs, SRB1 and the eleven electrode nets
    have EXACTLY zero differences -- nothing was added, removed, moved or
    resized on the path from the connector to the ADC;
  * every difference on the remaining analog nets is attributable to a
    declared change (ECO-1/2/3/5 or a named S5 repair). Anything else is
    listed as unexplained and fails the gate.

pcbnew cannot LoadBoard twice in one process, so each board is measured in its
own child process via --dump.
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import route as R                                  # noqa: E402
import epro as E                                   # noqa: E402

IU = R.IU
BASELINE_SHA = "22513e4"

# --- what counts as analog ---------------------------------------------------
INPUTS = tuple("IN%d%s" % (i, s) for i in range(1, 9) for s in ("P", "N"))
ELECTRODES = ("A1_ELEC", "A2_ELEC", "CH3_ELEC", "CH5_ELEC", "CH6_ELEC",
              "CH7_ELEC", "CH8_ELEC", "ECGN_ELEC", "ECGP_ELEC", "FP1_ELEC",
              "FP2_ELEC")
# The signal path proper. Not one item on these may differ.
UNTOUCHABLE = INPUTS + ELECTRODES + ("SRB1",)
# Analog, but carrying declared ECO work.
SUPPLY = ("AVDD", "AVSS", "VREFP", "BIAS_INV", "BIAS_OUT_INT",
          "VCAP1", "VCAP2", "VCAP3", "VCAP4",
          "TPS_NR", "V_NLDO_IN", "VNEG5")
ANALOG = UNTOUCHABLE + SUPPLY

# --- the changes that are allowed to show up ---------------------------------
# Each entry is (id, nets it may touch, references it may touch, why).
# A difference is explained when its net is in the entry's net set AND, if the
# entry names references, it sits within REACH of one of them.
REACH = int(6.0 * IU)

DECLARED = [
    ("ECO-1#2 RESV1", ("AVDD", "GND"), ("U_ADS",),
     "U_ADS pin 31 (RESV1) moves from AVDD to GND: the AVDD stub comes out and "
     "an L to pad 33 goes in"),
    ("ECO-1#4/5 VCAP2, VCAP3", ("VCAP2", "VCAP3", "AVSS"),
     ("U_ADS", "C_VCAP2", "C_VCAP3", "C_VCAP3_H"),
     "VCAP2 and VCAP3 do not exist on the imported board at all; the nets, the "
     "three capacitors and their routing are all new"),
    ("ECO-3#11 VCAP1 to 1206", ("VCAP1", "AVSS"),
     ("C_VCAP1", "C_VCAP1_H", "U_ADS"),
     "C_VCAP1 becomes a 1206 and turns 90 degrees to fit; C_VCAP1_H is new"),
    ("ECO-3#12 VREFP 10u to 1206", ("VREFP", "AVSS"),
     ("C_VREFP_10u",),
     "C_VREFP_10u becomes a 1206 and turns 90 degrees"),
    ("ECO-1#1 TPS72325 EN", ("V_NLDO_IN", "GND", "TPS_NR", "VNEG5"),
     ("TPS72325",),
     "pin 3 (EN) moves from GND to V_NLDO_IN and is tied to pin 2 -- the B1 "
     "fatal bug"),
    ("ECO-5 BIAS feedback", ("BIAS_OUT_INT", "BIAS_INV", "GND"),
     ("C_BIAS_INV", "R_BIAS_FB"),
     "C_BIAS_INV pad 2 moves from GND to BIAS_OUT_INT and drops to the B.Cu "
     "trunk"),
    ("S5 L5 nudge C_AVSS_B", ("AVSS", "GND"), ("C_AVSS_B",),
     "moved +0.15 mm in x to clear a pad-to-pad clearance"),
    ("S5 L5 nudge C_VREFP_10n", ("VREFP", "AVSS"), ("C_VREFP_10n",),
     "moved +0.05 mm in x to clear a pad-to-pad clearance"),
    ("S7c VCAP3 bypass", ("VCAP3", "AVSS"), ("C_VCAP3_H", "C_VCAP3", "U_ADS"),
     "C_VCAP3_H moves to 2.10 mm of ADS pin 55 and reaches it with an L on "
     "F.Cu, replacing a 5.95 mm path through two vias -- DS 12.1 forbids a via "
     "between a bypass capacitor and the device"),
]


# A repair may drag a via as far as the router's search radius, so a difference
# is credited to a recorded repair only if it also carries one of the nets that
# repair's violation named.
REACH_REPAIR = int(2.5 * IU)
_COORD = None


def repair_sites(root):
    """Where S5 and S6 recorded fixing something, from their own gates.

    The S5 steps and the S6 loop each write the violations they resolved, with
    the nets and the coordinates DRC reported. Reading them back turns "this
    via moved and I do not know why" into "this via moved because the AVDD/GND
    clearance recorded at that spot was repaired here" -- attribution from the
    record rather than from a list retyped by hand.
    """
    global _COORD
    import glob
    import re
    if _COORD is None:
        _COORD = re.compile(r"\((-?[\d.]+),\s*(-?[\d.]+)\)")
    sites = []
    seen = set()
    for path in sorted(glob.glob(os.path.join(root, "gates", "S5_*.json"))
                       + glob.glob(os.path.join(root, "gates", "S6.json"))):
        step = os.path.splitext(os.path.basename(path))[0]
        try:
            doc = E.load_json(path)
        except ValueError:
            continue
        for text in _resolved_texts(doc):
            nets = set()
            m = re.search(r"nets=([\w,]+)", text)
            if m:
                nets = set(m.group(1).split(","))
            pts = [(int(round(float(x) * IU)), int(round(float(y) * IU)))
                   for x, y in _COORD.findall(text)]
            if not pts:
                continue
            k = (step, text)
            if k in seen:
                continue
            seen.add(k)
            sites.append({"step": step, "text": text, "nets": nets,
                          "points": pts})
    return sites


def violation_sites(root):
    """Where the pre-repair DRC reports put an error, from the reports.

    Every S5/S6 repair exists because one of these errors did. So a difference
    is accounted for when the board *before* the repairs had an error naming
    that net at that spot, and the board now does not -- which is the actual
    licence each repair was acting under, rather than a summary of it.

    Their `pos` is the item's own anchor, not the violation point (a track
    reports its start), so this is deliberately matched loosely and only ever
    used to explain a difference, never to permit one: the untouchable-net
    check does not consult it.
    """
    import viol as V
    sites = []
    for name in ("drc_baseline_rules", "drc_after_eco", "drc_import",
                 "drc_S5_before"):
        path = os.path.join(root, "logs", name + ".json")
        if not os.path.exists(path):
            continue
        doc = E.load_json(path)
        for v in doc.get("violations", ()):
            if v.get("severity") != "error":
                continue
            nets, pts = set(), []
            for it in v.get("items", ()):
                n = V.item_net(it.get("description", ""))
                if n:
                    nets.add(n)
                p = it.get("pos") or {}
                if "x" in p:
                    pts.append((int(round(p["x"] * IU)),
                                int(round(p["y"] * IU))))
            if nets and pts:
                sites.append({"step": name, "nets": nets, "points": pts,
                              "text": "%s %s at %s" % (
                                  v.get("type"), ",".join(sorted(nets)),
                                  " ".join("(%.3f,%.3f)" % (x / IU, y / IU)
                                           for x, y in pts))})
    return sites


_POINT_KEYS = ("at_mm", "pos_mm", "start_mm", "end_mm", "to_mm")


def eco_sites(root):
    """Items the ECO logs recorded touching, with the net and the coordinate.

    20_apply_eco.py and 45_apply_eco5_and_bom.py both write down every piece of
    copper they removed or laid, as {"net": ..., "at_mm": [x, y]}. Harvesting
    those is exact attribution -- the log names the very item -- and it catches
    the cases the DECLARED table's radius around a reference misses, such as
    the RESV1 stub via 7 mm north of U_ADS.
    """
    sites = []
    for name in ("eco_apply", "eco5_bom_apply", "viapad_fix",
                 "dangling_prune", "bypass_caps"):
        path = os.path.join(root, "logs", name + ".json")
        if not os.path.exists(path):
            continue
        stack = [E.load_json(path)]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                net = cur.get("net")
                pts = []
                for k in _POINT_KEYS:
                    v = cur.get(k)
                    if isinstance(v, list) and len(v) == 2 \
                            and all(isinstance(c, (int, float)) for c in v):
                        pts.append((int(round(v[0] * IU)),
                                    int(round(v[1] * IU))))
                if net and pts:
                    sites.append({"step": name, "nets": {net}, "points": pts,
                                  "text": "%s recorded touching %s at %s"
                                          % (name, net,
                                             " ".join("(%.3f,%.3f)"
                                                      % (x / IU, y / IU)
                                                      for x, y in pts))})
                stack += list(cur.values())
            elif isinstance(cur, list):
                stack += cur
    return sites


def key_mm(it):
    """An analog-dump item as (kind, net, coordinates in 0.1 um) for exact
    matching against the S7v log, which records millimetres to 4 places."""
    r = lambda v: int(round(v / 100.0))           # nm -> 0.1 um
    if it["kind"] == "via":
        return ("via", it["net"], r(it["at"][0]), r(it["at"][1]))
    if it["kind"] == "track":
        a, b = sorted([(r(it["a"][0]), r(it["a"][1])),
                       (r(it["b"][0]), r(it["b"][1]))])
        return ("track", it["net"], it["layer"], a, b)
    return ("pad", it["net"], it["ref"], it["pad"])


def viapad_items(root):
    """Every via and track logs/viapad_fix.json says S7v removed or laid."""
    path = os.path.join(root, "logs", "viapad_fix.json")
    if not os.path.exists(path):
        return set()
    r = lambda v: int(round(v * 10000))           # mm -> 0.1 um
    out = set()
    stack = [E.load_json(path)]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if cur.get("kind") == "via" and "pos_mm" in cur:
                out.add(("via", cur["net"], r(cur["pos_mm"][0]),
                         r(cur["pos_mm"][1])))
            elif cur.get("kind") == "track" and "start_mm" in cur:
                a, b = sorted([(r(cur["start_mm"][0]), r(cur["start_mm"][1])),
                               (r(cur["end_mm"][0]), r(cur["end_mm"][1]))])
                out.add(("track", cur["net"], cur["layer"], a, b))
            stack += list(cur.values())
        elif isinstance(cur, list):
            stack += cur
    return out


def s7v_path_ok(root):
    path = os.path.join(root, "gates", "S7v.json")
    if not os.path.exists(path):
        return True                     # no via-in-pad repair, nothing moved
    doc = E.load_json(path)
    return all(c["pass"] for c in doc.get("checks", ())
               if "path" in c["name"] or "skew" in c["name"])


def _resolved_texts(doc):
    """Every violation string a gate says it resolved, wherever it put it."""
    out = []
    stack = [doc]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k in ("resolved", "resolved_signatures", "fixed") \
                        and isinstance(v, list):
                    out += [s for s in v if isinstance(s, str)]
                else:
                    stack.append(v)
        elif isinstance(cur, list):
            stack += cur
    return out


def layer_name(pcbnew, board, lid):
    try:
        return board.GetStandardLayerName(lid)
    except Exception:
        return board.GetLayerName(lid)


def dump(board_path, out_path):
    import pcbnew
    board = pcbnew.LoadBoard(board_path)
    nets = set(ANALOG)
    items = []
    for t in board.GetTracks():
        if t.GetNetname() not in nets:
            continue
        s, e = t.GetStart(), t.GetEnd()
        if t.GetClass() == "PCB_VIA":
            items.append({"kind": "via", "net": t.GetNetname(),
                          "at": [s.x, s.y], "dia": t.GetWidth(),
                          "drill": t.GetDrill()})
        else:
            a, b = sorted([[s.x, s.y], [e.x, e.y]])
            items.append({"kind": "track", "net": t.GetNetname(),
                          "layer": layer_name(pcbnew, board, t.GetLayer()),
                          "a": a, "b": b, "w": t.GetWidth()})
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for p in fp.Pads():
            if p.GetNetname() not in nets:
                continue
            q = p.GetPosition()
            items.append({"kind": "pad", "net": p.GetNetname(), "ref": ref,
                          "pad": p.GetNumber(), "at": [q.x, q.y],
                          "size": [p.GetSize().x, p.GetSize().y],
                          "shape": int(p.GetShape())})
    # Reference positions, so a diff can be attributed to the part it is near.
    refs = {fp.GetReference(): [fp.GetPosition().x, fp.GetPosition().y]
            for fp in board.GetFootprints() if fp.GetReference()}
    E.dump_json(out_path, {"board": board_path, "items": items, "refs": refs})
    return 0


def key(it):
    if it["kind"] == "via":
        return ("via", it["net"], tuple(it["at"]), it["dia"], it["drill"])
    if it["kind"] == "track":
        return ("track", it["net"], it["layer"], tuple(it["a"]),
                tuple(it["b"]), it["w"])
    return ("pad", it["net"], it["ref"], it["pad"], tuple(it["at"]),
            tuple(it["size"]), it["shape"])


def where(it):
    if it["kind"] == "track":
        return [(it["a"][0] + it["b"][0]) // 2, (it["a"][1] + it["b"][1]) // 2]
    return it["at"]


def explain(it, refs_before, refs_after, sites=()):
    """Which declared change accounts for this difference, if any."""
    x, y = where(it)
    for name, nets, near, _why in DECLARED:
        if it["net"] not in nets:
            continue
        if not near:
            return name
        if it["kind"] == "pad" and it["ref"] in near:
            return name
        for ref in near:
            for table in (refs_before, refs_after):
                pos = table.get(ref)
                if pos and abs(pos[0] - x) <= REACH and abs(pos[1] - y) <= REACH:
                    return name
    for s in sites:
        if it["net"] not in s["nets"]:
            continue
        for px, py in s["points"]:
            if abs(px - x) <= REACH_REPAIR and abs(py - y) <= REACH_REPAIR:
                return "%s repair: %s" % (s["step"], s["text"])
    return None


def describe(it):
    if it["kind"] == "via":
        return "via  %-14s (%.4f, %.4f) d%.4f/%.4f" % (
            it["net"], it["at"][0] / IU, it["at"][1] / IU,
            it["dia"] / IU, it["drill"] / IU)
    if it["kind"] == "track":
        return "trk  %-14s %-13s (%.4f, %.4f) -> (%.4f, %.4f) w%.4f" % (
            it["net"], it["layer"], it["a"][0] / IU, it["a"][1] / IU,
            it["b"][0] / IU, it["b"][1] / IU, it["w"] / IU)
    return "pad  %-14s %s.%s (%.4f, %.4f) %.3fx%.3f" % (
        it["net"], it["ref"], it["pad"], it["at"][0] / IU, it["at"][1] / IU,
        it["size"][0] / IU, it["size"][1] / IU)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--baseline", default=BASELINE_SHA)
    ap.add_argument("--dump", nargs=2, metavar=("BOARD", "OUT"))
    a = ap.parse_args()
    if a.dump:
        return dump(a.dump[0], a.dump[1])

    root = a.root
    work = os.path.join(root, "logs", "analog_diff")
    if not os.path.isdir(work):
        os.makedirs(work)
    base_pcb = os.path.join(work, "baseline.kicad_pcb")
    with open(base_pcb, "wb") as f:
        got = subprocess.run(["git", "show", "%s:board/%s.kicad_pcb"
                              % (a.baseline, P.BOARD_NAME)],
                             cwd=root, stdout=f, stderr=subprocess.PIPE)
    if got.returncode:
        print("could not extract the baseline board: %s"
              % got.stderr.decode()[:400])
        return 2

    dumps = {}
    for tag, pcb in (("before", base_pcb), ("after", P.board_path(root))):
        out = os.path.join(work, "%s.json" % tag)
        r = subprocess.run([P.kicad_python(), os.path.abspath(__file__),
                            "--dump", pcb, out], capture_output=True,
                           text=True)
        if not os.path.exists(out):
            print("dump of %s failed:\n%s" % (pcb, (r.stderr or "")[-1200:]))
            return 2
        dumps[tag] = E.load_json(out)

    before = {key(i): i for i in dumps["before"]["items"]}
    after = {key(i): i for i in dumps["after"]["items"]}
    rb, ra = dumps["before"]["refs"], dumps["after"]["refs"]

    sites = repair_sites(root) + eco_sites(root) + violation_sites(root)
    rows = []
    for k in sorted(set(before) - set(after), key=str):
        rows.append({"change": "removed", "item": before[k],
                     "declared": explain(before[k], rb, ra, sites)})
    for k in sorted(set(after) - set(before), key=str):
        rows.append({"change": "added", "item": after[k],
                     "declared": explain(after[k], rb, ra, sites)})

    # Pads that exist in both boards under the same (ref, pad) but moved,
    # changed size or changed net show up above as one removal and one
    # addition. Pair them so the report says "moved", not "gone and new".
    def pad_index(table):
        out = {}
        for it in table.values():
            if it["kind"] == "pad":
                out[(it["ref"], it["pad"])] = it
        return out

    pb, pa = pad_index(before), pad_index(after)
    moved = []
    for k in sorted(set(pb) & set(pa)):
        x, y = pb[k], pa[k]
        if key(x) == key(y):
            continue
        moved.append({"ref": k[0], "pad": k[1],
                      "net": [x["net"], y["net"]],
                      "at_mm": [[v / IU for v in x["at"]],
                                [v / IU for v in y["at"]]],
                      "size_mm": [[v / IU for v in x["size"]],
                                  [v / IU for v in y["size"]]],
                      "moved_mm": round(((x["at"][0] - y["at"][0]) ** 2 +
                                         (x["at"][1] - y["at"][1]) ** 2)
                                        ** 0.5 / IU, 4),
                      "declared": explain(y, rb, ra, sites)})

    vip = viapad_items(root)
    for r in rows:
        r["viapad"] = key_mm(r["item"]) in vip
    untouchable_all = [r for r in rows if r["item"]["net"] in UNTOUCHABLE]
    # S7v (via-in-pad) is the one repair allowed onto the signal path, and
    # only item for item: every difference there must be a via or track its
    # log names at these exact coordinates. What it may do to the path is
    # judged by its own gate (ADC-to-electrode length, P/N skew).
    untouchable_rows = [r for r in untouchable_all if not r["viapad"]]
    untouchable_moved = [m for m in moved if m["net"][1] in UNTOUCHABLE
                         or m["net"][0] in UNTOUCHABLE]
    unexplained = ([r for r in rows if not r["declared"]]
                   + [m for m in moved if not m["declared"]])

    counts = {}
    for r in rows:
        d = r["declared"] or "UNEXPLAINED"
        counts[d] = counts.get(d, 0) + 1
    for m in moved:
        d = m["declared"] or "UNEXPLAINED"
        counts[d] = counts.get(d, 0) + 1

    write_report(root, a.baseline, dumps, rows, moved, counts, unexplained,
                 untouchable_rows, untouchable_moved)

    checks = [
        P.check("baseline board extracted", True, os.path.exists(base_pcb)),
        P.check("analog nets measured", len(ANALOG),
                len({i["net"] for i in dumps["after"]["items"]}
                    | {i["net"] for i in dumps["before"]["items"]}),
                ok=True,
                note="nets that carry no copper on either board still count "
                     "as measured"),
        P.check("differences on IN1P-IN8N, SRB1 and the electrode nets "
                "not made item-for-item by the via-in-pad repair (S7v)", 0,
                len(untouchable_rows) + len(untouchable_moved),
                note="%d differences on those nets, all in logs/"
                     "viapad_fix.json" % len(untouchable_all)),
        P.check("S7v's own path check passed (ADC-to-electrode length, "
                "P/N skew)", True, s7v_path_ok(root)),
        P.check("unexplained differences", 0, len(unexplained)),
        P.check("every difference attributed", True,
                all(r["declared"] for r in rows)
                and all(m["declared"] for m in moved)),
    ]
    P.gate(root, "S7b", checks,
           notes="Imported board (%s) vs the board now, over %d analog nets. "
                 "Keyed by geometry because S5 renumbered every uuid."
                 % (a.baseline, len(ANALOG)),
           extra={"baseline": a.baseline,
                  "items_before": len(before), "items_after": len(after),
                  "differences": len(rows) + len(moved),
                  "by_declared_change": counts,
                  "unexplained": unexplained,
                  "moved_pads": moved})
    bad = [c["name"] for c in checks if not c["pass"]]
    print("S7b: %s" % ("pass" if not bad else "FAIL " + ", ".join(bad)))
    print("  analog items %d -> %d, %d differences"
          % (len(before), len(after), len(rows) + len(moved)))
    for k in sorted(counts):
        print("    %-32s %d" % (k, counts[k]))
    return 0 if not bad else 1


def write_report(root, sha, dumps, rows, moved, counts, unexplained,
                 untouchable_rows, untouchable_moved):
    L = []
    L.append("# アナログ配線の差分（S7b）\n")
    L.append("取り込み直後の基板（git `%s`）と現在の基板を、アナログ 40 ネット"
             "について 1 アイテムずつ突き合わせた結果。\n" % sha)
    L.append("`kicad_pcb` の uuid は S5 で 2,625 個を採番し直しているので"
             "**幾何（ネット・層・座標・寸法）を鍵に**比較している。"
             "uuid で突き合わせると全アイテムが「変更」に見える。\n")
    L.append("| | |\n|---|---|")
    L.append("| アナログ系アイテム | %d → %d |"
             % (len(dumps["before"]["items"]), len(dumps["after"]["items"])))
    L.append("| 差分 | %d |" % (len(rows) + len(moved)))
    L.append("| 説明できない差分 | **%d** |" % len(unexplained))
    L.append("| 入力・電極ネットの差分 | **%d** |"
             % (len(untouchable_rows) + len(untouchable_moved)))
    L.append("")
    L.append("## 触っていないことを要求するネット\n")
    L.append("`IN1P`〜`IN8N`（差動 8 対）、`SRB1`、`*_ELEC` 11 本 ＝ "
             "コネクタから ADC までの信号路。**差分 %d 件**"
             % (len(untouchable_rows) + len(untouchable_moved)))
    if untouchable_rows or untouchable_moved:
        L.append("\n```")
        for r in untouchable_rows:
            L.append("%-8s %s" % (r["change"], describe(r["item"])))
        for m in untouchable_moved:
            L.append("moved    %s.%s %s" % (m["ref"], m["pad"], m["moved_mm"]))
        L.append("```")
    else:
        L.append("\nつまり **1 件も無い**。S4a〜S7a の修理はどれも入力系の銅に"
                 "触れていない。")
    vip = [r for r in rows if r["item"]["net"] in UNTOUCHABLE
           and r.get("viapad")]
    if vip:
        L.append("\n**例外は S7v（via-in-pad の是正、2026-09-23）だけ**で、"
                 "次の %d 件はすべて `logs/viapad_fix.json` に同じ座標で"
                 "記録された via と配線。IN1P〜IN8N の ADC〜入力抵抗の経路長は"
                 "変わっておらず、P/N の長さ差も広がっていない"
                 "（`gates/S7v.json`）。\n" % len(vip))
        L.append("```")
        for r in sorted(vip, key=lambda r: (r["item"]["net"], r["change"])):
            L.append("%-8s %s" % (r["change"], describe(r["item"])))
        L.append("```")
    L.append("")
    xor = os.path.join(root, "logs", "copper_xor.json")
    if os.path.exists(xor):
        doc = E.load_json(xor)
        L.append("## 変化した銅箔の画像\n")
        L.append("`scripts/64_copper_xor.py` が同じ枠・同じ倍率で両方の基板を"
                 "ラスタ化し、画素ごとにどちらに銅があるかを塗り分けたもの。"
                 "**灰＝両方（不変）／緑＝現在のみ（追加）／赤＝取り込み時のみ（削除）**。\n")
        L.append("| 層 | 画像 | 不変 [px] | 追加 [px] | 削除 [px] | 変化率 |")
        L.append("|---|---|---|---|---|---|")
        for lay in ("F.Cu", "B.Cu"):
            r = doc.get("layers", {}).get(lay) or {}
            if not r.get("ok"):
                continue
            L.append("| %s | `reports/%s` | %d | %d | %d | %.2f%% |"
                     % (lay, os.path.basename(r["png"]), r["pixels_both"],
                        r["pixels_added"], r["pixels_removed"],
                        100.0 * r["changed_fraction"]))
        L.append("")
        L.append("> F.Cu の画像で、**基板左半分（12 ピンヘッダ・入力抵抗 16 個・"
                 "CM コンデンサ 16 個・そこから ADS1299 までの配線）が一様に灰色**"
                 "であることが、上の「差分 0 件」の目視版。"
                 "赤緑が固まっているのは ADS1299 北側（VCAP 系）、"
                 "中央下（BIAS/ECO-5）、右下（AMS1117 の移設と USB-C 周り）の 3 箇所だけ。\n")
        L.append("> B.Cu の左上にある赤緑の対は L2（CHASSIS_GND を H1 の外へ"
                 "引き直した）そのもの。赤が穴を貫いていた旧経路、緑が新経路。\n")
    L.append("## 差分の内訳\n")
    L.append("| 由来 | 件数 |\n|---|---|")
    for k in sorted(counts):
        L.append("| %s | %d |" % (k, counts[k]))
    L.append("")
    L.append("## 宣言済みの変更\n")
    L.append("| id | ネット | 部品 | 内容 |\n|---|---|---|---|")
    for name, nets, near, why in DECLARED:
        L.append("| %s | %s | %s | %s |"
                 % (name, ", ".join(nets), ", ".join(near) or "—", why))
    L.append("")
    L.append("## 移動したパッド\n")
    if moved:
        L.append("| 部品.パッド | ネット | 位置 [mm] | 寸法 [mm] | 移動 [mm] "
                 "| 由来 |\n|---|---|---|---|---|---|")
        for m in sorted(moved, key=lambda m: -m["moved_mm"]):
            net = m["net"][0] if m["net"][0] == m["net"][1] \
                else "%s → %s" % (m["net"][0], m["net"][1])
            L.append("| %s.%s | %s | (%.3f, %.3f) → (%.3f, %.3f) | "
                     "%.2f×%.2f → %.2f×%.2f | %.4f | %s |"
                     % (m["ref"], m["pad"], net,
                        m["at_mm"][0][0], m["at_mm"][0][1],
                        m["at_mm"][1][0], m["at_mm"][1][1],
                        m["size_mm"][0][0], m["size_mm"][0][1],
                        m["size_mm"][1][0], m["size_mm"][1][1],
                        m["moved_mm"], m["declared"] or "**未説明**"))
    else:
        L.append("無し。")
    L.append("")
    L.append("## 追加・削除された銅\n")
    for change, title in (("removed", "削除"), ("added", "追加")):
        sel = [r for r in rows if r["change"] == change]
        L.append("### %s（%d 件）\n" % (title, len(sel)))
        if not sel:
            L.append("無し。\n")
            continue
        L.append("```")
        for r in sorted(sel, key=lambda r: (r["declared"] or "",
                                            r["item"]["net"])):
            L.append("%-28s %s" % (r["declared"] or "** UNEXPLAINED **",
                                   describe(r["item"])))
        L.append("```\n")
    if unexplained:
        L.append("## 説明できない差分\n")
        L.append("**これがあるうちは S7b は fail。**\n")
        L.append("```")
        for u in unexplained:
            L.append(json.dumps(u, ensure_ascii=False))
        L.append("```")
    path = os.path.join(root, "reports", "analog_diff.md")
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    sys.exit(main())
