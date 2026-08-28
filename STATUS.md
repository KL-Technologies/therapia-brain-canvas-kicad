# STATUS — brain_canvas_kicad

最終更新: 2026-08-28 / 担当: S0–S2（前任）→ S3・S4 → **S5・S6**

## 現在地

**S0〜S6 の 16 ゲートすべて pass。DRC error 0 / unconnected 0。
L1〜L5 のレイアウト修理は全部入った。残りは S7（最終検査・製造データ出力）だけ。**

| ステップ | 結果 | 内容 |
|---|---|---|
| S0 | **pass** 11/11 | kicad-cli 10.0.5 / KiCad python 3.9.13 / `pcbnew` / `EASYEDAPRO` / `ZONE_FILLER` / `drc --refill-zones` 全て有り |
| S1 | **pass** 4/4 | `ProPrj_Therapia_EEG-HRV_2026-08-28_v2.epro`（227,363 B, sha256 `83c096a6c23aa482…`）を `import/` へ確保 |
| S1B | **pass** 6/6 | `.epro2` も同時に確保されていたため変換も実施（`*.converted.epro`）。ただし**正規の旧 `.epro` があるのでそちらを採用**。変換物は使っていない |
| S2 | **pass** 17/17 | 取り込み・パッド網補修・突合すべて一致 |
| S2B | **pass** 5/5 | 回路図ネットリスト（EasyEDA API 由来）を契約として取り込み、PCB との差分＝ECO-1 の残作業を列挙 |
| S4a | **pass** 10/10 | NPTH 6 穴を合成、基板外形を閉じた（`scripts/13_fix_import.py`） |
| S3 | **pass** 10/10 | ACCEPTANCE.md 凍結、JLC ルール生成、DRC ベースラインで L1〜L4 を検出（`14_make_rules.py` / `15_gate_s3.py`） |
| S4 | **pass** 10/10 | ECO-1/2/3 を PCB へ適用（`19_make_parts_table.py` / `20_apply_eco.py`） |
| S5_uuids | **pass** 3/3 | 重複 KIID 2,625 個を採番し直した（`26_fix_uuids.py`）。**これを先にやらないと DRC が違う部品を指す** |
| S5_L1 | **pass** 8/8 | AMS1117 を H4 から退避（`30_repair_L1.py`） |
| S5_L2 | **pass** 6/6 | CHASSIS_GND を H1 の東へ迂回（`31_repair_L2.py`） |
| S5_L3 | **pass** 6/6 | ESP_TXD を分割して中央だけ H4 から逃がす（`32_repair_L3.py`） |
| S5_L4 | **pass** 7/7 | USB-C ペグ穴 PEG1/PEG2 を完全に空けた（`33_repair_L4.py`） |
| S5_L5 | **pass** 7/7 | 残り 27 箇所の近接を解消（`34_repair_L5.py`） |
| S5_mask | **pass** 2/2 | レジスト開口の合体 3 件をパッド個別マージンで解消（`35_mask_bridges.py`） |
| S6 | **pass** 11/11 | DRC 自動ループが `clean` で停止（`40_drc_loop.py` / `41_drc_fix_pass.py`） |

`./run.sh --status` でいつでも同じ表が出る。**DRC を含むステップはサンドボックス外で実行すること。**

### 最終 DRC（`logs/drc_s6_final.json`）

```
violations 465   error 0   warning 465   unconnected 0
warning 内訳: silk_overlap 199 / silk_over_copper 152 / courtyards_overlap 78 /
              track_dangling 25 / clearance 5 / via_dangling 3 /
              silk_edge_clearance 2 / starved_thermal 1
```

**warning はすべて ACCEPTANCE A の許容リストに載っている種別だけ。**
`clearance` の 5 件は error ではなく、ACCEPTANCE C が warning と定めた
「推奨 5 mil (0.127 mm)」に対するもの（error 級の 0.0889 mm は 0 件）。
**Amendments は不要だった** — solder_mask_bridge は 8 件とも実際に直せたので、
ACCEPTANCE.md には一切手を入れていない。

### 実行順が S4a → S3 → S4 になっている理由

