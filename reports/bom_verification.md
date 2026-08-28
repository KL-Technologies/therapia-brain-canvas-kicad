# Brain Canvas Rev.A — BOM 実体照合レポート（2026-08-28）

対象: `data/parts_lcsc.csv` / `board/Therapia_EEG-HRV.kicad_pcb`  
実装点数 **135** ・品番数 **30**  
判定: **NG 2** / **要確認 7** / OK 21

## 照合方法

各 C 番号を LCSC 商品ページ / EasyEDA 部品 API / JLCPCB partdetail の いずれか複数で取得し、data/parts_lcsc.csv の値・パッケージと kicad_pcb のフットプリント実測パッド寸法、および contract/netlist_from_kicad_pcb.json の実接続ネットに突合した。

出典 URL は各行に記録。取得できなかった項目は「取得不能」と明記し、推測では埋めていない。

## 結論（発注前に潰すべき項目）

| 優先 | 品番 | designator | 問題 | 推奨対処 |
|---|---|---|---|---|
| **1** | `C94221` | FB1–FB5 (5) | LCSC/JLC に**存在しない品番**。3 ソースで不存在を確認 | `C1017`（Sunlord GZ2012D601TF, L0805, **Basic**, 在庫 75,200）へ差し替え |
| **2** | `C72043` | D_LED (1) | 実体は緑 LED **Vf 3.3V**。3.3V GPIO + 330Ω では電流ほぼ 0 で点灯しない | `C72044`（Everlight 19-217/R6C 赤, Vf 1.95V, フットプリント・極性とも完全一致）へ差し替え。330Ω のまま約 4.1mA。詳細は末尾の追記を参照 |
| 3 | `C13585` | C_VREFP_10u (1) | CSV の MPN が誤り（実体は …K**B**H…, 50V） | **設計上は OK**。BOM の MPN 文字列のみ訂正。C15008 代替は不要 |
| 4 | `C1546` | C_AVDD1_10n, C_VREFP_10n (2) | designator は「10n」だが実装は 100pF | 10nF が正なら `C15195`(0402) 相当へ。現状維持なら designator をリネーム |
| 5 | `C369159` `C69932` `C701341` `C19619` | F1 / TPS72325 / U_MCU / TLV70025 | 在庫表示が薄い or ソース間で乖離 | JLC カート投入時に実数を確認。F1 の同一フットプリント代替は `C883122` |
| 6 | `C2840012` `C19619` `C72043` | J2 / TLV70025 / D_LED | CSV のパッケージ表記が実体と不一致 | **基板側フットプリントは全て正しい**。CSV のラベルのみ訂正 |

## NG（発注前に必ず修正）

### `C72043` — D_LED（1 点）

- **設計意図**: value='LED_Y'（黄）+ R_LED 330Ω で ESP32 GPIO(3.3V) から駆動
- **取得した実体**: 19-217/GHC-YR1S2/3T / Everlight Elec / LED0603-RD / LED 0603 / Emerald Green(518nm) / Vf 3.3V @20mA / 199mcd
- **判定理由**: 実体は Emerald Green・**Vf 3.3V**。3.3V GPIO − Vf3.3V = 0V となり 330Ω では電流がほぼ流れず点灯しない/極端に暗い。また BOM value 'LED_Y'（黄）と実体（緑）が不一致。ECO-2#9 で 10kΩ→330Ω に変えた前提は Vf≈2V の赤/黄 LED。
- 補足: 色（緑）と Vf 3.3V は LCSC ページ・JLC partdetail の 2 ソースで一致。JLC 実装区分は 3 URL とも表示されず取得不能。
- **推奨代替**: `C72044` 19-217/R6C-AL1M2VY/3T / LED0603-RD / LED 0603 / 赤 617.5nm / Vf 1.95V @5mA / 11.5-28.5mcd / 120deg / 60mW / JLC **Extended** / 在庫 215,065
  - D_LED 第 1 候補。現フットプリントと**パッケージ名が完全一致**（LED0603-RD）で、ピン生データも pin1='C' / pin2='A'（C72043 と同一シリーズ・同一ライブラリ）。3.3V - 1.95V = 1.35V / 330Ω = 約 4.1mA。在庫は EasyEDA API 215,065（SZ 902,100）に対し LCSC 商品ページは 'Not available now' 表示で食い違う。
  - 出典: https://www.lcsc.com/product-detail/C72044.html , https://jlcpcb.com/partdetail/EverlightElec-19_217_R6C_AL1M2VY3T/C72044 , https://easyeda.com/api/products/C72044/components
- **推奨代替**: `C72038` 19-213/Y2C-CQ2R2L/3T(CY) / LED0603-RD-YELLOW / LED 0603 / 黄 / Vf 1.7-2.3V @20mA / 90-180mcd / JLC **Extended** / 在庫 70,862
  - D_LED 第 2 候補。ピン生データは pin1='C' / pin2='A' で**現基板の極性と一致**（`P~show~1~1~...C~start` / `P~show~1~2~...A~end`）。BOM の value 'LED_Y'（黄）とも色が一致し、輝度は C72044 より高い。ただしパッケージ名は 'LED0603-RD-**YELLOW**' で現フットプリント名と厳密には別名（0603 ランド自体は同等とみられるがカート投入時に要プレビュー確認）。Vf 2.0V 換算で (3.3-2.0)/330 = 約 3.9mA。
  - 出典: https://jlcpcb.com/partdetail/C72038 , https://easyeda.com/api/products/C72038/components
- 出典: https://www.lcsc.com/product-detail/C72043.html , https://jlcpcb.com/partdetail/EverlightElec-19_217_GHC_YR1S23T/C72043 , https://easyeda.com/api/products/C72043/components
- **【確定】この推奨は覆った。** カート投入時（2026-08-28）に `C72044` / `C72038` とも JLC 実装在庫 0。**採用は `C84268`**（末尾「カート投入時の差替 2026-08-28」）。

### `C94221` — FB1, FB2, FB3, FB4, FB5（5 点）

