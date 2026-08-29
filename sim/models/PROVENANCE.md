# Model provenance

Where every number in `sim/` came from, and how much weight it can carry.

Two of the four active devices use **TI's own unencrypted PSpice models, run
unmodified**. The other two are behavioural models written for this board,
and every result says which is which.

## Vendor models

| Part | TI document | Status |
|---|---|---|
| LM2664 | SNVMBY1 (datasheet SNVS005E) | **obtained, unencrypted, runs unmodified** — `vendor/lm2664_ti_pspice.lib` |
| TPS72325 | SLVMBZ8, the adjustable TPS72301 (datasheet SLVS346E) | **obtained, unencrypted, runs unmodified** — `vendor/tps72301_ti_pspice.lib`, re-parameterised to −2.5 V in `vendor/tps72325_ti.lib` |
| TLV70025 | SLVM174 (datasheet SLVSA00E) | **encrypted only.** No TINA-TI equivalent found. Behavioural model used. |
| AMS1117 | — | No manufacturer SPICE model exists. Behavioural model used. |

No hand conversion of TI's text was needed. ngspice parses it once
`set ngbehavior=psa` is issued **before** the deck is sourced — a `.options`
line inside the deck is too late, because by then `IF()`/`VALUE{}` have
already failed. `sim/lib/ngspice_ctypes.py` takes `pre_commands` for exactly
this.

Two consequences worth knowing:

* The vendor models are stiff. TI's LM2664 has a hard `IF()` on its
  quiescent-current source and the TPS723xx enable is `IF(ABS(...))`; putting
  either inside the full power-tree deck (four regulators, five ferrites,
  forty derated capacitors) stalls the transient at the first rail crossing
  no matter how the USB ramp is shaped. So the full-tree transient runs on
  behavioural models and `vendor_crosscheck()` in `power_tree_startup.py`
  runs each TI model **alone**, on the board's own derated capacitors, for
  the questions a vendor model answers best.
* ngspice 45.2's PSpice mode has a start-up race that kills the library
  about half the time (`failed to parse .func in: .func pwr(x a)`). Measured
  rates and the retry that covers it are documented in `ngspice_ctypes.py`.

### What the vendor models settled

* **TPS72325 EN.** TI's `ldo_basic` implements the enable as
  `IF(ABS(V(enb,vgnd) + hysteresis) > venb, 1, 0)` with `venb = 1.5` — an
  *absolute value*. The TPS723xx EN pin is **bipolar**, not active-low:
  SLVS346E §6.3.2 gives on for EN ≥ +1.5 V *or* ≤ −1.5 V, off only inside a
  ±0.4 V dead band. The board ties EN to IN (≈ −5 V), the datasheet's own
  always-enabled wiring, inside the −10…+5 V recommended EN range. Simulated:
  as wired → −2.500 V; EN forced to 0 V → −0.002 V. This was the single
  riskiest assumption in the whole exercise and it is now the vendor's answer,
  not ours.
* **LM2664 output resistance** on the board's *derated* 2.85 µF flying
  capacitor: 11.5 Ω, against SNVS005E's 12 Ω typical / 25 Ω maximum.
* **LM2664 SD polarity**: SD tied to V+ = running (SNVS005E: ≥ 2 V run,
  ≤ 0.8 V shutdown). TI's model uses 0.4·VIN / 0.2·VIN thresholds.

## Behavioural models

| Device | What is faithful | What is calibrated |
|---|---|---|
| TLV70025 | 2.5 V out, dropout ceiling, 220 mA limit, 31 µA Iq, EN high ≥ 0.9 V, SOT-23-5 pinout 1=IN 2=GND 3=EN 4=NC 5=OUT (SLVSA00E) | internal pole (20 MHz), PSRR feedthrough capacitor, pass-device K |
| AMS1117-3.3 | 3.3 V out, dropout fit V_do = 0.45 + 1.0·I (1.25 V at 800 mA vs datasheet 1.3 V max), 5 mA Iq | loop dynamics — **its load-step response is optimistic and its stability is NOT assessed** |
| ADS1299 BIAS amp | ±2.5 V rails, 100 Ω R_out, output clamp; **GBW 100 kHz is now a datasheet figure** | open-loop gain, input capacitance and output swing are not published; `drl_loop.py` sweeps GBW 10 kHz…1 MHz anyway so no conclusion rests on one value |
| S8050 | BF = 275 (middle of the J3Y 200–350 bin), f_T ≈ 133 MHz vs datasheet 100–150 MHz | base-collector junction parameters — these drive the absolute-maximum finding, so treat it as a reason to measure |
| GZ2012D601TF ferrite | L = 955 nH from the rated Z = 600 Ω @ 100 MHz | R_dc 0.20 Ω |
| SMD1206P050TF PTC | — | 0.55 Ω, between R_min 0.35 and R_1max 1.20 |

