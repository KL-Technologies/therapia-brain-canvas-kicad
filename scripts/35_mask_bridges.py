#!/usr/bin/env python3
"""Close the solder mask webs that DRC says are bridged.

    KPY scripts/35_mask_bridges.py --drc logs/drc_s5_l5.json

A `solder_mask_bridge` is not a copper fault. The copper of the two pads is far
enough apart; it is the *openings* in the resist that have merged, because each
one is drawn 0.0508 mm larger than its pad on every side and the board's
minimum web is another 0.0508 mm. Two pads whose copper is closer than

    2 x 0.0508 + 0.0508 = 0.1524 mm

therefore share one opening, and solder can wick from one to the other.

The fix is local, not global. ACCEPTANCE C fixes the board-wide pad-to-mask
clearance at 0.0508 mm and explains why (4 mil would leave a 0.0168 mm dam
between ADS1299 pins, which no fab can hold), so that value is not touched.
What changes is the margin on the individual pads that are bridged: shrink
their own openings until the web between them reaches the minimum. A margin of
zero -- the opening exactly the size of the pad -- is ordinary practice for
fine-pitch and 0402 parts, and it is the floor here; the resist is never pulled
inside the copper.

The arithmetic per pair, with G the copper gap and W the minimum web:

    both items have an opening    each may expand by (G - W) / 2
    only one has an opening       it may expand by  G - W        (a track is
                                  covered by resist, so it contributes none)

If G is below W the geometry cannot be saved by any margin, and the pair is
reported for the Amendments section of STATUS rather than quietly accepted.

Runs under the KiCad python. Does not run DRC; the caller re-runs it.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import route as R                                  # noqa: E402
import viol as V                                   # noqa: E402

TOL = int(0.01 * P.IU)


def resolve(pcbnew, board, entry):
    """The board item a DRC entry names, by description and position."""
    info = V.parse_item(entry)
    x = P.nm(info["x"]) if info["x"] is not None else None
    y = P.nm(info["y"]) if info["y"] is not None else None

    def near(p):
        return x is None or (abs(p.x - x) <= TOL and abs(p.y - y) <= TOL)

    if info["class"] in ("Pad", "NPTH", "PTH"):
        fp = board.FindFootprintByReference(info["ref"] or "")
        if fp is None:
            return None
        for p in fp.Pads():
            if info["pad"] is not None and p.GetNumber() != info["pad"]:
                continue
            if near(p.GetPosition()):
                return p
        return None
    for t in board.GetTracks():
        if info["net"] and t.GetNetname() != info["net"]:
            continue
        if t.GetClass() == "PCB_VIA":
            if info["class"] == "Via" and near(t.GetPosition()):
                return t
        elif info["class"] in ("Track", "Arc"):
            if near(t.GetStart()) or near(t.GetEnd()):
                return t
    return None


def copper_gap(pcbnew, a, b, ceiling):
    """Edge-to-edge copper distance on a layer both items are on."""
    la = set(R.item_layers(pcbnew, a))
    lb = set(R.item_layers(pcbnew, b))
    best = None
    for layer in la & lb:
        try:
            sa, sb = a.GetEffectiveShape(layer), b.GetEffectiveShape(layer)
        except Exception:
            continue
        g = P._actual_gap(sa, sb, ceiling)
        if g is None:
            continue
        best = g if best is None else min(best, g)
    return best


def has_aperture(pcbnew, board, item):
    """Does this item open a hole in the solder mask?

    Pads do. Tracks never do. Vias do only when tenting is off, and this board
    tents both sides."""
    if item.GetClass() != "PAD":
        return False
    return item.GetLayerSet().Contains(pcbnew.F_Mask) or \
        item.GetLayerSet().Contains(pcbnew.B_Mask)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--drc", default="logs/drc_s5_l5.json")
    a = ap.parse_args()
    root = a.root

    import pcbnew
    bpath = P.board_path(root)
    board = pcbnew.LoadBoard(bpath)
    ds = board.GetDesignSettings()
    web = ds.m_SolderMaskMinWidth
    default_margin = ds.m_SolderMaskExpansion
    log = {"min_web_mm": P.mm(web), "board_margin_mm": P.mm(default_margin)}

    doc = P.load_drc(a.drc if os.path.isabs(a.drc)
                     else os.path.join(root, a.drc))
    bridges = [v for v in doc.get("violations", [])
               if v.get("type") == "solder_mask_bridge"]
    log["bridges_in_report"] = len(bridges)

    # Per pad: the largest margin it may keep, over every pair it is in.
    allowed, pairs, impossible = {}, [], []
    pads = {}
    for v in bridges:
        its = v.get("items", [])
        if len(its) < 2:
            continue
        a_it, b_it = resolve(pcbnew, board, its[0]), resolve(pcbnew, board,
                                                             its[1])
        rec = {"a": its[0].get("description"), "b": its[1].get("description")}
        if a_it is None or b_it is None:
            rec["why"] = "an item named in the report is not on the board"
            impossible.append(rec)
            continue
        ceiling = int(2 * default_margin + web + int(0.05 * P.IU))
        g = copper_gap(pcbnew, a_it, b_it, ceiling)
        rec["copper_gap_mm"] = P.mm(g) if g is not None else None
        openers = [it for it in (a_it, b_it) if has_aperture(pcbnew, board, it)]
        rec["items_with_an_opening"] = len(openers)
        if g is None or not openers:
            rec["why"] = ("no shared layer, or neither item opens the mask"
                          if not openers else
                          "copper gap is larger than the search ceiling")
            impossible.append(rec)
            continue
        room = g - web
        if room < 0:
            rec["why"] = ("copper gap %.4f mm is below the %.4f mm minimum "
                          "web; no mask margin can separate these"
                          % (P.mm(g), P.mm(web)))
            impossible.append(rec)
            continue
        each = int(room // len(openers))
        rec["margin_allowed_mm"] = P.mm(each)
        for it in openers:
            k = R.uid(it)
            pads[k] = it
            allowed[k] = each if k not in allowed else min(allowed[k], each)
        pairs.append(rec)

    changed = []
    for k, it in pads.items():
        want = max(0, min(allowed[k], default_margin))
        cur = it.GetLocalSolderMaskMargin()
        cur_val = default_margin if cur is None else cur
        if want >= cur_val:
            continue
        it.SetLocalSolderMaskMargin(int(want))
        fp = it.GetParentFootprint()
        changed.append({"ref": fp.GetReference() if fp else None,
                        "pad": it.GetNumber(),
                        "net": it.GetNetname(),
                        "margin_before_mm": P.mm(cur_val),
                        "margin_after_mm": P.mm(want)})

    log["pairs"] = pairs
    log["not_fixable_by_margin"] = impossible
    log["pads_retuned"] = changed
    if changed:
        pcbnew.SaveBoard(bpath, board)
        log["saved"] = True
    print(json.dumps(log, indent=1))
    return 0 if not impossible else 1


if __name__ == "__main__":
    sys.exit(main())
