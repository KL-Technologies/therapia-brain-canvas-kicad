# STATUS — brain_canvas_kicad

最終更新: 2026-08-28 / 担当: S0–S2

## 現在地

**S0 / S1 / S1B / S2 すべて pass。KiCad 側の基板 `board/Therapia_EEG-HRV.kicad_pcb` は
EasyEDA の内容と完全一致（17/17 チェック）。S3 に引き渡せる状態。**

| ステップ | 結果 | 内容 |
|---|---|---|
| S0 | **pass** 11/11 | kicad-cli 10.0.5 / KiCad python 3.9.13 / `pcbnew` / `EASYEDAPRO` / `ZONE_FILLER` / `drc --refill-zones` 全て有り |
| S1 | **pass** 3/3 | `ProPrj_Therapia_EEG-HRV_2026-08-28_v2.epro`（227,363 B, sha256 `83c096a6c23aa482…`）を `import/` へ確保 |
| S1B | **pass** 6/6 | `.epro2` も同時に確保されていたため変換も実施（`*.converted.epro`）。ただし**正規の旧 `.epro` があるのでそちらを採用**。変換物は使っていない |
| S2 | **pass** 17/17 | 取り込み・パッド網補修・突合すべて一致 |

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
| 穴 | 20/20 一致（M2 φ2.3876 ×4、J2 φ1.05 ×12、J1 スロット ×4） |
| 原点移動 | KiCad が (120, 80) mm 平行移動 |

`fab_2026-08-16` の CPL（131 部品）と位置・回転・パッド1座標が**全件一致**したので、
この export は 2026-08-16 の製造パッケージと同じ幾何。

## 次にやること（S3 への申し送り）

1. **ECO-1 は PCB に入っていない。** 下の「設計上の発見」参照。S3 は L1〜L6 に加えて ECO-1 の
   銅箔変更も KiCad 上で実施する必要がある
2. **設計ルールを移すこと。** `contract/easyeda_rules.json` に EasyEDA の値を出してある。
   `board/Therapia_EEG-HRV.kicad_pro` は最小構成のダミーで、ネットクラスも custom rule も未設定。
   **今の DRC 件数（1025）は KiCad 既定ルールに対する数字で、EasyEDA の DRC とは比較できない**
3. **座標の読み替え**: EasyEDA メモの `(x, y)` [mm] → KiCad `(x+120, −y+80)` [mm]
4. **`lib_footprint_issues` 131 件**はライブラリ未リンクによるもので実害なし。気になるなら
   フットプリントをプロジェクトライブラリに書き出して紐付ける
5. **ECO L4 の前提を取り直すこと。** 下記「ブリーフとの差分」参照

## 設計上の発見（取り込みの不具合ではない）

`gates/design_observations.json` に機械可読な形で置いてある。

### ECO-1 は PCB に未適用（確定）

- **TPS72325 pin3 (EN) = `GND`**。ECO-1 項目1 は `V_NLDO_IN` を要求。
  **致命バグ B1（AVSS が出ず ADS1299 全数不動作）が基板上にそのまま残っている**
- **AVDD のパッド数 = 21**。`PROJECT_STATUS.md` は ECO 前 21・ECO 後 20 と記録。21 = ECO 前
- ADS1299 (U_ADS, TQFP-64) の無ネットパッド: `27, 29, 30, 37, 42, 44, 45, 46, 55, 60, 62, 64`。
  ECO-1 が要求する VCAP2/VCAP3 の結線と GPIO1–4 の GND 直結はどれも未実施
- 注意: PCB にはパッド**番号**しか無くピン名が無い。RESV1 / GPIO1–4 / VCAP2・3 がどの番号かは
  回路図シンボル側で確認してから触ること（ECO 文書も「pinNumber ではなく pinName で照合」と指示）

### FB5（lead の質問への回答）

**FB5 pin1 = `VDD_ESP` / pin2 = `DVDD`。AVDD ではない。**

