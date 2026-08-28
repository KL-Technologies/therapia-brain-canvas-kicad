# ADS1299 レイアウト チェックリスト — 一次資料ベース

対象: Brain Canvas Rev.A（ADS1299 TQFP-64 + ESP32 モジュール + CH340C SOP-16 / 4 層 / 61.8236 × 45.0088 mm / JLCPCB）
作成: 2026-08-28 / 調査は read-only。**基板は編集していない。**

## 凡例

| タグ | 意味 |
|---|---|
| **[HARD]** | データシート等の**明示的な要求**。原文を verbatim で引用する |
| **[PRACTICE]** | 一次資料に基づく良習。要求ではない |
| **[INFERENCE]** | **筆者の技術的推論・計算**。一次資料には無い |

主要文献: **ADS1299 データシート SBAS499C**（July 2012 – Rev. Jan 2017、83 頁）以下「DS」
https://www.ti.com/lit/ds/symlink/ads1299.pdf

---

## ⚠ 最初に読むこと — この文書が数字を書かない場所

**TI はデカップリングコンデンサの配置距離を一切数値で示していない。**
DS Figure 77/78 の NOTE も §12.1 も「as close as possible」だけである。
**「◯ mm 以内」という数字を作ってはいけない。**

数値ではなく**幾何学的に判定できる**一次資料の要求は 1 つだけ:

> **DS §12.1 verbatim:**
> *"**Do not place vias between bypass capacitors and the active device.**
> Placing the bypass capacitors on the same layer as close to the active device yields the best results."*

→ **判定基準は「ビアの有無」と「同一層か」。距離ではない。** これが唯一、機械チェックにできる HARD ルール。

---

## 文献番号の訂正（依頼の前提が誤っていた点）

| 依頼時の想定 | 事実 |
|---|---|
| SBAU204（ADS1299 EVM ユーザーガイド） | **存在しない（404）。正しくは SLAU443B** "EEG Front-End Performance Demonstration Kit"（64 頁）https://www.ti.com/lit/pdf/SLAU443 |
| TIDA-00175（EEG リファレンスデザイン） | **BiSS エンコーダ**。TIDA-00011 = 光学心拍+BLE、TIDA-00376 = 火災報知器ドライバ、TIDA-01227 = ステッパモータ。**ADS129x を使いレイアウト節を持つ現行 TI Design は存在しない** |
| SBAA160（ECG/EEG 信号チェーン） | ADS1299 を一切扱わず、**"layout" "ground plane" の出現が 0**。この用途には使えない |
| SBAA188 | RLD の理論と値は持つが**レイアウト節が無い** |

**最も近い代替**: **SBAU181B**（ADS1298R ECG-FE EVM）。**§A.2 が唯一「内層の役割」を明記**:
*"Figure 45. **Internal Ground Plane (Layer 2)** / Figure 46. **Internal Power Plane (Layer 3)**"*
→ **TI 自身の ADS129x EVM が Sig / GND / PWR / Sig であることの一次証拠。**

---

## A. デカップリング / 電源

### A-1 [HARD] ビアを挟まない・同一層に置く ★機械チェック可能

> DS §12.1: *"Do not place vias between bypass capacitors and the active device.
> Placing the bypass capacitors on the same layer as close to the active device yields the best results."*

**判定**: ADS1299 の各電源ピンと対応するバイパスコンデンサの間の配線に**ビアが 0 個**であること、
かつコンデンサが**IC と同じ層**にあること。

> **本基板での該当箇所**（STATUS.md「§設計上の発見」より）:
> - **C_VCAP3 の pin1 が 3.36 mm、C_VCAP3_H が 2.29 mm**（S4 から未変更）
> - **C_VCAP1 が 2.50 mm 移動**（S4、1206 化のため）
>
> **距離の閾値は TI が示していないので「3.36 mm は長すぎる」とは一次資料からは言えない。**
> **言えるのは「その経路にビアが入っていないか」「同一層か」だけ。S7 でこれを機械判定すること。**

### A-2 [HARD] 全デカップリングを「できる限り近く」に

> DS Figure 77/78 の NOTE（p.71）: *"Place the capacitors for supply, reference, and VCAP1 to VCAP4 as close to the package as possible."*

**数値は無い。**

### A-3 [HARD] ピン別の必須コンデンサ値（DS Pin Functions, p.6–7）

| ピン | 番号 | 要求 |
|---|---|---|
| AVDD | 19, 21, 22, 56, 59 | 1 µF → AVSS |
| AVDD（charge pump） | 59 | 1 µF → **AVSS pin 58**（ピン指定） |
| AVDD1 | 54 | 1 µF → AVSS1 |
| DVDD | 48, 50 | 1 µF → DGND |
| **VCAP1** | 28 | **100 µF** → AVSS |
| VCAP2 | 30 | 1 µF → AVSS |
| VCAP3 | 55 | **1 µF ∥ 0.1 µF** → AVSS |
| VCAP4 | 26 | 1 µF → AVSS |
| **VREFP** | 24 | **最小 10 µF → VREFN**（VREFP-VREFN 間、差動的に） |

### A-4 [HARD] ⚠ DS 内部で値が食い違っている