- **設計意図**: FB_600R 600Ω@100MHz フェライトビーズ 0805 x5
- **取得した実体**: 取得不能（部品が存在しない） / - / - / -
- **判定理由**: **この C 番号は LCSC/JLC に存在しない**（3 ソースで不存在を確認）。このまま発注すると JLC 側で部品が引けない。正しい品番は C1017。
- 補足: LCSC 商品ページ HTTP 404 / EasyEDA API 'Component not found' 404 / JLC partdetail は空欄（No specifications available）。3 ソースとも不存在。CSV が意図した GZ2012D601TF の正しい品番は C1017。
- **推奨代替**: `C1017` GZ2012D601TF / L0805 / フェライトビーズ 600Ω@100MHz +-25% / 定格 500mA / DCR 300mΩ / 0805 / JLC **Basic** / 在庫 75,200
  - C94221 が意図していた GZ2012D601TF の正しい品番。EasyEDA パッケージ名 'L0805' は KiCad 側フットプリントと完全一致。
  - 出典: https://jlcpcb.com/partdetail/Sunlord-GZ2012D601TF/C1017 , https://easyeda.com/api/products/C1017/components
- 出典: https://www.lcsc.com/product-detail/C94221.html , https://easyeda.com/api/products/C94221/components , https://jlcpcb.com/partdetail/C94221

## 要確認

### `C13585` — C_VREFP_10u（1 点）

- **設計意図**: ECO-3#12: 10uF 1206 25V（VREFP=4.5V の DC バイアス減衰対策）
- **取得した実体**: CL31A106KBHNNNE / Samsung Electro-Mechanics / C1206 / 10uF / 50V / X5R / +-10% / 1206
- **判定理由**: 【裏取り完了】実体は CL31A106K**B**HNNNE = 10uF **50V** X5R 1206。CSV の MPN 'CL31A106KAHNNNE' は誤り。値・パッケージ・材質は意図を満たし、50V なので 25V 品より DC バイアス減衰が小さく設計上はむしろ良好。→ C15008 での代替は不要。BOM の MPN 文字列のみ訂正。
- 補足: CSV の MPN 'CL31A106KAHNNNE' は誤り。LCSC ページ・JLC partdetail・EasyEDA API の 3 ソースとも 'CL31A106K**B**HNNNE / 50V'。在庫は LCSC ページ 917,300 に対し EasyEDA API 0/0 で食い違う。
- 出典: https://www.lcsc.com/product-detail/C13585.html , https://jlcpcb.com/partdetail/C13585 , https://easyeda.com/api/products/C13585/components

### `C1546` — C_AVDD1_10n, C_VREFP_10n（2 点）

- **設計意図**: designator は C_AVDD1_10n / C_VREFP_10n（= 10nF を示唆）
- **取得した実体**: 0402CG101J500NT / FH (Fenghua) / C0402 / 100pF / 50V / C0G(NP0, 型番 CG) / +-5% / 0402
- **判定理由**: 実体は 100pF C0G。ECO-2#7 が C_NR で修正したのと同型の 『名前は 10n・中身は 100pF』の不整合が 2 個所残っている。AVDD/VREFP には別途 100nF+10uF が並列なので実害は小さいが意図確認を推奨。
- 出典: https://easyeda.com/api/products/C1546/components

### `C19619` — TLV70025（1 点）

- **設計意図**: TLV70025 +2.5V LDO / CSV package='SOT-353'
- **取得した実体**: TLV70025DDCR / Texas Instruments / SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR / LDO +2.5V 固定 / 200mA / SOT-23-5(TI DDC)
- **判定理由**: 実体は SOT-23-5（TI DDC パッケージ）。PCB フットプリントは SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR で **正しい**（EasyEDA パッケージ名と完全一致）。CSV の 'SOT-353' 表記のみ誤り。在庫 1,480-2,186 でやや薄い。
- 補足: LCSC ページ 1,480 / EasyEDA API 2,186（SZ 1,577）。CSV の package 'SOT-353' は誤りで実体は SOT-23-5。
- 出典: https://www.lcsc.com/product-detail/C19619.html , https://easyeda.com/api/products/C19619/components

### `C2840012` — J2（1 点）

- **設計意図**: CSV value='Header_2x6' / package='HDR-2.54-2x6'
- **取得した実体**: PZ254V-11-12P / XFCN / HDR-TH_12P-P2.54-V-M / ピンヘッダ 1 列 x 12P / 2.54mm / スルーホール垂直 / 250V 3A
- **判定理由**: 実体は **1 列 x 12 ピン**（row=1）。PCB フットプリント HDR-TH_12P-P2.54-V-M も 12 パッド全て y=0 の 1 列なので**部品と基板は整合**。CSV のラベル表記のみ誤り。
- 補足: 1 列 12 ピン（2x6 ではない）。LCSC ページ・EasyEDA API とも row=1。
- 出典: https://www.lcsc.com/product-detail/C2840012.html , https://easyeda.com/api/products/C2840012/components

### `C369159` — F1（1 点）

- **設計意図**: Polyfuse hold 500mA / 1206（USB_VBUS_RAW→USB_5V）
- **取得した実体**: JK-NSMD050-13.2V / JK (Jinrui) / F1206 / PPTC リセッタブルヒューズ / hold 500mA / trip 1A / 13.2V / 1206
- **判定理由**: 仕様（500mA hold / 1206）は意図と一致し F1206 フットプリントとも整合。ただし LCSC 商品ページが 'Not available now' 表示で在庫要確認。
- 補足: LCSC 商品ページは 'Not available now'。EasyEDA API は 6,160/53,060。
- **代替候補**: `C883122` BSMD1206-050-6V / F1206 / PPTC リセッタブルヒューズ hold 500mA / 6V / 1206 / JLC **Extended** / 在庫 3,420
  - F1 の同一フットプリント代替。定格電圧は 13.2V→6V に下がる点に注意。
- 出典: https://www.lcsc.com/product-detail/C369159.html , https://easyeda.com/api/products/C369159/components
- **【確定】** カート投入時（2026-08-28）に `C369159` は JLC 実装在庫 0。**採用は `C43379`**（13.2V を維持。末尾「カート投入時の差替 2026-08-28」）。

### `C69932` — TPS72325（1 点）

- **設計意図**: TPS72325 -2.5V LDO / SOT-23-5
- **取得した実体**: TPS72325DBVR / Texas Instruments / SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR / 負電圧 LDO -2.5V / 200mA / 超低ノイズ 60uVrms / SOT-23-5
- **判定理由**: MPN・パッケージ一致（EasyEDA パッケージ名が KiCad と完全一致）。LCSC 在庫 0（SZ 3,843）で在庫リスクあり。
- 補足: LCSC ページ 7,086 / EasyEDA API 0（SZ 3,843）。
- 出典: https://www.lcsc.com/product-detail/C69932.html , https://easyeda.com/api/products/C69932/components

### `C701341` — U_MCU（1 点）

