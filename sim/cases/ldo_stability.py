#!/usr/bin/env python3
"""Case (b): are the two analog LDOs stable on the capacitors actually fitted?

The question is not "does the datasheet say 1 uF is enough" but "how much
capacitance is really there".  Every ceramic on AVDD and AVSS is a class-II
dielectric, and the board's own choices are unkind: C_NLDO_OUT is a 2.2 uF
6.3 V X5R in 0402 biased at 2.5 V, which keeps well under half its marking.
This case totals the DERATED capacitance from the netlist and runs the loop
on that.

Two independent measurements per rail:

  1. Loop gain by voltage injection.  Both LDO models expose their feedback
     sense point as a separate terminal (``*_CORE``), so the loop can be
     broken at a node that drives nothing but a high-impedance input --
     the condition under which the injection method is exact.
     T(jw) = -V(out)/V(sense); phase margin = 180 + arg T at |T| = 1.

  2. A load step, judged on whether the rail settles.  This is the primary
     evidence: the loop-gain number inherits the behavioural model's
     internal pole placement, which is a calibration; the settling of a
     real network of real capacitors is much less model-dependent.

Pass: phase margin >= 45 deg AND the load step settles without sustained
ringing.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))

from extract_subckt import Design, kind_of, effective_cap, fmt  # noqa: E402
from ngspice_ctypes import run_netlist                          # noqa: E402
import simutil as su                                            # noqa: E402

LIB = os.path.join(os.path.dirname(HERE), "models", "behavioral.lib")

BIAS = {"AVDD": 2.5, "AVSS": -2.5, "GND": 0.0, "V_PLDO_IN": 5.0,
        "V_NLDO_IN": -5.0, "TPS_NR": 0.0}

# Datasheet minimum output capacitance.  Both are the family's stated minimum
# ceramic value; PROVENANCE.md records how firmly each is pinned down.
# Both are the datasheet's requirement on EFFECTIVE capacitance, which is
# the whole point of derating before comparing.
#   TLV70025 (SLVSA00E 8.2.2.1): >= 0.1 uF effective, 1 uF recommended,
#                                ESR < 200 mohm
#   TPS72325 (SLVS346E 7.1.3/5.3): >= 1.0 uF effective (2.2 uF marked),
#                                ESR 0 to 0.5 ohm
MIN_COUT = {"TLV70025": 0.1e-6, "TPS72325": 1.0e-6}
MAX_ESR = {"TLV70025": 0.2, "TPS72325": 0.5}

# A BOM change moves C_NLDO_OUT and C_LM_IN from a 2.2 uF 6.3 V 0402
# (C12530) to a 4.7 uF 10 V 0402 (C23733).  Both are forced explicitly rather
# than read from the CSV, so the comparison stays meaningful whichever part
# data/parts_lcsc.csv currently names -- and so the case reports what the
# swap is worth rather than silently following it.
BOM_VARIANTS = {
    "old_C12530_2u2_6v3": {"C_NLDO_OUT": ("C12530", "2.2uF"),
                           "C_LM_IN": ("C12530", "2.2uF")},
    "new_C23733_4u7_10v": {"C_NLDO_OUT": ("C23733", "4.7uF"),
                           "C_LM_IN": ("C23733", "4.7uF")},
}

RAILS = {
    "TLV70025": {"rail": "AVDD", "nom": 2.5, "load_A": 0.050, "step_A": 0.100},
    "TPS72325": {"rail": "AVSS", "nom": -2.5, "load_A": 0.030, "step_A": 0.060},
}


def rail_capacitance(d, rail):
    """Total derated capacitance and effective ESR seen on a rail.

    Counts every capacitor with a pin on the rail whose other pin is GND or
    the opposite analog rail (those are still, at AC, capacitance to a low
    impedance).  Capacitors reaching ADS1299 internal nodes are listed
    separately rather than counted: their far side is not a node this model
    knows the impedance of.
    """
    counted, deferred = [], []
    total = 0.0
    esr_parallel = 0.0
    for ref, other in d.caps_between(rail):
        part = d.parts[ref]
        nom = None
        from extract_subckt import parse_value
        nom = parse_value(part.value, "C")
        if other in ("GND", "AVDD", "AVSS"):
            bias = abs(BIAS.get(rail, 0.0) - BIAS.get(other, 0.0))
            ceff, info = effective_cap(part.lcsc, bias, nominal=nom)
            counted.append({"ref": ref, "to": other, "nominal_F": nom,
                            "eff_F": ceff, "factor": info["factor"],
                            "bias_V": bias, "esr_ohm": info.get("esr_ohm"),
                            "trusted": info.get("trusted")})
            total += ceff
            if info.get("esr_ohm"):
                esr_parallel += 1.0 / info["esr_ohm"]
        else:
            deferred.append({"ref": ref, "to": other, "nominal_F": nom})
    return total, (1.0 / esr_parallel if esr_parallel else 0.05), counted, deferred


def cap_block(counted, rail, node="OUT"):
    """SPICE lines for the counted capacitors, each with its own ESR."""
    out = []
    for i, c in enumerate(counted):
        mid = "cx%d" % i
        far = "0" if c["to"] in ("GND",) else ("avdd_ac" if c["to"] != rail else "0")
        # The opposite analog rail is held by its own regulator, so at AC it
        # is a low impedance: tie those capacitors to ground too, which is
        # the same thing and keeps the deck to one loop.
        far = "0"
        out.append("R%s %s %s %s" % (mid, node, mid, fmt(max(c["esr_ohm"] or 0.02, 1e-3))))
        out.append("C%s %s %s %s" % (mid, mid, far, fmt(c["eff_F"])))
    return "\n".join(out)


def loop_gain(device, counted, load_A):
    """AC loop gain of one LDO on its real output network."""
    caps = cap_block(counted, RAILS[device]["rail"])
    if device == "TLV70025":
        deck = """TLV70025 loop gain
