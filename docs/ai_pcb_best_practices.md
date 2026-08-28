# AI × KiCad/PCB 設計 ベストプラクティス（2025–2026 調査）

調査日: 2026-08-28 / 調査は Web 中心・read-only。**基板・スクリプト・contract は一切編集していない。**

対象: 本リポジトリ（Brain Canvas Rev.A / ADS1299 + ESP32 + CH340C / 4層 / JLCPCB PCBA）の
S7（最終検査）・S8（Gerber/BOM/CPL）・S9（JLC カート準備）を、Claude で安全・高品質に回すこと。

**表記**: 【実測】= この環境で実際に動かして確認 / 【一次】= 公式文書に記載 / 【推論】= 筆者の推測

---

## 0. 即採用リスト — S7〜S9 に今すぐ効くもの

順番は「効果 ÷ 実装コスト」。**1〜4 は S7 を書き始める前に読むこと。設計が変わる。**

### 0-1. 【最優先】IPC-D-356 を S7 の主検査データにする 〔採用〕

```bash
kicad-cli pcb export ipcd356 -o fab/board.d356 board/Therapia_EEG-HRV.kicad_pcb
```

**80 桁固定長 ASCII。stdlib のスライスだけで完全にパースできる。**【実測: 682 行】

| レコード | 意味 | 本件での用途 |
|---|---|---|
| `327` | SMD パッド | ACCEPTANCE **B**（designator→pad→net 契約） |
| `317` | スルーホール / via | 同上 ＋ PTH 員数 |
| **`367`** | **N/C = NPTH** | **ACCEPTANCE D（NPTH 6 穴）** |

実測した列レイアウト（1-based）:
```
327GND              LM2664-1          A01X+010031Y-017074X0433Y0236R000S2
317GND              VIA        MD0120PA00X+005875Y-007930X0240Y0000R000S3
367N/C              PEG2        D0276UA00X+022386Y-011062X0276Y0000R000S3
1-3            4-17=net  21-26=ref  27-31=pin  M+4桁=ドリル径  P/U=plated/unplated
A00=両面/A01=表面のみ  41-48=X  49-56=Y  57-61=Xsize  62-66=Ysize  R=角度  S=面
```

- 単位は **0.0001 inch**、原点は **aux/drill 原点**（本件は 120,80 mm）、**Y は負**
- 検算済み: `D0940` = 0.0940" = 2.388 mm、`D0276` = 0.7 mm → `.drl` の `T2C2.388` / `T1C0.700` と一致
- **H1〜H4 の M2 穴と PEG1/PEG2 が `367` レコードとしてそのまま入っている**

**なぜこれが効くか**: ACCEPTANCE D の「各穴の切削円 +0.2 mm の内側に銅が無いこと」は、
`367`（NPTH 中心＋径）と `327`/`317`（銅パッド中心＋サイズ）の距離計算だけで、
**Gerber を一切パースせずに** パッド分が書ける。トラック/ゾーン分だけ Gerber で補えばよい。
ACCEPTANCE B の全パッド突合も、`.d356` ⇄ `contract/netlist_contract.json` の集合比較で済む。

**⚠ 罠**: `.d356` の原点は aux 原点、Gerber は絶対原点。**素朴に突き合わせると 120,80 mm ずれる。**

### 0-2. Gerber X2 属性でネットが取れる。ただし**属性はスティッキー** 〔採用・要注意〕

KiCad は Gerber に **デフォルトで** ネット属性を埋める【実測】。`--no-x2` / `--no-netlist` は「切る」側のフラグ。

```gerber
%TF.GenerationSoftware,KiCad,Pcbnew,10.0.5*%
%FSLAX46Y46*%      ← 4.6 形式・先頭ゼロ省略・絶対
%MOMM*%
%TO.P,LM2664,1*%
%TO.N,GND*%
X145480000Y-123368000D03*
```

実測カウント（本基板）: F.Cu で `TO.N` 511 / `TO.P` 423、In1.Cu で `TO.N` 52 / `TO.P` 0（内層にパッド属性は出ない・仕様通り）、B.Cu で 88 / 14。

> ### ⚠⚠ 最重要の罠 — これを知らずに独立パーサを書くと**静かに間違ったネットを割り当てる**
>
> ```gerber
> %TO.P,LM2664,4*%
> %TO.N,V5_LM_IN*%
> X142780000Y-121468000D03*
> %TO.P,LM2664,5*%          ← TO.N が無い！
> X142780000Y-122418000D03*
> ```
> **KiCad はネットが「変わったとき」だけ `%TO.N` を出す。** 属性辞書は `%TD*%` か上書きまで生き続ける。
> pcbnew と IPC-D-356 の双方で pin 5 も `V5_LM_IN` であることを確認済み【実測】。
> 「D03 の直前行に TO.N があるはず」と書いたパーサはエラーを出さずに誤答する。
> **必ず `{TO.N, TO.P, TO.C}` の状態機械を持ち、`%TD*%` で全消去すること。**（本基板の `%TD*%` は 177 個）

補足: `--no-x2`（JLC 互換で切りたくなる）でも情報は消えない。prepend が `%`→`G04 #@!`、eol が `*%`→`*` に変わるだけで、`G04 #@! TO.N,GND*` として残る【一次: KiCad `gbr_metadata.cpp`】。ネット名の `\ % * ,` と非 ASCII は `\uXXXX` にエスケープされる。

### 0-3. 【最重要】DRC は非決定的。**件数比較は必ず壊れる** 〔採用〕

同一入力（実行前後で SHA-256 一致を確認）・プロジェクトファイル一式を揃えて 6 回実行【実測】:

```
violation counts: [490, 490, 490, 492, 490, 493]
出力順序:         毎回異なる
distinct signatures: 495 / 全 run で安定: 488 / ゆらぐ: 7（全て type=clearance）
```

- **生 JSON の diff / チェックサムは絶対に安定しない**（`date` フィールドも毎回変わる）
- **`(type, sorted(items[].uuid))` の SET 比較なら 98.6% 安定**（495 中 488）
- ゆらぐ 7 件は**全て `clearance`**（境界値付近の判定ゆらぎ）

**本件への直撃**: `logs/drc_s6_final.json` の warning 内訳に **`clearance` 5 件**がある。
S7 の最終検査を「warning 465 件」や「clearance 5 件」で固定すると、**再実行で理由なく落ちる**。

採用ルール:
- 比較は **シグネチャ集合の差分**。**multiset（重複度）は使わない** — 重複行数こそがゆらぐ
- `clearance` 型の新規シグネチャは即 FAIL にせず、**2 回再現で確定**（隔離ルール）
- `pos` と `description` はシグネチャに入れない（`description` には "actual 0.0428 mm" と実測値が埋め込まれる）
- `uuid` は盤面オブジェクト固有で、移動しても同じ。`uuid` だけで十分（`pos` を足しても unique 数は変わらない【実測】）

### 0-4. DRC は**必ずプロジェクトディレクトリで実行**する 〔採用〕

```
board のみコピー（.kicad_pro / .kicad_dru なし）: 1256 violations
プロジェクト一式コピー:                              490 violations
```
【実測】**2.5 倍。エラーも警告も一切出ずに default ルールへ落ちる。**

→ 「一時ディレクトリにボードだけコピーして検査」は禁止。S7 がサンドボックス回避や並列化のために
コピーする実装を採るなら、`.kicad_pro` / `.kicad_prl` / `.kicad_dru` を必ず同梱する。

関連【実測】: `--exit-code-violations` の戻り値は **5**（1 ではない）。`-ne 0` で判定すること。

### 0-5. `.gbrjob` はプレーン JSON。無料のメタデータ相互 assert 〔採用〕

`kicad-cli pcb export gerbers` が出す `.gbrjob` は JSON で、
`GeneralSpecs.LayerNumber` / `BoardThickness` / `DesignRules[].PadToPad` / `.TrackToTrack` / `.MinLineWidth` / `MaterialStackup` を持つ。
ACCEPTANCE E の「14 ファイル・銅 4 層」を、ファイル数を数える以外に**もう 1 経路**で確認できる。stdlib の `json` だけ。

さらに 3 経路（Gerber+gbrjob / IPC-D-356 / ODB++ `netlists/cadnet/netlist`）が
**同じネット集合・同じ層数・同じ穴径**を主張することの確認は、エクスポータのバグを捕まえる本物のチェックになる。