- **設計意図**: ESP32-WROOM-32E-N4 / SMD モジュール
- **取得した実体**: ESP32-WROOM-32E-N4 / Espressif / WIFI-SMD_ESP32-WROOM-32E / ESP32 モジュール 4MB flash / SMD 25.5x18mm
- **判定理由**: MPN・パッケージ一致（47 パッド = 38 ピン + サーマル 9 分割）。在庫が LCSC ページ 29,577 と EasyEDA API 6 で大きく乖離。要カート確認。
- 補足: LCSC ページ 29,577 / EasyEDA API 6（SZ 916）。乖離が大きく要カート確認。
- 出典: https://www.lcsc.com/product-detail/C701341.html , https://easyeda.com/api/products/C701341/components

## 全品番一覧

| 判定 | C番号 | designator（数） | 取得した MPN / メーカー | 取得したスペック | 取得したパッケージ | KiCad フットプリント | JLC 区分 | LCSC 在庫 | SZLCSC 在庫 |
|---|---|---|---|---|---|---|---|---|---|
| **NG** | `C72043` | D_LED (1) | 19-217/GHC-YR1S2/3T / Everlight Elec | LED 0603 / Emerald Green(518nm) / Vf 3.3V @20mA / 199mcd | `LED0603-RD` | `LED0603-RD` | 取得不能 | 54,300 | 1,440,000 |
| **NG** | `C94221` | FB1, FB2, FB3, FB4, FB5 (5) | 取得不能（部品が存在しない） / - | - | `-` | `L0805` | 存在しない | 取得不能 | 取得不能 |
| 要確認 | `C13585` | C_VREFP_10u (1) | CL31A106KBHNNNE / Samsung Electro-Mechanics | 10uF / 50V / X5R / +-10% / 1206 | `C1206` | `Capacitor_SMD:C_1206_3216Metric` | Basic | 917,300 | 0 |
| 要確認 | `C1546` | C_AVDD1_10n, C_VREFP_10n (2) | 0402CG101J500NT / FH (Fenghua) | 100pF / 50V / C0G(NP0, 型番 CG) / +-5% / 0402 | `C0402` | `C0402` | Basic | 558,700 | 1,401,500 |
| 要確認 | `C19619` | TLV70025 (1) | TLV70025DDCR / Texas Instruments | LDO +2.5V 固定 / 200mA / SOT-23-5(TI DDC) | `SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR` | `SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR` | Extended | 2,186 | 1,577 |
| 要確認 | `C2840012` | J2 (1) | PZ254V-11-12P / XFCN | ピンヘッダ 1 列 x 12P / 2.54mm / スルーホール垂直 / 250V 3A | `HDR-TH_12P-P2.54-V-M` | `HDR-TH_12P-P2.54-V-M` | Extended | 28,720 | 取得不能 |
| 要確認 | `C369159` | F1 (1) | JK-NSMD050-13.2V / JK (Jinrui) | PPTC リセッタブルヒューズ / hold 500mA / trip 1A / 13.2V / 1206 | `F1206` | `F1206` | Extended | 6,160 | 53,060 |
| 要確認 | `C69932` | TPS72325 (1) | TPS72325DBVR / Texas Instruments | 負電圧 LDO -2.5V / 200mA / 超低ノイズ 60uVrms / SOT-23-5 | `SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR` | `SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR` | Extended | 7,086 | 3,843 |
| 要確認 | `C701341` | U_MCU (1) | ESP32-WROOM-32E-N4 / Espressif | ESP32 モジュール 4MB flash / SMD 25.5x18mm | `WIFI-SMD_ESP32-WROOM-32E` | `WIFI-SMD_ESP32-WROOM-32E` | Extended | 29,577 | 916 |
| OK | `C108573` | LM2664 (1) | LM2664M6X/NOPB / Texas Instruments | スイッチトキャパシタ電圧反転 / 1.8-5.5V in / 40mA / SOT-23-6 | `SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BR` | `SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BR` | Extended | 49,955 | 1,620 |
| OK | `C12530` | C_NLDO_OUT (1) | CL05A225MQ5NSNC / Samsung Electro-Mechanics | 2.2uF / 6.3V / X5R / +-20% / 0402 | `C0402` | `C0402` | Basic | 5,406,800 | 282,800 |
| OK | `C15008` | C_VCAP1 (1) | CL31A107MQHNNNE / Samsung Electro-Mechanics | 100uF / 6.3V / X5R / +-20% / 1206 | `C1206` | `Capacitor_SMD:C_1206_3216Metric` | Basic | 2,054,820 | 107,937 |
| OK | `C15195` | C_NR (1) | CL05B103KB5NNNC / Samsung Electro-Mechanics | 10nF / 50V / X7R / +-10% / 0402 | `C0402` | `C0402` | Basic | 4,411,600 | 266,400 |
| OK | `C1525` | C_3V3_H ほか (28) | CL05B104KO5NNNC / Samsung Electro-Mechanics | 100nF / 16V / X7R / +-10% / 0402 | `C0402` | `C0402` | Basic | 869,375 | 4,941,800 |
| OK | `C1588` | C_CM1N ほか (16) | CL10B102KB8NNNC / Samsung Electro-Mechanics | 1nF / 50V / X7R(型番 B) / +-10% / 0603 | `C0603` | `C0603` | Basic | 673,512 | 123,000 |
| OK | `C17477` | R_MISO, R_MOSI, R_SCLK, R_SRB_SER (4) | 0805W8F0000T5E / UNI-ROYAL | 0Ω ジャンパ / 0805 | `R0805` | `R0805` | Basic | 433,289 | 2,148,400 |
| OK | `C17514` | R_BIAS_FB, R_BIAS_SER (2) | 0805W8F1004T5E / UNI-ROYAL | 1MΩ / +-1% / 0805 | `R0805` | `R0805` | Basic | 203,700 | 872,900 |
| OK | `C19702` | C_3V3_B ほか (12) | CL10A106KP8NNNC / Samsung Electro-Mechanics | 10uF / 10V / X5R / +-10% / 0603 | `C0603` | `C0603` | Basic | 6,738,300 | 0 |
| OK | `C2146` | Q_EN, Q_IO0 (2) | S8050 J3Y(RANGE:200-350) / CJ (Changjiang) | NPN トランジスタ / hFE 200-350 / SOT-23-3 | `SOT-23-3_L3.0-W1.7-P0.95-LS2.9-BR` | `SOT-23-3_L3.0-W1.7-P0.95-LS2.9-BR` | Basic | 451,617 | 508,750 |
| OK | `C23138` | R_LED (1) | 0603WAF3300T5E / UNI-ROYAL | 330Ω / +-1% / 0603 | `R0603` | `R0603` | Basic | 470,600 | 359,100 |
| OK | `C23186` | R_CC1, R_CC2 (2) | 0603WAF5101T5E / UNI-ROYAL | 5.1kΩ / +-1% / 0603 | `R0603` | `R0603` | Basic | 897,098 | 1,796,800 |
| OK | `C237168` | C_DIF1 ほか (8) | 0805N103J500CT / Walsin | 10nF / 50V / NP0 / +-5% / 0805 | `C0805` | `C0805` | Extended | 152,260 | 5,820 |
| OK | `C25744` | R_IN1N ほか (16) | 0402WGF1002TCE / UNI-ROYAL | 10kΩ / +-1% / 0402 | `R0402` | `R0402` | Basic | 235,900 | 2,745,500 |
| OK | `C25804` | R_CS_UP ほか (11) | 0603WAF1002T5E / UNI-ROYAL | 10kΩ / +-1% / 0603 | `R0603` | `R0603` | Basic | 8,999,650 | 0 |
| OK | `C2765186` | J1 (1) | TYPE-C 16PIN 2MD(073) / SHOU HAN | USB Type-C レセプタクル 16P / SMD + 位置決めペグ / 5V 5A | `USB-C-SMD_TYPE-C-16PIN-2MD-073` | `USB-C-SMD_TYPE-C-6PIN-2MD-073` | Extended | 940,940 | 取得不能 |
| OK | `C476817` | U_ADS (1) | ADS1299IPAGR / Texas Instruments | 24bit 8ch 生体電位 AFE / TQFP-64(10x10) / MSL3 / $60.31 | `TQFP-64_L10.0-W10.0-P0.50-LS12.0-TL` | `TQFP-64_L10.0-W10.0-P0.50-LS12.0-TL` | Extended | 3,126 | 取得不能 |
| OK | `C52923` | C_3V3_IN ほか (10) | CL05A105KA5NQNC / Samsung Electro-Mechanics | 1uF / 25V / X5R / +-10% / 0402 | `C0402` | `C0402` | Basic | 3,790,400 | 3,663,900 |
| OK | `C6186` | AMS1117 (1) | AMS1117-3.3 / Advanced Monolithic Systems | LDO 3.3V fixed, SOT-223-3 | `SOT-223-3_L6.5-W3.4-P2.30-LS7.0-BR` | `SOT-223-3_L6.5-W3.4-P2.30-LS7.0-BR` | Basic | 222,228 | 113,340 |
| OK | `C7519` | D_ESD (1) | USBLC6-2SC6 / STMicroelectronics | USB ESD 保護ダイオードアレイ, SOT-23-6 | `SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL` | `SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL` | Extended | 28,668 | 3,590 |
| OK | `C84681` | U_USB (1) | CH340C / WCH | USB-UART ブリッジ / 内蔵クロック（水晶不要）/ SOP-16 | `SOP-16_L10.0-W3.9-P1.27-LS6.0-BL` | `SOP-16_L10.0-W3.9-P1.27-LS6.0-BL` | Extended | 61,409 | 63,893 |

