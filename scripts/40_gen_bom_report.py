#!/usr/bin/env python3
"""BOM 実体照合レポート生成（Web 一次情報の取得結果を正として MD/JSON を出力）.

取得日: 2026-08-28
出典:
  LCSC   = https://www.lcsc.com/product-detail/<C番号>.html
  EDA    = https://easyeda.com/api/products/<C番号>/components
  JLC    = https://jlcpcb.com/partdetail/<C番号>
"""
import csv
import collections
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FETCHED = "2026-08-28"

LCSC = "https://www.lcsc.com/product-detail/{}.html"
EDA = "https://easyeda.com/api/products/{}/components"
JLC = "https://jlcpcb.com/partdetail/{}"

# lcsc -> 取得した実体（Web 一次情報のみ。推測は入れない）
FACTS = {
    "C6186": dict(
        mpn="AMS1117-3.3", mfr="Advanced Monolithic Systems",
        pkg="SOT-223-3_L6.5-W3.4-P2.30-LS7.0-BR",
        spec="LDO 3.3V fixed, SOT-223-3",
        cls="Basic", stock_lcsc=222228, stock_sz=113340, jlc_onsale=True,
        src=[EDA, JLC]),
    "C19702": dict(
        mpn="CL10A106KP8NNNC", mfr="Samsung Electro-Mechanics", pkg="C0603",
        spec="10uF / 10V / X5R / +-10% / 0603",
        cls="Basic", stock_lcsc=6738300, stock_sz=0, jlc_onsale=True,
        note="LCSC ページ 6,738,300 / EasyEDA API 225,880（SZ 0）。値は両者一致。",
        src=[LCSC, EDA]),
    "C1525": dict(
        mpn="CL05B104KO5NNNC", mfr="Samsung Electro-Mechanics", pkg="C0402",
        spec="100nF / 16V / X7R / +-10% / 0402",
        cls="Basic", stock_lcsc=869375, stock_sz=4941800, jlc_onsale=True,
        src=[EDA]),
    "C52923": dict(
        mpn="CL05A105KA5NQNC", mfr="Samsung Electro-Mechanics", pkg="C0402",
        spec="1uF / 25V / X5R / +-10% / 0402",
        cls="Basic", stock_lcsc=3790400, stock_sz=3663900, jlc_onsale=True,
        note="定格 25V は LCSC ページと EasyEDA API の 2 ソースで一致。",
        src=[LCSC, EDA]),
    "C1546": dict(
        mpn="0402CG101J500NT", mfr="FH (Fenghua)", pkg="C0402",
        spec="100pF / 50V / C0G(NP0, 型番 CG) / +-5% / 0402",
        cls="Basic", stock_lcsc=558700, stock_sz=1401500, jlc_onsale=True,
        src=[EDA]),
    "C1588": dict(
        mpn="CL10B102KB8NNNC", mfr="Samsung Electro-Mechanics", pkg="C0603",
        spec="1nF / 50V / X7R(型番 B) / +-10% / 0603",
        cls="Basic", stock_lcsc=673512, stock_sz=123000, jlc_onsale=True,
        src=[EDA]),
    "C237168": dict(
        mpn="0805N103J500CT", mfr="Walsin", pkg="C0805",
        spec="10nF / 50V / NP0 / +-5% / 0805",
        cls="Extended", stock_lcsc=152260, stock_sz=5820, jlc_onsale=True,
        note="LCSC ページ 152,260 / EasyEDA API 9,790。API の Voltage Rated 500V は "
             "型番 '...J500CT' の誤パース、LCSC ページの 50V を採用。",
        src=[LCSC, EDA]),
    "C12530": dict(
        mpn="CL05A225MQ5NSNC", mfr="Samsung Electro-Mechanics", pkg="C0402",
        spec="2.2uF / 6.3V / X5R / +-20% / 0402",
        cls="Basic", stock_lcsc=5406800, stock_sz=282800, jlc_onsale=True,
        note="LCSC ページ 5,406,800 / EasyEDA API 0（SZ 282,800）。",
        src=[LCSC, EDA]),
    "C15195": dict(
        mpn="CL05B103KB5NNNC", mfr="Samsung Electro-Mechanics", pkg="C0402",
        spec="10nF / 50V / X7R / +-10% / 0402",
        cls="Basic", stock_lcsc=4411600, stock_sz=266400, jlc_onsale=True,
        note="LCSC ページ 4,411,600 / EasyEDA API 230（SZ 266,400）。",
        src=[LCSC, EDA]),
    "C15008": dict(
        mpn="CL31A107MQHNNNE", mfr="Samsung Electro-Mechanics", pkg="C1206",
        spec="100uF / 6.3V / X5R / +-20% / 1206",
        cls="Basic", stock_lcsc=2054820, stock_sz=107937, jlc_onsale=True,
        note="LCSC ページ 2,054,820 / EasyEDA API 0（SZ 107,937）。",
        src=[LCSC, EDA]),
    "C13585": dict(
        mpn="CL31A106KBHNNNE", mfr="Samsung Electro-Mechanics", pkg="C1206",
        spec="10uF / 50V / X5R / +-10% / 1206",
        cls="Basic", stock_lcsc=917300, stock_sz=0, jlc_onsale=None,
        note="CSV の MPN 'CL31A106KAHNNNE' は誤り。LCSC ページ・JLC partdetail・"
             "EasyEDA API の 3 ソースとも 'CL31A106K**B**HNNNE / 50V'。"
             "在庫は LCSC ページ 917,300 に対し EasyEDA API 0/0 で食い違う。",
        src=[LCSC, JLC, EDA]),
    "C7519": dict(
        mpn="USBLC6-2SC6", mfr="STMicroelectronics",
        pkg="SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL",
        spec="USB ESD 保護ダイオードアレイ, SOT-23-6",
        cls="Extended", stock_lcsc=28668, stock_sz=3590, jlc_onsale=True,
        src=[EDA]),
    "C72043": dict(
        mpn="19-217/GHC-YR1S2/3T", mfr="Everlight Elec", pkg="LED0603-RD",
        spec="LED 0603 / Emerald Green(518nm) / Vf 3.3V @20mA / 199mcd",
        cls="取得不能", stock_lcsc=54300, stock_sz=1440000, jlc_onsale=True,
        note="色（緑）と Vf 3.3V は LCSC ページ・JLC partdetail の 2 ソースで一致。"
             "JLC 実装区分は 3 URL とも表示されず取得不能。",
        src=[LCSC, JLC, EDA]),
    "C369159": dict(
        mpn="JK-NSMD050-13.2V", mfr="JK (Jinrui)", pkg="F1206",
        spec="PPTC リセッタブルヒューズ / hold 500mA / trip 1A / 13.2V / 1206",
        cls="Extended", stock_lcsc=6160, stock_sz=53060, jlc_onsale=True,
        note="LCSC 商品ページは 'Not available now'。EasyEDA API は 6,160/53,060。",
        src=[LCSC, EDA]),
    "C94221": dict(
        mpn="取得不能（部品が存在しない）", mfr="-", pkg="-",
        spec="-",
        cls="存在しない", stock_lcsc=None, stock_sz=None, jlc_onsale=False,
        note="LCSC 商品ページ HTTP 404 / EasyEDA API 'Component not found' 404 / "
             "JLC partdetail は空欄（No specifications available）。3 ソースとも不存在。"
             "CSV が意図した GZ2012D601TF の正しい品番は C1017。",
        src=[LCSC, EDA, JLC]),
    "C2765186": dict(
        mpn="TYPE-C 16PIN 2MD(073)", mfr="SHOU HAN",
        pkg="USB-C-SMD_TYPE-C-16PIN-2MD-073",
        spec="USB Type-C レセプタクル 16P / SMD + 位置決めペグ / 5V 5A",
        cls="Extended", stock_lcsc=940940, stock_sz=None, jlc_onsale=True,
        note="EasyEDA 側パッケージ名は '16PIN'、KiCad 側は '6PIN'（変換時の名称欠落）。"
             "パッド実体は 12 SMD + 4 TH シェルの 16 パッドで正しい。",
        src=[LCSC, EDA]),
    "C2840012": dict(
        mpn="PZ254V-11-12P", mfr="XFCN", pkg="HDR-TH_12P-P2.54-V-M",
        spec="ピンヘッダ 1 列 x 12P / 2.54mm / スルーホール垂直 / 250V 3A",
        cls="Extended", stock_lcsc=28720, stock_sz=None, jlc_onsale=True,
        note="1 列 12 ピン（2x6 ではない）。LCSC ページ・EasyEDA API とも row=1。",
        src=[LCSC, EDA]),
    "C108573": dict(
        mpn="LM2664M6X/NOPB", mfr="Texas Instruments",
        pkg="SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BR",
        spec="スイッチトキャパシタ電圧反転 / 1.8-5.5V in / 40mA / SOT-23-6",
        cls="Extended", stock_lcsc=49955, stock_sz=1620, jlc_onsale=True,
        note="LCSC ページ 49,955 / EasyEDA API 0（SZ 1,620）。",
        src=[LCSC, EDA]),
    "C2146": dict(
        mpn="S8050 J3Y(RANGE:200-350)", mfr="CJ (Changjiang)",
        pkg="SOT-23-3_L3.0-W1.7-P0.95-LS2.9-BR",
        spec="NPN トランジスタ / hFE 200-350 / SOT-23-3",
        cls="Basic", stock_lcsc=451617, stock_sz=508750, jlc_onsale=True,
        src=[EDA]),
    "C17514": dict(
        mpn="0805W8F1004T5E", mfr="UNI-ROYAL", pkg="R0805",
        spec="1MΩ / +-1% / 0805",
        cls="Basic", stock_lcsc=203700, stock_sz=872900, jlc_onsale=True,
        src=[EDA]),
    "C23186": dict(
        mpn="0603WAF5101T5E", mfr="UNI-ROYAL", pkg="R0603",
        spec="5.1kΩ / +-1% / 0603",
        cls="Basic", stock_lcsc=897098, stock_sz=1796800, jlc_onsale=True,
        src=[EDA]),
    "C25804": dict(
        mpn="0603WAF1002T5E", mfr="UNI-ROYAL", pkg="R0603",
        spec="10kΩ / +-1% / 0603",
        cls="Basic", stock_lcsc=8999650, stock_sz=0, jlc_onsale=True,
        src=[EDA]),
    "C25744": dict(
        mpn="0402WGF1002TCE", mfr="UNI-ROYAL", pkg="R0402",
        spec="10kΩ / +-1% / 0402",
        cls="Basic", stock_lcsc=235900, stock_sz=2745500, jlc_onsale=True,
        src=[EDA]),
    "C23138": dict(
        mpn="0603WAF3300T5E", mfr="UNI-ROYAL", pkg="R0603",
        spec="330Ω / +-1% / 0603",
        cls="Basic", stock_lcsc=470600, stock_sz=359100, jlc_onsale=True,
        src=[EDA]),
    "C17477": dict(
        mpn="0805W8F0000T5E", mfr="UNI-ROYAL", pkg="R0805",
        spec="0Ω ジャンパ / 0805",
        cls="Basic", stock_lcsc=433289, stock_sz=2148400, jlc_onsale=True,
        src=[EDA]),
    "C19619": dict(
        mpn="TLV70025DDCR", mfr="Texas Instruments",
        pkg="SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR",
        spec="LDO +2.5V 固定 / 200mA / SOT-23-5(TI DDC)",
        cls="Extended", stock_lcsc=2186, stock_sz=1577, jlc_onsale=True,
        note="LCSC ページ 1,480 / EasyEDA API 2,186（SZ 1,577）。"
             "CSV の package 'SOT-353' は誤りで実体は SOT-23-5。",
        src=[LCSC, EDA]),
    "C69932": dict(
        mpn="TPS72325DBVR", mfr="Texas Instruments",
        pkg="SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR",
        spec="負電圧 LDO -2.5V / 200mA / 超低ノイズ 60uVrms / SOT-23-5",
        cls="Extended", stock_lcsc=7086, stock_sz=3843, jlc_onsale=True,
        note="LCSC ページ 7,086 / EasyEDA API 0（SZ 3,843）。",
        src=[LCSC, EDA]),
    "C476817": dict(
        mpn="ADS1299IPAGR", mfr="Texas Instruments",
        pkg="TQFP-64_L10.0-W10.0-P0.50-LS12.0-TL",
        spec="24bit 8ch 生体電位 AFE / TQFP-64(10x10) / MSL3 / $60.31",
        cls="Extended", stock_lcsc=3126, stock_sz=None, jlc_onsale=True,
        src=[LCSC, JLC, EDA]),
    "C701341": dict(
        mpn="ESP32-WROOM-32E-N4", mfr="Espressif",
        pkg="WIFI-SMD_ESP32-WROOM-32E",
        spec="ESP32 モジュール 4MB flash / SMD 25.5x18mm",
        cls="Extended", stock_lcsc=29577, stock_sz=916, jlc_onsale=True,
        note="LCSC ページ 29,577 / EasyEDA API 6（SZ 916）。乖離が大きく要カート確認。",
        src=[LCSC, EDA]),
    "C84681": dict(
        mpn="CH340C", mfr="WCH", pkg="SOP-16_L10.0-W3.9-P1.27-LS6.0-BL",
        spec="USB-UART ブリッジ / 内蔵クロック（水晶不要）/ SOP-16",
        cls="Extended", stock_lcsc=61409, stock_sz=63893, jlc_onsale=True,
        note="LCSC ページ 61,409 / EasyEDA API 17,584（SZ 63,893）。",
        src=[LCSC, EDA]),
    # --- 推奨代替（現 BOM には無い） ---
    "C1017": dict(
        mpn="GZ2012D601TF", mfr="Sunlord", pkg="L0805",
        spec="フェライトビーズ 600Ω@100MHz +-25% / 定格 500mA / DCR 300mΩ / 0805",
        cls="Basic", stock_lcsc=75200, stock_sz=68250, jlc_onsale=True,
        note="C94221 が意図していた GZ2012D601TF の正しい品番。"
             "EasyEDA パッケージ名 'L0805' は KiCad 側フットプリントと完全一致。",
        src=[JLC, EDA]),
    "C2286": dict(
        mpn="KT-0603R", mfr="Hubei KENTO Elec", pkg="LED-SMD_L1.6-W0.8-R-RD",
        spec="LED 0603 / 赤 645nm / Vf 1.8-2.4V @20mA / If max 25mA",
        cls="Basic", stock_lcsc=624750, stock_sz=0, jlc_onsale=True,
        note="D_LED の代替候補。3.3V 駆動 + 330Ω で約 3.9mA 流れる。",
        src=[JLC, EDA]),
    "C883122": dict(
        mpn="BSMD1206-050-6V", mfr="BHFUSE", pkg="F1206",
        spec="PPTC リセッタブルヒューズ hold 500mA / 6V / 1206",
        cls="Extended", stock_lcsc=3420, stock_sz=2940, jlc_onsale=True,
        note="F1 の同一フットプリント代替。定格電圧は 13.2V→6V に下がる点に注意。",
        src=[JLC, EDA]),
}

