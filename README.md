# brain_canvas_kicad

Brain Canvas Rev.A (Therapia EEG/HRV board) を **EasyEDA Pro から KiCad 10 へ移行**し、
以後のレイアウト修理・製造データ出力を KiCad 側でヘッドレスに回すためのパイプライン。

対象基板: 4層 / 61.8236 × 45.0088 mm (2434 × 1772 mil) / 部品 131 個・全数 Top 実装。

## 前提

| 名前 | パス | 用途 |
|---|---|---|
| `KC` | `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli` | DRC・Gerber 等の CLI（10.0.5） |
| `KPY` | `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3` | `pcbnew` を持つ Python（3.9.13） |
| system `python3` | `/usr/bin/python3`（3.9.6） | 純 JSON 処理のステップ |

環境変数 `KC` / `KPY` で上書きできる。スクリプトは**標準ライブラリのみ**・**冪等**（再実行しても同じ結果）。
GUI は一切使わない。

## 使い方

```sh
./run.sh              # 未完のステップから順に実行（ゲート pass 済みは飛ばす）
./run.sh --status     # ゲート一覧を表示するだけ
./run.sh --force      # S0 から全部やり直す
./run.sh --from S2    # 指定ステップから再実行
./run.sh --no-commit  # git commit を作らない
```

ゲートが落ちると `exit 1` で停止する。**S1 の失敗は「.epro がまだ無い」待ち状態**であって
不具合ではない（`STATUS.md` 参照）。各ステップ成功後に `git commit` が入る。

```sh
python3 scripts/99_selftest.py   # 合成 .epro でパーサ／パッチャの動作確認（KiCad 不要）
```

## ステップ

| ID | スクリプト | 実行系 | 内容 | ゲート |
|---|---|---|---|---|
| S0 | `scripts/00_env_check.sh` | bash | kicad-cli / pcbnew / `EASYEDAPRO` / `ZONE_FILLER` / `drc --refill-zones` の存在確認 | `gates/S0.json` |
| S1 | `scripts/05_find_epro.sh` | bash + python3 | `~/Downloads` `~/Desktop` `~/Documents` `therapia-device/` から `.epro` / `.epro2` を捜して `import/` へ複製し sha256 記録 | `gates/S1.json` |
| S1B | `scripts/06_epro2_to_epro.py` | python3 | `.epro2`（EasyEDA Pro 3.2）を KiCad が読める旧 `.epro` へ変換。旧形式が既にあれば何もしない | `gates/S1B.json` |
| S2 | `scripts/10_epro_inventory.py` | python3 | `.epro` を自前パースして EasyEDA 側の員数表を作る | `gates/inventory_easyeda.json` |
| S2 | `scripts/11_import_epro.py` | KPY | パッチ段階を変えながら `PCB_IO_MGR.Load(EASYEDAPRO)` → `Save(KICAD_SEXP)` → パッド網の補修 → DRC | `board/*.kicad_pcb` |
| S2 | `scripts/12_verify_import.py` | KPY | `pcbnew.LoadBoard` で読み直して EasyEDA 側と突合 | `gates/S2.json` |
| S2B | `scripts/20_netlist_contract.py` | python3 | 回路図ネットリスト TSV を契約化し、PCB との差分（＝ECO-1 の残作業）を列挙 | `gates/S2B.json` |
| S4a | `scripts/13_fix_import.py` | KPY | NPTH 6 穴を合成（M2 ×4・USB-C ペグ ×2）し、開いていた基板外形を閉じる | `gates/S4a.json` |
| S3 | `scripts/14_make_rules.py` | python3 | JLC 4 層ルールを `.kicad_pro` / `.kicad_dru` / `.kicad_pcb` の `(setup)` へ生成 | — |
| S3 | `scripts/15_gate_s3.py` | python3 + KC | DRC ベースラインを取り、**ルールが L1〜L4 を実際に検出することを検定** | `gates/S3.json` |
| S4 | `scripts/19_make_parts_table.py` | python3 | 旧 BOM ＋ ECO-2/3 の置換表から `data/parts_lcsc.csv`（135 行）を生成 | — |
| S4 | `scripts/20_apply_eco.py` | KPY + KC | ECO-1/2/3 を PCB へ適用し、契約と全パッド突合、ゾーン再充填して DRC | `gates/S4.json` |