## 在庫リスク順位

在庫はソース間で食い違うことがあるため、最終確定は JLC カート投入時とする。以下は「発注前に実数を確認すべき」順。

| 順位 | 品番 | designator | 取得できた在庫 | JLC 区分 | リスク内容 | 代替 |
|---|---|---|---|---|---|---|
| 1 | `C94221` | FB1–FB5 | — | 存在しない | 品番自体が引けない（在庫以前の問題） | `C1017` (Basic, 75,200) |
| 2 | `C701341` | U_MCU | LCSC ページ 29,577 / API **6** | Extended | ソース間の乖離が最大。ESP32 モジュールは代替が効きにくい | 同等品は要検討 |
| 3 | `C69932` | TPS72325 | LCSC ページ 7,086 / API **0**（SZ 3,843） | Extended | 負電圧 LDO は代替品が少ない。欠品時は基板が動かない | ピン互換の TPS723xx 系を要調査 |
| 4 | `C13585` | C_VREFP_10u | LCSC ページ 917,300 / API **0/0** | Basic | ソース間の乖離。Basic なので JLC 側は通常確保 | `C15008`(100uF 6.3V 1206) で代替可 |
| 5 | `C369159` | F1 | LCSC ページ **Not available now** / API 6,160 | Extended | 商品ページが在庫なし表示 | `C883122`（F1206 同一, 6V 定格に低下） |
| 6 | `C19619` | TLV70025 | 1,480〜2,186 | Extended | 絶対数が少ない。10 台分なら足りる | +2.5V 200mA SOT-23-5 LDO を要調査 |
| 7 | `C476817` | U_ADS | 3,126 | Extended | 単価 $60.31 と高額。数量確保より価格インパクト大 | 代替不可（設計の中核） |
| 8 | `C108573` | LM2664 | LCSC ページ 49,955 / API **0**（SZ 1,620） | Extended | ソース間の乖離 | — |

## JLC Extended 部品（手数料対象）

現 BOM の Extended は **11 品番**: `C237168`(C_DIF1), `C7519`(D_ESD), `C369159`(F1), `C2765186`(J1), `C2840012`(J2), `C108573`(LM2664), `C19619`(TLV70025), `C69932`(TPS72325), `C476817`(U_ADS), `C701341`(U_MCU), `C84681`(U_USB)

推奨差し替え（`C94221`→`C1017`, `C72043`→`C2286`）はいずれも Basic 品なので、Extended 品番数は増えない。`C369159`→`C883122` は Extended のままで増減なし。

## BOM 以外に気づいた点（参考・lead 判断用）

> 注: `contract/netlist_from_kicad_pcb.json` は 13:45 のスナップショットで、その後 `board/Therapia_EEG-HRV.kicad_pcb` が 16:46 に更新された（並行作業）。以下は **16:47 に基板ファイルを直接読み直した結果**に基づく。

