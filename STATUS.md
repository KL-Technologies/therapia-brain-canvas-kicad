# STATUS — brain_canvas_kicad

最終更新: 2026-08-28 / 担当: S0–S2

## 現在地

**S0 / S1 / S1B / S2 / S2B すべて pass。KiCad 側の基板 `board/Therapia_EEG-HRV.kicad_pcb` は
EasyEDA の内容と完全一致（17/17 チェック）。S3 に引き渡せる状態。**

| ステップ | 結果 | 内容 |
|---|---|---|
| S0 | **pass** 11/11 | kicad-cli 10.0.5 / KiCad python 3.9.13 / `pcbnew` / `EASYEDAPRO` / `ZONE_FILLER` / `drc --refill-zones` 全て有り |
| S1 | **pass** 4/4 | `ProPrj_Therapia_EEG-HRV_2026-08-28_v2.epro`（227,363 B, sha256 `83c096a6c23aa482…`）を `import/` へ確保 |
| S1B | **pass** 6/6 | `.epro2` も同時に確保されていたため変換も実施（`*.converted.epro`）。ただし**正規の旧 `.epro` があるのでそちらを採用**。変換物は使っていない |
| S2 | **pass** 17/17 | 取り込み・パッド網補修・突合すべて一致 |
| S2B | **pass** 5/5 | 回路図ネットリスト（EasyEDA API 由来）を契約として取り込み、PCB との差分＝ECO-1 の残作業を列挙。スクリプトは `scripts/20_netlist_contract.py`（`13_*` は `13_fix_import.py` 用に空けてある） |

`./run.sh --status` でいつでも同じ表が出る。

### S2 の実測（EasyEDA ↔ KiCad 完全一致）

| 項目 | 値 |
|---|---|
| 部品 | 131（designator 集合も一致。重複なし） |
| フットプリント総数 | 135 = 131 ＋ M2 取付パッド 4（EasyEDA の基板直置きパッドは designator を持たないので KiCad が無名フットプリントに包む） |
| パッド | 429（うちネット有り 385 / 無ネット 44 ＝ 部品内 40 ＋ M2 4） |
| ネット | 77（員数も全ネット一致。**#19021 のネット融合なし**） |
| トラック | 1191（層別一致。ARC は 0） |
| ビア | 238 |
| ベタ（POUR） | 10（In1=GND / In2 に AVDD・USB_5V×2・VDD_ESP×3・AVSS ほか） |
| 銅箔層数 | 4 |
| 外形 | 61.8235 × 45.0090 mm（規定 61.8236 × 45.0088、Edge.Cuts 中心線基準） |
| 回転 | {0:79, 90:40, 180:4, 270:8} ⊆ {0,90,180,270}、CPL と全一致 |
| 穴 | 22/22 一致（M2 φ2.3876 ×4、J2 φ1.05 ×12、J1 スロット ×4、USB-C ペグ φ0.700 ×2） |
| 原点移動 | KiCad が (120, 80) mm 平行移動 |

`fab_2026-08-16` の CPL（131 部品）と位置・回転・パッド1座標が**全件一致**したので、
この export は 2026-08-16 の製造パッケージと同じ幾何。

## 次にやること（S3 への申し送り）

1. **ECO-1 は PCB に入っていない。** 残作業は `gates/netlist_diff.json` に全量が出ている
   （部品 4 個の追加 ＋ ピン 8 本のネット変更）。S3 は L1〜L6 に加えてこれも実施する
2. **設計ルールを移すこと。** `contract/easyeda_rules.json` に EasyEDA の値を出してある。
   `board/Therapia_EEG-HRV.kicad_pro` は最小構成のダミーで、ネットクラスも custom rule も未設定。
   **今の DRC 件数（1025）は KiCad 既定ルールに対する数字で、EasyEDA の DRC とは比較できない**
