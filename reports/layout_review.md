# レイアウト品質レビュー（S7c）

`docs/ads1299_layout_checklist.md`（一次資料ベース、opusQ3）の **J1〜J11** と、S7 への申し送りが挙げた点を、**基板から実測**して答えたもの。

> **距離に閾値を置いていないのは意図的。** チェックリストが冒頭で 「TI はデカップリングの配置距離を一切数値で示していない。『◯ mm 以内』という数字を作ってはいけない」と釘を刺している。したがって距離は**測定値として載せるだけ**で合否にしない。TI が規則として書いているのは J1（バイパス C と IC の間にビアを置かない・同一層）なので、合否はそちらで取る。

## 1. デカップリング — J1（ビアを挟まない・同一層）

DS §12.1: *"Do not place vias between bypass capacitors and the active device. Placing the bypass capacitors on the same layer as close to the active device yields the best results."*

> **J1 が効くのは配線で配る電源だけ。** この基板でベタになっているのは `AVDD`, `AVSS`, `CHASSIS_GND`, `GND`, `USB_5V`, `VDD_ESP`。ベタ電源はパッド→ビア→ベタ→ビア→ピンで繋がるので、「経路にビアがある」のはスタックアップの性質であってレイアウトの誤りではない。配線で配っている **VCAP1〜4 と VREFP** が J1 の対象。

| コンデンサ | ADS ピン | 配り方 | 直線 [mm] | 銅箔経路 [mm] | 経路上のビア | 同一層 | J1 | 戻り側 | 戻り via まで [mm] |
|---|---|---|---|---|---|---|---|---|---|
| C_AVDD_P19 | 19 (AVDD) | ベタ | 3.10 | 配線経路なし | — | はい | — | GND | 0.83 |
| C_AVDD_H | 21 (AVDD) | ベタ | 8.47 | 配線経路なし | — | はい | — | GND | 0.77 |
| C_AVDD_B | 21 (AVDD) | ベタ | 8.62 | 配線経路なし | — | はい | — | GND | 0.78 |
| C_AVDD_H | 22 (AVDD) | ベタ | 8.39 | 配線経路なし | — | はい | — | GND | 0.77 |
| C_VREFP_10u | 24 (VREFP) | 配線 | 6.46 | 9.40 | 0 | はい | OK | AVSS | 1.03 |
| C_VREFP_100n | 24 (VREFP) | 配線 | 3.40 | 6.47 | 0 | はい | OK | AVSS | 1.96 |
| C_VREFP_10n | 24 (VREFP) | 配線 | 2.83 | 2.55 | 0 | はい | OK | AVSS | 1.92 |
| C_VCAP4 | 26 (VCAP4) | 配線 | 5.24 | 9.00 | 2 | はい | **NG** | AVSS | 0.60 |
| C_VCAP1 | 28 (VCAP1) | 配線 | 9.89 | 17.40 | 2 | はい | **NG** | AVSS | 0.95 |
| C_VCAP1_H | 28 (VCAP1) | 配線 | 1.36 | 1.36 | 0 | はい | OK | AVSS | 2.51 |
| C_VCAP2 | 30 (VCAP2) | 配線 | 1.53 | 1.53 | 0 | はい | OK | AVSS | 0.94 |
| C_AVDD_P36 | 56 (AVDD) | ベタ | 16.29 | 配線経路なし | — | はい | — | GND | 1.02 |
| C_AVDD_P31 | 56 (AVDD) | ベタ | 14.13 | 配線経路なし | — | はい | — | GND | 2.10 |
| C_AVDD1_1u | 54 (AVDD1) | ベタ | 4.10 | 配線経路なし | — | はい | — | AVSS | 1.64 |
| C_AVDD1_100n | 54 (AVDD1) | ベタ | 3.95 | 配線経路なし | — | はい | — | AVSS | 3.65 |
| C_AVDD1_10n | 54 (AVDD1) | ベタ | 4.98 | 配線経路なし | — | はい | — | AVSS | 5.87 |
| C_AVDD1_10u | 54 (AVDD1) | ベタ | 5.54 | 配線経路なし | — | はい | — | AVSS | 1.41 |
| C_VCAP3 | 55 (VCAP3) | 配線 | 3.36 | 4.39 | 2 | はい | **NG** | AVSS | 2.75 |
| C_VCAP3_H | 55 (VCAP3) | 配線 | 2.10 | 2.10 | 0 | はい | OK | AVSS | 2.91 |
| C_AVDD_P59 | 59 (AVDD) | ベタ | 4.50 | 配線経路なし | — | はい | — | GND | 0.57 |
| C_DVDD_P58 | 48 (DVDD) | 配線 | 11.48 | 22.11 | 0 | はい | OK | GND | 0.65 |
| C_DVDD_H | 48 (DVDD) | 配線 | 12.09 | 17.14 | 0 | はい | OK | GND | 0.70 |
| C_DVDD_P40 | 50 (DVDD) | 配線 | 6.23 | 13.67 | 0 | はい | OK | GND | 0.70 |
| C_DVDD_10u | 50 (DVDD) | 配線 | 9.89 | 18.01 | 0 | はい | OK | GND | 0.72 |
| C_AVSS_P17 | 20 (AVSS) | ベタ | 6.28 | 配線経路なし | — | はい | — | GND | 0.60 |
| C_AVSS_H | 20 (AVSS) | ベタ | 9.49 | 配線経路なし | — | はい | — | GND | 0.56 |
| C_AVSS_P30 | 32 (AVSS) | ベタ | 9.29 | 配線経路なし | — | はい | — | GND | 0.63 |
| C_AVSS_P37 | 57 (AVSS) | ベタ | 16.22 | 配線経路なし | — | はい | — | GND | 0.69 |
| C_AVSS_P60 | 58 (AVSS) | ベタ | 17.79 | 配線経路なし | — | はい | — | GND | 0.58 |
| C_AVSS_B | 58 (AVSS) | ベタ | 19.23 | 配線経路なし | — | はい | — | GND | 0.73 |

