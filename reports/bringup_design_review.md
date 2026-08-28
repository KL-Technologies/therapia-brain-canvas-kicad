# Brain Canvas Rev.A 火入れ前 設計レビュー（データシート実読）

- 日付: 2026-08-28
- 回路の正: `contract/netlist_easyeda_api_2026-08-28.tsv`（423 行）
- BOM の正: `data/parts_lcsc.csv`
- 基板: `board/Therapia_EEG-HRV.kicad_pcb`（HEAD スナップショットを読み取りのみ）
- 方針: **推測ではなく一次資料（メーカー PDF）を実読して判定**。推測箇所は「推測」と明記した。

## 0. 判定サマリ

| 分類 | 件数 | 項目 |
|---|---|---|
| **要対処（発注前・BOM のみ）** | 3 | B1 GPIO12 ストラップ / B2 EN の RC / B3 LED 電流 |
| **要対処（ファーム・手順）** | 4 | F1 MISC1=0x00 / F2 ADS RESET の再パルス / F3 ADS GPIO レジスタ禁止 / F4 eFuse 予備手順 |
| **要対処（発注フロー）** | 1 | J1 JLC PCBA サービス選択（基板サイズ最小値） |
| **注意（Rev.A 受容・実測で判断）** | 5 | N1 BIASINV 補償 / N2 C_NLDO_OUT 実効容量 / N3 AMS1117 セラミック出力 / N4 CHASSIS_GND 浮き / N5 LM2664 絶対最大 |
| **OK（実読で確認済み）** | 多数 | 下記各項 |

**最重要（これを直さないと初回起動しない可能性が高い）: B1。**
なお契約ネットリストの `NC` は**実ネットではなく未接続プレースホルダ**であることを確認済み（KiCad 側で該当 44 パッドの net は空文字、`(net "NC")` は 0 件）。ADS1299 の CLK/BIASREF/BIASIN/RESERVED と ESP32 GPIO が短絡している、という懸念は**否定された**。

---

## 1. ESP32-WROOM-32E 起動ストラップ ← **要対処（BOM のみ・銅箔変更なし）**

### 該当ネットリスト行
```
U_MCU   14  IO12   ADS_RESET_N     ← GPIO12 = MTDI（ストラップピン）
R_RST_UP 1      ADS_RESET_N
R_RST_UP 2      DVDD              ← 10kΩ で DVDD(3.3V) にプルアップ
C_RST_DLY 1     ADS_RESET_N
C_RST_DLY 2     GND               ← 100nF
U_ADS   36  RESET#  ADS_RESET_N
FB5     1       VDD_ESP / FB5 2 DVDD   ← DVDD は 3.3V（VDD_ESP からフェライト経由）
```

### 根拠（実読）
- ESP32 Series Datasheet v5.3 §3.2 <https://documentation.espressif.com/esp32_datasheet_en.pdf>
  - 「**MTDI = 0 (by default), VDD_SDIO pin is powered directly from VDD3P3_RTC. Typically this voltage is 3.3 V. MTDI = 1, VDD_SDIO pin is powered from internal 1.8 V LDO.**」
  - Table 3-1: MTDI の既定は **Pull-down / bit value 0**（内部プルダウン RPD **typ 45 kΩ**、Table 5-3）
  - Table 3-2 / Figure 3-1: **tSU ≥ 0 ms、tH ≥ 1 ms**。ストラップ値は CHIP_PU が VIH_nRST を超える前後で安定していなければならない
  - Table 5-3: **VIH = 0.75×VDD = 2.475 V**、**VIH_nRST = 0.75×VDD = 2.475 V**
  - 「The default values of all the above eFuse bits are 0, which means that **they are not burnt**」→ 工場出荷時に eFuse による上書きは**されていない**
- ESP32-WROOM-32E/32UE Datasheet v2.1 <https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf>
  - §4.2 に上記と同一の記述。Table 4 で MTDI = Pull-down
  - **Figure 9 (Peripheral Schematics) の注記に明記: 「IO12 should be kept low when the module is powered on.」** ← モジュールベンダ自身の設計ルール
  - Table 17 Flash Specifications: 3.3 V 品は **VCC 2.7–3.6 V**。VDD_SDIO=1.8 V ではフラッシュが動作しない
- 元設計 Cerelog も **GPIO12 を ADS1299 RESET# に使用**（`firmware/V1_ESP_EEG_firmware.ino`: `pin_RST_NUM = 12`）。ただし Cerelog 側に 10k プルアップがあるかは未確認（`hardware/schematic.pdf` は画像 PDF でテキスト抽出不可、レンダラ（poppler）が本環境に無く**未検証**）。**本基板が独自に追加した R_RST_UP が問題の原因**である可能性が高い（推測）。

### 判定: **要対処（indeterminate = 起動する個体としない個体が出る）**

タイミングを実数で解くと「確実に落ちる」でも「確実に通る」でもなく、**tH 規定を破る**：

| ノード | 回路 | 終値 | τ |
|---|---|---|---|
| ESP_EN | 10k↑3.3V + 100nF | 3.30 V | 1.00 ms |
| GPIO12 | 10k↑3.3V + 100nF + 内部 45k↓ | **2.70 V** | 0.818 ms |

- CHIP_PU が VIH_nRST(2.475 V) を超えるのは **t = 1.386 ms**
- その瞬間の GPIO12 = **2.204 V**（VIH 2.475 V 未満 → LOW）
- GPIO12 が VIH を超えるのは **t = 2.033 ms**、すなわち **CHIP_PU 解除の 0.65 ms 後**
- → **tH ≥ 1 ms のホールド窓の内側でストラップ値が LOW→HIGH に変化する = 規格違反**
- さらに GPIO12 の終値 2.70 V は VIH 下限 2.475 V に対し余裕 225 mV しかなく、RPD は typ 値のみで min/max 規定が無い

MTDI=1 とラッチされた個体は VDD_SDIO=1.8 V となり 3.3 V フラッシュを読めず、ROM ブートで `flash read err` → ブートループになる。

### 対処（**推奨案は 1 つ**）

**★ R_RST_UP を DNP（不実装）にする。BOM 1 行の変更のみ、銅箔変更ゼロ。**