**S4a が S3 より先なのは意図的**。取付穴が NPTH になるまで hole clearance ルールに
引っかかる穴が存在せず、S3 のゲート（L1/L2/L4 の検出）が成立しないため。

### 共通ライブラリ

| ファイル | 中身 |
|---|---|
| `scripts/lib/epro.py` | `.epro` のパースとパッチ、ゲート JSON の読み書き |
| `scripts/lib/route.py` | 銅箔の空間索引・衝突判定、スタブ除去、2 層ルータ（直線→L 字→via ホップ）、部品配置探索。**L1〜L5 の修理もこれを使う** |
| `scripts/lib/drc.py` | DRC レポートの署名比較。`kicad-cli pcb drc` は同一入力で 525〜531 件と揺れるので、件数ではなく（種別, ネット集合）で比較する |
| `scripts/lib/xlsx.py` | 旧 BOM/CPL の xlsx を標準ライブラリだけで読む |

`import/` に**正規の旧 `.epro`** と `.epro2` が両方あるときは、必ず旧 `.epro` を使う（変換を挟まないぶん確実）。
`.converted.epro` は最下位。

## 落とし穴 3 つ（実測で確認済み）

### 1. `.epro2` は KiCad 10.0.5 では読めない。しかもエラーが出ない

EasyEDA Pro 3.2 の書き出しは `project2.json` ＋ 単一の `.epru`（全ドキュメントを
`{ヘッダ}||{本体}|\n` で連結したログ形式）。KiCad のバイナリに `project2.json` / `epru` /
`epro2` の文字列は 1 つも無く、`PCB_IO_MGR.Load` に渡すと **例外を出さずに空の基板
（フットプリント 0・ネット 1）を返す**。気づかず先へ進める形の失敗なので、S1 で形式を判定し
S1B で変換する。変換で運ばないもの:

- `RULE` — 3.2 の設計ルールは入れ子構造で旧形式への対応が付かない（これを誤ると #24303 を踏む）。値は `contract/easyeda_rules.json` に出すので S3 が `.kicad_pro` へ意図して書き写す
- `POURED` — EasyEDA が計算済みの銅箔充填。KiCad が `drc --refill-zones` で作り直すし、S3 は編集後にどのみち再充填が要る

### 2. 同じ番号のパッドは 1 つしかネットが付かない

KiCad は `PAD_NET` を `FindPadByNumber()` で当てるので、**同一番号のパッドが複数あると最初の 1 枚
にしか付かない**。この基板では ESP32 のサーマルパッド（`39` ×9）と USB-C のシェル脚
（`13`/`14` ×2）が該当し、GND が 10 パッド落ちる。`11_import_epro.py` が取り込み後に
EasyEDA 側の表を全パッドへ再適用して直す（`logs/pad_net_repair.json`）。

### 3. `kicad-cli pcb drc` はコマンドサンドボックス内では動かない（かつ非決定的）

サンドボックス下では `Swift/SwiftNativeNSArray.swift:78: Fatal error: Array index out of range`
で落ちる（Swift のエラーは表面的な症状で、原因は macOS のサービスが塞がれていること）。
`export gerbers` などほかのサブコマンドは影響を受けない。**DRC はサンドボックス外で実行する。**
通常のターミナルからは普通に動く。

さらに **DRC の出力は同一の基板に対しても揺れる**。実測で 525 / 528 / 531 件。
同じ物理的問題を代表する要素の選ばれ方が変わるためで、たとえば

```
run A   Track [V_NLDO_IN] on Bottom Layer, length 2.2860 mm  <-> Via [VNEG5]
run B   Track [V_NLDO_IN] on Bottom Layer, length 0.2543 mm  <-> Via [VNEG5]
```

は同じ 1 箇所を指している。したがって**件数で合否を判定してはいけない**。
`scripts/lib/drc.py` の署名（種別 ＋ ネット集合）で比較する。
部品参照を署名に含めてはいけない ── track（部品名を含まない）と pad（含む）が
入れ替わるだけで、無変更の基板が「新規 10 件・解決 10 件」に見える。

### 4. pcbnew の SWIG プロキシは `id()` で比較できない

基板から同じパッドを 2 回取り出すと別のプロキシが返り、`id()` が一致しない。
無視リストや訪問済み集合は `scripts/lib/route.uid()`（KIID 文字列）で持つこと。
関連して:

- `board.Remove()` は board 直下の要素に使うと以後 `GetFootprints()` が生の
  `SwigPyObject` を返すようになる。**`RemoveNative()` を使う**
- `pcbnew.FOOTPRINT(src)` は KIID ごと複製する（複製先のパッドが元と同じ uuid を持つ）。
  `m_Uuid` は書き込み不可で `FixUuids()` も効かないので、新規部品はゼロから組み立てる
- 同一プロセスでの 2 回目の `LoadBoard`、および `SaveBoard` の後は基板を走査できない。
  計測は保存前に済ませる

## KiCad 側インポータの既知バグと回避

`.epro` は ZIP の中に JSON Lines 文書（`project.json` / `*.epcb` / `*.esch` / `*.esym` / `*.efoo`）が入る形式
（仕様: <https://dev-docs.kicad.org/en/import-formats/easyeda/index.html>）。
KiCad 10 のインポータは現行の EasyEDA 出力に対して 2 つ落とし穴がある。

| KiCad issue | 症状 | 回避 |
|---|---|---|
| #24303 | パースが `type must be number, but is array` で落ちる。EasyEDA 2.2+ の `RULE` レコードが payload を 1 段深い dict に入れるため | `RULE` の `ruleData` を旧形式へ平坦化（clearance=`ruleType "1"` / track width=`"3"`） |
| #19021 | 読み込みは成功するのに**全パッド・全トラックが 1 ネットに融合**する。新しい出力が先頭の `NET` 宣言を落とすため | 各プリミティブの net 名フィールドを走査して、未宣言のネットを `["NET", name]` としてヘッダ直後に再注入 |
| （併発） | `std::out_of_range: map::at` で落ちる | 文書内の CRLF を LF へ正規化 |

手法は <https://github.com/enkhbold470/epro2kicad> を参照して `scripts/lib/epro.py` に自前実装した
（外部依存としては入れていない）。`11_import_epro.py` は

`raw` → `newlines` → `newlines+rules` → `newlines+rules+nets`

の 4 段階をそれぞれ**別プロセスの KPY で**試し（パーサが abort しても子プロセスだけが死ぬ）、
`gates/inventory_easyeda.json` の員数と突き合わせて**一番手を加えていないのに員数が合う段階**を採用する。
採用結果は `logs/import_attempts.json` / `logs/import_summary.json` に残る。

## 単位と座標

- EasyEDA Pro の PCB 内部単位は **mil**、**y は下向きが負**。`mm = mil × 0.0254`。
- KiCad は内部単位 nm、**y は下向きが正**。したがって EasyEDA の点 `(x, y)` は KiCad の `(x, −y)` に対応する。
- さらに KiCad は取り込み時に基板を **(120, 80) mm** 平行移動する（実測値。`gates/S2.json` の
  `board_offset_mm` に毎回記録される）。**S3 以降で EasyEDA 由来の座標メモ
  （`11_rev_a_eco_2026-08-16.md` の L1〜L6 など）を KiCad 上で使うときは
  `kicad = (x + 120, −y + 80)` [mm] で読み替えること。**
- 部品ローカル座標 → 基板座標は単純な回転（軸反転なし）:
  `bx = cx + lx·cosθ − ly·sinθ` / `by = cy + lx·sinθ + ly·cosθ`。
  `10_epro_inventory.py` が毎回 131 部品分を `fab_2026-08-16` の CPL（Pad X/Pad Y）と突き合わせて
  検証する（`cpl_crosscheck.placement_transform_verified`）。

## ディレクトリ

```
import/    .epro 原本（SHA256SUMS 付き）と patched.epro
board/     KiCad 成果物 (.kicad_pcb / .kicad_pro)
scripts/   パイプライン本体（lib/ は共通パーサ）
gates/     各ステップの合否 JSON と員数表
contract/  ネットリスト（S3 の契約）
fab/       製造データ出力先（S4 以降）
logs/      実行ログ・DRC 出力・パッチ試行履歴
```

## 参照する既存資料（読むだけ・変更しない）

- `../cerelog_research/11_rev_a_eco_2026-08-16.md` — ECO-1〜3 とレイアウト修理 L1〜L6 の正本
- `../cerelog_research/PROJECT_STATUS.md` — 経緯・ネット員数の記録
- `../cerelog_research/fab_2026-08-16/` — 旧版の Gerber / BOM / CPL。CPL の 131 designator と
  回転角は S2 の独立参照として自動で突合される
