# ACCEPTANCE — 「発注可」の定義

凍結: 2026-08-28 / 担当 S3。**以後この文書は変更しない。**
最終ゲート `scripts/50_final_check.py` はこの文書の仕様そのものとして実装される。

この基板は Brain Canvas Rev.A（Therapia EEG/HRV、4層・61.8236 × 45.0088 mm）。
「発注可」＝ 下の A〜G が**全て pass** した状態を指す。1 つでも落ちたら発注しない。

---

## A. DRC

| 条件 | 値 |
|---|---|
| error 級の違反 | **0 件** |
| 未接続（unconnected items） | **0 件** |
| ゾーン | 再フィル済みで保存されていること |

判定は `kicad-cli pcb drc --format json --severity-error --severity-warning`
（**`--refill-zones --save-board` を掛けた後の基板に対して**）。
warning は残ってよいが、下の許容リストに載っている種別だけ。

### warning へ落とす種別（許容リスト・これ以外は error のまま）

| 種別 | 落とす理由 |
|---|---|
| `courtyards_overlap` | EasyEDA 由来のコートヤードは実寸より大きく、既存配置で 69 件出る。実装可否は CPL 実績（2026-08-16 版と同一配置）で担保する |
| `silk_overlap` / `silk_over_copper` / `silk_edge_clearance` | シルクは EasyEDA が自動生成したもの。製造には影響しない |
| `starved_thermal` | ゾーンのサーマルスポーク本数。GND ベタは面で繋がっており実害なし |
| `track_dangling` / `via_dangling` | ベタ止めのスティッチ via を含む。断線には当たらない |
| `isolated_copper` / `copper_sliver` | 再フィル後のベタ島。面積が小さく実害なし |
| `holes_co_located` | 同位置の穴。J1 のスロット穴に出る |
| `footprint_type_mismatch` | 取り込んだフットプリントは `attr` 未設定（smd/through_hole フラグ無し）。実体は正しい |

### ignore にする種別

| 種別 | 理由 |
|---|---|
| `lib_footprint_issues` / `lib_footprint_mismatch` | フットプリントライブラリを紐付けていないため 131 件出る。基板内の実データは EasyEDA と一致済み（S2 17/17） |
| `missing_courtyard` / `pth_inside_courtyard` / `npth_inside_courtyard` | 取付穴とコートヤードの関係は L1 で個別に見る |

**error のまま維持しなければならない種別**（緩めた時点でこの ACCEPTANCE は無効）:
`clearance` `hole_clearance` `hole_to_hole` `hole_near_hole` `copper_edge_clearance`
`shorting_items` `tracks_crossing` `unconnected_items` `track_width` `annular_width`
`drill_out_of_range` `invalid_outline` `items_not_allowed` `padstack`
`solder_mask_bridge` `zone_has_empty_net` `zones_intersect` `malformed_courtyard`
`through_hole_pad_without_hole` `connection_width` `creepage`

## B. ネットリスト＝契約

PCB の**全パッドの designator→pad→net 表**が `contract/netlist_contract.json` と一致すること。

- 部品 **135**（契約に載る designator 集合と完全一致）
- 全ピン一致。契約が NC（net 空）としているピンは PCB 側も無ネット
- 差分 **0**。1 件でもあれば fail
- 取付穴 `H1`〜`H4` は契約外の機械部品として除外される（NPTH・銅なし・BOM/POS 除外が条件）

## C. 設計ルール（JLCPCB 4層）

`board/Therapia_EEG-HRV.kicad_pro` と `board/Therapia_EEG-HRV.kicad_dru` が
`scripts/14_make_rules.py` の生成物と一致すること（冪等なので再生成して差分 0）。

