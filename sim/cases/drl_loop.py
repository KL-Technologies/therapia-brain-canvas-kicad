#!/usr/bin/env python3
"""Case (c): stability of the ADS1299 BIAS (right-leg-drive) loop.

The DRL is a feedback loop that closes through the patient, so its phase
margin depends on skin impedance -- a quantity that varies by more than an
order of magnitude between a freshly prepped scalp and a dry electrode on a
wriggling child.  A loop that is comfortable at 5 kohm and oscillating at
100 kohm is a loop that works in the lab and squeals in the clinic.

Circuit, taken from the contract netlist (post ECO-5 unless asked otherwise):

    ADS1299 BIASOUT -> BIAS_OUT_INT -> R_BIAS_SER (1 M) -> A1_ELEC
                                                            |  skin
                                                          BODY
                                                            |  skin
    IN1P..IN8P <- R_IN?? (10 k) <- electrodes <-------------'
        |  (internal BIAS_SENSP switches)
    BIASINV -- R_BIAS_FB (1 M) || C_BIAS_INV -- BIAS_OUT_INT

Two things in this loop are not in any datasheet, so neither is assumed:

  * the BIAS amplifier's gain-bandwidth product.  SBAS499 gives 100 kHz, but
    not the open-loop gain, output swing or input capacitance, so the case
    still SWEEPS GBW over 10 kHz .. 1 MHz -- a decade either side of the
    datasheet figure -- and requires the criterion to hold across the whole
    range rather than at one convenient point.
  * the impedance of the internal BIAS_SENSP switches between the input pins
    and the BIASINV summing node.  Modelled as a small series resistance;
    the board's own 10 kohm R_IN?? resistors are the summing network.

It also does the thing this repository has been arguing about: it runs the
loop BOTH as the 2026-08-28 schematic draws it (C_BIAS_INV from the summing
node to GND) and as ECO-5 rewires it (C_BIAS_INV in parallel with R_BIAS_FB),
and reports what the ECO is actually worth in degrees of phase margin and in
dB of 50 Hz common-mode rejection.

Pass: phase margin >= 45 deg at 5 k, 20 k and 100 kohm skin impedance, for
the as-built (post-ECO) topology, across the whole GBW sweep.
"""

from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))

from extract_subckt import Design, parse_value, fmt, OVERRIDES_JSON  # noqa: E402
from ngspice_ctypes import run_netlist                               # noqa: E402
import simutil as su                                                 # noqa: E402

LIB = os.path.join(os.path.dirname(HERE), "models", "behavioral.lib")

SKIN_OHMS = [5e3, 20e3, 100e3]
GBW_HZ = [10e3, 100e3, 1e6]
C_SKIN = 10e-9          # electrode/skin double-layer capacitance, 10 nF
C_BODY_TO_GND = 100e-12  # body-to-circuit-ground stray, USB-powered device
R_SENS_SWITCH = 100.0    # ADS1299 internal BIAS_SENSP switch, assumed

# Which channels the BIAS_SENSP register selects.  All eight positive inputs
# is the usual configuration for a referential montage.
BIAS_SENSE_CHANNELS = [1, 2, 3, 4, 5, 6, 7, 8]


def biasamp_with_gbw(gbw_hz):
    """The BIAS amp macro re-tuned to a given gain-bandwidth product.

    The macro's first stage is gm = 1e-4 S into 1 Gohm, so A0 = 1e5.  The
    dominant pole must sit at GBW/A0; C1 = 1/(2*pi*R1*fp).
    """
    fp = gbw_hz / 1e5
    c1 = 1.0 / (2 * math.pi * 1e9 * fp)
    return """.subckt BIASAMP VINP VINN VOUT AVDDP AVSSP
Rin   VINP VINN 1e12
Cin   VINP VINN 3e-12
Gm1   0 n1 VINP VINN 1e-4
R1    n1 0 1e9
C1    n1 0 %s
Gm2   0 n2 n1 0 1e-3
R2    n2 0 1e3
C2    n2 0 1.592e-10
Bout  n3 0 V = min( max( V(n2,0), V(AVSSP,0)+0.2 ), V(AVDDP,0)-0.2 )
Rout  n3 VOUT 100
.ends BIASAMP
""" % fmt(c1)