- **§11 Power Supply Recommendations (p.70)**: *"Bypass each device supply with **10-μF and 0.1-μF** solid ceramic capacitors."*
- **Pin Functions 表と Figure 77/78**: **1 µF + 0.1 µF**

**TI 自身の不整合。** 安全側に倒すなら各電源に 10 µF + 0.1 µF。
**どちらか一方を「TI の要求」と断言してはいけない。**

### A-5 [HARD] VREFP に 0.1 µF 並列は DS の要求ではない

Figure 77/78 のネットリストを追った限り、VREFP-VREFN には **10 µF のみ**。
0.1 µF 並列は一般的慣行ではあるが **DS には記載が無い**。

### A-6 [HARD] ★見落としやすい最重要項目 — AVDD1 / AVSS1 はスター接続

> DS §11 verbatim: *"AVDD1 provides the supply to the charge pump block and **has transients at fCLK**.
> Therefore, **star connect AVDD1 to the AVDD pins and AVSS1 to the AVSS pins**."*

**ADS1299 はチップ内部にチャージポンプを持ち、2.048 MHz でスイッチングしている。**
AVDD1/AVSS1 をベタで AVDD/AVSS に繋ぐと、そのリップルがアナログ電源全体に載る。
**細い専用配線で 1 点接続すること。**

**判定**: AVDD1(54) / AVSS1 が AVDD / AVSS プレーンに面で接続されていないこと。

### A-7 [HARD] VCAP1 の誘電体材質

> DS §11 verbatim: *"in systems where the board is subjected to high- or low-frequency vibration,
> install a nonferroelectric capacitor, such as a **tantalum or class 1 capacitor (C0G or NPO)**.
> EIA class 2 and class 3 dielectrics such as (X7R, X5R, X8R, and so forth) are ferroelectric.
> The piezoelectric property of these capacitors can appear as electrical noise...
> **When using internal reference, noise on the VCAP1 node results in performance degradation.**"*

**装着型 EEG は「振動あり」と見なすべき。** 100 µF C0G は現実には入手困難なのでタンタルを検討。
→ **`data/parts_lcsc.csv` の VCAP1 の誘電体を確認すること。X5R/X7R なら設計判断として記録が要る。**

---

## B. グラウンド — 「分割 vs ベタ」論争の決着

### B-1 [HARD] ADS1299 の公式回答

> DS §12.1 verbatim:
> *"**The ground plane can be split into an analog plane (AGND) and digital plane (DGND), but is not necessary.**
> Place digital signals over the digital plane, and analog signals over the analog plane.
> As a final step in the layout, **the split between the analog and digital grounds must be connected together at the ADC**."*

**→ 分割は任意。ただし分割するなら ADC 直下で必ず結合。分割必須でもベタ必須でもない。**

### B-2 [HARD] 一次資料が真っ向から対立している事実

| 出典 | 立場 |
|---|---|
| **ADI MT-031**（Rev.A 10/08） | **split 派**: *"**When in doubt, it is always better to start out with a split analog and digital ground plane and later connect them with jumpers**, rather than to start out with a single ground plane and try and later try and split it!"* |
| **TI SLYT512** | **単一プレーン派**: *"**A better approach is partitioning. It is always preferable to use only one ground plane, partitioning the PCB into analog and digital sections**... use a single ground plane, partition it into analog and digital sections, and apply discipline in routing."* |
| **TI SLYT499** | 単一派: *"Although the split-plane approach can be made to work, it has many problems—especially in large, complex systems."* / *"**Remember that a data converter is analog!** Thus, the AGND and DGND pins should be connected to the analog ground plane."* |
| **Henry Ott** | 単一派: *"Do not split the ground plane. Use one solid ground plane."* |

**全ソースが一致している物理的根拠は 1 点のみ**:
**危険なのは分割そのものではなく、信号トレースがプレーンのスリットをまたぐこと**（リターン経路の断絶 → 大ループ）。

### B-3 [PRACTICE] 本基板の推奨解

**L2 を単一の切れ目のないベタ GND とし、分割はせず、「配置による分離（partitioning）」で
ADS1299 のアナログ側と ESP32 / CH340C のデジタル側を物理的に分ける。**

理由 3 つ:
1. DS が分割を必須としていない（B-1）
2. **ESP32 の RF リターンと USB 差動対のリファレンス連続性は単一プレーンでないと成立しない**
3. 分割すると SPI がスリットをまたぐリスクが必ず生じ、DS §12.1 の要求（B-4）に真っ向から反する

### B-4 [HARD] ★S7 の機械チェック項目 — リターン経路の連続性

> DS §12.1 verbatim: *"Provide good ground return paths. Signal return currents flow on the path of least impedance.
> **If the ground plane is cut or has other traces that block the current from flowing right next to the signal trace**,
> then the current must find another path to return to the source... If current is forced into a longer path,
> the chances that the signal radiates increases."*

**判定基準**: **SPI（SCLK / DIN / DOUT / CS / DRDY）および USB D+/D− の直下 L2 に、
スリット・他レイヤのビアアンチパッド列・他の配線が一切ないこと。**

### B-5 [HARD] 信号層の空き領域は GND で埋める

> DS §12.1: *"Fill void areas on signal layers with ground fill."*

※ ただし C-8（高 Z 入力部）とは緊張関係にある。入力部だけは例外扱いを検討する。