| 項目 | 値 [mm] | 級 |
|---|---|---|
| clearance（最小・ネットクラス／`min_clearance`） | **0.0889**（3.5 mil） | error |
| track 幅（`min_track_width`） | **0.0889** | error |
| hole-to-hole（`min_hole_to_hole`） | **0.2** | error |
| hole clearance 穴→他ネット銅（`min_hole_clearance`） | **0.2** | error |
| 基板端クリアランス（`min_copper_edge_clearance`） | **0.2** | error |
| via ドリル（`min_through_hole_diameter`） | **0.3** | error |
| via アニュラリング（`min_via_annular_width`） | **0.076** | error |
| via 径（`min_via_diameter`） | **0.45** | error |
| pad→mask クリアランス | **0.0508**（2 mil） | — |
| pad→paste クリアランス | **0** | — |
| track-track 間隔（参考・推奨） | **0.127**（5 mil） | **warning** |

既存 via は φ0.3048 ドリル / φ0.6096 外径（アニュラリング 0.1524）なのでそのまま通る。

> **`pad_to_mask_clearance` の値についての明示的な逸脱**
> チームブリーフの指定値は 0.1016 mm（4 mil）だが、**0.0508 mm（2 mil）を採用する**。
> 理由 2 つ。(1) EasyEDA 側の `solderMaskExpansion.padTopExpan` が 2 mil で、
> 2026-08-16 に一度レビューを通った fab パッケージはこの値で出ている。ここを変えると
> 旧 Gerber とソルダーレジストが比較できなくなる。(2) ADS1299 は TQFP-64 0.5 mm ピッチ
> （パッド幅 0.28 mm・隙間 0.22 mm）で、片側 4 mil 拡張するとレジストダムが
> 0.22 − 0.2032 = **0.0168 mm** しか残らない。どの製造業者も保持できない寸法であり、
> DRC は「重なっていない」ので通してしまう＝黙って不良を出す設定になる。
> 2 mil なら 0.118 mm 残る。`solder_mask_min_width` を 0.0508 に設定し、
> 薄いダムが出たら DRC が実際に落ちるようにしてある。

## D. NPTH 6 穴

`kicad-cli pcb export drill --excellon-separate-th` の **NPTH ファイル**に 6 穴あること。
座標は旧 DRL（`cerelog_research/fab_2026-08-16/`）と **±2 µm** 一致。

| 穴 | KiCad 座標 [mm] | φ [mm] |
|---|---|---|
| USB-C ペグ ×2 | (176.861075, 108.097861) / (176.861075, 113.877885) | 0.700 |
| M2 取付 H1 | (123.048, 83.048) | 2.3876 |
| M2 取付 H2 | (176.9468, 83.048) | 2.3876 |
| M2 取付 H3 | (123.048, 121.9608) | 2.3876 |
| M2 取付 H4 | (176.9468, 121.9608) | 2.3876 |

さらに **各穴の切削円 ＋0.2 mm の内側に銅が 1 つも無いこと**
（トラック・via・パッド・ゾーンフィルの全て。Gerber を独立パーサで読んで判定する。
pcbnew の DRC 結果は使わない ＝ 二重チェック）。

PTH 穴と via の員数は S2 の実測から**変化しないこと**（PTH 16、via 238）。
ECO で via を足す場合はその増分だけを許容し、`gates/S4.json` に記録する。

## E. Gerber

`kicad-cli pcb export gerbers` ＋ `export drill` の出力が:

- **14 ファイル**（銅 4 ＋ レジスト 2 ＋ シルク 2 ＋ ペースト 2 ＋ 外形 1 ＋ `.gbrjob` 1 ＋ ドリル PTH/NPTH 2）
- 銅層 **4**（F.Cu / In1.Cu / In2.Cu / B.Cu）
- 外形 **61.8236 × 45.0088 mm（±0.01）**
- **独立パーサで解析できること**（KiCad に読み直させるのではなく、自前の RS-274X パーサで
  アパーチャと座標を解いて上の寸法・D. の銅無し判定を出す）

## F. BOM / CPL

- BOM の**全行に LCSC 番号**があること（空・不明が 1 つでもあれば fail）
- BOM の designator 集合 ⇄ CPL の designator 集合が**一致**
- 部品 **135**（＝契約と同じ。`H1`〜`H4` と USB-C ペグは両方から除外）
- ECO-2 / ECO-3 の置換が反映されていること（`data/parts_lcsc.csv` が正）

## G. 実装プレビュー

