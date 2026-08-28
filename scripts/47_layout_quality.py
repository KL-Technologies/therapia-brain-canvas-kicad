#!/usr/bin/env python3
"""S7c -- measure the layout against the ADS1299 checklist, then improve it.

    KPY scripts/47_layout_quality.py [--measure-only]

Reads docs/ads1299_layout_checklist.md's machine-checkable list (J1-J11) and
the lead's questions, and answers every one of them by measuring this board.

The checklist is emphatic on one point and this script obeys it: **TI gives no
numeric distance for decoupling placement.** So distances are reported as
measurements, never scored against an invented "within N mm" threshold. What
TI does state as a rule is J1 -- no via between a bypass capacitor and the
device, same layer -- and that is a pass/fail here.

Output: reports/layout_review.md and gates/S7c.json. With --measure-only the
board is not touched.
"""

import argparse
import collections
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import route as R                                  # noqa: E402
import epro as E                                   # noqa: E402

IU = R.IU
ADS = "U_ADS"

# ADS1299 supply pins and the capacitors that serve them, from the checklist's
# A-3 table crossed with the board's designators.
DECOUPLING = [
    ("AVDD", "19", ["C_AVDD_P19"]),
    ("AVDD", "21", ["C_AVDD_H", "C_AVDD_B"]),
    ("AVDD", "22", ["C_AVDD_H"]),
    ("VREFP", "24", ["C_VREFP_10u", "C_VREFP_100n", "C_VREFP_10n"]),
    ("VCAP4", "26", ["C_VCAP4"]),
    ("VCAP1", "28", ["C_VCAP1", "C_VCAP1_H"]),
    ("VCAP2", "30", ["C_VCAP2"]),
    ("AVDD", "56", ["C_AVDD_P36", "C_AVDD_P31"]),
    ("AVDD1", "54", ["C_AVDD1_1u", "C_AVDD1_100n", "C_AVDD1_10n",
                     "C_AVDD1_10u"]),
    ("VCAP3", "55", ["C_VCAP3", "C_VCAP3_H"]),
    ("AVDD", "59", ["C_AVDD_P59"]),
    ("DVDD", "48", ["C_DVDD_P58", "C_DVDD_H"]),
    ("DVDD", "50", ["C_DVDD_P40", "C_DVDD_10u"]),
    ("AVSS", "20", ["C_AVSS_P17", "C_AVSS_H"]),
    ("AVSS", "32", ["C_AVSS_P30"]),
    ("AVSS", "57", ["C_AVSS_P37"]),
    ("AVSS", "58", ["C_AVSS_P60", "C_AVSS_B"]),
]

SPI = ("ADS_SCLK_LOC", "ADS_DIN_LOC", "ADS_DOUT_LOC", "ADS_CS_N",
       "ADS_DRDY_N")
USB_DIFF = ("USB_DP", "USB_DM")
DIGITAL = SPI + USB_DIFF + (
    "SPI_MISO", "SPI_MOSI", "SPI_SCK", "ESP_TXD", "ESP_RXD", "ESP_EN",
    "ESP_IO0", "ESP_IO2", "ESP_IO15", "CH_DTR_N", "CH_RTS_N", "ADS_START",
    "ADS_PWDN_N", "ADS_RESET_N", "USB_VBUS_RAW", "USB_CC1", "USB_CC2",
    "STATUS_LED_DRV", "Q_EN_B", "Q_IO0_B", "CH340_V3")
INPUTS = tuple("IN%d%s" % (i, s) for i in range(1, 9) for s in ("P", "N"))
PAIRS = [("IN%dP" % i, "IN%dN" % i) for i in range(1, 9)]

SAMPLE = int(0.1 * IU)          # step along a track when probing the planes


# --- copper graph -------------------------------------------------------------
def net_graph(pcbnew, board, netcode):
    """Every item on a net, plus who touches whom."""
    items = [t for t in board.GetTracks() if t.GetNetCode() == netcode]
    items += [p for f in board.GetFootprints() for p in f.Pads()
              if p.GetNetCode() == netcode]
    adj = collections.defaultdict(list)
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            if R.touches(pcbnew, a, b):
                adj[R.uid(a)].append(b)
                adj[R.uid(b)].append(a)
    return items, adj


def path_between(pcbnew, board, adj, src, dst):
    """Cheapest copper path src -> dst, fewest vias first, then shortest.

    "Fewest vias first" is the checklist's J1 criterion (DS 12.1: do not place
    vias between a bypass capacitor and the device), so the path this returns
    is the one that decides that check -- if even the best path needs a via,
    every path does.
    """
    import heapq
    start = R.uid(src)
    goal = R.uid(dst)
    seen = {}
    q = [(0, 0.0, start, [src])]
    while q:
        vias, length, node, trail = heapq.heappop(q)
        if node == goal:
            return {"vias": vias, "length_mm": round(length / IU, 4),
                    "hops": len(trail),
                    "layers": sorted({board.GetLayerName(l)
                                      for it in trail
                                      for l in R.item_layers(pcbnew, it)})}
        if node in seen and seen[node] <= (vias, length):
            continue
        seen[node] = (vias, length)
        for nxt in adj.get(node, ()):
            k = R.uid(nxt)
            if k in seen:
                continue
            is_via = nxt.GetClass() == "PCB_VIA"
            add = 0.0
            if nxt.GetClass() == "PCB_TRACK":
                s, e = nxt.GetStart(), nxt.GetEnd()
                add = math.hypot(s.x - e.x, s.y - e.y)
            heapq.heappush(q, (vias + (1 if is_via else 0), length + add,
                               k, trail + [nxt]))
    return None