### B-6 [PRACTICE] 実測による裏づけ

TI **SBAA052A**: ADC の AGND/DGND を ADC 直下で結合したが**そこから長いトレースでシステム GND に戻した**基板で
DLE **±0.4 LSB** → コンバータ直下の単一グラウンドプレーンに戻す設計で **±0.1 LSB** に改善。
*"using ground planes is the best way to set up grounding systems for high-resolution ADCs."*

---

## C. アナログ入力（電極入力）

### C-1 [HARD] 差動コンデンサを使う。GND 落としの個別 RC は劣る

> DS §10.2.2 verbatim: *"the filter is advised to be formed by using a **differential capacitor CFilt that shunts the inputs
> rather than individual RC filters whose capacitors shunt to ground**. The differential capacitor configuration
> **significantly improves common-mode rejection** because this approach removes dependence on component mismatch."*

> DS §12.1 verbatim: *"Analog inputs with differential connections **must** have a capacitor placed differentially
> across the inputs. The differential capacitors must be of high quality. **The best ceramic chip capacitors are C0G (NPO)**."*

### C-2 [HARD] ⚠ TI 自身の EVM が上記助言に従っていない

**SLAU443B**（ADS1299EEG-FE）の実回路は **4.99 kΩ 1% × 各ライン + 4.7 nF × 各ラインを AGND へ**、
つまり**差動コンデンサではなく片側ごとの GND 落とし RC**。DS Figure 74 も 4.99 kΩ / 4.7 nF を示す。

**→ 設計判断: DS の本文（差動）を採用すべき。** EVM は測定器用途で、CMRR より各ライン独立性を優先したと推測される。

### C-3 [INFERENCE — 筆者の計算] コーナー周波数

TI は**コーナー周波数を一切明記していない。** 4.99 kΩ / 4.7 nF から:

| 構成 | 計算 | f |
|---|---|---|
| 差動（各脚に R、C は P-N 間） | 1/(2π·2R·C) = 1/(2π·9.98k·4.7n) | **約 3.4 kHz** |
| EVM 構成（C は各々 AGND へ） | 1/(2π·R·C) | **約 6.8 kHz** |

### C-4 [HARD] ★エイリアシングの真の脅威は fMOD であって、データレートではない

> DS §10.2.2 verbatim: *"The cutoff frequency for the filter can be placed well past the data rate of the ADC
> because of the delta-sigma ADC filter-then-decimate topology. **Take care to prevent aliasing around the first
> repetition of the digital decimation filter response at fMOD. Assuming a 2.048-MHz fCLK, fMOD = 1.024 MHz.**"*

> DS §9.3.2.1.1 verbatim: *"The ADS1299-x **pass band repeats itself at every fMOD**.
> The input R-C antialiasing filters in the system should be chosen such that any interference in frequencies
> around multiples of fMOD are attenuated sufficiently."*

**[INFERENCE]** 3.4 kHz の 1 次極なら 1.024 MHz で約 **−50 dB**。足りるかは環境次第。

> **本基板への適用**: **ESP32 の Wi-Fi バースト・USB 12 Mbps・電源の DC-DC が
> 1.024 MHz の整数倍近傍に成分を持たないことを確認する意味がここにある。**
> → §F-4 で LM27762（2 MHz）を避ける根拠になる。

### C-5 [HARD] EMI 環境ではコモンモードコンデンサを追加。ただし差動の 1/10〜1/20 以下

> DS §10.2.2 verbatim: *"If the system is likely to be exposed to high-frequency EMI, adding very small-value,
> common-mode capacitors to the inputs is advisable... **the capacitors should be 10 or 20 times smaller than
> the differential capacitor** to ensure their effect of CMRR is minimized."*

**[INFERENCE]** Cdiff = 4.7 nF なら CM 側は **235–470 pF**。

### C-6 [HARD] RFilt の下限は医療規格が決める。TI は値を示さない

> DS §10.2.2 verbatim: *"The value of RFilt has a minimum set by technical standards for medical electronics."*
> — **DS は数値を出していない。**

参考値として **TI SBAA188**: *"In a system with VS = 5V, the minimum value of the resistor needed is **100kΩ**;
if a 3-V power supply is used, a **60-kΩ** resistor can limit..."*（IEC の 50 µA 漏れ電流基準）

> **⚠ これは ECG の患者直接接続の話で、4.99 kΩ とは 20 倍違う。**
> **用途（患者接続の有無、絶縁の有無）で決まるので、この 2 つを混同しないこと。**

### C-7 [HARD] 入力の絶対最大定格と保護

- DS §7.1: アナログ入力 **AVSS − 0.3 V 〜 AVDD + 0.3 V**、連続電流（電源ピン以外の任意ピン）**±10 mA**
- DS 脚注: *"Input pins are diode-clamped to the power-supply rails. **Limit the input current to 10 mA or less**
  if the analog input voltage exceeds AVDD + 0.3 V or is less than AVSS – 0.3 V."*
- ESD 定格（DS §7.2）: HBM **±1000 V** / CDM **±500 V**

**[INFERENCE]** ±2.5 V バイポーラ運用時、入力許容は **−2.8 V 〜 +2.8 V しかない。**
基板外に出る電極ケーブルには外部 ESD 保護が必須（**HBM 1 kV は人体接触に対して不十分**）。
**TI はこの保護素子を指定していない。**