`kicad-cli pcb render`（または `export image`）で top / bottom の PNG を
`fab/preview_top.png` / `fab/preview_bottom.png` に保存すること。

---

## この文書が定義しないもの

- **回路の正しさ**。契約 `contract/netlist_contract.json` が正であることは前提で、
  本文書はそれと基板が一致することしか見ない
- **C_VREFP_10u の LCSC 番号 C13585 の実在性**。ECO-3 が「実装前に JLC API で裏取り必須、
  不能なら C15008」としている。裏取りは発注担当の作業で、ここでは
  `data/parts_lcsc.csv` に書かれた番号をそのまま通す（記録は残す）
- **FB5 が VDD_ESP(3.3V) と DVDD(2.5V) をフェライトで直結している件**（S2 の申し送り）。
  回路図＝契約がそう書いている以上、基板をそれに合わせるのが本パイプラインの仕事。
  設計判断は別件として `gates/design_observations.json` に残す
  → **この 1 点は決着した。下の追記を参照**

---

## 追記（2026-08-28）— 合否基準は 1 つも変えていない

凍結後に判明した事実の記録。**A〜G の基準・数値・許容リストには一切手を入れていない。**

**FB5 は疑義ではなく仕様だった。** 上の「この文書が定義しないもの」3 つめの括弧書き
「DVDD(2.5V)」は誤り。**DVDD は 3.3V 給電が正**（ADS1299 の DVDD 範囲 1.8〜3.6V 内、
ESP32 の 3.3V ロジックとも整合）。`PROJECT_STATUS.md` の「DVDD = 2.5V 共通」という記述のほうが
旧い。したがって FB5 pin1=`VDD_ESP` / pin2=`DVDD` は契約どおりで正しく、
**基板側の変更は不要**（S4 時点で既に一致。B 節の「差分 0」はこれを含めて満たしている）。

---

## 追記 2（2026-08-28）— 基準 **H** を追加した。A〜G は 1 文字も変えていない

カート投入後に **R_CC1（0603・高さ 0.45 mm）が USB-C レセプタクル J1 の本体外形の
内側に丸ごと入っている**ことが、コネクタの外形図から判明した。J1 のシェルは基板に
べたで着座するので、この基板は**組み立てられない**。A〜G は 32 項目すべて pass のまま
これを通した。

### なぜ A〜G はこれを見つけられなかったか

**`courtyards_overlap` を warning に落としたことが、そのまま穴になっていた。**
A 節の許容リストにある通り、EasyEDA 由来のコートヤードは実寸よりはるかに大きく
（1.0 × 0.5 mm の 0402 に対して 1.93 × 1.17 mm）、既存配置だけで 69 組が重なる。
だから warning に落とす判断自体は正しい ── 誤りは、**落とした代わりに本当の問いを
聞かなかったこと**。本当の問いはコートヤードではなく**本体（F.Fab 外形）**である。
コートヤードは「置けるか」の目安だが、F.Fab はベンダが描いた部品そのもので、
これが交わっていたら物理的に載らない。R_CC1 は J1 の F.Fab の **3.16 mm 内側**にいた。

### H. 部品本体の重なり

**部品本体（F.Fab 外形）どうしの重なり 0（許容リスト `data/body_overlap_allow.json`
記載のみ）。**

判定は `scripts/64_body_overlap.py` →ゲート `gates/S7_body.json`（`run.sh` の S7 段、
S7 の直後）。本体箱の求め方は **F.Fab / B.Fab の `PCB_SHAPE` のみ**（テキストは除く。
リファレンス文字を含めると 0603 が 3 mm 幅に見えて検査が無意味になる）→無ければシルクの
`PCB_SHAPE` →無ければパッド範囲、の順。

| 区分 | 条件 | 合否 |
|---|---|---|
| overlap | 隙間 < 0（負値＝食い込み量 [mm]） | **H は fail**（許容リスト記載を除く） |
| contained | 一方の箱が他方に完全に含まれる | 同上（overlap の部分集合） |
| tight | 0 ≤ 隙間 < 0.15 mm | 報告のみ。fail にはしない |

