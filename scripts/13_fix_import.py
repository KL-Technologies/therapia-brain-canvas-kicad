#!/usr/bin/env python3
"""S4a: repair the three things the EasyEDA importer could not carry across.

All three are recorded by S2 in gates/design_observations.json. None of them is
lost data -- the geometry is present, it just landed in the wrong kind of object:

  1. the four M2 mounting holes arrive as PTH pads (drill == size, no net), so
     they end up in the PLATED drill file and DRC never treats them as holes
  2. the two USB-C positioning pegs arrive as Edge.Cuts polygons owned by J1.
     EasyEDA stores them as FILL records with a CIRCLE path on layer 12 (Multi),
     which maps to Edge.Cuts, so the position and size are right but they are
     milled slots rather than drilled NPTH -- they never reach the drill file
  3. the board outline arrives as THREE open segments. EasyEDA holds it as one
     closed POLY (["POLY", ..., 11, 4, [0,0,"L",2434,0,2434,-1772,0,-1772], 0])
     and the importer emits a segment per vertex pair without closing the loop.
     That is the single invalid_outline error in logs/drc_import.json, and an
     open outline makes copper_edge_clearance and zone fill meaningless.

Nothing here changes copper. Idempotent in content: a second run leaves every
object identical, though KiCad's own writer may reorder footprints in the
s-expression, so the file is not guaranteed byte-identical.
Must run under the KiCad-bundled python (needs pcbnew).
"""

import os
import sys
import json
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import epro as E                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD_NAME = "Therapia_EEG-HRV"
IU = 1000000                                   # nm per mm

# EasyEDA board outline: POLY on layer 11, path 0,0 -> 2434,0 -> 2434,-1772 ->
# 0,-1772 (mil). KiCad shifted the origin to (120, 80) mm; y flips sign.
BOARD_ORIGIN_MM = (120.0, 80.0)
OUTLINE_MIL = (2434, 1772)
EDGE_WIDTH_NM = 101600                         # 4 mil, as EasyEDA drew it

# The six NPTH holes, in EasyEDA coordinates (mm, y negative downward) exactly
# as cerelog_research/fab_2026-08-16/.../Drill_NPTH_Through.DRL lists them.
# reference -> (easyeda_x, easyeda_y, diameter)
NPTH_SPEC = [
    ("PEG1", 56.861075, -33.877885, 0.700024),
    ("PEG2", 56.861075, -28.097861, 0.700024),
    ("H1",    3.048,     -3.048,    2.387600),
    ("H2",   56.9468,    -3.048,    2.387600),
    ("H3",    3.048,    -41.9608,   2.387600),
    ("H4",   56.9468,   -41.9608,   2.387600),
]
PEG_REFS = ("PEG1", "PEG2")
M2_REFS = ("H1", "H2", "H3", "H4")

OLD_DRL_ZIP = os.path.join(
    os.path.dirname(ROOT), "cerelog_research", "fab_2026-08-16",
    "Therapia_EEG-HRV_Gerber.zip")
OLD_DRL_MEMBER = "Drill_NPTH_Through.DRL"

DRILL_TOL_MM = 0.002                           # +-2 um, per ACCEPTANCE.md D


def to_kicad(x_mm, y_mm):
    """EasyEDA (x, y) mm -> KiCad (x + 120, -y + 80) mm. See README 'Units'."""
    return (x_mm + BOARD_ORIGIN_MM[0], -y_mm + BOARD_ORIGIN_MM[1])


def nm(v_mm):
    return int(round(float(v_mm) * IU))


def npth_layer_set(pcbnew):
    """The layer set KiCad's own MountingHole_*.kicad_mod uses: *.Cu + *.Mask.

    With size == drill this leaves no annular ring, so no copper is plotted --
    the Cu layers only mark the hole as passing through the stack.
    """
    ls = pcbnew.LSET.AllCuMask()
    ls.addLayer(pcbnew.F_Mask)
    ls.addLayer(pcbnew.B_Mask)
    return ls