### C-8 [HARD] 未使用アナログ入力は AVDD へ直結

> DS p.6 脚注: *"Connect unused analog inputs directly to AVDD."*

**GND でもオープンでもない。**

### C-9 [数値] 入力インピーダンス / バイアス電流（DS §7.5）

| 項目 | 値 |
|---|---|
| 入力容量 | 20 pF |
| 入力バイアス電流 | **±300 pA**（25°C および −40〜+85°C） |
| DC 入力インピーダンス | **1000 MΩ**（lead-off オフ）/ **500 MΩ**（lead-off 電流源オン、6 nA） |

### C-10 [PRACTICE + INFERENCE] ガードリング

**TI SCDA042**（"Guarding in Multiplexer Applications", May 2022）:
> *"it is best to **bury sensitive nets within the PCB** itself"*
> *"implement a **'boxing' ring** around the entire net... the layers above and below also provide shielding
> by being at the same potential as the guard traces... **shields the net 360°**"*
> *"the design must ensure that the guard is well generated... **incorporate a precision buffer** to be able to drive the guard appropriately."*

**→ SCDA042 は寸法（ギャップ幅・リング幅）を一切示していない。数字は無い。**

**[INFERENCE]** SCDA042 の自例（*"At just a 5 V potential difference... trace to trace resistance in the Gigaohm range,
this would amount to nA's worth of leakage"*）から: 5 V / 1 GΩ = 5 nA は
ADS1299 のバイアス電流 300 pA の**約 16 倍**。**表面リークは実際に効く。**

ただし **ADS1299 にはガード駆動出力ピンが存在しない**ため、真のドリブンガードには外部バッファが必要。
**現実解**: (a) 電極入力トレース近傍に高電位ネット（AVDD / DVDD / USB）を通さない、
(b) 入力部の GND ベタ埋めをあえて避ける（B-5 との緊張関係を意識して判断する）。

---

## D. リファレンスと BIAS

### D-1 [HARD] 内部リファレンス使用時は VREFN を AVSS に接続

> DS §9.3.1.3.4: *"When using the internal voltage reference, connect VREFN to AVSS."*

内部 VREF = **4.5 V**（AVSS 基準）。

### D-2 [HARD・数値] ★リファレンスの帯域制限は 10 Hz 未満

> DS §9.3.1.3.4 verbatim: *"The external band-limiting capacitors determine the amount of reference noise contribution.
> For high-end EEG systems, **the capacitor values should be chosen such that the bandwidth is limited to less than 10 Hz**
> so that the reference noise does not dominate system noise."*

**VCAP1 の 100 µF と VREFP の 10 µF がこの役割。**
→ **A-3 の値を減らすと直接ノイズフロアが悪化する。BOM 最適化で容量を落としてはいけない。**

### D-3 [HARD] ★重大な起動時の落とし穴 — デフォルトは外部リファレンスモード

> DS §9.3.1.3.4 verbatim: *"**By default, the device wakes up in external reference mode.**"*

内部リファレンスを使うなら CONFIG3 の PD_REFBUF を明示的に立てる必要がある。
**ファームで忘れると全チャネルが無出力に見える。**（ハードのバグと誤診しやすい）

### D-4 [PRACTICE] BIAS ループの帯域決定素子

> **SLAU443B §7.1.3** verbatim: *"The bandwidth of the BIAS loop is determined by **R8 (390kΩ) and C20 (10nF)**."*
> （BOM: R8 = 392 kΩ 1%, C20 = 10 nF）— **ADS1299 EEG-FE の実装値**

DS §10.2.2: BIAS アンプの DC ゲインは RBias と有効チャネル数で決まり、
*"the **330-kΩ** resistors at each PGA output are in parallel for common-mode signals"*（チップ内部値）

**⚠ 比較**: ECG 版 SBAU181B は本文で 392 k / 10 nF と書きながら BOM・回路図は **1 MΩ / 1.5 nF**（TI のコピペミス。SBAA188 が 1 MΩ/1.5 nF を裏づけ）。
**EEG には SLAU443B の 392 k / 10 nF を採る。**

### D-5 [注意・二次情報] OpenBCI Cyton は BIAS フィードバックを持たない

TI E2E スレッド 1057136（直接 fetch は 403、検索インデックス経由のため確度は落ちる）:
Cyton は DS Figure 47 が推奨する BIASOUT → BIASINV の RC フィードバックを持たず、
**BIAS_REF を AGND に接続、BIASINV はオープン**。単体基板ではバイアスアンプが負レールに飽和しうる、との指摘。
デイジーチェーン用の意図的設計とも説明されている。

**→ Cyton をコピーする際に無批判に真似てはいけない箇所。**

### D-6 [FYI] SRB1 / SRB2

DS §10.2.2: リファレンシャルモンタージュでは基準電極を **SRB1** に接続し、MISC1 レジスタの SRB1 ビットで全チャネル負入力に内部接続。
SRB1/SRB2 は Analog input/output であり、**アナログ入力と同格に扱う**
（DS Pin Functions: *"Patient stimulus, reference, and bias signal"*）。

---

## E. クロック・リセット・モードピン

### E-1 [PRACTICE] ★設計上の大きな利点 — この基板に外部発振子は存在しない