## Datasheet figures used, with their source

* **TPS72325** (SLVS346E): PSRR 65 dB @ 1 kHz, 48 dB @ 10 kHz, 40 dB @
  100 kHz. 80 kHz is not tabulated, so `power_tree_startup.py` uses the
  100 kHz figure — the lowest of the three, above our frequency, so the
  ripple verdict errs towards failing. C_out ≥ 1.0 µF **effective** (2.2 µF
  marked), ESR 0–0.5 Ω. Current limit 300 mA min.
* **TPS72325 ships as two silicon revisions under one part number**:
  legacy (CSO DLN) 280 mV dropout, 130 µA Iq, 1 ms startup, ±3.0 % V_out;
  newer (DM6) 140 mV, 30 µA, 8 ms, ±1.6 %. TI's model carries the legacy
  numbers, which are the worse ones, and that is what is simulated.
* **TLV70025** (SLVSA00E): C_out ≥ 0.1 µF effective (1 µF recommended),
  ESR < 200 mΩ, Iq 31 µA, current limit 220 mA min, t_startup 100 µs,
  UVLO 1.9 V, EN high 0.9 V min. Dropout 43 mV at 50 mA is quoted for the
  2.8 V option and 175/250 mV at 200 mA for the 2.35 V option; the 2.5 V
  option's own figures are not published, so the model interpolates.
* **LM2664** (SNVS005E): R_out 12 Ω typ / 25 Ω max at 40 mA *including
  external capacitor ESR*, R_sw 4/8 Ω, f_SW 80 kHz typ with a **40 kHz
  minimum**, V+ 1.8–5.5 V, I_q 220 µA, **40 mA maximum output current**, no
  FC pin. Pinout 1=GND 2=OUT 3=CAP− 4=SD 5=V+ 6=CAP+.
* **ADS1299 BIAS amplifier** (SBAS499): GBW 100 kHz, slew rate 0.07 V/µs,
  short-circuit current 1.1 mA, common-mode range AVSS+0.3 to AVDD−0.3,
  recommended external feedback 1 MΩ ∥ 1.5 nF (a 106 Hz pole — exactly what
  ECO-5 restores). Open-loop gain, output swing and input capacitance are
  not published.

## Capacitor derating

`sim/data/cap_derating.json`: nine of eleven rows are **fetched Samsung
curves** (weblib.samsungsem.com, 25 °C, typical sample, 2026-08-29) and are
marked `trusted: true`. The C0G/NP0 row needs no curve — bias independence
follows from the dielectric class. One row (C1588, the 1 nF input
common-mode capacitors) is a documented estimate and appears only where the
result is insensitive to it.

Each row also carries a `bias_retention_worst_case` curve: the same
measurement times the tolerance low limit times 0.85 for the X5R/X7R
temperature coefficient. `ldo_stability.py` reports both corners.

Three findings from the real curves that a rule of thumb would have missed:

1. "A 50 V part used at 5 V does not derate" is **false** for CL31A106KBHNNNE
   (C13585): −4 % at 3.3 V, −20 % at 5 V.
2. CL05A105KA5NQNC (C52923) is a 25 V part and still loses 38 % at 3.3 V.
   It is C_EN_DLY, and the ESP32 power-on reset delay is computed from it —
   which is why that check fails.
3. CL31A107MQHNNNE (C15008) is already 91 µF of its marked 100 µF at zero
   bias and keeps 41 % at 3.3 V.

## Numbers that decide a verdict and are still assumptions

1. **CH340C output level in 5 V supply mode.** `esp32_autoreset.py` assumes
   DTR#/RTS# swing to VCC = 5 V, which is what produces the absolute-maximum
   finding. Confirm against the WCH datasheet before acting on it.
2. **ADS1299 internal BIAS_SENSP switch resistance = 100 Ω**, and the
   assumption that the board's 10 kΩ R_IN?? resistors are the DRL summing
   network. The DRL phase margin is insensitive to both — it is dominated by
   the local R_BIAS_FB feedback — so this is a small risk.
3. **Electrode/body model**: Rskin ∥ 10 nF per electrode, 100 pF body-to-
   circuit-ground stray, mains coupled through 5 pF. Standard lumped values,
   not measured on a patient.

## What depends on no model at all

* Every component value, net and connection comes from
  `contract/netlist_easyeda_api_2026-08-28.tsv` and `data/parts_lcsc.csv`
  via `sim/lib/extract_subckt.py`. Nothing is typed into a case script, so a
  BOM edit changes the answers on the next run.
* ECO-5 is applied from `contract/contract_overrides.json`, so the DRL case
  simulates the board as built and can reproduce the pre-ECO wiring exactly.
* The capacitance survey in `ldo_stability.py` is arithmetic on manufacturer
  curves and the netlist.
* The auto-reset truth table is topology: it follows from the cross-coupled
  transistors and would be the same with any reasonable NPN.