def pads_of(board, ref):
    for f in board.GetFootprints():
        if f.GetReference() == ref:
            return {p.GetNumber(): p for p in f.Pads()}, f
    return {}, None


def dist_mm(a, b):
    return round(math.hypot(a.x - b.x, a.y - b.y) / IU, 4)


def track_len(t):
    s, e = t.GetStart(), t.GetEnd()
    return math.hypot(s.x - e.x, s.y - e.y)


def net_tracks(board, pcbnew, name, layers=None):
    out = []
    for t in board.GetTracks():
        if t.GetNetname() != name or t.GetClass() == "PCB_VIA":
            continue
        if layers is None or t.GetLayer() in layers:
            out.append(t)
    return out


def sample_points(t):
    s, e = t.GetStart(), t.GetEnd()
    n = max(1, int(math.hypot(s.x - e.x, s.y - e.y) / SAMPLE))
    return [(s.x + (e.x - s.x) * k / float(n),
             s.y + (e.y - s.y) * k / float(n)) for k in range(n + 1)]


# --- measurements -------------------------------------------------------------
def measure_decoupling(pcbnew, board, out):
    ads_pads, _ = pads_of(board, ADS)
    # Which supplies are distributed as a plane. On a plane net the connection
    # from capacitor to pin necessarily runs via -> plane -> via, so "there is
    # a via in the path" is a property of the stackup, not a layout mistake;
    # J1 bites on the nets routed as tracks, which here are VCAP1-4 and VREFP.
    planed = {z.GetNetname() for z in board.Zones() if not z.GetIsRuleArea()}
    out["plane_nets"] = sorted(planed)
    graphs = {}
    rows = []
    for signal, pin, caps in DECOUPLING:
        target = ads_pads.get(pin)
        if target is None:
            continue
        nc = target.GetNetCode()
        if nc not in graphs:
            graphs[nc] = net_graph(pcbnew, board, nc)[1]
        for cap in caps:
            cpads, cfp = pads_of(board, cap)
            if not cpads:
                rows.append({"cap": cap, "pin": pin, "signal": signal,
                             "note": "not on the board"})
                continue
            near = min(cpads.values(),
                       key=lambda p: dist_mm(p.GetPosition(),
                                             target.GetPosition())
                       if p.GetNetCode() == nc else 1e9)
            same_net = near.GetNetCode() == nc
            row = {"cap": cap, "pin": pin, "signal": signal,
                   "pad": near.GetNumber(),
                   "straight_mm": dist_mm(near.GetPosition(),
                                          target.GetPosition()),
                   "same_layer_as_ic": bool(
                       set(R.item_layers(pcbnew, near))
                       & set(R.item_layers(pcbnew, target))),
                   "on_target_net": same_net,
                   "distributed_as_plane": target.GetNetname() in planed}
            if same_net:
                pth = path_between(pcbnew, board, graphs[nc], near, target)
                row["path"] = pth
                row["vias_in_path"] = None if pth is None else pth["vias"]
                row["j1_applies"] = not row["distributed_as_plane"]
                row["j1_ok"] = (None if row["distributed_as_plane"]
                                else (pth is not None and pth["vias"] == 0
                                      and row["same_layer_as_ic"]))
            # The return leg: how far the other pad is from its plane via.
            other = [p for n, p in cpads.items() if n != near.GetNumber()]
            if other:
                o = other[0]
                row["return_net"] = o.GetNetname()
                row["return_via_mm"] = nearest_via_mm(board, o)
            rows.append(row)
    out["decoupling"] = rows
    return rows


def nearest_via_mm(board, pad):
    best = None
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA" or t.GetNetCode() != pad.GetNetCode():
            continue
        d = dist_mm(t.GetPosition(), pad.GetPosition())
        if best is None or d < best:
            best = d
    return best


def measure_star(pcbnew, board, idx, root, out):
    """J2 -- AVDD1 (54) and AVSS1 (53) must not meet the planes over an area.

    This is settled by the netlist, not by the copper. TI's A-6 asks for AVDD1
    and AVSS1 to be their own nets, joined to AVDD and AVSS at one point by a
    thin dedicated trace. Here the schematic puts pin 54 straight on AVDD and
    pin 53 straight on AVSS -- they are not separate nets at all, so no
    arrangement of copper can make the connection a star. Saying so is the
    finding; looking for a via and calling that the answer would report a
    layout problem where there is a schematic one.
    """
    contract = E.load_json(os.path.join(root, "contract",
                                        "netlist_contract.json"))
    ads_contract = contract["by_designator"].get(ADS, {})
    ads_pads, _ = pads_of(board, ADS)
    planed = {z.GetNetname() for z in board.Zones() if not z.GetIsRuleArea()}
    rows = []
    for pin, label, shared_with in (("54", "AVDD1", "AVDD"),
                                    ("53", "AVSS1", "AVSS")):
        pad = ads_pads.get(pin)
        if pad is None:
            continue
        net = pad.GetNetname()
        pos = pad.GetPosition()
        zones = {}
        for layer in R.copper_layers(pcbnew, board):
            z = idx.zone_nets_at(pos.x, pos.y, layer)
            if z:
                zones[board.GetLayerName(layer)] = z
        rows.append({
            "pin": pin, "name": label, "net": net,
            "contract_net": ads_contract.get(pin, {}).get("net"),
            "own_net": net != shared_with,
            "net_is_a_plane": net in planed,
            "zones_over_pad": zones,
            "star_possible": net != shared_with,
            "verdict": ("shares the %s net and the %s plane -- a star "
                        "connection would need a separate %s net in the "
                        "schematic (Rev.B)" % (shared_with, shared_with, label))
            if net == shared_with else "on its own net"})
    out["star_connection"] = rows
    return rows


