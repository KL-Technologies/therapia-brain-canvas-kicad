#!/usr/bin/env python3
"""S7a -- apply ECO-5 to the copper and the BOM corrections to the fields.

    KPY scripts/45_apply_eco5_and_bom.py [--dry-run] [--no-drc]

Two changes, both idempotent, both driven by files rather than by constants
here:

ECO-5 (copper, one pad)
    C_BIAS_INV pad 2 moves from GND to BIAS_OUT_INT, putting the capacitor in
    parallel with R_BIAS_FB's 1 M instead of shunting the BIAS summing node to
    ground -- TI's SBAS499 BIAS drive circuit. contract/contract_overrides.json
    is where that decision lives; parity is checked against the contract with
    it applied, so the board is not "off contract" for having it.

    The old GND connection was a via sitting under the pad plus a 0.14 mm stub.
    Both come out. The new connection drops to B.Cu, where BIAS_OUT_INT already
    runs a 18.2 mm trunk at y = 87.7215 straight underneath the part, so the
    net is reached in one via and a short drop rather than by going the 5.2 mm
    around R_BIAS_FB on the front -- both of R_BIAS_FB's and C_BIAS_INV's own
    BIAS_INV pads sit on the straight line between the two pads.

Fields (no copper)
    Value / MPN / LCSC for all 135 fitted parts, read from data/parts_lcsc.csv,
    which 19_make_parts_table.py now regenerates with data/bom_fixes JSON
    applied. R_RST_UP and R_IO15_DN are additionally marked DNP: the footprint,
    the pads and the nets stay exactly as they are and only the BOM and the
    placement file skip them.

Runs DRC afterwards and re-measures the saved board in a child process --
pcbnew cannot LoadBoard twice in one process, and measurements taken after
SaveBoard read back as raw SWIG objects.
"""

import argparse
import csv
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
ECO5_REF = "C_BIAS_INV"
ECO5_PAD = "2"
ECO5_NET = "BIAS_OUT_INT"


def parts_table(root):
    with open(os.path.join(root, "data", "parts_lcsc.csv")) as f:
        return {r["designator"]: r for r in csv.DictReader(f)}


def find_fp(board, ref):
    for fp in board.GetFootprints():
        if fp.GetReference() == ref:
            return fp
    return None


def find_pad(fp, number):
    for p in fp.Pads():
        if p.GetNumber() == number:
            return p
    return None


def trunk_under(board, pcbnew, net_name, x, y):
    """The B.Cu track of `net_name` that passes under x, nearest in y.

    Looked up rather than written down so that the drop lands on copper that is
    actually there; a hard-coded y would survive the trunk being rerouted and
    quietly connect to nothing.
    """
    best = None
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA" or t.GetLayer() != pcbnew.B_Cu:
            continue
        if t.GetNetname() != net_name:
            continue
        s, e = t.GetStart(), t.GetEnd()
        if s.y != e.y:                             # horizontal runs only
            continue
        if not (min(s.x, e.x) <= x <= max(s.x, e.x)):
            continue
        d = abs(s.y - y)
        if best is None or d < best[0]:
            best = (d, t, s.y)
    return best


def via_ladder(pad, pcbnew):
    """Via sites west of the pad, land-clear first, pad centre last.

    A via under a 0402 land wicks solder in reflow. The GND via this replaces
    sat exactly there, so keeping the position would not make the board worse
    -- but the connection is being rebuilt anyway, and moving the drill out
    from under the land costs a 0.2 mm stub of same-net copper on the front.
    """
    c = pad.GetPosition()
    half = pad.GetSize().x / 2.0
    land_clear = c.x - half - P.VIA_DIA / 2.0
    drill_clear = c.x - half - P.VIA_DRILL / 2.0
    out = []
    for x, why in ((land_clear, "via land clear of the pad"),
                   (land_clear + 0.05 * IU, "via land clear of the pad"),
                   (drill_clear, "via drill clear of the pad land"),
                   (drill_clear + 0.05 * IU, "via drill clear of the pad land"),
                   (c.x - half, "via centred on the pad edge"),
                   (c.x, "via under the pad, as the GND via was")):
        out.append((int(round(x)), why))
    return out