> DS §9.3.2.2 Table 6: **CLKSEL = 1, CLK_EN = 0 → 内部発振器動作、CLK ピンは 3-state**（外部部品不要）
> CLKSEL = 0 → 外部クロック入力（1.5 / **2.048** / 2.25 MHz、DS §7.3）

- **ADS1299 は内部発振器選択時、水晶キープアウトの問題が存在しない**
- ESP32 側の水晶は WROOM モジュール内に封止済み
- **CH340C も水晶不要**（下記 H-4）

**→ したがって本基板に「クロック キープアウト」を要する外部発振子は原則存在しない。**
S7 のチェックリストからクロック関連の項目を落としてよい（CLKSEL の結線だけ確認する）。

### E-2 [HARD] モードピンは抵抗経由でタイ

> DS p.6 脚注: *"Set the two-state mode setting pins high to DVDD or low to DGND through **≥10-kΩ** resistors."*（CLKSEL 等）

### E-3 [HARD] 固定接続の要求

| ピン | 要求 |
|---|---|
| **RESV1 (31)** | *"Reserved for future use, **connect directly to DGND**"* |
| NC (27, 29) / Reserved (64) | *"leave as open circuit"* |
| 未使用 GPIO1–4 | *"Connect to DGND with a **≥10-kΩ** resistor if unused."* |

> **⚠ ECO-1 との関係**: `gates/netlist_diff.json` の 8 本のうち
> **RESV1(31) = GND、GPIO1–4(42/44/45/46) = GND** はまさにこの要求。
> ただし DS は GPIO を **≥10 kΩ 経由**と言っており、契約は**直結 GND**。
> **RESV1 は「directly to DGND」なので契約が正しいが、GPIO1–4 の直結は DS の文言とは異なる。**
> S4 で契約どおり適用済み＝**回路図が正**という本パイプラインの原則に従った結果であり、
> 基板側の作業としては正しい。**設計上の申し送りとして記録に残すこと。**

### E-4 [HARD] 電源投入シーケンス

> DS §11.1: *"Before device power up, **all digital and analog inputs must be low**."*
> tPOR = **2^18 tCLK**、tRST(min) = **2 tCLK**（Table 30）
> *"Issue the reset after tPOR or after the **VCAP1 voltage is greater than 1.1 V**, whichever time is longer."*
> *"When using an external clock, tPOR timing does not start until CLK is present and valid."*

**[INFERENCE]** 2^18 / 2.048 MHz = **約 128 ms**。加えて VCAP1 = 100 µF の充電時間。
**ESP32 のブートより ADS1299 の準備が遅い可能性がある。** ファーム側で待つこと。

### E-5 [HARD] SPI 配線

> DS §12.1: *"Route digital lines away from analog lines."*
> DS Figure 80 のコールアウト: *"**Long digital input lines terminated with resistors to prevent reflection**"* /
> *"Via to AVSS pour or plane"* / *"Via to digital ground pour or plane"*

**→ TI は終端抵抗値も「long」の閾値も示していない。数字は無い。**
機械判定できるのは B-4（SPI 直下 L2 の連続性）のみ。

### E-6 [HARD] デジタル回路の配置

> DS §11: *"place the digital circuits (DSP, microcontrollers, FPGAs, and so forth) in the system so that
> **the return currents on those devices do not cross the analog return path of the device**."*

**ESP32 と CH340C のリターン電流が ADS1299 直下を通らない配置にする。** B-3 の partitioning と同じ要求。

---

## F. ±2.5 V バイポーラ生成

### F-1 [HARD] ★AVSS to DGND の絶対最大定格は −3 V 〜 +0.2 V

DS §7.1。**±2.5 V 運用では 0.5 V しかマージンが無い。**
負電源の起動時オーバーシュートが −3 V を超えると破壊する。

### F-2 [PRACTICE] TI EVM の実装構成（SLAU443B, Table 3）

**U6 = TPS60403**（チャージポンプ反転、+5 V → −5 V）→ **U8 = TPS72325DBVT**（負 LDO, −2.5 V）+ **U9 = TPS73225DBVT**（正 LDO, +2.5 V）

**→ チャージポンプ出力を直接 AVSS にせず、必ず LDO で後処理する構成。**
本基板も TPS72325 を持っている（`gates/netlist_diff.json` の B1 = TPS72325 pin3 EN）ので同系統。

### F-3 [HARD] TPS60403 のレイアウト節は 1 段落しかない

> TPS60403（SLVS324C）§11.1 **全文** verbatim:
> *"**All capacitors should be soldered as close as possible to the IC.**
> A PCB layout proposal for a single-layer board is shown in Figure 11-1.
> Care has been taken to connect all capacitors as close as possible to the circuit
> to achieve optimized output voltage ripple performance."*

数値: フライングキャップ **C(fly) = 1 µF**、CI = 1 µF、CO = 1 µF、入力バイパス **0.1 µF**、スイッチング **固定 250 kHz**。

> **⚠ "loop area" という語も「スイッチングのリターン電流をアナロググラウンドから分離せよ」という記述も、
> この DS には存在しない。数値を作らないこと。**

### F-4 [HARD] LM27762 のレイアウト節が唯一「1 点集中リターン」を明記