- **ECO-1 は PCB に反映済み（再確認して訂正）**: 本レポート初版では「TPS72325 の pin3(EN) が `GND` のままで B1 致命バグが残存」と書いたが、これは 13:45 のネットリストに基づく古い所見だった。現在の基板ファイルでは **pin3 = `V_NLDO_IN`**（pin1=GND / pin2=V_NLDO_IN / pin4=TPS_NR / pin5=AVSS）で、ECO-1#1 は適用済み。
- **ECO-1/ECO-3 の新設・変更部品も配置済み（同上）**: `C_VCAP1_H`(VCAP1-AVSS)、`C_VCAP2`(VCAP2-AVSS)、`C_VCAP3`(VCAP3-AVSS)、`C_VCAP3_H`(VCAP3-AVSS) の 4 点が `C0402` で配置・結線済み。`C_VCAP1` と `C_VREFP_10u` も `C_1206_3216Metric` に差し替わっており ECO-3 の 1206 化も完了している。BOM 135 点と基板の点数は整合する。
- **D_LED まわりは未変更**: `D_LED` pad1=`GND` / pad2=`LED_A`、`R_LED` pad1=`STATUS_LED_DRV` / pad2=`LED_A` で、上記 LED の判定はそのまま有効。
- **DVDD は +3.3V 給電**: FB5 が `VDD_ESP → DVDD`。`08_simplified_power_design.md` の「AVDD と DVDD を共通 +2.5V」という記述と食い違う。実回路の 3.3V は ADS1299 の DVDD 定格範囲内で、ESP32 の 3.3V ロジックとも整合するため 回路としては妥当。ドキュメント側が古い。
- **フェライトビーズの DCR 前提が古い**: `08_simplified_power_design.md` は BLM18PG600SN1D（DCR 38mΩ / 2.5A）前提で電圧降下 5.7mV としているが、実体の GZ2012D601TF は **DCR 300mΩ / 定格 500mA**。FB3 は ESP32 系 80–240mA を通すため 降下は 24–72mV（想定の 4〜12 倍）。Rev.A は許容範囲だが、余裕を取るなら低 DCR 品を検討。
- **ADS1299 PAG にサーマルパッドは無い**: KiCad フットプリントは 64 パッドのみで実体と整合。`08_simplified_power_design.md` の「ADS1299 の thermal pad 直下に 9 個の via」は成立しない。
- **USB-C のフットプリント名**: KiCad 側 `USB-C-SMD_TYPE-C-6PIN-2MD-073` は EasyEDA 側 `…-16PIN-…` の名称欠落。パッド実体（12 SMD + 4 TH）は正しく、ピン割当も EasyEDA シンボルの pinName と netlist が一致しているため実害なし。

## 変更しなかったもの

本レポートは調査のみ。`data/parts_lcsc.csv`・`board/` は一切編集していない。差し替えの反映は lead 判断とする。

---

# 追記（2026-08-28、追加調査）

## 1. D_LED の代替を確定

### 前提：現基板側の極性

- フットプリント: `ProPrj_The-easyedapro:LED0603-RD`
- パッド実測: pad1/pad2 とも 0.8x0.8mm 角、x=-0.749 / +0.749mm（0603 ランド）
- **極性: pad1 = C（カソード）→ GND / pad2 = A（アノード）→ LED_A**
- 根拠: contract/netlist_easyeda_api_2026-08-28.tsv の D_LED 行が pinName を保持: `D_LED 1 C GND` / `D_LED 2 A LED_A`

シルクの向きではなく **EasyEDA シンボルの pinName** を根拠にした（J1 の ピン割当を確定したのと同じ方法）。`pinNumber` はライブラリ内連番でデータシートと一致しないことがあるため単独では使わない。

### 候補の比較

| | C番号 | MPN / 色 | EasyEDA パッケージ名 | ピン番号→名 | Vf | 330Ω・3.3V での電流 | JLC 区分 | 在庫(LCSC / SZLCSC) | 判定 |
|---|---|---|---|---|---|---|---|---|---|
| **第1候補** | `C72044` | 19-217/R6C-AL1M2VY/3T / 赤 617.5nm | `LED0603-RD` **完全一致** | **1=C, 2=A**（現基板と一致） | 1.95V @5mA | **約 4.1mA** | Extended | 215,065 / 902,100 | **採用推奨** |
| **第2候補** | `C72038` | 19-213/Y2C-CQ2R2L/3T(CY) / 黄 | `LED0603-RD-YELLOW`（別名） | **1=C, 2=A**（現基板と一致） | 1.7–2.3V @20mA | 約 3.9mA | Extended | 70,862 / 187,040 | 採用可 |
| 不採用 | `C2286` | KT-0603R / 赤 645nm | `LED-SMD_L1.6-W0.8-R-RD`（別名） | **1=A, 2=K**（**反転**） | 1.8–2.4V | 約 3.9mA | Basic | 624,750 / 0 | **NG（逆実装になる）** |
| 不採用 | `C183844` | 19-217/G7C-AM1N2B/3T / 黄緑 | `LED0603-RD` 一致 | 取得不能 | 取得不能 | — | Extended | 2,920 / 540 | 非推奨（在庫薄） |

### 判定理由

**`C72044` を第 1 候補とする。** 現在の `C72043` と同じ Everlight 19-217 シリーズ・同じ EasyEDA ライブラリの赤バリアントで、パッケージ名が `LED0603-RD` と完全一致する。ピン生データも `P~show~1~**1**~...~**C**~end~...` / `P~show~1~**2**~...~**A**~start~...` で pin1=カソード・pin2=アノード、現基板の pad1=GND(カソード) と一致するため、**C 番号の差し替えだけで済み、基板の銅箔も配線も触らなくてよい**。Vf 1.95V に対し (3.3−1.95)/330 = 約 4.1mA で、依頼の 3〜4mA 帯に収まる。

JLC 区分は Extended だが、差し替え前の `C72043` も同シリーズで、同ページに Basic バッジが出ていないため区分は実質変わらないと見込まれる（`C72043` の区分は 3 URL とも表示されず取得不能のままなので、断定はしない）。

**`C72038`（黄）を第 2 候補とする。** ピン番号→名は `1=C / 2=A` で現基板と一致し、BOM の value `LED_Y`（黄）とも色が揃う。輝度も 90–180mcd@20mA と `C72044` の 11.5–28.5mcd@5mA より高く、ステータス表示としては見やすい。唯一の引っかかりはパッケージ名が `LED0603-RD-YELLOW` と別名である点で、0603 ランド自体は同等と見られるが名称一致の条件を厳密には満たさないため第 2 候補とした。採用する場合はカート投入時に JLC のプレビューで外形と向きを確認すること。