### 0-6. ラスタ XOR 回帰 diff が KiCad 同梱だけで書ける 〔採用〕

```
kicad-cli pcb export svg --layers F.Cu --black-and-white --mode-single \
          --exclude-drawing-sheet --page-size-mode 2 -o fcu.svg board.kicad_pcb
  → wx.svg.SVGimage.CreateFromFile()        # wxPython 4.2 同梱の nanosvg
  → .ConvertToScaledBitmap(wx.Size(W,H))    # wx.App 不要・ヘッドレスで動く
  → .ConvertToImage().GetAlphaBuffer()      # 生バイト列
  → 純 stdlib で XOR / popcount
```
【実測】`PYTHONNOUSERSITE=1` で通る。同一 SVG を 2 回ラスタ化して SHA-256 一致・`diff_px = 0` を確認。

- **インク判定は α チャンネルを使う。** `--black-and-white` の SVG は背景が透明で、RGB を見ると全面黒（99% インク）と誤判定する。`GetAlphaBuffer() > 127` で正しく 23.16% と出た
- `--page-size-mode 2` を固定しないと外形変更でスケールが変わり全面差分になる
- **`kicad-cli pcb render` は 3D レイトレースなので銅箔の幾何比較には使えない**（照明・視点依存）。ACCEPTANCE G のプレビュー PNG 生成には render でよいが、回帰比較には SVG 経路を使う

用途: 2026-08-16 版 fab パッケージとの目視回帰、L1〜L6 修理前後の差分確認。

### 0-7. Python 環境の落とし穴 — PIL / numpy は KiCad 同梱ではない 〔採用〕

【実測】KiCad 同梱 Python は **3.9.13**。`PYTHONNOUSERSITE=1` を立てたときの可否:

| モジュール | 通常 | `PYTHONNOUSERSITE=1` | 実体 |
|---|---|---|---|
| `wx` 4.2.2a1 / `pcbnew` / `requests` / `urllib3` | OK | **OK** | KiCad 同梱 |
| **`PIL` 11.3.0 / `numpy` 2.0.2 / `scipy` / `matplotlib` / `lxml` / `pydantic`** | OK | **MISS** | `~/Library/Python/3.9/…` ＝**過去の `pip install --user` の残骸** |
| `shapely` / `pycairo` / `rtree` | MISS | MISS | — |

**S7 のスクリプトが `PIL` や `numpy` を import すると、この開発機では動くが CI・他マシンでは落ちる。**
可搬性を担保するなら **stdlib + wx + pcbnew のみ**に縛り、スクリプト冒頭で
`PYTHONNOUSERSITE=1` を前提にした self-test を入れる（`scripts/00_env_check.sh` に 1 行足すだけ）。

### 0-8. SOT-23 系 6 部品が CPL 回転補正の危険地帯 〔S8 で必ず目視〕

`data/parts_lcsc.csv` の実測: **SOT-23-6 ×2 / SOT-23-3 ×2 / SOT-23-5 ×1 / SOT-353 ×1 = 計 6 部品。**

主要な 2 つの回転補正 DB が **SOT-23 で 270° 食い違う**:

| パターン | matthewlai `cpl_rotations_db.csv` | bennymeg `transformations.csv` |
|---|---|---|
| `^SOT-23` | **−90** | **180** |
| `^QFN-` 系 | 270 | 90 |
| `^SOIC-` / `^TSSOP-` / `^CP_Elec_` | 270 / 270 / 180 | 一致 |

本基板に QFN は無い。TQFP-64（ADS1299）・SOP-16（CH340C）は比較的安全。
**危険なのは SOT-23 系 6 部品と SOT-223（AMS1117）・USB-C。**
→ S9 の「Confirm Parts Placement」でこの 6 部品を最優先で目視する。チェックリストに固有名で載せること。

### 0-9. Extended 部品 17 個が Economic/Standard の分岐点 〔S9〕

【一次: jlcpcb.com/help/article/pcb-assembly-price】

| | Economic | Standard |
|---|---|---|
| セットアップ | $8.18 | $25.56（片面）/ $51.12（両面） |
| **フィーダー装填** | **$3.07（Extended のみ）** | $1.53（Basic/Extended とも） |

課金単位は**ユニークな BOM 行 1 つ＝フィーダー 1 台**（同じ部品を何個載せても 1 回）。
Preferred Extended は Economic のフィーダー料が免除される。
**損益分岐は Extended 17 個**（$25.56 vs $8.18 + 17×$3.07）。

分類用データ: **lrks/jlcpcb-economic-parts の CSV（約 3 MB、週次更新、`first seen`/`last seen`/`deleted` 列付き）**
https://lrks.github.io/jlcpcb-economic-parts/ — WebFetch で取れるサイズ。
（本家 yaqwsx/jlcparts は約 10 GB で Bash 無網では取得不可）

### 0-10. gerbonara / pygerber / pcb-tools は**全滅**。自前パーサの方針は正しい 〔見送り確定〕

| ライブラリ | 判定 | 理由 |
|---|---|---|
| **gerbonara** | **不可** | Python **`>=3.12`** 要求（同梱は 3.9.13）＋ `rtree`（C 拡張）依存 |
| **pcb-tools** | **不可** | **2024-06-19 アーカイブ済み**。README 自身が別ツールを見よと書いている |
| **pygerber** | 非推奨 | 3.8+ で依存もこの開発機には揃うが、**本体を入れる手段が無い**（pip 不可）＋クリーン機では依存も無い |
| **gerber-parser** | 不可 | C++/Qt のビルドが必要 |

→ **ACCEPTANCE E の「独立パーサで解析できること」は自前 stdlib 実装しか道が無い。**
ただし 0-1 / 0-2 のおかげで、幾何演算をほとんど書かずに済む。

---

## 1. KiCad 向け LLM / MCP ツール

### 1-1. 実行基盤: SWIG `pcbnew` vs IPC API（kipy）— **本件は SWIG 一択**

| | SWIG `pcbnew` | IPC API（`kicad-python` / `kipy`） |
|---|---|---|
| 公式ステータス | **KiCad 9.0 で deprecated、11.0 で削除予定**【一次】 | 「モダンなプラグイン開発で使うべきもの」 |
| KiCad 10.0.5 での可否 | **動く**（`GetBuildVersion()` = 10.0.5【実測】） | 動くが**GUI 常駐必須** |
| GUI 不要でファイルを開いて書いて保存 | **できる**（＝真のヘッドレス） | **できない**（公式明言） |
| pip | 不要 | **必須**（`pynng` はコンパイル済みホイール）→ **本環境では導入不能** |

**ヘッドレス化（`kicad-cli api-server`）は KiCad 11 で追加予定。10.0.5 にこのサブコマンドは存在しない【実測】。**
CI での現行回避策は Xvfb + PyVirtualDisplay（X11 前提）で、**macOS では成立しない。**

→ **判定〔採用継続〕**: 現行の SWIG 方針は正しい。ただし **KiCad 11 で消える**ので、
`pcbnew` 依存を 1 ファイルに閉じ込め、`pcbnew.GetBuildVersion()` を gate JSON に記録しておくこと。

**単位【実測・KiCad 10.0.5】**:
```python
pcbnew.PCB_IU_PER_MM       # 1000000.0  → 1 IU = 1 nm
pcbnew.FromMM(1)           # 1000000  <class 'int'>
pcbnew.VECTOR2I(...).x     # nm int
hasattr(pcbnew, 'wxPoint') # True  ← ★罠
```
> **`wxPoint` は KiCad 10 でも存在し、DeprecationWarning も出さずに動く。**
> LLM が KiCad 5/6 時代のコード（`wxPoint`、`FromMM` なしの生ミリ値）を書いても**その場では通る**。
> 対策: 座標ヘルパを 1 本（`mm(x) -> int`）に集約し、`wxPoint` と「6 桁未満の裸の整数座標」を hook で拒否。

### 1-2. MCP サーバ

