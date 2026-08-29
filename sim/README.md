# `sim/` — headless SPICE for Brain Canvas Rev.A

Circuit simulation of the board as the contract netlist wires it, run
head­lessly from Python. No GUI, no ngspice CLI, no LTspice, no PySpice.

```
python3 sim/run_all.py            # every case -> gates/S3_sim.json
python3 sim/cases/drl_loop.py     # one case  -> sim/out/drl_loop.json
python3 sim/lib/ngspice_ctypes.py # self-test the engine
```

Use `/usr/bin/python3` (3.9, arm64). The KiCad-bundled interpreter at
`/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`
works identically.

## The engine

KiCad 10.0.5 ships the full ngspice shared library, so there is no need to
install anything:

```
/Applications/KiCad/KiCad.app/Contents/Frameworks/libngspice.0.dylib   ngspice-45.2
/Applications/KiCad/KiCad.app/Contents/PlugIns/sim/ngspice/*.cm        XSPICE code models
```

`sim/lib/ngspice_ctypes.py` drives it through the classic sharedspice API
(`ngSpice_Init` / `ngSpice_Command` / `ngGet_Vec_Info`). Both interpreters
`dlopen` it without any codesign or Library Validation trouble — the library
is already signed as part of the KiCad bundle, and both it and the
interpreters are arm64.

Every netlist runs in **its own subprocess**. libngspice keeps global state
and can tear the process down on a fatal error, so isolating each run makes a
blown-up simulation a recoverable event and guarantees circuit N+1 inherits
nothing from circuit N.

## Layout

| Path | What it is |
|---|---|
| `lib/ngspice_ctypes.py` | ctypes driver; `run_netlist(deck) -> SimResult` |
| `lib/extract_subckt.py` | contract netlist + BOM → SPICE elements, with DC-bias derating |
| `lib/simutil.py` | measurement helpers (ripple, settling, phase margin) and the result format |
| `models/behavioral.lib` | behavioural models (TLV70025, AMS1117, ADS1299 BIAS amp, S8050) |
| `models/vendor/` | TI's unencrypted PSpice models for LM2664 and TPS723xx, used **unmodified**, plus thin board-pinout wrappers |
| `models/PROVENANCE.md` | **read this before believing a number** |
| `data/cap_derating.json` | per-LCSC MLCC DC-bias retention, ESR, ESL |
| `cases/*.py` | one script per test, each writing `sim/out/<case>.json` |
| `run_all.py` | runs them all, writes `gates/S3_sim.json` |

## Nothing is typed in twice

Component values and connections are read from
`contract/netlist_easyeda_api_2026-08-28.tsv` and `data/parts_lcsc.csv`, with
`contract/contract_overrides.json` (ECO-5) applied by default. A case script
asks for a set of designators or nets and gets SPICE back:

```python
from extract_subckt import Design
d = Design()                       # as built (overrides applied)
d.numeric_value("R_BIAS_FB")       # 1e6   -- "1M" is megohms, not milliohms
text, report = d.spice(nets=["AVSS"], bias={"AVSS": -2.5, "GND": 0.0})
```

`report["skipped"]` lists everything that was *not* emitted and why, so a
case can prove it did not silently drop a component.

## Vendor models

TI's unencrypted PSpice models are used for the two devices where one exists:

* **LM2664** — SNVMBY1, verbatim. Real oscillator, real 1.25 Ω switches,
  real SD comparator.
* **TPS72325** — SLVMBZ8 (the adjustable TPS72301), re-parameterised to
  −2.5 V. Its enable term is `IF(ABS(V(enb)) > 1.5)`, which is how the
  simulation confirms the board's EN wiring rather than assuming it.

`TLV70025`'s TI model is encrypted and the AMS1117 has none, so those two are
behavioural. `models/PROVENANCE.md` has the full table.

ngspice parses TI's PSpice text unmodified once `set ngbehavior=psa` is
issued **before** the deck is sourced — `run_netlist(..., pre_commands=[...])`.
A `.options` line inside the deck is too late.

## Capacitor derating is not optional here

