#!/usr/bin/env python3
"""Case (d): the two-transistor DTR/RTS auto-reset circuit.

As wired in the contract netlist (resistor values come from the parts table,
never from this file -- R29-6 moved the two base resistors and the case has
to follow the BOM, not a number typed here):

    CH_DTR_N --R_Q_EN_B(470k)-> Q_EN.B     Q_EN.E  = CH_RTS_N
                                Q_EN.C  = ESP_EN   <--R_EN_UP(10k)-- VDD_ESP
                                                   <--C_EN_DLY(1u)-- GND
    CH_RTS_N --R_Q_IO0_B(470k)> Q_IO0.B    Q_IO0.E = CH_DTR_N
                                Q_IO0.C = ESP_IO0  <--R_IO0_UP(10k)- VDD_ESP

Both transistors are S8050 NPN.  The cross-coupling is the point: neither
transistor can pull its output low unless the two handshake lines differ, so
opening the port (which drives both lines the same way) never resets the chip.

Two questions:

  1. Does the truth table match what esptool drives?  The CH340C's DTR#/RTS#
     pins are inverting, so esptool's ClassicReset sequence
         DTR=0,RTS=1 -> DTR#=H, RTS#=L  (assert reset)
         DTR=1,RTS=0 -> DTR#=L, RTS#=H  (release reset with IO0 low)
         DTR=0,RTS=0 -> DTR#=H, RTS#=H  (run)
     must produce EN and IO0 levels the ESP32 reads as the intended logic.

  2. Does EN release only after the 3.3 V rail has settled?  R_EN_UP with
     C_EN_DLY is the power-on reset delay, and C_EN_DLY is a class-II
     ceramic, so the answer depends on the DC-bias derating, not on the
     printed 1 uF.

The CH340C runs from USB_5V (netlist: U_USB pin 16 VCC -> USB_5V) with V3
decoupled to ground, which is its 5 V supply mode: DTR# and RTS# swing to
5 V, not 3.3 V.  That matters, because a 5 V base sitting above a 3.3 V
collector forward-biases the base-collector junction of an "off" transistor.
Whether that lifts ESP_EN above the ESP32's absolute maximum is precisely
the sort of thing worth asking a simulator rather than assuming.

What this case found, and what was done about it (R29-6, 2026-08-29)
--------------------------------------------------------------------
With the original 10 k base resistors it lifted ESP_EN to 4.238 V and
ESP_IO0 to 4.203 V, against an absolute maximum of VDD+0.3 = 3.6 V.

The first mitigation proposed was 100 k, on the reasoning that ten times the
resistance is a tenth of the injected current.  This case rejected that: the
off-side transistor is not a diode but a transistor in REVERSE-ACTIVE mode
(B-C forward biased, B-E reverse biased), so the collector pushes (1 + BR)
times the base current into the node -- measured 7.63 uA of base current
against 38.71 uA of injection, a ratio of 5.07 against the model's BR = 4.
On top of that the loop self-limits: raising R lowers the node, which raises
the drop across R, so 10 k -> 100 k cut the current only 2.4x (93.85 ->
38.71 uA) and left ESP_EN at 3.687 V, still over the limit.

470 k was adopted instead: ESP_EN 3.414 V, ESP_IO0 3.398 V, injection
11.40 uA.  It was chosen over 330 k and 1 M by sweeping the S8050's reverse
beta over BR = 1..10, which is the least constrained parameter in a generic
Gummel-Poon fit and is not published in the S8050 datasheet.  100 k passes
only for BR <= 2 and 150 k / 220 k fail at BR >= 7; 330 k passes throughout
but with only 8 mV of margin at BR = 10; 470 k holds 3.347..3.523 V across
the whole range, i.e. 77 mV of margin in the worst corner, while keeping
more base drive than 1 M.

The EN delay criterion
----------------------
This check used to demand "EN rises >= 10 ms after the 3.3 V rail", which is
not a requirement anyone publishes.  Espressif's requirement is that EN be
held low until the supply is stable -- the ESP32-WROOM-32E/32UE datasheet
recommends the 10 k / 1 uF RC on EN as a way to achieve that, without naming
a minimum delay.  So the criterion is now rail-settled-before-EN: the 3.3 V
rail reaches 99 % at about 0.3 ms and EN does not reach VIH until about
8.5 ms, so the rail is settled roughly 28x over before the chip is released.
The old 10 ms threshold made the DERATED capacitor (0.62 uF, from a fetched
Samsung curve) "fail" at 8.55 ms while the marked 1 uF "passed" at 13.85 ms,
which was an artifact of the invented threshold and not a defect.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))

from extract_subckt import Design, parse_value, effective_cap, fmt  # noqa: E402
from ngspice_ctypes import run_netlist                              # noqa: E402
import simutil as su                                                # noqa: E402

LIB = os.path.join(os.path.dirname(HERE), "models", "behavioral.lib")

VDD = 3.3
VIH = 0.75 * VDD          # ESP32 datasheet: VIH min = 0.75 VDD
VIL = 0.25 * VDD          # ESP32 datasheet: VIL max = 0.25 VDD
VABSMAX = VDD + 0.3       # ESP32 absolute maximum on a digital pin
IO0_PULLUP = 45e3         # ESP32 internal weak pull-up on IO0

# esptool ClassicReset, expressed at the CH340 pins (which invert).
# (name, DTR# level, RTS# level, expected EN, expected IO0)
SEQUENCE = [
    ("idle / run          (host DTR=0 RTS=0)", "H", "H", "H", "H"),
    ("assert reset        (host DTR=0 RTS=1)", "H", "L", "L", "H"),
    ("release into loader (host DTR=1 RTS=0)", "L", "H", "H", "L"),
    ("both asserted       (host DTR=1 RTS=1)", "L", "L", "H", "H"),
]


def ch340_supply(d):
    """The net feeding CH340C VCC decides its I/O swing."""
    return d.net_of("U_USB", "16")


def build_truth_deck(d, dtr_v, rts_v, vio):
    """Steady-state deck for one (DTR#, RTS#) combination."""
    r_qen_b = d.numeric_value("R_Q_EN_B")
    r_qio0_b = d.numeric_value("R_Q_IO0_B")
    r_en_up = d.numeric_value("R_EN_UP")
    r_io0_up = d.numeric_value("R_IO0_UP")
    cen = parse_value(d.parts["C_EN_DLY"].value, "C")
    return """ESP32 auto reset truth table
.include %s
Vdd vdd_esp 0 DC %s
Vdtr ch_dtr_n 0 DC %s
Vrts ch_rts_n 0 DC %s
R_Q_EN_B  ch_dtr_n q_en_b %s
R_Q_IO0_B ch_rts_n q_io0_b %s
R_EN_UP   vdd_esp esp_en %s
R_IO0_UP  vdd_esp esp_io0 %s
C_EN_DLY  esp_en 0 %s
* ESP32 pin loading: EN is high impedance, IO0 has a weak internal pull-up
Ren_in esp_en 0 10e6
Rio0_pu esp_io0 vdd_esp %s
* Q_EN : B=Q_EN_B  E=CH_RTS_N  C=ESP_EN
Q_EN  esp_en q_en_b ch_rts_n S8050
* Q_IO0: B=Q_IO0_B E=CH_DTR_N  C=ESP_IO0
Q_IO0 esp_io0 q_io0_b ch_dtr_n S8050
.options rshunt=1e9 gmin=1e-12
.control
op
.endc
.end
""" % (LIB, fmt(VDD), fmt(dtr_v * vio), fmt(rts_v * vio), fmt(r_qen_b),
       fmt(r_qio0_b), fmt(r_en_up), fmt(r_io0_up), fmt(cen), fmt(IO0_PULLUP))


def build_poweron_deck(d, cen_farad, ramp_s=200e-6):
    """VDD_ESP ramps up with both handshake lines idle high."""
    r_en_up = d.numeric_value("R_EN_UP")
    return """ESP32 power-on EN delay
.include %s
Vdd vdd_esp 0 PWL(0 0 100u 0 %s %s 200m %s)
Vdtr ch_dtr_n 0 DC 0
Vrts ch_rts_n 0 DC 0
R_Q_EN_B  ch_dtr_n q_en_b %s
R_EN_UP   vdd_esp esp_en %s
C_EN_DLY  esp_en 0 %s
Ren_in esp_en 0 10e6
Q_EN  esp_en q_en_b ch_rts_n S8050
.options rshunt=1e9 gmin=1e-12
.control
tran 20u 60m 0 100u
.endc
.end
""" % (LIB, fmt(100e-6 + ramp_s), fmt(VDD), fmt(VDD),
       fmt(d.numeric_value("R_Q_EN_B")), fmt(r_en_up), fmt(cen_farad))


def level(v):
    if v >= VIH:
        return "H"
    if v <= VIL:
        return "L"
    return "?"


def main():
    d = Design()
    checks, numbers, notes = [], {}, []

    vcc_net = ch340_supply(d)
    vio = 5.0 if vcc_net == "USB_5V" else 3.3
    numbers["ch340_vcc_net"] = vcc_net
    numbers["ch340_io_swing_V"] = vio
    # Straight from data/parts_lcsc.csv, so the gate records the BOM it was
    # actually run against rather than the values in this file's docstring.
    numbers["resistors"] = {
        ref: {"ohm": d.numeric_value(ref), "lcsc": d.parts[ref].lcsc,
              "value": d.parts[ref].value}
        for ref in ("R_Q_EN_B", "R_Q_IO0_B", "R_EN_UP", "R_IO0_UP")}
    notes.append("CH340C VCC is on net %s, so its DTR#/RTS# outputs swing to "
                 "%.1f V." % (vcc_net, vio))

    # ---------------- truth table ---------------------------------------
    table, all_ok, absmax_ok = [], True, True
    for name, dtr, rts, exp_en, exp_io0 in SEQUENCE:
        deck = build_truth_deck(d, 1 if dtr == "H" else 0, 1 if rts == "H" else 0, vio)
        res = run_netlist(deck, timeout=120)
        if not res.ok:
            checks.append({"name": "truth table %s runs" % name, "pass": False,
                           "detail": (res.error or "") + res.log[-300:]})
            all_ok = False
            continue
        ven = res.vector("v(esp_en)")[0]
        vio0 = res.vector("v(esp_io0)")[0]
        got = (level(ven), level(vio0))
        ok = got == (exp_en, exp_io0)
        over = max(ven, vio0) > VABSMAX
        absmax_ok = absmax_ok and not over
        all_ok = all_ok and ok
        table.append({"state": name, "DTR#": dtr, "RTS#": rts,
                      "EN_V": ven, "IO0_V": vio0,
                      "EN": got[0], "IO0": got[1],
                      "expected": [exp_en, exp_io0], "match": ok,
                      "over_absmax": over})
    numbers["truth_table"] = table

    # Same sweep with 3.3 V handshake levels, purely as a comparison: if the
    # absolute-maximum check fails at 5 V and passes at 3.3 V, the finding is
    # about the CH340C's supply mode and not about the topology.
    alt = []
    for name, dtr, rts, exp_en, exp_io0 in SEQUENCE:
        deck = build_truth_deck(d, 1 if dtr == "H" else 0, 1 if rts == "H" else 0, 3.3)
        res = run_netlist(deck, timeout=120)
        if res.ok:
            alt.append({"state": name, "EN_V": res.vector("v(esp_en)")[0],
                        "IO0_V": res.vector("v(esp_io0)")[0]})
    numbers["truth_table_if_ch340_were_3v3"] = alt
    if alt:
        numbers["worst_pin_V_at_3v3_io"] = max(max(r["EN_V"], r["IO0_V"]) for r in alt)
    numbers["esp32_thresholds"] = {"VIH_V": VIH, "VIL_V": VIL, "abs_max_V": VABSMAX}
    checks.append({
        "name": "EN/IO0 truth table matches the esptool reset sequence",
        "pass": all_ok,
        "detail": "; ".join("%s->EN=%s,IO0=%s%s"
                            % (r["DTR#"] + r["RTS#"], r["EN"], r["IO0"],
                               "" if r["match"] else " MISMATCH")
                            for r in table),
    })
    checks.append({
        "name": "EN and IO0 stay within the ESP32 absolute maximum",
        "pass": absmax_ok,
        "detail": "worst EN %.3f V, worst IO0 %.3f V, limit %.2f V"
                  % (max(r["EN_V"] for r in table), max(r["IO0_V"] for r in table), VABSMAX)
                  if table else "no data",
    })

    # ---------------- power-on EN delay ----------------------------------
    part = d.parts["C_EN_DLY"]
    cnom = parse_value(part.value, "C")
    ceff, info = effective_cap(part.lcsc, VDD, nominal=cnom)
    numbers["C_EN_DLY_nominal_F"] = cnom
    numbers["C_EN_DLY_derated_F"] = ceff
    numbers["C_EN_DLY_derating_trusted"] = info.get("trusted")
    numbers["C_EN_DLY_source"] = info.get("source")

    delays = {}
    for tag, cval in (("nominal", cnom), ("derated", ceff)):
        res = run_netlist(build_poweron_deck(d, cval), timeout=300)
        if not res.ok:
            delays[tag] = {"error": (res.error or "") + res.log[-200:]}
            continue
        t = res.vector("time")
        ven = res.vector("v(esp_en)")
        vdd = res.vector("v(vdd_esp)")
        t_rail = su.time_to_reach(t, vdd, 0.95 * VDD)
        t_rail99 = su.time_to_reach(t, vdd, 0.99 * VDD)
        t_en = su.time_to_reach(t, ven, VIH)
        delays[tag] = {"C_F": cval, "t_rail_95pct_s": t_rail,
                       "t_rail_99pct_s": t_rail99,
                       "t_EN_VIH_s": t_en, "delay_s": t_en - t_rail,
                       "margin_over_rail_99pct_s": t_en - t_rail99}
    numbers["en_delay"] = delays

    # Criterion: rail-settled-before-EN. Espressif requires EN to stay low
    # until the supply is stable and recommends the 10 k / 1 uF RC as the way
    # to get there; it names no minimum delay, so the check is that the rail
    # really is settled first -- measured on the DERATED capacitor, which is
    # the pessimistic end.
    der = delays.get("derated", {})
    dly = der.get("delay_s", float("nan"))
    t_en_d = der.get("t_EN_VIH_s", float("nan"))
    t_r99 = der.get("t_rail_99pct_s", float("nan"))
    ratio = (t_en_d / t_r99) if t_r99 else float("nan")
    numbers["en_release_vs_rail_settle_ratio"] = ratio
    checks.append({
        "name": "EN releases only after the 3.3 V rail has settled",
        "pass": bool(t_en_d > t_r99),
        "detail": "3.3 V rail reaches 99 %% at %.2f ms; EN reaches VIH at "
                  "%.2f ms (%.2f ms later, %.0fx the rail settling time) with "
                  "the DERATED %.2f uF. With the marked %.2f uF EN releases at "
                  "%.2f ms. Espressif specifies no minimum delay -- only that "
                  "EN stay low until the supply is stable."
                  % (t_r99 * 1e3, t_en_d * 1e3, dly * 1e3, ratio, ceff * 1e6,
                     cnom * 1e6,
                     delays.get("nominal", {}).get("t_EN_VIH_s", float("nan")) * 1e3),
    })
    notes.append(
        "EN-delay criterion: this check previously demanded 'EN rises >= "
        "10 ms after the 3.3 V rail'. No datasheet states that threshold. "
        "Espressif's ESP32-WROOM-32E/32UE datasheet recommends the 10 k / "
        "1 uF RC on EN so that EN stays low until the supply is stable, "
        "without naming a minimum. Against the invented 10 ms the DERATED "
        "capacitor 'failed' at %.2f ms while the marked value 'passed' at "
        "%.2f ms -- an artifact of the threshold, not a defect. The criterion "
        "is now rail-settled-before-EN, which is what the part actually "
        "requires; the delay is still reported so the number stays visible."
        % (dly * 1e3,
           delays.get("nominal", {}).get("delay_s", float("nan")) * 1e3))

    if not info.get("trusted"):
        notes.append("The EN-delay verdict hinges on C_EN_DLY's DC-bias "
                     "derating (%s, %.0f %% retention at 3.3 V), and that "
                     "figure is an ENGINEERING ESTIMATE, not a fetched "
                     "manufacturer curve. Marked value passes, derated value "
                     "may not: this check is only as good as that number."
                     % (part.lcsc, info["factor"] * 100))
    if not absmax_ok:
        notes.append(
            "ABSOLUTE-MAXIMUM FINDING: with the CH340C on %s its DTR#/RTS# "
            "outputs idle at %.1f V. Both transistors are then off with a "
            "base above their 3.3 V collector, which forward-biases the "
            "base-collector junction and lifts ESP_EN and ESP_IO0 to about "
            "%.2f V -- past the ESP32's %.2f V maximum. The same deck with "
            "3.3 V handshake levels peaks at %.2f V, so this is a consequence "
            "of the CH340C's supply mode, not of the reset topology."
            % (vcc_net, vio, max(r["EN_V"] for r in table), VABSMAX,
               numbers.get("worst_pin_V_at_3v3_io", float("nan"))))
    else:
        notes.append(
            "The CH340C on %s still idles its DTR#/RTS# outputs at %.1f V and "
            "still forward-biases the off-side base-collector junctions; "
            "R29-6's %.0f k base resistors do not remove that injection, they "
            "bound it. ESP_EN idles at %.3f V and ESP_IO0 at %.3f V against "
            "the %.2f V absolute maximum -- inside the limit, but above the "
            "3.3 V rail. Measure both pins at bring-up rather than treating "
            "the margin as proven."
            % (vcc_net, vio, d.numeric_value("R_Q_EN_B") / 1e3,
               max(r["EN_V"] for r in table), max(r["IO0_V"] for r in table),
               VABSMAX))

    # Reported whether or not the absolute-maximum check passes: this one is
    # not fixed by the base resistors and must not disappear from the gate the
    # moment the EN/IO0 finding is closed.
    notes.append(
        "INFORMATIONAL, NOT FIXED (Rev.B): U_USB pin 2 TXD drives ESP_RXD "
        "(U_MCU pin 34) directly with no level shift, so with the CH340C in "
        "its %.1f V supply mode that pin sees the same overvoltage the reset "
        "transistors were injecting -- and here it is a driven push-pull "
        "output, not a leakage path, so no resistor value bounds it. R29-6 "
        "does nothing for this. The root fix is to run the CH340C from 3.3 V "
        "(VCC = 3.3 V with V3 tied to VCC), which is a copper change and is "
        "therefore deferred to Rev.B; it would close the EN/IO0 injection and "
        "the TXD path at once. Confirm the CH340C's output level in 5 V "
        "supply mode against its datasheet before acting on this." % vio)
    notes.append("Transistors use a generic Gummel-Poon S8050 fit (BF=275, "
                 "the middle of the J3Y 200..350 bin). The absolute-maximum "
                 "check depends on the base-collector junction parameters, "
                 "which are the least well pinned down part of that fit -- "
                 "treat a marginal result as a reason to measure, not as proof.")

    passed = all(c["pass"] for c in checks)
    doc = su.write_result("esp32_autoreset", passed, checks, numbers,
                          notes="\n".join(notes),
                          models={"S8050": "behavioural (generic Gummel-Poon fit)",
                                  "ESP32 pins": "resistive/threshold model",
                                  "CH340C": "ideal 5 V push-pull driver"})
    su.report(doc)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