| ツール | ★ / 最終更新 | 実体 | 判定 |
|---|---|---|---|
| **lamaalrajih/kicad-mcp** | 496 / **2025-10-17**（約 10 か月停滞） | プロジェクト一覧・PCB 解析・ネットリスト抽出・BOM・DRC（内部で kicad-cli）。**読み取り専用** | **〔見送り〕Python 3.10+ と uv 必須で動かない。かつ read-only で ECO 修正に無力** |
| **mixelpixx/Konnect** | 346 / **2026-08-27** | KiCad 10 専用 Rust 単一バイナリ。**回路図は S 式直接編集で GUI 不要**、**PCB は IPC API ＝ GUI 常駐必須**。Python 依存ゼロ。Claude skills 6 + agents 2 同梱 | **〔検討〕**機能は最も合致し Python 制約も受けない。ただし **AGPL-3.0**・PCB 編集が GUI 前提・バイナリ手動入手が必要 |
| **Seeed-Studio/kicad-mcp-server** | 88 / 2026-08-27 | ピンレベル接続トレース・design editing を謳う | **〔見送り〕ライセンス表記なし**（業務利用でリスク）＋実装方式 UNVERIFIED |

### 1-3. Claude Code 向け KiCad スキル

**aklofas/kicad-happy** — https://github.com/aklofas/kicad-happy
★1,000〜2,200（調査時点で計測差あり）/ MIT / **最終更新 2026-08-20** / 693 commits /
**Anthropic の `claude-plugins-community` マーケットプレイスに収録済み**（`/plugin install kicad-happy@claude-community`）。

- **同梱スキル 11 種**: `kicad`（回路図/PCB/Gerber パース、design review、DFM）、`spice`（テストベンチ生成・実行）、
  `emc`（**44 ルール**の EMI / PDN インピーダンス / 差動ペアスキュー / ESD 経路）、`datasheets`（PDF からピン配置抽出）、
  `bom` / `digikey` / `mouser` / `lcsc` / `element14` / `jlcpcb` / `pcbway`
- **KiCad 5〜10 全対応**。S 式を直接パースするので **kicad-cli も pcbnew も KiCad インストールすら不要**
- **解析専用（書き込みなし）** ＝ 破壊リスクゼロ
- 依存: 必須依存ゼロの純 Python

**判定〔検討・要検証〕**: **`Python 3.10+` 要求が唯一の障害**（同梱は 3.9.13）。
中身は ADS1299 基板の EMC/PDN レビューと JLC 提出前 DFM にそのまま刺さるので、**3.9 で実際に動くか試す価値が高い**。

**学ぶべき設計**（動かなくても真似できる）:
- **"Design Review Contract"** — 「レビュー」と言われたら最低限これを全部やれ、を SKILL.md に明記
- **trust gate**: `DS-001`（データシート未取得）が出たら **"verified" / "confirmed" / "per datasheet" の語の使用を禁止**し "consistency only" と書かせる
- skill 間の **handoff テーブル**（どのスキルに引き継ぐか明示）
- ⚠ **jlcpcb スキルには「発注するな」のガードレールが無い**（"Confirm and order" が普通に手順にある）。**発注ガードは自作必須**

**nickkraakman/skidl-skills**（★17 / 2026-04-08 で実質停止）— **〔見送り〕** SKiDL は回路をゼロからコードで書く流儀で、既存設計の修理には不適。

### 1-4. ファイルパーサ（pip 不可環境でのベンダリング候補）

| | ★ / 最終更新 | 依存 | 判定 |
|---|---|---|---|
| **kiutils** | 129 / **2024-07-10** | **依存ゼロの純 Python**（3.7+）。ソースコピーだけで載る | **〔見送り・優先度低〕** SWIG が使える以上不要。**2024-02 が最終リリース＝KiCad 9/10 より前**でラウンドトリップ危険。GPL-3.0 |
| **kicad-skip** | 228 / **2024-05-26** | `sexpdata`（単一モジュール純 Python）を併せてベンダリングすれば可 | **〔見送り〕**同上。更新停止が 2 年 3 か月 |

### 1-5. kicad-cli 10.0.5【実測で全列挙】

トップレベル: `fp` / `jobset` / `pcb` / `sch` / `sym` / `version`

**`pcb drc`**:
```
[-o OUT] [-D KEY=VALUE]... [--format json|report] [--all-track-errors]
[--schematic-parity] [--units in|mm|mils]
[--severity-all] [--severity-error] [--severity-warning] [--severity-exclusions]
[--exit-code-violations] [--refill-zones] [--save-board] INPUT
```

**JSON スキーマ**（`https://schemas.kicad.org/drc.v1.json`）:
```json
{ "$schema", "source", "date", "kicad_version", "coordinate_units",
  "included_severities", "ignored_checks": [{"key","description"}],
  "violations": [...], "unconnected_items": [...], "schematic_parity": [...] }
```
> **⚠ `violations` / `unconnected_items` / `schematic_parity` は 3 つの別配列。**
> 1 本だと思うとパリティ違反を丸ごと見落とす。

各要素: `{type, severity, excluded, comment, description, items:[{uuid, description, pos:{x,y}}]}`

**`pcb export` サブコマンド**: `3dpdf, brep, drill, dxf, gencad, gerbers, glb, hpgl, ipc2581, ipcd356, odb, pdf, ply, pos, ps, stats, step, stl, stpz, svg, u3d, vrml, xao`
- **ODB++ は `odb`**（`odb++` ではない）
- **`hpgl` は "No longer supported as of KiCad 10.0."**【実測・8.x/9.x からの変更点】
- `gerbers --precision 5|6`（既定 6）、`--check-zones`（DRC の `--refill-zones` に相当・付けること）
- **`drill` の既定は PTH/NPTH 混在の 1 ファイル**。`--excellon-separate-th` が必須（本件は既に使用済み）
- `--excellon-zeros-format` 既定 `decimal` ＝ **ゼロ抑制なし**（LZ/TZ 地獄は起きない）。ただし**ヘッダの `METRIC` / `decimal` / `FMAT,2` を必ず assert する**（設定変更で 25.4 倍事故が起きる）

**`sch export netlist --format`**: `kicadsexpr, kicadxml, cadstar, orcadpcb2, spice, spicemodel, pads, allegro`
→ **net→(ref,pin) 契約に一番向くのは `kicadxml`**（stdlib の `xml.etree.ElementTree` でそのまま読める）。
※ 本リポジトリには `.kicad_sch` が存在しないため現状は使えない。

**`jobset`（KiCad 9 で導入）〔検討〕**:
```
kicad-cli jobset run [--stop-on-error] [--file JOB_FILE] [--output OUT] INPUT
```
GUI で「Gerber・BOM・PDF・ERC・DRC」のジョブと出力先（フォルダ / ZIP）を組み立てて `.kicad_jobset` に保存 → CLI から一発実行。
**S8 の出力パイプラインを 1 行に集約でき、「出力の正典」をリポジトリにコミットできる。**
ただし**ジョブの組み立てに GUI が要る**ので、現行の「全部スクリプト」方針と流儀が競合する。急ぐ話ではない。

### 1-6. その他

| ツール | 判定 | 理由 |
|---|---|---|
| **InteractiveHtmlBom** (★4,533 / 2026-07-12 / MIT) | **〔検討・S9 に有用〕** `generate_interactive_bom board.kicad_pcb --no-browser --dest-dir OUT` を KiCad 同梱 Python で実行。**pip 不要で動く可能性が高い**（`pcbnew` は実測で動く）。実装/検品時の部品ハイライト付きビューは Confirm Parts Placement の往復削減に効く。KiCad 10 macOS 動作は UNVERIFIED |
| **kicad_netlist_reader** | **〔採用可〕** KiCad 同梱・純 stdlib。`sch export python-bom` の XML を読む。**インストール不要** |
| **KiBot** (★734 / 2026-08-27 / AGPL) | **〔見送り〕** 依存の KiAuto が **Xvfb + xdotool（X11）**前提で**実質 Linux/Docker 専用**。macOS 対応の明示なし。将来 Linux CI を作るなら第一候補 |
| **KiAuto** | **〔見送り〕** kicad-cli 10.0.5 が DRC/ERC/エクスポートをネイティブ提供する今、存在意義が無い |
| **KiDiff** | **〔見送り〕** Linux 前提の系譜。0-6 の wx.svg 経路で代替する |

---

## 2. JLCPCB 向け

### 2-1. Fabrication Toolkit（bennymeg）〔採用推奨・S8 の本命〕