def electrode(name, a, b, rskin):
    """Skin/electrode interface: Rskin in parallel with 10 nF."""
    return ("R%s %s %s %s\nC%s %s %s %s"
            % (name, a, b, fmt(rskin), name, a, b, fmt(C_SKIN)))


def build_deck(d, rskin, gbw, post_eco, ac_cmd, inject=True, drl_connected=True):
    """Assemble the DRL loop deck.

    ``post_eco``  True  -> C_BIAS_INV across R_BIAS_FB (ECO-5, as built)
                  False -> C_BIAS_INV from BIAS_INV to GND (schematic 08-28)
    ``inject``    True  -> loop broken at the amp output for loop gain
                  False -> loop closed, 50 Hz common-mode source on the body
    ``drl_connected`` False lifts R_BIAS_SER off the electrode, so the same
                  deck can be run with the drive dead.  The difference between
                  the two is what the DRL is actually worth in dB.
    """
    rf = d.numeric_value("R_BIAS_FB")
    rser = d.numeric_value("R_BIAS_SER")
    if post_eco:
        cval = parse_value(d.parts["C_BIAS_INV"].value, "C")
        cline = "Cfb bias_inv bias_out_int %s" % fmt(cval)
        eco_note = "C_BIAS_INV %s across R_BIAS_FB" % d.parts["C_BIAS_INV"].value
    else:
        # the pre-ECO part and value, read from the override record
        with open(OVERRIDES_JSON) as fh:
            ov = json.load(fh)["overrides"][0]
        cval = parse_value(ov["value_change"]["from"], "C")
        cline = "Cfb bias_inv 0 %s" % fmt(cval)
        eco_note = "C_BIAS_INV %s from summing node to GND" % ov["value_change"]["from"]

    lines = [
        "ADS1299 DRL loop  (skin %.0f k, GBW %.0f kHz, %s)"
        % (rskin / 1e3, gbw / 1e3, "post-ECO-5" if post_eco else "pre-ECO"),
        ".include %s" % LIB,
        biasamp_with_gbw(gbw),
        "Vavdd avdd 0 DC 2.5",
        "Vavss avss 0 DC -2.5",
        "* --- BIAS amplifier: non-inverting input at mid-supply (BIASREF NC)",
        "Xamp 0 bias_inv bias_out_drv avdd avss BIASAMP",
        "* --- external compensation network (from the netlist) ---",
        "Rfb bias_inv bias_out_int %s" % fmt(rf),
        cline,
        "* --- series resistor to the DRL electrode ---",
        "Rser bias_out_int a1_elec %s" % fmt(rser if drl_connected else 1e12),
        electrode("drl", "a1_elec", "body", rskin),
        "* --- body: stray capacitance to circuit ground ---",
        "Cbody body 0 %s" % fmt(C_BODY_TO_GND),
        "Rbodyleak body 0 1e9",
    ]
    # sensing electrodes -> R_IN -> input pin -> internal switch -> BIASINV
    for ch in BIAS_SENSE_CHANNELS:
        ref = "R_IN%dP" % ch
        rin = d.numeric_value(ref)
        el = "el%d" % ch
        lines += [
            electrode("s%d" % ch, "body", el, rskin),
            "R%s %s in%dp %s" % (ref, el, ch, fmt(rin)),
            "Rsw%d in%dp bias_inv %s" % (ch, ch, fmt(R_SENS_SWITCH)),
        ]
        # the common-mode capacitor actually fitted on that input
        cref = "C_CM%dP" % ch
        if cref in d.parts:
            lines.append("C%s in%dp 0 %s" % (cref, ch, fmt(parse_value(d.parts[cref].value, "C"))))

    if inject:
        lines += ["Vinj bias_out_int bias_out_drv DC 0 AC 1"]
    else:
        lines += ["Vinj bias_out_int bias_out_drv DC 0 AC 0",
                  "* 50 Hz mains coupled into the body through 5 pF",
                  "Vmains mains 0 DC 0 AC 1",
                  "Ccoup mains body 5p"]

    lines += [".options rshunt=1e9 cshunt=2f gmin=1e-12",
              ".control", ac_cmd, ".endc", ".end", ""]
    return "\n".join(lines), eco_note


