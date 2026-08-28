"""Reader for the EasyEDA Pro 3.2 `.epro2` container and its `.epru` payload.

This is NOT the format KiCad imports. KiCad's EASYEDAPRO plugin expects the
older `.epro` archive (project.json + JSON-Lines `*.epcb` / `*.efoo`); handed an
`.epro2` it finds no documents and returns an empty board without erroring --
0 footprints, 1 net, no warning. See scripts/06_epro2_to_epro.py.

`.epro2` layout
    project2.json          title / editorVersion
    <name>.epru            every document, concatenated
    IMAGE/*.webp           referenced images

`.epru` layout
    Records are separated by "|\n". Each record is
        <header json> || <body json>
    header: {"type": ..., "ticket": int, "id": ..., "firstTicket": int}
    body:   the element's fields as a named dict, or empty when deleted.
    A record of type DOCHEAD starts a new document; its body carries docType
    ("PCB", "FOOTPRINT", "SYMBOL", "DEVICE", "SCH", "SCH_PAGE", "BOARD", ...)
    and the document uuid.
"""

import json
import os
import zipfile

SEP = "|\n"
DOC_SEP = "||"


class Doc(object):
    def __init__(self, head):
        self.head = head or {}
        self.records = []          # list of (header dict, body dict|None)

    @property
    def doc_type(self):
        return self.head.get("docType")

    @property
    def uuid(self):
        return self.head.get("uuid")

    def meta(self):
        for h, b in self.records:
            if h.get("type") == "META" and isinstance(b, dict):
                return b
        return {}

    def title(self):
        return self.meta().get("title") or ""

    def of_type(self, *types):
        """Live records of the given types (deleted ones have an empty body)."""
        return [(h, b) for h, b in self.records
                if h.get("type") in types and b is not None]


def parse_epru(text):
    """Split an .epru payload into documents, preserving record order."""
    docs, cur = [], None
    for chunk in text.split(SEP):
        if not chunk.strip():
            continue
        parts = chunk.split(DOC_SEP)
        try:
            head = json.loads(parts[0])
        except ValueError:
            continue
        body = None
        if len(parts) > 1 and parts[1].strip():
            try:
                body = json.loads(parts[1])
            except ValueError:
                body = None
        if head.get("type") == "DOCHEAD":
            cur = Doc(body)
            docs.append(cur)
        elif cur is not None:
            cur.records.append((head, body))
    return docs


class Epro2(object):
    """An .epro2 archive: documents plus the images alongside them."""

    def __init__(self, path):
        self.path = path
        self.zf = zipfile.ZipFile(path)
        self.names = [n for n in self.zf.namelist() if not n.endswith("/")]
        self.project2 = {}
        for n in self.names:
            if os.path.basename(n) == "project2.json":
                self.project2 = json.loads(self.zf.read(n).decode("utf-8", "replace"))
        payloads = [n for n in self.names if n.lower().endswith(".epru")]
        if not payloads:
            raise ValueError("no .epru payload in %s" % path)
        self.payload_name = payloads[0]
        self.docs = parse_epru(
            self.zf.read(self.payload_name).decode("utf-8", "replace"))

    def close(self):
        self.zf.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def by_type(self, doc_type):
        return [d for d in self.docs if d.doc_type == doc_type]

    def images(self):
        return [n for n in self.names if n.upper().startswith("IMAGE/")]

    def title(self):
        return self.project2.get("title") or os.path.splitext(
            os.path.basename(self.path))[0]


def looks_like_epro2(path):
    """(is_epro2, why) -- cheap enough to run on every search candidate."""
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
    except Exception as exc:                                # noqa: BLE001
        return False, "not a zip: %s" % exc
    has_p2 = any(os.path.basename(n) == "project2.json" for n in names)
    epru = [n for n in names if n.lower().endswith(".epru")]
    if has_p2 and epru:
        return True, "project2.json + %s" % epru[0]
    return False, "no project2.json/.epru (project2=%s epru=%d)" % (has_p2, len(epru))
