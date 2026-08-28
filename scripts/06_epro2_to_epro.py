#!/usr/bin/env python3
"""S1B: convert an EasyEDA Pro 3.2 `.epro2` export into the classic `.epro`
archive that KiCad's EASYEDAPRO plugin can actually read.

Why this step exists: KiCad 10.0.5 has no knowledge of `.epro2` / `.epru` /
`project2.json`. Handed one it opens the zip, finds no `project.json` and no
`*.epcb`, and returns an EMPTY BOARD -- 0 footprints, 1 net, no error, no
warning. Verified on this machine before writing the converter.

The two formats describe the same object model; only the serialisation differs.
`.epru` stores each element as a named dict, the classic format as a positional
JSON array. The field order used here comes from KiCad's own parser
(pcbnew/pcb_io/easyedapro/pcb_io_easyedapro_parser.cpp and
common/io/easyedapro/easyedapro_parser.cpp), because that parser is the only
consumer that matters -- nlohmann's `.at(n)` throws on a short array, so every
record is padded to the highest index the parser touches.

Deliberately NOT converted:
  RULE    EasyEDA 3.2 design rules are a nested structure with no stable mapping
          onto the classic `["RULE", type, name, isDefault, data]` payload, and
          getting it wrong is what trips KiCad #24303. The values are written to
          contract/easyeda_rules.json instead, for S3 to transcribe into
          .kicad_pro deliberately.
  POURED  EasyEDA's precomputed copper fill. KiCad regenerates it from the POUR
          outlines via `drc --refill-zones`, which S3 has to do anyway after
          editing. Pass --with-poured to emit it.

Runs under system python3; no KiCad needed.
"""

import os
import sys
import json
import zipfile
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import epro as E                      # noqa: E402
from lib import epru as U                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# how long each emitted record must be so KiCad's .at(n) never throws
MIN_LEN = {"PAD": 15, "ATTR": 19, "LINE": 10, "ARC": 11, "VIA": 9, "POLY": 7,
           "FILL": 8, "POUR": 9, "POURED": 6, "REGION": 7, "COMPONENT": 8,
           "PAD_NET": 4, "NET": 2, "LAYER": 5, "STRING": 17}


def pad_to(rec):
    n = MIN_LEN.get(rec[0], 0)
    while len(rec) < n:
        rec.append(None)
    return rec


def hole_array(body):
    """{"holeType":"ROUND","width":w,"height":h} -> ["ROUND", w, h]

    KiCad reads padHole.at(0) as the shape name and .at(1)/.at(2) as the drill
    size, and treats any non-zero drill as a hole.
    """
    h = body.get("hole") or {}
    return [h.get("holeType") or "ROUND", h.get("width") or 0, h.get("height") or 0]


def shape_array(body):
    """{"padType":"ELLIPSE","width":w,"height":h} -> ["ELLIPSE", w, h]"""
    p = body.get("defaultPad") or {}
    arr = [p.get("padType") or "ELLIPSE", p.get("width") or 0, p.get("height") or 0]
    if p.get("cornerRadius") is not None:
        arr.append(p["cornerRadius"])
    return arr


def pad_record(rid, body):
    return pad_to(["PAD", rid, body.get("partitionId", ""),
                   body.get("netName") or "", body.get("layerId"),
                   str(body.get("num", "")), body.get("centerX"),
                   body.get("centerY"), body.get("padAngle") or 0,
                   hole_array(body), shape_array(body)])


def attr_record(rid, body):
    return pad_to(["ATTR", rid, "", body.get("parentId") or "",
                   body.get("layerId"), body.get("x"), body.get("y"),
                   body.get("key") or "", body.get("value"),
                   body.get("keyVisible"), body.get("valueVisible"),
                   body.get("fontFamily"), body.get("fontSize"),
                   body.get("strokeWidth"), None, None,
                   None,                       # textOrigin: EasyEDA gives a
                                               # string, KiCad wants a number,
                                               # and skips it when it is not one
                   body.get("angle"), body.get("reverse")])