**`C2286`（前回の推奨）は撤回する。** EasyEDA シンボルのピン生データを読むと `0~1~-5~0~**A**~end~~~#800^^0~9~-9~0~**1**~start` と `0~**K**~start~~~#800^^0~-9~-9~0~**2**~end` で、**A=pin1 / K=pin2**。現基板は pad1 がカソードなので、そのまま置換すると LED が逆実装になる。Basic かつ在庫潤沢という利点はあるが、極性が合わないので採用しない。

## 2. C1017（GZ2012D601TF）のフットプリント整合

- 基板側: `ProPrj_The-easyedapro:L0805（FB1-FB5 の 5 点すべて）`
- パッド実測: pad1/pad2 とも 1.1325 x 1.377mm、x=-0.966 / +0.966mm。内側ギャップ 0.8mm / 外形スパン 3.065mm / パッド幅 1.377mm
- 部品側: C1017 の EasyEDA パッケージ名は `L0805`（JLC partdetail の表記は `0805`）
- **判定: OK**
- 理由: フットプリント名が `L0805` で完全一致。MPN の 'GZ2012' は 2012 メートル法 = 0805 インチで、パッド幅 1.377mm > 本体幅 1.25mm、スパン 3.065mm > 本体長 2.0mm とランドが本体を包含する。2 端子無極性なので向きの検討は不要。

`grep -o 'footprint "[^"]*"'` の結果でも `ProPrj_The-easyedapro:L0805` はちょうど 5 個で、FB1–FB5 の 5 点と一致する。他の 0805 系（`C0805` 8 個・`R0805` 6 個）とは別フットプリントとして分かれており、取り違えは起きていない。

---

# 追記 2（2026-08-28、追加調査その 2）

## 3. BIAS 帰還用 1.5nF 0402（ECO-5）

### 現基板の該当箇所

- `R_BIAS_FB`: 1MΩ 0805 (C17514) が BIAS_INV <-> BIAS_OUT_INT を橋渡し
- `C_BIAS_INV`: 現在 100nF (C1525) が BIAS_INV -> GND、フットプリント C0402
- `ADS1299_pinName`: pin61=BIASINV / pin63=BIASOUT（contract TSV の pinName で確認）
- ECO-5 でこの `C_BIAS_INV` の pad2 を `GND` から `BIAS_OUT_INT` に移し 1.5nF にすると、TI 推奨の 1MΩ ∥ 1.5nF になる。極は 1/(2*pi*1M*1.5n) = 約 106Hz（TI 推奨値）。

### 候補

| | C番号 | MPN / メーカー | EasyEDA パッケージ | スペック | JLC 区分 | 在庫(LCSC / SZLCSC) |
|---|---|---|---|---|---|---|
| **第1候補** | `C23967` | CL05B152KB5NNNC / Samsung | `C0402` **一致** | 1.5nF **50V X7R ±10%** | Extended | 60,236 / 21,600 |
| **第2候補** | `C284989` | 0402B152K500NT / FH(風華) | `C0402` **一致** | 1.5nF 50V ±10%(K) | Extended | 19,300 / 95,000 |
| 不採用 | `C281752` | CC0402JRX7R9BB152 / YAGEO | `C0402` | 1.5nF X7R | Extended | **0 / 0** |
| 参考(C0G) | `C52037853` | CGA0402C0G152J500GT / HRE | `0402` | 1.5nF 50V **C0G** ±5% | 取得不能 | 2,250 / — |

### 判定理由

**Basic は選べない。** JLC Basic に 1.5nF 0402 は存在しない。検索した 1.5nF 0402 は Samsung/FH/YAGEO/Walsin/KEMET/AVX/Vishay/Meritek いずれも Extended。1nF に落とす案（C14442）も Extended なので手数料回避にならない。 したがって値を妥協する理由がなく、TI 推奨の 1.5nF をそのまま使うのが合理的。

**第 1 候補は `C23967`（Samsung CL05B152KB5NNNC）。** JLC partdetail が 「1.5nF 50V X7R ±10% 0402」と明示しており誘電体まで確定できる唯一の候補で、EasyEDA パッケージ名 `C0402` は現フットプリント `ProPrj_The-easyedapro:C0402` と完全一致する。在庫も 60,236 / 21,600 と十分。

**第 2 候補は `C284989`（FH 0402B152K500NT）。** パッケージ名 `C0402` 一致、SZLCSC 在庫 95,000 と潤沢で、FH は既に `C1546` で BOM に入っているメーカー。ただし誘電体の明記が取得できなかった（型番の 'B' は FH の X7R 系だが未裏取り）ので第 2 候補とした。なお EasyEDA API が返す「Voltage Rated 500V」は型番 '...500NT' の誤パースで、同じ表記体系の `C1546`（0402CG101J500NT）が 50V と確認済みなので 50V と判断している。

**材質について。** C0G が理想ではあるが、X7R でも実害は小さいと判断した。この C は 1MΩ と並列で BIASINV(加算節点) と BIASOUT の間に入り両端の DC 電位差がほぼ 0V なので、X7R の弱点である DC バイアス容量減衰が効かない。残る誘電吸収・圧電は 106Hz の極を作るだけの用途では二次的。 C0G をどうしても優先するなら `C52037853` だが、在庫 2,250・メーカー実績不明・個別ページ未取得（検索 API 一覧の値のみ）というリスクを取ることになる。

## 4. `C52923`（ESP32 EN の RC 用、B2）の判定: OK

- 現基板: C_EN_DLY = 100nF (C1525) が ESP_EN -> GND / R_EN_UP = 10kΩ (C25804) が VDD_ESP -> ESP_EN
- 実体: C52923 = CL05A105KA5NQNC / Samsung / C0402 / 1uF 25V X5R +-10% / JLC Basic
- 在庫: LCSC 3,790,400 / SZLCSC 3,663,900、jlcOnSale=1（LCSC 商品ページと EasyEDA API の 2 ソースが一致）
- **判定: OK**

定格 25V は要求の 6.3V 以上を約 4 倍上回る。EN ノードは 3.3V なので DC バイアスによる容量減衰も小さく、10kΩ との時定数は WROOM-32E 推奨の 10kΩ/1µF の意図どおりに出る。フットプリントは現行 C1525 と同じ C0402 で 品番差し替えのみ・銅箔変更なし。

**さらに、部品種類が増えないという利点がある。** C52923 は既に BOM の 10 箇所（C_3V3_IN / C_3V3_M / C_AVDD1_1u / C_LM_IN / C_NLDO_IN / C_PLDO_IN / C_PLDO_OUT / C_VCAP2 / C_VCAP3 / C_VCAP4）で使用中。C_EN_DLY を C52923 にしても品番数が増えず、Basic のままリールも増えない。