https://github.com/bennymeg/Fabrication-Toolkit — ★672 / Apache-2.0 / **最終更新 2026-05-15**
**v5.3.0 で "Added KiCad 10 support"**、v5.3.1 で「KiCad 10 のフットプリント重複」修正。

```bash
python3 -m plugins.cli -p board/Therapia_EEG-HRV.kicad_pcb -t -nI -e
```
| フラグ | 意味 |
|---|---|
| **`-t / --autoTranslate`** | **回転/位置補正を適用**（JLCPCB 公式がこれを ON にせよと明記） |
| **`-nI / --nonInteractive`** | CI/CD 用（v5.2.0 で追加） |
| `-e / --excludeDNP` | DNP 除外 |
| `-f / --autoFill` | ゾーン再フィル |

**依存は `pcbnew` のみ**（`process.py` の import は `os, re, csv, math, shutil, collections, typing` + `pcbnew`。`cli.py` は `argparse` だけで `ProcessThread(wx=None)` を渡す）→ **GUI 不要・pip 不要**。

生成物: Gerber / ドリル `.xln` / IPC ネットリスト / designators / **補正済み CPL** / BOM CSV / zip。

**⚠ 唯一の外部依存**: プラグイン本体の取得。Bash 無網なので **KiCad GUI の Plugin Manager 経由か手動ダウンロード**が必要。

**〔採用の但し書き〕** 本件は既に自前で Gerber/ドリルを出す流儀が確立しており、ACCEPTANCE E が
「14 ファイル」「自前パーサで解析」を要求している。**Fabrication Toolkit を全面採用すると出力構成が変わり ACCEPTANCE と衝突する。**
→ **推奨は「CPL の回転補正だけを借りる」**（`plugins/transformations.csv` を読んで自前 CPL に適用する、
または Toolkit の CPL と自前 CPL を突き合わせる二重チェック）。

### 2-2. 回転補正 DB 〔採用: データファイルだけ借りる〕

**Bouni/kicad-jlcpcb-tools**（★2,044 / 2026-07-30 / MIT）は KiCad 10 対応済み（2026.04.01）だが、
**CLI が無く** standalone モードはボードデータがハードコードのスタブ → **ヘッドレス生成には使えない**。

**ただし回転 DB はスタンドアロンで取れる**（1,413 バイト・約 57 行、WebFetch で取り込めるサイズ）:
```
https://raw.githubusercontent.com/matthewlai/JLCKicadTools/master/jlc_kicad_tools/cpl_rotations_db.csv
ヘッダ: "Footprint pattern","Rotation","Offset X","Offset Y"
例: "^USB_C_Receptacle_XKB_U262-16XN-4BVC11",0,1.44,0
    "^PinHeader_2x05_P1\.27mm_Vertical",90,2.54,0.635
```
オフセット対応は 2025.09.01 で追加された。

**⚠ 2 つの DB が SOT-23 / QFN で食い違う**（→ §0-8）。**権威あるリストは存在しない。**
Bouni issue #752「Down the rabbit hole: Footprint rotation matching」（2026-04-24 起票、未解決）が現状を最もよく表す:
EasyEDA はフットプリント名のサフィックス（`-FD`/`-RD`）で向きを符号化しており、
同じ「ダイオード」でも pin1 の定義が部品ごとに違う（C131280 は pin1=K、C50494 は pin1=A）。

**根本原因**: KiCad は裏面部品をミラーするが JLCPCB はしない（KiBot 公式ドキュメント）＋
テープ&リール内の向き（EIA-481）と KiCad フットプリント基準向きの不一致。IPC-7351 / JEDEC への準拠宣言は**どちらの側にも無い**。

**JLCPCB 公式の見解**（https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad 、**2026-08-27 更新**）:
- BOM 必須列: `Comment, Designator, Footprint, JLCPCB/LCSC Part #` / CPL 必須列: `Designator, Mid X, Mid Y, Rotation, Layer`
- 単位 mm、CSV、**表裏を 1 ファイルに統合**
- **Method 2（Fabrication Toolkit）を推奨し、"Apply automatic component translations" を ON にせよ**
  → **JLCPCB 自身が「補正は必要」と認めている**

**`kicad-cli pcb export pos` に補正機能は無い**【実測】。オプション: `--side {front,back,both}` / `--format {ascii,csv,gerber}` / `--units {in,mm}`（**既定が `in` なので mm 指定必須**）/ `--bottom-negate-x` / `--use-drill-file-origin` / `--smd-only` / `--exclude-fp-th` / `--exclude-dnp`。

### 2-3. 設計ルール 〔検討: クロスチェックに使う〕

**JLCPCB 公式の `.kicad_dru` は存在しない。** 全て community 製。

**Cimos/kicad-druid** — https://github.com/Cimos/kicad-druid（MIT / **2026-08-16 更新**、labtroll → Cimos の系譜の最新）。
`JLCPCB.kicad_dru`（4 層 1oz が既定）/ `JLCPCB-2L-1oz` / `JLCPCB-4L-2oz` / `JLCPCB-6L-1oz`。KiCad 8 構文で 9/10 に前方互換。

**本リポジトリの ACCEPTANCE C と突き合わせた結果**:

| 項目 | ACCEPTANCE C（現行） | JLC 公式 capability | kicad-druid | 評価 |
|---|---|---|---|---|
| clearance / track 幅 | 0.0889（3.5 mil） | **0.09 / 0.09（1oz）** | 0.09 / 0.09 | ほぼ一致。**0.0889 は JLC の 0.09 をわずかに下回る** |
| hole-to-hole | 0.2 | — | 0.2 | 一致 |
| hole clearance | 0.2 | 内層 via hole→copper 0.2 | 0.2（via↔track） | 一致 |
| **基板端クリアランス** | **0.2** | **0.2** | **0.3** | **公式と一致。druid の方が保守的** |
| via ドリル | 0.3 | 最小 0.15 | ≥0.2 | 余裕あり |
| via アニュラリング | 0.076 | — | ≥0.05（via） | 余裕あり |
| **PTH アニュラリング** | 規定なし | **≥0.20** | 0.15 | **公式が最も厳しい。要確認** |

**→ 実務結論〔採用〕**: 現行ルールは概ね妥当。**追加すべきは PTH アニュラリング ≥0.20 mm の 1 項目**。
本基板の PTH は 16 個（+ HDR-2.54-2x6 と J1）なので、S7 で `.d356` の `317` レコード
（ドリル径 `M####` と `Xsize/Ysize`）から機械的に検算できる。

**⚠ 矛盾フラグ**: 基板端クリアランスは公式 0.2 / druid 0.3、PTH アニュラリングは公式 0.20 / druid 0.15 で逆方向にずれる。
どちらか一方を「正」と断言できない。**安全側（端 0.3 / アニュラ 0.20）を採るのが無難だが、現行 0.2 でも公式値は満たす。**

**非推奨**: tinfever 版は KiCad 7 専用、MuratovAS 版は archived（2023-09）。

**インピーダンス制御スタックアップ**（https://jlcpcb.com/impedance）: 4 層で 18 種。
`JLC04161H-7628` が最も標準・安価。誘電率: 7628 = 4.4 / 3313 = 4.1 / 1080 = 3.91 / 2116 = 4.16 / コア = 4.6。
**⚠ 目標インピーダンスに対する線幅/ギャップの表は非公開**（同社の計算機を使えとの案内のみ）。数値を捏造しないこと。

### 2-4. DFM 〔採用: S9 のゲートに入れる〕

**JLCDFM** — https://jlcdfm.com/viewer（JLCPCB 公式。EasyEDA / LCSC / OSHWLAB と並記）。
5 モジュール（traces / solder masks / drilling / silkscreen / component assembly）、**30 項目以上**。
入力は **Gerber の zip/rar、最大 50 MB**。BOM マッチング機能あり。
検出例: クリアランス違反を X/Y 座標付きで指摘 / リファレンスデザネータがパッドに重なる警告 / 最小トレース幅・drill-to-copper・アニュラリング。

**API / CLI は見つからず**。ローカル DFM チェッカーも JLC 固有のものは無い → **KiCad DRC + カスタムルールで一次スクリーニング、最終は Web の DFM**。

### 2-5. Confirm Parts Placement 〔S9 の必読〕

**公式の定義**（https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2）:
> "Generally, we only assemble those components which you have confirmed when ordering.
> **If you haven't click the 'confirm' button for the components, even if they occurs in the BOM file, we will not assemble them for you.**"