S3 のゲートは「設計ルールが L1〜L4 を実際に検出すること」を検定する。取り込み直後は
取付穴が NPTH ではなく PTH パッドなので、hole clearance ルールに引っかかる穴が 1 つも無く、
L1 / L2 / L4 が原理的に検出できない。だから NPTH 合成（S4a）を先に済ませる。

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

## S3 / S4 でやったこと

### S4a — 取り込み欠陥の修理（`scripts/13_fix_import.py`）

| 症状 | 対処 |
|---|---|
| M2 取付穴 ×4 が PTH パッド | `H1`〜`H4` の NPTH（φ2.3876、銅なし、BOM/POS 除外）へ |
| USB-C ペグ ×2 が J1 の Edge.Cuts 多角形 | 独立フットプリント `PEG1`/`PEG2` の NPTH（φ0.700024）へ。J1 の多角形は削除 |
| **基板外形が 3 本の開いた線分**（新発見） | EasyEDA は外形を閉じた `POLY` 1 本（`0,0 → 2434,0 → 2434,-1772 → 0,-1772` mil）で持っているのに、KiCad のインポータが**閉じる 1 本を落としていた**。取り込み時 DRC の `invalid_outline` 1 件の正体。矩形 4 本を厳密寸法で引き直した |

ゲート: NPTH 6 穴が `fab_2026-08-16` の旧 DRL と **±2µm 一致**、PTH 16・via 238 不変、Edge.Cuts 4 本。

### S3 — 受け入れ基準とルールの凍結

- `ACCEPTANCE.md`（発注可の定義 A〜G）。**以後変更しない**。最終ゲートの仕様そのもの
- `scripts/14_make_rules.py` が `.kicad_pro` / `.kicad_dru` / `.kicad_pcb` の `(setup)` を生成（冪等）
- **DRC は 1025 件 → 526 件（error 67〜69）に落ちた。** 前は KiCad 既定ルールに対する数字だったので
  意味が無かった。`invalid_outline` `track_width` `annular_width` `padstack` `shorting_items`
  `copper_edge_clearance` `lib_footprint_issues` は全て消えた
- **ゲートは「ルールが L1〜L4 を実際に検出すること」を検定する**。4 件とも実測 0.0000 mm で検出:

| | 検出内容 | 実測 |
|---|---|---|
| L1 | H4 ↔ AMS1117 pad1 (GND) | hole clearance **0.0000 mm** |
| L2 | H1 ↔ CHASSIS_GND の Bottom 配線 | **0.0000 mm** |
| L3 | H4 ↔ ESP_TXD の Bottom 配線 | **0.0000 mm** |
| L4 | PEG2 ↔ USB_VBUS_RAW トラック 6 本＋via 8 本 / PEG1 ↔ via 4 本 | hole clearance **0.0000**、hole-to-hole **0.0000**（ECO の「via バレル不成立」と一致） |

### S4 — ECO-1 / ECO-2 / ECO-3 の適用（`scripts/20_apply_eco.py`）

**ネット変更 8 ピン、全部入った**（致命バグ B1 を含む）:

| designator | pad | → | 結線方法 |
|---|---|---|---|
| TPS72325 | 3 (EN) | `V_NLDO_IN` | pin2 (IN) へ直線 0.95 mm ＝ **B1 解消** |
| U_ADS | 31 (RESV1) | `GND` | AVDD スタブ除去 → pad33 (GND) へ L 字 |
| U_ADS | 42/44/45/46 (GPIO1–4) | `GND` | 42→pad41、44/46→45 で同辺に束ね |
| U_ADS | 30 / 55 (VCAP2/VCAP3) | 新ネット | コンデンサ側で結線（下記） |

**新設 4 部品・全部配置**（`C0402` を実寸複製、値/MPN/LCSC 付き）:

| designator | 位置 [mm] | 回転 | 対象ピンからの距離 | pin1 経路 |
|---|---|---|---|---|
| C_VCAP2 | (149.166, 109.172) | 0° | 1.53 mm | 直線 |
| C_VCAP3 | (144.118, 94.262) | 90° | 3.36 mm | via ホップ |
| C_VCAP3_H | (141.832, 95.024) | 270° | 5.44 mm | L 字（VCAP3 へ 2.29 mm） |
| C_VCAP1_H | (147.912, 109.426) | 270° | 1.36 mm | 直線 |

**ECO-3 の 1206 化・両方成功**（**90° 回転が鍵**。元の向きでは物理的に入らない）:

| designator | 位置 [mm] | 回転 | 移動量 |
|---|---|---|---|
| C_VCAP1 | (152.258, 115.052) | 90° | 2.50 mm |
| C_VREFP_10u | (150.937, 110.226) | 90° | 0.57 mm |

**ECO-2** は値と LCSC のみ（フットプリント不変）。**135 部品全部**に Value / MPN / `LCSC` フィールドを設定
（`data/parts_lcsc.csv` が正、`scripts/19_make_parts_table.py` が生成）。

結果: 部品 137→**141**（135 実装部品 ＋ 機械 6）、トラック 1191→1213、via 238→240。
**PCB 全パッドの net map ＝ 契約（差分 0）**、**未接続 0**、DRC error は**ベースラインから増えていない**。

## S5 — L1〜L5 のレイアウト修理

DRC error の推移: **S4 後 67〜69 → L1 59 → L2 57 → L3 56 → L4 30 →
（KIID 修正）28 → L5 4 → mask 1 → S6 0**。
unconnected は全工程を通じて 0、契約パリティも全工程 0 差分。

### 修理の一覧（座標はすべて KiCad mm）

| | 対象 | やったこと | 実測 |
|---|---|---|---|
| **L1** | H4 (176.9468, 121.9608) φ2.3876 が AMS1117 pin1(GND) を貫通 | AMS1117 を **+3.25 / +1.25 mm**（東・南）へ移設。原点 (173.594, 119.9795) → **(176.844, 121.2295)**。GND スタブ 3 本と GND via (175.372, 122.418) を撤去し、pin1 は新しい via で GND 面へ落とした。pin2/3/4 は既存銅に接続したまま | 全パッドの穴縁間 **0.4335 mm**（規則 0.2） |
| **L2** | H1 (123.048, 83.048) を CHASSIS_GND の Bottom 配線が貫通 | J2/12 (123.556, 87.2645) → (124.064, 81.016) を **H1 の東 x≈124.6505 まで膨らませて 4 セグメントで引き直し**（6.43 mm、直線なら 5.84 mm） | 0.3 mm 以上 |
| **L3** | H4 に ESP_TXD の Bottom 配線が 0.076 mm 食い込み | 11.68 mm の配線を**3 本に分割**し、(178.4755, 120.7415)〜(175.4181, 120.7415) の中央だけ 3 セグメントで引き直し | 0.3 mm 以上 |
| **L4** | PEG1 (176.8611, 113.8779) / PEG2 (176.8611, 108.0979) φ0.7 | PEG1 は via 退避＋配線 4 本の迂回。**PEG2 は経路そのものを廃止**（下記）。J1 の pin1/pin12 は 0.05 mm/片側 詰めた | 両穴とも**リング内の銅ゼロ**、J1 パッド 0.1712 → **0.2211 mm** |
| **L5** | 残り 27 箇所の近接 | via 退避 14・配線分割迂回 9・部品微動 4 | すべて 0.0889 mm 以上 |
| **mask** | レジスト開口の合体 3 件 | 該当 5 パッドのマージンを 0.0508 → 0.0307 / 0.0418 mm | web 0.0508 mm ＋2 µm 確保 |

### L4 の PEG2 は「近接」ではなく「経路の問題」だった

ECO は原因を「Slot Region e54/e55」としているが、実体は EasyEDA layer 12 の
FILL 円 **id e36 / e37**（S4a が NPTH パッド化済み）。ECO の id は当てにせず、
**基板の実形状から取り直した**。実測:

```
PEG2  via [USB_VBUS_RAW] (177.2010, 108.1430)  銅 -0.3119  穴間 -0.1596
      USB_VBUS_RAW トラック 6 本  -0.1086 〜 -0.3711
PEG1  via [USB_VBUS_RAW] (176.6930, 113.2230)  銅 +0.0213  穴間 +0.1736
```

via のドリルとペグのドリルが 0.16 mm 重なる＝**バレルが成立せず VBUS が基板に来ない**
（ECO の指摘どおり）。しかし PEG2 側は退避では直らなかった:
VBUS が J1 pin11 に届く唯一の経路が、ペグと裏面 ESP_RXD の間を東へ抜ける通路で、
**その通路の銅がすべてペグのリング内にある**。トラックは両端がリング内なので
「自分の両端の間を引き直す」では動かせず、via は 2.5 mm 以内に合法な置き場所が無い。
→ **その 7 本（トラック 6・via 1）を削除し、J1 pin11 を西側から給電**した
（2.03 mm。VBUS の via が 2.4 mm 西に既にあり、もう一方の VBUS パッド pin2 は
もともと西から来ている）。

### J1 pin1 / pin12 のパッドを 0.05 mm 詰めた（フットプリント変更）

USB-C コネクタの**自分の GND パッドが自分のペグ穴から 0.5213 mm** しか離れておらず、
穴縁間 0.1712 mm ＝ 規則 0.2 mm に **0.0288 mm 足りない**。これは配線ミスではなく
ベンダのフットプリント形状。基準を緩めるのではなく、
**ペグ側の軸に 0.05 mm/片側 詰めた**（ランド長 1.10 → 1.00 mm、−9%）。
USB-C の機械的保持は PTH のシェル脚 pad13/14 が担っており、pin1/12 は信号 GND なので
接合強度に実害はない。`gates/S5_L4.json` の `pad_trims` に前後の寸法と隙間を記録。

### 部品の微動（L5）

| designator | 移動 |
|---|---|
| C_AVSS_B | +0.15 mm (x) |
| C_3V3_H | +0.05 mm (y) |
| C_VREFP_10n | +0.05 mm (x) |
| C_RST_DLY | −0.05 mm (x) |

いずれも 0402。どちらもパッド同士の近接で、動かせる銅が他に無かった箇所。

### レジスト開口（solder_mask_bridge）— 8 件すべて実際に直した

`ACCEPTANCE.md` は**一文字も変えていない**。Amendments 節も作っていない。
S4 時点の 8 件のうち 5 件は L1〜L5 の銅の移動で自然に消え、残り 3 件は
パッド個別の `solder_mask_margin` を下げて解決した:

| ペア | 銅の隙間 | マージン |
|---|---|---|
| C_VCAP1_H/2 (AVSS) ↔ C_VREFP_100n/1 (VREFP) | 0.1142 mm | 0.0508 → 0.0307 |
| Q_IO0/3 (ESP_IO0) ↔ R_Q_EN_B/2 (Q_EN_B) | 0.1364 mm | 0.0508 → 0.0418 |
| Q_IO0/3 (ESP_IO0) ↔ R_Q_EN_B/1 (CH_DTR_N) | 0.1364 mm | 0.0508 → 0.0418 |

板全体の `pad_to_mask_clearance`（ACCEPTANCE C の 0.0508 mm）は不変。
レジストをパッドの内側に食い込ませてもいない（下限は 0）。

## S6 — DRC 自動ループ

`scripts/40_drc_loop.py`（ドライバ・素の python3）＋
`scripts/41_drc_fix_pass.py`（1 反復ぶんの修正・KPY）。
**pcbnew は 1 プロセスで 2 回 LoadBoard できない**ので、DRC を回す側と基板を触る側は
必ず別プロセスにする。停止条件は 4 つ（`clean` / 20 反復 / 2 連続で解決ゼロ /
違反集合ハッシュの再出現）。**件数では判定しない**（同一基板でも 525〜531 と揺れる）。