3. **座標の読み替え**: EasyEDA メモの `(x, y)` [mm] → KiCad `(x+120, −y+80)` [mm]
4. **`lib_footprint_issues` 131 件**はライブラリ未リンクによるもので実害なし。気になるなら
   フットプリントをプロジェクトライブラリに書き出して紐付ける
5. **ECO L4 の前提を取り直すこと。** 下記「ブリーフとの差分」参照

## 設計上の発見（取り込みの不具合ではない）

`gates/design_observations.json` に機械可読な形で置いてある。

### ECO-1 は PCB に未適用（確定）— 残作業の全量

回路図（ECO-1 適用済み）と PCB（未適用）の差分を機械的に取った結果が
`gates/netlist_diff.json`。**これが S3 の作業指示そのもの**。

**追加すべき部品 4 個**: `C_VCAP1_H` / `C_VCAP2` / `C_VCAP3` / `C_VCAP3_H`
（いずれも 2 ピン、片側 `AVSS`）。新規ネット `VCAP2` / `VCAP3` も PCB 側に存在しない。

**ネットを変更すべきピン 8 本**:

| designator | pin | pin name | 回路図（正） | 現 PCB |
|---|---|---|---|---|
| TPS72325 | 3 | EN | `V_NLDO_IN` | **`GND`** ← 致命バグ B1 が残存 |
| U_ADS | 31 | RESV1 | `GND` | `AVDD` |
| U_ADS | 42 | GPIO1 | `GND` | 未結線 |
| U_ADS | 44 | GPIO2 | `GND` | 未結線 |
| U_ADS | 45 | GPIO3 | `GND` | 未結線 |
| U_ADS | 46 | GPIO4 | `GND` | 未結線 |
| U_ADS | 30 | VCAP2 | `VCAP2` | 未結線 |
| U_ADS | 55 | VCAP3 | `VCAP3` | 未結線 |

ECO-1 の表（項目 1〜5）と完全に対応する。`AVDD` のパッド数 21 も
`PROJECT_STATUS.md` の「ECO 前 21・ECO 後 20」と整合。

KiCad 側には回路図が無いので、**S3 はこの 8 本＋4 部品を PCB 上で手作業で再現する**ことになる。

**expected_delta の数え方について**: lead の想定は「20 ピン差＋新設 4 部品 8 パッド」だが、
現 PCB との実差分は **16**（既存ピンのネット変更 8 ＋ 新設 4 部品のパッド 8）。
ECO 文書の「全ピン diff = 意図した 20 件」は**回路図の変更前後**の差分で、
④リネーム（`C_3V3_B`/`C_3V3_H` 系 2 部品 ×2 ピン = 4 件）を含む。
リネームは PCB 側に既に反映済み（`C_3V3_B` と `C_3V3_B2`、`C_3V3_H` と `C_3V3_H2` が
回路図・PCB の双方に別部品として存在し、ネットも一致）。よって PCB に対する残作業は 16 で正しい。

### FB5（lead の質問への回答）

**FB5 pin1 = `VDD_ESP` / pin2 = `DVDD`。AVDD ではない。**

`PROJECT_STATUS.md` の「FB5(3V3→DVDD フェライト)」「FB5 給電は VDD_ESP ミニベタ」という記述と整合する。
ただし同ファイルはレール構成を「±2.5V (AVDD/AVSS) ＋ 2.5V (DVDD 共通) ＋ 3.3V (ESP32)」とも書いており、
その通りなら **3.3V 系の VDD_ESP と 2.5V 系の DVDD をフェライトで直結していることになる**。
これは計測結果であって判断ではない。**S3 は着手前にこの 1 点を設計側で確認すること**（推測ではなく確認事項）。

### 取り込み時の既知欠陥（as-imported の期待どおりの FAIL・`13_fix_import.py` で修正）

機械可読な形は `gates/design_observations.json` の `known_import_defects`。
**いずれもデータの欠損ではない**（EasyEDA 側の 22 穴は 22 穴とも KiCad に入っている）。