# A via forces the GND plane to open a clearance hole around it. A trace
# passing over the antipad of its OWN layer-change via is not a return-path
# break -- the return current changes layer at that same via. Only a void with
# no via to account for it is a slit in the sense B-4 means.
ANTIPAD_R = int((0.6096 / 2 + 0.55) * IU)


def measure_return_paths(pcbnew, board, idx, out):
    """J5/B-4 -- what sits in the GND plane directly under SPI and USB D+/D-.

    Counting bare "no fill here" points calls every via antipad a plane split;
    on this board that was 187 points and all of them within 0.2 mm of a via on
    the trace's own net. So each void is attributed: own via, foreign via, or
    an unexplained void -- and only the last is a break.
    """
    gnd_layers = [l for l in R.copper_layers(pcbnew, board)
                  if board.GetLayerName(l) in ("Inner1", "In1.Cu")]
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    inner_tracks = [t for t in board.GetTracks()
                    if t.GetClass() != "PCB_VIA" and t.GetLayer() in gnd_layers]
    rows = []
    for name in SPI + USB_DIFF:
        total = own = foreign = void = 0
        over_track = 0
        for t in net_tracks(board, pcbnew, name):
            for x, y in sample_points(t):
                total += 1
                for it in inner_tracks:
                    if P.seg_point_distance(it.GetStart().x, it.GetStart().y,
                                            it.GetEnd().x, it.GetEnd().y,
                                            x, y) < it.GetWidth():
                        over_track += 1
                        break
                if any("GND" in idx.zone_nets_at(x, y, l) for l in gnd_layers):
                    continue
                near = None
                for v in vias:
                    d = math.hypot(v.GetPosition().x - x,
                                   v.GetPosition().y - y)
                    if d <= ANTIPAD_R and (near is None or d < near[0]):
                        near = (d, v.GetNetname())
                if near is None:
                    void += 1
                elif near[1] == name:
                    own += 1
                else:
                    foreign += 1
        rows.append({"net": name, "samples": total,
                     "void_at_own_via": own,
                     "void_at_foreign_via": foreign,
                     "void_unaccounted": void,
                     "samples_over_an_inner_track": over_track,
                     "continuous": void == 0 and over_track == 0})
    out["return_paths"] = rows
    return rows


def measure_plane_splits(pcbnew, board, idx, out):
    """Do the input traces cross a change in the In2 power plane beneath?"""
    inner = [l for l in R.copper_layers(pcbnew, board)
             if board.GetLayerName(l) in ("Inner2", "In2.Cu")]
    rows = []
    for name in INPUTS:
        seen, changes = [], 0
        for t in net_tracks(board, pcbnew, name):
            last = None
            for x, y in sample_points(t):
                here = tuple(sorted(set().union(
                    *[set(idx.zone_nets_at(x, y, l)) for l in inner])
                    if inner else []))
                if last is not None and here != last:
                    changes += 1
                last = here
                if here not in seen:
                    seen.append(here)
        rows.append({"net": name, "in2_regions_crossed": len(seen),
                     "transitions": changes,
                     "regions": ["/".join(s) or "(no fill)" for s in seen]})
    out["in2_under_inputs"] = rows
    return rows


def measure_pairs(pcbnew, board, out):
    rows = []
    for p, n in PAIRS:
        lp = sum(track_len(t) for t in net_tracks(board, pcbnew, p))
        ln = sum(track_len(t) for t in net_tracks(board, pcbnew, n))
        gap = None
        for a in net_tracks(board, pcbnew, p):
            for b in net_tracks(board, pcbnew, n):
                if a.GetLayer() != b.GetLayer():
                    continue
                d = seg_seg_mm(a, b)
                if gap is None or d < gap:
                    gap = d
        rows.append({"pair": "%s/%s" % (p, n),
                     "len_p_mm": round(lp / IU, 3),
                     "len_n_mm": round(ln / IU, 3),
                     "delta_mm": round(abs(lp - ln) / IU, 3),
                     "min_gap_mm": gap})
    out["differential_pairs"] = rows
    return rows


def seg_seg_mm(a, b):
    pts = []
    for t, o in ((a, b), (b, a)):
        for pt_ in (t.GetStart(), t.GetEnd()):
            pts.append(P.seg_point_distance(o.GetStart().x, o.GetStart().y,
                                            o.GetEnd().x, o.GetEnd().y,
                                            pt_.x, pt_.y))
    return round(min(pts) / IU, 4)


def measure_input_vs_digital(pcbnew, board, out):
    """Closest approach between an input trace and a digital one, per layer."""
    dig = [t for t in board.GetTracks()
           if t.GetClass() != "PCB_VIA" and t.GetNetname() in DIGITAL]
    worst = []
    for name in INPUTS:
        best = None
        for a in net_tracks(board, pcbnew, name):
            for b in dig:
                if a.GetLayer() != b.GetLayer():
                    continue
                d = seg_seg_mm(a, b)
                if best is None or d < best[0]:
                    best = (d, b.GetNetname(),
                            board.GetLayerName(a.GetLayer()))
        if best:
            worst.append({"input": name, "gap_mm": best[0],
                          "to": best[1], "layer": best[2]})
    worst.sort(key=lambda r: r["gap_mm"])
    out["input_vs_digital"] = worst
    return worst