**→ 確認ボタンを押さなかった部品は、BOM にあっても実装されない。これが最大の落とし穴。**

- 発注時に**部品在庫が引き当て（occupied）される**ため即時支払いを求められる（放置できない）
- エンジニアが目視するのは **回転 / 極性 / pin1 を silkscreen 表記と照合**。CPL プレビューでは**赤ドットが pin1**
- JLC 公式の要請: 「**silkscreen レイヤを入れてほしい。確認が速くなり生産遅延を避けられる**」
- 極性判定基準（公式ガイド）: SMD 電解コン = **黒帯が負極** / SMD LED = **緑マーキングがカソード** / QFP・SOP = ディンプル or**他と大きさ・形が違うドット 1 個** / QFN = 差異のあるドット or 面取りコーナー
- 「**pin1 インジケータはパッド外か、基板の空きエリアに置くことを推奨**」

**往復を減らす実務**（一次情報: Graham Sutherland, 2025-07-05）:
- パネライズ時は **"Confirm Production File" を必ず ON**。JLC の自動パネル生成は**キャステレーションやコネクタの上に平気でマウスバイトを置く**（自動回避しない）→ バリでコネクタが刺さらなくなる
- サポートへの注記頼みで **1 週間の遅延**を食らった実体験あり

**本件のチェックリスト**: (a) SOT-23 系 6 部品＋SOT-223＋USB-C の pin1/極性を優先確認、
(b) 全デザネータをシルクに残す、(c) zip に README とアセンブリ図を同梱、
(d) **発注後は必ず全部品の confirm を押す**。

### 2-6. 発注自動化 〔S9・重要な安全事項〕

**JLCPCB 公式 API は存在する** — https://api.jlcpcb.com/ / https://jlcpcb.com/help/article/jlcpcb-online-api-available-now（**2026-03-25 更新**）
4 系統: PCB API（ファイルアップロード → 自動見積 → **発注** → 生産追跡）/ Stencil / 3D Printing / **Parts API**。
利用は無料だが、**「その partner の JLCPCB での過去発注実績・会社および事業状況」に基づく個別審査**がある。

> **⚠ つまり API キーを入れた瞬間、エージェントは技術的に発注できてしまう。**
> **PCBA / SMT 実装の発注が API に含まれるかは明記が無い**（PCB・ステンシル・3D プリント・部品のみ記載）。
> → **PCBA のカート準備はブラウザ経由が現実解。決済は絶対に押さない。**（§5-3 のガード構成を参照）

**ファイル命名**（https://jlcpcb.com/help/article/suggested-naming-patterns）:
`.GTL/.GBL`（外層）/ **`.G2L`/`.G3L`（4 層の内層）** / `.GTS/.GBS` / `.GTO/.GBO` / `.GKO` または `.GM1`（外形）/ `.XLN`（ドリル）。
「**Our site understands KiCAD's gerber naming patterns**」＝ KiCad 既定命名も自動認識される。
- **単一 zip（Gerber + ドリル）は受理される**
- ⚠ **PCBA では BOM と CPL は Gerber zip とは別にアップロードする**（zip に入れない）
- ドリルマップ / drill drawing の同梱を強く推奨

---

## 3. 検証ツール

### 3-1. 自前 stdlib 実装の難易度（正直な評価）

| チェック | 難易度 | 手口と罠 |
|---|---|---|
| **(a) ネット別接続性** | **易 ★☆☆☆☆** | X2 の `TO.N` でフラッシュにネットが直付け。集合比較だけ。**幾何演算ゼロ**。罠はスティッキー属性のみ（§0-2） |
| **(b) 異ネット銅箔の重なり / 最小クリアランス** | **難 ★★★★★** | 真面目にやると多角形ブーリアンが要る（shapely 無し）。**やらない。** KiCad DRC の `clearance` / `physical_clearance` に任せる |
| **(c) NPTH ドリル vs 銅箔** | **中 ★★☆☆☆** | **本命。** NPTH は円なので多角形不要。パッドは `.d356` から直接（§0-1）、トラックは Gerber の D01 を「線分＋線幅/2」のカプセル、フラッシュは「アパーチャ外接半径」で保守的に近似 → 距離計算。**保守側に倒れるので誤検出は出るが見逃さない** |
| **(d) Excellon パース** | **易 ★☆☆☆☆**（KiCad 出力に限れば） | 既定が `decimal` + `mm` で、ヘッダに `; FORMAT={-:-/ absolute / metric / decimal}`、座標は `X176.861Y-108.098`。**LZ/TZ 地獄は起きない。** ただしヘッダを必ず assert |
| **(e) アパーチャマクロ** | **中 ★★★☆☆**（実際は易） | **本基板に出る `%AM` は `RoundRect` 1 個だけ**。プリミティブは `4`(outline) / `1`(circle) / `20`(vector line) のみ。汎用マクロエンジン（式評価・`$1` 変数・回転）は大変だが、**「外接円半径だけ求める」なら全頂点/中心+半径の最大値で済む** |

**丸め誤差**: ドリル `X126.604Y-91.15`（3 桁）⇔ Gerber `Y-91150500`（= −91.1505）。
**±0.5 µm ずれるので突合トレランスは 1 µm 以上**にすること。
※ ACCEPTANCE D の「±2 µm 一致」はこの誤差を吸収できている。

**推奨実装順**: (a) → (c) → (d) の assert 群 → (b) はやらない。

### 3-2. `.kicad_dru` の落とし穴 3 つ 〔S7 で確認すべき〕

【一次: https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#custom_design_rules 】

1. **ルールは「逆順」に評価される。ファイル末尾のルールが最初に判定され、最初にマッチしたら以降は見ない。**
   → 具体的なルールほど**後ろ**に書く。
   現行 `Therapia_EEG-HRV.kicad_dru` は 3 ルール（`npth_hole_to_copper` / `track_to_track_5mil_preferred` / `via_annular_ring`）で
   条件が排他的なので**今は影響なし**。ルールを増やすときは順序を必ず意識すること。
2. **`(severity ignore)` はルールを無効化しない。** 効果だけ消え、マッチ判定は生きるので**前のルールを上書きし続ける**。
3. **公式は「`.kicad_dru` は KiCad が自動管理するファイルで、外部エディタで編集するな」と明記。**
   本件は `scripts/14_make_rules.py` で生成しているので、**生成後は必ず `kicad-cli pcb drc` を通して構文エラーが無いことを確認する**。
   **構文エラーがあると DRC 自体が走らない ＝ 静かに検査ゼロになる。**

**既知バグ〔重要〕**: `.kicad_dru` の `(severity exclusion)` は kicad-cli の JSON に `"excluded": true` が付かず、
**普通のエラーとして出る**（KiCad 9.0.7 / **10.0.1（macOS Sequoia）で再現**）。
GUI から `.kicad_pro` の `drc_exclusions` に入った除外は正しく機能する。
- https://gitlab.com/kicad/code/kicad/-/work_items/24264
- https://gitlab.com/kicad/code/kicad/-/issues/22079（`sch erc` が除外を無視）

→ **運用結論**: 「意図的に無視する違反」は `.kicad_dru` の `(severity exclusion)` に頼らず、
**CI 側で JSON をパースして期待違反リストと突き合わせる**方が堅い。**uuid は編集で変わるので基準にしない**
（ただし §0-3 のシグネチャ比較は「同一ボードの連続実行」なので uuid で正しい。用途が違う）。

### 3-3. ゾーンと `--refill-zones` 〔採用継続〕

ゾーンのフィルは `.kicad_pcb` に保存されたキャッシュ。編集後に refill されていないと
**「実際には短絡しているのに DRC が通る／その逆」が起きる**。
`copper_zones_intersect`（異ネットゾーン衝突＝短絡）/ `isolated_copper` / `connection_width` /
`min_resolved_spokes` はいずれも**フィル済みポリゴンに対する検査**。

**⚠ 注意**: ACCEPTANCE A は `--refill-zones --save-board` を掛けた後の基板で判定すると定めている。
これは **DRC が基板を書き換える**ことを意味する。**`--save-board` は S7 の指定箇所以外では禁止**にし、
gate JSON に「refill を掛けたか」と基板の SHA-256（実行前後）を記録すること。

