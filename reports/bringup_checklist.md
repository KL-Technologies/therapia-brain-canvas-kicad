# Brain Canvas Rev.A 火入れ手順書（合格値つき）

- 対象: Brain Canvas Rev.A（ADS1299 + ESP32-WROOM-32E + CH340C、USB-C 5V 給電、61.8×45 mm 4層）
- 前提: `reports/bringup_design_review.md` の **B1／B2／B3 を BOM に反映済み**であること
- 原則: **各ステップの合格値を満たすまで次へ進まない。** 不合格なら末尾「切り分けフロー」へ
- 記録: 各ステップの実測値をこの表に書き込んで残す（Rev.B の判断材料になる）

---

## Step 0. 着手前の確認（机上）

| # | 確認項目 | 合格条件 |
|---|---|---|
| 0-1 | **R_RST_UP が DNP（不実装）** になっているか | 発注 BOM に R_RST_UP の行が無い／DNP 指定。**最重要。実装されていると起動しない個体が出る（GPIO12 ストラップ）** |
| 0-2 | **C_EN_DLY = 1 µF**（C52923）に差し替え済みか | Espressif 推奨 R=10 kΩ / C=1 µF |
| 0-3 | **R_LED = 100 Ω** に差し替え済みか | 緑 LED (Vf 3.3 V) を 3.3 V で光らせるため |
| 0-4 | （初号機のみ）**R_IO15_DN を DNP** にしたか | ROM ブートログを見られるようにするため。2 台目以降は実装で可 |
| 0-5 | ECO-1/2/3 と L1〜L6 のレイアウト修理がすべて反映され、最終 DRC が通っているか | 別途 gates の記録を参照 |

### 必要な器材
- **電流制限つき DC 電源**（0–6 V / 0–500 mA）＋ USB-C ブレークアウト、または USB 電流計つきケーブル
- テスタ（DC 電圧、4 桁半以上）
- オシロスコープ（20 MHz 以上、AC 結合、×10 プローブ）
- PC（`esptool` インストール済み）、USB-C ケーブル（**データ線つき**。充電専用ケーブル不可）
- 短いジャンパ線（J2 の電極短絡用）

---

## Step 1. 無通電チェック（目視＋テスタ）

**通電前に必ず実施する。** 短絡したまま通電すると LM2664 / LDO を壊す。

| # | 測定 | 合格値 |
|---|---|---|
| 1-1 | 目視: 部品の向き（U_ADS pin1 マーク、U_MCU、AMS1117、LDO 3 個、D_ESD、LM2664） | シルクの 1 番表示と一致 |
| 1-2 | 目視: J1(USB-C) のはんだブリッジ、U_ADS(0.5 mm ピッチ) のブリッジ | ブリッジなし |
| 1-3 | USB_5V ↔ GND 抵抗 | **> 1 kΩ**（数十 kΩ〜∞ が正常。数 Ω なら短絡） |
| 1-4 | VDD_ESP ↔ GND 抵抗 | **> 1 kΩ** |
| 1-5 | AVDD ↔ GND 抵抗 | **> 1 kΩ** |
| 1-6 | AVSS ↔ GND 抵抗 | **> 1 kΩ** |
| 1-7 | VNEG5 ↔ GND 抵抗 | **> 1 kΩ** |
| 1-8 | AVDD ↔ AVSS 抵抗 | **> 1 kΩ** |
| 1-9 | CHASSIS_GND ↔ GND | **∞（導通しないのが正常）**。本設計は意図的に非接続（レビュー N4 参照） |

---

## Step 2. 初回通電（電流制限つき電源）

**まだ USB データ線はつながない**（電源のみ）。電流制限を **250 mA** に設定。