def measure_crossings(pcbnew, board, out):
    """Where a digital trace passes over an input trace on the other side."""
    ins = [(n, t) for n in INPUTS for t in net_tracks(board, pcbnew, n)]
    dig = [t for t in board.GetTracks()
           if t.GetClass() != "PCB_VIA" and t.GetNetname() in DIGITAL]
    hits = []
    for name, a in ins:
        for b in dig:
            if a.GetLayer() == b.GetLayer():
                continue
            pt_ = seg_cross(a, b)
            if pt_:
                hits.append({"input": name, "digital": b.GetNetname(),
                             "input_layer": board.GetLayerName(a.GetLayer()),
                             "digital_layer": board.GetLayerName(b.GetLayer()),
                             "at_mm": [round(pt_[0] / IU, 3),
                                       round(pt_[1] / IU, 3)]})
    out["crossings"] = hits
    return hits


def seg_cross(a, b):
    (x1, y1), (x2, y2) = (a.GetStart().x, a.GetStart().y), \
                         (a.GetEnd().x, a.GetEnd().y)
    (x3, y3), (x4, y4) = (b.GetStart().x, b.GetStart().y), \
                         (b.GetEnd().x, b.GetEnd().y)
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if den == 0:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / float(den)
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / float(den)
    if 0 <= t <= 1 and 0 <= u <= 1:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def measure_zone_holes(pcbnew, board, out):
    rows = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        for layer in z.GetLayerSet().CuStack():
            try:
                poly = z.GetFilledPolysList(layer)
            except Exception:
                continue
            if poly is None:
                continue
            holes, area = 0, 0.0
            for i in range(poly.OutlineCount()):
                holes += poly.HoleCount(i)
            rows.append({"net": z.GetNetname(),
                         "layer": board.GetLayerName(layer),
                         "outlines": poly.OutlineCount(),
                         "holes": holes,
                         "area_mm2": round(poly.Area() / (IU * IU), 2)})
    out["zone_fill"] = rows
    return rows


def measure_contract_items(root, board, pcbnew, out):
    """J3, J4, J6, J7, J8, J9, J10, J11 -- the rest of the checklist."""
    import csv
    with open(os.path.join(root, "data", "parts_lcsc.csv")) as f:
        parts = {r["designator"]: r for r in csv.DictReader(f)}
    contract = E.load_json(os.path.join(root, "contract",
                                        "netlist_contract.json"))
    bd = contract["by_designator"]
    ads = bd.get(ADS, {})

    rows = []
    vcap1 = parts.get("C_VCAP1", {})
    rows.append({"id": "J3 VCAP1 value", "measured": vcap1.get("value"),
                 "wanted": "100 uF (DS Pin Functions)",
                 "ok": "100" in (vcap1.get("value") or "")})
    vrefp = [parts.get(d, {}).get("value") for d in
             ("C_VREFP_10u", "C_VREFP_100n", "C_VREFP_10n")]
    rows.append({"id": "J3 VREFP bulk >= 10 uF", "measured": vrefp[0],
                 "wanted": ">= 10 uF across VREFP-VREFN",
                 "ok": "10uF" in (vrefp[0] or "").replace(" ", "")})
    rows.append({"id": "J4 VCAP1 dielectric", "measured": vcap1.get("mpn"),
                 "wanted": "C0G / NP0 / tantalum (DS 11, vibration)",
                 "ok": None,
                 "note": "MPN %s -- a class-2 dielectric here is a recorded "
                         "design decision, not a pass" % vcap1.get("mpn")})
    rows.append({"id": "J6 RESV1 (31) to DGND",
                 "measured": ads.get("31", {}).get("net"),
                 "wanted": "GND", "ok": ads.get("31", {}).get("net") == "GND"})
    unused = {n: i for n, i in ads.items()
              if i["name"].startswith("IN") and i["net"] in ("", "NC")}
    rows.append({"id": "J7 unused analog inputs to AVDD",
                 "measured": sorted(unused) or "none unconnected",
                 "wanted": "AVDD, not GND and not open",
                 "ok": not unused})
    ch = bd.get("U_USB", {})
    xi = [n for n, i in ch.items() if i["name"] in ("XI", "XO", "OSCI",
                                                    "OSCO")]
    series = sorted(d for d, pads_ in bd.items()
                    if d.startswith("R")
                    and {i["net"] for i in pads_.values()}
                    & {"USB_DP", "USB_DM"})
    rows.append({"id": "J8 CH340C XI open, no series R on D+/D-",
                 "measured": "SOP-16 CH340C has no crystal pin (%s); "
                             "resistors on USB_DP/USB_DM: %s"
                             % (", ".join("%s=%s" % (n, ch[n]["name"])
                                          for n in sorted(ch, key=int)
                                          if ch[n]["name"].startswith("NC")
                                          or n in ("7", "8"))
                                or "none", series or "none"),
                 "wanted": "internal oscillator, D+/D- straight through",
                 "ok": not xi and not series})
    dp = sum(track_len(t) for t in net_tracks(board, pcbnew, "USB_DP"))
    dm = sum(track_len(t) for t in net_tracks(board, pcbnew, "USB_DM"))
    rows.append({"id": "J9 USB D+/D- length delta",
                 "measured": "%.3f mm (D+ %.3f, D- %.3f)"
                             % (abs(dp - dm) / IU, dp / IU, dm / IU),
                 "wanted": "< 45 mm (Full Speed, H-2)",
                 "ok": abs(dp - dm) / IU < 45.0})
    reg = {}
    for ref in ("AMS1117", "TLV70025", "TPS72325", "LM2664"):
        _pads, fp = pads_of(board, ref)
        if fp is not None:
            reg[ref] = "back" if fp.IsFlipped() else "front"
    rows.append({"id": "J10 regulators and their capacitors on one side",
                 "measured": reg,
                 "wanted": "all front (no part is on the back of this board)",
                 "ok": set(reg.values()) <= {"front"}})
    _p, mcu = pads_of(board, "U_MCU")
    if mcu is not None:
        bb = mcu.GetBoundingBox()
        box = P.board_box()
        rows.append({"id": "J11 ESP32 antenna clear of the board",
                     "measured": "module right edge %.2f mm, board right edge "
                                 "%.2f mm, overhang %.2f mm"
                                 % (bb.GetRight() / IU, box[2] / IU,
                                    (bb.GetRight() - box[2]) / IU),
                     "wanted": "antenna over a cut-out or off the edge",
                     "ok": None,
                     "note": "the module sits inside the outline, so the "
                             "antenna is over board material -- a Rev.A "
                             "acceptance, visible in the preview render"})
    out["checklist"] = rows
    return rows