.include %s
Vin IN 0 DC 5
Xu IN 0 IN NCX OUT SENSE TLV70025_CORE
Vinj SENSE OUT DC 0 AC 1
Rload OUT 0 %s
%s
.control
ac dec 60 1 10meg
.endc
.end
""" % (LIB, fmt(2.5 / load_A), caps)
    else:
        deck = """TPS72325 loop gain
.include %s
Vin IN 0 DC -5
Xu 0 IN IN NR OUT SENSE TPS72325_CORE
Cnr NR 0 10n
Vinj SENSE OUT DC 0 AC 1
Rload OUT 0 %s
%s
.control
ac dec 60 1 10meg
.endc
.end
""" % (LIB, fmt(2.5 / load_A), caps)
    res = run_netlist(deck, timeout=300)
    if not res.ok:
        return None, res
    f = [abs(x) for x in res.vector("frequency")]
    vout = res.vector("v(out)")
    vsen = res.vector("v(sense)")
    if not (f and vout and vsen):
        return None, res
    T = [-(a / b) if abs(b) > 0 else 0j for a, b in zip(vout, vsen)]
    return (f, T), res


def load_step(device, counted, load_A, step_A):
    """Load-step transient on the real output network."""
    caps = cap_block(counted, RAILS[device]["rail"])
    sign = 1 if RAILS[device]["nom"] > 0 else -1
    # a 10 us edge, which is fast for an LDO loop but not a discontinuity
    if sign > 0:
        istep = ("Bstep OUT 0 I = %s + %s*min(max((TIME-2e-3)/1e-5,0),1)"
                 % (fmt(load_A), fmt(step_A)))
        deck = """TLV70025 load step
.include %s
Vin IN 0 DC 5
Xu IN 0 IN NCX OUT TLV70025
%s
%s
.options reltol=2e-3 chgtol=1e-14 rshunt=1e9 cshunt=2f
.control
tran 1u 6m 0 5u
.endc
.end
""" % (LIB, istep, caps)
    else:
        istep = ("Bstep 0 OUT I = %s + %s*min(max((TIME-2e-3)/1e-5,0),1)"
                 % (fmt(load_A), fmt(step_A)))
        deck = """TPS72325 load step