**配線で配る電源のうち、ビアを挟んでいるのは 3 経路。**

- `C_VCAP4` → ADS ピン 26（VCAP4）: ビア 2 個・銅箔 9.00 mm
- `C_VCAP1` → ADS ピン 28（VCAP1）: ビア 2 個・銅箔 17.40 mm
- `C_VCAP3` → ADS ピン 55（VCAP3）: ビア 2 個・銅箔 4.39 mm

## 2. VREFP の 3 個は近い順に並んでいるか

| コンデンサ | ADS pin24 から [mm] |
|---|---|
| C_VREFP_10n | 2.83 |
| C_VREFP_100n | 3.40 |
| C_VREFP_10u | 6.46 |

## 3. J2 — AVDD1 / AVSS1 のスター接続

DS §11: *"AVDD1 provides the supply to the charge pump block and has transients at fCLK. Therefore, star connect AVDD1 to the AVDD pins and AVSS1 to the AVSS pins."*

**これは銅箔ではなくネットリストで決まる。** TI が求めているのは AVDD1 / AVSS1 を**独立したネットにして**、細い専用配線で AVDD / AVSS に 1 点で繋ぐこと。この基板の回路図はピン 54 を `AVDD` に、ピン 53 を `AVSS` に直結しており、**そもそも別ネットになっていない**。したがって銅箔をどう引いてもスター接続にはならず、**PCB 側で直せる問題ではない（回路図の変更＝Rev.B 案件）**。

| ピン | 名前 | 回路図のネット | 独立ネット | パッド下のゾーン | 所見 |
|---|---|---|---|---|---|
| 54 | AVDD1 | `AVDD` | **いいえ** | In1.Cu=GND, In2.Cu=AVDD | shares the AVDD net and the AVDD plane -- a star connection would need a separate AVDD1 net in the schematic (Rev.B) |
| 53 | AVSS1 | `AVSS` | **いいえ** | In1.Cu=GND, In2.Cu=AVDD | shares the AVSS net and the AVSS plane -- a star connection would need a separate AVSS1 net in the schematic (Rev.B) |

> **影響**: ADS1299 は内部チャージポンプを 2.048 MHz で回しており、そのリップルが AVDD / AVSS 全体に載る。Rev.A では受容し、火入れ時に AVDD のリップルを実測して Rev.B の判断材料にすること。

## 4. J5 / B-4 — SPI と USB 差動のリターン経路

DS §12.1 は「グラウンドプレーンが切れていたり他の配線がリターン電流を妨げていたりすると、電流は遠回りを強いられ放射が増える」と述べている。判定は **直下の In1 が GND で埋まっていること**と**In1 に他の配線が無いこと**。

> ベタが無い点をそのまま数えると**ビアのアンチパッド**まで「分割」に見える。実測 187 点はすべて**その配線自身のビア**から 0.2 mm 以内だった（リターン電流もそのビアで層を替える）。そこで欠落は原因別に分類し、**ビアで説明できない空白だけ**を断絶とする。

| ネット | サンプル点 | 自ネットのビア | 他ネットのビア | **原因不明の空白** | 内層配線の上 | 判定 |
|---|---|---|---|---|---|---|
| ADS_SCLK_LOC | 354 | 0 | 0 | **0** | 0 | 連続 |
| ADS_DIN_LOC | 56 | 0 | 0 | **0** | 0 | 連続 |
| ADS_DOUT_LOC | 301 | 0 | 0 | **0** | 0 | 連続 |
| ADS_CS_N | 772 | 40 | 0 | **0** | 0 | 連続 |
| ADS_DRDY_N | 976 | 22 | 0 | **0** | 0 | 連続 |
| USB_DP | 351 | 61 | 0 | **0** | 0 | 連続 |
| USB_DM | 474 | 51 | 0 | **0** | 0 | 連続 |