def convert_records(doc, want_poured=False):
    """One .epru document -> classic JSON-Lines records, in source order."""
    out, skipped = [], {}
    for h, b in doc.records:
        t = h.get("type")
        rid = h.get("id")
        if b is None:                       # deleted element
            continue
        if t == "LAYER":
            lid = b.get("layerId")
            if lid is None and isinstance(rid, str) and rid.startswith("["):
                try:
                    lid = json.loads(rid)[1]
                except (ValueError, IndexError):
                    lid = None
            out.append(pad_to(["LAYER", lid, b.get("layerType"),
                               b.get("layerName"), bool(b.get("use"))]))
        elif t == "NET":
            name = None
            if isinstance(rid, str) and rid.startswith("["):
                try:
                    name = json.loads(rid)[1]
                except (ValueError, IndexError):
                    name = None
            if name is not None:
                out.append(pad_to(["NET", name]))
        elif t == "COMPONENT":
            out.append(pad_to(["COMPONENT", rid, b.get("partitionId", ""),
                               b.get("layerId"), b.get("x"), b.get("y"),
                               b.get("angle") or 0, dict(b.get("attrs") or {})]))
        elif t == "ATTR":
            out.append(attr_record(rid, b))
        elif t == "PAD":
            out.append(pad_record(rid, b))
        elif t == "PAD_NET":
            comp = pad_num = None
            if isinstance(rid, str) and rid.startswith("["):
                try:
                    key = json.loads(rid)
                    comp, pad_num = key[1], key[2]
                except (ValueError, IndexError):
                    pass
            if comp is not None:
                out.append(pad_to(["PAD_NET", comp, str(pad_num),
                                   b.get("padNet") or ""]))
        elif t == "LINE":
            out.append(pad_to(["LINE", rid, b.get("partitionId", ""),
                               b.get("netName") or "", b.get("layerId"),
                               b.get("startX"), b.get("startY"),
                               b.get("endX"), b.get("endY"), b.get("width")]))
        elif t == "ARC":
            out.append(pad_to(["ARC", rid, b.get("partitionId", ""),
                               b.get("netName") or "", b.get("layerId"),
                               b.get("startX"), b.get("startY"),
                               b.get("endX"), b.get("endY"),
                               b.get("angle"), b.get("width")]))
        elif t == "VIA":
            out.append(pad_to(["VIA", rid, b.get("partitionId", ""),
                               b.get("netName") or "", "",
                               b.get("centerX"), b.get("centerY"),
                               b.get("holeDiameter"), b.get("viaDiameter")]))
        elif t == "POLY":
            out.append(pad_to(["POLY", rid, b.get("partitionId", ""),
                               b.get("netName") or "", b.get("layerId"),
                               b.get("width"), b.get("path")]))
        elif t == "FILL":
            out.append(pad_to(["FILL", rid, b.get("partitionId", ""),
                               b.get("netName") or "", b.get("layerId"),
                               b.get("width"), b.get("fillStyle"),
                               b.get("path")]))
        elif t == "POUR":
            out.append(pad_to(["POUR", rid, b.get("partitionId", ""),
                               b.get("netName") or "", b.get("layerId"),
                               b.get("width"), b.get("name"),
                               b.get("order"), b.get("path")]))
        elif t == "POURED":
            if not want_poured:
                skipped["POURED"] = skipped.get("POURED", 0) + 1
                continue
            parent = rid
            if isinstance(rid, str) and rid.startswith("["):
                try:
                    parent = json.loads(rid)[1]
                except (ValueError, IndexError):
                    pass
            for i, fill in enumerate(b.get("pourFill") or []):
                out.append(pad_to(["POURED", "%s_f%d" % (parent, i), parent, 0,
                                   True, fill.get("path")]))
        elif t == "REGION":
            out.append(pad_to(["REGION", rid, b.get("partitionId", ""),
                               b.get("layerId"), b.get("width"),
                               b.get("flags"), b.get("path")]))
        else:
            skipped[t] = skipped.get(t, 0) + 1
    return out, skipped