### 3-4. ODB++ / IPC-2581 のクロスチェック 〔部分採用〕

`kicad-cli pcb export odb --compression none -o out/` の出力は**プレーン ASCII のディレクトリツリー**【実測】:
```
out/matrix/matrix                       ← 層構成（STEP/LAYER、CONTEXT/TYPE/POLARITY）
out/steps/pcb/netlists/cadnet/netlist   ← CAD ネットリスト（762 行）
out/steps/pcb/eda/data                  ← NET / PKG / PIN レコード（312 件）
out/steps/pcb/layers/<layer>/features   ← 幾何（計 52,533 行）
```
feature 形式は Gerber より素直（`$1 rect1100.0x600.0` ＝**シンボル名がそのまま寸法。アパーチャマクロ不要**）。

**ただし正直に言うと**: KiCad の ODB++ 出力では **feature にネット属性が付いていない**。
幾何 ↔ ネットの紐付けは `eda/data` の `SNT`/`FID` インデックス参照の解読が必要で、
**Gerber X2 の「行内に `%TO.N`」より明確に面倒**。

**判定**: ODB++ を「Gerber の代わり」にするメリットは薄い（KiCad 内部の同じ `BOARD` オブジェクトから吐かれる）。
**ただし `netlists/cadnet/netlist` と `matrix/matrix` を「メタデータの相互 assert」に使うのは安価で有効。**
3 経路が同じネット集合・層数・穴径を主張することの確認は、エクスポータのバグを捕まえる本物のチェックになる。

### 3-5. 業界の「CAD から独立した製造データ検証」の作法

CAM 側（CAM350 / Valor）の標準手順:
1. Gerber + ドリルを読む
2. **銅箔とめっきスルーホールの層間接続から「抽出ネットリスト」を機械的に再構築**
3. CAD が出した **IPC-D-356 ネットリストと比較**（netlist compare）
4. 差分＝「CAD → 製造データ変換で情報が壊れた」証拠

**これが fab が Gerber を受け取ったらまずやること**であり、ACCEPTANCE E が求めている独立検証そのもの。
§0-1 の IPC-D-356 採用は、この業界標準手順の入力側を無料で手に入れることに相当する。

### 3-6. `--schematic-parity` について

**本リポジトリには `.kicad_sch` が存在しない**（`find` で 0 件）ため、
`--schematic-parity` / `sch erc` / `sch export netlist` は**現状すべて使えない**。
実測した DRC JSON でも `"schematic_parity": []`（0 件）。

→ **現行の「EasyEDA API 由来の netlist を契約とする」方式は、この制約下では正しい選択。**
将来 KiCad 側に回路図を起こしたら、`--schematic-parity` を毎回付けて
`schematic_parity` 配列が非空なら即 FAIL にするのが最も安価な契約チェックになる。
パリティが検出するキー: `missing_footprint` / `extra_footprint` / `net_conflict` /
`footprint_symbol_mismatch` / `footprint_type_mismatch` / `duplicate_footprints` 他。

---

## 4. ADS1299 レイアウト指針

→ **`docs/ads1299_layout_checklist.md`** に分離。一次資料（TI SBAS499C 本文の verbatim 引用）ベース。

**この文書側での要点だけ**:
- **文献番号の訂正**: **SBAU204 は存在しない**（404）。ADS1299 EVM のユーザーガイドは **SLAU443B**。
  **TIDA-00175 / 00011 / 00376 はいずれも EEG ではない**（BiSS エンコーダ / 光学心拍 / 火災報知器）。
  **ADS129x を使いレイアウト節を持つ現行 TI Design は存在しない。**
- **TI は decoupling の距離を数値で示していない。**「as close as possible」だけ。**mm の数字を作らないこと。**
  数値で判定できるのは **「バイパスコンデンサと IC の間にビアを入れない」**（DS §12.1、幾何学的に判定可能）。
- 本リポジトリの STATUS.md が挙げている「C_VCAP3 pin1 が 3.36 mm」「C_VCAP1 が 2.50 mm 移動」は、
  **DS §12.1 の「ビアを挟むな」ルールで機械判定できる**。距離の閾値は TI が示していないので、
  ビアの有無と「同一層か」で判定するのが唯一の一次資料に忠実なやり方。

---

## 5. エージェント運用の安全策

### 5-1. この環境で実測された事故パターン

| # | 実測された事実 | 対策 |
|---|---|---|
| **1** | **DRC が非決定的**（490〜493）。生 JSON の diff もチェックサムも安定しない | §0-3 のシグネチャ集合比較。`clearance` は 2 回再現で確定 |
| **2** | **ボード単体コピーで DRC ルールが黙って default に落ちる**（490 → 1256） | §0-4。プロジェクトディレクトリで実行 |
| **3** | **`~Therapia_EEG-HRV.kicad_pro.lck` が残置**（KiCad GUI がプロジェクトを開いたまま）。さらに調査中に `board/*.kicad_pcb` の mtime が変化（別エージェントの書き込み）を観測 | ゲート冒頭で **`.lck` 存在チェック → あれば即 FAIL**。処理前後で board の SHA-256 を記録 |
| **4** | **`wxPoint` が KiCad 10 でも警告なしで動く** | 座標ヘルパ 1 本に集約。`wxPoint` と裸整数を hook で拒否 |
| **5** | `--exit-code-violations` の戻り値が **5** | `-ne 0` で判定 |
| **6** | **PIL / numpy が KiCad 同梱ではなくユーザ site-packages** | §0-7。stdlib + wx + pcbnew に縛る |
| **7** | `kicad-cli` がサンドボックス内で `Swift/SwiftNativeNSArray.swift:78: Fatal error`（exit 133）でクラッシュ。`dangerouslyDisableSandbox: true` で正常動作 | STATUS.md 既記載の「DRC を含むステップはサンドボックス外で実行」は正しい。hook からゲートを呼ぶ際も同様の注意が要る |

### 5-2. 学術・産業の知見から取るべきルール

**pcbGPT（arXiv 2606.01188, 2026-06-02）— 400 run 中 115 が非動作。人手ラベルによるエラー分類**:

| コード | 内容 | 比率 |
|---|---|---|
| **F1** | **補助部品の有無/種類の誤り** | **59.1%** |
| **F4** | インタフェース接続の誤り | 40.0% |
| **F2** | 補助部品の**値**の誤り | 33.9% |
| **F5** | ローカルトポロジの誤り | 27.0% |
| **F3** | 部品コンフィグの誤り | 22.6% |

同論文の重要な観測:
> **「約 12〜13 部品を超えると電気的一貫性を維持できなくなる」**
> 「電源ドメイン・インタフェース・サポート回路にまたがる同時判断が必要な複数サブシステム統合で精度を維持できない」
> 「レビュー可能な初稿は生成できるが、**専門家レビューを置き換えられるほど信頼できない**」

> **本件への直撃**: ADS1299 フロントエンドは「12 部品超・複数電源ドメイン・複数インタフェース」に完全に該当。
> **pcbGPT が「崩れる」と実証した領域そのもの。**
> → エージェントに任せる単位を **1 サブシステム / 12 部品程度**に切り、ゲートを間に挟む。
> → レビュー観点を **F1〜F5 にマップ**する（特に F1「補助部品の欠落」＝デカップリング/プルアップ/終端の抜けが最頻）。
> **ECO-1 の実体（VCAP2/VCAP3 のコンデンサ 4 個が PCB に無かった）はまさに F1 そのもの。**

**その他の一次情報**:
- **Altium Academy 2026**: 同じ回路図を人間と AI レイアウトツールに通した結果 → **人間 0 DRC violation、AI 168**
- **ProtoFlow（2026-06-06）**: 「**2026 年に describe-to-fab を端から端まで実現している信用できるツールは存在しない。全ステージに人間レビューが要る**」「**LLM を検証レイヤにするな**」（ルールチェックは決定論的、モデルは確率的）
- **JITX（2025 Q4 に Stanza → Python 移行、理由は明示的に「AI のコード生成のため」）**: 「**AI とチャットボットとして対話すると hallucinate しすぎる → コードという制約の中でだけ使う**」
- **Anthropic × Diode Computers（2026-03-30）**: 採点を「部品完全一致」ではなく **testbench 要件**（性質）で行った。Sonnet 4.5 がブラインド評価で 10 回中 8 回選好。→ **ゴールデンは厳密一致にせず、性質（property）で判定する**
- **Claude Code + KiCad チュートリアル（2026-01-17）**: 「**Claude はグラフィカルな出力を*見る*ことができない。下層のテキスト表現でしか作業していない**」
- **Promwad（2026-01-27）**: 失敗モードは「plausible but wrong」「コーナーケースの見落とし」「**model drift — ツールチェーン/ライブラリ変更で性能劣化**」