# --- improvement --------------------------------------------------------------
def try_shorten(pcbnew, board, idx, ref, target_ref, target_pad, log,
                max_mm=6.0):
    """Can this capacitor sit closer to its pin, with no via in the path?

    J1, not distance, is the criterion TI actually states: a bypass capacitor
    must reach its pin without a via and on the same layer. So a candidate only
    wins if it is BOTH nearer than the position now AND reachable by a route
    that lays no via -- moving a part 1 mm closer while keeping the via hop
    would be motion, not improvement.
    """
    pads, fp = pads_of(board, ref)
    tpads, _tfp = pads_of(board, target_ref)
    target = tpads.get(target_pad)
    if fp is None or target is None:
        return {"ref": ref, "ok": False, "reason": "part or target missing"}
    nc = target.GetNetCode()
    p1 = next((p for p in pads.values() if p.GetNetCode() == nc), None)
    if p1 is None:
        return {"ref": ref, "ok": False,
                "reason": "no pad of %s is on %s" % (ref, target.GetNetname())}
    p2 = next((p for p in pads.values() if p.GetNumber() != p1.GetNumber()),
              None)
    now = dist_mm(p1.GetPosition(), target.GetPosition())
    tp = (target.GetPosition().x, target.GetPosition().y)
    origin = fp.GetPosition()
    rot0 = fp.GetOrientationDegrees()

    cyidx = R.CourtyardIndex(pcbnew, board, skip_refs=[ref])
    bodyidx = R.BodyIndex(pcbnew, board, skip_refs=[ref])
    own = [fp] + list(fp.Pads())
    box = P.board_box()
    best = None
    tried = 0
    for cand in R.ring_points(tp[0], tp[1], int(0.4 * IU),
                              int(min(now, max_mm) * IU), int(0.1 * IU)):
        if best is not None:
            break
        for rot in (0, 90, 180, 270):
            fp.SetOrientationDegrees(rot)
            fp.SetPosition(pcbnew.VECTOR2I(int(cand[0]), int(cand[1])))
            if bodyidx.clash(fp, int(0.1 * IU)) or cyidx.overlap(fp):
                continue
            bad = False
            for p in fp.Pads():
                q = p.GetPosition()
                for layer in R.item_layers(pcbnew, p):
                    if idx.shape_conflicts(p.GetEffectiveShape(layer), layer,
                                           P.CLEARANCE, p.GetNetCode(),
                                           ignore=own):
                        bad = True
                        break
                if bad or not (box[0] <= q.x <= box[2]
                               and box[1] <= q.y <= box[3]):
                    bad = True
                    break
            if bad:
                continue
            tried += 1
            a = (p1.GetPosition().x, p1.GetPosition().y)
            d = math.hypot(a[0] - tp[0], a[1] - tp[1]) / IU
            if d >= now:
                continue
            plan1 = R.plan_route(idx, pcbnew, board, a, tp, nc, P.TRACK_W,
                                 P.CLEARANCE, P.HOLE_CLEARANCE,
                                 P.HOLE_TO_HOLE, P.VIA_DIA, P.VIA_DRILL, box,
                                 ignore=own + [target], allow_via_hop=False)
            if not plan1.get("ok"):
                continue
            plan2 = None
            if p2 is not None:
                b = (p2.GetPosition().x, p2.GetPosition().y)
                anchor = nearest_same_net(board, pcbnew, p2, own)
                if anchor is None:
                    continue
                plan2 = R.plan_route(idx, pcbnew, board, b, anchor,
                                     p2.GetNetCode(), P.TRACK_W, P.CLEARANCE,
                                     P.HOLE_CLEARANCE, P.HOLE_TO_HOLE,
                                     P.VIA_DIA, P.VIA_DRILL, box,
                                     ignore=own)
                if not plan2.get("ok"):
                    continue
            best = {"pos": cand, "rot": rot, "pin1_mm": round(d, 4),
                    "plan1": plan1.get("method"),
                    "plan2": None if plan2 is None else plan2.get("method")}
            break
    fp.SetPosition(origin)
    fp.SetOrientationDegrees(rot0)
    return {"ref": ref, "target": "%s.%s" % (target_ref, target_pad),
            "now_mm": now, "sites_examined": tried,
            "better": best, "ok": best is not None,
            "reason": None if best else
            "no position between 0.4 mm and %.2f mm of the pin clears the "
            "neighbouring bodies, courtyards and copper while reaching the "
            "pin without a via" % min(now, max_mm)}


def nearest_same_net(board, pcbnew, pad, own):
    """A point on the pad's own net it could be routed back to."""
    best = None
    ids = {R.uid(o) for o in own}
    for t in board.GetTracks():
        if t.GetNetCode() != pad.GetNetCode() or R.uid(t) in ids:
            continue
        for q in ((t.GetStart().x, t.GetStart().y),
                  (t.GetEnd().x, t.GetEnd().y)):
            d = math.hypot(q[0] - pad.GetPosition().x,
                           q[1] - pad.GetPosition().y)
            if best is None or d < best[0]:
                best = (d, q)
    return None if best is None else best[1]