- 結果: GPIO12 ノードは C_RST_DLY(100nF) + ESP32 内部 45kΩ プルダウンのみ → **tSU/tH の全区間で 0 V を保持 → MTDI = 0 確定 → VDD_SDIO = 3.3 V**
- 機能面の副作用なし: ADS1299 の RESET# はファームが push-pull で駆動する（Cerelog firmware は `pinMode(RST, OUTPUT)`）。ESP32 起動前は RESET# が Low = ADS1299 がリセット保持 = **むしろ望ましい初期状態**
- C_RST_DLY(100nF) は残置でよい（ストラップを Low に保つ役割として有効）。GPIO が 100nF を駆動する突入は CMOS 出力の自己電流制限内。気になれば 10nF 品への差し替えも可（任意）

**代替（採らない）**: RESET# を別 GPIO へ移設 → 銅箔変更＋ファーム改修が必要でコスト大。プルダウンへの変更 → ネット変更＝銅箔変更が必要。**DNP が最小・最安・最も安全。**

**保険（手順側）**: 万一 R_RST_UP を実装済みの基板を救済する場合は
`espefuse.py set-flash-voltage 3.3V`（XPD_SDIO_FORCE + XPD_SDIO_REG + XPD_SDIO_TIEH を焼く。以後「MTDI pin (GPIO12) is ignored」。**不可逆**）
根拠 <https://docs.espressif.com/projects/esptool/en/latest/esp32/espefuse/set-flash-voltage-cmd.html>

### 他のストラップピン（同資料 Table 3-1/3-3/3-4/3-5 で確認）

| ピン | 本基板 | 既定 | 判定 |
|---|---|---|---|
| GPIO0 | R_IO0_UP 10k↑VDD_ESP | Pull-up (1) | **OK** — SPI Boot |
| GPIO2 | R_IO2_DN 10k↓GND | Pull-down (0) | **OK** — GPIO0=1 なら GPIO2 は不問。書き込み時は両方 Low が必要で本回路で成立 |
| GPIO12/MTDI | 10k↑DVDD | Pull-down (0) | **NG（上記 B1）** |
| GPIO15/MTDO | R_IO15_DN 10k↓GND | Pull-up (1) | **注意** — Table 3-4 より **U0TXD Printing = Disabled**。ROM ブートログが出ない＝B1 由来の `flash read err` が見えない。**初号機のみ R_IO15_DN を DNP 推奨**（ESP_IO15 は他に接続なし、DNP で内部プルアップ＝ログ有効） |
| GPIO5 | R_CS_UP 10k↑DVDD | Pull-up (1) | **OK** — SDIO slave timing のみに影響。起動中 ADS1299 CS# が Deassert に保たれる利点あり |

補足: GPIO14(=ADS_START) は起動時に短時間トグルする既知挙動があるが、R_START_DN 10k↓ があり ADS1299 は未初期化なので無害（推測を含むが実害なし）。

---

## 2. 自動リセット回路（Q_EN / Q_IO0 / S8050 / DTR・RTS） ← **OK**

### 該当行
```
R_Q_EN_B  1 CH_DTR_N / 2 Q_EN_B     Q_EN  1 B Q_EN_B / 2 E CH_RTS_N / 3 C ESP_EN
R_Q_IO0_B 1 CH_RTS_N / 2 Q_IO0_B    Q_IO0 1 B Q_IO0_B / 2 E CH_DTR_N / 3 C ESP_IO0
U_USB 13 DTR# CH_DTR_N / U_USB 14 RTS# CH_RTS_N
```

**NodeMCU 型と完全に等価**（DTR→R→Q1.B, RTS→Q1.E, Q1.C→EN / RTS→R→Q2.B, DTR→Q2.E, Q2.C→IO0）。S8050 (SOT-23-3, J3Y) のピン配 1=B/2=E/3=C も一致。esptool の DTR/RTS シーケンスで書き込みモードに入れる。

**注意（実害小）**: CH340C は VCC=5 V 動作のため DTR#/RTS# は **0–5 V スイング**。片方 High・片方 Low の遷移時に S8050 の B-E 接合に約 5 V の逆電圧がかかる（V(BR)EBO 定格 5 V 近傍）。電流は 10kΩ で 0.5 mA 以下に制限され、破壊には至らない。書き込み時のみの過渡であり Rev.A は受容。OFF 時に 5 V が ESP32 の EN/IO0 へ回り込む経路は無いことを確認済み（B-E・B-C とも逆バイアス）。

---

## 3. CH340C ← **OK（全ピン一致）**

根拠: WCH CH340 Datasheet (I) v3B <https://docs.sparkfun.com/SparkFun_RTK_Facet_mosaic/assets/component_documentation/CH340DS1.PDF> §4 Pin definitions / §5.1