**stale read（TOCTOU）**: エージェントが read → プレビュー → 承認 → **再読み込みせずキャッシュ内容を書き込む**。
間の変更は黙って消える。Claude Code の Edit ツールは「会話内で read 済みのファイルしか編集できない」を実装しているが、
**Bash / Python 経由の書き込みには効かない**【推論】。`pcbnew` スクリプトで書く以上、**ハッシュ検証は自前で必要**。

### 5-3. 発注（不可逆）のガード 〔S9・最重要〕

業界コンセンサス:
> 「不可逆・高コスト・規制対象・影響半径が大きい —— 特にこれらが複数重なるとき、人間のチェックポイントに値する」
> 「エージェントは止まり、**アクションを下書きし**、人間が approve を押すまで金は動かない」
> 「タイムアウトではなく、**approver identity をログに残す耐久的な人間承認ゲート**」

**Anthropic 公式の見解**（https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more, 2026-06-18）:
> **「何かが絶対に起きてはならないとき、instruction は間違った道具だ。真のガードレールは決定論的でなければならず、その強制手段は hooks と permissions である。」**
> 「CLAUDE.md やスキルの中の『絶対に X するな』は*お願い*であって*保証*ではない。」

**推奨構成**:

| 層 | 実装 |
|---|---|
| **1. 資格情報を持たせない** | JLCPCB API キーをエージェントの環境から物理的に排除。`permissions.deny` に `Bash(*jlcpcb*)` / `WebFetch(domain:api.jlcpcb.com)`。**これが唯一の確実な防御** |
| **2. prepare-cart-but-don't-checkout** | 成果物は **`fab/order_manifest.json`**（Gerber パス・SHA-256・BOM・CPL・数量・層数・見積額）と **`fab/ORDER_README.md`**（人間が踏む手順）**まで**。カート投入もしない |
| **3. 人間署名ファイル** | `fab/APPROVED_BY.txt` に人間が **氏名 + 日付 + manifest の SHA-256** を書く。ゲートは manifest ハッシュ不一致なら FAIL（＝承認後に中身が変わったら無効） |
| **4. コスト上限** | manifest に `estimated_cost_usd`。閾値超は無条件 FAIL |
| **5. Hook で強制** | `PreToolUse`: matcher `Bash\|WebFetch`、コマンド/URL に `jlcpcb` / `checkout` / `pay` / `order` を含むなら **exit 2** で deny |
| **6. Skill 側** | 発注準備スキルは **`disable-model-invocation: true`**（公式が副作用ワークフローに明示推奨）。Claude が「準備ができたから」と自分で起動できなくなる |

⚠ 参考事例の kicad-happy `jlcpcb` スキルには**このガードが無い**（"Confirm and order" が手順にある）。**流用するなら発注ステップを削ること。**

---

## 6. Claude Code での固定化（Skill / hook 設計）

### 6-1. 何をどれで実装するか【一次: Anthropic 公式】

| 目的 | 使うもの | コンテキストコスト |
|---|---|---|
| 毎セッション必要な「必ず X しろ」 | **CLAUDE.md**（**200 行以内**） | 毎リクエスト全文 |
| パス限定の制約 | **`.claude/rules/`**（`paths` frontmatter） | 該当時のみ |
| 手続き・チェックリスト・参照資料 | **Skill** | 説明文のみ常駐、本文は起動時 |
| コンテキスト隔離・並列・専門ワーカー | **Subagent** | 分離 |
| **絶対に破らせない** | **Hook（+ permissions）** | **ゼロ** |

### 6-2. SKILL.md の実務仕様【一次: https://code.claude.com/docs/en/skills 】

frontmatter（全て optional。推奨は `description` のみ）で本件に効くもの:

| フィールド | 用途 |
|---|---|
| **`disable-model-invocation: true`** | **副作用のあるワークフローに必須**。ユーザーのみ起動可、説明文もコンテキストに載らない → **発注準備スキルはこれ** |
| **`paths`** | glob で自動ロードを限定。`board/**` を触るときだけロード |
| **`hooks`** | **skill 起動時に hook を登録し、以降セッション中ずっと動く** → **ステージ制パイプラインに最適** |
| `allowed-tools` | **そのターン中だけ**無承認で使えるツール。次のユーザーメッセージで失効。ツールを*制限*はしない |
| `disallowed-tools` | skill がアクティブな間、ツールプールから除去 |

**サイズと分割**:
- 公式 Tip: **「SKILL.md は 500 行以内に保て。詳細な参照資料は別ファイルへ」**
- **auto-compaction の予算**: 各 skill の**最新起動分の先頭 5,000 トークン**が要約後に再添付され、**合計 25,000 トークン**。
  最近起動したものから埋まる → **多数の skill を起動すると古いものは丸ごと落ちる。**
  **→ 長時間パイプラインでは、1 本の巨大 skill ではなくステージごとに skill を分ける。**
- レンダリング済み SKILL.md は**1 メッセージとして会話に入り、以降のターンも残る**。
  **Claude Code は後続ターンでファイルを再読しない。** → タスク全体に効かせたいことは常設の指示として書く

**`${CLAUDE_SKILL_DIR}` パターン**（ゲートスクリプト同梱に最適）:
```yaml
---
name: pcb-gate
description: Run the DRC/parity gate and write gate JSON
disable-model-invocation: true
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/gate.sh *)
---
Run `${CLAUDE_SKILL_DIR}/scripts/gate.sh <stage>`.
```
frontmatter と本文の**両方**で置換されるので、承認プロンプトなしでちょうどそのコマンドだけが通る。

**外部配布の制約**: claude.ai アップロード / Skills API では **`name, description, license, compatibility, metadata, allowed-tools` の 6 つしか使えず、他フィールドがあると hard error**。Claude Code 内だけなら全フィールド可。

### 6-3. Hook でガードレールを強制する【一次: https://code.claude.com/docs/en/hooks 】

- **exit 2 = ブロック**。「JSON を出そうが出すまいが exit 2 はブロックする。`permissionDecision: "allow"` でも上書きできない」
- `matcher`（ツール名）と `if`（パスパターン）の 2 段階
- ⚠ **`Edit(board/**)` は作業ディレクトリ直下の `board` にしかマッチしない。** 任意の深さなら `Edit(**/board/**)`

**本件の要件への直接マッピング**:

| 要件 | 実装 |
|---|---|
| 「repair ステップ以外で `board/*.kicad_pcb` を編集させない」 | `PreToolUse` / matcher `Edit\|Write` / `if: "Edit(board/**)"` → **ステージ状態ファイルを読み、該当ステージ以外なら exit 2** |
| **「Bash 経由の書き込みも塞ぐ」** | `matcher: "Bash"` で command を grep（`>`, `tee`, `cp`, `mv`, `--save-board`, `pcbnew.*Save`）。**Edit だけ塞いでも `KPY` スクリプトから書けるので必須** |
| 「書き込みのたびにゲートを走らせる」 | `PostToolUse` → gate スクリプト。出力はコンテキストに入るので Claude が読んで自己修正できる |
| 「ゲートが通るまでターンを終わらせない」 | **`Stop` hook**。ただし**8 回連続ブロックで Claude Code が上書きして終了する**ので、最終判定を Stop hook だけに頼らない |
| 「single writer を機械的に保証」 | `PreToolUse` で board の SHA-256 と所有者を照合。**`.lck` があれば deny** |

### 6-4. 本件のパイプラインに対する推奨分割【推論】

