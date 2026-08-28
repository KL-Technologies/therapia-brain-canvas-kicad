#!/usr/bin/env python3
"""S4b: put ECO-1, ECO-2 and ECO-3 onto the PCB.

The schematic was corrected on 2026-08-16 and "Import Changes" was never run,
so the board S2 handed over is the pre-ECO layout. gates/netlist_diff.json is
the exact list of what it still owes:

  8 pins on the wrong net   TPS72325 EN (the fatal B1: EN tied to GND holds the
                            negative LDO disabled, so AVSS never comes up and
                            no ADS1299 works), ADS1299 RESV1, GPIO1-4, and the
                            two VCAP pins that were never routed
  4 parts missing           C_VCAP2, C_VCAP3, C_VCAP3_H, C_VCAP1_H
  2 parts in the wrong size ECO-3 takes C_VCAP1 and C_VREFP_10u to 1206

contract/netlist_contract.json is the authority for the result: after this runs
every pad on the board must carry the net the schematic says, and the gate
fails on a single difference.

Nothing is placed on faith. Every track, via and footprint position is checked
against the real copper with the design-rule clearance first (scripts/lib/
route.py); when no position works the step is recorded as a failure rather than
forced, so a bad edit cannot slip through as a pass.

Idempotent: pins already on the right net, parts already placed and footprints
already swapped are left alone.

Must run under the KiCad-bundled python (needs pcbnew), and the DRC at the end
needs a normal shell (see README).
"""

import os
import sys
import csv
import json
import math
import argparse
import subprocess
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import epro as E                      # noqa: E402
from lib import drc as D                       # noqa: E402
from lib import route as R                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD_NAME = "Therapia_EEG-HRV"
IU = R.IU

# --- design rule values, mirroring scripts/14_make_rules.py ------------------
CLEARANCE = int(0.0889 * IU)
HOLE_TO_HOLE = int(0.2 * IU)
HOLE_CLEARANCE = int(0.2 * IU)
EDGE_CLEARANCE = int(0.2 * IU)
VIA_DIA = int(0.6096 * IU)
VIA_DRILL = int(0.3048 * IU)
TRACK_W = int(0.2032 * IU)                     # 8 mil, the board's signal width

BOARD_BOX_MM = (120.0, 80.0, 181.8236, 125.0088)

# --- ECO-1: the eight pins ---------------------------------------------------
# (designator, pad number, net the schematic wants, note)
NET_CHANGES = [
    ("TPS72325", "3", "V_NLDO_IN", "ECO-1#1 EN to IN -- the fatal B1"),
    ("U_ADS", "31", "GND", "ECO-1#2 RESV1 to DGND"),
    ("U_ADS", "42", "GND", "ECO-1#3 GPIO1"),
    ("U_ADS", "44", "GND", "ECO-1#3 GPIO2"),
    ("U_ADS", "45", "GND", "ECO-1#3 GPIO3"),
    ("U_ADS", "46", "GND", "ECO-1#3 GPIO4"),
    ("U_ADS", "30", "VCAP2", "ECO-1#4 VCAP2"),
    ("U_ADS", "55", "VCAP3", "ECO-1#5 VCAP3"),
]

# --- ECO-1 / ECO-3: the four new capacitors ----------------------------------
# (designator, pad1 net, pad2 net, the ADS pad it decouples, source footprint)
NEW_PARTS = [
    ("C_VCAP2",   "VCAP2", "AVSS", ("U_ADS", "30"), "C_AVDD1_100n"),
    ("C_VCAP3",   "VCAP3", "AVSS", ("U_ADS", "55"), "C_AVDD1_100n"),
    ("C_VCAP3_H", "VCAP3", "AVSS", ("U_ADS", "55"), "C_AVDD1_100n"),
    ("C_VCAP1_H", "VCAP1", "AVSS", ("U_ADS", "28"), "C_AVDD1_100n"),
]

# ECO-3: 0603 -> 1206, from KiCad's own library.
FOOTPRINT_SWAPS = {
    "C_VCAP1": ("Capacitor_SMD", "C_1206_3216Metric"),
    "C_VREFP_10u": ("Capacitor_SMD", "C_1206_3216Metric"),
}
KICAD_FP_DIR = ("/Applications/KiCad/KiCad.app/Contents/SharedSupport/"
                "footprints")

PLACE_MIN_MM = 40 * 0.0254                                # 40 mil
PLACE_PREFERRED_MM = 250 * 0.0254                         # the ECO's window
PLACE_MAX_MM = 600 * 0.0254                               # fallback, recorded
PLACE_STEP_MM = 5 * 0.0254                                # 5 mil grid
# The search walks a 10 mil grid -- still a multiple of the 5 mil grid the rest
# of the board sits on, and a quarter of the candidates to test.
PLACE_SEARCH_STEP_MM = 10 * 0.0254
PLACE_ROTATIONS = (0.0, 90.0, 180.0, 270.0)
# Keep several viable positions, not just the nearest: committing pin 1's route
# can consume the space pin 2 needed, and the next position over usually works.
PLACE_CANDIDATES = 8
# The via-hop router is ~100x the cost of a straight/L test, so the sweeps that
# use it look at a bounded number of the nearest candidates rather than the
# whole ring.
VIA_HOP_ANCHORS = 6
VIA_HOP_SITES = 1200
# How far an ECO-3 part may be nudged to make its 1206 body fit. Beyond this
# the part is no longer next to the pin it decouples, so the script reports
# rather than moves.
SWAP_MOVE_MAX_MM = 150 * 0.0254
SWAP_MOVE_REVIEW_MM = 40 * 0.0254
# Minimum gap between the new part's body and any existing one. See
# lib/route.BodyIndex for why this replaces a courtyard-overlap test, and what
# the board's existing parts actually manage.
BODY_GAP = int(0.2 * IU)
# How long the track from a new capacitor's pin 1 to its net may be. Without a
# bound the search happily accepts a clear 10 mm run across the board, which
# defeats the point of a decoupling capacitor.
PIN1_MAX_ROUTE_MM = 4.0
PIN1_REVIEW_ROUTE_MM = 2.0
# A new part's pads are held further off other copper than the 0.0889 mm
# copper rule needs. At 2 mil mask expansion per side plus a 2 mil web, two
# pads closer than 0.152 mm have their solder mask openings merge -- copper
# clearance passes and DRC reports solder_mask_bridge instead. Placing
# C_VCAP2 0.6 mm from the ADS1299 produced exactly that.
NEW_PAD_CLEARANCE = int(0.17 * IU)