| # | 症状 | 実測 | 修正方針 |
|---|---|---|---|
| 1 | **NPTH が 0 個** | 取付穴 6 個すべて幾何としては正しい位置にあるが、NPTH 属性のパッドは 1 つも無い | 下記 2・3 の修正で 6 個にする |
| 2 | M2 取付穴 ×4 が **PTH** | 無名フットプリント `Pad_e525`〜`Pad_e528`、drill = size = 2.3875mm、ネット無し | `SetAttribute(PAD_ATTRIB_NPTH)`・銅なし |
| 3 | USB-C ペグ ×2 が **Edge.Cuts の多角形** | J1 が持つ Edge.Cuts 形状（shape=POLY, 実効径 0.694mm）。位置は (56.861075, −33.877885) / (56.861075, −28.097861) mm ＝ブリーフの期待値と厳密一致 | NPTH パッドを生成し、Edge.Cuts の多角形は削除 |
| 4 | 設計ルールが空 | `.kicad_pro` は最小スタブ | JLC 4 層ルールを書き込む |

**ペグの正体（重要な訂正）**: 私は当初「ペグ穴は存在しない」と報告したが**誤り**だった。
実体は USB-C フットプリント（`109d95f4….efoo`）内の **`FILL` レコードで、layer 12 (Multi) 上の
CIRCLE パス r = 13.78 mil**（id `e36` / `e37`）。REGION でも PAD でもないので、
REGION と PAD の穴だけを見ていた初版の検出器が取りこぼしていた。
J1 の配置 (2290, −1220) mil・回転 90° を掛けると φ0.7000mm の 2 穴がブリーフの座標に
**小数 6 桁まで一致**する。`10_epro_inventory.py` は layer 12 の FILL/POLY/REGION の円を
すべて穴として拾うよう修正済み（EasyEDA 側の穴 20 → 22）。

なお ECO の L4 が言う「Slot Region e54/e55」はこの 2 つの FILL 円のことと**推測**されるが、
id が e36/e37 で一致しないため、S3 は L4 を実形状に対して取り直すこと。
この export に REGION プリミティブは 1 つも無い。

J1 はほかに CHASSIS_GND のメッキ済みスロット穴 4 個を持つ
（(56.3409/60.5410, −35.3130/−26.6630) mm、1.5×0.6 と 1.2×0.6 mm、パッド番号 13/14）。

### 取り込み時 DRC（参考値のみ）

`logs/drc_import.json`: violations **1025**（error 609 / warning 477）、unconnected **0**。
内訳上位は clearance 336 / silk_overlap 199 / lib_footprint_issues 131 / silk_over_copper 115 /
track_width 90 / courtyards_overlap 69。**KiCad 既定ルールに対する数字**なので、
設計ルールを入れるまで意味のある値ではない。

## 途中で直した問題

| 問題 | 対処 |
|---|---|
| EasyEDA Pro 3.2 が書き出す `.epro2` を KiCad が**無言で空基板として**読む | 形式を判定（S1）し、旧 `.epro` へ変換する S1B を追加。今回は正規の旧 `.epro` が用意されたのでそちらを採用 |
| 同一番号パッドの 2 枚目以降にネットが付かない（GND 90→82 / CHASSIS_GND 5→3） | 取り込み後に EasyEDA の表を全パッドへ再適用。10 パッド補修、DRC の unconnected 2→0 |
| `kicad-cli pcb drc` がサンドボックス内で Swift エラー落ち | サンドボックス外で実行。README に明記、スクリプトも検知してヒントを出す |
| 外形が 61.925 × 45.111 と出る | `GetBoardEdgesBoundingBox()` が線幅 4mil を含むため。Edge.Cuts の中心線から算出するよう変更 |
| 層別比較が全件不一致になる | 取り込み後の層名が EasyEDA 表記（"Top Layer"）のまま。`GetStandardLayerName()` で正規名に揃えて比較 |
| `wx.App()` が headless で `SystemExit` を投げ子プロセスごと落ちる | `pcbnew` は wx 無しで動くので生成しない |

## 成果物

