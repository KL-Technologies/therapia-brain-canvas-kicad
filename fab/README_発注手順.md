# JLCPCB 発注手順 — Brain Canvas Rev.A（Therapia EEG/HRV）

作成: 2026-08-28 / S8（KiCad 移行パイプライン）
基板: 4 層・**61.8236 × 45.0088 mm**・1.6 mm
`ACCEPTANCE.md` の A〜G を全て満たした状態（`gates/S7.json` に 32 項目の実測）。

> **この文書は「発注してよい」とは言っていない。**
> パイプラインが保証するのは「回路図（＝契約）と基板が一致し、製造データが
> 設計ルールと寸法を満たすこと」だけ。回路の正しさ・部品の実在・在庫は
> **カート投入時に人が確認する**。下の「投入前に必ず見る 4 点」がその作業。

---

## 1. アップロードするファイル

| 用途 | ファイル | 中身 |
|---|---|---|
| PCB | `fab/Therapia_EEG-HRV_Rev.A.zip` | Gerber 11 ＋ `.gbrjob` ＋ ドリル 2 ＝ **14 ファイル** |
| 実装 BOM | `fab/BOM_JLCPCB.csv` | **30 行 / 133 点**（全行に LCSC 番号あり） |
| 実装座標 | `fab/CPL_JLCPCB.csv` | **133 行**（全て Top 面） |

補助資料（アップロード不要・人が見る用）:

| ファイル | 用途 |
|---|---|
| `fab/preview_top.png` / `preview_bottom.png` | 3D レンダ。JLC の Confirm Parts Placement と見比べる |
| `fab/assembly_top.pdf` | **部品番号入りの実装図。DNP 2 点に × が入っている** |
| `fab/gerber/*-drl_map.pdf` | ドリル位置図（PTH / NPTH） |

`fab/gerber/` には zip に入れた 14 ファイルがそのまま置いてある。
zip をやり直す場合は `scripts/60_export_fab.sh` を**サンドボックス外**で実行する。

---

## 2. PCB の設定

| 項目 | 値 | 理由 |
|---|---|---|
| Base Material | FR-4 | |
| Layers | **4** | |
| Dimensions | 61.8 × 45.0 mm（自動認識されるはず） | Gerber の外形を独立パーサで実測して 61.8236 × 45.0088 mm |
| PCB Qty | **5** | |
| Product Type | Industrial/Consumer electronics | |
| PCB Thickness | **1.6 mm** | |
| Impedance Control | **なし** | USB は Full Speed。長さ差 9.67 mm ≪ 許容 45 mm で蛇行不要 |
| Layer Stack-up | JLC04161H-7628（標準） | |
| PCB Color | 任意（緑が最速） | |
| Silkscreen | 白 | |
| Surface Finish | **HASL（無鉛）** または ENIG | ENIG のほうが 0.5 mm ピッチ TQFP-64 には有利 |
| Outer Copper Weight | 1 oz | |
| Inner Copper Weight | **0.5 oz** | 標準。内層は GND / 電源ベタのみ |
| Via Covering | **Tented** | |
| Min via hole size/diameter | 0.3mm/(0.4/0.45mm) | 実装済み via は φ0.3048 ドリル / φ0.6096 外径 |
| Board Outline Tolerance | ±0.2mm (Regular) | |
| Remove Order Number | **Specify a location**（推奨） | 指定しないと JLC がシルクの空きに勝手に入れる |

---

## 3. PCBA の設定

| 項目 | 値 | 理由 |
|---|---|---|
| PCBA Type | **Economic PCBA** | **Standard は単板 70×70 mm 以上が必要**。この基板は 61.8×45.0 mm なので Standard を選ぶならパネル化が要る。部品要件は全て Economic の範囲内（最小 0402・最小ピッチ TQFP 0.5 mm） |
| Assembly Side | **Top Side** | 実装部品は 133 点すべて Top。Bottom は部品ゼロ（B.Paste が空なのはそのため） |
| PCBA Qty | **2** | Rev.A 初号機 |
| Tooling holes | Added by JLCPCB | |
| Confirm Parts Placement | **ON（自動確認にしない）** | 下記 4 点を目視するため。**ここを OFF にすると本文書の意味が半分無くなる** |

> **Economic PCBA はスルーホール部品を実装しない。**
> `J1`（USB-C・PTH シェル脚 4 本）と `J2`（12 ピンヘッダ）は**手はんだ**になる。
> 両方とも BOM と CPL には入れてあるので、JLC 側で «not supported» と出たら
> その 2 点だけ Do Not Place にして基板だけ受け取り、手で付ける。
> **その 2 点のはんだ面（表・裏とも）のレジストは開いている**（後述 §6）。