許容リストは「実際に誰かが下した機械設計上の判断」だけを載せる。初期値は 1 件、
**`AMS1117` × `H4`（決定 M1）**── レギュレータ本体が M2 取付穴に張り出す件。H4 は
素の穴であって部品ではないので実装時に当たるものが無く、制約されるのは筐体側
（ねじ頭・ワッシャの逃げ）であって、本パイプラインの外の判断。

### H は現時点で fail する。それが正しい

| 組 | 隙間 [mm] | 内容 |
|---|---|---|
| `C_AVDD1_10n` × `U_MCU` | −3.1384 | ESP32-WROOM-32E の 25.5 mm 外形の下 |
| `U_ADS` × `U_MCU` | −2.8124 | 同上 |
| `C_DVDD_P40` × `U_MCU` | −1.6484 | 同上 |
| `C_AVDD1_100n` × `U_MCU` | −0.8524 | 同上 |
| `J1` × `PEG1` / `J1` × `PEG2` | −1.7495 | J1 自身のペグ穴（S4a が別 NPTH フットプリントとして合成したもの）。部品ではないので `part-on-hole` として区別表示している |

上 4 件は **ESP32-WROOM-32E → 32UE（全長 19.2 mm）への差し替え**で解消する見込みで、
その判断は本作業の外。**この 4 件が残っているうちは発注しない。**

### L7（R_CC1 の移設）で via が 2 本増えた ── D 節の「記録する」に従った記録

`scripts/36_repair_L7_rcc1.py` の記録。J1 パッド 4 は西からは入れない
（pad 3 / pad 5 まで 0.2002 mm、USB_DM のビアまで 0.1738 mm。最小トラック 0.0889 ＋
両側クリアランス 0.0889 ×2 ＝ **0.2667 mm** が必要）ので、USB_CC1 は J1 のパッド列を
B.Cu でくぐる。**via 239 → 241。** D 節は「ECO で via を足す場合はその増分だけを許容し
記録する」としており、これはその記録。

**次に S8 を出し直したとき、`scripts/50_final_check.py` の
`"D IPC-D-356 feature counts"` の定数を `[239, 417, 16, 6]` → `[241, 417, 16, 6]` に
直すこと。** 本作業では `fab/` を再出力していないので、いまの A〜G は現存する
パッケージ（via 239）を測っており全て pass している。

---

## 追記 3（2026-09-23）— 基準 **I** を追加した。A〜H の基準は変えていない

Y8 としてカートに入れた基板（決済なし）に、**SMD パッドのソルダーマスク開口の中に
ドリルが開いている via が 106 本**あった（Gerber 実測。ハーネス S7_viapad の盤面センサスでは 112 本）。
発注は Via Covering = Tented の 4 層で、via を塞ぐ工程がない。そのため 0402 の 29 か所、
ADS1299 の TQFP ピン 1 本、入力 CM コンデンサ 16 個などで、リフロー時にはんだが穴へ流れ込む。
A〜H にはこれを見る項目がなく、DRC にも該当する種別がない。

### I. ソルダーマスク開口の中の via

**via のドリルが SMD パッドの開口（F.Mask / B.Mask / F.Paste）にかかる本数が 0 であること。**
開口にはフットプリントが自前で描いたペースト図形も含める。

| 読み手 | 何を読むか | 判定 |
|---|---|---|
| `scripts/67_viapad_gate.py` | `fab/gerber` の PTH ドリル（⌀0.5 mm 以下を via とする）と F.Mask / B.Mask / F.Paste の開口を lib/gerber_parse で読む | ドリル縁と開口の距離 < 0.005 mm の via が **0 本** |
| ハーネス `pcbharness.gates.s7_viapad` | 盤面（テキスト）と fab の両方 | **pass** |

- **陰性対照**: SMD 開口の中心に仮の via を置き、読み手が数えることを毎回確かめる。
  数えられなければ fail とする。
- **ハーネスが見つからない場合も fail**。1 つの読み手だけでは pass にしない。
- ゲートは `gates/S7_viapad.json`（`run.sh` では S7_body の後に実行）。
- 是正は `scripts/66_fix_via_in_pad.py`（S7v）が行う。via をパッドの外へ出し、
  短い配線（dogbone）でつなぐ。穴埋め（有料 POFV）は使わない。