初回は `stalled` で止まり、それが**修正器の本当の穴を炙り出した**:
最後の 1 件は ADS_RESET_N が C_RST_DLY の自分の GND パッドから 0.0685 mm の位置で
西へ折れる**トラックの端点そのもの**にあった。端点が違反なのだから、
同じ両端の間を引き直しても直らない。加えて部品微動は「成功」と報告していたが、
その合法性検査は**自部品のパッドと自部品に付いた配線を無視する**ので、
まさに問題のペアを見ていなかった。`retreat_track_end`（角と、そこに集まる配線を
まとめて動かす）を足し、微動には実際のペアの隙間を検証させた。次の実行で 1 反復で解決。

### 人が見るべき点（施主向け・DRC は通っている）

1. **AMS1117 が 3.48 mm 動き、その本体が H4 の真上に来た。**
   西・北（ECO が指定した向き）は塞がっている ── 西は pad4 が FB3 pin2 と U_USB pin8 に、
   北は pad3 が J1 pin13（USB-C シェル）と PEG1 に当たる。空いているのは南東の隅だけ。
   **移設前から本体は H4 の西半分を覆っていた**が、移設後は穴全体を覆う。
   H4 に M2 のネジ頭やスペーサが来る設計なら干渉する。**筐体側の確認が要る。**
   （探索は「本体が穴に掛からない位置」を最優先で走査したが、±8 mm に 1 つも無かった）
2. **J1 pin1 / pin12 のランドが 1.10 → 1.00 mm。** 上記のとおり。
3. **C_VCAP3 の pin1 が 3.36 mm、C_VCAP3_H が 2.29 mm**（S4 から未変更）。
   バイパスコンデンサとしては長い。ADS1299 北側は AVDD/AVSS の逃げ配線で埋まっている
4. **C_VCAP1 が 2.50 mm 移動**（S4、1206 化のため）。ADS1299 のレイアウト指針に照らして要確認
5. 旧 STATUS の「C_VCAP1_H が C_AVSS_P37 とレジスト開口を共有」は**誤りだった**。
   重複 KIID のせいで DRC が別のパッドを指していただけで、実際の相手は
   **C_VREFP_100n**。上表のとおり解決済み

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

### FB5 — **決着済み（2026-08-28、lead 判断）。PCB 側の変更は不要**

**FB5 pin1 = `VDD_ESP` / pin2 = `DVDD`。契約どおりで、これが設計の正。**

S2 は「3.3V 系の VDD_ESP と 2.5V 系の DVDD をフェライトで直結しているように見える」と疑義を出したが、
**前提が古かった。DVDD は 3.3V 給電が正**（ADS1299 の DVDD 範囲 1.8〜3.6V 内、ESP32 の 3.3V ロジックとも整合）。
`PROJECT_STATUS.md` の「DVDD = 2.5V 共通」という記述のほうが旧く、そちらが誤り。

基板は既に契約と一致しているので**やることは無い**（実測: FB5 pin1=VDD_ESP / pin2=DVDD、
DVDD 13 パッド・VDD_ESP 12 パッド、いずれも契約の員数と一致）。
契約に対する残差分は `gates/netlist_diff.json` の 16 件（ピン 8 ＋ 新設 4 部品のパッド 8）だけで、
それは S4 で全部消えている。**S5 は FB5 を触らないこと。**

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

## S7（最終検査・製造データ）への申し送り

`ACCEPTANCE.md` が発注可の定義。**凍結済みで、S5/S6 でも一文字も変えていない。**
A（DRC）と B（契約）と D の一部は S6 のゲートで既に満たしている。
残りは E（Gerber）/ F（BOM・CPL）/ G（プレビュー）と、それらを A〜G として
束ねる `scripts/50_final_check.py`。

### いま基板がどうなっているか（`KPY scripts/42_board_facts.py` でいつでも再測定できる）

| 項目 | 値 | 備考 |
|---|---|---|
| DRC error / unconnected | **0 / 0** | `logs/drc_s6_final.json` |
| 契約パリティ | **0 差分** | 全 439 パッドの designator→pad→net |
| 部品 | 141（実装 135 ＋ 機械 6） | 機械 = H1〜H4 / PEG1 / PEG2 |
| トラック / via | 1250 / **239** | S2 実測 238 → S4 で 240 → L4 で 1 本削除して 239 |
| PTH / NPTH | **16 / 6** | S2 から不変 |
| ゾーン | 10、**全部フィル済みで保存** | |
| パッドのレジストマージン個別指定 | **5 パッド** | 上表。Gerber 出力に効く |

