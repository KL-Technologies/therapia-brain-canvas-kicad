#!/usr/bin/env python3
"""S7b aid -- a picture of every square millimetre of copper that changed.

    KPY scripts/64_copper_xor.py [--baseline 22513e4]

46_analog_untouched.py answers "did anything move" exactly, item by item, and
that is the gate. This answers "show me", which is a different question and the
one a person reviewing the board actually asks. It plots F.Cu and B.Cu from the
board as imported and from the board now, rasterises both, and writes an image
where each pixel says which of the two has copper there:

    grey    both      -- unchanged
    green   now only  -- copper added
    red     then only -- copper removed

`kicad-cli pcb render` is a 3D view with lighting and perspective and cannot be
compared pixel to pixel. `export svg` plots flat -- but `--page-size-mode 2`
sizes the page to the plotted content, which differs between the two boards
(1421 rows against 1456), so the two would not line up. Mode 0 puts both on the
same A4 frame in board millimetres, and this then renders just the board
rectangle out of that shared frame, which makes the two rasters the same pixels
of the same place by construction.

PNG is written with zlib and struct. Pillow is not available under
PYTHONNOUSERSITE=1 (see the S0 stdlib check) and this does not need it.
"""

import argparse
import os
import struct
import subprocess
import sys
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import repair as P                                 # noqa: E402
import epro as E                                   # noqa: E402

BASELINE_SHA = "22513e4"
PX_PER_MM = 20                   # 0.0889 mm, the narrowest track, is ~1.8 px
PAGE_MODE = "0"                  # a fixed A4 frame, identical for both boards


def export_svg(board_path, layer, out_path):
    cmd = [P.kicad_cli(), "pcb", "export", "svg", "--layers", layer,
           "--black-and-white", "--mode-single", "--exclude-drawing-sheet",
           "--page-size-mode", PAGE_MODE, "-o", out_path, board_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return os.path.exists(out_path), (proc.stdout or "") + (proc.stderr or "")


def rasterize(svg_path, box, px_per_mm):
    """Render just `box` (in board mm) out of the SVG's page, at a fixed scale.

    The SVG's user units are board millimetres on an A4 page, so translating by
    -x0, -y0 and scaling puts the board's own rectangle at the origin. Both
    boards go through the same numbers, so pixel (i, j) is the same square
    millimetre in both images.
    """
    import wx.svg
    x0, y0, x1, y1 = box
    w = int(round((x1 - x0) * px_per_mm))
    h = int(round((y1 - y0) * px_per_mm))
    img = wx.svg.SVGimage.CreateFromFile(svg_path)
    # `scale` is relative to the SVG's natural pixel size, and nanosvg converts
    # the "297.0022mm" width to pixels at 96 dpi -- so scale 1 is 3.7795 px per
    # millimetre, not 1. Passing px_per_mm directly renders the page five times
    # too large and the board rectangle lands off the buffer, which is why the
    # first attempt produced an entirely empty image rather than an error.
    scale = px_per_mm * 25.4 / 96.0
    # RasterizeToBuffer wants the destination buffer as its first positional
    # argument; it does not allocate one. tx/ty are output pixels.
    buf = bytearray(w * h * 4)
    img.RasterizeToBuffer(buf, tx=-x0 * px_per_mm, ty=-y0 * px_per_mm,
                          scale=scale, width=w, height=h, stride=w * 4)
    return w, h, bytes(buf)


def alpha_mask(w, h, rgba):
    """One byte per pixel: 1 where the plot put ink."""
    return bytearray(1 if rgba[i * 4 + 3] > 32 else 0 for i in range(w * h))


def write_png(path, w, h, rows_rgb):
    """Truecolour PNG, no filtering. rows_rgb is one bytes() per scanline."""
    raw = b"".join(b"\x00" + r for r in rows_rgb)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def compare(before, now, out_png):
    w, h, a = before
    w2, h2, b = now
    if (w, h) != (w2, h2):
        return {"ok": False, "reason": "rasters differ in size: %dx%d vs %dx%d"
                                       % (w, h, w2, h2)}
    ma = alpha_mask(w, h, a)
    mb = alpha_mask(w, h, b)
    both = added = removed = 0
    rows = []
    for y in range(h):
        row = bytearray(w * 3)
        base = y * w
        for x in range(w):
            i = base + x
            pa, pb = ma[i], mb[i]
            o = x * 3
            if pa and pb:
                both += 1
                row[o] = row[o + 1] = row[o + 2] = 0x50
            elif pb:
                added += 1
                row[o + 1] = 0xE0
            elif pa:
                removed += 1
                row[o] = 0xE0
            else:
                row[o] = row[o + 1] = row[o + 2] = 0xF2
        rows.append(bytes(row))
    write_png(out_png, w, h, rows)
    return {"ok": True, "png": out_png, "width": w, "height": h,
            "pixels_both": both, "pixels_added": added,
            "pixels_removed": removed,
            "changed_fraction": round((added + removed)
                                      / float(both + added + removed or 1), 6)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=P.ROOT)
    ap.add_argument("--baseline", default=BASELINE_SHA)
    ap.add_argument("--px-per-mm", type=int, default=PX_PER_MM)
    a = ap.parse_args()
    root = a.root
    work = os.path.join(root, "logs", "copper_xor")
    if not os.path.isdir(work):
        os.makedirs(work)

    base_pcb = os.path.join(work, "baseline.kicad_pcb")
    with open(base_pcb, "wb") as f:
        got = subprocess.run(["git", "show", "%s:board/%s.kicad_pcb"
                              % (a.baseline, P.BOARD_NAME)],
                             cwd=root, stdout=f, stderr=subprocess.PIPE)
    if got.returncode:
        print("could not extract the baseline board: %s"
              % got.stderr.decode()[:300])
        return 2

    log = {"baseline": a.baseline, "layers": {}}
    for layer, tag in (("F.Cu", "f_cu"), ("B.Cu", "b_cu")):
        paths = {}
        for name, pcb in (("before", base_pcb),
                          ("after", P.board_path(root))):
            svg = os.path.join(work, "%s_%s.svg" % (tag, name))
            ok, blob = export_svg(pcb, layer, svg)
            if not ok:
                print("svg export failed for %s %s:\n%s"
                      % (layer, name, blob[-600:]))
                return 2
            paths[name] = svg
        box = tuple(v / float(P.IU) for v in P.board_box())
        before = rasterize(paths["before"], box, a.px_per_mm)
        after = rasterize(paths["after"], box, a.px_per_mm)
        out = os.path.join(root, "reports",
                           "copper_xor_%s.png" % tag)
        log["layers"][layer] = compare(before, after, out)
        r = log["layers"][layer]
        if not r.get("ok"):
            print("%s: %s" % (layer, r["reason"]))
            return 1
        print("%-5s %dx%d px  unchanged %d  added %d  removed %d  (%.3f%% changed)"
              % (layer, r["width"], r["height"], r["pixels_both"],
                 r["pixels_added"], r["pixels_removed"],
                 100.0 * r["changed_fraction"]))
        print("      %s" % out)
    E.dump_json(os.path.join(root, "logs", "copper_xor.json"), log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