def shape_npth_pad(pcbnew, pad, dia_mm):
    pad.SetNumber("")
    pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_CIRCLE)
    pad.SetSize(pcbnew.VECTOR2I(nm(dia_mm), nm(dia_mm)))
    pad.SetDrillSize(pcbnew.VECTOR2I(nm(dia_mm), nm(dia_mm)))
    pad.SetLayerSet(npth_layer_set(pcbnew))
    pad.SetNetCode(0)
    return pad


def hide_texts(fp):
    for t in (fp.Reference(), fp.Value()):
        t.SetVisible(False)


def mech_attributes(pcbnew):
    return (pcbnew.FP_THROUGH_HOLE
            | pcbnew.FP_EXCLUDE_FROM_BOM
            | pcbnew.FP_EXCLUDE_FROM_POS_FILES)


# --- the three repairs -------------------------------------------------------
def fix_mounting_holes(board, pcbnew, log):
    """The M2 holes are single-pad footprints named Pad_<uuid> with no
    reference. Give them H1..H4, make the pad NPTH, drop it out of BOM/POS."""
    want = {r: to_kicad(x, y) + (d,) for r, x, y, d in NPTH_SPEC if r in M2_REFS}
    done = []
    for ref, (kx, ky, dia) in sorted(want.items()):
        fp = None
        for cand in board.GetFootprints():
            if cand.GetReference() == ref:
                fp = cand
                break
            if cand.GetReference():
                continue
            p = cand.GetPosition()
            if (E.approx(p.x / IU, kx, 0.01) and E.approx(p.y / IU, ky, 0.01)
                    and len(list(cand.Pads())) == 1):
                fp = cand
                break
        if fp is None:
            log.append({"step": "m2", "ref": ref, "result": "NOT FOUND"})
            continue
        fp.SetReference(ref)
        fp.SetValue("NPTH_%.4fmm_M2" % dia)
        fp.SetAttributes(mech_attributes(pcbnew))
        hide_texts(fp)
        pad = list(fp.Pads())[0]
        shape_npth_pad(pcbnew, pad, dia)
        pad.SetPosition(pcbnew.VECTOR2I(nm(kx), nm(ky)))
        done.append(ref)
        log.append({"step": "m2", "ref": ref, "kicad_mm": [kx, ky],
                    "dia_mm": dia, "result": "npth"})
    return done


def fix_pegs(board, pcbnew, log):
    """Delete the Edge.Cuts polygons J1 carries for the two 0.7 mm pegs and put
    real NPTH pads at the same centres, as standalone mechanical footprints.

    Standalone rather than pads added to J1: a footprint with its pad at local
    (0, 0) needs no relative-coordinate juggling, it matches how the M2 holes
    already sit on this board, and S5 can move a peg for the L4 repair without
    touching the connector."""
    want = {r: to_kicad(x, y) + (d,) for r, x, y, d in NPTH_SPEC if r in PEG_REFS}
    for ref, (kx, ky, dia) in sorted(want.items()):
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            fp = pcbnew.FOOTPRINT(board)
            fp.SetFPID(pcbnew.LIB_ID("", "NPTH_0.7mm_USB-C_peg"))
            board.Add(fp)
        fp.SetReference(ref)
        fp.SetValue("NPTH_%.4fmm_peg" % dia)
        fp.SetAttributes(mech_attributes(pcbnew))
        fp.SetPosition(pcbnew.VECTOR2I(nm(kx), nm(ky)))
        hide_texts(fp)
        pads = list(fp.Pads())                 # reuse, so the KIID is stable
        if pads:
            pad = pads[0]
        else:
            pad = pcbnew.PAD(fp)
            fp.Add(pad)
        shape_npth_pad(pcbnew, pad, dia)
        pad.SetPosition(pcbnew.VECTOR2I(nm(kx), nm(ky)))
        log.append({"step": "peg", "ref": ref, "kicad_mm": [kx, ky],
                    "dia_mm": dia, "result": "npth"})