NPTH 6 穴は ACCEPTANCE D の表と一致（S6 ゲートが assert 済み）:
PEG1 (176.8611, 113.8779) / PEG2 (176.8611, 108.0979) φ0.700、
H1 (123.048, 83.048) / H2 (176.9468, 83.048) / H3 (123.048, 121.9608) /
H4 (176.9468, 121.9608) φ2.3876。

### 必ず知っておくべきこと

1. **重複 KIID は直したが、それが何を意味するかは覚えておくこと。**
   取り込み直後の基板は 231 個の uuid を複数アイテムで共有していた（38 部品が同じ 1 個）。
   KiCad の DRC は違反アイテムを **KIID で保存して後から引き直す**ので、
   重複があるとレポートが**別の部品を名指しする**。`26_fix_uuids.py` が採番し直した。
   **`11_import_epro.py` からやり直す場合は、S5_uuids を必ず先に通すこと。**
   `scripts/lib/route.uid()` も KIID 単独では一意でないので、パッドと部品は
   reference とフットプリント相対座標を足した鍵を返すようにしてある
2. **DRC レポートの `pos` は違反の位置ではない。** アイテム自身のアンカー
   （トラックなら始点）なので、11 mm のトラックだと違反箇所と数 mm ずれる。
   位置が要る処理は `scripts/lib/repair.py` の
   `clearance_pairs` / `hole_pairs` / `copper_near_hole` で**自分で幾何から出す**
3. **DRC 件数で判定しないこと。** 同一入力で 525〜531 件と揺れる。
   `scripts/lib/drc.py` の署名比較（種別＋ネット集合）を使う
4. **`pcbnew` は 1 プロセスで 2 回 `LoadBoard` できない。** DRC を回すスクリプトと
   基板を編集するスクリプトは分けること（S6 がその形）
5. **DRC はコマンドサンドボックス内では落ちる。** サンドボックス外で実行する
6. **FB5 は触らないこと。** 決着済み。契約どおりで基板も一致している

### まだ書いていないもの

- `scripts/50_final_check.py`（ACCEPTANCE A〜G の機械化）
- Gerber / ドリル / BOM / CPL の出力と**独立パーサでの検証**（ACCEPTANCE E・D 後半）。
  `fab/` は空（`fab/drill_check/` だけ S4a が使う）
- 実装プレビュー PNG（ACCEPTANCE G）
- BOM 側は別担当が `scripts/40_gen_bom_report.py` と `reports/` で進めている
  （こちらは基板側しか触っていない）

### 使えるもの

| ファイル | 何ができるか |
|---|---|
| `scripts/42_board_facts.py` | 上表を基板から再測定して JSON で出す。ゲートはこれを引用する |
| `scripts/29_drc_report.py` | 保存済み DRC レポートを種別ごとに整形。`--type` `--json` |
| `scripts/28_board_inspect.py` | KIID / reference / ネット / 座標でアイテムを引く |
| `scripts/27_net_islands.py` | ネットが電気的に分断されていないかを保存前に見る |
| `scripts/40_drc_loop.py` | 何か直したあとに回せば、DRC が clean になるまで自動で追い込む |
| `scripts/39_fix_unconnected.py` | DRC が unconnected を出したとき、その 2 点を繋ぎ直す |

## 途中で直した問題