def block(doc_type, head, records):
    lines = [json.dumps(["DOCTYPE", doc_type], separators=(",", ":"))]
    lines.append(json.dumps(["HEAD", head], separators=(",", ":"),
                            ensure_ascii=False))
    for r in records:
        lines.append(json.dumps(r, separators=(",", ":"), ensure_ascii=False))
    return "\n".join(lines) + "\n"


def build_project_json(src, pcb_doc, board_doc, sch_doc, sch_pages,
                       footprints, symbols, devices):
    def entry(d):
        m = d.meta()
        e = {"title": m.get("title") or "", "display_title": m.get("title") or "",
             "description": m.get("description") or "",
             "source": m.get("source") or "", "version": str(d.head.get("version") or "")}
        if m.get("docType") is not None:
            e["type"] = m["docType"]
        if m.get("attributes"):
            e["attributes"] = m["attributes"]
        return e

    sheets = []
    for i, p in enumerate(sch_pages, 1):
        sheets.append({"name": p.title() or ("Sheet%d" % i),
                       "uuid": p.uuid, "id": i})
    return {
        "schematics": {sch_doc.uuid: {"name": sch_doc.title() or "Schematic1",
                                      "sheets": sheets}} if sch_doc else {},
        "boards": {board_doc.uuid: {"schematic": sch_doc.uuid if sch_doc else "",
                                    "pcb": pcb_doc.uuid}} if board_doc else {},
        "pcbs": {pcb_doc.uuid: {"title": pcb_doc.title() or "PCB1",
                                "display_title": pcb_doc.title() or "PCB1"}},
        "footprints": {d.uuid: entry(d) for d in footprints},
        "symbols": {d.uuid: entry(d) for d in symbols},
        "devices": {d.uuid: entry(d) for d in devices},
        "title": src.title(),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", help=".epro2 (default: newest in import/)")
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--out", help="output .epro (default: import/<name>.epro)")
    ap.add_argument("--with-poured", action="store_true",
                    help="also emit EasyEDA's precomputed copper fill")
    args = ap.parse_args()
    root = args.root

    src_path = args.src
    if not src_path:
        staged = sorted(os.listdir(os.path.join(root, "import")))
        cands = [os.path.join(root, "import", f) for f in staged
                 if f.lower().endswith(".epro2")]
        if not cands:
            classic = [f for f in staged if f.lower().endswith((".epro", ".eprj"))
                       and not f.startswith("patched")]
            if classic:
                E.write_gate(os.path.join(root, "gates", "S1B.json"), "S1B",
                             [E.gate_check("conversion_needed", "none", "none",
                                           ok=True)],
                             notes="input is already a classic .epro (%s); nothing "
                                   "to convert" % classic[0])
                print("S1B: not needed -- %s is already a classic .epro" % classic[0])
                return 0
            print("nothing staged in import/ -- run scripts/05_find_epro.sh first")
            return 2
        src_path = max(cands, key=os.path.getmtime)

    out_path = args.out or os.path.join(
        root, "import",
        os.path.splitext(os.path.basename(src_path))[0] + ".converted.epro")

    with U.Epro2(src_path) as src:
        pcbs = src.by_type("PCB")
        if not pcbs:
            print("no PCB document in %s" % src_path)
            return 2
        pcb = pcbs[0]
        boards = src.by_type("BOARD")
        schs = src.by_type("SCH")
        pages = src.by_type("SCH_PAGE")
        fps = src.by_type("FOOTPRINT")
        syms = src.by_type("SYMBOL")
        devs = src.by_type("DEVICE")

        project = build_project_json(src, pcb, boards[0] if boards else None,
                                     schs[0] if schs else None, pages,
                                     fps, syms, devs)

        pcb_records, pcb_skipped = convert_records(pcb, args.with_poured)
        pcb_head = {"uuid": pcb.uuid, "title": pcb.title() or "PCB1",
                    "originX": 0, "originY": 0,
                    "version": str(pcb.head.get("version") or "")}

        report = {"source": os.path.abspath(src_path),
                  "source_sha256": E.sha256_file(src_path),
                  "editor_version": src.project2.get("editorVersion"),
                  "output": os.path.abspath(out_path),
                  "documents": {t: len(src.by_type(t)) for t in
                                ("PCB", "BOARD", "SCH", "SCH_PAGE", "FOOTPRINT",
                                 "SYMBOL", "DEVICE", "CONFIG", "BLOB")},
                  "pcb": {"uuid": pcb.uuid, "records_in": len(pcb.records),
                          "records_out": len(pcb_records),
                          "skipped": pcb_skipped},
                  "footprints": {}}

        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("project.json",
                       json.dumps(project, indent=1, ensure_ascii=False))
            z.writestr("PCB/%s.epcb" % pcb.uuid,
                       block("PCB", pcb_head, pcb_records))
            for d in fps:
                recs, skipped = convert_records(d, args.with_poured)
                head = {"uuid": d.uuid, "title": d.title(),
                        "originX": 0, "originY": 0,
                        "version": str(d.head.get("version") or "")}
                z.writestr("FOOTPRINT/%s.efoo" % d.uuid,
                           block("FOOTPRINT", head, recs))
                report["footprints"][d.uuid] = {
                    "title": d.title(), "records_out": len(recs),
                    "pads": sum(1 for r in recs if r[0] == "PAD"),
                    "skipped": skipped}

        # design rules are not converted -- hand them to S3 as data
        rules = []
        for h, b in pcb.of_type("RULE"):
            key = h.get("id")
            try:
                key = json.loads(key) if isinstance(key, str) and key.startswith("[") else key
            except ValueError:
                pass
            rules.append({"id": key, "body": b})
        E.dump_json(os.path.join(root, "contract", "easyeda_rules.json"), {
            "source": report["source"],
            "note": "EasyEDA Pro 3.2 design rules, verbatim. NOT transferred to "
                    "the KiCad board -- S3 must transcribe the values it wants "
                    "into board/*.kicad_pro net classes and custom DRC rules.",
            "rules": rules,
            "preference": next((b for h, b in pcb.of_type("PREFERENCE")), None),
            "layer_phys": [b for h, b in pcb.of_type("LAYER_PHYS")],
        })

    E.dump_json(os.path.join(root, "logs", "epro2_convert.json"), report)
    fp_pads = sum(f["pads"] for f in report["footprints"].values())
    print("converted %s -> %s" % (os.path.basename(src_path),
                                  os.path.basename(out_path)))
    print("  PCB records %d -> %d (skipped %s)" % (
        report["pcb"]["records_in"], report["pcb"]["records_out"],
        json.dumps(pcb_skipped)))
    print("  footprints %d, footprint pads %d" % (len(report["footprints"]), fp_pads))

    checks = [
        E.gate_check("pcb_document_found", 1, len(pcbs), ok=bool(pcbs)),
        E.gate_check("components_converted", E.EXPECTED_FOOTPRINT_COUNT,
                     sum(1 for r in pcb_records if r[0] == "COMPONENT")),
        E.gate_check("footprint_documents", ">0", len(report["footprints"]),
                     ok=bool(report["footprints"])),
        E.gate_check("footprint_pads", ">0", fp_pads, ok=fp_pads > 0),
        E.gate_check("nets_declared", ">0",
                     sum(1 for r in pcb_records if r[0] == "NET"),
                     ok=any(r[0] == "NET" for r in pcb_records)),
        E.gate_check("output_is_zip", True, zipfile.is_zipfile(out_path)),
    ]
    E.write_gate(os.path.join(root, "gates", "S1B.json"), "S1B", checks,
                 notes="EasyEDA Pro %s exported .epro2, which KiCad 10.0.5 cannot "
                       "read (it returns an empty board silently). Converted to "
                       "the classic .epro layout. RULE and POURED records are "
                       "deliberately not carried over; see "
                       "contract/easyeda_rules.json."
                       % src.project2.get("editorVersion"),
                 extra={"report": "logs/epro2_convert.json", "output": out_path})
    return 0 if all(c["pass"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