- S7b の「入力・電極ネットの差分 0」は例外を 1 つだけ認める。
  S7v がログに同じ座標で記録した via と配線に限る。
  その代わり S7v 自身が、IN1P〜IN8N の ADC〜入力抵抗の経路長が変わらないこと
  （0.1 mm 以内）と、P/N の長さ差が広がらないことを判定する。
- **SRB1 の ADC〜R_SRB_SER の経路長は、増加 1.0 mm 以内**（lead 裁定 2026-09-23）。
  SRB1 は共通の基準ネットで、差動対の長さ差の対象ではない。
  via がパッドの外に出ると、その分だけ経路が必ず伸びる。実測は +0.9 mm（全長 40.8 mm）。
- **VCAP1**（lead 裁定 2026-09-23、条件つきで受け入れ）: ADS1299 のピン 28 から C_VCAP1_H（100 nF）のパッドまでの経路は
  1.358 mm で、変わっていない。伸びたのは via からバルク側（C_VCAP1 100 µF、B.Cu）だけで、
  12.665 → 16.548 mm。AVSS に戻るループの面積は、投影面積で次のとおり悪化していない。
  | コンデンサ | Y8 | Y9 |
  |---|---|---|
  | C_VCAP1_H | 4.282 mm² | 4.277 mm² |
  | C_VCAP1 | 14.723 mm² | 14.730 mm² |
- **CM コンデンサの GND via がパッドから 1.3〜1.9 mm 離れた件**は受け入れる（lead 裁定 2026-09-23）。
- D 節の via 員数は 241 → **239** とする。F.Cu 以外のどこにもつながっていない AVSS via 2 本を
  S7v が取り除いたため（`logs/viapad_fix.json` の `removed`）。
  D 節の「変化は記録して許容する」に従った記録である。
  その後、基準 K で片側しかつながっていない via 5 本を取り除き、**234** になった（下記）。

## 追記 4（2026-09-23）— 基準 **J**（ステンシル）と **K**（行き先のない銅）を追加した

### J. ステンシル開口はパッドの上に収まる

EasyEDA からの取り込みで、50 フットプリントがパッドとは別に自前の F.Paste 図形（178 個）を持っていた。
そのうち **168 個が銅の外まで出ていた**。
- 0805 の 6 個（R_BIAS_SER ほか）は最大 0.134 mm。
- ADS1299 の 64 ランドは片側 0.076 mm。ランド間の隙間は 0.22 mm しかない。

ステンシルの開口がパッドの外に出ていると、はんだボールやブリッジの原因になる。

**F.Paste の開口は、どの点もいずれかのパッドの銅の上にあること（許容 0.002 mm）。**

- 判定: `scripts/69_paste_gate.py`（`gates/S7_paste.json`）。`fab/gerber` の F_Paste を F_Cu のパッド
  （%TO.P% 属性つきのフラッシュと領域）と突き合わせる。開口の外周を、領域は頂点と各辺の中点、
  フラッシュは 48 方向で調べる。
- 陰性対照: 開口を 0.1 mm ずらしたものを必ず検出すること。
- 是正: `scripts/68_fix_paste_graphics.py`（S7p）が、はみ出した図形をそのフットプリントの
  パッドとの積に置き換える。パッドの内側に収まっている図形はそのまま残す。
  盤面側でも同じ判定を行い、陰性対照を付ける（`gates/S7p.json`）。

### K. 行き先のない配線と via は 0

A 節では track_dangling / via_dangling を warning として許容していた。
実際に残っていたのは 27 本と 3 本で、どれもスティッチ via ではなかった。
EasyEDA の残骸と修理の切れ端で、アンテナとして働くだけのものだった。

**DRC の track_dangling と via_dangling が 0 であること。**

- 是正と判定: `scripts/70_prune_dangling.py`（S7d）。KiCad 自身の dangling 判定を使い、
  片側だけつながっている配線と、1 層にしか触れていない via を取り除く。
  連なっている場合は、なくなるまで繰り返す。
