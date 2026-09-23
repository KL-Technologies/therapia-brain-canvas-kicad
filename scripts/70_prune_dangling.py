#!/usr/bin/env python3
"""S7d -- take out every track and via that ends in nothing.

    KPY scripts/70_prune_dangling.py [--root DIR] [--dry-run]

DRC listed 27 track_dangling and 3 via_dangling warnings on Rev.A. ACCEPTANCE
A lets them stand as warnings ("stitching vias that end in a pour"), but
none of the 27 is that: they are EasyEDA leftovers and repair offcuts --
stubs off pads that lead nowhere, a 3.65 mm USB_VBUS_RAW run on B.Cu behind a
via that connects to nothing else. On a 250 SPS EEG front end a stub is an
antenna, and on USB it is a reflection; none carries current.

The test is KiCad's own: CONNECTIVITY_DATA.TestTrackEndpointDangling with
tracks-in-pads ignored, which is the exact predicate behind DRC's
track_dangling, and for vias the number of copper layers on which anything
of the net touches them (a via touching one layer is DRC's via_dangling).
Dangling items are removed, connectivity is rebuilt and the search runs again,
because a stub is often a chain: the first cut exposes the next piece.
Nothing is removed if the unconnected count or any pad's net would change;
the step refuses to save instead.

Writes logs/dangling_prune.json and gates/S7d.json.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import epro as E                                   # noqa: E402

# Items that end in nothing on purpose and stay. Each needs its reason.
# (net, kind, (x_mm, y_mm)) -> why
KEEP = {}


def via_layers(pcbnew, board, conn, via):
    """Copper layers on which something of the via's own net touches it."""
    net = via.GetNetCode()
    pos = via.GetPosition()
    layers = set()
    for t in board.GetTracks():
        if t.GetNetCode() != net or t.GetClass() == "PCB_VIA":
            continue
        l = t.GetLayer()
        if via.IsOnLayer(l) and t.GetEffectiveShape(l).Collide(
                via.GetEffectiveShape(l), 0):
            layers.add(l)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() != net:
                continue
            for l in p.GetLayerSet().CuStack():
                if via.IsOnLayer(l) and p.GetEffectiveShape(l).Collide(
                        via.GetEffectiveShape(l), 0):
                    layers.add(l)
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetCode() != net:
            continue
        for l in z.GetLayerSet().CuStack():
            if z.HitTestFilledArea(l, pos, int(via.GetWidth(l) / 2)):
                layers.add(l)
    return layers


def kept(board, item):
    p = item.GetPosition() if item.GetClass() == "PCB_VIA" else item.GetStart()
    for (net, kind, at), _why in KEEP.items():
        if item.GetNetname() == net and abs(P.mm(p.x) - at[0]) < 1e-3 \
                and abs(P.mm(p.y) - at[1]) < 1e-3:
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    root = a.root

    import pcbnew
    bpath = P.board_path(root)
    board = pcbnew.LoadBoard(bpath)
    nets_before = P.pad_net_map(board, pcbnew)
    unc_before = P.unconnected_count(pcbnew, board)
    log = {"step": "S7d", "removed": [], "rounds": 0, "kept": []}
    first = None
    for rnd in range(50):
        board.BuildConnectivity()
        conn = board.GetConnectivity()
        tracks = [t for t in board.GetTracks()
                  if t.GetClass() == "PCB_TRACK"
                  and conn.TestTrackEndpointDangling(t, True)]
        vias = [v for v in board.GetTracks() if v.GetClass() == "PCB_VIA"
                and len(via_layers(pcbnew, board, conn, v)) < 2]
        if first is None:
            first = {"tracks": len(tracks), "vias": len(vias)}
        todo = [i for i in tracks + vias if not kept(board, i)]
        log["kept"] = [P.describe(board, i) for i in tracks + vias
                       if kept(board, i)]
        if not todo:
            break
        log["rounds"] = rnd + 1
        recs = [P.describe(board, it) for it in todo]
        for rec in recs:
            rec["round"] = rnd + 1
        log["removed"] += recs
        for it in todo:
            board.RemoveNative(it)

    board.BuildConnectivity()
    conn = board.GetConnectivity()
    left_t = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"
              and conn.TestTrackEndpointDangling(t, True)]
    left_v = [v for v in board.GetTracks() if v.GetClass() == "PCB_VIA"
              and len(via_layers(pcbnew, board, conn, v)) < 2]
    unc_after = P.unconnected_count(pcbnew, board)
    nets_after = P.pad_net_map(board, pcbnew)
    same_nets = nets_before == nets_after
    ok = unc_after <= unc_before and same_nets
    saved = False
    if ok and log["removed"] and not a.dry_run:
        board.Save(bpath)
        saved = True
    log.update({"found": first, "left": {"tracks": len(left_t),
                                         "vias": len(left_v)},
                "unconnected": [unc_before, unc_after], "saved": saved})
    E.dump_json(os.path.join(root, "logs", "dangling_prune.json"), log)
    n_tracks = sum(1 for r in log["removed"] if r["kind"] == "track")
    n_vias = sum(1 for r in log["removed"] if r["kind"] == "via")
    checks = [
        P.check("dangling tracks left (KiCad's own predicate)",
                len(log["kept"]), len(left_t),
                ok=len(left_t) <= len(log["kept"])),
        P.check("vias touching fewer than two layers left", 0, len(left_v)),
        P.check("unconnected items", unc_before, unc_after,
                ok=unc_after <= unc_before),
        P.check("every pad on the net it had", True, same_nets),
        P.check("board saved (or nothing to do)", True,
                saved or not log["removed"] or a.dry_run),
    ]
    P.gate(root, "S7d", checks,
           notes="found %d dangling tracks and %d one-layer vias; removed %d "
                 "tracks and %d vias in %d rounds; kept %d on purpose."
                 % (first["tracks"], first["vias"], n_tracks, n_vias,
                    log["rounds"], len(log["kept"])))
    bad = [c["name"] for c in checks if not c["pass"]]
    print("S7d: %s" % ("pass" if not bad else "FAIL " + ", ".join(bad)))
    print("  found %s, removed %d tracks / %d vias, left %s"
          % (first, n_tracks, n_vias, log["left"]))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