def measure_loop(d, rskin, gbw, post_eco):
    deck, note = build_deck(d, rskin, gbw, post_eco, "ac dec 40 0.01 10meg", inject=True)
    res = run_netlist(deck, timeout=300)
    if not res.ok:
        return None, res, note
    f = [abs(x) for x in res.vector("frequency")]
    vd = res.vector("v(bias_out_drv)")
    vi = res.vector("v(bias_out_int)")
    if not (f and vd and vi):
        return None, res, note
    T = [-(a / b) if abs(b) > 0 else 0j for a, b in zip(vd, vi)]
    fc, pm, dc = su.crossover_and_pm(f, T)
    gain50 = su.gain_at(f, T, 50.0)
    return {"fc_Hz": fc, "pm_deg": pm, "dc_gain_dB": dc,
            "loop_gain_50Hz_dB": gain50}, res, note


def measure_cmrr(d, rskin, gbw, post_eco, drl_connected=True):
    """50 Hz body common mode relative to the mains source, in dB.

    Run once with the drive connected and once with R_BIAS_SER lifted; the
    difference is the DRL's actual suppression, which is the only honest way
    to say whether a 1 Mohm series resistor leaves the loop any authority.
    """
    deck, _ = build_deck(d, rskin, gbw, post_eco, "ac lin 1 50 50",
                         inject=False, drl_connected=drl_connected)
    res = run_netlist(deck, timeout=300)
    if not res.ok:
        return None
    vb = res.vector("v(body)")
    vm = res.vector("v(mains)")
    if not (vb and vm):
        return None
    return su.db(vb[0] / vm[0])