def apply_eco5(pcbnew, board, idx, root, log):
    fp = find_fp(board, ECO5_REF)
    if fp is None:
        log["eco5"] = {"ok": False, "reason": "%s is not on the board"
                                              % ECO5_REF}
        return False
    pad = find_pad(fp, ECO5_PAD)
    net = R.get_or_create_net(pcbnew, board, ECO5_NET)
    rec = {"ref": ECO5_REF, "pad": ECO5_PAD,
           "pad_pos_mm": [P.mm(pad.GetPosition().x), P.mm(pad.GetPosition().y)],
           "net_before": pad.GetNetname(), "net_after": ECO5_NET}

    if pad.GetNetname() == ECO5_NET:
        rec.update({"ok": True, "action": "already applied"})
        log["eco5"] = rec
        return True

    island, shared = R.trace_island(pcbnew, board, pad)
    if shared:
        rec.update({"ok": False, "reason":
                    "the GND island under this pad is shared with %s -- "
                    "removing it would disconnect them"
                    % ", ".join("%s.%s" % (p.GetParent().GetReference(),
                                           p.GetNumber()) for p in shared)})
        log["eco5"] = rec
        return False
    rec["removed"] = [P.describe(board, i) for i in island]

    px, py = pad.GetPosition().x, pad.GetPosition().y
    hit = trunk_under(board, pcbnew, ECO5_NET, px, py)
    if hit is None:
        rec.update({"ok": False, "reason":
                    "no horizontal %s track on B.Cu passes under the pad"
                    % ECO5_NET})
        log["eco5"] = rec
        return False
    _d, trunk, trunk_y = hit
    rec["landing"] = {"track": P.describe(board, trunk),
                      "y_mm": P.mm(trunk_y)}

    # The old GND copper is about to go, so it must not count as an obstacle
    # while the replacement is being checked.
    ignore = [pad] + list(island)
    chosen = None
    tried = []
    for vx, why in via_ladder(pad, pcbnew):
        ok_via = R.via_site_ok(idx, pcbnew, vx, py, net.GetNetCode(),
                               P.VIA_DIA, P.VIA_DRILL, P.CLEARANCE,
                               P.HOLE_TO_HOLE, P.HOLE_CLEARANCE,
                               P.board_box(), ignore=ignore)
        ok_stub = True if vx == px else R.straight_ok(
            idx, pcbnew, board, (px, py), (vx, py), pcbnew.F_Cu, P.TRACK_W,
            net.GetNetCode(), P.CLEARANCE, P.HOLE_CLEARANCE, ignore=ignore)
        ok_drop = R.straight_ok(
            idx, pcbnew, board, (vx, py), (vx, trunk_y), pcbnew.B_Cu,
            P.TRACK_W, net.GetNetCode(), P.CLEARANCE, P.HOLE_CLEARANCE,
            ignore=ignore)
        on_trunk = (min(trunk.GetStart().x, trunk.GetEnd().x) <= vx
                    <= max(trunk.GetStart().x, trunk.GetEnd().x))
        tried.append({"x_mm": P.mm(vx), "why": why, "via_site": ok_via,
                      "front_stub": ok_stub, "back_drop": ok_drop,
                      "lands_on_trunk": on_trunk})
        if ok_via and ok_stub and ok_drop and on_trunk:
            chosen = (vx, why)
            break
    rec["via_sites_tried"] = tried
    if chosen is None:
        rec.update({"ok": False, "reason":
                    "no legal via site west of the pad reaches the trunk"})
        log["eco5"] = rec
        return False

    vx, why = chosen
    R.remove_items(board, island)
    pad.SetNet(net)
    made = []
    made.append(R.add_via(pcbnew, board, (vx, py), net.GetNetCode(),
                          P.VIA_DIA, P.VIA_DRILL))
    if vx != px:
        made.append(R.add_track(pcbnew, board, (px, py), (vx, py),
                                pcbnew.F_Cu, P.TRACK_W, net.GetNetCode()))
    made.append(R.add_track(pcbnew, board, (vx, py), (vx, trunk_y),
                            pcbnew.B_Cu, P.TRACK_W, net.GetNetCode()))
    idx.rebuild()
    rec.update({"ok": True, "action": "rerouted",
                "via_mm": [P.mm(vx), P.mm(py)], "via_choice": why,
                "front_stub_mm": P.mm(abs(px - vx)),
                "back_drop_mm": P.mm(abs(py - trunk_y)),
                "added": [P.describe(board, i) for i in made],
                "vias_removed": sum(1 for i in island
                                    if i.GetClass() == "PCB_VIA"),
                "vias_added": 1})
    log["eco5"] = rec
    return True