> LM27762（SNVSAF7C）§7.4.1 verbatim: *"Place CIN on the top layer (same layer as the LM27762) and as close as possible
> to the device... **The returns for both CIN and CCPOUT must come together at one point, as close as possible to the GND pin.**...
> **For best performance the ground connection for COUT must connect back to the GND connection at the thermal pad of the device.**"*

スイッチング **2 MHz typ**（1.7–2.3 MHz）、C(fly) 0.47–1 µF、CIN 4.7 µF、CCP 4.7–10 µF、LDO 出力 2.2 µF。

> **[INFERENCE] 2 MHz は ADS1299 の fMOD = 1.024 MHz の 2 倍近傍にあり、C-4 のエイリアシング窓に入りうる。**
> **250 kHz の TPS60403 の方がこの点では安全。** 部品変更を検討する際の判断材料。

### F-5 [HARD] TPS7A39 のグラウンド分離指示（数値ではないが明確）

> TPS7A39（SBVS263B）§7.4.1.1 verbatim: *"TI recommends that the board be designed with
> **separate ground planes for VIN and VOUT, with each ground plane star connected only at the GND pin of the device**."* /
> *"**Every capacitor must be placed as close as possible to the device and on the same side of the PCB as the regulator.
> Do not place any of the capacitors on the opposite side of the PCB.**"*

**→ どの TI 電源 DS も「as close as possible」以上の定量的距離を示していない。mm の数字は存在しない。**
機械判定できるのは「**コンデンサがレギュレータと同じ面にあるか**」（＝ A-1 と同型のチェック）。

---

## G. ESP32（RF）

### G-1 [HARD] ⚠ 重要な否定的発見 — Espressif はモジュール実装時の銅箔キープアウト寸法を公表していない

公式ドキュメント（https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html
および ESP32-WROOM-32E/32UE Datasheet v2.1）の該当節は**完全に定性的**:

> *"It is suggested to place the module's on-board PCB antenna **outside the base board**,
> and the feed point of the antenna **close to the edge of the base board**."*
> *"If the antenna cannot extend beyond the board edge... **cut off the base board on both sides of the antenna and below it**...
> to provide a sufficiently large clearance area."*（**mm 値なし**）
> *"The module **should not be placed in the center of the board** with clearance created by hollowing out on all four sides."*
> *"sufficient ground copper and dense ground vias should be placed on the base board near the antenna."*

### G-2 [HARD] ★唯一の数値 15 mm は「ケース内クリアランス」であり、基板銅箔キープアウトではない

> verbatim: *"Ensure that the PCB antenna on the base board also has a sufficiently large clearance area **inside the housing**.
> **A clearance of at least 15 mm is recommended in all directions.**"*

**→ この 15 mm を「基板上のキープアウト」として転用しないこと。Espressif は基板側の mm を出していない。**

**判定基準（定性）**: モジュールのアンテナ部が基板端から張り出しているか、
それが不可能なら**アンテナの両側と下側の基板をくり抜いてある**こと。4 辺くり抜きで中央配置は NG。

### G-3 [参考・チップダウン設計向け／モジュールには非該当]

ガイドライン §1.2/§1.3 は明示的に *"General Principles of PCB Layout for **the Chip**"* 配下＝**ベアチップ設計用**。
**WROOM モジュールでは水晶も RF マッチングもモジュール内に封止されており該当しない。**
（参考値: 主電源トレース幅 ≥25 mil、VDD3P3 ≥20 mil、水晶はクロックピンから ≥2.7 mm）

### G-4 [HARD] EN ピン

> WROOM-32E DS: *"it is advised to add an RC delay circuit at the EN pin.
> The recommended setting... is usually **R = 10 kΩ and C = 1 µF**."*

---

## H. USB / CH340C

### H-1 [HARD] 差動インピーダンス 90 Ω

> Microchip AN13.10（DS00002972A）verbatim: *"The USB 2.0 specification requires the USB DP/DM traces maintain
> nominally **90 Ohms** differential impedance (**see USB specification Rev 2.0, paragraph 7.1.1.3**)."*

**±15%** は **TI SLLA414A** §2.1 の表: *"Trace Impedance: **90Ω ±15% differential, 45Ω ±15% single ended**"*。
※ USB-IF 原典テキスト内での ±15% の verbatim 確認は usb.org のペイウォールにより**未達**。

### H-2 [HARD・数値] ★Full Speed の長さマッチング許容は極めて緩い — 蛇行配線は不要

> Silicon Labs AN0046（EFM32 は FS/LS のみサポート＝CH340C と同条件）verbatim:
> *"A common rule of thumb is to keep the skew less than 1/10th of the fastest rise time.
> **For USB full-speed this translates to 400 ps or 60 mm.** However, this is the total skew over the entire communication link...
> the USB specification the maximum allowed skew in a cable is 100 ps, which leaves
> **a maximum of 300 ps (45 mm) of skew to be distributed amongst the host and device.**"*

**→ CH340C の 12 Mbps で serpentine（蛇行配線）は完全に不要。**
比較: 同じ TI SLLA414A の SuperSpeed 向け intra-pair skew 推奨は **5 mil (0.13 mm)** ＝ FS は約 350–450 倍緩い。