`PROJECT_STATUS.md` の「FB5(3V3→DVDD フェライト)」「FB5 給電は VDD_ESP ミニベタ」という記述と整合する。
ただし同ファイルはレール構成を「±2.5V (AVDD/AVSS) ＋ 2.5V (DVDD 共通) ＋ 3.3V (ESP32)」とも書いており、
その通りなら **3.3V 系の VDD_ESP と 2.5V 系の DVDD をフェライトで直結していることになる**。
これは計測結果であって判断ではない。**S3 は着手前にこの 1 点を設計側で確認すること**（推測ではなく確認事項）。

### ブリーフとの差分: ペグ穴 2 個が存在しない

ブリーフは NPTH 6 穴（M2 φ2.3876 ×4 ＋ **ペグ φ0.700 ×2**）を期待値としていたが、
この export に**ペグ穴（(56.861075, −33.877885) / (56.861075, −28.097861) の丸穴）は無い**。
代わりに J1 が **CHASSIS_GND のメッキ済みスロット穴 4 個**を持つ:

| 位置 (mm) | 穴サイズ | パッド番号 | ネット |
|---|---|---|---|
| (56.3409, −35.3130) | 1.5 × 0.6 | 13 | CHASSIS_GND |
| (60.5410, −35.3130) | 1.2 × 0.6 | 13 | CHASSIS_GND |
| (56.3409, −26.6630) | 1.5 × 0.6 | 14 | CHASSIS_GND |
| (60.5410, −26.6630) | 1.2 × 0.6 | 14 | CHASSIS_GND |

**取り込みの欠損ではない**（EasyEDA 側にある 20 穴は 20 穴とも KiCad に入っている）。
ECO の L4 は「CIRCLE r13.8mil の Slot Region e54/e55」を前提に書かれているので、
**S3 は L4 を実際の形状に対して取り直すこと**。この export に REGION プリミティブは 1 つも無い。

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
gates/design_observations.json     ECO 状態・FB5・ペグ穴・DRC 内訳
contract/netlist_from_epro_pcb.json        designator→パッド→ネット（PCB 由来・S3 の契約）
contract/netlist_from_epro_schematic.json  同（回路図由来・後述）
contract/netlist_from_kicad_pcb.json       取り込み後の KiCad 側
contract/easyeda_rules.json        EasyEDA 設計ルール（未移植・S3 が書き写す）
logs/drc_import.json               取り込み時 DRC
logs/pad_net_repair.json           パッド網補修の記録
logs/import_attempts.json          パッチ段階ごとの試行結果
```

### 回路図由来ネットリストについて

`.esch` の幾何から解いた（各 WIRE が `ATTR "NET"` に自分のネット名を持っているので、
ピン位置に重なる WIRE を引くだけで求まる。ラベル伝搬は不要）。
**128 部品 / ピン 375 本を解決、34 本未解決（91.7%）**。`status: "ok"`。

未解決 34 本は NC ピンや直付けピンとみられるが**未検証**。また PCB 側は 131 部品なのに
回路図側が 128 なのは、PCB 側だけでリネームした designator（`C_3V3_B`→`C_3V3_B2`、
`C_3V3_H`→`C_3V3_H2`）が回路図では旧名のままで重複しているため（`PROJECT_STATUS.md` 記載の既知事項）。

**S3 が回路図の正しさを厳密に判定する必要がある場合は、これを使わず
EasyEDA Pro エディタで `sch_ManufactureData.getNetlistFile()` を実行し、その `pinInfoMap` を
正とすること**（`11_rev_a_eco_2026-08-16.md` の受け入れ基準もそれ）。本ファイルは相互確認用。

## 再実行の仕方

```sh
./run.sh --status     # 現状確認
./run.sh              # 未完ステップから再開（全 pass 済みなら何もしない）
./run.sh --force      # 全部やり直し
python3 scripts/99_selftest.py   # 合成データでパーサを検証（24 チェック・KiCad 不要）
```

DRC を含むステップだけはサンドボックス外で実行すること。