---

## 4. 投入前に必ず見る 4 点

### (1) 在庫を確認する 3 品番

`data/bom_fixes_2026-08-28.json` の `stock_watch_at_cart`。ソース間で在庫表示が食い違っていたもの。

| LCSC | 部品 | 状況 | 欠品時 |
|---|---|---|---|
| `C69932` | TPS72325（負電圧 LDO） | LCSC 7,086 / API 0（深圳 3,843） | **代替が少ない。欠品すると基板が動かない**。ピン互換の TPS723xx を要調査 |
| `C701341` | ESP32-WROOM-32E-N4 | 表示がソース間で乖離 | 実装在庫を確認 |
| `C19619` | TLV70025（+2.5V LDO） | 1,480〜2,186 とやや薄い | 10 台分なら足りる |
| `C369159` | F1（PTC 500mA） | LCSC ページが "Not available now" | 同一フットプリント `F1206` の **`C883122`** に差し替え（6V 定格に低下） |

### (2) Extended 部品は 13 品番 / 20 個 → 手数料対象

`C237168`(C_DIF1–8) `C7519`(D_ESD) `C23967`(C_BIAS_INV) `C369159`(F1)
`C2765186`(J1) `C2840012`(J2) `C108573`(LM2664) `C19619`(TLV70025)
`C69932`(TPS72325) `C476817`(U_ADS) `C701341`(U_MCU) `C72044`(D_LED) `C84681`(U_USB)

`C476817`（ADS1299）は単価 $60 台。数量より価格の影響が大きい。

### (3) DNP 2 点 — **BOM にも CPL にも入っていない**

| 部品 | 値 | 実装しない理由 |
|---|---|---|
| `R_RST_UP` | 10 kΩ | GPIO12(MTDI) を 3.3 V にプルアップしてしまい、ESP32-WROOM-32E の**起動ストラップに違反**（IO12 は電源投入時 Low 必須、eFuse 未焼成）。個体によって flash read err で起動しない。DNP にすると `C_RST_DLY` と内部 45 kΩ プルダウンで MTDI=0 が確定する。ADS1299 の RESET# はファームが push-pull で駆動するのでプルアップは要らない |
| `R_IO15_DN` | 10 kΩ | GPIO15 Low は ROM のブートログを止める。**Rev.A の火入れではそのログを見たい**。GPIO15 は内部プルアップで High＝通常起動。量産 Rev.B で戻すかは火入れ後に判断 |

**基板上にはフットプリントもネットも銅も残してある。** 後から手で付けられる。
`fab/assembly_top.pdf` ではこの 2 点に × が入っている。

### (4) Confirm Parts Placement で見る向き

`fab/preview_top.png` と `fab/assembly_top.pdf` を横に置いて、次を確認する。

| 部品 | 見るところ |
|---|---|
| `U_ADS`（ADS1299 TQFP-64） | 1 番ピンの白丸が**左上**。0.5 mm ピッチなので回転 90° 違いは致命的 |
| `D_LED` | **pad1 = カソード（GND 側）**。`C72044` は pin1=C / pin2=A で現フットプリントと一致することを確認済み（`reports/bom_verification.md`）。JLC のプレビューで極性マークが逆に見えたら止める |
| `D_ESD`（USBLC6-2SC6） | SOT-23-6 の 1 番ピン向き |
| `U_MCU`（ESP32-WROOM-32E） | アンテナが基板の**内側**を向いている（後述 §7 の既知事項） |
| `J1` / `J2` | Economic では実装されない見込み。«not supported» なら Do Not Place |

---

## 5. 発注しない条件

次のどれかに当てはまったら**投入を止めて設計に戻す**。

- JLC の Gerber ビューアで外形が 61.8 × 45.0 mm 以外に見える
- DRC/DFM で **clearance / hole / short 系のエラー**が出る（シルク系の警告は既知・許容）
- Confirm Parts Placement で `U_ADS` の 1 番ピンが左上でない
- `D_LED` の極性が逆に見える
- `C69932`（TPS72325）が欠品で代替が決まっていない

---

## 6. この発注で直した、見えにくい 2 件

発注前チェックで見つけて直したもの。**同じ Gerber を EasyEDA から出し直すと再発する可能性がある**ので記録しておく。

### スルーホール部品のレジストが両面とも開いていなかった

EasyEDA → KiCad の取り込みで、**PTH / NPTH パッド 22 個すべてが「銅箔層だけ」のレイヤ構成**になっていた（F.Mask も B.Mask も持っていない）。そのまま出すと:

- `J2` の 12 ピン全部と `J1` のシェル脚 4 本が**表裏ともレジストで覆われ、はんだ付けできない**
- DRC は何も言わない（「開口を要求していないパッド」は違反ではない）