- 出典: https://www.lcsc.com/product-detail/C52923.html , https://easyeda.com/api/products/C52923/components

## 追加調査で参照した URL

- `C72044`: https://www.lcsc.com/product-detail/C72044.html , https://jlcpcb.com/partdetail/EverlightElec-19_217_R6C_AL1M2VY3T/C72044 , https://easyeda.com/api/products/C72044/components
- `C72038`: https://jlcpcb.com/partdetail/C72038 , https://easyeda.com/api/products/C72038/components
- `C2286`: https://jlcpcb.com/partdetail/Hubei_KentoElec-KT0603R/C2286 , https://easyeda.com/api/products/C2286/components
- `C183844`: https://easyeda.com/api/products/C183844/components
- `C1017`: https://jlcpcb.com/partdetail/Sunlord-GZ2012D601TF/C1017 , https://easyeda.com/api/products/C1017/components
- `C23967`: https://jlcpcb.com/partdetail/C23967 , https://easyeda.com/api/products/C23967/components
- `C284989`: https://easyeda.com/api/products/C284989/components
- `C281752`: https://easyeda.com/api/products/C281752/components
- `C52037853`: https://easyeda.com/api/eda/product/search?keyword=1.5nF%200402%20C0G&needAggs=false&currPage=1&pageSize=20  (検索一覧)
- `C14442`: https://easyeda.com/api/products/C14442/components
- `C52923`: https://www.lcsc.com/product-detail/C52923.html , https://easyeda.com/api/products/C52923/components

# カート投入時の差替 2026-08-28

JLC のカートに入れた時点で 2 品番が**実装在庫 0（20 shortfall）**となり、その場で差し替えた。正本は
`data/bom_fixes_2026-08-28.json`。**どちらもフットプリント・銅箔・CPL は不変**で、変わったのは
`data/parts_lcsc.csv` と基板の Value/MPN/LCSC フィールド、`fab/BOM_JLCPCB.csv` の当該 2 行だけ。

| designator | 旧 | 新 | 根拠 |
|---|---|---|---|
| `D_LED` | `C72044`（Everlight 赤 Vf1.95V） | **`C84268`** NationStar NCD0603Y1 / 黄 595nm / Vf≈2.0V | EasyEDA パッケージ名が `LED0603-RD` で現フットプリントと完全一致、生データ pin1=K / pin2=A で現基板 pad1=GND（カソード）と一致するため**回転補正なし（CPL 0° のまま）**。(3.3−2.0)/330 ≈ 3.9mA。JLC Extended / 実装在庫 605,820 / Economic 対応。BOM value 'LED_Y'（黄）とも整合。不採用: `C2286`（Basic・在庫最大だが pin1=A で極性反転、CPL 180° 補正が要る）、`C84263`（赤・pin1=K だが Standard 専用） |
| `F1` | `C369159`（JK-NSMD050-13.2V） | **`C43379`** RUILON SMD1206P050TF/13.2 | 1206・hold 500mA / trip 1A / **13.2V** で旧品と定格が同一＝設計変更なし。本体 3.6×1.9mm は現 `F1206` ランド（パッド 1.19×1.728 @ ±1.445mm）に対し長手は余裕、幅は片側 0.086mm はみ出し（PPTC では許容）。**CPL 90° のまま**。JLC Extended / 実装在庫 19,984。6V 品 `C69688` / `C883122` より 13.2V の余裕を優先 |

Extended 品番数は増減なし（`C72044`→`C84268`、`C369159`→`C43379` とも Extended）。
再生成後の照合: Gerber・ドリル 14 ファイルは生成時刻行を除いて**全ファイル一致**、`fab/CPL_JLCPCB.csv` は**完全一致**、
`fab/BOM_JLCPCB.csv` は 30 行中この 2 行のみ差分。S7a 16/16・S8 30/30・ACCEPTANCE A–G 40/40 いずれも pass。

> この節は手書き。`scripts/40_gen_bom_report.py` はこのファイルの生成元だが、ECO-5 で
> `C23967` 等が `data/parts_lcsc.csv` に入って以降 `JUDGE` に定義が無く `KeyError` で止まるため、
> 本レポートは 2026-08-28 時点の凍結スナップショットとして手で追記している（本件以前からの既存事象）。

# 追記 2026-08-28（3）— `U_MCU` を ESP32-WROOM-32E → **32UE** に差し替えた

カート投入後の配置レビューで、**32E の本体（25.5 × 18 mm）が ADS1299 の上に乗っている**ことが
判明した。ACCEPTANCE に基準 **H（部品本体の重なり）** が追加され、`scripts/64_body_overlap.py` が
F.Fab 外形どうしで測った結果は次の 4 件（負値＝食い込み）:

| 組 | 隙間 [mm] |
|---|---|
| `C_AVDD1_10n` × `U_MCU` | −3.1384 |
| `U_ADS` × `U_MCU` | −2.8124 |
| `C_DVDD_P40` × `U_MCU` | −1.6484 |
| `C_AVDD1_100n` × `U_MCU` | −0.8524 |

25.5 mm のうち **6.3 mm は PCB アンテナとその keep-out** で、しかもその端が ADS1299 側（−X）を
向いている。**`ESP32-WROOM-32UE-N4`（`C701344`）はこの 6.3 mm が無いだけの同一製品**で、
Espressif のデータシートが「The pin layout of ESP32-WROOM-32UE is the same as that of
ESP32-WROOM-32E, except that ESP32-WROOM-32UE has no keepout zone」と明記している。

## 何を変えたか — **銅箔は 1 mil も動いていない**

`scripts/37_umcu_32ue.py`（S5_L8）。フットプリントの**図形と文字だけ**を書き換える:

| レイヤ | 変更 |
|---|---|
| F.Fab | 25.5 × 18 の外形 4 本を **19.2 × 18**（ローカル x −9.945…+9.255 / y ±9.000）に引き直し。1 番ピン印の塗り polygon は新しい角へ +6.5825 mm 平行移動 |
| F.SilkS | 10 本（アンテナ keep-out 線 x −10.1925 を含む）→ **7 本**。線幅 0.254 mm も、パッド列を跨ぐ手前で 0.206 mm 空ける流儀も既存の 32E 外形と同じ（座標は**パッドから導出**しているので、偶然ではなく一致する） |
| F.CrtYd | 本体 + 0.25 mm の矩形 |
| フィールド | Value / MPN = `ESP32-WROOM-32UE-N4`、LCSC = **`C701344`** |