Every ceramic on this board is class II. `C_NLDO_OUT` is a 2.2 µF 6.3 V X5R
in 0402 biased at 2.5 V; simulating it as 2.2 µF would be self-deception.
The harness derates from `data/cap_derating.json` and totals what is really
there — AVDD and AVSS each lose about 52 % of their marked
capacitance at typical 25 C bias, and about 64 % in the worst corner.

Nine of the eleven rows are **fetched Samsung curves** (weblib, 25 °C,
2026-08-29) and are flagged `trusted: true`; one is a documented estimate and
says so. Each row also carries a worst-case curve — the measurement times the
tolerance low limit times 0.85 for the temperature coefficient — and
`ldo_stability.py` reports both corners, plus a current-versus-proposed BOM
comparison.

Three things the real curves show that a rule of thumb would miss: a 50 V
1206 part still loses 20 % at 5 V; a 25 V 0402 1 µF loses 38 % at 3.3 V (that
is C_EN_DLY, and it is why the ESP32 reset-delay check fails); and a 100 µF
6.3 V 1206 is only 91 µF before any bias is applied.

## Cases

| Case | Asks |
|---|---|
| `power_tree_startup.py` | USB hot-plug at 4.75 / 5.25 V through F1 → AMS1117, TLV70025, LM2664 → TPS72325. Rail values, rise, overshoot, AVSS ripple, and whether TPS72325's EN is asserted |
| `ldo_stability.py` | Loop gain and load-step settling for both analog LDOs on the *derated* output capacitance |
| `drl_loop.py` | ADS1299 BIAS loop through an electrode/body model at 5 k / 20 k / 100 kΩ skin, with the BIAS amp's unpublished GBW swept 10 kHz…1 MHz. Also runs the pre-ECO-5 wiring to quantify what that ECO bought |
| `esp32_autoreset.py` | DTR#/RTS# truth table against esptool's reset sequence, ESP32 pin levels against absolute maximum, and the power-on EN delay |

## ngspice traps worth knowing

Found the hard way while building this; all are silent failures.

1. **`limit(x, lo, hi)` in a B-source returns 0 and raises no error.** It is
   not an ngspice B-source function. Use `min(max(x, lo), hi)`.
2. **`GND` is a reserved global alias for node 0.** A sub-circuit terminal
   named `GND` is silently shorted to ground. The models here use `GNDP`.
3. **A `? :` step on a node that multiplies a current is a discontinuity the
   solver cannot cross** — it shows up as `Timestep too small`. Enable
   comparators here ramp over a narrow window instead.
4. **A fixed DC current sink on a rail that is still at 0 V** drives the t=0
   operating point to kilovolts through whatever leakage resistor the model
   has, and the transient never starts. Loads are gated on their own rail.
5. **An error amplifier with no anti-windup** runs away while its regulator
   is disabled and then demands kiloamps on the first step after enable.
6. `.options rshunt=1e9 cshunt=2f` cures most remaining stiffness.
7. **`set ngbehavior=psa` must be issued before the deck is sourced**, not as
   a `.options` line inside it.
8. **ngspice 45.2's PSpice mode has a start-up race** that kills the library
   roughly half the time with `failed to parse .func in: .func pwr(x a)`.
   Loading the XSPICE code models makes it much less likely (3 in 6 versus
   6 in 6 without); `run_netlist` retries eight times to cover the rest.
   Because of this, PSpice mode is switched on only for decks that actually
   contain a vendor model.
9. **Passing the same node to two formals of a sub-circuit** can stall a
   transient. The board ties LM2664 SD to V+ and TPS72325 EN to IN, so both
   vendor wrappers insert a 1 mΩ isolation resistor.
10. TI's vendor models are stiff enough that they will not converge inside
    the full power-tree deck; each runs in its own focused deck instead.

## Possible future replacement

[`spicelib`](https://github.com/nunobrum/spicelib) offers a common API over
ngspice and LTspice plus Monte Carlo / worst-case tooling, and would be a
reasonable replacement for `lib/ngspice_ctypes.py` if tolerance analysis is
ever wanted. Not adopted now: it needs a `pip` install, which the command
sandbox blocks, and the ctypes driver already does what these cases need.
