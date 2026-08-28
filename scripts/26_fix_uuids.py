#!/usr/bin/env python3
"""Give every board item its own KIID again.

    python3 scripts/26_fix_uuids.py [--check]

The EasyEDA importer reuses one KIID for every instance of a library
footprint. On this board 231 distinct uuids are shared, 2625 occurrences in
excess: 38 footprints carry one, and their 38 pin-1 pads carry another. KiCad
requires uuids to be unique and quietly misbehaves when they are not --
`BOARD::GetItem(KIID)` returns whichever item it finds first.

That last point is what makes this worth fixing rather than working around.
DRC does not store pointers to the items in a violation; it stores their KIIDs
and resolves them when the report is written. With duplicates, the report names
the wrong item. It is why the pre-repair report paired a solder mask bridge
between two pads 9.3 mm apart, why a clearance violation of 0.0420 mm was
reported between pads 8.9 mm apart, and why the unconnected-item healer, asked
to join two VDD_ESP pads, resolved one of them to a USB_5V pad and routed
24.7 mm of track to it.

The violation types and counts were always right. Only the identification of
which items were involved was wrong -- and L5 and the DRC loop have to work
from exactly that.

Nothing in this file cross-references a uuid (no groups, no members lists), so
renumbering the repeats is safe: the second and later occurrences of each
duplicated uuid get a fresh one, the first keeps its own, and the s-expression
is otherwise untouched. Verified afterwards by re-opening the board and
checking that footprint, pad, track and via counts and the whole pad->net map
are unchanged.

Idempotent: with no duplicates left it rewrites nothing.
"""

import argparse
import collections
import hashlib
import json
import os
import re
import sys
import uuid as uuidlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "lib"))

import epro as E                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = "board/Therapia_EEG-HRV.kicad_pcb"
UUID_RE = re.compile(r'\(uuid "([0-9a-fA-F-]{36})"\)')


def survey(text):
    found = UUID_RE.findall(text)
    counts = collections.Counter(found)
    dups = {k: v for k, v in counts.items() if v > 1}
    return {
        "tokens": len(found),
        "distinct": len(counts),
        "duplicated_uuids": len(dups),
        "excess_occurrences": sum(v - 1 for v in dups.values()),
        "worst": sorted(dups.values(), reverse=True)[:5],
    }


def rewrite(text):
    seen = set()
    made = [0]

    def sub(m):
        u = m.group(1)
        if u not in seen:
            seen.add(u)
            return m.group(0)
        made[0] += 1
        return '(uuid "%s")' % uuidlib.uuid4()

    return UUID_RE.sub(sub, text), made[0]


def measure(path):
    """Counts and the pad->net map, to prove the rewrite changed nothing."""
    import pcbnew
    b = pcbnew.LoadBoard(path)
    fps = list(b.GetFootprints())
    pads = [(f.GetReference(), p.GetNumber(), p.GetNetname(),
             p.GetPosition().x, p.GetPosition().y)
            for f in fps for p in f.Pads()]
    tracks = [t for t in b.GetTracks() if t.GetClass() != "PCB_VIA"]
    vias = [t for t in b.GetTracks() if t.GetClass() == "PCB_VIA"]
    return {
        "footprints": len(fps),
        "pads": len(pads),
        "tracks": len(tracks),
        "vias": len(vias),
        "zones": len(list(b.Zones())),
        # hashlib, not hash(): the before and after measurements run in
        # different processes and Python randomises str hashing per process,
        # so the built-in would report a change on an identical board.
        "pad_net_digest": hashlib.sha256(
            repr(sorted(pads)).encode()).hexdigest()[:16],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--check", action="store_true",
                    help="report duplicates and change nothing")
    a = ap.parse_args()
    path = os.path.join(a.root, BOARD)

    text = open(path).read()
    before = survey(text)
    log = {"before": before}
    if before["excess_occurrences"] == 0 or a.check:
        log["action"] = "none" if not a.check else "check only"
        print(json.dumps(log, indent=1))
        return 0

    have_pcbnew = True
    try:
        log["measure_before"] = measure(path)
    except ImportError:
        have_pcbnew = False
        log["measure_before"] = "pcbnew unavailable; counts not verified"

    new_text, made = rewrite(text)
    with open(path, "w") as f:
        f.write(new_text)
    log["uuids_replaced"] = made
    log["after"] = survey(new_text)

    checks = [
        E.gate_check("no_duplicate_uuids", 0,
                     log["after"]["excess_occurrences"]),
        E.gate_check("token_count_unchanged", before["tokens"],
                     log["after"]["tokens"]),
    ]
    if have_pcbnew:
        # A second LoadBoard in one process returns raw SWIG objects, so the
        # after-measurement runs as its own process.
        import subprocess
        kpy = os.environ.get(
            "KPY", "/Applications/KiCad/KiCad.app/Contents/Frameworks/"
                   "Python.framework/Versions/Current/bin/python3")
        proc = subprocess.run(
            [kpy, os.path.abspath(__file__), "--root", a.root, "--measure"],
            capture_output=True, text=True)
        try:
            log["measure_after"] = json.loads(proc.stdout)
        except ValueError:
            log["measure_after"] = {"stderr": proc.stderr[-300:]}
        checks.append(E.gate_check("board_unchanged", log["measure_before"],
                                   log["measure_after"]))

    E.write_gate(os.path.join(a.root, "gates", "S5_uuids.json"), "S5_uuids",
                 checks,
                 notes="Renumbered %d duplicated KIIDs so DRC can name the "
                       "items in a violation correctly." % made,
                 extra=log)
    print(json.dumps(log, indent=1))
    return 0 if all(c["pass"] for c in checks) else 1


if __name__ == "__main__":
    if "--measure" in sys.argv:
        i = sys.argv.index("--root") if "--root" in sys.argv else -1
        root = sys.argv[i + 1] if i >= 0 else ROOT
        print(json.dumps(measure(os.path.join(root, BOARD))))
        sys.exit(0)
    sys.exit(main())