**パッド 47 枚（38 + サーマル 9）・ネット・トラック・ビア・ゾーンは 1 つも触っていない。**
`P.counts` は前後で `{footprints 141, tracks 1248, vias 241, npth 6, pth 16}` で不変、
契約パリティ 0、DRC error 0 / unconnected 0 / 新規署名 0。

## 差し替え後の実測

| 相手 | 本体間 [mm] | 本体→相手パッド [mm] |
|---|---|---|
| `U_ADS` | −2.8124 → **+3.7701** | −4.2369 → **+2.3456** |
| `C_AVDD1_10n` | −3.1384 → **+3.4441** | −3.2829 → **+3.2996** |
| `C_DVDD_P40` | −1.6484 → **+4.9341** | −1.6129 → **+4.9696** |
| `C_AVDD1_100n` | −0.8524 → **+5.7301** | −0.9969 → **+5.5856** |
| `R_IO2_DN` / `R_IO15_DN` | 0.5606 → **0.2781** | 0.2592 → **0.0022**（F.Fab 外形中心線まで） |

ACCEPTANCE H は **pass**（残る重なり 3 件はすべて許容リスト: `AMS1117`×`H4` と
`J1`×`PEG1`/`PEG2`＝J1 自身の NPTH ペグ穴）。

## 東側 2 点（`R_IO2_DN` / `R_IO15_DN`）を動かさなかった理由

本体東端が x = 174.213、この 2 点の pad 1 の西端が x = 174.2152 で **0.0022 mm** しかない。
+0.30 mm 東へ逃がす案を `scripts/38_nudge_io_pulldowns.py`（S5_L9）で実測したが**不可**:

- `ESP_RXD` が **x = 175.2195 の F.Cu を y 91.2775→103.165 まで縦断**しており（幅 0.1525 mm）、
  pad 1 の東端 175.0217 との隙間は **0.1216 mm**。0.30 mm 動かすと pad 1 がこのトラックに乗り、
  `ESP_IO2` / `ESP_IO15` が `ESP_RXD` と短絡する
- clearance 0.0889 mm を守れる最大の東移動は **0.030 mm**（必要量 0.198 mm に対して）

**そして 0.0022 mm という数字が隠している事実のほうが重要**: `R_IO2_DN` の pad 1 は
`U_MCU` の pad 24（castellation）と **0.7953 mm 重なって同じランドを共有**しており、
両者は同一ネット `ESP_IO2` である（`R_IO15_DN` pad 1 と pad 23 / `ESP_IO15` も同じ）。
モジュール本体の下に**別部品の独立したはんだ接合は存在しない**。モジュール自身の
castellation も本体端から 0.7975 mm 外へ出ている（そういう部品である）。

なお本体位置 x −9.945…+9.255 は、19.2 mm を置ける 2 通りのうち**東寄り＝悲観側**の解釈である
（32E の外形から keep-out 6.3 mm を引くと −10.2275…+8.9725 になり、この 2 点は 0.2847 mm 空く）。
西側は U_ADS まで 3.4 mm 以上あるのでどちらでも変わらない。

## CPL の回転だけ 0° → **90°**

`C701344` の JLC / EasyEDA フットプリントは**モジュール長辺が Y 軸方向**に描かれており、
repo のフットプリントに対して +90° CCW（38 パッド全部が +90° で一致、原点はどちらも
パッド外接矩形の中心）。したがって **Mid X / Mid Y は不変、Rotation だけ 90**。
基板側は 0° のまま正しいので、`data/cpl_overrides.json` に理由付きで置き、
`scripts/61_make_bom_cpl.py` が pos 出力後に当該行だけ書き換え、`gates/S8.json` に記録する。

## アンテナについて

**32UE にオンボードアンテナは無い**（代わりに U.FL コネクタ。本基板では未接続で使わない）。
Rev.A の通信は USB-UART のみで WiFi/BLE を初期化しないため機能上の欠落はない
（Espressif: RF スタック未初期化なら RF ピンはオープンで可）。
**Rev.B で無線を使うなら外部アンテナが必要**になる。
併せて、旧レポート §7 にあった「アンテナが基板内側を向いている（Rev.A 受容）」は
**部品変更により消滅した**（改善したのではなく、アンテナ自体が無くなった）。

## 再出力した製造データの差分（生成時刻行を除く）

| ファイル | 差分 | 由来 |
|---|---|---|
| `F_Cu` / `B_Cu` / `In1_Cu` / `In2_Cu` / `F_Mask` / `F_Paste` / `PTH.drl` | 変化 | **L7（`R_CC1` の移設）のみ**。変化した座標は全て x 172〜179 / y −116〜−106 の R_CC1 窓の中（内層は追加 via 2 本ぶんのアンチパッド。ベタ面積 GND In1 −1.03 mm² / USB_5V In2 −1.03 mm² ＝ 半径 0.394 mm の穴 2 個ぶん） |
| `F_Silkscreen` | 変化 | R_CC1 の移動（112 点）＋ **U_MCU の外形（30 点）**。それ以外の座標はゼロ |
| `Edge_Cuts` / `B_Mask` / `B_Paste` / `B_Silkscreen` / `NPTH.drl` / `.gbrjob` | **完全一致** | |
| `BOM_JLCPCB.csv` | 30 行中 **1 行**（`U_MCU`: `C701341` → `C701344`、Value / MPN も 32UE へ） | Footprint 欄 `WIFI-SMD_ESP32-WROOM-32E` は 32E/32UE 共通のランドパターン名なので据え置き |
| `CPL_JLCPCB.csv` | 133 行中 **2 行**（`R_CC1` 位置・回転／`U_MCU` 回転 90°） | 他 131 行は完全一致 |

ゲート: DRC error 0 / unconnected 0、契約パリティ 0、アナログ 40 ネット差分 0（`--baseline 2b18a8c`）、
S5_L8 16/16・S5_L9 9/9・S7_body 3/3・ACCEPTANCE A–G 40/40・S8 31/31。

> 既知の未修正（軽微）: `scripts/47_layout_quality.py` の J11「ESP32 antenna clear of the board」は
> 32E 前提の文言（`ok: null` の情報項目）で、32UE ではアンテナ自体が無い。指標は判定に使われて
> いないため、この作業では文言を変更していない。