```
CLAUDE.md (<200行)      : 「ボードは repair ステージでのみ編集」「単位は nm」「ゲートを通さず commit しない」
.claude/rules/board.md  : paths: board/**  → wxPoint 禁止、裸整数座標禁止、--save-board は S7 のみ
.claude/skills/
  pcb-gate/             : disable-model-invocation: true
    SKILL.md (<500行)   : ゲートの契約 + Minimum Checklist + Failure Modes (F1〜F5)
    references/drc.md   : シグネチャ設計、type 一覧、既知の flap（clearance）
    references/units.md : nm / VECTOR2I / 変換ヘルパ
    scripts/gate.sh
  pcb-repair/           : L1〜L6。frontmatter の hooks で「このステージ中だけ board 編集を許可」を登録
  pcb-fab/              : S8。Gerber/BOM/CPL 出力 + 独立パーサ検査
  pcb-order-prep/       : S9。disable-model-invocation: true 必須
.claude/agents/
  pcb-verifier.md       : tools: Read, Grep, Glob, Bash(gate.sh)  ← 書き込み権限なし
.claude/settings.json   : PreToolUse(board/** deny outside repair) / PostToolUse(gate) / Stop(gate)
```

**設計理由**:
- **ステージごとに skill を分ける** → §6-2 の compaction 予算（各 5k / 合計 25k）に収まる。1 本の巨大 skill は compaction で落ちる
- **`hooks` frontmatter** でステージ入場時に guardrail を登録すれば、「今どのステージか」を**モデルの記憶ではなく hook が持つ**
- **verifier は書き込みツールを持たない subagent**（Anthropic 公式の adversarial review パターン）。**作った本人に採点させない**
  - 公式の注意: 「gap を探せと言われたレビュアーは、健全な成果物に対しても必ず何か報告する。**正しさか明示要件に影響する gap だけ**を挙げさせろ」

### 6-5. 現行流儀への具体的な補正提案

現行設計（file-based / commit per step / JSON gate / netlist contract / single writer）は**文献と完全に整合している**。
追加すべきは以下:

| # | 追加 | 根拠 |
|---|---|---|
| **A1** | DRC 比較は `(type, sorted(uuid))` の**集合差分**。カウント・生 JSON diff・チェックサムは使わない | §0-3【実測】 |
| **A2** | `clearance` 型の新規シグネチャは**2 回再現で確定** | §0-3【実測】flap 7/495 は全て clearance |
| **A3** | gate JSON に必ず入れる: board の SHA-256（実行**前後**）、`kicad_version`、`PCB_IU_PER_MM`、`ignored_checks`、`.lck` 有無、git commit SHA | §0-3/0-4/5-1 |
| **A4** | **`ignored_checks` をゲートで検証**。ACCEPTANCE が定めた 5 種**以外**が ignore されていたら FAIL | 【実測】現状 8 種が ignore（ACCEPTANCE の 5 種 ＋ `footprint_filters_mismatch` / `track_not_centered_on_via` / `tuning_profile_track_geometries`）。**差分を明示的に承認すること** |
| **A5** | DRC は**必ずプロジェクトディレクトリで実行**。ボード単体コピー禁止 | §0-4【実測】 |
| **A6** | **`--refill-zones` の有無を固定**し gate JSON に記録。**`--save-board` は S7 の指定箇所以外で禁止** | §3-3 |
| **A7** | ライブラリ固定は**絶対パス**で。KiCad 10 は環境変数展開にリグレッションあり（issue #24244） | 【一次】 |
| **A8** | **ゴールデンは「バイト一致」ではなく「性質」で持つ**。契約は「ネットとピンの集合」、DRC は「シグネチャ集合」、寸法は「許容範囲」 | Anthropic × Diode |
| **A9** | **同一入力で 2 回連続 run し、gate 結果が一致することをゲート自身が検査**（idempotency self-check） | §0-3 |
| **A10** | 単位変換は `mm()` ヘルパ 1 本に集約。`wxPoint` と裸整数座標を hook で禁止 | §5-1【実測】 |

**`ignored_checks` について補足**: ACCEPTANCE C の「ignore にする種別」は
`lib_footprint_issues` / `lib_footprint_mismatch` / `missing_courtyard` / `pth_inside_courtyard` / `npth_inside_courtyard` の 5 種で、
**理由（フットプリントライブラリ未紐付け、S2 で 17/17 一致済み）も明記されている**ので判断としては妥当。
ただし `lib_footprint_mismatch` は**ライブラリドリフト検出そのもの**なので、
「この基板はライブラリを参照しない自己完結データである」ことを gate JSON に明示的に記録しておくこと。

---

## 7. 出典

**Anthropic 公式**
- Skills: https://code.claude.com/docs/en/skills
- Hooks: https://code.claude.com/docs/en/hooks
- Best practices: https://code.claude.com/docs/en/best-practices
- Verification loops（2026-07-22）: https://claude.com/blog/building-verification-loops-in-claude-code-with-skills
- Steering Claude Code（2026-06-18）: https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more
- Claude × Diode PCB（2026-03-30）: https://www.gend.co/blog/enhancing-claude-pcb-design-skills

**KiCad**
- CLI: https://docs.kicad.org/10.0/en/cli/cli.html
- カスタムデザインルール: https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html#custom_design_rules
- API/バインディング（SWIG 廃止予定）: https://dev-docs.kicad.org/en/apis-and-binding/pcbnew/index.html
- DRC JSON schema: https://gitlab.com/kicad/code/kicad/-/raw/master/resources/schemas/drc.v1.json
- 除外バグ #24264: https://gitlab.com/kicad/code/kicad/-/work_items/24264 / ERC 版 #22079: https://gitlab.com/kicad/code/kicad/-/issues/22079
- 環境変数バグ #24244: https://gitlab.com/kicad/code/kicad/-/work_items/24244

**Gerber / 検証**
- Gerber X3 仕様 Rev. 2026.05（Ucamco）: https://www.ucamco.com/files/downloads/file_en/554/gerber-layer-format-specification-revision-2026-05_en.pdf
- IPC-D-356 フォーマット: https://manual.pcb-investigator.com/posts/02-ipcd
- Altium KB（IPC-D-356A と抽出ネットリストの比較）: https://www.altium.com/documentation/knowledge-base/altium-designer/generate-ipc-d-356a-document-and-compare-to-extracted-netlist

**JLCPCB**
- KiCad からの BOM/CPL 生成（2026-08-27 更新）: https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad
- PCB capabilities: https://jlcpcb.com/capabilities/pcb-capabilities
- インピーダンス制御スタックアップ: https://jlcpcb.com/impedance
- PCBA 価格: https://jlcpcb.com/help/article/pcb-assembly-price
- 部品確認（PCBA FAQ part 2）: https://jlcpcb.com/help/article/pcb-assembly-faqs-part-2
- 極性・pin1 判定ガイド: https://jlcpcb.com/help/article/component-polarity-and-orientation-identification-guide
- ファイル命名: https://jlcpcb.com/help/article/suggested-naming-patterns
- 公式 API（2026-03-25 更新）: https://jlcpcb.com/help/article/jlcpcb-online-api-available-now / https://api.jlcpcb.com/
- DFM: https://jlcdfm.com/viewer

**ツール**
- kicad-happy: https://github.com/aklofas/kicad-happy
- Fabrication Toolkit: https://github.com/bennymeg/Fabrication-Toolkit
- Bouni/kicad-jlcpcb-tools: https://github.com/Bouni/kicad-jlcpcb-tools
- 回転 DB（生ファイル）: https://raw.githubusercontent.com/matthewlai/JLCKicadTools/master/jlc_kicad_tools/cpl_rotations_db.csv
- kicad-druid: https://github.com/Cimos/kicad-druid
- Konnect: https://github.com/mixelpixx/Konnect
- InteractiveHtmlBom: https://github.com/openscopeproject/InteractiveHtmlBom
- Basic/Preferred 部品 CSV（週次）: https://lrks.github.io/jlcpcb-economic-parts/

**論文・記事**
- pcbGPT（2026-06-02）: https://arxiv.org/abs/2606.01188
- PCB-QA（2026-06-24）: https://arxiv.org/abs/2606.23704
- GenAI in PCB survey（2026-06-17）: https://arxiv.org/abs/2606.17074
- ProtoFlow「Real vs Hype」（2026-06-06）: https://www.protoflow.ai/blog/ai-pcb-design-2026-guide
- Claude Code + KiCad（2026-01-17）: https://yuan.fyi/blog/using-claude-code-for-kicad-pcb-design/
- JLCPCB 実務 tips（2025-07-05）: https://blog.poly.nomial.co.uk/2025-07-05-tips-for-getting-pcbs-made-with-jlcpcb.html
