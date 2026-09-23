#!/usr/bin/env python3
"""S7m -- keep a 0.1 mm solder-mask dam between pads of different nets.

    KPY scripts/71_mask_webs.py [--root DIR] [--dry-run]

JLC does not hold a green solder-mask dam narrower than 0.1 mm: it is
removed, and the two pad openings either side of it print as one. Between
two pads of one net that is harmless. Between two nets it is a solder bridge
waiting to happen, and the independent QA of Y9 found 24 dams under 0.1 mm
(smallest 0.053 mm) with the board-wide 0.0508 mm pad-to-mask expansion.

The board-wide expansion stays 0.0508 mm (ACCEPTANCE C, product.yaml
fab.mask.pad_to_mask_mm). Where two pads of different nets would leave a dam
under WEB_MM, each pad's own expansion is lowered just enough -- to
(copper gap - WEB_MM) / 2, never below 0 -- and a pad in several such pairs
keeps the smallest. The copper does not move.

A pair whose copper gap is itself under WEB_MM cannot get the dam by any
expansion; both pads go to 0 (the widest dam the copper allows) and the pair
is listed with its gap and why. Same-net pairs are listed and left alone.

Writes logs/mask_webs.json and gates/S7m.json.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import route as R                                  # noqa: E402
import epro as E                                   # noqa: E402

IU = R.IU
WEB_MM = 0.10
WEB = int(WEB_MM * IU)


def mask_sides(pcbnew, pad):
    out = []
    for mask, cu in ((pcbnew.F_Mask, pcbnew.F_Cu), (pcbnew.B_Mask, pcbnew.B_Cu)):
        if pad.IsOnLayer(mask):
            out.append((mask, cu))
    return out


def margin(pad, default):
    m = pad.GetLocalSolderMaskMargin()
    return default if m is None else m


def pairs_below(pcbnew, board, default):
    """(pad a, pad b, side, copper gap, dam) for every pad pair on a shared
    mask side whose dam is under WEB."""
    pads = [p for f in board.GetFootprints() for p in f.Pads()
            if mask_sides(pcbnew, p)]
    reach = WEB + 2 * default + int(0.05 * IU)
    out = []
    for i, a in enumerate(pads):
        ba = a.GetBoundingBox()
        for b in pads[i + 1:]:
            bb = b.GetBoundingBox()
            if (bb.GetLeft() > ba.GetRight() + reach
                    or ba.GetLeft() > bb.GetRight() + reach
                    or bb.GetTop() > ba.GetBottom() + reach
                    or ba.GetTop() > bb.GetBottom() + reach):
                continue
            sides_a = dict(mask_sides(pcbnew, a))
            for mask, cu in mask_sides(pcbnew, b):
                if mask not in sides_a:
                    continue
                try:
                    sa = a.GetEffectiveShape(cu)
                    sb = b.GetEffectiveShape(cu)
                except Exception:
                    continue
                g = P._actual_gap(sa, sb, reach, steps=14)
                if g is None:
                    continue
                dam = g - margin(a, default) - margin(b, default)
                if dam < WEB:
                    out.append((a, b, mask, g, dam))
    return out


def name(pad):
    fp = pad.GetParentFootprint()
    return "%s.%s" % (fp.GetReference() if fp else "?", pad.GetNumber())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    root = a.root

    import pcbnew
    bpath = P.board_path(root)
    board = pcbnew.LoadBoard(bpath)
    default = board.GetDesignSettings().m_SolderMaskExpansion
    before = pairs_below(pcbnew, board, default)

    want, fixed, impossible, same_net = {}, [], [], []
    for pa, pb, mask, gap, dam in before:
        rec = {"pads": [name(pa), name(pb)],
               "nets": [pa.GetNetname(), pb.GetNetname()],
               "side": board.GetLayerName(mask),
               "copper_gap_mm": P.mm(gap), "dam_before_mm": P.mm(dam)}
        if pa.GetNetCode() == pb.GetNetCode() and pa.GetNetCode() != 0:
            rec["why"] = ("same net: the two openings print as one, which "
                          "joins nothing that is not already joined")
            same_net.append(rec)
            continue
        each = max(0, (gap - WEB) // 2)
        if gap < WEB:
            rec["why"] = ("copper gap %.4f mm is under the %.2f mm dam itself; "
                          "no mask expansion can make the dam, so both pads "
                          "open at the copper (0 mm) -- the widest dam the "
                          "land pattern allows" % (P.mm(gap), WEB_MM))
            impossible.append(rec)
        else:
            fixed.append(rec)
        for p in (pa, pb):
            k = R.uid(p)
            want[k] = (p, min(want.get(k, (p, each))[1], each))

    retuned = []
    for _k, (p, m) in sorted(want.items(), key=lambda kv: name(kv[1][0])):
        cur = margin(p, default)
        if m >= cur:
            continue
        p.SetLocalSolderMaskMargin(int(m))
        retuned.append({"pad": name(p), "net": p.GetNetname(),
                        "margin_before_mm": P.mm(cur),
                        "margin_after_mm": P.mm(m)})

    after = pairs_below(pcbnew, board, default)
    diff_after = [x for x in after
                  if not (x[0].GetNetCode() == x[1].GetNetCode()
                          and x[0].GetNetCode() != 0)]
    left = [{"pads": [name(x[0]), name(x[1])],
             "nets": [x[0].GetNetname(), x[1].GetNetname()],
             "copper_gap_mm": P.mm(x[3]), "dam_mm": P.mm(x[4])}
            for x in diff_after]
    impossible_names = {tuple(r["pads"]) for r in impossible}
    unexplained = [r for r in left if tuple(r["pads"]) not in impossible_names]
    saved = False
    if retuned and not a.dry_run:
        board.Save(bpath)
        saved = True
    log = {"step": "S7m", "web_mm": WEB_MM,
           "board_wide_margin_mm": P.mm(default),
           "pairs_below_before": len(before),
           "different_net_fixed": fixed, "not_possible": impossible,
           "same_net_left": same_net, "pads_retuned": retuned,
           "different_net_below_after": left, "saved": saved}
    E.dump_json(os.path.join(root, "logs", "mask_webs.json"), log)
    checks = [
        P.check("different-net dams under %.2f mm, other than the listed "
                "land-pattern limits" % WEB_MM, 0, len(unexplained)),
        P.check("board-wide pad-to-mask expansion unchanged (ACCEPTANCE C)",
                0.0508, P.mm(default), ok=abs(P.mm(default) - 0.0508) < 1e-6),
        P.check("no pad expansion below 0", 0,
                sum(1 for r in retuned if r["margin_after_mm"] < 0)),
    ]
    P.gate(root, "S7m", checks,
           notes="%d pad pairs with a dam under %.2f mm: %d different-net "
                 "fixed by lowering %d pads' own expansion, %d not possible "
                 "(copper gap under the dam), %d same-net left."
                 % (len(before), WEB_MM, len(fixed), len(retuned),
                    len(impossible), len(same_net)))
    bad = [c["name"] for c in checks if not c["pass"]]
    print("S7m: %s" % ("pass" if not bad else "FAIL " + ", ".join(bad)))
    print("  pairs %d: fixed %d, not possible %d, same net %d; pads retuned %d"
          % (len(before), len(fixed), len(impossible), len(same_net),
             len(retuned)))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