## 5. 入力ネットの直下（In2 電源ベタ）

In2 は電源ベタ（AVDD / AVSS / USB_5V / VDD_ESP ほか）。

> **表の「またぐ」は問題ではない。** 入力配線のリターン電流が流れるのは**直下ではなく最も近いリファレンス面**で、この基板ではそれが **In1（GND、1 枚もの・2497.1 mm²・基板面積の 90%）**。In1 に切れ目が無い以上リターン経路は連続しており（第 4 節で実測）、In2 の境界越えはリターンの断絶にはならない。下表は「入力の下に何があるか」の記録であって合否ではない。

| 入力 | またぐ領域数 | 遷移回数 | 領域 |
|---|---|---|---|
| IN1P | 3 | 2 | AVSS, AVDD, (no fill) |
| IN1N | 3 | 8 | AVSS, (no fill), AVDD |
| IN2P | 3 | 2 | AVSS, (no fill), AVDD |
| IN2N | 3 | 8 | (no fill), AVSS, AVDD |
| IN3P | 3 | 2 | AVSS, (no fill), AVDD |
| IN3N | 3 | 8 | AVSS, (no fill), AVDD |
| IN4P | 3 | 2 | AVSS, (no fill), AVDD |
| IN4N | 3 | 8 | AVSS, (no fill), AVDD |
| IN5P | 3 | 2 | AVSS, (no fill), AVDD |
| IN5N | 3 | 8 | AVSS, (no fill), AVDD |
| IN6P | 3 | 2 | AVSS, (no fill), AVDD |
| IN6N | 3 | 8 | (no fill), AVSS, AVDD |
| IN7P | 3 | 2 | AVSS, (no fill), AVDD |
| IN7N | 3 | 8 | AVSS, (no fill), AVDD |
| IN8P | 3 | 2 | AVSS, AVDD, (no fill) |
| IN8N | 3 | 8 | AVSS, (no fill), AVDD |

## 6. 差動ペアの長さ差と間隔

| ペア | P 側 [mm] | N 側 [mm] | 差 [mm] | 最小間隔 [mm] |
|---|---|---|---|---|
| IN1P/IN1N | 22.38 | 20.52 | 1.85 | 0.331 |
| IN2P/IN2N | 20.38 | 18.52 | 1.85 | 0.331 |
| IN3P/IN3N | 18.38 | 16.53 | 1.85 | 0.330 |
| IN4P/IN4N | 16.38 | 14.53 | 1.85 | 0.330 |
| IN5P/IN5N | 14.80 | 14.94 | 0.15 | 0.441 |
| IN6P/IN6N | 16.80 | 16.94 | 0.14 | 0.330 |
| IN7P/IN7N | 18.79 | 18.94 | 0.14 | 0.331 |
| IN8P/IN8N | 20.79 | 20.94 | 0.14 | 0.331 |

## 7. 入力配線とデジタル配線の最接近

| 入力 | 相手 | 層 | 間隔 [mm] |
|---|---|---|---|
| IN8N | ADS_RESET_N | F.Cu | 8.190 |
| IN8P | ADS_RESET_N | F.Cu | 9.510 |
| IN2N | ADS_RESET_N | F.Cu | 9.741 |
| IN2P | ADS_RESET_N | F.Cu | 9.754 |
| IN3P | ADS_RESET_N | F.Cu | 9.754 |
| IN1N | ADS_RESET_N | F.Cu | 9.792 |
| IN3N | ADS_RESET_N | F.Cu | 9.792 |
| IN1P | ADS_RESET_N | F.Cu | 9.856 |
| IN4P | ADS_RESET_N | F.Cu | 9.856 |
| IN4N | ADS_RESET_N | F.Cu | 9.944 |
| IN5P | ADS_RESET_N | F.Cu | 10.056 |
| IN5N | ADS_RESET_N | F.Cu | 10.192 |
| IN6P | ADS_RESET_N | F.Cu | 10.350 |
| IN6N | ADS_RESET_N | F.Cu | 10.529 |
| IN7P | ADS_RESET_N | F.Cu | 10.729 |
| IN7N | ADS_RESET_N | F.Cu | 10.886 |

## 8. 入力配線とデジタル配線の交差（層違い）

**0 箇所。**

## 9. ベタの充填状態

> **穴の数が 0 なのは「アンチパッドが無い」という意味ではない。** KiCad は充填結果の穴を外形に切り込む形で保持するので `HoleCount` は 0 を返す。実際にはビアごとにアンチパッドが開いており、第 4 節のサンプリングがそれを 187 点として拾っている。意味があるのは面積のほう。