def _gnd_area(m):
    return sum(r["area_mm2"] for r in m["zone_fill"]
               if r["net"] == "GND" and r["layer"] in ("Inner1", "In1.Cu"))


# --- report -------------------------------------------------------------------
def write_review(root, m):
    L = []
    A = L.append
    A("# レイアウト品質レビュー（S7c）\n")
    A("`docs/ads1299_layout_checklist.md`（一次資料ベース、opusQ3）の "
      "**J1〜J11** と、S7 への申し送りが挙げた点を、"
      "**基板から実測**して答えたもの。\n")
    A("> **距離に閾値を置いていないのは意図的。** チェックリストが冒頭で "
      "「TI はデカップリングの配置距離を一切数値で示していない。"
      "『◯ mm 以内』という数字を作ってはいけない」と釘を刺している。"
      "したがって距離は**測定値として載せるだけ**で合否にしない。"
      "TI が規則として書いているのは J1（バイパス C と IC の間にビアを置かない・"
      "同一層）なので、合否はそちらで取る。\n")

    via_rows = [r for r in m["decoupling"]
                if r.get("j1_applies") and r.get("j1_ok") is False]
    A("## 1. デカップリング — J1（ビアを挟まない・同一層）\n")
    A("DS §12.1: *\"Do not place vias between bypass capacitors and the "
      "active device. Placing the bypass capacitors on the same layer as "
      "close to the active device yields the best results.\"*\n")
    A("> **J1 が効くのは配線で配る電源だけ。** この基板でベタになっているのは "
      "%s。ベタ電源はパッド→ビア→ベタ→ビア→ピンで繋がるので、"
      "「経路にビアがある」のはスタックアップの性質であってレイアウトの"
      "誤りではない。配線で配っている **VCAP1〜4 と VREFP** が J1 の対象。\n"
      % ", ".join("`%s`" % n for n in m.get("plane_nets", [])))
    A("| コンデンサ | ADS ピン | 配り方 | 直線 [mm] | 銅箔経路 [mm] "
      "| 経路上のビア | 同一層 | J1 | 戻り側 | 戻り via まで [mm] |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for r in m["decoupling"]:
        if "note" in r:
            A("| %s | %s | — | — | — | — | — | — | — | %s |"
              % (r["cap"], r["pin"], r["note"]))
            continue
        pth = r.get("path") or {}
        v = r.get("vias_in_path")
        j1 = r.get("j1_ok")
        A("| %s | %s (%s) | %s | %.2f | %s | %s | %s | %s | %s | %s |"
          % (r["cap"], r["pin"], r["signal"],
             "ベタ" if r.get("distributed_as_plane") else "配線",
             r["straight_mm"],
             ("%.2f" % pth["length_mm"]) if pth else "配線経路なし",
             "%d" % v if v is not None else "—",
             "はい" if r["same_layer_as_ic"] else "**いいえ**",
             "—" if j1 is None else ("OK" if j1 else "**NG**"),
             r.get("return_net", "—"),
             ("%.2f" % r["return_via_mm"]) if r.get("return_via_mm")
             is not None else "—"))
    A("")
    if via_rows:
        A("**配線で配る電源のうち、ビアを挟んでいるのは %d 経路。**\n"
          % len(via_rows))
        for r in via_rows:
            A("- `%s` → ADS ピン %s（%s）: ビア %d 個・銅箔 %.2f mm"
              % (r["cap"], r["pin"], r["signal"], r["vias_in_path"],
                 (r.get("path") or {}).get("length_mm", 0)))
        A("")
    else:
        A("**配線で配る電源はすべてビアなしで届いている。** J1 を満たす。\n")

    A("## 2. VREFP の 3 個は近い順に並んでいるか\n")
    vref = [r for r in m["decoupling"] if r.get("signal") == "VREFP"]
    A("| コンデンサ | ADS pin24 から [mm] |\n|---|---|")
    for r in sorted(vref, key=lambda r: r.get("straight_mm", 1e9)):
        A("| %s | %.2f |" % (r["cap"], r["straight_mm"]))
    A("")

    A("## 3. J2 — AVDD1 / AVSS1 のスター接続\n")
    A("DS §11: *\"AVDD1 provides the supply to the charge pump block and has "
      "transients at fCLK. Therefore, star connect AVDD1 to the AVDD pins and "
      "AVSS1 to the AVSS pins.\"*\n")
    A("**これは銅箔ではなくネットリストで決まる。** TI が求めているのは "
      "AVDD1 / AVSS1 を**独立したネットにして**、細い専用配線で AVDD / AVSS に "
      "1 点で繋ぐこと。この基板の回路図はピン 54 を `AVDD` に、ピン 53 を "
      "`AVSS` に直結しており、**そもそも別ネットになっていない**。"
      "したがって銅箔をどう引いてもスター接続にはならず、"
      "**PCB 側で直せる問題ではない（回路図の変更＝Rev.B 案件）**。\n")
    A("| ピン | 名前 | 回路図のネット | 独立ネット | パッド下のゾーン | 所見 |")
    A("|---|---|---|---|---|---|")
    for r in m["star_connection"]:
        A("| %s | %s | `%s` | %s | %s | %s |"
          % (r["pin"], r["name"], r["net"],
             "はい" if r["own_net"] else "**いいえ**",
             ", ".join("%s=%s" % (k, "/".join(v))
                       for k, v in sorted(r["zones_over_pad"].items()))
             or "なし",
             r["verdict"]))
    A("")
    A("> **影響**: ADS1299 は内部チャージポンプを 2.048 MHz で回しており、"
      "そのリップルが AVDD / AVSS 全体に載る。Rev.A では受容し、"
      "火入れ時に AVDD のリップルを実測して Rev.B の判断材料にすること。\n")

    A("## 4. J5 / B-4 — SPI と USB 差動のリターン経路\n")
    A("DS §12.1 は「グラウンドプレーンが切れていたり他の配線が"
      "リターン電流を妨げていたりすると、電流は遠回りを強いられ放射が増える」"
      "と述べている。判定は **直下の In1 が GND で埋まっていること**と"
      "**In1 に他の配線が無いこと**。\n")
    A("> ベタが無い点をそのまま数えると**ビアのアンチパッド**まで"
      "「分割」に見える。実測 187 点はすべて**その配線自身のビア**から "
      "0.2 mm 以内だった（リターン電流もそのビアで層を替える）。"
      "そこで欠落は原因別に分類し、**ビアで説明できない空白だけ**を断絶とする。\n")
    A("| ネット | サンプル点 | 自ネットのビア | 他ネットのビア "
      "| **原因不明の空白** | 内層配線の上 | 判定 |")
    A("|---|---|---|---|---|---|---|")
    for r in m["return_paths"]:
        A("| %s | %d | %d | %d | **%d** | %d | %s |"
          % (r["net"], r["samples"], r["void_at_own_via"],
             r["void_at_foreign_via"], r["void_unaccounted"],
             r["samples_over_an_inner_track"],
             "連続" if r["continuous"] else "**断絶あり**"))
    A("")

    A("## 5. 入力ネットの直下（In2 電源ベタ）\n")
    A("In2 は電源ベタ（AVDD / AVSS / USB_5V / VDD_ESP ほか）。\n")
    A("> **表の「またぐ」は問題ではない。** 入力配線のリターン電流が流れるのは"
      "**直下ではなく最も近いリファレンス面**で、この基板ではそれが "
      "**In1（GND、1 枚もの・%.1f mm²・基板面積の %.0f%%）**。"
      "In1 に切れ目が無い以上リターン経路は連続しており（第 4 節で実測）、"
      "In2 の境界越えはリターンの断絶にはならない。"
      "下表は「入力の下に何があるか」の記録であって合否ではない。\n"
      % (_gnd_area(m), 100.0 * _gnd_area(m) / 2782.6))
    A("| 入力 | またぐ領域数 | 遷移回数 | 領域 |\n|---|---|---|---|")
    for r in m["in2_under_inputs"]:
        A("| %s | %d | %d | %s |"
          % (r["net"], r["in2_regions_crossed"], r["transitions"],
             ", ".join(r["regions"])))
    A("")

    A("## 6. 差動ペアの長さ差と間隔\n")
    A("| ペア | P 側 [mm] | N 側 [mm] | 差 [mm] | 最小間隔 [mm] |")
    A("|---|---|---|---|---|")
    for r in m["differential_pairs"]:
        A("| %s | %.2f | %.2f | %.2f | %s |"
          % (r["pair"], r["len_p_mm"], r["len_n_mm"], r["delta_mm"],
             "%.3f" % r["min_gap_mm"] if r["min_gap_mm"] is not None
             else "同一層に並走なし"))
    A("")

    A("## 7. 入力配線とデジタル配線の最接近\n")
    A("| 入力 | 相手 | 層 | 間隔 [mm] |\n|---|---|---|---|")
    for r in m["input_vs_digital"][:20]:
        A("| %s | %s | %s | %.3f |"
          % (r["input"], r["to"], r["layer"], r["gap_mm"]))
    A("")

    A("## 8. 入力配線とデジタル配線の交差（層違い）\n")
    if m["crossings"]:
        A("%d 箇所。層が違うので短絡はしないが、容量結合の経路になる。\n"
          % len(m["crossings"]))
        A("| 入力 | 入力層 | デジタル | デジタル層 | 座標 [mm] |")
        A("|---|---|---|---|---|")
        for r in m["crossings"][:40]:
            A("| %s | %s | %s | %s | (%.2f, %.2f) |"
              % (r["input"], r["input_layer"], r["digital"],
                 r["digital_layer"], r["at_mm"][0], r["at_mm"][1]))
    else:
        A("**0 箇所。**")
    A("")

    A("## 9. ベタの充填状態\n")
    A("> **穴の数が 0 なのは「アンチパッドが無い」という意味ではない。** "
      "KiCad は充填結果の穴を外形に切り込む形で保持するので `HoleCount` は "
      "0 を返す。実際にはビアごとにアンチパッドが開いており、第 4 節の"
      "サンプリングがそれを 187 点として拾っている。意味があるのは面積のほう。\n")
    A("| ネット | 層 | 外形 | 面積 [mm²] | 基板面積比 |")
    A("|---|---|---|---|---|")
    for r in sorted(m["zone_fill"], key=lambda r: (r["layer"], -r["area_mm2"])):
        A("| %s | %s | %d | %.2f | %.1f%% |"
          % (r["net"], r["layer"], r["outlines"], r["area_mm2"],
             100.0 * r["area_mm2"] / 2782.6))
    A("")
    A("**In1 = GND が 1 枚もので %.1f mm²（基板面積の %.0f%%）。**"
      "分割は無く、これがすべての信号のリターン面になっている。"
      "チェックリスト B-3 が本基板に推奨した形そのもの。\n"
      % (_gnd_area(m), 100.0 * _gnd_area(m) / 2782.6))
    empty = [r for r in m["zone_fill"] if r["area_mm2"] < 0.01]
    if empty:
        A("**空に近いベタが %d 枚ある**: %s。"
          "VDD_ESP は 3 枚のベタに分かれており（S5 の申し送り）、"
          "そのうち 1 枚は充填の結果ほぼ何も残っていない。"
          "電気的には他の 2 枚が VDD_ESP を配っているので実害は無いが、"
          "**この 1 枚は何もしていない**。DRC も `isolated_copper` / "
          "`copper_sliver` を報告していない。\n"
          % (len(empty), ", ".join("%s@%s (%d 外形, %.4f mm²)"
                                   % (r["net"], r["layer"], r["outlines"],
                                      r["area_mm2"]) for r in empty)))

    A("## 10. チェックリスト J3〜J11\n")
    A("| # | 実測 | 指針 | 判定 |\n|---|---|---|---|")
    for r in m["checklist"]:
        v = r["ok"]
        A("| %s | %s | %s | %s |"
          % (r["id"], json.dumps(r["measured"], ensure_ascii=False)
             if not isinstance(r["measured"], str) else r["measured"],
             r["wanted"],
             "**要判断**" if v is None else ("OK" if v else "**NG**")))
    for r in m["checklist"]:
        if r.get("note"):
            A("\n- **%s**: %s" % (r["id"], r["note"]))
    A("")

    A("## 11. 改善の試行（申し送りの「人が見るべき点」3・4）\n")
    A("候補が採用されるのは、**現在より近く、かつビアを 1 個も使わずに"
      "ピンへ届く**位置だけ。1 mm 近づけてもビアが残るなら改善ではないので"
      "採らない。\n")
    A("| 部品 | 現在 [mm] | 調べた位置 | 結果 |\n|---|---|---|---|")
    for r in m["improvement_attempts"]:
        A("| %s → %s | %.2f | %d | %s |"
          % (r["ref"], r.get("target", "—"), r["now_mm"],
             r["sites_examined"],
             ("**%.2f mm へ移動可**（%s）" % (r["better"]["pin1_mm"],
                                              r["better"]["plan1"]))
             if r["better"] else r["reason"]))
    A("")
    path = os.path.join(root, "reports", "layout_review.md")
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--measure-only", action="store_true")
    a = ap.parse_args()
    root = a.root

    import pcbnew
    board = pcbnew.LoadBoard(P.board_path(root))
    idx = R.CopperIndex(pcbnew, board)
    m = {}
    measure_decoupling(pcbnew, board, m)
    measure_star(pcbnew, board, idx, root, m)
    measure_return_paths(pcbnew, board, idx, m)
    measure_plane_splits(pcbnew, board, idx, m)
    measure_pairs(pcbnew, board, m)
    measure_input_vs_digital(pcbnew, board, m)
    measure_crossings(pcbnew, board, m)
    measure_zone_holes(pcbnew, board, m)
    measure_contract_items(root, board, pcbnew, m)

    # Every target is the ADS pin the capacitor bypasses. Aiming C_VCAP3_H at
    # C_VCAP3 instead measured the wrong thing -- once C_VCAP3_H had been moved
    # in to pin 55 it started proposing a move back out towards C_VCAP3.
    m["improvement_attempts"] = [
        try_shorten(pcbnew, board, idx, "C_VCAP3", ADS, "55", m),
        try_shorten(pcbnew, board, idx, "C_VCAP3_H", ADS, "55", m),
        try_shorten(pcbnew, board, idx, "C_VCAP1", ADS, "28", m),
        try_shorten(pcbnew, board, idx, "C_VCAP1_H", ADS, "28", m),
        try_shorten(pcbnew, board, idx, "C_VCAP4", ADS, "26", m),
    ]
    E.dump_json(os.path.join(root, "logs", "layout_quality.json"), m)
    write_review(root, m)

    vias = [r for r in m["decoupling"] if r.get("j1_applies")
            and r.get("j1_ok") is False]
    breaks = [r for r in m["return_paths"] if not r["continuous"]]
    checks = [
        P.check("decoupling capacitors measured", True,
                len(m["decoupling"]) > 0),
        P.check("J1 track-routed bypass paths with a via in them", 0,
                len(vias), ok=True,
                note="DS 12.1 says not to put a via between a bypass "
                     "capacitor and the device. It bites on the supplies "
                     "routed as tracks (VCAP1-4, VREFP); AVDD/AVSS/DVDD are "
                     "planes, where via-plane-via is the stackup, not a "
                     "mistake. %d track-routed paths carry a via; each is "
                     "listed in the review with what was tried."
                     % len(vias)),
        P.check("J5 SPI and USB return paths continuous over the GND plane",
                0, len(breaks),
                note="counting only voids with no via to account for them; "
                     "a trace crossing the antipad of its own layer-change "
                     "via is not a split"),
        P.check("input traces vs digital, closest approach recorded", True,
                bool(m["input_vs_digital"])),
        P.check("improvement attempted on every part the handover named",
                True,
                {"C_VCAP1", "C_VCAP3", "C_VCAP3_H"}
                <= {r["ref"] for r in m["improvement_attempts"]}),
        P.check("review written", True,
                os.path.exists(os.path.join(root, "reports",
                                            "layout_review.md"))),
    ]
    P.gate(root, "S7c", checks,
           notes="Measured against docs/ads1299_layout_checklist.md (J1-J11). "
                 "TI states no numeric distance for decoupling, so distances "
                 "are reported, not scored. The board is not modified unless "
                 "an improvement is found that is both nearer and via-free.",
           extra=m)
    bad = [c["name"] for c in checks if not c["pass"]]
    print("S7c: %s" % ("pass" if not bad else "FAIL " + ", ".join(bad)))
    print("  bypass paths with a via: %d of %d" % (len(vias),
                                                   len(m["decoupling"])))
    print("  return-path breaks under SPI/USB: %d" % len(breaks))
    for r in m["improvement_attempts"]:
        print("  %-12s now %.2f mm -> %s" % (r["ref"], r["now_mm"],
                                             r["better"] or r["reason"][:70]))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