# lcsc -> (verdict, 設計意図, 判定理由)
JUDGE = {
    "C6186": ("OK", "AMS1117-3.3 / SOT-223 / USB5V→3.3V",
              "MPN・パッケージ・機能すべて一致。フットプリント SOT-223-3(4パッド) 一致。"),
    "C19702": ("OK", "ECO-2#10: 10uF 10V X5R 0603（12個スイープ）",
               "10uF/10V/X5R/0603 が ECO 指定と完全一致。実接続ネットの最大は USB_5V(5V)/"
               "VNEG5(-5V)/LM フライングキャップ(約5V)で 10V 定格に収まる。"),
    "C1525": ("OK", "100nF 0402（HF デカップ全般）",
              "100nF/0402 一致。定格 16V。最大電位は USB_5V(5V) 系なので 3 倍以上の余裕。"),
    "C52923": ("OK", "1uF 0402（LDO 入出力・VCAP2/3/4）",
               "1uF/0402 一致。定格 25V は USB_5V(5V) 系・V_NLDO_IN(-5V) に対し十分。"),
    "C1546": ("要確認", "designator は C_AVDD1_10n / C_VREFP_10n（= 10nF を示唆）",
              "実体は 100pF C0G。ECO-2#7 が C_NR で修正したのと同型の "
              "『名前は 10n・中身は 100pF』の不整合が 2 個所残っている。"
              "AVDD/VREFP には別途 100nF+10uF が並列なので実害は小さいが意図確認を推奨。"),
    "C1588": ("OK", "C_CM 1nF 0603（ECO で X7R 継続を明示的に受容）",
              "1nF/50V/X7R/0603 一致。ECO『意図的に見送り』欄で Rev.A 受容と明記済み。"),
    "C237168": ("OK", "ECO-2#6: 10nF ±5% 50V NP0 0805（C_DIF、NP0 必須）",
                "10nF/50V/NP0/±5%/0805 が ECO 指定と完全一致。C_DIF の NP0 要件を満たす。"),
    "C12530": ("OK", "ECO-2#8: 2.2uF 6.3V X5R 0402（C_NLDO_OUT）",
               "2.2uF/6.3V/X5R/0402 一致。AVSS(-2.5V) に対し 6.3V は 2.5 倍の余裕。"),
    "C15195": ("OK", "ECO-2#7: 10nF X7R 0402（C_NR）",
               "10nF/50V/X7R/0402 一致。TPS_NR ノードは低電圧なので定格十分。"),
    "C15008": ("OK", "ECO-3#11: 100uF 6.3V X5R 1206（C_VCAP1）",
               "100uF/6.3V/X5R/1206 一致。VCAP1-AVSS 間の最大は VREFP=4.5V 相当で 6.3V に収まる"
               "（設計意図でも 6.3V 可と明記）。"),
    "C13585": ("要確認", "ECO-3#12: 10uF 1206 25V（VREFP=4.5V の DC バイアス減衰対策）",
               "【裏取り完了】実体は CL31A106K**B**HNNNE = 10uF **50V** X5R 1206。"
               "CSV の MPN 'CL31A106KAHNNNE' は誤り。値・パッケージ・材質は意図を満たし、"
               "50V なので 25V 品より DC バイアス減衰が小さく設計上はむしろ良好。"
               "→ C15008 での代替は不要。BOM の MPN 文字列のみ訂正。"),
    "C7519": ("OK", "USBLC6-2SC6 / SOT-23-6 / USB ESD 保護",
              "MPN・パッケージ一致。EasyEDA パッケージ名が KiCad フットプリント名と完全一致。"),
    "C72043": ("NG", "value='LED_Y'（黄）+ R_LED 330Ω で ESP32 GPIO(3.3V) から駆動",
               "実体は Emerald Green・**Vf 3.3V**。3.3V GPIO − Vf3.3V = 0V となり "
               "330Ω では電流がほぼ流れず点灯しない/極端に暗い。"
               "また BOM value 'LED_Y'（黄）と実体（緑）が不一致。"
               "ECO-2#9 で 10kΩ→330Ω に変えた前提は Vf≈2V の赤/黄 LED。"),
    "C369159": ("要確認", "Polyfuse hold 500mA / 1206（USB_VBUS_RAW→USB_5V）",
                "仕様（500mA hold / 1206）は意図と一致し F1206 フットプリントとも整合。"
                "ただし LCSC 商品ページが 'Not available now' 表示で在庫要確認。"),
    "C94221": ("NG", "FB_600R 600Ω@100MHz フェライトビーズ 0805 x5",
               "**この C 番号は LCSC/JLC に存在しない**（3 ソースで不存在を確認）。"
               "このまま発注すると JLC 側で部品が引けない。正しい品番は C1017。"),
    "C2765186": ("OK", "USB-C 16P 2MD(073) レセプタクル",
                 "MPN 一致。KiCad フットプリントのパッド実体は 12 SMD(0.5mm ピッチ) + "
                 "4 TH シェルタブ = 16 パッドで 16P 品として正しい。"
                 "フットプリント名の '6PIN' は変換時の名称欠落で実害なし。"
                 "ピン割当も EasyEDA シンボルの pinName（GND/VBUS/SBU2/CC1/DN2/DP1/DN1/DP2/"
                 "SBU1/CC2/VBUS/GND/SHELL）と netlist が一致。"),
    "C2840012": ("要確認", "CSV value='Header_2x6' / package='HDR-2.54-2x6'",
                 "実体は **1 列 x 12 ピン**（row=1）。PCB フットプリント "
                 "HDR-TH_12P-P2.54-V-M も 12 パッド全て y=0 の 1 列なので"
                 "**部品と基板は整合**。CSV のラベル表記のみ誤り。"),
    "C108573": ("OK", "LM2664 チャージポンプ / SOT-23-6",
                "MPN・パッケージ一致。EasyEDA パッケージ名が KiCad フットプリント名と完全一致。"),
    "C2146": ("OK", "S8050 NPN / SOT-23-3（EN・IO0 の自動書込回路）",
              "MPN・パッケージ一致。"),
    "C17514": ("OK", "1MΩ 0805（BIAS 帰還・直列）", "抵抗値・パッケージ一致。"),
    "C23186": ("OK", "5.1kΩ 0603（USB-C CC プルダウン、UFP 宣言）",
               "抵抗値・パッケージ一致。CC1/CC2 → GND 接続を netlist で確認。"),
    "C25804": ("OK", "10kΩ 0603（プルアップ/ダウン群）", "抵抗値・パッケージ一致。"),
    "C25744": ("OK", "10kΩ 0402（電極入力直列 R_IN*）", "抵抗値・パッケージ一致。"),
    "C23138": ("OK", "ECO-2#9: 330Ω 0603（R_LED）",
               "330Ω/0603 が ECO 指定と一致。ただし直列の D_LED 側に問題あり（C72043 参照）。"),
    "C17477": ("OK", "0Ω 0805（SPI 直列ジャンパ・SRB 直列）", "抵抗値・パッケージ一致。"),
    "C19619": ("要確認", "TLV70025 +2.5V LDO / CSV package='SOT-353'",
               "実体は SOT-23-5（TI DDC パッケージ）。PCB フットプリントは "
               "SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR で **正しい**（EasyEDA パッケージ名と完全一致）。"
               "CSV の 'SOT-353' 表記のみ誤り。在庫 1,480-2,186 でやや薄い。"),
    "C69932": ("要確認", "TPS72325 -2.5V LDO / SOT-23-5",
               "MPN・パッケージ一致（EasyEDA パッケージ名が KiCad と完全一致）。"
               "LCSC 在庫 0（SZ 3,843）で在庫リスクあり。"),
    "C476817": ("OK", "ADS1299IPAGR / TQFP-64",
                "MPN・パッケージ一致。KiCad フットプリント 64 パッド（サーマルパッド無し）は "
                "PAG パッケージの実体と整合。Extended かつ $60/個。"),
    "C701341": ("要確認", "ESP32-WROOM-32E-N4 / SMD モジュール",
                "MPN・パッケージ一致（47 パッド = 38 ピン + サーマル 9 分割）。"
                "在庫が LCSC ページ 29,577 と EasyEDA API 6 で大きく乖離。要カート確認。"),
    "C84681": ("OK", "CH340C / SOP-16",
               "MPN・パッケージ一致。EasyEDA パッケージ名が KiCad フットプリント名と完全一致。"),
}