| # | 測定 | 合格値 | 実測 |
|---|---|---|---|
| 2-1 | 5.00 V 印加直後の突入電流 | 一瞬 200 mA 前後まで振れてよい（バルク 10 µF×複数の充電） | |
| 2-2 | **定常電流**（10 秒後） | **80–160 mA**（設計値 typ 約 105 mA） | |
| 2-3 | 電源が電流制限に張り付く | **不合格 → 直ちに切る。** 短絡箇所を探す | |
| 2-4 | 部品の発熱（指で触れる） | 熱いものが無いこと。AMS1117 は温かい程度（(5−3.3)×0.07 W ≈ 0.12 W）が正常 | |

> 定常電流が **50 mA 未満**なら ESP32 が起動していない可能性が高い。**60 mA 未満でも次の Step 3 は実施する**（電源系だけ先に確定させる）。

---

## Step 3. レール電圧測定

すべて **GND 基準**で測る。VCAP1 と VREFP だけは AVSS 基準（後述、Step 7）。

| # | ネット | 測定点の目安 | 合格値（GND 基準） | 実測 |
|---|---|---|---|---|
| 3-1 | USB_5V | C_BULK / C_HF の＋側 | **+4.75 〜 +5.25 V** | |
| 3-2 | V5_LM_IN | FB1 の LM2664 側 / C_LM_IN | USB_5V との差 **< 50 mV** | |
| 3-3 | **VNEG5** | LM2664 pin2 / C_LM_OUT | **−4.55 〜 −5.05 V**（無負荷 −5 V、ROUT 12–25 Ω × 約 9 mA で 0.1–0.23 V 降下） | |
| 3-4 | V_NLDO_IN | FB4 の TPS72325 側 / C_NLDO_IN | VNEG5 との差 **< 50 mV** | |
| 3-5 | **AVSS** | TPS72325 pin5 / C_AVSS_H | **−2.45 〜 −2.55 V**（狙い −2.500 V） | |
| 3-6 | V_PLDO_IN | FB2 の TLV70025 側 | USB_5V との差 **< 50 mV** | |
| 3-7 | **AVDD** | TLV70025 pin5 / C_AVDD_H | **+2.45 〜 +2.55 V**（狙い +2.500 V） | |
| 3-8 | V_3V3_IN | FB3 の AMS1117 側 | USB_5V との差 **< 50 mV** | |
| 3-9 | **VDD_ESP** | AMS1117 pin2 / C_3V3_OUT | **+3.20 〜 +3.40 V**。**+3.00 V 未満は不可**（WROOM-32E の VDD33 min = 3.0 V） | |
| 3-10 | **DVDD** | FB5 の ADS1299 側 / C_DVDD_H | VDD_ESP との差 **< 20 mV** | |
| 3-11 | AVDD − AVSS | 差動で測る | **+4.90 〜 +5.10 V**（ADS1299 Abs Max 5.5 V を超えないこと） | |
| 3-12 | AVSS − GND | = 3-5 | **> −3.0 V**（ADS1299 Abs Max: AVSS to DGND ≥ −3 V） | |

> **VNEG5 が 0 V に近い** → LM2664 の SD（pin4）が V+ に来ているか、フライングキャップ C_LM_FLY の実装を確認。
> **AVSS が 0 V** → TPS72325 の EN（pin3）が V_NLDO_IN につながっているか確認（ECO-1#1。EN=GND だと −0.4〜+0.4 V の disable 窓に入り出力が出ない）。

---

## Step 4. リップル・発振の確認（オシロ、AC 結合、プローブのグランドは最短に）

| # | 測定点 | 合格値 | 実測 |
|---|---|---|---|
| 4-1 | USB_5V | **< 50 mVpp** | |
| 4-2 | VNEG5 | **< 30 mVpp**（LM2664 のスイッチングは fSW 40–80 kHz。10 µF フライング/出力なら数 mVpp オーダー） | |
| 4-3 | **AVSS** | **< 5 mVpp、かつ持続発振なし**（レビュー N2: C_NLDO_OUT の実効容量が下限付近。数百 kHz の正弦波状リンギングが見えたら発振） | |
| 4-4 | **AVDD** | **< 5 mVpp、発振なし** | |
| 4-5 | **VDD_ESP** | **< 50 mVpp、発振なし**（レビュー N3: AMS1117 のセラミック出力のみ構成。数百 kHz〜MHz の発振が出たら要対処） | |
| 4-6 | DVDD | < 50 mVpp | |