def fix_edge_cuts(board, pcbnew, log):
    """Edge.Cuts must be exactly the four sides of the outline rectangle.

    Everything else on the layer goes: the J1 peg polygons (now real NPTH pads)
    and any partial segment the importer left behind. The rectangle is then
    redrawn at the exact EasyEDA dimensions -- the imported segments sit 100 nm
    and 200 nm off because the importer rounded 2434/1772 mil through a float."""
    # Collect first, delete after. Removing an item mid-walk invalidates the
    # SWIG proxies behind board.GetFootprints(), and BOARD::Remove() breaks
    # them outright -- RemoveNative() is the variant that leaves the type
    # information intact.
    removed, victims = [], []
    for fp in board.GetFootprints():
        for d in fp.GraphicalItems():
            if d.GetLayer() == pcbnew.Edge_Cuts:
                c = d.GetCenter()
                removed.append({"owner": fp.GetReference() or "(anon)",
                                "shape": int(d.GetShape()),
                                "center_mm": [c.x / IU, c.y / IU]})
                victims.append((fp, d))
    for fp, d in victims:
        fp.Remove(d)

    x0, y0 = BOARD_ORIGIN_MM
    x1 = x0 + OUTLINE_MIL[0] * E.MIL_TO_MM
    y1 = y0 + OUTLINE_MIL[1] * E.MIL_TO_MM
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    # Reuse the segments already on the layer instead of replacing them: a
    # fresh PCB_SHAPE would get a fresh KIID and the file would churn on every
    # run. Each side takes the existing segment whose midpoint is nearest to
    # it, so the mapping does not depend on the order GetDrawings() happens to
    # return.
    sides = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    pool = [d for d in board.GetDrawings()
            if d.GetLayer() == pcbnew.Edge_Cuts
            and int(d.GetShape()) == int(pcbnew.SHAPE_T_SEGMENT)]
    surplus = [d for d in board.GetDrawings()
               if d.GetLayer() == pcbnew.Edge_Cuts and d not in pool]
    taken = set()
    for i, (a, b) in enumerate(sides):
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        free = [j for j in range(len(pool)) if j not in taken]
        if not free:
            continue
        j = min(free, key=lambda k: abs(pool[k].GetCenter().x / IU - mid[0])
                + abs(pool[k].GetCenter().y / IU - mid[1]))
        taken.add(j)
        sides[i] = (a, b, pool[j])
    for d in surplus + [pool[j] for j in range(len(pool)) if j not in taken]:
        c = d.GetCenter()
        removed.append({"owner": "(board)", "shape": int(d.GetShape()),
                        "center_mm": [c.x / IU, c.y / IU]})
        board.RemoveNative(d)
    for i, side in enumerate(sides):
        a, b = side[0], side[1]
        if len(side) == 3:
            seg = side[2]
        else:
            seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
            board.Add(seg)
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(EDGE_WIDTH_NM)
        seg.SetStart(pcbnew.VECTOR2I(nm(a[0]), nm(a[1])))
        seg.SetEnd(pcbnew.VECTOR2I(nm(b[0]), nm(b[1])))
    log.append({"step": "edge_cuts", "removed": removed,
                "rectangle_mm": [[x0, y0], [x1, y1]],
                "size_mm": [round(x1 - x0, 4), round(y1 - y0, 4)]})
    return removed


# --- gate --------------------------------------------------------------------
def parse_excellon(text):
    """Minimal Excellon reader: tool diameters plus (x, y, tool) for every hit.

    Handles both the METRIC,LZ,00.000000 explicit-decimal form EasyEDA writes
    and the leading-zero-suppressed integer form KiCad writes, by looking at
    whether the coordinate token carries a '.'."""
    tools, holes = {}, []
    cur, metric, fmt_dec = None, True, 4
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("METRIC"):
            metric = True
            parts = line.split(",")
            for p in parts[1:]:
                if "." in p:
                    fmt_dec = len(p.split(".")[1])
            continue
        if line.startswith("INCH"):
            metric = False
            continue
        if line.startswith("T") and "C" in line:
            t, _, c = line.partition("C")
            try:
                tools[t] = float(c)
            except ValueError:
                pass
            continue
        if line.startswith("T") and line[1:].isdigit():
            cur = line
            continue
        if line.startswith("X") or line.startswith("Y"):
            vals = {}
            i = 0
            while i < len(line):
                if line[i] in "XY":
                    axis = line[i]
                    j = i + 1
                    while j < len(line) and (line[j].isdigit() or line[j] in "+-."):
                        j += 1
                    tok = line[i + 1:j]
                    if tok:
                        v = float(tok)
                        if "." not in tok:
                            v = v / (10.0 ** fmt_dec)
                        vals[axis] = v if metric else v * 25.4
                    i = j
                else:
                    i += 1
            if "X" in vals and "Y" in vals:
                holes.append({"x_mm": vals["X"], "y_mm": vals["Y"],
                              "tool": cur, "dia_mm": tools.get(cur)})
    return tools, holes


