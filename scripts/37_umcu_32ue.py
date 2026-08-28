#!/usr/bin/env python3
"""S5_L8: U_MCU becomes an ESP32-WROOM-32UE -- the body shrinks 25.5 -> 19.2 mm.

    KPY scripts/37_umcu_32ue.py [--root .] [--dry-run] [--skip-drc]

Why
---
ACCEPTANCE H (scripts/64_body_overlap.py) fails on four pairs, all of them the
same fact: the ESP32-WROOM-32E's 25.5 mm outline reaches across the ADC.

    U_ADS         x U_MCU   -2.8124 mm
    C_AVDD1_10n   x U_MCU   -3.1384 mm
    C_DVDD_P40    x U_MCU   -1.6484 mm
    C_AVDD1_100n  x U_MCU   -0.8524 mm

6.3 mm of that 25.5 mm is the PCB antenna and its keep-out zone, at the -X end,
which is the end pointing at the ADS1299. The lead's decision (recorded in
data/bom_fixes_2026-08-28.json) is to fit the **ESP32-WROOM-32UE-N4**, LCSC
C701344, instead:

  * identical land pattern. Espressif's datasheet is explicit -- "The pin layout
    of ESP32-WROOM-32UE is the same as that of ESP32-WROOM-32E, except that
    ESP32-WROOM-32UE has no keepout zone" -- so all 38 pads stay exactly where
    they are and no copper moves. This script does not touch a single pad.
  * body 19.2 x 18 x 3.2 mm instead of 25.5 x 18 x 3.1 mm.
  * Rev.A talks to the host over USB-UART only, so the missing PCB antenna
    costs nothing. Espressif allows the RF pin to be left floating when the RF
    stack is never initialised; the 32UE's U.FL connector is simply unused.
  * JLC: C701344, stock 5,490, Extended, "Standard Only" -- the same assembly
    category the 32E was in, so the cart's Standard PCBA choice still holds.
    $3.95.

What changes on the board
-------------------------
Graphics only, and only on three layers of this one footprint:

    F.Fab     the four outline lines are redrawn on the 19.2 x 18 body; the
              small filled polygon that marks pin 1 travels with the corner it
              sits on rather than being deleted
    F.SilkS   the ten segments of the 25.5 mm outline (including the antenna
              keep-out line at local x -10.1925) are replaced by seven drawn on
              the new body, with the same 0.254 mm width and the same 0.206 mm
              gap the footprint already leaves where the outline would cross a
              pad row
    F.CrtYd   the rectangle becomes body + 0.25 mm

plus the fields Value / MPN / LCSC. Pads, nets, tracks, zones, the reference
field and the Dwgs.User pin-1 circle are untouched.

Where the body sits
-------------------
BODY_LOCAL below is the lead's measurement, in footprint-local millimetres:
x -9.945 .. +9.255, y -9.000 .. +9.000. It is 19.2 x 18.0 exactly, and it is
the *pessimistic* placement of the two you can defend:

    lead's placement          -9.945  .. +9.255   right edge board x 174.213
    old outline minus 6.3    -10.2275 .. +8.9725  right edge board x 173.9305

The second is what you get by deleting the keep-out from the 32E outline this
footprint already carries; the first is 0.2825 mm further east. Everything to
the west -- U_ADS and the three capacitors -- clears by 3.4 mm or more either
way, so the choice only matters at the east edge, where R_IO2_DN's and
R_IO15_DN's pad 1 sit: 0.0022 mm clear under the lead's placement, 0.2847 mm
under the other. Taking the pessimistic one means the question gets asked
rather than assumed away; scripts/38_nudge_io_pulldowns.py measures it.

The JLC_3D_Size property still reads "25.5 18" and JLC_3DModel_Q still names the
32E's model. Both are EasyEDA metadata for a 3D preview, neither is read by
anything in this pipeline, and neither has a 32UE value that could be filled in
honestly from here -- so they are left alone and recorded here instead. The
authority on the body is F.Fab, which is what ACCEPTANCE H measures.

Idempotent: on a board that already carries the 19.2 mm body it re-measures,
re-gates and saves nothing.
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import route as R                                  # noqa: E402
import drc as D                                    # noqa: E402

REF = "U_MCU"
OLD_VALUE = "ESP32-WROOM-32E-N4"
NEW_VALUE = "ESP32-WROOM-32UE-N4"
NEW_MPN = "ESP32-WROOM-32UE-N4"
OLD_LCSC = "C701341"
NEW_LCSC = "C701344"

# The 32UE body in footprint-local mm (x0, y0, x1, y1). See the docstring.
BODY_LOCAL = (-9.945, -9.000, 9.255, 9.000)
BODY_MM = (19.2, 18.0)
COURTYARD_MM = 0.25

# Line widths, taken from what the footprint already uses on each layer.
FAB_W_MM = 0.051
SILK_W_MM = 0.254
CRTYD_W_MM = 0.05
# The gap this footprint's own silkscreen leaves between a pad's bounding box
# and the end of a silk segment -- measured off the 32E outline being replaced
# (its top-right segment ends at local 8.1885 against pad 25's edge at 7.9825).
SILK_PAD_GAP_MM = 0.206

# Measured and reported every run; the first four are the ACCEPTANCE H failures
# this swap exists to clear, the last two are the parts at the other end.
NEIGHBOURS = ("U_ADS", "C_AVDD1_100n", "C_AVDD1_10n", "C_DVDD_P40",
              "R_IO2_DN", "R_IO15_DN")

EXPECTED_SILK_SEGMENTS = 7


def box_gap(a, b):
    """Separation of two axis-aligned boxes; negative when they overlap."""
    dx = max(a[0] - b[2], b[0] - a[2])
    dy = max(a[1] - b[3], b[1] - a[3])
    if dx >= 0 and dy >= 0:
        return math.hypot(dx, dy)
    return max(dx, dy)


def shapes_on(fp, layers):
    return [d for d in fp.GraphicalItems()
            if d.GetClass() == "PCB_SHAPE" and d.GetLayer() in layers]


def pad_box(fp):
    xs, ys = [], []
    for p in fp.Pads():
        bb = p.GetBoundingBox()
        xs += [bb.GetLeft(), bb.GetRight()]
        ys += [bb.GetTop(), bb.GetBottom()]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def free_spans(lo, hi, blocked):
    """[lo, hi] minus the intervals in `blocked`, merged, in order."""
    out = []
    cur = lo
    for a, b in sorted(blocked):
        if b <= cur:
            continue
        if a > cur:
            out.append((cur, min(a, hi)))
        cur = max(cur, b)
        if cur >= hi:
            break
    if cur < hi:
        out.append((cur, hi))
    return [(a, b) for a, b in out if b - a > 0]


def silk_segments(fp, box, gap):
    """The four body edges, minus wherever a pad row crosses them.

    Derived from the pads rather than written down, so the outline cannot end
    up drawn across a castellation if the land pattern is ever regenerated.
    The numbers it produces on this board are the same ones the 32E outline
    used at its own corners: local -9.6835 / 8.1885 on the top and bottom
    edges, -6.396 / 6.396 on the right one.
    """
    x0, y0, x1, y1 = box
    pads = [p.GetBoundingBox() for p in fp.Pads()]
    out = []
    for edge, const, lo, hi in (("top", y0, x0, x1), ("bottom", y1, x0, x1)):
        blocked = [(bb.GetLeft() - gap, bb.GetRight() + gap) for bb in pads
                   if bb.GetTop() - gap <= const <= bb.GetBottom() + gap]
        for a, b in free_spans(lo, hi, blocked):
            out.append(((a, const), (b, const), edge))
    for edge, const, lo, hi in (("left", x0, y0, y1), ("right", x1, y0, y1)):
        blocked = [(bb.GetTop() - gap, bb.GetBottom() + gap) for bb in pads
                   if bb.GetLeft() - gap <= const <= bb.GetRight() + gap]
        for a, b in free_spans(lo, hi, blocked):
            out.append(((const, a), (const, b), edge))
    return out


def add_line(pcbnew, fp, a, b, layer, width):
    s = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_SEGMENT)
    s.SetLayer(layer)
    s.SetWidth(int(width))
    fp.Add(s)
    s.SetStart(pcbnew.VECTOR2I(int(a[0]), int(a[1])))
    s.SetEnd(pcbnew.VECTOR2I(int(b[0]), int(b[1])))
    return s


def add_rect(pcbnew, fp, box, layer, width):
    s = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_RECT)
    s.SetLayer(layer)
    s.SetWidth(int(width))
    s.SetFilled(False)
    fp.Add(s)
    s.SetStart(pcbnew.VECTOR2I(int(box[0]), int(box[1])))
    s.SetEnd(pcbnew.VECTOR2I(int(box[2]), int(box[3])))
    return s


def describe_shape(board, d):
    bb = d.GetBoundingBox()
    return {"layer": board.GetLayerName(d.GetLayer()), "shape": d.ShowShape(),
            "start_mm": [P.mm(d.GetStart().x), P.mm(d.GetStart().y)],
            "end_mm": [P.mm(d.GetEnd().x), P.mm(d.GetEnd().y)],
            "bbox_mm": [P.mm(bb.GetLeft()), P.mm(bb.GetTop()),
                        P.mm(bb.GetRight()), P.mm(bb.GetBottom())],
            "width_mm": P.mm(d.GetWidth()),
            "uuid": d.m_Uuid.AsString()}


def field(fp, key):
    try:
        return fp.GetField(key).GetText() if fp.HasField(key) else None
    except Exception:
        return None


def set_field(pcbnew, fp, key, value):
    """Same convention as 45_apply_eco5_and_bom.py: hidden, on Cmts.User."""
    fp.SetField(key, value)
    f = fp.GetField(key)
    f.SetVisible(False)
    f.SetLayer(pcbnew.Cmts_User)


def outline_rect(shapes):
    """The rectangle the outline lines draw, from their endpoints.

    Not their bounding box: that is fattened by half the stroke width on every
    side, so a 19.2 mm body measures 19.251 mm and no size assertion can be
    written against the datasheet.
    """
    xs, ys = [], []
    for d in shapes:
        if d.ShowShape() == "Polygon":
            continue
        for pt in (d.GetStart(), d.GetEnd()):
            xs.append(pt.x)
            ys.append(pt.y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def measure(pcbnew, board, fp, others):
    """Body box, and how far it is from the parts this swap is about."""
    box = R.body_box(pcbnew, fp)
    rect = outline_rect(shapes_on(fp, (pcbnew.F_Fab,)))
    rec = {"body_mm": [P.mm(v) for v in box],
           "outline_rect_mm": [P.mm(v) for v in rect] if rect else None,
           "body_size_mm": [round(P.mm(rect[2] - rect[0]), 4),
                            round(P.mm(rect[3] - rect[1]), 4)]
           if rect else None,
           "to_bodies_mm": {}, "to_pads_mm": {}}
    for ref, other in sorted(others.items()):
        obox = R.body_box(pcbnew, other)
        if obox:
            rec["to_bodies_mm"][ref] = round(P.mm(box_gap(box, obox)), 4)
        pbox = pad_box(other)
        if pbox:
            rec["to_pads_mm"][ref] = round(P.mm(box_gap(box, pbox)), 4)
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-drc", action="store_true")
    ap.add_argument("--baseline", default="drc_s5_l7",
                    help="logs/<name>.json to compare the DRC signatures with")
    a = ap.parse_args()
    root = a.root

    import pcbnew
    bpath = P.board_path(root)
    board = pcbnew.LoadBoard(bpath)
    log = {"step": "L8", "ref": REF,
           "part": {"from": {"value": OLD_VALUE, "lcsc": OLD_LCSC},
                    "to": {"value": NEW_VALUE, "mpn": NEW_MPN,
                           "lcsc": NEW_LCSC}}}

    fp = board.FindFootprintByReference(REF)
    if fp is None:
        P.gate(root, "S5_L8", [P.check("footprint found", REF, None)],
               notes="%s is not on the board" % REF, extra=log)
        return 1
    if abs(fp.GetOrientationDegrees()) > 1e-6:
        # Every coordinate below is in board millimetres reached by adding the
        # footprint origin, which is only the same as the local frame at rot 0.
        log["error"] = ("%s is rotated %.3f deg; this script only knows the "
                        "rot 0 frame the board has always had"
                        % (REF, fp.GetOrientationDegrees()))
        P.gate(root, "S5_L8", [P.check("footprint at rot 0", 0.0,
                                       fp.GetOrientationDegrees())],
               notes=log["error"], extra=log)
        print(log["error"])
        return 1

    others = {r: board.FindFootprintByReference(r) for r in NEIGHBOURS}
    others = {r: f for r, f in others.items() if f is not None}
    origin = fp.GetPosition()
    target = (int(round(origin.x + BODY_LOCAL[0] * P.IU)),
              int(round(origin.y + BODY_LOCAL[1] * P.IU)),
              int(round(origin.x + BODY_LOCAL[2] * P.IU)),
              int(round(origin.y + BODY_LOCAL[3] * P.IU)))
    court = (target[0] - int(COURTYARD_MM * P.IU),
             target[1] - int(COURTYARD_MM * P.IU),
             target[2] + int(COURTYARD_MM * P.IU),
             target[3] + int(COURTYARD_MM * P.IU))
    log["origin_mm"] = [P.mm(origin.x), P.mm(origin.y)]
    log["body_local_mm"] = list(BODY_LOCAL)
    log["body_target_mm"] = [P.mm(v) for v in target]
    log["courtyard_target_mm"] = [P.mm(v) for v in court]

    fab = shapes_on(fp, (pcbnew.F_Fab,))
    silk = shapes_on(fp, (pcbnew.F_SilkS,))
    crtyd = shapes_on(fp, (pcbnew.F_CrtYd,))
    counts_before = P.counts(board, pcbnew)
    log["counts_before"] = counts_before
    log["before"] = measure(pcbnew, board, fp, others)
    log["before"].update({
        "value": fp.GetValue(), "mpn": field(fp, "MPN"),
        "lcsc": field(fp, "LCSC"),
        "shapes": {"F.Fab": len(fab), "F.SilkS": len(silk),
                   "F.CrtYd": len(crtyd)},
        "pads": len(list(fp.Pads())),
        "fab_outline": [describe_shape(board, d) for d in fab],
        "silk_outline": [describe_shape(board, d) for d in silk],
        "courtyard": [describe_shape(board, d) for d in crtyd]})
    log["kept_metadata"] = {
        "JLC_3D_Size": field(fp, "JLC_3D_Size"),
        "JLC_3DModel_Q": field(fp, "JLC_3DModel_Q"),
        "footprint": fp.GetFPIDAsString(),
        "why": "EasyEDA 3D-preview metadata and the land-pattern name. The "
               "land pattern is shared by the 32E and the 32UE, and neither "
               "property is read by anything in this pipeline; F.Fab is what "
               "ACCEPTANCE H measures. Recorded rather than edited."}

    outline = [d for d in fab if d.ShowShape() != "Polygon"]
    markers = [d for d in fab if d.ShowShape() == "Polygon"]
    old_fab = outline_rect(outline)
    already = (old_fab is not None
               and all(abs(old_fab[i] - target[i]) <= 1000 for i in range(4))
               and fp.GetValue() == NEW_VALUE
               and field(fp, "LCSC") == NEW_LCSC)
    log["already_swapped"] = already

    made = []
    if not already:
        # --- F.Fab: redraw the outline, carry the pin-1 marker with it -------
        dx = target[0] - old_fab[0] if old_fab else 0
        for d in markers:
            d.Move(pcbnew.VECTOR2I(int(dx), 0))
        log["pin1_marker_moved_mm"] = [P.mm(dx), 0.0]
        log["removed_shapes"] = [describe_shape(board, d)
                                 for d in outline + silk + crtyd]
        for d in outline + silk + crtyd:
            # Delete, not Remove: Remove only detaches, and SWIG then reports
            # a leak per item on stdout because the proxy does not own it --
            # which lands in the middle of this script's JSON output.
            fp.Delete(d)
        for a_pt, b_pt in ((target[0:2], (target[2], target[1])),
                           ((target[2], target[1]), target[2:4]),
                           (target[2:4], (target[0], target[3])),
                           ((target[0], target[3]), target[0:2])):
            made.append(add_line(pcbnew, fp, a_pt, b_pt, pcbnew.F_Fab,
                                 FAB_W_MM * P.IU))
        # --- F.SilkS: the same edges, broken where the pads cross ------------
        segs = silk_segments(fp, target, int(SILK_PAD_GAP_MM * P.IU))
        log["silk_segments"] = [
            {"edge": e, "start_mm": [P.mm(s[0]), P.mm(s[1])],
             "end_mm": [P.mm(t[0]), P.mm(t[1])],
             "length_mm": round(P.mm(math.hypot(t[0] - s[0], t[1] - s[1])), 4)}
            for s, t, e in segs]
        for s, t, _edge in segs:
            made.append(add_line(pcbnew, fp, s, t, pcbnew.F_SilkS,
                                 SILK_W_MM * P.IU))
        # --- F.CrtYd ---------------------------------------------------------
        made.append(add_rect(pcbnew, fp, court, pcbnew.F_CrtYd,
                             CRTYD_W_MM * P.IU))
        # --- fields ----------------------------------------------------------
        fp.SetValue(NEW_VALUE)
        set_field(pcbnew, fp, "MPN", NEW_MPN)
        set_field(pcbnew, fp, "LCSC", NEW_LCSC)

    log["after"] = measure(pcbnew, board, fp, others)
    log["after"].update({
        "value": fp.GetValue(), "mpn": field(fp, "MPN"),
        "lcsc": field(fp, "LCSC"),
        "pads": len(list(fp.Pads())),
        "shapes": {"F.Fab": len(shapes_on(fp, (pcbnew.F_Fab,))),
                   "F.SilkS": len(shapes_on(fp, (pcbnew.F_SilkS,))),
                   "F.CrtYd": len(shapes_on(fp, (pcbnew.F_CrtYd,)))},
        "fab_outline": [describe_shape(board, d)
                        for d in shapes_on(fp, (pcbnew.F_Fab,))],
        "silk_outline": [describe_shape(board, d)
                         for d in shapes_on(fp, (pcbnew.F_SilkS,))],
        "courtyard": [describe_shape(board, d)
                      for d in shapes_on(fp, (pcbnew.F_CrtYd,))]})
    counts_after = P.counts(board, pcbnew)
    log["counts_after"] = counts_after
    log["unconnected_before_save"] = P.unconnected_count(pcbnew, board)
    diffs, _mech = P.contract_diff(board, pcbnew, root)
    log["contract_diffs"] = diffs[:20]

    if a.dry_run:
        print(json.dumps(log, indent=1))
        return 0
    if not already:
        pcbnew.SaveBoard(bpath, board)

    drc_ok, cur, sig = False, None, {}
    if not a.skip_drc:
        drc_ok, cur, _p = P.drc_with_healing(root, "s5_l8", log=log)
        if drc_ok:
            base = P.load_baseline(root, a.baseline)
            if base is not None:
                sig = D.compare(base, cur)
                log["drc_signature"] = sig
            log["drc_after"] = {"errors_by_type": P.by_type(cur),
                                "unconnected": P.unconnected(cur)}

    after = log["after"]
    size = after["body_size_mm"]
    silk_n = after["shapes"]["F.SilkS"]
    checks = [
        P.check("body size", list(BODY_MM), size),
        P.check("body rectangle", [round(P.mm(v), 4) for v in target],
                after["outline_rect_mm"],
                note="from the outline's endpoints. The F.Fab bounding box "
                     "ACCEPTANCE H reads is %s -- wider by half the 0.051 mm "
                     "stroke and by the pin-1 marker at the west corner"
                     % after["body_mm"]),
        P.check("pads untouched", log["before"]["pads"], after["pads"]),
        P.check("value", NEW_VALUE, after["value"]),
        P.check("MPN", NEW_MPN, after["mpn"]),
        P.check("LCSC", NEW_LCSC, after["lcsc"]),
        P.check("silk segments", EXPECTED_SILK_SEGMENTS, silk_n),
        P.check("courtyard is body + %.2f mm" % COURTYARD_MM,
                [round(P.mm(v), 4) for v in court],
                (after["courtyard"][0]["start_mm"]
                 + after["courtyard"][0]["end_mm"]) if after["courtyard"]
                else None),
        P.check("no body overlaps U_ADS or the three capacitors", [],
                sorted(r for r in ("U_ADS", "C_AVDD1_100n", "C_AVDD1_10n",
                                   "C_DVDD_P40")
                       if after["to_bodies_mm"].get(r, 1.0) < 0)),
        P.check("contract parity", 0, len(diffs)),
        P.check("copper unchanged", counts_before, counts_after,
                note="this script adds and removes graphics only -- no pad, "
                     "track, via or zone is created, moved or deleted"),
        P.check("unconnected", 0, log["unconnected_before_save"]),
    ]
    if not a.skip_drc:
        checks += [
            P.check("drc ran", True, drc_ok),
            P.check("drc errors", 0,
                    sum(P.by_type(cur).values()) if cur else -1,
                    ok=(drc_ok and not P.by_type(cur))),
            P.check("drc unconnected", 0, P.unconnected(cur) if cur else -1,
                    ok=(drc_ok and P.unconnected(cur) == 0)),
            P.check("no new drc signatures", [],
                    sig.get("new_signatures", ["drc did not run"]),
                    ok=(drc_ok and not sig.get("new_signatures"))),
        ]

    head = ("%s already carries the %.1f x %.1f mm body; nothing to redraw."
            % (REF, BODY_MM[0], BODY_MM[1])) if already else (
        "%s: %s -> %s (%s -> %s). The 25.5 mm outline is replaced by the "
        "19.2 x 18 one on F.Fab, F.SilkS and F.CrtYd; no pad, net or track "
        "moved." % (REF, OLD_VALUE, NEW_VALUE, OLD_LCSC, NEW_LCSC))
    P.gate(root, "S5_L8", checks,
           notes="%s Body gaps now: %s. The four ACCEPTANCE H failures under "
                 "the 32E outline are cleared; the east end is measured "
                 "separately by 38_nudge_io_pulldowns.py."
                 % (head, ", ".join("%s %.4f mm" % kv for kv in
                                    sorted(after["to_bodies_mm"].items()))),
           extra=log)
    bad = [c["name"] for c in checks if not c["pass"]]
    print("S5_L8: %s" % ("pass" if not bad else "FAIL " + ", ".join(bad)))
    for c in checks:
        print("  %-1s %-48s %s" % ("" if c["pass"] else "!", c["name"],
                                   "ok" if c["pass"] else
                                   "expected %r got %r" % (c["expected"],
                                                           c["actual"])))
    print("  body %s -> %s" % (log["before"]["body_mm"], after["body_mm"]))
    for ref in sorted(after["to_bodies_mm"]):
        print("  %-14s body %8.4f -> %8.4f mm   pads %8.4f -> %8.4f mm"
              % (ref, log["before"]["to_bodies_mm"][ref],
                 after["to_bodies_mm"][ref],
                 log["before"]["to_pads_mm"][ref], after["to_pads_mm"][ref]))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