- 未接続数が増えた場合、またはパッドのネットが 1 つでも変わる場合は保存しない。
- `run.sh` の S7d 段は、ゾーンを再フィルした DRC で dangling が 0 であることを確かめる。
- 意図して残す切れ端を置く場合は、`KEEP` に 1 本ずつ理由を書く。今回は 0 本。
- 取り除いた内訳: 配線 33 本、via 5 本（`logs/dangling_prune.json`）。
  via の員数は 239 → **234** になる（D 節）。

---

## 追記 5（2026-09-23、独立 QA の MINOR への対応）— 基準 I を 0.1 mm に強め、基準 **L**（マスク堤）を追加した

### I の強化: via のドリルと SMD 開口の間を 0.1 mm 以上あける

JLC の目安は、via のドリル端から SMD パッドのマスク開口まで 0.1 mm です。
QA の時点では S7v の配置余裕が 0.03 mm だったため、0.0327〜0.1 mm の via が 20 本残っていました。

**`scripts/67_viapad_gate.py` の判定に「SMD 開口からドリル端までが 0.10 mm 未満の via が 0 本（Gerber で測る）」を加えた。**
あわせて、S7v（`scripts/66_fix_via_in_pad.py`）の違反判定と配置余裕を、4 段階とも 0.10 mm に上げた。
既存の「開口にかかる via 0 本」（許容 0.005 mm）の判定はそのまま残す。

### L. 異ネットのパッド間のマスク堤は 0.1 mm 以上

JLC は 0.1 mm 未満の緑のマスク堤を残さない。堤が削られると、隣り合う 2 つの開口が 1 つにつながる。
全体のマスク拡張 0.0508 mm（C 節）のままだと、異ネットのパッド 22 組で堤が 0.1 mm を切っていた（最小 0.0526 mm）。

**マスク開口どうしが異なるネットを含む場合、堤は 0.10 mm 以上であること。**

- **判定**: `scripts/72_mask_web_gate.py`（`gates/S7_maskweb.json`）。`fab/gerber` の F_Mask / B_Mask の開口に、
  その下にある F_Cu / B_Cu のパッドのネット（%TO.N%）を割り当て、開口の外形どうしの最小距離を測る（許容は丸めの 0.0005 mm だけ）。
  - 同じネットの開口どうしは、数えるだけで判定しない。
  - パッドも NPTH も下にない開口は赤とする。
- **陰性対照**: 異ネットの開口を 2 つ選び、堤が 0.05 mm になるまで近づけたものを必ず検出すること。
- **是正**: `scripts/71_mask_webs.py`（S7m）が、該当するパッドだけマスク拡張を下げる。値は (銅の間隔 − 0.10) / 2 で、0 未満にはしない。
  - 全体のマスク拡張 0.0508 mm（C 節）は変えない。
  - 銅の間隔がもともと 0.1 mm 未満で、マスク拡張をどうしても堤が取れない組は、理由をつけて `logs/mask_webs.json` に列挙する。
  - 同じネットの組は列挙して触らない。

### その他

- **D_ESD.3 のパッド内の切れ端（MINOR-5）**: 旧 via の中心からパッド中心までの F.Cu 0.45 mm を、S7v の `ROOM_EDITS` で削除した。
- **S3_sim（MINOR-4）**: 期待チェック数を 29 に固定し、数が足りなければ赤にする。
  TI のモデルが失敗またはタイムアウトした場合も、その行を省かず赤として書く。

---

## 追記 6（2026-09-23）— バイパスコンデンサ（SBAS499C 12.1、afe-adc J1）

VCAP3 / VCAP4 は、DS が求める容量のコンデンサ（C_VCAP3、C_VCAP4）を、ピンと同じ F.Cu 上で via なしに結んだ（S7j）。
どのコンデンサを J1 の判定対象にするかは `product.yaml` の `packs.afe-adc.ds_required_cap` で宣言している。
**C_VCAP1（100 µF、1206）は物理的に同じ層で結べない**（寸法は STATUS.md と `logs/bypass_caps.json` に記載）。
J1 の例外として扱うかどうかは lead の確認後に決める。それまで J1 は 1 件赤のまま置く。