def read_reference_npth():
    """The 6 NPTH holes as the 2026-08-16 fab package shipped them."""
    import zipfile
    if not os.path.exists(OLD_DRL_ZIP):
        return None
    with zipfile.ZipFile(OLD_DRL_ZIP) as z:
        name = next((n for n in z.namelist()
                     if n.endswith(OLD_DRL_MEMBER)), None)
        if not name:
            return None
        _tools, holes = parse_excellon(z.read(name).decode("utf-8", "replace"))
    for h in holes:                            # into the KiCad frame
        h["x_mm"], h["y_mm"] = to_kicad(h["x_mm"], h["y_mm"])
    return holes


def export_drill(kc, board_path, outdir):
    if os.path.isdir(outdir):
        for f in os.listdir(outdir):
            os.remove(os.path.join(outdir, f))
    else:
        os.makedirs(outdir)
    cmd = [kc, "pcb", "export", "drill", "--format", "excellon",
           "--excellon-separate-th", "--drill-origin", "absolute",
           "--excellon-units", "mm", "--excellon-zeros-format", "decimal",
           "-o", outdir + os.sep, board_path]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p, sorted(os.listdir(outdir)) if os.path.isdir(outdir) else []


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--board")
    args = ap.parse_args()
    root = args.root
    board_path = args.board or os.path.join(root, "board", BOARD_NAME + ".kicad_pcb")

    try:
        import pcbnew
    except ImportError:
        print("pcbnew unavailable -- run this with the KiCad-bundled python (KPY)")
        return 2
    if not os.path.exists(board_path):
        print("board not found: %s (run 11_import_epro.py first)" % board_path)
        return 2

    board = pcbnew.LoadBoard(board_path)
    log = []

    before = {"npth_pads": 0, "pth_pads": 0, "vias": 0}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if max(p.GetDrillSize().x, p.GetDrillSize().y) <= 0:
                continue
            if int(p.GetAttribute()) == int(pcbnew.PAD_ATTRIB_NPTH):
                before["npth_pads"] += 1
            else:
                before["pth_pads"] += 1
    before["vias"] = sum(1 for t in board.GetTracks() if t.GetClass() == "PCB_VIA")

    fix_mounting_holes(board, pcbnew, log)
    fix_pegs(board, pcbnew, log)
    fix_edge_cuts(board, pcbnew, log)
    board.BuildListOfNets()

    # Measured before the save on purpose. pcbnew.SaveBoard() leaves the python
    # side holding bare SwigPyObjects, and a second pcbnew.LoadBoard() in the
    # same interpreter does the same, so neither can be walked afterwards. What
    # actually landed on disk is verified by the drill export further down,
    # which re-reads the file through kicad-cli.
    after = {"npth_pads": 0, "pth_pads": 0, "vias": 0, "copper_layers":
             board.GetCopperLayerCount()}
    npth_found = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if max(p.GetDrillSize().x, p.GetDrillSize().y) <= 0:
                continue
            if int(p.GetAttribute()) == int(pcbnew.PAD_ATTRIB_NPTH):
                after["npth_pads"] += 1
                npth_found.append({"ref": fp.GetReference(),
                                   "x_mm": p.GetPosition().x / IU,
                                   "y_mm": p.GetPosition().y / IU,
                                   "dia_mm": p.GetDrillSize().x / IU})
            else:
                after["pth_pads"] += 1
    after["vias"] = sum(1 for t in board.GetTracks() if t.GetClass() == "PCB_VIA")
    edge_segs = [d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
    fp_edge = sum(1 for fp in board.GetFootprints()
                  for d in fp.GraphicalItems() if d.GetLayer() == pcbnew.Edge_Cuts)
    pcbnew.SaveBoard(board_path, board)

    # ---- gate -------------------------------------------------------------
    kc = os.environ.get("KC", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
    outdir = os.path.join(root, "fab", "drill_check")
    proc, files = export_drill(kc, board_path, outdir)
    npth_file = next((f for f in files if "NPTH" in f.upper()), None)
    pth_file = next((f for f in files if "PTH" in f.upper() and f != npth_file), None)
    drl_holes, drl_tools = [], {}
    if npth_file:
        with open(os.path.join(outdir, npth_file)) as f:
            drl_tools, drl_holes = parse_excellon(f.read())
    pth_holes = []
    if pth_file:
        with open(os.path.join(outdir, pth_file)) as f:
            _t, pth_holes = parse_excellon(f.read())
    # Excellon counts Y upward, KiCad's board frame counts it downward, so the
    # writer negates it. Put the export back into board coordinates before
    # comparing. Coordinates land on a 1 um grid (KiCad writes 3 decimals in
    # mm), which the +-2 um gate allows for.
    for h in drl_holes + pth_holes:
        h["y_mm"] = -h["y_mm"]

    ref_holes = read_reference_npth()
    matched, unmatched = [], []
    if ref_holes:
        for r in ref_holes:
            hit = next((h for h in drl_holes
                        if E.approx(h["x_mm"], r["x_mm"], DRILL_TOL_MM)
                        and E.approx(h["y_mm"], r["y_mm"], DRILL_TOL_MM)
                        and E.approx(h["dia_mm"], r["dia_mm"], DRILL_TOL_MM)), None)
            row = {"reference_kicad_mm": [round(r["x_mm"], 6), round(r["y_mm"], 6)],
                   "reference_dia_mm": r["dia_mm"],
                   "found": None if hit is None else
                   {"x_mm": round(hit["x_mm"], 6), "y_mm": round(hit["y_mm"], 6),
                    "dia_mm": hit["dia_mm"]}}
            (matched if hit else unmatched).append(row)

    checks = [
        E.gate_check("npth_pads", 6, after["npth_pads"]),
        # 22 drilled pads: the 20 the importer produced plus the two pegs it
        # had left on Edge.Cuts. Stated absolutely so a re-run reads the same.
        E.gate_check("drilled_pads_total", 22,
                     after["pth_pads"] + after["npth_pads"]),
        E.gate_check("pth_pads", 16, after["pth_pads"],
                     note="J2 header 12 + J1 shell slots 4"),
        E.gate_check("vias_unchanged", before["vias"], after["vias"]),
        E.gate_check("copper_layers", 4, after["copper_layers"]),
        E.gate_check("edge_cuts_is_4_segments", 4, len(edge_segs)),
        E.gate_check("no_edge_cuts_inside_footprints", 0, fp_edge),
        E.gate_check("drill_export_ok", 0, proc.returncode,
                     note=(proc.stderr or "")[:300]),
        E.gate_check("npth_drill_file_holes", 6, len(drl_holes)),
        E.gate_check("npth_matches_old_drl_within_2um",
                     "%d/6" % (len(ref_holes) if ref_holes else 0),
                     "%d/%d" % (len(matched), len(ref_holes) if ref_holes else 0),
                     ok=(bool(ref_holes) and len(matched) == len(ref_holes) == 6)),
    ]
    E.write_gate(os.path.join(root, "gates", "S4a.json"), "S4a", checks,
                 notes="NPTH synthesis + outline closure. Counts before=%s after=%s"
                       % (json.dumps(before), json.dumps(after)),
                 extra={"log": log, "npth_pads_on_board": npth_found,
                        "drill_files": files, "npth_tools": drl_tools,
                        "npth_vs_old_drl": {"matched": matched,
                                            "unmatched": unmatched},
                        "pth_holes_in_export": len(pth_holes)})

    ok = all(c["pass"] for c in checks)
    print("S4a pass=%s (%d/%d checks)  NPTH=%d PTH=%d vias=%d edge_segs=%d"
          % (ok, sum(c["pass"] for c in checks), len(checks), after["npth_pads"],
             after["pth_pads"], after["vias"], len(edge_segs)))
    for c in checks:
        if not c["pass"]:
            print("  FAIL %s: expected=%s actual=%s"
                  % (c["name"], json.dumps(c["expected"])[:80],
                     json.dumps(c["actual"])[:200]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