> 4-3 が発振 → C_NLDO_OUT を 4.7 µF（0402）へ変更、または AVSS 直近に 10 µF を手付け。
> 4-5 が発振 → C_3V3_OUT に 0.5–1 Ω を直列に手付け（ESR 付加）して再確認。

---

## Step 5. ESP32 の起動確認（ROM ブートログ）

USB-C を **PC に接続**（データ線つきケーブル）。シリアルポートを **115200 baud** で開く。

> ROM ブートローダのログは 115200 baud で出る（アプリの `Serial.begin(9600)` とは別）。
> R_IO15_DN を実装したまま（Step 0-4 未実施）だとこのログは**出ない**ので、その場合は 5-3 だけ確認して Step 6 へ進む。

| # | 確認 | 合格 | 不合格の意味 |
|---|---|---|---|
| 5-1 | `rst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)` 相当が出る | **合格** | — |
| 5-2 | `flash read err`／`ets_main.c` でループ／文字化けの連続 | — | **GPIO12 ストラップ（B1）を疑う。** R_RST_UP が実装されていないか目視確認。実装されていたら除去（0603 なので手はんだで外せる）。外せない場合は Step 6-0 の eFuse 手順へ |
| 5-3 | PC 側にシリアルポートが列挙される（`ls /dev/cu.usbserial*` など） | **合格**（CH340C が enumerate している） | ポートが出ない → CH340C の VCC/V3/UD±、USB-C の VBUS/D± 経路（ECO L4 のペグ穴修理）を疑う |
| 5-4 | Step 2 の定常電流が **80 mA 以上**に増える | 合格（ESP32 が動作している） | — |

### Step 6-0（不合格 5-2 の救済のみ）eFuse による恒久回避
> **不可逆操作。R_RST_UP を物理的に外せる場合は外す方が良い。**
```
espefuse.py --port <PORT> set-flash-voltage 3.3V
```
XPD_SDIO_FORCE + XPD_SDIO_REG + XPD_SDIO_TIEH を焼き、以後 GPIO12(MTDI) は無視される。
書き込みモードに入れるため、実行時は GPIO0 を Low にする必要がある（自動リセット回路が効くので通常は不要）。

---

## Step 6. ファーム書き込み

```
esptool.py --chip esp32 --port <PORT> --baud 460800 flash_id
esptool.py --chip esp32 --port <PORT> --baud 460800 write_flash 0x1000 <bootloader.bin> 0x8000 <partitions.bin> 0x10000 <app.bin>
```
Arduino IDE を使う場合は Board = "ESP32 WROOM DA Module"（Cerelog 準拠）。

| # | 確認 | 合格値 |
|---|---|---|
| 6-1 | `flash_id` が成功し、`Detected flash size: 4MB` 相当が出る | **合格**（自動リセット回路 Q_EN/Q_IO0 が正しく動作している証拠） |
| 6-2 | 手で BOOT ボタンを押す必要がある | 本基板にボタンは無い。自動リセットが効かないなら Q_EN/Q_IO0/R_Q_EN_B/R_Q_IO0_B の実装と向きを確認 |
| 6-3 | 書き込み完了後 `Hard resetting via RTS pin...` で再起動 | 合格 |