```
board/Therapia_EEG-HRV.kicad_pcb   取り込み済み基板（ゾーン充填済み・パッド網補修済み）
board/Therapia_EEG-HRV.kicad_pro   最小プロジェクト。設計ルールは未設定（S3 の作業）
gates/S0.json S1.json S1B.json S2.json
gates/inventory_easyeda.json       EasyEDA 側の員数表（基準）
gates/inventory_kicad.json         KiCad 側の同じ測定
gates/design_observations.json     ECO 状態・FB5・取り込み既知欠陥・DRC 内訳
gates/schematic_solver_accuracy.json  自前の回路図解きを契約 TSV と全数照合した結果
gates/netlist_diff.json            回路図 ↔ PCB の差分＝ECO-1 の残作業（S3 の作業指示）
contract/netlist_contract.json     回路図ネットリスト（ピン名付き・正）
contract/netlist_from_epro_pcb.json        designator→パッド→ネット（PCB の実態）
contract/netlist_from_epro_schematic.json  同（自前の幾何解き・参考）
contract/netlist_from_kicad_pcb.json       取り込み後の KiCad 側
contract/easyeda_rules.json        EasyEDA 設計ルール（未移植・S3 が書き写す）
logs/drc_import.json               取り込み時 DRC
logs/pad_net_repair.json           パッド網補修の記録
logs/import_attempts.json          パッチ段階ごとの試行結果
```

### ネットリストが 2 系統ある。正はどちらか

| ファイル | 由来 | 位置づけ |
|---|---|---|
| `contract/netlist_contract.json` | `contract/netlist_easyeda_api_2026-08-28.tsv`（EasyEDA の `sch_ManufactureData.getNetlistFile()` 出力、135 部品 / 423 ピン、**ピン名付き**） | **正**。回路図の意図。S3 の契約 |
| `contract/netlist_from_epro_pcb.json` | `.epcb` の `PAD_NET` ＋ `.efoo` のパッド | **正**。現在の基板の実態 |
| `contract/netlist_from_epro_schematic.json` | `.esch` の幾何を自前で解いたもの | **参考のみ**。相互確認用 |

TSV は本作業中に外部から `contract/` に置かれたもの（13:00）で、こちらで生成したものではない。
中身は ECO-1 適用後の回路図と完全に整合している（TPS72325 EN=`V_NLDO_IN`、RESV1=`GND`、
GPIO1–4=`GND`、C_VCAP2/3/3_H/1_H 在り）。

自前の幾何解きを契約 TSV と全数照合した結果（`gates/schematic_solver_accuracy.json`）:

- **NC ピン 34 本を 34/34 正しく特定**（過不足ゼロ）
- 解決したピン 375 本のうち **366 本は契約と一致、9 本が不一致**
  — `R_IN1N`〜`R_IN8N` と `R_SRB_SER` の pin1 で `SRB2` と誤答（正は `SRB1`）。
  `SRB2` はネットとして実在しない（PCB にも契約にも EasyEDA の NET 宣言にも無い）。
  SRB1/SRB2 を意図的に束ねてある箇所で、ワイヤ側に残った旧ラベルを拾ったもの
- **7 部品を丸ごと取りこぼし**: `R_EN_UP` `R_IO0_UP` `R_IO15_DN` `R_IO2_DN` `R_LED`
  `R_Q_EN_B` `R_Q_IO0_B`（ESP32 のブート/リセット周り）

つまり実用精度 97.6%・部品欠けあり。**相互確認以外に使わないこと。**
ピン名が要る作業では必ず TSV 由来の `netlist_contract.json` を使う（PCB にはパッド番号しか無い）。

## 再実行の仕方

```sh
./run.sh --status     # 現状確認
./run.sh              # 未完ステップから再開（全 pass 済みなら何もしない）
./run.sh --force      # 全部やり直し
python3 scripts/99_selftest.py   # 合成データでパーサを検証（24 チェック・KiCad 不要）
```

DRC を含むステップだけはサンドボックス外で実行すること。