.include %s
Vin IN 0 DC -5
Xu 0 IN IN NR OUT TPS72325
Cnr NR 0 10n
%s
%s
.options reltol=2e-3 chgtol=1e-14 rshunt=1e9 cshunt=2f
.control
tran 1u 6m 0 5u
.endc
.end
""" % (LIB, istep, caps)
    return run_netlist(deck, timeout=300)


def survey(checks, numbers):
    """Total the derated capacitance on both rails, in four corners.

    typical/worst-case DC-bias derating x current/proposed BOM.  This is the
    part of the case that does not depend on any device model at all: it is
    arithmetic on manufacturer curves and the netlist.
    """
    import extract_subckt as ex
    table = {}
    for corner in ("typical", "worst_case"):
        old = ex.WORST_CASE
        ex.WORST_CASE = (corner == "worst_case")
        try:
            for bom, swaps in sorted(BOM_VARIANTS.items()):
                dd = Design(part_swaps=swaps)
                for rail in ("AVDD", "AVSS"):
                    total, esr, counted, _ = rail_capacitance(dd, rail)
                    table["%s/%s/%s" % (rail, corner, bom)] = {
                        "derated_F": total,
                        "nominal_F": sum(c["nominal_F"] for c in counted),
                        "esr_ohm": esr,
                    }
        finally:
            ex.WORST_CASE = old
    numbers["capacitance_survey"] = table
    # the criterion has to hold in the worst corner of the CURRENT BOM
    for device, spec in RAILS.items():
        rail = spec["rail"]
        old = table["%s/worst_case/old_C12530_2u2_6v3" % rail]["derated_F"]
        new = table["%s/worst_case/new_C23733_4u7_10v" % rail]["derated_F"]
        checks.append({
            "name": "%s Cout above datasheet minimum in the WORST corner" % device,
            "pass": bool(min(old, new) >= MIN_COUT[device]),
            "detail": "%.2f uF (old C12530 BOM) / %.2f uF (new C23733 BOM), "
                      "worst-case bias+tolerance+temperature, vs %.2f uF "
                      "required effective"
                      % (old * 1e6, new * 1e6, MIN_COUT[device] * 1e6),
        })
    return table


def main():
    d = Design()
    checks, numbers, notes = [], {}, []
    survey(checks, numbers)

    for device, spec in RAILS.items():
        rail = spec["rail"]
        total, esr, counted, deferred = rail_capacitance(d, rail)
        untrusted = [c["ref"] for c in counted if not c["trusted"]]
        numbers["%s_Cout_nominal_F" % rail] = sum(c["nominal_F"] for c in counted)
        numbers["%s_Cout_derated_F" % rail] = total
        numbers["%s_Cout_shrink_pct" % rail] = (
            100.0 * (1 - total / sum(c["nominal_F"] for c in counted)))
        numbers["%s_caps" % rail] = counted
        numbers["%s_caps_not_counted" % rail] = deferred

        # Is the derated capacitance still above the datasheet minimum?
        checks.append({
            "name": "%s Cout above datasheet minimum (typical derating)" % device,
            "pass": bool(total >= MIN_COUT[device]),
            "detail": "%.2f uF derated from %.2f uF marked (-%.0f %%), datasheet "
                      "min %.2f uF effective"
                      % (total * 1e6, sum(c["nominal_F"] for c in counted) * 1e6,
                         numbers["%s_Cout_shrink_pct" % rail], MIN_COUT[device] * 1e6),
        })
        numbers["%s_bulk_esr_ohm" % rail] = esr
        checks.append({
            "name": "%s Cout ESR inside the datasheet's stable band" % device,
            "pass": bool(esr <= MAX_ESR[device]),
            "detail": "%.3f ohm effective (parallel combination) vs %.2f ohm max"
                      % (esr, MAX_ESR[device]),
        })

        # --- loop gain -------------------------------------------------
        got, res = loop_gain(device, counted, spec["load_A"])
        if got is None:
            checks.append({"name": "%s loop gain runs" % device, "pass": False,
                           "detail": (res.error or "") + res.log[-400:]})
        else:
            f, T = got
            fc, pm, dc = su.crossover_and_pm(f, T)
            numbers["%s_loop_dc_gain_dB" % device] = dc
            numbers["%s_crossover_Hz" % device] = fc
            numbers["%s_phase_margin_deg" % device] = pm
            checks.append({
                "name": "%s phase margin >= 45 deg" % device,
                "pass": bool(pm == pm and pm >= 45.0),
                "detail": "PM %.1f deg at fc %.3g Hz (DC loop gain %.1f dB)" % (pm, fc, dc),
            })

        # --- load step -------------------------------------------------
        res = load_step(device, counted, spec["load_A"], spec["step_A"])
        if not res.ok:
            checks.append({"name": "%s load step runs" % device, "pass": False,
                           "detail": (res.error or "") + res.log[-400:]})
        else:
            t = res.vector("time")
            v = res.vector("v(out)")
            settled, pp = su.settles(t, v, 2e-3, 2e-3, settle_window=1.5e-3)
            excursion = max(abs(x - su.final_value(t, v)) for x in v if True)
            numbers["%s_step_residual_pp_V" % device] = pp
            numbers["%s_step_excursion_V" % device] = excursion
            numbers["%s_step_final_V" % device] = su.final_value(t, v)
            checks.append({
                "name": "%s %d mA load step settles" % (device, spec["step_A"] * 1e3),
                "pass": bool(settled),
                "detail": "excursion %.1f mV, residual %.4f mV pp after 1.5 ms, "
                          "final %.4f V" % (excursion * 1e3, pp * 1e3,
                                            numbers["%s_step_final_V" % device]),
            })
        if untrusted:
            notes.append("%s: DC-bias derating for %s is an ESTIMATE, not a "
                         "fetched manufacturer curve." % (rail, ", ".join(sorted(set(untrusted)))))

    notes.append("Loop-gain figures come from behavioural LDO models whose "
                 "internal pole is a calibration choice, so treat the phase "
                 "margin as indicative and the load-step settling as the "
                 "primary evidence. Both are computed on the DERATED "
                 "capacitance taken from the netlist, which is the part of "
                 "this result that is not model-dependent.")
    notes.append("The DC-bias curves are Samsung's own (weblib, 25 C typical). "
                 "The worst-case corner multiplies them by the tolerance low "
                 "limit and by 0.85 for the X5R/X7R temperature coefficient, "
                 "which is the corner a shipped board has to survive.")
    notes.append("Capacitors reaching ADS1299 internal nodes (VCAP1..4, VREFP) "
                 "are listed under *_caps_not_counted and excluded: their far "
                 "side is an internal buffer whose impedance is not modelled. "
                 "Including them would only add capacitance.")

    passed = all(c["pass"] for c in checks)
    doc = su.write_result("ldo_stability", passed, checks, numbers,
                          notes="\n".join(notes),
                          models={
                              "TLV70025": "behavioural (TI's model is encrypted)",
                              "TPS72325": "behavioural HERE ONLY -- the loop-gain "
                                          "measurement needs a feedback terminal to "
                                          "break, which TI's model does not expose. "
                                          "power_tree_startup.py uses TI's own model "
                                          "for this part."})
    su.report(doc)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