### 書き込むファームに入れておくべき変更（レビュー F1/F2/F3）
| 項目 | 内容 |
|---|---|
| **F1** | `MISC1 = 0x00`（**0x20 は不可**）。**ECG は ch3 ではなく ch4**（IN4P=ECGP / IN4N=ECGN）。EEG 使用 ch は `CHnSET = 0x68`（Gain24 + SRB2）、**未使用 ch は `CHnSET = 0x81`**（power-down + MUX short） |
| **F2** | PWDN#/RESET# を High にして待機したあと、**改めて RESET# を Low(≥1 µs)→High**（または RESET コマンド 0x06）→ 18 tCLK(≈9 µs) 待ち → SDATAC → 以降のレジスタ操作 |
| **F3** | **ADS1299 の GPIO レジスタ (0x14) を絶対に書かない**（GPIO1–4 は GND 直結のため、出力 High にすると恒常短絡） |

---

## Step 7. ADS1299 の生存確認

### 7-1. ID レジスタ読み出し（最重要）
`SDATAC`(0x11) を送ってから `RREG 0x00`（0x20, 0x00）を実行。

| 確認 | 合格値 |
|---|---|
| ID レジスタ | **`(ID & 0x1F) == 0x1E`**（典型値 **0x3E**）。上位 3 bit は REV_ID で個体差あり |
| 内訳（SBAS499C Table 12） | bit4 = 1 固定 / DEV_ID[3:2] = 11b（ADS1299-x）/ NU_CH[1:0] = 10b（8ch） |
| 0x00 または 0xFF が返る | **不合格** → 末尾の切り分けフローへ |

### 7-2. 全レジスタのライト／リードバック
CONFIG1 に 0x96、CONFIG3 に 0xEC を書き、読み戻して一致すること。**不一致なら SPI 配線（SCLK/DIN/DOUT/CS#）を疑う。**

### 7-3. VCAP1 の立ち上がり時間（**C_VCAP1 を 100 µF にした影響の実測。必ず実施**）
オシロの **プローブ GND を AVSS に当て**、C_VCAP1 の非 AVSS 側（= ADS1299 pin28）を観測。USB を挿した瞬間からトリガ。

| 確認 | 合格値 |
|---|---|
| VCAP1 が **AVSS 基準で +1.1 V** に達するまでの時間 | ファームの「PWDN/RESET High → 最初の SPI アクセス」までの待機時間より **短い**こと |
| 実測が待機時間（現行 1000 ms）を超える | **待機時間をその 1.5 倍以上に延長する**（SBAS499C §11.1「Issue the reset after tPOR **or after the VCAP1 voltage is greater than 1.1 V, whichever time is longer**」／Figure 67） |
| 参考: tPOR | 2^18 / 2.048 MHz = **128 ms**（内部発振使用時） |

### 7-4. VREFP の確認（**初期化後にのみ有効**）
CONFIG3 の PD_REFBUF=1（=0xEC 書き込み）後に測る。

| 測定 | 合格値 |
|---|---|
| **AVSS 基準**の VREFP（pin24） | **+4.49 〜 +4.51 V** |
| **GND 基準**の VREFP | **+1.99 〜 +2.01 V** ← AVSS(−2.5 V) + 4.5 V |

> ⚠️ `08_simplified_power_design.md` の TP 表は「TP_VREFP = +4.500 V」とだけ書いているが、**GND 基準では +2.0 V** である。テスタを GND 基準で当てて「4.5 V が出ない」と誤判定しないこと。