| ネット | 層 | 外形 | 面積 [mm²] | 基板面積比 |
|---|---|---|---|---|
| CHASSIS_GND | F.Cu | 2 | 43.16 | 1.6% |
| GND | In1.Cu | 1 | 2497.14 | 89.7% |
| AVSS | In2.Cu | 5 | 841.58 | 30.2% |
| USB_5V | In2.Cu | 5 | 360.89 | 13.0% |
| VDD_ESP | In2.Cu | 1 | 329.44 | 11.8% |
| USB_5V | In2.Cu | 1 | 282.70 | 10.2% |
| AVDD | In2.Cu | 1 | 280.33 | 10.1% |
| VDD_ESP | In2.Cu | 8 | 215.61 | 7.7% |
| VDD_ESP | In2.Cu | 1 | 75.36 | 2.7% |
| VDD_ESP | In2.Cu | 4 | 0.00 | 0.0% |

**In1 = GND が 1 枚もので 2497.1 mm²（基板面積の 90%）。**分割は無く、これがすべての信号のリターン面になっている。チェックリスト B-3 が本基板に推奨した形そのもの。

**空に近いベタが 1 枚ある**: VDD_ESP@In2.Cu (4 外形, 0.0000 mm²)。VDD_ESP は 3 枚のベタに分かれており（S5 の申し送り）、そのうち 1 枚は充填の結果ほぼ何も残っていない。電気的には他の 2 枚が VDD_ESP を配っているので実害は無いが、**この 1 枚は何もしていない**。DRC も `isolated_copper` / `copper_sliver` を報告していない。

## 10. チェックリスト J3〜J11

| # | 実測 | 指針 | 判定 |
|---|---|---|---|
| J3 VCAP1 value | 100uF | 100 uF (DS Pin Functions) | OK |
| J3 VREFP bulk >= 10 uF | 10uF 50V X5R 1206 | >= 10 uF across VREFP-VREFN | OK |
| J4 VCAP1 dielectric | CL31A107MQHNNNE | C0G / NP0 / tantalum (DS 11, vibration) | **要判断** |
| J6 RESV1 (31) to DGND | GND | GND | OK |
| J7 unused analog inputs to AVDD | none unconnected | AVDD, not GND and not open | OK |
| J8 CH340C XI open, no series R on D+/D- | SOP-16 CH340C has no crystal pin (7=NC., 8=OUT#); resistors on USB_DP/USB_DM: none | internal oscillator, D+/D- straight through | OK |
| J9 USB D+/D- length delta | 11.534 mm (D+ 33.304, D- 44.838) | < 45 mm (Full Speed, H-2) | OK |
| J10 regulators and their capacitors on one side | {"AMS1117": "front", "TLV70025": "front", "TPS72325": "front", "LM2664": "front"} | all front (no part is on the back of this board) | OK |
| J11 ESP32 antenna clear of the board | module right edge 175.01 mm, board right edge 181.62 mm, overhang -6.61 mm | antenna over a cut-out or off the edge | **要判断** |

- **J4 VCAP1 dielectric**: MPN CL31A107MQHNNNE -- a class-2 dielectric here is a recorded design decision, not a pass

- **J11 ESP32 antenna clear of the board**: the module sits inside the outline, so the antenna is over board material -- a Rev.A acceptance, visible in the preview render

## 11. 改善の試行（申し送りの「人が見るべき点」3・4）

候補が採用されるのは、**現在より近く、かつビアを 1 個も使わずにピンへ届く**位置だけ。1 mm 近づけてもビアが残るなら改善ではないので採らない。

| 部品 | 現在 [mm] | 調べた位置 | 結果 |
|---|---|---|---|
| C_VCAP3 → U_ADS.55 | 3.36 | 108 | no position between 0.4 mm and 3.36 mm of the pin clears the neighbouring bodies, courtyards and copper while reaching the pin without a via |
| C_VCAP3_H → U_ADS.55 | 2.10 | 0 | no position between 0.4 mm and 2.10 mm of the pin clears the neighbouring bodies, courtyards and copper while reaching the pin without a via |
| C_VCAP1 → U_ADS.28 | 9.89 | 0 | no position between 0.4 mm and 6.00 mm of the pin clears the neighbouring bodies, courtyards and copper while reaching the pin without a via |
| C_VCAP1_H → U_ADS.28 | 1.36 | 0 | no position between 0.4 mm and 1.36 mm of the pin clears the neighbouring bodies, courtyards and copper while reaching the pin without a via |
| C_VCAP4 → U_ADS.26 | 5.24 | 62 | no position between 0.4 mm and 5.24 mm of the pin clears the neighbouring bodies, courtyards and copper while reaching the pin without a via |