`scripts/43_fix_pth_mask.py` で 22 パッドに F.Mask / B.Mask を追加。
銅箔は一切変えていない。**独立パーサで再確認済み**: F.Mask 403→425 開口、B.Mask 0→22 開口、
J2 の 12 ピンすべてが両面で開いていること、`fab/preview_bottom.png` でも金色に見えること。

見つけ方は「Gerber を KiCad に読み直させず、自前パーサ（`scripts/lib/gerber_parse.py`）で読む」だった。
**KiCad に自分の出力を読ませても、自分と矛盾していないことしか分からない。**

### 基板外形の Gerber が `Multi-Layer.gm1` という名前で出ていた

取り込みが EasyEDA のレイヤ名を引き継いでいたため。拡張子 `.gm1` と X2 属性
（`TF.FileFunction,Profile`）は正しいので機械は間違えないが、
**EasyEDA の "Multi-Layer" は「全層」の意味**で、外形＝ルータの切断線を決めるファイルに
その名前が付いているのは人が読み違える。`scripts/49_normalize_layer_names.py` で
KiCad の正規名に戻した（表示名だけの変更・銅箔は不変）。

---

## 7. Rev.A として受容した既知事項

すべて `data/bom_fixes_2026-08-28.json` と `reports/layout_review.md` に根拠がある。

| # | 内容 | 判断 |
|---|---|---|
| M1 | **AMS1117 の本体が取付穴 H4 の真上**（L1 修理で +3.25/−1.25 mm 移設。±8 mm 探索で本体が穴に掛からない位置は無かった） | **筐体側で対応**: 上面にネジ頭・ナットを置かない。H1〜H3 の 3 点止めにするか、H4 は下面からの位置決めピンのみ |
| M2 | `J1` の pin1/pin12 の GND ランドを 1.10 → 1.00 mm に詰めた | 機械保持は PTH シェル脚が担う。穴-銅 0.2 mm ルールを優先 |
| A-6 | **AVDD1(54) / AVSS1(53) がスター接続になっていない**。回路図が `AVDD` / `AVSS` に直結しており別ネットですらないので、**PCB では直せない** | Rev.A 受容。火入れで AVDD のリップルを実測し Rev.B の判断材料にする |
| J1 | `C_VCAP1`(100 µF) が ADS1299 pin28 から 9.89 mm・銅箔 12.16 mm・ビア 2 個。`C_VCAP4` も 5.24 mm / ビア 2 個 | より近い合法位置が無い（62 箇所探索）。TI は距離の数値基準を示していない |
| J4 | `C_VCAP1` が **X5R**（`CL31A107MQHNNNE`）。TI DS §11 は振動環境で VCAP1 に C0G/NP0 かタンタルを推奨 | Rev.A 受容。装着型なので Rev.B で要検討 |
| — | `CHASSIS_GND` が GND に対してフローティング。`J2` pin12(SHLD) は Rev.A では電極ケーブルに繋がない運用 | |
| — | `U_MCU` のアンテナが基板内側（右端から 6.34 mm 内側）。WiFi 感度が落ちる | Rev.A 受容 |
| — | In2 の `VDD_ESP` ベタ 3 枚のうち 1 枚が充填後ほぼ面積ゼロ（< 0.005 mm²）。残り 2 枚が配電している | 実害なし |

---

## 8. 基板が届いたあと

火入れの順序と合格値は **`reports/bringup_checklist.md`**。
ファームウェア側で必ず守ることは `data/bom_fixes_2026-08-28.json` の
`firmware_and_bringup_musts`。とくに:

- **MISC1 レジスタは 0x00**（Cerelog 既定の 0x20 は不可。SRB1 が内部で全 ch の N 側に繋がり、ch4 の ECGN が SRB1 に短絡して ECG が壊れる）
- **ADS1299 のリセットは 電源投入 → tPOR 128 ms 以上 → RESET# パルス**。
  Cerelog の firmware は PWDN#/RESET# 同時 High だけで非適合
- **ADS1299 の GPIO レジスタ(0x14) を出力に設定しない**（GPIO1–4 は GND 直結）
- `R_RST_UP` を実装してしまった基板の救済: `espefuse.py set-flash-voltage 3.3V`

---

## 9. 再生成の仕方

```sh
# すべてサンドボックス外で
./scripts/60_export_fab.sh                 # Gerber / ドリル / プレビュー / 実装図 / zip
KPY scripts/61_make_bom_cpl.py             # BOM / CPL
python3 scripts/62_check_fab.py            # 独立パーサで製造データを検査
KPY scripts/50_final_check.py              # ACCEPTANCE A〜G（gates/S7.json）
```
