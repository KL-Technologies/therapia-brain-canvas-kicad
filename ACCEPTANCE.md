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