**判定**: D+ / D− の長さ差が **45 mm 未満**であること（本基板は 61.8 × 45.0 mm なので実質的に自動的に満たす）。

### H-3 [数値] FS ではそもそもインピーダンス制御が支配的でない長さがある

> AN0046 verbatim: *"USB specifies a minimum rise time of 4 ns, which equals a maximum signal bandwidth of 87.5 MHz...
> **if PCB traces are shorter than 170 mm, it can be argued that the characteristic impedance of a track is not important.**
> However, good design practice is to route USB signals as an impedance matched differential pair according to specification."*

**→ 本基板（最長でも 62 mm）ではインピーダンス制御スタックアップの指定は必須ではない。**
JLC の追加費用を払うかどうかの判断材料になる。

### H-4 [PRACTICE・数値／HS 向けの保守的値] TI SLLA414A §3–4

- 差動対と他信号の間隔は **5W ルール**、*"maintain a minimum keep-out area of **30 mils** to any other signal"*
  （クロック等の周期信号隣接時は **50 mil**）
- *"Do not place probe or test points on any high-speed differential signal."*
- *"routed **≥90 mils** from the edge of the reference plane"*
- *"keeping via stubs to less than **15 mils**"*

**→ これらは HS/SS 前提で FS には過剰。ただし本基板では「ADS1299 との距離を稼ぐ根拠」として使える。**

### H-5 [HARD] CH340C 固有

> WCH CH340 Datasheet (I) v3B verbatim:
> *"**CH340C/N/K/E/X/B have integrated clock generator, no external crystal and oscillating capacitor required.**"*
> （XI ピン: *"NC. NONE — No Connection, do not connect"*）
> *"When using 5V power supply, the VCC pin connects 5V power and **the V3 pin should connect with a 0.1uF decoupling capacitor**.
> When using 3.3V power supply, **V3 should connect with VCC**."*
> *"**C8 and C9 decoupling capacitors must keep close to connection pin of CH340**;
> make sure D+ and D- signal lines are parallel and provide ground or pour copper on both sides"*（距離の数値なし）
> *"it is recommended that **no external resistor is in series with UD+ and UD- pins**."*

**判定**: (a) XI がオープンであること、(b) 電源電圧に応じた V3 の処理、
(c) **UD+ / UD− に直列抵抗が入っていないこと**（契約から機械判定可能）。

---

## I. スタックアップ（JLCPCB 4 層）

### I-1 [PRACTICE・出典あり] 4 層順は Sig / GND / PWR / Sig

> Henry Ott, PCB Stack-Up Part 2: 推奨構成 *"Sig. / Ground / Power / Sig."*、
> *"space the signal layers as close to the planes as possible (**<0.010"**)"*、
> *"with normal PCB construction techniques there is not sufficient inter-plane capacitance between the adjacent
> power and ground planes to provide adequate decoupling."*

**裏づけ**: SBAU181B §A.2 が **TI 自身の ADS129x EVM が Layer2=GND / Layer3=Power** であることを示す（→ 冒頭の文献訂正）。

### I-2 [数値・JLCPCB 公表値] 標準 4 層 JLC04161H-7628 は Ott の条件を満たす

| 層 | 厚さ | εr |
|---|---|---|
| Top Cu | 0.035 mm | — |
| **Prepreg 7628** | **0.2104 mm** | 4.4 |
| Core（内層 Cu 0.0152 mm） | **1.065 mm** | 4.6 |
| Prepreg 7628 | 0.2104 mm | 4.4 |
| Bottom Cu | 0.035 mm | — |

**[INFERENCE — 筆者の計算]**
- **L1 → L2 = 0.2104 mm = 8.3 mil < 10 mil ＝ Ott の基準を満たす**
- **L2 → L3 は 1.065 mm と極端に遠い** → **L3 を電源プレーンにしても L2-L3 間容量はデカップリングに寄与しない**
  （Ott の指摘そのまま）。**→ A-1 / A-2 のローカルデカップリングが全て。**

### I-3 [HARD] ⚠ JLCPCB は 90 Ω 差動の線幅 / ギャップ表を公表していない

https://jlcpcb.com/impedance にはスタックアップ寸法と εr は載るが、
**目標インピーダンスに対する線幅 / ギャップの表は非公開**（同社の Impedance Calculator で算出せよ、との案内のみ）。

**→ ここに数値を捏造しないこと。** 必要なら JLCPCB の計算機の出力を発注時のスタックアップ指定と一致させて確定する。
※ H-3 のとおり本基板の長さではインピーダンス制御は必須ではない。

### I-4 [HARD] ADS1299 DS が層数について述べていること

> DS §12.2 verbatim: *"an example layout of the ADS1299 requiring a **minimum of two PCB layers**...
> **If a three- or four-layer PCB is used, the additional inner layers can be dedicated to route power traces.**
> The PCB is partitioned with **analog signals routed from the left, digital signals routed to the right,
> and power routed above and below the device**."*

**→ TI 自身が 4 層で L3 を電源に使うことを想定している（I-1 と整合）。**
また**「アナログは左、デジタルは右、電源は上下」という配置の型**を明示している。

---

## J. 機械チェックにできる項目のまとめ（S7 実装用）

一次資料から**数値または明確な幾何基準が取れる**もの＝スクリプトで判定できるもの:

| # | 判定 | 出典 | データ源 |
|---|---|---|---|
| **J1** | ADS1299 の各電源ピンとバイパスコンデンサの間に**ビアが 0 個**、かつ**同一層** | A-1 [HARD] | pcbnew / Gerber |
| **J2** | **AVDD1(54) / AVSS1 がプレーンに面接続されていない**（スター接続） | A-6 [HARD] | pcbnew |
| **J3** | VCAP1 = 100 µF、VREFP-VREFN ≥ 10 µF が BOM にある | A-3 / D-2 [HARD] | `data/parts_lcsc.csv` |
| **J4** | VCAP1 の誘電体が **C0G / NPO / タンタル**（X5R/X7R なら要記録） | A-7 [HARD] | `data/parts_lcsc.csv` |
| **J5** | **SPI 5 本と USB D+/D− の直下 L2 にスリット・配線が無い** | B-4 [HARD] | Gerber In1.Cu |
| **J6** | RESV1(31) = DGND 直結 | E-3 [HARD] | contract |
| **J7** | 未使用アナログ入力が **AVDD** に接続（GND でもオープンでもない） | C-8 [HARD] | contract |
| **J8** | CH340C の XI がオープン、**UD+/UD− に直列抵抗なし** | H-5 [HARD] | contract |
| **J9** | **USB D+/D− の長さ差 < 45 mm** | H-2 [HARD] | pcbnew |
| **J10** | 電源レギュレータのコンデンサが**レギュレータと同じ面** | F-5 [HARD] | pcbnew |
| **J11** | ESP32 モジュールのアンテナ部が**基板中央配置でない**（端張り出しか両側+下くり抜き） | G-1/G-2 [HARD・定性] | 目視 + Edge.Cuts |

**機械チェックにできないもの**（＝人間のレビューが必要）:
デカップリングの距離（TI が数値を示していない・A-1/A-2）、
入力部のガードとベタ埋めの兼ね合い（C-10 と B-5 の緊張関係）、
アナログ/デジタルの partitioning の妥当性（B-3 / E-6）、
差動 vs 片側 RC の設計判断（C-1 vs C-2）。

---

## K. 検証できなかった／通説の可能性が高いもの

- **OpenBCI Cyton の ±2.5 V に TPS60403 が使われている**という一般的な記述は**一次資料で確認できなかった**。
  実際の `OpenBCI 32bit.sch`（DesignSpark バイナリ）の strings 抽出では TPS60403 は 1 件も出現せず、
  代わりに設計メモ **"SWITCH THIS TO TCM828"**（Microchip のスイッチトキャパシタ反転器）と
  "VOLTAGE INVERTER" / "-2.5V REGULATOR" / "+2.5V REGULATOR" のセクションラベルが出た。
  バイナリ形式のため最終 BOM 品番は断定不可。**Cyton の電源品番を根拠に設計しないこと。**
- **Cyton のグラウンド戦略は公式ドキュメントに一切記述が無い**（docs.openbci.com の Specs、READ_ME.md とも split/solid を明言せず）。
  4 層であることのみ確認。
- Cyton の入力 RC は **2.2 kΩ（CAY16-F4 抵抗アレイ）+ 1000 pF** が回路図 strings から確認できたが、
  OpenBCI フォーラム discussion/3506 で **「コーナーが 7 kHz 超で 250 SPS のアンチエイリアスとして緩すぎる」**
  との具体的批判が未解決のまま残っている。TI の 4.99 k / 4.7 nF とも異なる。

---

## L. 出典 URL

| 文書 | URL |
|---|---|
| ADS1299 SBAS499C | https://www.ti.com/lit/ds/symlink/ads1299.pdf |
| SLAU443B（ADS1299 EVM・**SBAU204 ではない**） | https://www.ti.com/lit/pdf/SLAU443 |
| SBAU181B（ADS1298R EVM・内層定義あり） | https://www.ti.com/lit/pdf/sbau181b |
| SBAA188（RLD） | https://www.ti.com/lit/pdf/sbaa188 |
| SCDA042（ガード） | https://www.ti.com/lit/an/scda042/scda042.pdf |
| SLYT499 / SLYT512（グラウンド） | https://www.ti.com/lit/an/slyt499/slyt499.pdf / https://www.ti.com/lit/an/slyt512/slyt512.pdf |
| SBAA052A（実測ケース） | https://www.ti.com/lit/an/sbaa052/sbaa052.pdf |
| ADI MT-031 | https://www.analog.com/media/en/training-seminars/tutorials/MT-031.pdf |
| Henry Ott（split GND / stack-up） | https://hott.shielddigitaldesign.com/techtips/split-gnd-plane.html / .../pcb-stack-up-2.html |
| Espressif PCB Layout | https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/pcb-layout-design.html |
| TI SLLA414A（USB） | https://www.ti.com/lit/an/slla414/slla414.pdf |
| SiLabs AN0046（USB FS skew） | https://www.silabs.com/documents/public/application-notes/an0046-efm32-usb-hardware-design-guidelines.pdf |
| TPS60403 / LM27762 / TPS7A39 | https://www.ti.com/lit/ds/symlink/tps60403.pdf / lm27762.pdf / tps7a39.pdf |
| JLCPCB スタックアップ | https://jlcpcb.com/impedance |