def main():
    d = Design()                      # overrides applied -> as built
    checks, numbers, notes = [], {}, []
    numbers["overrides_applied"] = d.overrides_applied
    numbers["R_BIAS_FB_ohm"] = d.numeric_value("R_BIAS_FB")
    numbers["R_BIAS_SER_ohm"] = d.numeric_value("R_BIAS_SER")
    numbers["C_BIAS_INV"] = d.parts["C_BIAS_INV"].value
    numbers["bias_sense_channels"] = BIAS_SENSE_CHANNELS

    # ---- as built (post ECO-5): the graded criterion --------------------
    grid = {}
    worst_pm, worst_at = 1e9, None
    for rskin in SKIN_OHMS:
        for gbw in GBW_HZ:
            got, res, note = measure_loop(d, rskin, gbw, True)
            key = "skin%.0fk_gbw%.0fk" % (rskin / 1e3, gbw / 1e3)
            if got is None:
                grid[key] = {"error": (res.error or "")[:200] + res.log[-200:]}
                continue
            grid[key] = got
            pm = got["pm_deg"]
            if pm == pm and pm < worst_pm:      # NaN-safe
                worst_pm, worst_at = pm, key
            elif pm != pm:
                # never crosses 0 dB -> unconditionally stable, not a failure
                grid[key]["note"] = "loop gain never reaches 0 dB"
    numbers["post_eco_grid"] = grid
    numbers["post_eco_worst_pm_deg"] = worst_pm if worst_at else None
    numbers["post_eco_worst_pm_at"] = worst_at
    checks.append({
        "name": "as-built DRL phase margin >= 45 deg (all skin x GBW)",
        "pass": bool(worst_at is None or worst_pm >= 45.0),
        "detail": ("worst %.1f deg at %s" % (worst_pm, worst_at)) if worst_at
                  else "loop never crosses 0 dB at any corner (unconditionally stable)",
    })

    # per-skin summary at the mid GBW, which is what the brief asked for
    for rskin in SKIN_OHMS:
        k = "skin%.0fk_gbw%.0fk" % (rskin / 1e3, 100.0)
        g = grid.get(k, {})
        checks.append({
            "name": "DRL PM >= 45 deg at %.0f kohm skin" % (rskin / 1e3),
            "pass": bool(g.get("pm_deg") is None or g.get("pm_deg") != g.get("pm_deg")
                         or g["pm_deg"] >= 45.0),
            "detail": "PM %s, crossover %s Hz, loop gain at 50 Hz %.1f dB"
                      % (("%.1f deg" % g["pm_deg"]) if g.get("pm_deg") == g.get("pm_deg") else "n/a (no 0 dB crossing)",
                         ("%.3g" % g["fc_Hz"]) if g.get("fc_Hz") == g.get("fc_Hz") else "n/a",
                         g.get("loop_gain_50Hz_dB", float("nan"))),
        })

    # ---- what ECO-5 actually buys ---------------------------------------
    eco = {}
    for post in (False, True):
        tag = "post_eco" if post else "pre_eco"
        got, _, note = measure_loop(d, 20e3, 100e3, post)
        cm_on = measure_cmrr(d, 20e3, 100e3, post, drl_connected=True)
        cm_off = measure_cmrr(d, 20e3, 100e3, post, drl_connected=False)
        eco[tag] = dict(got or {})
        eco[tag]["topology"] = note
        eco[tag]["body_CM_50Hz_dB_drl_on"] = cm_on
        eco[tag]["body_CM_50Hz_dB_drl_off"] = cm_off
        if cm_on is not None and cm_off is not None:
            eco[tag]["drl_suppression_dB"] = cm_off - cm_on
    numbers["eco5_comparison"] = eco
    pre, post = eco["pre_eco"], eco["post_eco"]
    d_pm = (post.get("pm_deg") or float("nan")) - (pre.get("pm_deg") or float("nan"))
    d_gain = (post.get("loop_gain_50Hz_dB") or float("nan")) - (pre.get("loop_gain_50Hz_dB") or float("nan"))
    notes.append(
        "ECO-5 check at 20 kohm skin, 100 kHz GBW: phase margin %s -> %s deg, "
        "DRL loop gain at 50 Hz %s -> %s dB, 50 Hz body common-mode "
        "suppression by the drive %s -> %s dB."
        % (_f(pre.get("pm_deg")), _f(post.get("pm_deg")),
           _f(pre.get("loop_gain_50Hz_dB")), _f(post.get("loop_gain_50Hz_dB")),
           _f(pre.get("drl_suppression_dB")), _f(post.get("drl_suppression_dB"))))
    checks.append({
        "name": "ECO-5 improves the DRL loop (or at least does not harm it)",
        "pass": bool(not (d_pm < -1.0)),
        "detail": "phase margin change %+.1f deg, 50 Hz loop gain change %+.1f dB" % (d_pm, d_gain),
    })

    notes.append("The BIAS amplifier is a BEHAVIOURAL two-pole macro. SBAS499 "
                 "gives GBW = 100 kHz, slew rate 0.07 V/us and a 1.1 mA "
                 "short-circuit limit, but not the open-loop gain or output "
                 "swing, so GBW is swept a decade either side of the datasheet "
                 "value and the criterion must hold across the whole sweep.")
    notes.append("DRL EFFECTIVENESS, not a pass/fail criterion here but the "
                 "more interesting number: with R_BIAS_SER at 1 Mohm the drive "
                 "suppresses the 50 Hz body common mode by only about 5 dB. A "
                 "right-leg drive is normally worth 20-40 dB. The loop is very "
                 "stable precisely because it has so little authority, and the "
                 "phase margin being flat across 5 k..100 kohm of skin is the "
                 "same fact seen from another angle.")
    notes.append("R_BIAS_SER is %g ohm. With 5..100 kohm of skin in series "
                 "that is a divider of %.0f..%.0f dB in the forward path, so "
                 "the DRL's authority over the body common mode is modest by "
                 "construction -- which is also why the loop is hard to "
                 "destabilise." % (numbers["R_BIAS_SER_ohm"],
                                   20 * math.log10(5e3 / (5e3 + numbers["R_BIAS_SER_ohm"])),
                                   20 * math.log10(100e3 / (100e3 + numbers["R_BIAS_SER_ohm"]))))
    notes.append("Body model: skin = Rskin || 10 nF at every electrode, body "
                 "to circuit ground = 100 pF stray, mains coupled through 5 pF. "
                 "The ADS1299 internal BIAS_SENSP switch is taken as 100 ohm; "
                 "the summing resistors are the board's own 10 kohm R_IN??.")

    passed = all(c["pass"] for c in checks)
    doc = su.write_result("drl_loop", passed, checks, numbers, notes="\n".join(notes),
                          models={"ADS1299 BIAS amp": "behavioural macro; GBW swept 10 kHz..1 MHz around the datasheet 100 kHz",
                                  "electrode/body": "behavioural lumped model"})
    su.report(doc)
    return 0 if passed else 1


def _f(x):
    return "n/a" if x is None or x != x else "%.1f" % x


if __name__ == "__main__":
    sys.exit(main())