### 7-5. DRDY の確認
`START` を High にして `RDATAC`。GPIO27(DRDY#) をオシロで観測。

| 確認 | 合格値 |
|---|---|
| DRDY# の周期 | **4.00 ms ± 2.5 %**（250 SPS。内部発振の確度 −40〜85 °C で ±2.5 %、25 °C なら ±0.5 %） |
| DRDY# が出ない | CLKSEL(pin52)=DVDD の導通、START(pin38) のレベル、RESET シーケンス（F2）を疑う |

---

## Step 8. ノイズ測定

### 8-1. 内部短絡（デバイス自身のノイズ）
全 ch を `CHnSET = 0x61`（Gain=24, MUX=001 = input shorted to (VREFP+VREFN)/2）に設定、250 SPS、1000 サンプル以上取得。

| 確認 | 合格値 |
|---|---|
| 入力換算ノイズ | **≤ 0.30 µVrms**（SBAS499C **Table 4**: Gain=24 / 250 SPS / −3dB BW 65 Hz の typ は **0.14 µVrms、0.98 µVpp**）。0.14 に近いほど良い |
| 0.5 µVrms を超える | 電源ノイズ（Step 4）またはレイアウトを疑う |

### 8-2. 外部短絡（基板の入力段込み）
J2 の全電極ピンと A2（pin10）をジャンパで短絡し、`CHnSET = 0x60`（Gain=24, MUX=000 normal）で測定。

| 確認 | 合格値 |
|---|---|
| 入力換算ノイズ | **≤ 0.40 µVrms**。理論値は デバイス 0.14 µVrms と直列 20 kΩ の熱雑音 0.146 µVrms(65 Hz 帯域) の二乗和 ≈ **0.20 µVrms** |
| 8-1 と大差ない | 合格（入力段が健全） |
| 8-2 だけ極端に悪い | 入力の 10 kΩ / C_DIF / C_CM の実装、電極ラインのリーク、BIAS ループの発振（8-3）を疑う |

### 8-3. BIAS(DRL) ループの発振確認（**レビュー N1。必ず実施**）
CONFIG3 = 0xEC（PD_BIAS=1）、BIAS_SENSP = 使用 ch のビット を設定した状態で、
オシロで **BIASOUT（R_BIAS_SER の ADS1299 側）** を観測。

| 確認 | 合格値 |
|---|---|
| BIASOUT の波形 | **持続発振が無いこと**（DC ≈ 0 V 付近で静か） |
| 発振している／全 ch のノイズが 8-1 より 1 桁悪い | **C_BIAS_INV を外す（DNP）** → 再測定。改善しなければ **R_BIAS_FB(0805) の上に 1.5 nF(0402) を手付けで並列**に載せる（TI SBAS499C Figure 68 の推奨構成 = 1 MΩ ∥ 1.5 nF に一致させる） |

### 8-4. 電源スイッチングの漏れ込み
8-2 の状態で取得したデータを FFT。

| 確認 | 合格値 |
|---|---|
| 10–65 Hz 帯にスプリアス | 電源起因のスパイクが無いこと（LM2664 の fSW は 40–80 kHz で帯域外だが、折り返しが無いか確認） |
| 50 Hz（マレーシアの商用周波数） | 電極開放時は大きく出て正常。短絡時に大きいなら基板起因 |

---

## Step 9. 動作確認

| # | 確認 | 合格値 |
|---|---|---|
| 9-1 | ステータス LED（GPIO17）が点灯する | 目視で明るく点灯（R_LED=100 Ω で約 4–5 mA） |
| 9-2 | 37 バイトパケットがホストに届く | START marker `0xAB 0xCD` / LENGTH `0x1F` / END `0xDC 0xBA`、チェックサム一致 |
| 9-3 | ハンドシェイクで 115200 baud に切り替わる | パケットの取りこぼしが無い |
| 9-4 | ch4 に ECG 電極を当てて心電波形が見える | R 波が識別できる（F1 の ch4 設定が正しいことの確認） |
| 9-5 | ch1/ch2 に前頭電極＋A2 参照で EEG が見える | 開閉眼でアルファ波（8–12 Hz）の増減が見える |
| 9-6 | 実運用電源での連続動作（30 分） | **モバイルバッテリでは自動オフしないことを確認する**（消費約 105 mA。低電流オートオフ付きのバッテリだと切れる。切れる個体なら PC の USB ポートか低電流モード対応バッテリを使う運用に決める） |

---

## 切り分けフロー

### A. Step 2 で電流制限に張り付く
1. 電源を切り、Step 1 の抵抗測定をやり直す
2. 5 V を 1 V まで下げて印加し、サーモカメラ／指で発熱箇所を探す
3. FB1/FB2/FB3 を順に外して、どの系統が短絡しているか切り分ける

### B. Step 3 で VNEG5 が出ない
- LM2664 pin4(SD) が pin5(V+) と同電位か → 違えば実装不良
- C_LM_FLY(10 µF) が pin6(CAP+)–pin3(CAP−) に載っているか
- pin2(OUT) の負荷が重すぎないか（VNEG5–GND 抵抗を測る）

### C. Step 3 で AVSS が出ない（VNEG5 は出ている）
- **TPS72325 pin3(EN) が pin2(IN) と同電位（≈−4.8 V）か**を最優先で確認
  - EN が 0 V なら disable 窓（−0.4〜+0.4 V）に入っており出力は出ない（ECO-1#1 未反映）
- pin1=GND / pin5=OUT の向き（DBV: 1 GND, 2 IN, 3 EN, 4 NR, 5 OUT）

### D. Step 5 で ESP32 が起動しない
1. VDD_ESP が **3.0 V 以上**か（Step 3-9）
2. ESP_EN の電圧が VDD_ESP と同じか（R_EN_UP 実装確認）。電源投入からの立ち上がりをオシロで見て、**τ ≈ 10 ms** で 3.3 V に達しているか
3. **`flash read err` が出る → GPIO12。R_RST_UP を外す（最優先）**
4. ROM ログが全く出ない → R_IO15_DN が実装されている（仕様どおり）か、CH340C 側の問題
5. CH340C が列挙されない → USB-C の VBUS/D± 経路（ECO L4 のペグ穴修理が正しく入っているか）、CH340C の V3(pin4) に 100 nF があるか

### E. Step 7-1 で ID が 0x00 / 0xFF
| 症状 | 疑うところ |
|---|---|
| 常に 0x00 | DOUT が Low 固定。ADS1299 が動いていない（AVDD/AVSS/DVDD を再確認）、または R_MISO(0 Ω) 未実装 |
| 常に 0xFF | DOUT が High 固定／未接続。R_MISO、ADS pin43 のはんだ、CS# が Low になっているか |
| 値が不安定 | SPI モード（**SPI_MODE1 = CPOL0/CPHA1**）、クロック 4 MHz、CS# のタイミング |
| SCLK が出ていない | ESP32 の VSPI 設定（GPIO18/23/19/5）とファームの define |
| DRDY が来ない | CLKSEL(pin52)=DVDD、RESET シーケンス（F2）、START(pin38) |

### F. Step 8 でノイズが規格の 3 倍以上
1. Step 4 の電源リップル／発振を再確認
2. 8-3 の BIAS ループ発振を確認（C_BIAS_INV を外して再測定）
3. USB ケーブルを外し、モバイルバッテリ単独給電で再測定（PC 経由のグランドループ切り分け）
4. 筐体・電極ケーブルのシールド（**J2 pin12 は CHASSIS_GND = USB シェル直結。電極を接続しないこと**）

---

## 記録テンプレート

```
基板シリアル:            測定日:            測定者:
Step 2 定常電流:        mA
Step 3  USB_5V:      V   VNEG5:      V   AVSS:      V   AVDD:      V   VDD_ESP:      V   DVDD:      V
Step 4  AVSS ripple:    mVpp   AVDD:    mVpp   VDD_ESP:    mVpp   発振の有無:
Step 5  ROM ログ: 出た / 出ない / flash read err     CH340 列挙: OK / NG
Step 6  write_flash: OK / NG
Step 7  ID = 0x        VCAP1 が +1.1V(AVSS基準) に達する時間:      ms
        VREFP(AVSS基準):      V     DRDY 周期:      ms
Step 8  内部短絡ノイズ:      µVrms   外部短絡:      µVrms   BIAS 発振: 無 / 有
Step 9  LED: OK/NG   パケット: OK/NG   ECG(ch4): OK/NG   EEG α波: OK/NG   バッテリ 30 分: OK/NG
所見:
```