def mm(v):
    return round(v / float(IU), 6)


def pt(p):
    return (p.x, p.y)


def board_box():
    lo_x, lo_y, hi_x, hi_y = BOARD_BOX_MM
    return (lo_x * IU + EDGE_CLEARANCE, lo_y * IU + EDGE_CLEARANCE,
            hi_x * IU - EDGE_CLEARANCE, hi_y * IU - EDGE_CLEARANCE)


def find_pad(board, ref, number):
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        return None, None
    for p in fp.Pads():
        if p.GetNumber() == number:
            return fp, p
    return fp, None


# --- connecting a pad to its net ---------------------------------------------
def anchors_for(pcbnew, board, netcode, exclude_pad=None, layer=None):
    """Points that already belong to the net and can be routed to on F.Cu."""
    layer = pcbnew.F_Cu if layer is None else layer
    out = []
    for t in board.GetTracks():
        if t.GetNetCode() != netcode:
            continue
        if t.GetClass() == "PCB_VIA":
            out.append((pt(t.GetPosition()), "via"))
        elif t.GetLayer() == layer:
            a, b = pt(t.GetStart()), pt(t.GetEnd())
            out.append((a, "track_end"))
            out.append((b, "track_end"))
            out.append((((a[0] + b[0]) // 2, (a[1] + b[1]) // 2), "track_mid"))
    for f in board.GetFootprints():
        for p in f.Pads():
            if p.GetNetCode() != netcode:
                continue
            if exclude_pad is not None and R.uid(p) == R.uid(exclude_pad):
                continue
            if p.GetLayerSet().Contains(layer):
                out.append((pt(p.GetPosition()), "pad %s/%s"
                            % (f.GetReference(), p.GetNumber())))
    return out


def route_plan(idx, pcbnew, board, a, b, netcode, ignore=(), via_hop=True):
    """lib/route.plan_route with this board's rule values filled in."""
    return R.plan_route(idx, pcbnew, board, a, b, netcode, TRACK_W, CLEARANCE,
                        HOLE_CLEARANCE, HOLE_TO_HOLE, VIA_DIA, VIA_DRILL,
                        board_box(), ignore=ignore, allow_via_hop=via_hop)


def connect_point(idx, pcbnew, board, start, netcode, log_prefix,
                  ignore=(), max_reach_mm=6.0, exclude_pad=None,
                  anchors=True, dry_run=False):
    """Join `start` to the rest of its net: a track to something already on the
    net if one is reachable, otherwise a track to a freshly placed via.

    `exclude_pad` must be the pad being connected. Without it the pad's own
    centre is in the anchor list, sits zero away from `start`, and every call
    cheerfully reports "already touching" while laying no copper at all.

    `anchors=False` skips straight to the via, for callers that specifically
    want a drop to the plane rather than another surface connection.

    `dry_run=True` answers "could this be connected" without laying copper --
    the placement search needs it to reject a position where the capacitor's
    second pad could not reach AVSS.

    Returns a dict describing what was done, or one with ok=False."""
    layer = pcbnew.F_Cu
    cands = anchors_for(pcbnew, board, netcode, exclude_pad=exclude_pad,
                        layer=layer) if anchors else []
    cands = [(math.hypot(p[0] - start[0], p[1] - start[1]), p, why)
             for p, why in cands]
    cands.sort()
    cands = [c for c in cands if c[0] <= max_reach_mm * IU]
    # Two passes over the same anchors: straight/L first for all of them, then
    # the via hop for the nearest few. The via hop costs a hundred times more,
    # so trying it on every anchor before trying a cheap route on the next one
    # is what made this script time out.
    for via_hop, pool in ((False, cands), (True, cands[:VIA_HOP_ANCHORS])):
        for dist, p, why in pool:
            if dist < 1000:                    # genuinely coincident copper
                return {"ok": True, "method": "already touching",
                        "anchor": why}
            plan = route_plan(idx, pcbnew, board, start, p, netcode, ignore,
                              via_hop=via_hop)
            if plan.get("ok"):
                if not dry_run:
                    R.commit_route(pcbnew, board, plan, netcode, TRACK_W,
                                   VIA_DIA, VIA_DRILL)
                return {"ok": True, "method": "route to existing copper (%s)"
                        % plan["method"], "anchor": why, "length_mm": mm(dist),
                        "to_mm": [mm(p[0]), mm(p[1])],
                        "vias": [[mm(v[0]), mm(v[1])] for v in plan["vias"]]}

    # A via only connects anything if it lands inside a filled zone of the same
    # net. GND, AVSS, AVDD and the rest have planes, so dropping a via is a
    # real connection; VCAP1/VCAP2/VCAP3 do not, and a via there would be a
    # hole in the board joined to nothing while the net silently stayed open.
    name = board.FindNet(netcode).GetNetname()
    box = board_box()
    r_min = VIA_DIA / 2.0 + CLEARANCE
    for p in R.ring_points(start[0], start[1], r_min, 4.0 * IU,
                           PLACE_STEP_MM * IU):
        if not R.via_site_ok(idx, pcbnew, p[0], p[1], netcode, VIA_DIA,
                             VIA_DRILL, CLEARANCE, HOLE_TO_HOLE,
                             HOLE_CLEARANCE, box, ignore=ignore):
            continue
        zones = []
        for lyr in (pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
            zones += idx.zone_nets_at(p[0], p[1], lyr)
        if name not in zones:
            continue
        if not R.straight_ok(idx, pcbnew, board, start, p, layer, TRACK_W,
                             netcode, CLEARANCE, HOLE_CLEARANCE, ignore=ignore):
            continue
        if not dry_run:
            R.add_via(pcbnew, board, p, netcode, VIA_DIA, VIA_DRILL)
            R.add_track(pcbnew, board, start, p, layer, TRACK_W, netcode)
        return {"ok": True, "method": "new via into the %s plane" % name,
                "via_mm": [mm(p[0]), mm(p[1])],
                "length_mm": mm(math.hypot(p[0] - start[0], p[1] - start[1])),
                "zones_here": sorted(set(zones))}
    return {"ok": False,
            "reason": "no reachable anchor, and no via site that lands in a "
                      "%s zone (%s)" % (name, "the net has no plane to drop "
                                        "into" if not any(
                                            z.GetNetname() == name
                                            for z in idx.zones)
                                        else "nowhere legal in reach"),
            "from_mm": [mm(start[0]), mm(start[1])]}


# --- phase 1: net changes ----------------------------------------------------
def apply_net_changes(board, pcbnew, log):
    results = []
    for ref, number, want, note in NET_CHANGES:
        fp, pad = find_pad(board, ref, number)
        row = {"ref": ref, "pad": number, "want": want, "note": note}
        if pad is None:
            row.update(ok=False, reason="pad not found")
            results.append(row)
            continue
        have = pad.GetNetname()
        row["was"] = have
        if have == want:
            row.update(ok=True, action="already applied",
                       pad_mm=[mm(pad.GetPosition().x),
                               mm(pad.GetPosition().y)])
            results.append(row)
            continue

        removed = []
        if have:
            island, shared = R.trace_island(pcbnew, board, pad)
            if shared:
                row.update(ok=False, action="refused",
                           reason="the copper on this pad also serves %s -- "
                                  "removing it would disconnect them"
                                  % ", ".join(sorted(
                                      "%s/%s" % (p.GetParentFootprint()
                                                 .GetReference(),
                                                 p.GetNumber())
                                      for p in shared)))
                results.append(row)
                continue
            for it in island:
                removed.append({"class": it.GetClass(), "net": it.GetNetname(),
                                "at_mm": [mm(it.GetPosition().x),
                                          mm(it.GetPosition().y)]})
            R.remove_items(board, island)
        row["removed_stub"] = removed

        net = R.get_or_create_net(pcbnew, board, want)
        pad.SetNetCode(net.GetNetCode())
        row["created_net"] = want not in log.get("nets_before", [])
        row["ok"] = True
        row["action"] = "net changed"
        results.append(row)
    return results


def net_has_other_members(board, netcode, pad):
    """Is there anything else on this net to connect to?"""
    for t in board.GetTracks():
        if t.GetNetCode() == netcode:
            return True
    for f in board.GetFootprints():
        for p in f.Pads():
            if p.GetNetCode() == netcode and R.uid(p) != R.uid(pad):
                return True
    return False


def connect_net_changes(board, pcbnew, log, results):
    """Second pass: every pad whose net we changed now needs copper to it.

    Separate from the change pass so that pads moving onto the same net (the
    four GPIOs) can anchor onto each other.

    Two cases are deliberately not routed here:
      * VCAP2 and VCAP3 are brand new nets whose only other member is the
        capacitor that phase 3 has yet to place. Dropping a via for them now
        would connect the pin to nothing -- the via would land under the
        ADS1299 and stitch into whatever inner-layer zone happens to be there.
      * a pad that already has same-net copper touching it.
    """
    idx = R.CopperIndex(pcbnew, board)
    order = sorted(range(len(results)),
                   key=lambda i: results[i].get("want") or "")
    for i in order:
        row = results[i]
        if not row.get("ok", True) or row.get("action") == "already applied":
            continue
        fp, pad = find_pad(board, row["ref"], row["pad"])
        if pad is None:
            continue
        netcode = pad.GetNetCode()
        start = pt(pad.GetPosition())
        if not net_has_other_members(board, netcode, pad):
            row["connect"] = {"ok": True, "method": "deferred",
                              "note": "net %s has no other member yet; the "
                                      "capacitor placed in phase 3 makes the "
                                      "connection" % row["want"]}
            continue
        touching = [t for t in board.GetTracks()
                    if t.GetNetCode() == netcode and R.touches(pcbnew, pad, t)]
        if touching:
            row["connect"] = {"ok": True, "method": "already touching",
                              "items": len(touching)}
            continue
        row["connect"] = connect_point(idx, pcbnew, board, start, netcode,
                                       row["ref"], ignore=[pad],
                                       exclude_pad=pad)
        row["ok"] = bool(row["connect"].get("ok"))
        idx.rebuild()

    # The four GPIO pins can end up chained to each other and to nothing else
    # -- pad 44 routes to pad 45, pad 46 routes to pad 45, and the little
    # island floats. Anything that only reaches pads this ECO just moved needs
    # a via down to the plane.
    idx.rebuild()
    moved = {"%s/%s" % (r["ref"], r["pad"]) for r in results}
    for row in results:
        if not row.get("ok", True) or row.get("connect", {}).get("method") \
                in ("deferred",):
            continue
        fp, pad = find_pad(board, row["ref"], row["pad"])
        if pad is None:
            continue
        island, shared = R.trace_island(pcbnew, board, pad)
        has_via = any(i.GetClass() == "PCB_VIA" for i in island)
        reaches_old = any(
            "%s/%s" % (p.GetParentFootprint().GetReference(), p.GetNumber())
            not in moved for p in shared)
        if has_via or reaches_old:
            continue
        res = connect_point(idx, pcbnew, board, pt(pad.GetPosition()),
                            pad.GetNetCode(), row["ref"], ignore=[pad],
                            exclude_pad=pad, anchors=False)
        row["plane_drop"] = res
        row["ok"] = row.get("ok", True) and bool(res.get("ok"))
        idx.rebuild()
    return results


# --- phase 2: ECO-3 footprint swaps -----------------------------------------
def swap_footprints(board, pcbnew, log):
    out = []
    for ref, (lib, name) in sorted(FOOTPRINT_SWAPS.items()):
        row = {"ref": ref, "to": "%s:%s" % (lib, name)}
        old = board.FindFootprintByReference(ref)
        if old is None:
            row.update(ok=False, reason="footprint not on board")
            out.append(row)
            continue
        if old.GetFPIDAsString() == "%s:%s" % (lib, name):
            row.update(ok=True, action="already swapped",
                       placed_at_mm=[mm(old.GetPosition().x),
                                     mm(old.GetPosition().y)],
                       placed_rotation=old.GetOrientationDegrees(),
                       pad_nets={p.GetNumber(): p.GetNetname()
                                 for p in old.Pads()})
            out.append(row)
            continue
        pos = pt(old.GetPosition())
        rot = old.GetOrientationDegrees()
        nets = {p.GetNumber(): p.GetNetCode() for p in old.Pads()}
        old_pads = {p.GetNumber(): pt(p.GetPosition()) for p in old.Pads()}
        row.update(from_fpid=old.GetFPIDAsString(), at_mm=[mm(pos[0]),
                                                          mm(pos[1])],
                   rotation=rot, pad_nets={k: board.FindNet(v).GetNetname()
                                           for k, v in nets.items()})

        path = os.path.join(KICAD_FP_DIR, lib + ".pretty")
        try:
            new = pcbnew.FootprintLoad(path, name)
        except Exception as exc:
            row.update(ok=False, reason="FootprintLoad failed: %s" % exc)
            out.append(row)
            continue
        if new is None:
            row.update(ok=False, reason="footprint %s not in %s" % (name, path))
            out.append(row)
            continue

        board.RemoveNative(old)
        board.Add(new)
        new.SetReference(ref)
        new.SetOrientationDegrees(rot)
        for p in new.Pads():
            if p.GetNumber() in nets:
                p.SetNetCode(nets[p.GetNumber()])
        new.Reference().SetVisible(False)
        new.Value().SetVisible(False)

        # A 1206 is 1.55 mm wider than the 0603 it replaces, and this board has
        # no slack: dropped straight onto C_VCAP1's old centre the new pad 1
        # lands 0.074 mm from C_VCAP4's pad. So the old centre is only the
        # first candidate, and the search walks outwards from it if it clashes.
        idx = R.CopperIndex(pcbnew, board)
        cyidx = R.CourtyardIndex(pcbnew, board, skip_refs=[ref])
        bodyidx = R.BodyIndex(pcbnew, board, skip_refs=[ref])
        own = [new] + list(new.Pads())
        box = board_box()
        # Deliberately a short leash. C_VCAP1 is the ADS1299's 100 uF charge
        # pump reservoir and C_VREFP_10u sits on the reference; both have to
        # stay next to the pin they serve. An unbounded search "succeeds" by
        # moving the part across the board, which is worse than reporting that
        # it does not fit.
        sites = [pos] + R.ring_points(pos[0], pos[1],
                                      PLACE_SEARCH_STEP_MM * IU,
                                      SWAP_MOVE_MAX_MM * IU,
                                      PLACE_SEARCH_STEP_MM * IU)
        # Rotations matter here: a 1206 is 4.6 mm end to end and 1.8 mm across,
        # so turning it 90 degrees can fit it into a channel that the original
        # orientation cannot use.
        chosen, chosen_rot, reasons = None, rot, collections.Counter()
        for cand in sites:
            for cand_rot in (rot, (rot + 90) % 360):
                new.SetOrientationDegrees(cand_rot)
                new.SetPosition(pcbnew.VECTOR2I(int(cand[0]), int(cand[1])))
                why = site_is_clear(idx, bodyidx, pcbnew, board, new, box, own)
                if why is None:
                    chosen, chosen_rot = cand, cand_rot
                    break
                reasons[why.split(" by ")[0]] += 1
            if chosen:
                break
        if chosen is None:
            board.RemoveNative(new)
            board.Add(old)                     # put the 0603 back
            row.update(ok=False, rejects=dict(reasons.most_common()),
                       reason="the 1206 body does not fit within %d mil of "
                              "%s's position at either orientation; ECO-3 "
                              "needs a human layout change here (neighbouring "
                              "parts have to move)"
                              % (round(SWAP_MOVE_MAX_MM / 0.0254), ref))
            out.append(row)
            continue
        new.SetOrientationDegrees(chosen_rot)
        new.SetPosition(pcbnew.VECTOR2I(int(chosen[0]), int(chosen[1])))
        row["placed_rotation"] = chosen_rot
        row["ok"] = True
        moved = math.hypot(chosen[0] - pos[0], chosen[1] - pos[1])
        row["moved_mm"] = mm(moved)
        cy = cyidx.overlap(new)
        row["courtyard_overlap"] = (None if cy is None else
                                    {"with": cy[0], "area_mm2": cy[1]})
        if moved > SWAP_MOVE_REVIEW_MM * IU:
            row["review"] = (
                "moved %.2f mm to fit the 1206 body. That is further than a "
                "decoupling part should drift from its pin; a human should "
                "check the result against the ADS1299 layout guidance."
                % (moved / float(IU)))
        row["placed_at_mm"] = [mm(chosen[0]), mm(chosen[1])]
        row["new_pads_mm"] = {p.GetNumber(): [mm(p.GetPosition().x),
                                              mm(p.GetPosition().y)]
                              for p in new.Pads()}
        row["old_pads_mm"] = {k: [mm(v[0]), mm(v[1])]
                              for k, v in old_pads.items()}
        row["bridge"] = []
        # The tracks that used to land on the 0603 pads now stop short of the
        # 1206 ones, so each pad has to be joined back to its net.
        idx.rebuild()
        own = [new] + list(new.Pads())
        for p in new.Pads():
            num = p.GetNumber()
            res = connect_point(idx, pcbnew, board, pt(p.GetPosition()),
                                p.GetNetCode(), ref, ignore=own, exclude_pad=p)
            row["bridge"].append(dict(res, pad=num))
            row["ok"] = row["ok"] and bool(res.get("ok"))
            idx.rebuild()
        out.append(row)
    return out


# --- phase 3: the four new capacitors ---------------------------------------
def make_chip_footprint(pcbnew, board, src, ref, value):
    """A copy of `src`'s pads and courtyard, built from scratch.

    pcbnew.FOOTPRINT(src) would be shorter, but a copied footprint keeps the
    original's KIIDs -- verified: the copy's pads come back with the same
    uuids as C_AVDD1_100n's, and there is no way to reassign them from python
    (m_Uuid is read-only and FixUuids() is a no-op here). Duplicated uuids
    would collide in the board file and break every ignore-set in
    lib/route.py, which is keyed on them.

    Silkscreen is deliberately not copied: these four parts go into an already
    crowded area, and the board's silk_overlap count is high enough."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID(*src.GetFPIDAsString().split(":", 1)))
    board.Add(fp)
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    fp.SetAttributes(pcbnew.FP_SMD)
    fp.SetPosition(src.GetPosition())
    for sp in src.Pads():
        p = pcbnew.PAD(fp)
        p.SetNumber(sp.GetNumber())
        p.SetAttribute(sp.GetAttribute())
        p.SetShape(sp.GetShape())
        p.SetSize(sp.GetSize())
        p.SetDrillSize(sp.GetDrillSize())
        p.SetLayerSet(sp.GetLayerSet())
        try:
            p.SetRoundRectRadiusRatio(sp.GetRoundRectRadiusRatio())
        except Exception:
            pass
        fp.Add(p)
        p.SetFPRelativePosition(sp.GetFPRelativePosition())
    # Carry the body outline over as well as the courtyard: the placement
    # search measures body-to-body clearance off F.Fab.
    fab = R.body_box(pcbnew, src)
    if fab:
        sp = src.GetPosition()
        rect = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_RECT)
        rect.SetLayer(pcbnew.F_Fab)
        rect.SetWidth(int(0.051 * IU))
        rect.SetFilled(False)
        fp.Add(rect)
        here = fp.GetPosition()
        rect.SetStart(pcbnew.VECTOR2I(fab[0] - sp.x + here.x,
                                      fab[1] - sp.y + here.y))
        rect.SetEnd(pcbnew.VECTOR2I(fab[2] - sp.x + here.x,
                                    fab[3] - sp.y + here.y))
    cy = src.GetCourtyard(pcbnew.F_Cu)
    if cy is not None and cy.OutlineCount():
        bb = cy.BBox(0)
        sp = src.GetPosition()
        rect = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_RECT)
        rect.SetLayer(pcbnew.F_CrtYd)
        rect.SetWidth(int(0.05 * IU))
        rect.SetFilled(False)
        fp.Add(rect)
        rect.SetStart(pcbnew.VECTOR2I(bb.GetLeft() - sp.x + fp.GetPosition().x,
                                      bb.GetTop() - sp.y + fp.GetPosition().y))
        rect.SetEnd(pcbnew.VECTOR2I(bb.GetRight() - sp.x + fp.GetPosition().x,
                                    bb.GetBottom() - sp.y + fp.GetPosition().y))
    return fp


def site_is_clear(idx, bodyidx, pcbnew, board, fp, box, own):
    """Does this footprint position clear copper, mechanical holes, the board
    edge and every other part's courtyard?"""
    bb = fp.GetBoundingBox()
    if not (box[0] <= bb.GetLeft() and bb.GetRight() <= box[2]
            and box[1] <= bb.GetTop() and bb.GetBottom() <= box[3]):
        return "off the board"
    for p in fp.Pads():
        pp = pt(p.GetPosition())
        reach = max(p.GetSize().x, p.GetSize().y) / 2.0
        if idx.npth_conflicts(pp[0], pp[1], reach, HOLE_CLEARANCE, ignore=own):
            return "over a mechanical hole"
        for layer in p.GetLayerSet().CuStack():
            if idx.shape_conflicts(p.GetEffectiveShape(layer), layer,
                                   NEW_PAD_CLEARANCE, p.GetNetCode(),
                                   ignore=own):
                return "pad too close to other copper"
    clash = bodyidx.clash(fp, BODY_GAP)
    if clash:
        return "body within %.2f mm of %s" % (BODY_GAP / float(IU), clash)
    return None


def place_new_parts(board, pcbnew, log, parts_table):
    out = []
    box = board_box()
    for ref, net1, net2, (tref, tpad), source_ref in NEW_PARTS:
        row = {"ref": ref, "pad1_net": net1, "pad2_net": net2,
               "targets": "%s/%s" % (tref, tpad)}
        existing = board.FindFootprintByReference(ref)
        _tfp, target = find_pad(board, tref, tpad)
        if target is None:
            row.update(ok=False, reason="target pad %s/%s not found"
                       % (tref, tpad))
            out.append(row)
            continue
        if existing is not None:
            # Report the geometry on a re-run too; a gate file that only says
            # "already placed" is useless to whoever reads it later.
            p1 = next((p for p in existing.Pads()
                       if p.GetNumber() == "1"), None)
            d = (math.hypot(p1.GetPosition().x - target.GetPosition().x,
                            p1.GetPosition().y - target.GetPosition().y)
                 if p1 is not None else None)
            row.update(ok=True, action="already placed",
                       at_mm=[mm(existing.GetPosition().x),
                              mm(existing.GetPosition().y)],
                       rotation=existing.GetOrientationDegrees(),
                       pad1_mm=(None if p1 is None else
                                [mm(p1.GetPosition().x),
                                 mm(p1.GetPosition().y)]),
                       distance_to_pin_mm=(None if d is None else mm(d)),
                       within_eco_window=(None if d is None else
                                          bool(d <= PLACE_PREFERRED_MM * IU)),
                       footprint=existing.GetFPIDAsString())
            out.append(row)
            continue
        src = board.FindFootprintByReference(source_ref)
        if src is None:
            row.update(ok=False, reason="source footprint %s not on board"
                       % source_ref)
            out.append(row)
            continue

        n1 = R.get_or_create_net(pcbnew, board, net1)
        n2 = R.get_or_create_net(pcbnew, board, net2)
        tp = pt(target.GetPosition())
        # Index the board before the new part exists, so its own pads are not
        # obstacles to itself.
        idx = R.CopperIndex(pcbnew, board)
        cyidx = R.CourtyardIndex(pcbnew, board, skip_refs=[ref])
        bodyidx = R.BodyIndex(pcbnew, board, skip_refs=[ref])
        info = parts_table.get(ref, {})
        fp = make_chip_footprint(pcbnew, board, src, ref,
                                 info.get("value", ""))
        for p in fp.Pads():
            p.SetNetCode(n1.GetNetCode() if p.GetNumber() == "1"
                         else n2.GetNetCode())
        own = [fp] + list(fp.Pads())
        # Candidate-major, not rotation-major: the ring is already sorted
        # nearest-first, so the first position that works is the closest one,
        # and a decoupling capacitor wants to be as close to its pin as the
        # board allows.
        # Pin 1 may land on the target pad or on anything else already on the
        # same net -- C_VCAP3_H is the second capacitor on VCAP3 and reaches
        # its pin through C_VCAP3.
        targets = [tp] + [p for p, _why in
                          anchors_for(pcbnew, board, n1.GetNetCode(),
                                      layer=pcbnew.F_Cu)]
        # Four sweeps, cheapest and closest first. The ring is sorted
        # nearest-first, so the first hit in a sweep is the closest position
        # that sweep allows. Sweeping the ECO's 250 mil window before the wider
        # fallback keeps a far placement from winning just because it was found
        # with a cheaper route test.
        sweeps = [(PLACE_MIN_MM, PLACE_PREFERRED_MM, False),
                  (PLACE_MIN_MM, PLACE_PREFERRED_MM, True),
                  (PLACE_PREFERRED_MM, PLACE_MAX_MM, False),
                  (PLACE_PREFERRED_MM, PLACE_MAX_MM, True)]
        best, rejects = [], collections.Counter()
        for r_lo, r_hi, via_hop in sweeps:
            tried = 0
            for cand in R.ring_points(tp[0], tp[1], r_lo * IU, r_hi * IU,
                                      PLACE_SEARCH_STEP_MM * IU):
                if via_hop and tried >= VIA_HOP_SITES:
                    break
                for rot in PLACE_ROTATIONS:
                    fp.SetOrientationDegrees(rot)
                    fp.SetPosition(pcbnew.VECTOR2I(int(cand[0]), int(cand[1])))
                    why = site_is_clear(idx, bodyidx, pcbnew, board, fp, box, own)
                    if why:
                        rejects[why.split(" by ")[0]] += 1
                        continue
                    p1 = next((p for p in fp.Pads()
                               if p.GetNumber() == "1"), None)
                    if p1 is None:
                        continue
                    a = pt(p1.GetPosition())
                    near = sorted(targets, key=lambda q: math.hypot(
                        q[0] - a[0], q[1] - a[1]))
                    near = [q for q in near
                            if math.hypot(q[0] - a[0], q[1] - a[1])
                            <= PIN1_MAX_ROUTE_MM * IU]
                    if not near:
                        rejects["no %s to reach within %g mm"
                                % (net1, PIN1_MAX_ROUTE_MM)] += 1
                        continue
                    tried += 1
                    # Ignore the footprint and pad 1 itself, but NOT pad 2:
                    # it is on another net, and letting the router treat it as
                    # invisible produced a track straight across it.
                    skip1 = [fp, p1, target]
                    plan = None
                    for q in near[:(2 if via_hop else 6)]:
                        trial = route_plan(idx, pcbnew, board, a, q,
                                           n1.GetNetCode(), ignore=skip1,
                                           via_hop=via_hop)
                        if trial.get("ok"):
                            plan = trial
                            plan["to"] = q
                            break
                    if plan is None:
                        rejects["pin 1 not routable to %s" % net1] += 1
                        continue
                    # Pin 2 has to reach AVSS from here too; a position that
                    # only satisfies pin 1 is not a position.
                    p2 = next((p for p in fp.Pads()
                               if p.GetNumber() == "2"), None)
                    if p2 is not None and not connect_point(
                            idx, pcbnew, board, pt(p2.GetPosition()),
                            n2.GetNetCode(), ref, ignore=[fp, p2],
                            exclude_pad=p2, dry_run=True).get("ok"):
                        rejects["pin 2 not connectable to %s" % net2] += 1
                        continue
                    best.append((math.hypot(a[0] - tp[0], a[1] - tp[1]),
                                 cand, rot, plan))
                    break
                if len(best) >= PLACE_CANDIDATES:
                    break
            if best:
                break
        if not best:
            board.RemoveNative(fp)
            row.update(ok=False, rejects=dict(rejects.most_common()),
                       reason="no position within %d..%d mil of %s/%s clears "
                              "copper, courtyards and a route to pin 1"
                              % (round(PLACE_MIN_MM / 0.0254),
                                 round(PLACE_MAX_MM / 0.0254), tref, tpad))
            out.append(row)
            continue

        # Try the candidates in order. Committing pin 1 changes the board, so
        # a position that looked fine can leave pin 2 stranded; back the whole
        # thing out and take the next one rather than leaving a half-wired part.
        placed_ok, last_fail = False, None
        for _d, cand, rot, plan in best:
            fp.SetOrientationDegrees(rot)
            fp.SetPosition(pcbnew.VECTOR2I(int(cand[0]), int(cand[1])))
            pads = {p.GetNumber(): p for p in fp.Pads()}
            a = pt(pads["1"].GetPosition())
            idx.rebuild()
            made = R.commit_route(pcbnew, board, plan, n1.GetNetCode(),
                                  TRACK_W, VIA_DIA, VIA_DRILL)
            idx.rebuild()
            r2 = connect_point(idx, pcbnew, board, pt(pads["2"].GetPosition()),
                               n2.GetNetCode(), ref, ignore=[fp, pads["2"]],
                               exclude_pad=pads["2"])
            if r2.get("ok"):
                placed_ok = True
                break
            R.remove_items(board, made)
            last_fail = ("placed at %s but pad 2 could not reach %s: %s"
                         % ([mm(cand[0]), mm(cand[1])], net2, r2.get("reason")))
            idx.rebuild()
        if not placed_ok:
            board.RemoveNative(fp)
            row.update(ok=False, action="rolled back",
                       candidates_tried=len(best), reason=last_fail)
            out.append(row)
            continue

        cy = cyidx.overlap(fp)
        row.update(ok=True, action="placed", candidates_tried=len(best),
                   courtyard_overlap=(None if cy is None else
                                      {"with": cy[0], "area_mm2": cy[1]}),
                   at_mm=[mm(cand[0]), mm(cand[1])], rotation=rot,
                   pad1_mm=[mm(a[0]), mm(a[1])],
                   distance_to_pin_mm=mm(_d),
                   within_eco_window=bool(_d <= PLACE_PREFERRED_MM * IU),
                   pad2_connect=r2, pad1_route=plan["method"],
                   footprint=fp.GetFPIDAsString())
        route_len = math.hypot(a[0] - plan["to"][0], a[1] - plan["to"][1])
        row["pad1_route_mm"] = mm(route_len)
        if route_len > PIN1_REVIEW_ROUTE_MM * IU:
            row["review_route"] = (
                "pin 1 reaches %s over %.2f mm of track. For a bypass "
                "capacitor that is a long path; a human should check it."
                % (net1, route_len / float(IU)))
        if not row["within_eco_window"]:
            row["review"] = (
                "placed %.2f mm from %s/%s, beyond the ECO's 250 mil window. "
                "Nothing closer clears copper and courtyards -- this corner of "
                "the board is full. Decoupling at this distance is weaker than "
                "intended; a human should decide whether to move neighbouring "
                "parts to bring it in." % (_d / float(IU), tref, tpad))
        out.append(row)
    return out


# --- phase 4: fields ---------------------------------------------------------
def apply_fields(board, pcbnew, parts_table):
    touched, missing = 0, []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref:
            continue
        info = parts_table.get(ref)
        if info is None:
            if int(fp.GetAttributes()) & int(pcbnew.FP_EXCLUDE_FROM_BOM):
                continue                       # H1..H4, PEG1/PEG2
            missing.append(ref)
            continue
        fp.SetValue(info["value"])
        for key, val in (("MPN", info["mpn"]), ("LCSC", info["lcsc"])):
            fp.SetField(key, val)
            # A field created by SetField lands visible on F.SilkS, which
            # would print 135 part numbers onto the silkscreen.
            f = fp.GetField(key)
            f.SetVisible(False)
            f.SetLayer(pcbnew.Cmts_User)
        touched += 1
    return {"fields_set": touched, "no_table_entry": sorted(missing)}


# --- verification against the contract ---------------------------------------
def pad_net_map(board, pcbnew):
    """designator -> pad number -> set of nets. Multiple physical pads can
    share a number (the ESP32 thermal pad is nine of them), so the value is a
    set: the contract is met when that set is exactly the one net it names."""
    out = collections.defaultdict(lambda: collections.defaultdict(set))
    mech = set()
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref:
            continue
        if int(fp.GetAttributes()) & int(pcbnew.FP_EXCLUDE_FROM_BOM):
            mech.add(ref)
            continue
        for p in fp.Pads():
            out[ref][p.GetNumber()].add(p.GetNetname())
    return out, mech


def diff_against_contract(board, pcbnew, contract):
    have, mech = pad_net_map(board, pcbnew)
    want = contract["by_designator"]
    diffs = []
    for ref in sorted(set(want) | set(have)):
        if ref not in want:
            diffs.append({"ref": ref, "issue": "on the board, not in the "
                                               "contract"})
            continue
        if ref not in have:
            diffs.append({"ref": ref, "issue": "in the contract, not on the "
                                               "board"})
            continue
        for num in sorted(set(want[ref]) | set(have[ref])):
            wnet = (want[ref].get(num) or {}).get("net", "")
            if wnet == "NC":                   # the contract's word for "no net"
                wnet = ""
            hnets = have[ref].get(num)
            if hnets is None:
                diffs.append({"ref": ref, "pad": num, "want": wnet,
                              "have": None, "issue": "pad missing"})
                continue
            if hnets != {wnet}:
                diffs.append({"ref": ref, "pad": num, "want": wnet,
                              "have": sorted(hnets),
                              "issue": "net mismatch"})
    return diffs, sorted(mech)


def read_parts_table(root):
    path = os.path.join(root, "data", "parts_lcsc.csv")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return {r["designator"]: r for r in csv.DictReader(f)}


def run_drc(kc, board_path, out_path, refill=True):
    cmd = [kc, "pcb", "drc", "--format", "json", "--severity-all"]
    if refill:
        cmd += ["--refill-zones", "--save-board"]
    cmd += ["-o", out_path, board_path]
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--skip-drc", action="store_true")
    args = ap.parse_args()
    root = args.root
    board_path = os.path.join(root, "board", BOARD_NAME + ".kicad_pcb")

    try:
        import pcbnew
    except ImportError:
        print("pcbnew unavailable -- run this with the KiCad-bundled python")
        return 2

    contract = E.load_json(os.path.join(root, "contract",
                                        "netlist_contract.json"))
    parts_table = read_parts_table(root)
    board = pcbnew.LoadBoard(board_path)
    log = {"nets_before": sorted(
        board.FindNet(i).GetNetname() for i in range(board.GetNetCount()))}

    before_counts = {
        "footprints": len(list(board.GetFootprints())),
        "tracks": sum(1 for t in board.GetTracks()
                      if t.GetClass() != "PCB_VIA"),
        "vias": sum(1 for t in board.GetTracks() if t.GetClass() == "PCB_VIA"),
    }

    changes = apply_net_changes(board, pcbnew, log)
    changes = connect_net_changes(board, pcbnew, log, changes)
    # New parts before the ECO-3 swaps: the four 0402s have to sit next to
    # specific ADS1299 pins, while the two 1206s only have to sit somewhere.
    # Growing C_VREFP_10u to 1206 first would take the last free ground next to
    # the VCAP pins.
    placed = place_new_parts(board, pcbnew, log, parts_table)
    swaps = swap_footprints(board, pcbnew, log)
    fields = apply_fields(board, pcbnew, parts_table)

    board.BuildListOfNets()
    diffs, mech = diff_against_contract(board, pcbnew, contract)
    after_counts = {
        "footprints": len(list(board.GetFootprints())),
        "tracks": sum(1 for t in board.GetTracks()
                      if t.GetClass() != "PCB_VIA"),
        "vias": sum(1 for t in board.GetTracks() if t.GetClass() == "PCB_VIA"),
    }
    nets_after = sorted(board.FindNet(i).GetNetname()
                        for i in range(board.GetNetCount()))
    pcbnew.SaveBoard(board_path, board)

    # ---- DRC ---------------------------------------------------------------
    kc = os.environ.get("KC",
                        "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
    drc_path = os.path.join(root, "logs", "drc_after_eco.json")
    drc_ok, drc_sum, cmp = False, {}, {}
    if not args.skip_drc:
        proc = run_drc(kc, board_path, drc_path, refill=True)
        blob = (proc.stdout or "") + (proc.stderr or "")
        drc_ok = os.path.exists(drc_path) and "Fatal error" not in blob
        if drc_ok:
            cur = D.load(drc_path)
            drc_sum = D.summarize(cur)
            base_path = os.path.join(root, "logs", "drc_baseline_rules.json")
            if os.path.exists(base_path):
                cmp = D.compare(D.load(base_path), cur)

    eco_nets = ("V_NLDO_IN", "GND", "VCAP1", "VCAP2", "VCAP3", "AVSS", "AVDD",
                "VREFP")
    unconnected_eco = []
    if drc_ok:
        for u in D.load(drc_path).get("unconnected_items", []):
            texts = [i.get("description", "") for i in u.get("items", [])]
            if any(("[%s]" % n) in t for n in eco_nets for t in texts):
                unconnected_eco.append(texts)

    # Anything the geometry refused, collected in one place so S5 gets a work
    # list rather than having to read the logs.
    blocked = []
    for c in changes:
        if not c.get("ok"):
            blocked.append({"item": "%s/%s -> %s" % (c["ref"], c["pad"],
                                                     c["want"]),
                            "kind": "net change",
                            "why": c.get("reason")
                            or json.dumps(c.get("connect"))})
    for p in placed:
        if not p.get("ok"):
            blocked.append({"item": p["ref"], "kind": "new part placement",
                            "why": p.get("reason")
                            or json.dumps(p.get("pad2_connect")),
                            "rejects": p.get("rejects")})
    for s in swaps:
        if not s.get("ok"):
            blocked.append({"item": s["ref"], "kind": "ECO-3 footprint swap",
                            "why": s.get("reason")
                            or json.dumps(s.get("bridge")),
                            "rejects": s.get("rejects")})
    review = [{"item": p["ref"], "note": p[k]}
              for p in placed for k in ("review", "review_route") if p.get(k)]
    review += [{"item": s["ref"], "note": s["review"]}
               for s in swaps if s.get("review")]

    checks = [
        E.gate_check("net_changes_applied", len(NET_CHANGES),
                     sum(1 for c in changes if c.get("ok"))),
        E.gate_check("new_parts_placed", len(NEW_PARTS),
                     sum(1 for p in placed if p.get("ok"))),
        E.gate_check("footprint_swaps", len(FOOTPRINT_SWAPS),
                     sum(1 for s in swaps if s.get("ok"))),
        E.gate_check("vcap_nets_exist", ["VCAP2", "VCAP3"],
                     [n for n in ("VCAP2", "VCAP3") if n in nets_after]),
        E.gate_check("pad_net_map_matches_contract", 0, len(diffs)),
        E.gate_check("component_count", contract["components"],
                     after_counts["footprints"] - len(mech)),
        E.gate_check("all_parts_have_lcsc", 0, len(fields["no_table_entry"])),
        E.gate_check("drc_ran", True, drc_ok),
        E.gate_check("no_unconnected_on_eco_nets", 0, len(unconnected_eco)),
        E.gate_check("drc_no_new_failure_signatures", [],
                     cmp.get("new_signatures", ["drc did not run"]),
                     ok=(drc_ok and not cmp.get("new_signatures"))),
    ]

    E.write_gate(os.path.join(root, "gates", "S4.json"), "S4", checks,
                 notes="ECO-1/2/3 applied to the PCB. %d pin net changes, "
                       "%d new parts, %d footprint swaps. DRC after: %s"
                       % (len(NET_CHANGES), len(NEW_PARTS),
                          len(FOOTPRINT_SWAPS),
                          json.dumps(drc_sum.get("errors_by_type", {}))),
                 extra={"net_changes": changes, "new_parts": placed,
                        "footprint_swaps": swaps, "fields": fields,
                        "contract_diffs": diffs[:80],
                        "mechanical_footprints": mech,
                        "counts_before": before_counts,
                        "counts_after": after_counts,
                        "nets_added": sorted(set(nets_after)
                                             - set(log["nets_before"])),
                        "drc_summary": drc_sum,
                        "drc_vs_baseline": cmp,
                        "unconnected_on_eco_nets": unconnected_eco[:20],
                        "blocked_needs_layout_work": blocked,
                        "placed_but_review": review})
    E.dump_json(os.path.join(root, "logs", "eco_apply.json"),
                {"net_changes": changes, "new_parts": placed,
                 "footprint_swaps": swaps, "fields": fields,
                 "contract_diffs": diffs})

    ok = all(c["pass"] for c in checks)
    print("S4 pass=%s (%d/%d checks)" % (ok, sum(c["pass"] for c in checks),
                                         len(checks)))
    print("  parts %d -> %d, tracks %d -> %d, vias %d -> %d"
          % (before_counts["footprints"], after_counts["footprints"],
             before_counts["tracks"], after_counts["tracks"],
             before_counts["vias"], after_counts["vias"]))
    if drc_sum:
        print("  DRC after ECO: %d violations = %d error + %d warning, "
              "unconnected %d" % (drc_sum["violations"], drc_sum["errors"],
                                  drc_sum["warnings"], drc_sum["unconnected"]))
        print("  errors by type: %s" % json.dumps(drc_sum["errors_by_type"]))
    if cmp:
        print("  vs baseline: %+d errors, %d new signatures, %d resolved"
              % (cmp["error_delta"], len(cmp["new_signatures"]),
                 len(cmp["resolved_signatures"])))
        for s in cmp["new_signatures"][:8]:
            print("     NEW %s" % s)
        for s in cmp.get("new_but_harmless", [])[:8]:
            print("     NEW but harmless (same-net mask aperture) %s" % s)
    for c in changes:
        if not c.get("ok"):
            print("  net change FAILED %s/%s -> %s: %s"
                  % (c["ref"], c["pad"], c["want"],
                     c.get("reason") or json.dumps(c.get("connect"))[:150]))
    for p in placed:
        if not p.get("ok"):
            print("  placement FAILED %s: %s"
                  % (p["ref"], p.get("reason")
                     or json.dumps(p.get("pad2_connect"))[:150]))
    for s in swaps:
        if not s.get("ok"):
            print("  swap FAILED %s: %s" % (s["ref"], s.get("reason")
                                            or json.dumps(s.get("bridge"))[:150]))
    for d in diffs[:12]:
        print("  CONTRACT DIFF %s" % json.dumps(d))
    for c in checks:
        if not c["pass"]:
            print("  FAIL %s: expected=%s actual=%s"
                  % (c["name"], json.dumps(c["expected"])[:80],
                     json.dumps(c["actual"])[:220]))
    for r in review:
        print("  REVIEW %s: %s" % (r["item"], r["note"]))
    for bl in blocked:
        print("  BLOCKED (%s) %s: %s" % (bl["kind"], bl["item"],
                                         str(bl["why"])[:200]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
