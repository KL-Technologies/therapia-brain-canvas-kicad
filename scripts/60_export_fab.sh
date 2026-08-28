#!/bin/sh
# S8 -- the manufacturing package.
#
#     scripts/60_export_fab.sh          (run OUTSIDE the command sandbox)
#
# Settings are copied from the package JLCPCB actually accepted, which is
# ganglion_clone/jlcpcb_order: Protel extensions, X2 attributes, 4.6 mm
# coordinates, Excellon with PTH and NPTH in separate files, metric decimal.
# All four are kicad-cli 10 defaults, so what looks like an empty command line
# is the point -- the flags below are only the ones that differ from default.
#
#   --check-zones        refill before plotting, so the copper in the Gerber is
#                        the copper DRC passed and not a stale fill
#   --subtract-soldermask  keep silkscreen off exposed pads
#   no --use-drill-file-origin   absolute coordinates, matching the drill file
#                        and the 2026-08-16 package the CPL was checked against
#
# ACCEPTANCE E wants 14 files: 4 copper, 2 mask, 2 silk, 2 paste, 1 outline,
# 1 .gbrjob, 2 drill.

set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KC="${KC:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}"
BOARD="$ROOT/board/Therapia_EEG-HRV.kicad_pcb"
OUT="$ROOT/fab/gerber"
NAME="Therapia_EEG-HRV_Rev.A"

rm -rf "$OUT"
mkdir -p "$OUT"

echo "== gerbers =="
"$KC" pcb export gerbers \
    --output "$OUT/" \
    --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,F.SilkS,B.SilkS,Edge.Cuts \
    --subtract-soldermask \
    --check-zones \
    "$BOARD"

echo "== drill (PTH and NPTH separate, mm, decimal, absolute) =="
"$KC" pcb export drill \
    --output "$OUT/" \
    --format excellon \
    --drill-origin absolute \
    --excellon-units mm \
    --excellon-zeros-format decimal \
    --excellon-oval-format alternate \
    --excellon-separate-th \
    --generate-map --map-format pdf \
    "$BOARD"

echo "== placement preview =="
"$KC" pcb render --side top    --width 1600 --height 1200 \
    --output "$ROOT/fab/preview_top.png" "$BOARD"
"$KC" pcb render --side bottom --width 1600 --height 1200 \
    --output "$ROOT/fab/preview_bottom.png" "$BOARD"

echo "== assembly drawing =="
# The 3D render shows shapes; this shows names. It is what to hold next to
# JLC's Confirm Parts Placement screen, and --crossout-DNP puts an X through
# R_RST_UP and R_IO15_DN so the two parts that must NOT be fitted are visible
# rather than merely absent from a list.
# In --mode-single the output is a file, not a directory.
"$KC" pcb export pdf \
    --output "$ROOT/fab/assembly_top.pdf" \
    --layers F.Fab,F.SilkS,Edge.Cuts \
    --mode-single \
    --include-border-title \
    --crossout-DNP-footprints-on-fab-layers \
    --black-and-white \
    "$BOARD"

echo "== zip =="
# The map PDF is a human aid, not part of what JLC reads; keeping it out of the
# archive means the archive is exactly the 14 files ACCEPTANCE E counts.
( cd "$OUT" && rm -f "../$NAME.zip" \
  && zip -q -X "../$NAME.zip" \
       *.gtl *.g1 *.g2 *.gbl *.gts *.gbs *.gtp *.gbp *.gto *.gbo *.gm1 \
       *.gbrjob *PTH.drl 2>/dev/null || true )

ls -la "$OUT"
echo
echo "archive: $ROOT/fab/$NAME.zip"
unzip -l "$ROOT/fab/$NAME.zip" | tail -3