# 在庫リスク → 代替案
ALTS = {
    "C94221": ["C1017"],
    "C72043": ["C2286"],
    "C369159": ["C883122"],
}


def main():
    rows = [r for r in csv.DictReader(open(os.path.join(ROOT, "data/parts_lcsc.csv")))
            if r.get("designator")]
    grp = collections.OrderedDict()
    for r in rows:
        grp.setdefault(r["lcsc"], []).append(r)

    # PCB に実在する designator
    nl = json.load(open(os.path.join(ROOT, "contract/netlist_from_kicad_pcb.json")))
    on_pcb = set(p["ref"] for p in nl["pads"])

    out = []
    for lcsc, items in grp.items():
        f = FACTS[lcsc]
        verdict, intent, reason = JUDGE[lcsc]
        des = [i["designator"] for i in items]
        missing = [d for d in des if d not in on_pcb]
        rec = dict(
            lcsc=lcsc,
            designators=des,
            qty=len(des),
            csv_value=items[0]["value"],
            csv_mpn=items[0]["mpn"],
            csv_package=items[0]["package"],
            kicad_footprint=(items[0]["kicad_footprint"]
                             or "ProPrj_The-easyedapro:" + items[0]["easyeda_footprint"]),
            eco=sorted(set(i["eco"] for i in items if i["eco"])),
            fetched_mpn=f["mpn"],
            fetched_manufacturer=f["mfr"],
            fetched_package=f["pkg"],
            fetched_spec=f["spec"],
            jlc_part_class=f["cls"],
            jlc_on_sale=f["jlc_onsale"],
            stock_lcsc=f["stock_lcsc"],
            stock_szlcsc=f["stock_sz"],
            design_intent=intent,
            verdict=verdict,
            reason=reason,
            note=f.get("note"),
            not_placed_on_pcb=missing,
            alternatives=[dict(lcsc=a, mpn=FACTS[a]["mpn"], pkg=FACTS[a]["pkg"],
                               spec=FACTS[a]["spec"], jlc_part_class=FACTS[a]["cls"],
                               stock_lcsc=FACTS[a]["stock_lcsc"],
                               note=FACTS[a].get("note"),
                               source_urls=[u.format(a) for u in FACTS[a]["src"]])
                          for a in ALTS.get(lcsc, [])],
            source_urls=[u.format(lcsc) for u in f["src"]],
        )
        out.append(rec)

    doc = dict(
        generated=FETCHED,
        board="board/Therapia_EEG-HRV.kicad_pcb",
        parts_table="data/parts_lcsc.csv",
        total_placements=len(rows),
        unique_part_numbers=len(grp),
        method=("各 C 番号を LCSC 商品ページ / EasyEDA 部品 API / JLCPCB partdetail の "
                "いずれか複数で取得し、data/parts_lcsc.csv の値・パッケージと "
                "kicad_pcb のフットプリント実測パッド寸法、および "
                "contract/netlist_from_kicad_pcb.json の実接続ネットに突合した。"),
        summary=dict(
            ng=[r["lcsc"] for r in out if r["verdict"] == "NG"],
            needs_check=[r["lcsc"] for r in out if r["verdict"] == "要確認"],
            ok=[r["lcsc"] for r in out if r["verdict"] == "OK"],
            extended_part_numbers=[r["lcsc"] for r in out
                                   if r["jlc_part_class"] == "Extended"],
        ),
        rows=out,
    )
    jp = os.path.join(ROOT, "reports/bom_verification.json")
    with open(jp, "w") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    print("wrote", jp, len(out), "rows")
    return doc


if __name__ == "__main__":
    main()