def apply_fields(pcbnew, board, table, log):
    """Value / MPN / LCSC on every fitted part, DNP where the table says so."""
    set_fields, dnp_set, missing = 0, [], []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref:
            continue
        row = table.get(ref)
        if row is None:
            if int(fp.GetAttributes()) & int(pcbnew.FP_EXCLUDE_FROM_BOM):
                continue                           # H1-H4, PEG1, PEG2
            missing.append(ref)
            continue
        fp.SetValue(row["value"])
        fields = [("MPN", row["mpn"]), ("LCSC", row["lcsc"])]
        want_dnp = bool(row.get("dnp"))
        fields.append(("DNP", "1" if want_dnp else ""))
        for key, val in fields:
            if not val and not fp.HasField(key):
                continue
            fp.SetField(key, val)
            f = fp.GetField(key)
            # SetField makes the field visible on F.SilkS; 135 part numbers
            # printed on the silkscreen is not what anyone wants.
            f.SetVisible(False)
            f.SetLayer(pcbnew.Cmts_User)
        fp.SetDNP(want_dnp)
        fp.SetExcludedFromBOM(want_dnp)
        fp.SetExcludedFromPosFiles(want_dnp)
        if want_dnp:
            dnp_set.append(ref)
        set_fields += 1
    log["fields"] = {"parts_with_fields": set_fields,
                     "dnp": sorted(dnp_set),
                     "no_table_entry": sorted(missing)}
    return not missing


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-drc", action="store_true")
    a = ap.parse_args()
    root = a.root

    import pcbnew
    board = pcbnew.LoadBoard(P.board_path(root))
    idx = R.CopperIndex(pcbnew, board)
    log = {"before": P.counts(board, pcbnew)}

    ok_eco = apply_eco5(pcbnew, board, idx, root, log)
    ok_fld = apply_fields(pcbnew, board, parts_table(root), log)

    # Everything that has to be read off the board is read now: after
    # SaveBoard the SWIG proxies go raw, and a second LoadBoard in this
    # process is not possible.
    diffs, mech = P.contract_diff(board, pcbnew, root)
    log["after"] = P.counts(board, pcbnew)
    log["contract_diffs"] = diffs
    log["mechanical_footprints"] = mech
    log["unconnected"] = P.unconnected_count(pcbnew, board)

    have, _ = P.pad_net_map(board, pcbnew)
    board_pins = {}
    for ref, pads in have.items():
        for num, nets in pads.items():
            for n in nets:
                if n:
                    board_pins[n] = board_pins.get(n, 0) + 1
    want_pins = P.contract_net_counts(root)
    log["net_pin_counts"] = {
        n: {"board": board_pins.get(n, 0), "contract": want_pins.get(n, 0)}
        for n in ("GND", ECO5_NET, "BIAS_INV")}

    if a.dry_run:
        print(json.dumps(log, indent=1))
        return 0

    pcbnew.SaveBoard(P.board_path(root), board)
    E.dump_json(os.path.join(root, "logs", "eco5_bom_apply.json"), log)

    drc = {}
    if not a.no_drc:
        import drc as D
        out = os.path.join(root, "logs", "drc_s7a.json")
        got, _proc, blob = P.run_drc(out, root)
        if not got:
            print("DRC did not produce a report -- run outside the sandbox")
            print(blob[-1500:])
            return 2
        doc = P.load_drc(out)
        drc = D.summarize(doc, "error")
        log["drc"] = drc
        base = os.path.join(root, "logs", "drc_s6_final.json")
        if os.path.exists(base):
            worse = D.compare(P.load_drc(base), doc, "error")
            log["drc_vs_s6"] = worse
            log["drc_regressions"] = worse["new_signatures"]

    facts = json.loads(subprocess.run(
        [P.kicad_python(), os.path.join(root, "scripts", "42_board_facts.py"),
         "--root", root], capture_output=True, text=True).stdout)
    log["facts"] = facts

    checks = [
        P.check("ECO-5 applied", True, log["eco5"].get("ok")),
        P.check("C_BIAS_INV pad2 net", ECO5_NET,
                log["eco5"].get("net_after")),
        P.check("GND pins on the board", want_pins["GND"],
                board_pins.get("GND", 0),
                note="pins, not pads: pad_net_map keys on the pad number, so "
                     "the ESP32's nine thermal pads count once. GND was 86 "
                     "before ECO-5 took C_BIAS_INV pad 2 off it"),
        P.check("%s pins" % ECO5_NET, want_pins[ECO5_NET],
                board_pins.get(ECO5_NET, 0)),
        P.check("contract parity (overrides applied)", 0, len(diffs)),
        P.check("mechanical footprints", ["H1", "H2", "H3", "H4", "PEG1",
                                          "PEG2"], mech),
        P.check("fitted parts carrying fields", 135,
                log["fields"]["parts_with_fields"]),
        P.check("parts with no table entry", [],
                log["fields"]["no_table_entry"]),
        P.check("DNP parts", ["R_IO15_DN", "R_RST_UP"], log["fields"]["dnp"]),
        P.check("NPTH holes", 6, facts["npth_count"]),
        P.check("PTH pads", 16, facts["counts"]["pth_pads"]),
        P.check("zones filled and saved", True, facts["zones_all_filled"]),
        P.check("unconnected", 0, facts["unconnected"]),
    ]
    if drc:
        checks += [P.check("DRC errors", 0, drc["errors"]),
                   P.check("DRC unconnected", 0, drc["unconnected"]),
                   P.check("no new error signatures vs S6", [],
                           log.get("drc_regressions", []))]
    P.gate(root, "S7a", checks,
           notes="ECO-5 moves one pad from GND to BIAS_OUT_INT and reroutes "
                 "it; the BOM corrections are field-only. Parity is measured "
                 "against contract/netlist_contract.json with "
                 "contract/contract_overrides.json applied.",
           extra=log)
    bad = [c["name"] for c in checks if not c["pass"]]
    print("S7a: %s" % ("pass" if not bad else "FAIL " + ", ".join(bad)))
    for c in checks:
        print("  %-42s %s" % (c["name"], "ok" if c["pass"] else
                              "expected %r got %r" % (c["expected"],
                                                      c["actual"])))
    return 0 if not bad and ok_eco and ok_fld else 1


if __name__ == "__main__":
    sys.exit(main())