| ピン | 契約 | データシート | 判定 |
|---|---|---|---|
| 16 VCC | USB_5V | 「requires an external 0.1uF decoupling capacitor」→ C_USB_VCC 100nF あり | OK |
| 4 V3 | CH340_V3 + C_USB_V3 100nF→GND | 「**Connect to VCC when VCC is 3V3, connect to 0.1uF decoupling capacitor when VCC is 5V**」 | **OK（5V 動作なので 0.1µF が正解）** |
| 7 | NC | 「CH340C: No Connection, do not connect」 | OK |
| 8 (OUT#) | NC | 「CH340C: MODEM output IO」＝出力なので開放可 | OK |
| 15 R232 | GND | 「Assistant RS232 enable, **active high, integrated pull-down resistor**」 | **OK（GND = 通常 TTL モード）** |
| 5/6 UD+/UD− | USB_DP / USB_DM | 「connect to USB bus **directly, do not series resistors**」 | OK（直列抵抗なし。USBLC6 はシャント） |
| 2 TXD / 3 RXD | ESP_RXD / ESP_TXD | — | **OK（クロス結線が正しい）** |
| 9-12 CTS#/DSR#/RI#/DCD# | NC | 「**Unused I/O pins of CH340 should be NC**」 | OK |
| 7/8 水晶 | 不要 | 「CH340C … have integrated clock, **no external crystal required**」 | OK |

補足（無害）: 「DTR# pin of CH340G/C/T/K is used as a configuration input pin before the USB configuration completion」— 4.7kΩ プルダウンで大電流ディスクリプタを要求できるが、本基板は自動リセット網につながるのみ。ボード全体の VBUS 電流は CH340 のディスクリプタで制限されないため実害なし。

---

## 4. USB 入口 ← **OK**

### USBLC6-2SC6 のピン ← **一次資料で確認済み（Web 検索の回答は誤りだった）**
ST USBLC6-2 Doc ID 11265 Rev 5, Figure 1 Functional diagram (top view):
```
1  6      I/O1   I/O1
2  5      GND    VBUS
3  4      I/O2   I/O2
```
→ **Pin1 = I/O1, Pin2 = GND, Pin3 = I/O2, Pin4 = I/O2, Pin5 = VBUS, Pin6 = I/O1**

契約: `D_ESD 1 USB_DP / 2 GND / 3 USB_DM / 4 USB_DM / 5 USB_VBUS_RAW / 6 USB_DP` → **完全一致**。1&6 は内部で同一ノード（I/O1）、3&4 も同一（I/O2）なので、両方を同じネットに落とすのは正しい使い方。

> 途中の WebSearch は「Pin2=I/O1, Pin3=GND, Pin6=VBUS」と回答したが、ST の一次資料と矛盾するため**棄却**した。もし検索側が正しければ GND と D+ が短絡する致命傷になるため、一次資料での確認は必須だった。

### CC1/CC2
`R_CC1 5.1k → GND`, `R_CC2 5.1k → GND`（C23186, 5.1k 1%）→ UFP(Sink) 宣言として正しい。**OK**

### Polyfuse と全体電流
F1 = JK-NSMD050-13.2V（<https://jlcpcb.com/partdetail/C369159>）: **Ihold 0.5 A / Itrip 1 A / Ri min 150 mΩ / R1max 700 mΩ**

消費電流見積（WiFi/BT 未使用が前提。ファームは `Arduino.h`+`SPI.h` のみで RF を初期化しない）:

| 系統 | 内訳 | USB_5V 換算 |
|---|---|---|
| +3.3V (AMS1117) | ESP32 非 RF 約 40–70 mA（**推測: ESP32 DS は非 RF 時の値を表で示さないため実測必須**）+ ADS1299 IDVDD **1.0 mA**(実読) + AMS1117 接地電流 ~5 mA | ~76 mA |
| +2.5V (TLV70025) | ADS1299 IAVDD **7.14 mA**(実読, 8ch/bias off) | ~8 mA |
| −2.5V (LM2664→TPS72325) | AVSS ~8 mA、LM2664 効率 91% | ~9.5 mA |
| CH340C | ~12 mA | ~12 mA |
| **合計** | | **約 105 mA（typ）／140 mA（max）** |

→ Ihold 500 mA に対し 3.5 倍の余裕。**OK**。F1 の電圧降下は最悪 0.14 V（0.2 A × 0.7 Ω）で AMS1117 のヘッドルームに影響なし。

> **運用注意**: 消費が約 105 mA なので、低電流でオートオフするモバイルバッテリでは切れる可能性がある（多くは 50 mA 未満で切断なので通常は問題ないが要実機確認）。`08_simplified_power_design.md` §9 が想定した「LED で 30–50 mA 底上げ」は **B3 の通り実現していない**（実際は約 1.5 mA）。

---

## 5. 電源チェーン ← **OK（ピン配・EN 極性を一次資料で再確認）／一部注意**

### LM2664 ← **OK**
TI SNVS005E <https://www.ti.com/lit/ds/symlink/lm2664.pdf>

| ピン | データシート | 契約 | 判定 |
|---|---|---|---|
| 1 | GND | GND | OK |
| 2 | OUT | VNEG5 | OK |
| 3 | CAP− | LM_CAP_N | OK |
| 4 | SD 「**tie this pin to V+ in normal operation**」 | V5_LM_IN (=V+) | **OK（常時動作）** |
| 5 | V+ | V5_LM_IN | OK |
| 6 | CAP+ | LM_CAP_P | OK |

- IL = **40 mA** 定格に対し負荷 ~8 mA。ROUT max 25 Ω → 電圧降下 0.2 V → VNEG5 ≈ −4.8 V。TPS72325 のヘッドルーム十分。**OK**
- fSW = 40–80 kHz（fOSC の 1/2）。EEG 帯域外だが AVSS 経由の漏れは火入れ時に FFT で確認する（チェックリスト step 8）
- **N5 注意**: Abs Max「Supply voltage (V+ to GND) 5.8 V」。USB-C VBUS は規格上 5.5 V まで許容 → 余裕 0.3 V。USBLC6 の VBUS クランプは **VBR = 6 V min**（ST 実読）なので **LM2664 の絶対最大より上でしか効かない**。規格内では問題ないが、粗悪な 5 V 電源での過渡には無防備。Rev.B で USB_5V に 5.1 V 級 TVS 追加を推奨

### TPS72325 ← **OK（ECO-1#1 の正しさを確認）**
TI SLVS346E <https://www.ti.com/lit/ds/symlink/tps723.pdf>

- **DBV (SOT-23-5) ピン: 1=GND, 2=IN, 3=EN, 4=NR, 5=OUT** → 契約と**完全一致**
- EN: 「**Bipolar enable pin.** Driving this pin above the positive enable threshold **or below the negative enable threshold** turns on the regulator.」
  電気特性: **VEN(LO) = −1.5 V**（enable）、VDIS(HI)=+0.4 V / VDIS(LO)=−0.4 V（disable 窓）
  → 本基板 EN = V_NLDO_IN ≈ **−4.8 V** ≪ −1.5 V → **確実に enable**。**ECO-1#1 は正しい**
  （旧設計の EN=GND は −0.4〜+0.4 V の disable 窓ど真ん中 = 発注ストップ級バグだったことも裏付け）
- VEN 定格レンジ **−10 〜 +5.0 V** → −4.8 V は範囲内 **OK**
- CNR = **0.01 µF** 推奨 → C_NR 10nF（ECO-2#7）**一致 OK**
- CIN: 「An input capacitor is not required for LDO stability. However, an input capacitance with an effective value of **0.1 μF minimum** is recommended」→ C_NLDO_IN 1µF **OK**
- COUT: **2.2 〜 100 µF**、注記「**the effective capacitance is assumed to derate to 50% of the nominal**」

> **N2 注意**: C_NLDO_OUT = 2.2 µF **0402 6.3 V X5R**（C12530）。0402/6.3V 品は 2.5 V バイアスで大きくデレートし、実効 **0.9–1.3 µF** 程度になる（推測。メーカーの DC バイアス曲線は未取得）。単体では規定下限に届かない可能性がある。
> ただし AVSS ネットには **C_AVSS_B 10 µF 0603 + C_AVSS_H 100nF + C_AVSS_P17/P30/P37/P60 100nF×4** が並列に載っており、合計実効容量は十分（〜6 µF 以上）。**Rev.A は受容し、火入れ時に AVSS をオシロで発振確認**（チェックリスト step 5）。BOM 変更が安価なら C_NLDO_OUT を 0402 4.7 µF 品へ引き上げると確実。

### TLV70025 ← **OK**
TI SLVSA00E <https://www.ti.com/lit/ds/symlink/tlv700.pdf>

- 「**DDC Package 5-Pin SOT**」＝ SOT-23-5。ピン: **IN=1, GND=2, EN=3, NC=4, OUT=5** → 契約と**完全一致**
- EN: 「Driving EN over 0.9 V turns on the regulator」→ EN=V_PLDO_IN(5 V) で **常時 ON OK**
- CIN/COUT とも「a small, **1-μF** ceramic capacitor is recommended/needed」→ C_PLDO_IN / C_PLDO_OUT = 1 µF **完全一致 OK**
- NC ピン（4）: 「This pin can be tied to ground to improve thermal dissipation」→ 開放でも可 **OK**

> **BOM のデータ誤り**: `data/parts_lcsc.csv` の TLV70025 行の `package` 列が **`SOT-353`（= SC-70-5, 0.65 mm ピッチ）** になっている。TI の DDC は SOT-23-5（0.95 mm）であり、基板のフットプリント `SOT-23-5_L3.0-W1.7-P0.95` が**正しい**。MPN 列は `TLV70025DDCR` で正しいので実害はないが、**発注前に JLC の C19619 部品ページで実パッケージを目視確認すること**（万一 SC-70 品なら実装不能）。

### AMS1117 ← **注意（N3、Rev.A 受容）**
- ピン: 1=GND, 2=OUT, 3=IN, 4(tab)=OUT → 契約一致（`AMS1117 4 VOUT VDD_ESP`）**OK**
- 入出力: C_3V3_IN 1µF / C_3V3_OUT 10µF + C_3V3_B/B2 10µF×2 + C_3V3_M 1µF + C_3V3_H/H2 100nF×2 ≒ セラミック合計 30 µF 超
- **N3**: AMS1117 データシートは出力に **22 µF タンタル**を要求し、**ESR ≤ 0.5 Ω** を規定する（**二次情報**: 一次 PDF <https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/8122/AMS11173.3SOT223.pdf> はスキャン画像でテキスト抽出できず、本環境に OCR/レンダラが無いため**未検証**）。超低 ESR のセラミックのみだと発振する個体がある、というのが広く知られた挙動。
  → ECO の判断（「実績上動作する構成。発振兆候が出たら対処」）を踏襲し **Rev.A 受容**。火入れ時に VDD_ESP をオシロで確認（チェックリスト step 5）。発振したら C_3V3_OUT に 0.5–1 Ω を直列（手付け）で対処可能。

### フェライト
FB1–FB5 = GZ2012D601TF（0805, 600 Ω@100 MHz）。FB5 が **VDD_ESP → DVDD** を分離しており、DVDD は **3.3 V**。
→ `08_simplified_power_design.md` の「AVDD と DVDD は同じ +2.5 V」という記述は**現物と異なる（ドキュメントが陳腐化）**。そして **現物の方が正しい**（次項参照）。

---

## 6. ADS1299 電源・クロック・基準 ← **OK（DVDD=3.3V は TI 推奨構成に一致）**

根拠: TI SBAS499C <https://www.ti.com/lit/ds/symlink/ads1299.pdf>

### バイポーラ電源構成（§11.3 / Figure 78）
Figure 78「Bipolar Supply Operation」の推奨は **AVDD=+2.5 V / AVSS=−2.5 V / DVDD=+3.3 V**。本基板と一致。**OK**
Abs Max（§7.1）: AVDD−AVSS = −0.3〜**5.5 V**（本基板 5.0 V ✓）、DVDD−DGND = −0.3〜**3.9 V**（3.3 V ✓）、**AVSS to DGND = −3 〜 +0.2 V**（−2.5 V ✓、余裕 0.5 V）

### 外付け容量（§6 Pin Functions を実読）

| ピン | データシート指定 | 本基板 | 判定 |
|---|---|---|---|
| VCAP1 (28) | 「Connect a **100-μF** capacitor to AVSS」 | C_VCAP1 100µF 1206 + C_VCAP1_H 100nF | **OK**（ECO-3#11 は正しい） |
| VCAP2 (30) | 「**1-μF** to AVSS」 | C_VCAP2 1µF | **OK**（ECO-1#4） |
| VCAP3 (55) | 「parallel combination of **1-μF and 0.1-μF** to AVSS」 | C_VCAP3 1µF + C_VCAP3_H 100nF | **OK**（ECO-1#5） |
| VCAP4 (26) | 「**1-μF** to AVSS」 | C_VCAP4 1µF | OK |
| VREFP (24) | 「minimum **10-μF** capacitor to VREFN」 | C_VREFP_10u 10µF/25V + 100nF + 100pF、VREFN(25)=AVSS | **OK** |
| AVDD/DVDD | §11「Bypass each device supply with **10-μF and 0.1-μF**」 | AVDD/DVDD とも 10µF+100nF+個別 100nF | OK |
| RESV1 (31) | 「Reserved for future use, **connect directly to DGND**」 | GND 直結 | **OK**（ECO-1#2 は正しい） |
| DAISY_IN (41) | 「If not daisy-chaining devices, **tie DAISYIN directly to DGND**」 | GND 直結 | **OK** |
| BIASREF (60) | 未使用時は AVSS または開放。BIASREF_INT=1 で内部生成 | 開放 | **OK** |
| BIASIN (62) | 「can also float」 | 開放 | OK |
| NC (27,29) / RESERVED (64) | 「leave as open circuit」 | 開放 | OK |
| DRDY (47) | 「Pull DRDY to supply using weak pullup」 | R_DRDY_UP 10k↑DVDD | OK |

### クロック
- CLKSEL(52) = DVDD、CLK(37) = 開放
- Table 6「CLKSEL=1, CLK_EN=0 → 内部発振、**CLK PIN STATUS = 3-state**」
- CONFIG1 = 0x96（=リセット既定値）で **CLK_EN=0**（bit5）→ CLK は 3-state → **開放で OK**
- 内部発振 = **2.048 MHz**（typ、25 °C で ±0.5 %、−40〜85 °C で ±2.5 %）
- **既知の逸脱（Rev.A 受容、ECO 記載どおり）**: §6 の脚注(1) と §10.1.1 は「Set the two-state mode setting pins high to DVDD or low to DGND **through ≥10-kΩ resistors**」と規定。CLKSEL は直結。静的モードピンであり実害は小さいが、Rev.B で 10 kΩ 挿入。

### GPIO1–4（42/44/45/46）= GND 直結 ← **OK（ただしファーム制約あり → F3）**
データシートは自己矛盾している:
- §6 Pin Functions: 「Connect to DGND with a **≥10-kΩ resistor** if unused」
- §9.3.2.3: 「The GPIO pins are set as inputs after power-on or after a reset. **The pins should be shorted to DGND if not used.**」
- GPIO レジスタ(14h) reset = **0Fh**、GPIOC=1 が **入力** → **リセット後は 4 本とも入力**

→ 直結でも起動時は競合しない。**ただし GPIOC ビットを 0（出力）にして GPIOD を 1 にすると GND に対する恒常的な短絡になる**。Cerelog firmware は 0x14 を書かない（書き込みは 0x01–0x02, 0x05–0x0F, 0x15–0x17）ことを確認済み。→ **F3 としてファーム側の禁止事項に明記する。**

### 電源投入順序とリセット（§11.1）← **要対処（F2）**
実読:
> 「Before device power up, all digital and analog inputs must be low. ... Allow time for the supply voltages to reach their final value, and then begin supplying the master clock signal to the CLK pin. **Wait for time tPOR, then transmit a reset pulse using either the RESET pin or RESET command** to initialize the digital portion of the chip. **Issue the reset after tPOR or after the VCAP1 voltage is greater than 1.1 V, whichever time is longer.**」
> Table 30: **tPOR = 2^18 tCLK**、tRST = 2 tCLK

- tPOR = 2^18 / 2.048 MHz = **128 ms**
- Figure 67（Initial Flow at Power-Up）: 「If VCAP1 < 1.1 V at tPOR, continue waiting until VCAP1 ≥ 1.1 V」

**Cerelog firmware の実シーケンス**（実読）:
```
PWDN=LOW; RST=LOW; delay(100ms); PWDN=HIGH; RST=HIGH; delay(1000ms);
```
→ **RESET# を PWDN# と同時に解放している＝ tPOR 後のリセットパルスが存在しない**。§11.1 に非適合。

さらに **ECO-3#11 で C_VCAP1 を 1 µF → 100 µF に増やした**ため、VCAP1 の充電時間は約 100 倍になる。1000 ms で足りるかは TI が VCAP1 の内部駆動インピーダンスを公表していないため**計算では確定できない（要実測）**。

→ **F2**: ファームで「PWDN/RESET を High にして 1000 ms 待機 → **RESET# を再度 Low に 10 µs 以上 → High** →（または RESET コマンド 0x06 送出）→ 18 tCLK(≈9 µs) 待ち → SDATAC → ID 読み出し」に変更。加えて **火入れ時に VCAP1(pin 28) を AVSS 基準でオシロ観測し、1.1 V 到達時刻を実測**（チェックリスト step 6）。実測値が 1000 ms を超えるようなら待機時間を延長する。

### 電源投入時の「全デジタル入力 Low」要求
PWDN#/CS#/RESET# は DVDD へプルアップされているが、**プルアップ先が DVDD 自身**なので DVDD より高い電圧が印加されることはなく、ESD ダイオードの順バイアスは起こらない。TI の要求趣旨（自電源より高い入力を避ける）は満たされる。**OK**

---

## 7. アナログ入力段・BIAS ← **概ね OK／N1 注意**

### 入力ネットワーク
各 ch: 電極 → 10 kΩ 直列（R_INxP / R_INxN, 0402 1%）→ C_DIF 10 nF（**0805 NP0/C0G**, C237168）を差動に、C_CM 1 nF（0603 X7R）を各ノード→GND。

- ADS1299 §12.1: 「Analog inputs with differential connections must have a capacitor placed differentially across the inputs. The differential capacitors must be of high quality. **The best ceramic chip capacitors are C0G (NPO)**」→ **C_DIF が C0G なのは要求どおり OK**（ECO-2#6 が正しい）
- 差動カットオフ ≈ 1/(2π·20 kΩ·(10 nF + 1 nF/2)) ≈ **758 Hz**。ADS1299 の変調器 fMOD = fCLK/2 = 1.024 MHz に対し −62 dB → **アンチエイリアスとして十分 OK**
- C_CM が X7R ±10 % のため 50 Hz CMRR は外部網律速で **70 dB 前後**（ECO の見積 64 dB と同オーダー）。**Rev.A 受容（ECO 記載どおり）**、実測で不足なら対処

### SRB / 参照電極
```
R_SRB_SER (0Ω)  A2_ELEC ── SRB1ネット
U_ADS 17 SRB1 = SRB1 / U_ADS 18 SRB2 = SRB1      ← SRB1・SRB2 を束ね
R_IN1N,2N,3N,5N,6N,7N,8N (10k)  SRB1 ── INxN     ← ch4 以外の N 側を外部で SRB1 に接続
R_IN4N (10k)  ECGN_ELEC ── IN4N                  ← ch4 のみ真の差動（ECG）
```
- ADS1299 §6: SRB1/SRB2 は「Patient stimulus, reference, and bias signal」。束ねは電気的に問題なし。**OK**
- **ECG は ch4**（J2 pin4=ECGP→IN4P, pin5=ECGN→IN4N）。`02_firmware_analysis.md` の「CH3SET = 0x20 (bipolar ECG)」は**現物と不一致**（ドキュメントが陳腐化）→ **F1 に含める**

### BIAS（DRL）ループ ← **N1 注意**
```
U_ADS 63 BIASOUT = BIAS_OUT_INT
R_BIAS_SER (1MΩ)  BIAS_OUT_INT ── A1_ELEC        ← BIAS 電極へ
R_BIAS_FB  (1MΩ)  BIAS_INV ── BIAS_OUT_INT       ← 帰還抵抗
C_BIAS_INV (100nF) BIAS_INV ── GND               ← ★ ここが TI 推奨と異なる
U_ADS 61 BIASINV = BIAS_INV / 60 BIASREF = 開放 / 62 BIASIN = 開放
```
- TI **Figure 68**（Setting Common-Mode Using BIAS Electrode）の推奨定数は **1 MΩ と 1.5 nF**、いずれも BIASOUT–BIASINV 間（帰還経路）に置かれる構成。
- 本基板は 1 MΩ は帰還経路で正しいが、**容量は BIASINV → GND（加算節点→GND）に 100 nF** で入っている。
- 反転アンプの一般論として、帰還に並列の C は高域利得を落として**安定化**、加算節点→GND の C は雑音利得を持ち上げて**不安定化**方向に働く。TI も §9.3.2.4.5 で「**Stabilizing the entire loop is specific to the individual user system based on the various poles in the loop.**」「All the amplifier terminals are available at the pins, allowing the user to choose the components for the feedback loop」と、ループ安定化は設計者責任と明記している。
- なお AVDD/AVSS = ±2.5 V なので **GND = 中点電位 = BIASREF 内部基準と同電位**であり、容量の落とし先が GND であること自体は正しい。問題は**位置（帰還ではなく加算節点）と値（100 nF vs 1.5 nF）**。
- 100 nF・1 MΩ で考えると極は約 **1.6 Hz** となり、1.5 nF 相当（約 106 Hz）に比べ DRL ループ帯域が桁で狭い。50 Hz の同相除去に対する DRL の寄与はほぼ失われる。

**判定: Rev.A は「注意」。発振すれば全 ch にノイズが乗るため、火入れで必ず確認する。**

対処（安い順）:
1. **BOM のみ**: C_BIAS_INV を **DNP**。加算節点の容量を除去し、不安定化要素を無くす（ループは 1 MΩ 帰還のみ）
2. 発振または 50 Hz 除去不足が実測されたら、**R_BIAS_FB(0805) の上に 1.5 nF（0402）を手付けで並列**に載せて TI Figure 68 に一致させる
3. Rev.B で C を帰還経路（BIAS_INV–BIAS_OUT_INT）へ移設し 1.5 nF に変更（銅箔変更）

### 未使用 ch
§6 脚注(2)「Connect unused analog inputs directly to AVDD」／§10.1.1「Power down unused analog inputs and connect them directly to AVDD」。
本基板は 8 ch すべて J2 に配線されており、未使用 ch は電極未接続＝開放になる。→ **F1 で CHnSET = 0x81（power-down + MUX short）に設定して内部 MUX で切り離す**ことで対処（外部結線の変更は不要）。

---

## 8. SPI / 制御線 ← **OK**

| 信号 | ESP32 | 契約ネット | Cerelog firmware（実読） | 判定 |
|---|---|---|---|---|
| SCLK | GPIO18 (pin30) | SPI_SCK →R_SCLK 0Ω→ ADS_SCLK_LOC → ADS pin40 | `pin_SCK_NUM = 18` | OK |
| MOSI | GPIO23 (pin37) | SPI_MOSI →R_MOSI 0Ω→ ADS_DIN_LOC → ADS pin34 | `pin_MOSI_NUM = 23` | OK |
| MISO | GPIO19 (pin31) | SPI_MISO ←R_MISO 0Ω← ADS_DOUT_LOC ← ADS pin43 | `pin_MISO_NUM = 19` | OK |
| CS# | GPIO5 (pin29) | ADS_CS_N, R_CS_UP 10k↑DVDD, ADS pin39 | `pin_CS_NUM = 5` | OK |
| PWDN# | GPIO13 (pin16) | ADS_PWDN_N, R_PWDN_UP 10k↑DVDD, ADS pin35 | `pin_PWDN_NUM = 13` | OK |
| RESET# | GPIO12 (pin14) | ADS_RESET_N, R_RST_UP 10k↑DVDD, ADS pin36 | `pin_RST_NUM = 12` | **配線 OK / B1 で R_RST_UP を DNP** |
| START | GPIO14 (pin13) | ADS_START, R_START_DN 10k↓GND, ADS pin38 | `pin_START_NUM = 14` | OK |
| DRDY# | GPIO27 (pin12) | ADS_DRDY_N, R_DRDY_UP 10k↑DVDD, ADS pin47 | `pin_DRDY_NUM = 27`、FALLING 割込 | OK |
| LED | GPIO17 (pin28) | STATUS_LED_DRV | `pin_LED_DEBUG = 17` | 配線 OK（B3 参照） |

**VSPI 既定ピン（18/23/19/5）と firmware 定義が完全一致。** SPI 設定は 4 MHz / SPI_MODE1 / MSBFIRST（実読）。

論理レベル: ESP32 VOH min = 0.8×VDD = **2.64 V**、ADS1299 VIH min = 0.8×DVDD = **2.64 V**。数値上は余裕ゼロだが、DVDD は VDD_ESP から FB5(DCR 数十 mΩ)経由で**わずかに低い**ため実効的には順方向のマージンがある。同一レールなので温度・電圧変動でも追従する。**OK**（懸念なし）

---

## 9. ステータス LED ← **要対処（B3、BOM のみ）**

```
U_MCU 28 IO17 → STATUS_LED_DRV → R_LED(330Ω, C23138) → LED_A → D_LED(A→C) → GND
```
D_LED = **C72043 / Everlight 19-217/GHC-YR1S2/3T**（<https://jlcpcb.com/partdetail/C72043>）
実測データ: **package = 0603**、**Emerald Green、518 nm、Vf = 3.3 V @20 mA、199 mcd**

- **フットプリント整合は OK**: 基板は `LED0603-RD`（パッド 0.8×0.8 mm、中心間 1.5 mm）で **0603 品と一致**。`data/parts_lcsc.csv` の `package` 列の「0805」が**誤記**（実害なし、CSV の修正のみ）
- **電流が足りない**: 電源が 3.3 V、LED の Vf が 3.3 V(@20 mA)。ESP32 の VOH min は 2.64 V。330 Ω では動作点が Vf(I)+330·I = 約 3.2 V となり **I ≈ 1.5 mA**（緑 InGaN の低電流域 Vf ≈ 2.7 V として。**推測を含む — 実測で確認**）。輝度は約 15 mcd 相当で暗い
- `08_simplified_power_design.md` §9 の「LED で 30–50 mA のダミー負荷を作りモバイルバッテリの自動オフを防ぐ」は **完全に未達**（1.5 mA）

**対処: R_LED を 330 Ω → 100 Ω に変更（BOM 1 行、0603 同フットプリント）。** 約 4–5 mA になり視認性が確保される。
より確実にしたい場合は D_LED を Vf ≈ 2.0 V の赤/黄 0603 LED に差し替える（330 Ω のままで約 4 mA）。
**モバイルバッテリ対策は LED では解決しないので、運用側で「PC の USB ポートか、オートオフしない/低電流モードのあるバッテリを使う」と決めること。**

---

## 10. JLC 実装上の注意 ← **要対処（J1、発注フローのみ）**

根拠 <https://jlcpcb.com/capabilities/pcb-assembly-capabilities>

| 項目 | 本基板 | JLC 能力 | 判定 |
|---|---|---|---|
| 最小受動部品 | 0402（R_INxP/N ほか） | Economic **0402** / Standard **0201** | **OK（Economic で可）** |
| QFP ピッチ | U_ADS TQFP-64 **0.50 mm**（パッド 0.28×1.8 mm、パッド間 0.22 mm） | Economic **0.40 mm** / Standard 0.35 mm | **OK（Economic で可）** |
| THT | J2（2×6 ピンヘッダ、φ1.524 スルーホール） | 両サービスとも THT / 混載対応 | OK |
| ESP32 モジュール EPAD | U_MCU = 47 パッド（信号 38 + EPAD 9 分割） | — | **OK**。WROOM-32E DS §9「Soldering the EPAD to the ground of the base board **is not a must**, however, it can optimize thermal performance」→ 9 分割は推奨ランドパターン準拠 |
| **基板サイズ** | **61.8 × 45 mm** | **Standard PCBA は単板 70×70 mm 以上**／Economic は 10×10 mm から／パネル化は両方 10×10–250×250 mm | **要対処 J1** |
| USB-C のペグ穴/スロット | J1 = `TYPE-C-16PIN-2MD(073)`、位置決めペグ NPTH あり | 明記なし | ECO の **L4** で既にレイアウト修理項目として管理中。**本レビューでは再掲のみ** |

**J1 の対処**: 61.8×45 mm は **Standard PCBA の単板最小 70×70 mm を下回る**。
→ **(a) Economic PCBA で発注する**（部品要件はすべて Economic の範囲内なのでこれが最短）、または **(b) 2×2 等にパネル化して Standard PCBA を使う**。
どちらでも技術的に成立するが、**発注操作の前に JLC の見積画面でサービス種別と最小サイズを必ず確認する**こと（能力ページの記載は改定されうるため）。
なお Economic は「Gold Fingers/Castellated Holes/Edge Plating」非対応と記載があるが、これは**基板側の加工**の話であり、キャスタレーション付き**モジュールの実装**を禁じるものではない（推測。見積時に確認を推奨）。

---

## 11. その他（レイアウト担当への申し送り）

### デカップリングコンデンサの designator が実ピン番号と一致していない ← **レイアウトで要注意**
`C_AVDD_P3 / P19 / P31 / P36 / P59 / P64`、`C_AVSS_P17 / P30 / P37 / P60`、`C_DVDD_P40 / P58` は名前が「Pnn = ピン番号」に見えるが、ADS1299 の実際の電源ピンは:
- **AVDD: 19, 21, 22, 56, 59**（AVDD1 = 54）
- **AVSS: 20, 23, 32, 57, 58**（AVSS1 = 53）
- **DVDD: 48, 50**（DGND = 33, 49, 51）

一致するのは P19 と P59 のみ。**C_AVSS_P17/P30/P37/P60 と C_DVDD_P40/P58 はどれも該当ピンではない**（pin17=SRB1, 30=VCAP2, 37=CLK, 40=SCLK, 58=AVSS, 60=BIASREF）。
→ **配置は designator の名前ではなく、上の実ピン番号に従って行うこと。** ネット接続自体は正しいので、電気的な誤りではない。

### 星型接続（§11）
「star connect **AVDD1 to the AVDD pins** and **AVSS1 to the AVSS pins**」「Place the capacitors for supply, reference, and VCAP1 to VCAP4 **as close to the package as possible**」「Do not place vias between bypass capacitors and the active device」。VCAP1 は 100 µF/1206 と大きいので、極力 IC 直近に置く。

### CHASSIS_GND が浮いている ← **N4（Rev.A 受容だが要認識）**
`CHASSIS_GND` に接続されているのは **J1 pin13/14（SHELL）と J2 pin12 のみ**で、GND との間に抵抗・容量・ビーズが**1 つも無い**（`08_simplified_power_design.md` は「EMI ビーズで 1 点接続」と書いているが、実回路には存在しない）。

含意:
1. USB-C シェルが完全にフローティング → ESD/EMI の帰還路が無く、シールドとしてはほぼ機能しない
2. **電極コネクタ J2 の pin12 が USB-C シェルと直結** → PC に挿すと患者側の pin12 がシャーシ／保護接地と導通しうる

本機は医療機器ではなく awareness 用途であり、運用上もモバイルバッテリ給電を前提としているため **Rev.A は受容**。ただし
- **J2 pin12 に電極を接続しない**運用ルールを明文化する（ケーブルシールドのドレイン専用）
- Rev.B で CHASSIS_GND–GND 間に **1 MΩ ∥ 4.7 nF**（または 0 Ω リンク）を追加

### R_SRB_SER = 0 Ω（Rev.B 検討）
参照電極 A2 だけが直列抵抗 0 Ω で ADS1299 の SRB1/SRB2 ピンに直結（他の電極はすべて 10 kΩ）。ノイズ上は 0 Ω が有利だが、患者リードが IC ピンに直結するのは ESD 上望ましくない。Rev.A は現状維持、Rev.B で 1 kΩ 程度を検討。

### C_AVDD1_10n / C_VREFP_10n の実体は 100 pF
designator は「10n」だが BOM 実体は **C1546 = 100 pF**（ECO-2#7 は C_NR だけを 10 nF へ修正し、この 2 つは対象外）。VREFP は 10 µF + 100 nF が既にあり TI 要求を満たすため**実害なし**。designator の誤解を招くので Rev.B で改名。

---

## 12. PCB 修正提案（lead 判断用・本レビューからは 0 件）

**本レビューで新たに発生した銅箔変更（PCB 修正）は 0 件。** 要対処 3 件（B1/B2/B3）は**すべて BOM 行の変更のみ**で解決し、S5/S6 のレイアウト修理作業に追加負荷を与えない。

| ID | 変更内容 | 種別 | 銅箔変更 |
|---|---|---|---|
| **B1** | **R_RST_UP → DNP（不実装）** | BOM 削除 | **なし** |
| **B2** | **C_EN_DLY: 100 nF → 1 µF**（C1525 → **C52923**、0402 同フットプリント） | BOM 差し替え | **なし** |
| **B3** | **R_LED: 330 Ω → 100 Ω**（0603 同フットプリント） | BOM 差し替え | **なし** |
| （任意） | R_IO15_DN → DNP（初号機のみ、ROM ブートログを見るため） | BOM 削除 | なし |
| （任意） | C_BIAS_INV → DNP（N1 の不安定化要素を除去） | BOM 削除 | なし |
| （任意） | C_NLDO_OUT: 2.2 µF → 4.7 µF 0402（N2 のマージン確保） | BOM 差し替え | なし |

**B2 の根拠**: ESP32-WROOM-32E DS §9「it is advised to add an RC delay circuit at the EN pin. The recommended setting for the RC delay circuit is usually **R = 10 kΩ and C = 1 µF**」。現状は 10 kΩ + 100 nF（τ=1 ms）で Espressif 推奨（τ=10 ms）の 1/10。
**重要: B2 は B1 とセットで実施すること。** B1 を直さないまま C_EN_DLY だけ 1 µF にすると、EN の立ち上がりだけが 10 倍遅くなり GPIO12 が確実に High でラッチされる（＝必ず起動しなくなる）。

既存の ECO / レイアウト修理項目（L1–L6、ECO-1/2/3）に対する変更・追加は**なし**。すべて有効性を再確認した。

---

## 13. ファーム／手順側の要対処

| ID | 内容 | 根拠 |
|---|---|---|
| **F1** | **レジスタ設定を本基板向けに変更**: `MISC1 = 0x00`（**0x20 は不可**）。0x20 だと SRB1 が内部で全 ch の N 側に接続され、**ch4 の ECGN が SRB1 に短絡して ECG が壊れる**。本基板は ch4 以外の N 側を外部 10 kΩ で SRB1 に接続済みなので、MISC1=0x00 で参照モードが成立する。あわせて **ECG は ch3 ではなく ch4**（`02_firmware_analysis.md` の記述は陳腐化）。未使用 ch は `CHnSET = 0x81`(power-down + MUX short) にして開放入力を内部で切り離す | ADS1299 §9.6.1.15（MISC1 bit5 = SRB1）、§6 脚注(2)、契約ネットリスト R_IN4N |
| **F2** | **ADS1299 リセット手順を §11.1 準拠に**: PWDN#/RESET# を High にして待機後、**改めて RESET# を Low(≥2 tCLK ≈ 1 µs)→High**、または RESET コマンド 0x06 を送出し、18 tCLK 待ってから SDATAC → ID 読み出し。現行 Cerelog firmware は PWDN と RESET を同時に解放しており tPOR 後のリセットパルスが無い。加えて C_VCAP1 が 100 µF になった影響で VCAP1 の充電に 1000 ms で足りるか未確定 → **実測して待機時間を決める** | ADS1299 §11.1 Table 30、Figure 67、Figure 76 |
| **F3** | **ADS1299 GPIO レジスタ(0x14) を書かないこと**（特に GPIOC ビットを 0＝出力にしない）。GPIO1–4 は GND 直結のため、出力 High にすると恒常短絡になる。現行 firmware は 0x14 を書いていないので**現状維持を明文化**する | ADS1299 §9.3.2.3、§9.6.1.14（reset = 0Fh = 全入力） |
| **F4** | **eFuse 手順を予備として用意**: B1 を DNP で対処すれば不要。R_RST_UP 実装済みの基板を救済する場合のみ `espefuse.py set-flash-voltage 3.3V` を実施（**不可逆**、要 UART 書き込み経路） | esptool docs（上記 URL） |

---

## 14. 参照した一次資料

| 資料 | URL | 用途 |
|---|---|---|
| ESP32 Series Datasheet v5.3 | <https://documentation.espressif.com/esp32_datasheet_en.pdf> | ストラップピン、VDD_SDIO、DC 特性、tSU/tH |
| ESP32-WROOM-32E/32UE Datasheet v2.1 | <https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf> | IO12 注記、EN の RC 推奨、EPAD、ピン表、フラッシュ電圧 |
| esptool espefuse set-flash-voltage | <https://docs.espressif.com/projects/esptool/en/latest/esp32/espefuse/set-flash-voltage-cmd.html> | eFuse 手順 |
| TI ADS1299 SBAS499C | <https://www.ti.com/lit/ds/symlink/ads1299.pdf> | ピン機能、VCAP/VREFP、§11.1 電源投入、Figure 68/78、レジスタ |
| TI TPS723 SLVS346E | <https://www.ti.com/lit/ds/symlink/tps723.pdf> | DBV ピン配、bipolar EN しきい値、CIN/COUT/CNR |
| TI LM2664 SNVS005E | <https://www.ti.com/lit/ds/symlink/lm2664.pdf> | SOT-23-6 ピン配、SD 極性、IL/ROUT/fSW、Abs Max |
| TI TLV700 SLVSA00E | <https://www.ti.com/lit/ds/symlink/tlv700.pdf> | DDC=SOT-23-5 ピン配、EN しきい値、CIN/COUT |
| WCH CH340 Datasheet (I) v3B | <https://docs.sparkfun.com/SparkFun_RTK_Facet_mosaic/assets/component_documentation/CH340DS1.PDF> | SOP-16 ピン表、V3/R232、水晶不要 |
| ST USBLC6-2 Doc ID 11265 Rev 5 | <https://www.st.com/resource/en/datasheet/usblc6-2.pdf>（実取得は <https://pdf.datasheet.support/6df39106/st.com/USBLC6-2SC6.pdf>） | SOT-23-6L ピン配、VBR |
| Cerelog ESP-EEG firmware | <https://github.com/Cerelog-ESP-EEG/ESP-EEG> / `firmware/V1_ESP_EEG_firmware.ino` | GPIO 割当、SPI 設定、起動シーケンス |
| JLCPCB Assembly Capabilities | <https://jlcpcb.com/capabilities/pcb-assembly-capabilities> | 最小部品/ピッチ、基板サイズ |
| JLC 部品ページ C72043 / C369159 | <https://jlcpcb.com/partdetail/C72043> / <https://jlcpcb.com/partdetail/C369159> | LED パッケージ・Vf、Polyfuse 定数 |

### 検証できなかった項目（明記）
- **Cerelog 公式回路図** `cerelog_research/schematic.pdf`: ベクタ画像 PDF でテキスト抽出不可（3 ページで 60 文字）。本環境に poppler/Ghostscript/OCR が無いためレンダリング不能。**「Cerelog 実機が GPIO12 をプルアップしているか」は未確認**。ただし B1 の判定は Espressif 一次資料（「IO12 should be kept low when the module is powered on」）のみで確定するため、結論に影響しない。
- **AMS1117 データシート一次 PDF**: スキャン画像でテキスト抽出不可。「22 µF タンタル / ESR ≤ 0.5 Ω」は二次情報。N3 の扱い（Rev.A 受容＋実測確認）は変わらない。
- **C_NLDO_OUT / C_EN_DLY の DC バイアス実効容量**: メーカーのデレーティング曲線を取得していないため、実効値は推測。N2 の結論（実測で確認）に反映済み。
