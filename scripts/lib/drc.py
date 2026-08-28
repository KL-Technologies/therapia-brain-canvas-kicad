"""Comparing two kicad-cli DRC reports without being fooled by its jitter.

Running `kicad-cli pcb drc` twice on a byte-identical board does not give the
same answer. Measured on this board: 523 and 525 violations, differing by two
`clearance` errors. Both runs are describing the same two physical problems --

    run A   Track [V_NLDO_IN] on Bottom Layer, length 2.2860 mm  <-> Via [VNEG5]
    run B   Track [V_NLDO_IN] on Bottom Layer, length 0.2543 mm  <-> Via [VNEG5]

-- a via sitting too close to a V_NLDO_IN polyline; which of the polyline's
segments gets named depends on the order the spatial query happened to reach
them, and sometimes both are named. So a gate that compares raw counts fails
at random.

What is stable is (violation type, set of nets involved). That is what
`signature` returns and what `compare` gates on: a regression is a signature
that was not in the baseline. Counts are still reported, with
`COUNT_JITTER` as the slack allowed on them, because a large count change is
worth seeing even when the signatures match.
"""

import re
import collections

COUNT_JITTER = 2

_NET_RE = re.compile(r"\[([^\]]+)\]")
_ACTUAL_RE = re.compile(r"actual ([\d.]+) mm")
_REF_RE = re.compile(r"of ([A-Za-z_][\w.+-]*)")


def nets_of(violation):
    nets = set()
    for item in violation.get("items", []):
        nets.update(_NET_RE.findall(item.get("description", "")))
    return nets


def refs_of(violation):
    refs = set()
    for item in violation.get("items", []):
        refs.update(_REF_RE.findall(item.get("description", "")))
    return refs


def actual_mm(violation):
    m = _ACTUAL_RE.search(violation.get("description", ""))
    return float(m.group(1)) if m else None


def signature(violation):
    """(type, nets, refs) -- everything about a violation that does not depend
    on which of several equivalent items DRC decided to name."""
    return (violation.get("type"),
            tuple(sorted(nets_of(violation))),
            tuple(sorted(refs_of(violation))))


def sig_text(sig):
    kind, nets, refs = sig
    parts = [kind]
    if nets:
        parts.append("nets=" + ",".join(nets))
    if refs:
        parts.append("refs=" + ",".join(refs))
    return " ".join(parts)


def load(path):
    import json
    with open(path) as f:
        return json.load(f)


def summarize(doc, severity="error"):
    viol = doc.get("violations", [])
    sel = [v for v in viol if v.get("severity") == severity] if severity else viol
    return {
        "violations": len(viol),
        "errors": sum(1 for v in viol if v.get("severity") == "error"),
        "warnings": sum(1 for v in viol if v.get("severity") == "warning"),
        "unconnected": len(doc.get("unconnected_items", [])),
        "by_type": dict(collections.Counter(v.get("type") for v in viol
                                            ).most_common()),
        "errors_by_type": dict(collections.Counter(
            v.get("type") for v in viol
            if v.get("severity") == "error").most_common()),
        "signatures": sorted(sig_text(s) for s in {signature(v) for v in sel}),
    }


def compare(baseline_doc, current_doc, severity="error"):
    """Did the board get worse? Signature-level, so DRC's jitter cannot flip it."""
    def sigs(doc):
        return {signature(v) for v in doc.get("violations", [])
                if not severity or v.get("severity") == severity}

    base, cur = sigs(baseline_doc), sigs(current_doc)
    new = sorted(sig_text(s) for s in cur - base)
    gone = sorted(sig_text(s) for s in base - cur)
    b_err = sum(1 for v in baseline_doc.get("violations", [])
                if v.get("severity") == "error")
    c_err = sum(1 for v in current_doc.get("violations", [])
                if v.get("severity") == "error")
    return {
        "new_signatures": new,
        "resolved_signatures": gone,
        "baseline_errors": b_err,
        "current_errors": c_err,
        "error_delta": c_err - b_err,
        "count_jitter_allowed": COUNT_JITTER,
        "count_within_jitter": (c_err - b_err) <= COUNT_JITTER,
        "regressed": bool(new),
    }