| 問題 | 対処 |
|---|---|
| EasyEDA Pro 3.2 が書き出す `.epro2` を KiCad が**無言で空基板として**読む | 形式を判定（S1）し、旧 `.epro` へ変換する S1B を追加。今回は正規の旧 `.epro` が用意されたのでそちらを採用 |
| 同一番号パッドの 2 枚目以降にネットが付かない（GND 90→82 / CHASSIS_GND 5→3） | 取り込み後に EasyEDA の表を全パッドへ再適用。10 パッド補修、DRC の unconnected 2→0 |
| `kicad-cli pcb drc` がサンドボックス内で Swift エラー落ち | サンドボックス外で実行。README に明記、スクリプトも検知してヒントを出す |
| 外形が 61.925 × 45.111 と出る | `GetBoardEdgesBoundingBox()` が線幅 4mil を含むため。Edge.Cuts の中心線から算出するよう変更 |
| 層別比較が全件不一致になる | 取り込み後の層名が EasyEDA 表記（"Top Layer"）のまま。`GetStandardLayerName()` で正規名に揃えて比較 |
| `wx.App()` が headless で `SystemExit` を投げ子プロセスごと落ちる | `pcbnew` は wx 無しで動くので生成しない |
| **`id()` が pcbnew では使えない** | SWIG は基板から取り出すたびに別のプロキシを返すので、同じパッドを 2 回取ると `id()` が違う。無視リストが全部壊れ、ECO スクリプトが「自分自身と衝突する」と言い続けた。`lib/route.uid()`（KIID 文字列）に統一 |
| **`board.Remove()` が SWIG の型情報を壊す** | board 直下の要素を消すと以後 `GetFootprints()` が生の `SwigPyObject` を返す。`RemoveNative()` は壊さない。footprint 内の要素は先に集めてから消せば `Remove()` で可 |
| **`pcbnew.FOOTPRINT(src)` は KIID ごと複製する** | 複製した部品のパッドが元と同じ uuid を持つ（実測）。`m_Uuid` は書き込み不可、`FixUuids()` も効かない。新設部品はゼロから組み立てる（`make_chip_footprint`） |
| **`LoadBoard` / `SaveBoard` の後は基板を走査できない** | 同一プロセスで 2 回目の `LoadBoard`、および `SaveBoard` の後は proxy が生のオブジェクトになる。計測は保存前に済ませる |
| **DRC が非決定的** | 同じ基板で 525／528／531 件と揺れる。原因は同一箇所を代表する要素の選ばれ方。`lib/drc.py` の署名比較で吸収 |
| **KIID が一意でない（S5 の最大の発見）** | EasyEDA インポータがライブラリ部品の全インスタンスに同じ KIID を振る。231 個の uuid が重複、うち 1 個は 38 部品で共有。KiCad は uuid の一意性を前提にしており、`BOARD::GetItem(KIID)` は最初に見つけたものを返す。**DRC は違反アイテムを KIID で保存して後から引き直す**ので、レポートが別の部品を名指しする ── 9.3 mm 離れたパッド同士の `solder_mask_bridge`、8.9 mm 離れたパッド同士の 0.0420 mm `clearance`、VDD_ESP のはずが USB_5V のパッドを掴んだ結線修復（24.7 mm・106 本のトラックを敷いた）。**種別と件数は常に正しく、間違っていたのはアイテムの同定だけ**。`26_fix_uuids.py` が 2,625 個を採番し直した（基板の幾何・ネットは不変を検証済み） |
| `lib/route.uid()` が KIID 単独だった | 上記の重複により、`ignore` リストが無関係な部品まで無視し、`CopperIndex` のクエリ内重複排除が本物の障害物を捨て、接続性チェックが 38 パッドを 1 ノードに融合していた。パッドは reference ＋フットプリント相対座標、部品は reference を鍵に足した。相対座標なのは、部品を動かしても鍵が変わらないようにするため |
| DRC レポートの `pos` は違反の位置ではない | アイテム自身のアンカー（トラックなら始点）。11 mm のトラックだと違反箇所と数 mm ずれる。位置が要る処理は `lib/repair.py` の `clearance_pairs` / `copper_near_hole` で幾何から出す |
| ゾーンの塗り潰しを穴なしで再構成すると全部繋がって見える | `net_components` の初版が `SHAPE_POLY_SET::Outline(i)` だけを足していた。ベタは「1 本の外形＋異ネットのパッドごとに開けた穴」なので、穴を落とすと板全体が 1 枚の銅になる。`HoleCount`/`Hole` も足す |
| 同一ネットのゾーンが複数あると分断に見える | VDD_ESP は 3 枚のベタに分かれている。重なっているベタ同士は 1 つの導体なので、フィル島同士も併合する |
| 結線修復が板を横断する | 上限を付けないと、切れた VDD_ESP に対して 24.7 mm・106 セグメントの経路を「合法だから」と敷く。`MAX_HEAL_MM` と、直線距離の 3 倍という上限を入れた |
| 迷路ルータの結果が階段状 | 8 方向グリッドは等コスト経路が大量にあり、A* は最初に到達したものを返す。H1 の迂回が 25 セグメントになった。経路を string-pull（見通しの利く限り直線に置き換える）してから採用する |
| 部品微動が「成功」と言って何も直さない | 合法性検査が自部品のパッドと自部品に付いた配線を無視するので、その 2 者の近接（C_RST_DLY のケース）が見えない。移動後に**実際のペアの隙間**を測って検証する |
| 端点にある違反は迂回では直らない | トラックの端点そのものが違反位置だと、同じ両端の間をどう引き直しても直らない。`retreat_track_end` で角ごと（そこに集まる配線ごと）動かす |

## 成果物

```
ACCEPTANCE.md                      発注可の定義（凍結）。最終ゲートの仕様
data/parts_lcsc.csv                designator -> Value / MPN / LCSC（135 行、ECO-2/3 込み）
board/Therapia_EEG-HRV.kicad_pcb   ECO 適用＋L1〜L5 修理済み。DRC error 0 / unconnected 0
board/Therapia_EEG-HRV.kicad_pro   JLC 4 層ルール／ネットクラス／severity（14_make_rules.py が生成）
board/Therapia_EEG-HRV.kicad_dru   NPTH hole clearance と 5mil 推奨の custom rule（同上）

--- S5/S6 で足したもの ---
scripts/26_fix_uuids.py            重複 KIID の採番し直し。**S5 の最初に必ず通す**
scripts/27_net_islands.py          ネットの電気的分断を保存前に見る
scripts/28_board_inspect.py        KIID/reference/ネット/座標でアイテムを引く
scripts/29_drc_report.py           保存済み DRC を種別ごとに整形
scripts/30_repair_L1.py 〜 34_repair_L5.py   L1〜L5 の修理本体
scripts/35_mask_bridges.py         レジスト開口の合体をパッド個別マージンで解消
scripts/39_fix_unconnected.py      DRC の unconnected を読んで 2 点を繋ぎ直す（別プロセス用）
scripts/40_drc_loop.py             DRC 自動ループのドライバ（素の python3）
scripts/41_drc_fix_pass.py         1 反復ぶんの修正（KPY）
scripts/42_board_facts.py          ゲートが assert する事実を基板から再測定
scripts/lib/maze.py                2 層 A* ルータ（via 遷移つき・DRC と同じ判定・経路を直線化）
scripts/lib/repair.py              ルール値・穴距離・接続性・修理プリミティブ・ゲート雛形
scripts/lib/viol.py                DRC レポートを作業リストに変換
gates/S5_uuids.json S5_L1..L5.json S5_mask.json S6.json
logs/drc_S5_before.json            S5 開始時（＝S4 直後）の DRC
logs/drc_after_L1.json 〜 drc_s5_l5.json   各修理後の DRC
logs/drc_after_uuidfix.json        KIID 修正直後（初めてアイテム同定が正しくなった DRC）
logs/drc_loop_NN.json              S6 の各反復
logs/drc_s6_final.json             最終 DRC（error 0 / unconnected 0）

--- S3/S4 まで ---
scripts/lib/route.py               衝突判定・スタブ除去・2 層ルータ・配置探索
scripts/lib/drc.py                 DRC の揺れを吸収する署名比較
gates/S3.json S4.json S4a.json
logs/drc_baseline_rules.json       ECO 前・JLC ルールでの DRC（S4 の比較基準）
logs/drc_after_eco.json            ECO 後の DRC
logs/eco_apply.json                ECO の全操作ログ
logs/rules_applied.json            採用したルール値と EasyEDA 値との突合
gates/S0.json S1.json S1B.json S2.json S2B.json
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
