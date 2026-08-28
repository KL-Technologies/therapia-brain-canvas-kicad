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
# 個別ページではなく検索 API の一覧から得た値の出典
SEARCH_C0G = ("https://easyeda.com/api/eda/product/search"
              "?keyword=1.5nF%200402%20C0G&needAggs=false&currPage=1&pageSize=20  (検索一覧)")

# 短縮 URL ではなくフルスラッグで取得した品番（実際に叩いた URL を正確に残す）
JLC_SLUG = {
    "C1017": "https://jlcpcb.com/partdetail/Sunlord-GZ2012D601TF/C1017",
    "C2286": "https://jlcpcb.com/partdetail/Hubei_KentoElec-KT0603R/C2286",
    "C72043": "https://jlcpcb.com/partdetail/EverlightElec-19_217_GHC_YR1S23T/C72043",
    "C72044": "https://jlcpcb.com/partdetail/EverlightElec-19_217_R6C_AL1M2VY3T/C72044",
    "C883122": "https://jlcpcb.com/partdetail/BHFUSE-BSMD1206_0506V/C883122",
}


def url(tpl, lcsc):
    """出典 URL を組み立てる。フルスラッグで取得したものはそちらを返す。"""
    if tpl is JLC and lcsc in JLC_SLUG:
        return JLC_SLUG[lcsc]
    if "{}" not in tpl:
        return tpl
    return tpl.format(lcsc)

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
        note="【追加調査で不採用】EasyEDA シンボルのピン生データは "
             "A=pin**1** / K=pin**2**（`0~1~-5~0~A~end~~~#800^^0~9~-9~0~1~start` と "
             "`0~K~start~~~#800^^0~-9~-9~0~2~end`）。現基板は pad1=GND=カソードなので "
             "**極性が反転**し、そのまま置換すると LED が逆実装になる。"
             "パッケージ名も 'LED-SMD_L1.6-W0.8-R-RD' で現フットプリントと別名。",
        src=[JLC, EDA]),
    "C72044": dict(
        mpn="19-217/R6C-AL1M2VY/3T", mfr="Everlight Elec", pkg="LED0603-RD",
        spec="LED 0603 / 赤 617.5nm / Vf 1.95V @5mA / 11.5-28.5mcd / 120deg / 60mW",
        cls="Extended", stock_lcsc=215065, stock_sz=902100, jlc_onsale=True,
        note="D_LED 第 1 候補。現フットプリントと**パッケージ名が完全一致**（LED0603-RD）で、"
             "ピン生データも pin1='C' / pin2='A'（C72043 と同一シリーズ・同一ライブラリ）。"
             "3.3V - 1.95V = 1.35V / 330Ω = 約 4.1mA。"
             "在庫は EasyEDA API 215,065（SZ 902,100）に対し LCSC 商品ページは "
             "'Not available now' 表示で食い違う。",
        src=[LCSC, JLC, EDA]),
    "C72038": dict(
        mpn="19-213/Y2C-CQ2R2L/3T(CY)", mfr="Everlight Elec", pkg="LED0603-RD-YELLOW",
        spec="LED 0603 / 黄 / Vf 1.7-2.3V @20mA / 90-180mcd",
        cls="Extended", stock_lcsc=70862, stock_sz=187040, jlc_onsale=True,
        _src_note="LCSC 商品ページは未取得（JLC partdetail と EasyEDA API のみ）",
        note="D_LED 第 2 候補。ピン生データは pin1='C' / pin2='A' で"
             "**現基板の極性と一致**（`P~show~1~1~...C~start` / `P~show~1~2~...A~end`）。"
             "BOM の value 'LED_Y'（黄）とも色が一致し、輝度は C72044 より高い。"
             "ただしパッケージ名は 'LED0603-RD-**YELLOW**' で現フットプリント名と厳密には別名"
             "（0603 ランド自体は同等とみられるがカート投入時に要プレビュー確認）。"
             "Vf 2.0V 換算で (3.3-2.0)/330 = 約 3.9mA。",
        src=[JLC, EDA]),
    "C183844": dict(
        mpn="19-217/G7C-AM1N2B/3T", mfr="Everlight Elec", pkg="LED0603-RD",
        spec="LED 0603 / 黄緑",
        cls="Extended", stock_lcsc=2920, stock_sz=540, jlc_onsale=True,
        note="パッケージ名は LED0603-RD で一致し 19-217 シリーズだが、"
             "在庫が LCSC 2,920 / SZ 540 と薄く非推奨。参考記録のみ。",
        src=[EDA]),
    "C23967": dict(
        mpn="CL05B152KB5NNNC", mfr="Samsung Electro-Mechanics", pkg="C0402",
        spec="1.5nF / 50V / X7R / +-10% / 0402",
        cls="Extended", stock_lcsc=60236, stock_sz=21600, jlc_onsale=True,
        note="ECO-5（BIAS 帰還 1MΩ∥1.5nF）用の第 1 候補。誘電体 X7R は "
             "JLC partdetail が明示。EasyEDA パッケージ名 `C0402` は現フットプリントと完全一致。",
        src=[JLC, EDA]),
    "C284989": dict(
        mpn="0402B152K500NT", mfr="FH (Fenghua)", pkg="C0402",
        spec="1.5nF / 50V / +-10%(K) / 0402",
        cls="Extended", stock_lcsc=19300, stock_sz=95000, jlc_onsale=True,
        note="ECO-5 用の第 2 候補。EasyEDA API の Voltage Rated 500V は型番 '...500NT' の"
             "誤パース（同じ FH 表記の C1546=0402CG101J500NT が 50V と確認済み）。"
             "誘電体の明記は取得できず（型番の 'B' は FH の X7R 系だが未裏取り）。",
        src=[EDA]),
    "C281752": dict(
        mpn="CC0402JRX7R9BB152", mfr="YAGEO", pkg="C0402",
        spec="1.5nF / X7R / 0402",
        cls="Extended", stock_lcsc=0, stock_sz=0, jlc_onsale=True,
        note="在庫 0/0 のため不採用。",
        src=[EDA]),
    "C52037853": dict(
        mpn="CGA0402C0G152J500GT", mfr="HRE", pkg="0402",
        spec="1.5nF / 50V / C0G / +-5% / 0402",
        cls="取得不能", stock_lcsc=2250, stock_sz=None, jlc_onsale=None,
        note="唯一在庫のある C0G 1.5nF 0402。ただし在庫 2,250 と薄く、"
             "EasyEDA 検索 API の一覧からの値で個別ページは未取得。参考記録。",
        src=[SEARCH_C0G]),
    "C14442": dict(
        mpn="CL05B102KB5NNNC", mfr="Samsung Electro-Mechanics", pkg="C0402",
        spec="1nF / 50V / +-10% / 0402",
        cls="Extended", stock_lcsc=200, stock_sz=205200, jlc_onsale=True,
        note="1.5nF を避けて 1nF に落とす案の検証用に確認。これも Extended なので "
             "Extended 手数料の回避にはならない。",
        src=[EDA]),
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
    "C72043": ["C72044", "C72038"],
    "C369159": ["C883122"],
}

# 追加調査（2026-08-28、lead 依頼）
ADDENDUM = dict(
    led_polarity=dict(
        board_footprint="ProPrj_The-easyedapro:LED0603-RD",
        board_pad_geometry="pad1/pad2 とも 0.8x0.8mm 角、x=-0.749 / +0.749mm（0603 ランド）",
        board_polarity="pad1 = C（カソード）→ GND / pad2 = A（アノード）→ LED_A",
        board_polarity_source=("contract/netlist_easyeda_api_2026-08-28.tsv の "
                               "D_LED 行が pinName を保持: `D_LED 1 C GND` / `D_LED 2 A LED_A`"),
        first_choice="C72044",
        second_choice="C72038",
        rejected=["C2286", "C183844"],
    ),
    board_recheck=dict(
        when="2026-08-28 16:47（board が 16:46 に並行作業で更新されたため読み直し）",
        stale_snapshot="contract/netlist_from_kicad_pcb.json は 13:45 時点",
        pad_net_syntax='この kicad_pcb のパッド net は (net "名前") 形式で index を持たない',
        findings={
            "TPS72325": {"1": "GND", "2": "V_NLDO_IN", "3": "V_NLDO_IN",
                         "4": "TPS_NR", "5": "AVSS"},
            "ECO-1#1 (EN=V_NLDO_IN)": "適用済み（初版の『未反映』は誤りだったので訂正）",
            "C_VCAP1_H": {"1": "VCAP1", "2": "AVSS", "footprint": "C0402"},
            "C_VCAP2": {"1": "VCAP2", "2": "AVSS", "footprint": "C0402"},
            "C_VCAP3": {"1": "VCAP3", "2": "AVSS", "footprint": "C0402"},
            "C_VCAP3_H": {"1": "VCAP3", "2": "AVSS", "footprint": "C0402"},
            "C_VCAP1": {"footprint": "C_1206_3216Metric"},
            "C_VREFP_10u": {"footprint": "C_1206_3216Metric"},
            "D_LED": {"1": "GND", "2": "LED_A", "footprint": "LED0603-RD"},
            "R_LED": {"1": "STATUS_LED_DRV", "2": "LED_A"},
            "FB5": {"1": "VDD_ESP", "2": "DVDD", "footprint": "L0805"},
        },
    ),
    bias_cap=dict(
        eco="ECO-5（data/bom_fixes_2026-08-28.json）",
        board_now={
            "R_BIAS_FB": "1MΩ 0805 (C17514) が BIAS_INV <-> BIAS_OUT_INT を橋渡し",
            "C_BIAS_INV": "現在 100nF (C1525) が BIAS_INV -> GND、フットプリント C0402",
            "ADS1299_pinName": "pin61=BIASINV / pin63=BIASOUT（contract TSV の pinName で確認）",
        },
        pole_hz_with_1n5="1/(2*pi*1M*1.5n) = 約 106Hz（TI 推奨値）",
        first_choice="C23967",
        second_choice="C284989",
        no_basic_option=("JLC Basic に 1.5nF 0402 は存在しない。検索した 1.5nF 0402 は "
                         "Samsung/FH/YAGEO/Walsin/KEMET/AVX/Vishay/Meritek いずれも Extended。"
                         "1nF に落とす案（C14442）も Extended なので手数料回避にならない。"),
        dielectric_note=("この C は 1MΩ と並列で "
                         "BIASINV(加算節点) と BIASOUT の間に入り両端の DC 電位差がほぼ 0V なので、"
                         "X7R の弱点である DC バイアス容量減衰が効かない。残る誘電吸収・圧電は "
                         "106Hz の極を作るだけの用途では二次的。"),
    ),
    en_rc_cap=dict(
        eco="B2（data/bom_fixes_2026-08-28.json）",
        board_now="C_EN_DLY = 100nF (C1525) が ESP_EN -> GND / R_EN_UP = 10kΩ (C25804) が VDD_ESP -> ESP_EN",
        part="C52923 = CL05A105KA5NQNC / Samsung / C0402 / 1uF 25V X5R +-10% / JLC Basic",
        verdict="OK",
        reason=("定格 25V は要求の 6.3V 以上を約 4 倍上回る。EN ノードは 3.3V なので "
                "DC バイアスによる容量減衰も小さく、10kΩ との時定数は WROOM-32E 推奨の "
                "10kΩ/1µF の意図どおりに出る。フットプリントは現行 C1525 と同じ C0402 で "
                "品番差し替えのみ・銅箔変更なし。"),
        bonus=("C52923 は既に BOM の 10 箇所（C_3V3_IN / C_3V3_M / C_AVDD1_1u / C_LM_IN / "
               "C_NLDO_IN / C_PLDO_IN / C_PLDO_OUT / C_VCAP2 / C_VCAP3 / C_VCAP4）で使用中。"
               "C_EN_DLY を C52923 にしても品番数が増えず、Basic のままリールも増えない。"),
        sources=["https://www.lcsc.com/product-detail/C52923.html",
                 "https://easyeda.com/api/products/C52923/components"],
    ),
    fb_footprint=dict(
        board_footprint="ProPrj_The-easyedapro:L0805（FB1-FB5 の 5 点すべて）",
        board_pad_geometry=("pad1/pad2 とも 1.1325 x 1.377mm、x=-0.966 / +0.966mm。"
                            "内側ギャップ 0.8mm / 外形スパン 3.065mm / パッド幅 1.377mm"),
        part_package="C1017 の EasyEDA パッケージ名は `L0805`（JLC partdetail の表記は `0805`）",
        verdict="OK",
        reason=("フットプリント名が `L0805` で完全一致。MPN の 'GZ2012' は 2012 メートル法 = "
                "0805 インチで、パッド幅 1.377mm > 本体幅 1.25mm、スパン 3.065mm > 本体長 2.0mm と"
                "ランドが本体を包含する。2 端子無極性なので向きの検討は不要。"),
    ),
)


def main():
    rows = [r for r in csv.DictReader(open(os.path.join(ROOT, "data/parts_lcsc.csv")))
            if r.get("designator")]
    grp = collections.OrderedDict()
    for r in rows:
        grp.setdefault(r["lcsc"], []).append(r)

    # PCB に実在する designator は基板ファイルを直読みする。
    # contract/netlist_from_kicad_pcb.json は 13:45 のスナップショットで、
    # その後 board が更新されているため配置判定には使わない。
    import re
    board = open(os.path.join(ROOT, "board/Therapia_EEG-HRV.kicad_pcb")).read()
    on_pcb = set(re.findall(r'\(property "Reference" "([^"]+)"', board))

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
                               source_urls=[url(u, a) for u in FACTS[a]["src"]])
                          for a in ALTS.get(lcsc, [])],
            source_urls=[url(u, lcsc) for u in f["src"]],
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
        addendum=ADDENDUM,
        addendum_rows=[
            dict(lcsc=k, role=role, mpn=FACTS[k]["mpn"],
                 manufacturer=FACTS[k]["mfr"], package=FACTS[k]["pkg"],
                 spec=FACTS[k]["spec"], jlc_part_class=FACTS[k]["cls"],
                 stock_lcsc=FACTS[k]["stock_lcsc"], stock_szlcsc=FACTS[k]["stock_sz"],
                 jlc_on_sale=FACTS[k]["jlc_onsale"], verdict=verdict,
                 note=FACTS[k].get("note"),
                 source_urls=[url(u, k) for u in FACTS[k]["src"]])
            for k, role, verdict in [
                ("C72044", "D_LED 代替 第1候補", "採用推奨"),
                ("C72038", "D_LED 代替 第2候補", "採用可"),
                ("C2286", "D_LED 代替 検討→不採用", "NG（極性反転）"),
                ("C183844", "D_LED 代替 検討→不採用", "非推奨（在庫薄）"),
                ("C1017", "FB1-FB5 代替 確定", "採用推奨"),
                ("C883122", "F1 代替 候補", "採用可"),
                ("C23967", "ECO-5 BIAS 帰還 1.5nF 第1候補", "採用推奨"),
                ("C284989", "ECO-5 BIAS 帰還 1.5nF 第2候補", "採用可"),
                ("C281752", "ECO-5 検討→不採用", "NG（在庫 0）"),
                ("C52037853", "ECO-5 C0G 参考", "参考（在庫薄）"),
                ("C14442", "ECO-5 1nF 代案の検証", "不採用（Extended で利点なし）"),
                ("C52923", "B2 ESP32 EN の RC 用", "OK"),
            ]],
    )
    jp = os.path.join(ROOT, "reports/bom_verification.json")
    with open(jp, "w") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    print("wrote", jp, len(out), "rows")

    mp = os.path.join(ROOT, "reports/bom_verification.md")
    with open(mp, "w") as fh:
        fh.write(render_md(doc))
    print("wrote", mp)
    return doc


def n(v):
    if v is None:
        return "取得不能"
    return f"{v:,}"


def render_md(doc):
    L = []
    w = L.append
    order = {"NG": 0, "要確認": 1, "OK": 2}
    rows = sorted(doc["rows"], key=lambda r: (order[r["verdict"]], r["lcsc"]))
    ng = [r for r in rows if r["verdict"] == "NG"]
    chk = [r for r in rows if r["verdict"] == "要確認"]

    w(f"# Brain Canvas Rev.A — BOM 実体照合レポート（{doc['generated']}）\n")
    w(f"対象: `{doc['parts_table']}` / `{doc['board']}`  ")
    w(f"実装点数 **{doc['total_placements']}** ・品番数 **{doc['unique_part_numbers']}**  ")
    w(f"判定: **NG {len(ng)}** / **要確認 {len(chk)}** / OK {len(doc['summary']['ok'])}\n")
    w("## 照合方法\n")
    w(doc["method"] + "\n")
    w("出典 URL は各行に記録。取得できなかった項目は「取得不能」と明記し、推測では埋めていない。\n")

    w("## 結論（発注前に潰すべき項目）\n")
    w("| 優先 | 品番 | designator | 問題 | 推奨対処 |")
    w("|---|---|---|---|---|")
    w("| **1** | `C94221` | FB1–FB5 (5) | LCSC/JLC に**存在しない品番**。3 ソースで不存在を確認 | "
      "`C1017`（Sunlord GZ2012D601TF, L0805, **Basic**, 在庫 75,200）へ差し替え |")
    w("| **2** | `C72043` | D_LED (1) | 実体は緑 LED **Vf 3.3V**。3.3V GPIO + 330Ω では電流ほぼ 0 で点灯しない | "
      "`C72044`（Everlight 19-217/R6C 赤, Vf 1.95V, フットプリント・極性とも完全一致）へ差し替え。"
      "330Ω のまま約 4.1mA。詳細は末尾の追記を参照 |")
    w("| 3 | `C13585` | C_VREFP_10u (1) | CSV の MPN が誤り（実体は …K**B**H…, 50V） | "
      "**設計上は OK**。BOM の MPN 文字列のみ訂正。C15008 代替は不要 |")
    w("| 4 | `C1546` | C_AVDD1_10n, C_VREFP_10n (2) | designator は「10n」だが実装は 100pF | "
      "10nF が正なら `C15195`(0402) 相当へ。現状維持なら designator をリネーム |")
    w("| 5 | `C369159` `C69932` `C701341` `C19619` | F1 / TPS72325 / U_MCU / TLV70025 | 在庫表示が薄い or ソース間で乖離 | "
      "JLC カート投入時に実数を確認。F1 の同一フットプリント代替は `C883122` |")
    w("| 6 | `C2840012` `C19619` `C72043` | J2 / TLV70025 / D_LED | CSV のパッケージ表記が実体と不一致 | "
      "**基板側フットプリントは全て正しい**。CSV のラベルのみ訂正 |")
    w("")

    w("## NG（発注前に必ず修正）\n")
    for r in ng:
        w(f"### `{r['lcsc']}` — {', '.join(r['designators'])}（{r['qty']} 点）\n")
        w(f"- **設計意図**: {r['design_intent']}")
        w(f"- **取得した実体**: {r['fetched_mpn']} / {r['fetched_manufacturer']} / "
          f"{r['fetched_package']} / {r['fetched_spec']}")
        w(f"- **判定理由**: {r['reason']}")
        if r["note"]:
            w(f"- 補足: {r['note']}")
        for a in r["alternatives"]:
            w(f"- **推奨代替**: `{a['lcsc']}` {a['mpn']} / {a['pkg']} / {a['spec']} / "
              f"JLC **{a['jlc_part_class']}** / 在庫 {n(a['stock_lcsc'])}")
            if a["note"]:
                w(f"  - {a['note']}")
            w(f"  - 出典: " + " , ".join(a["source_urls"]))
        w(f"- 出典: " + " , ".join(r["source_urls"]))
        w("")

    w("## 要確認\n")
    for r in chk:
        w(f"### `{r['lcsc']}` — {', '.join(r['designators'])}（{r['qty']} 点）\n")
        w(f"- **設計意図**: {r['design_intent']}")
        w(f"- **取得した実体**: {r['fetched_mpn']} / {r['fetched_manufacturer']} / "
          f"{r['fetched_package']} / {r['fetched_spec']}")
        w(f"- **判定理由**: {r['reason']}")
        if r["note"]:
            w(f"- 補足: {r['note']}")
        for a in r["alternatives"]:
            w(f"- **代替候補**: `{a['lcsc']}` {a['mpn']} / {a['pkg']} / {a['spec']} / "
              f"JLC **{a['jlc_part_class']}** / 在庫 {n(a['stock_lcsc'])}")
            if a["note"]:
                w(f"  - {a['note']}")
        w(f"- 出典: " + " , ".join(r["source_urls"]))
        w("")

    w("## 全品番一覧\n")
    w("| 判定 | C番号 | designator（数） | 取得した MPN / メーカー | 取得したスペック | "
      "取得したパッケージ | KiCad フットプリント | JLC 区分 | LCSC 在庫 | SZLCSC 在庫 |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    mark = {"NG": "**NG**", "要確認": "要確認", "OK": "OK"}
    for r in rows:
        des = ", ".join(r["designators"])
        if len(des) > 46:
            des = r["designators"][0] + " ほか"
        kf = r["kicad_footprint"].replace("ProPrj_The-easyedapro:", "")
        w(f"| {mark[r['verdict']]} | `{r['lcsc']}` | {des} ({r['qty']}) | "
          f"{r['fetched_mpn']} / {r['fetched_manufacturer']} | {r['fetched_spec']} | "
          f"`{r['fetched_package']}` | `{kf}` | {r['jlc_part_class']} | "
          f"{n(r['stock_lcsc'])} | {n(r['stock_szlcsc'])} |")
    w("")

    w("## 在庫リスク順位\n")
    w("在庫はソース間で食い違うことがあるため、最終確定は JLC カート投入時とする。"
      "以下は「発注前に実数を確認すべき」順。\n")
    w("| 順位 | 品番 | designator | 取得できた在庫 | JLC 区分 | リスク内容 | 代替 |")
    w("|---|---|---|---|---|---|---|")
    w("| 1 | `C94221` | FB1–FB5 | — | 存在しない | 品番自体が引けない（在庫以前の問題） | `C1017` (Basic, 75,200) |")
    w("| 2 | `C701341` | U_MCU | LCSC ページ 29,577 / API **6** | Extended | ソース間の乖離が最大。ESP32 モジュールは代替が効きにくい | 同等品は要検討 |")
    w("| 3 | `C69932` | TPS72325 | LCSC ページ 7,086 / API **0**（SZ 3,843） | Extended | 負電圧 LDO は代替品が少ない。欠品時は基板が動かない | ピン互換の TPS723xx 系を要調査 |")
    w("| 4 | `C13585` | C_VREFP_10u | LCSC ページ 917,300 / API **0/0** | Basic | ソース間の乖離。Basic なので JLC 側は通常確保 | `C15008`(100uF 6.3V 1206) で代替可 |")
    w("| 5 | `C369159` | F1 | LCSC ページ **Not available now** / API 6,160 | Extended | 商品ページが在庫なし表示 | `C883122`（F1206 同一, 6V 定格に低下） |")
    w("| 6 | `C19619` | TLV70025 | 1,480〜2,186 | Extended | 絶対数が少ない。10 台分なら足りる | +2.5V 200mA SOT-23-5 LDO を要調査 |")
    w("| 7 | `C476817` | U_ADS | 3,126 | Extended | 単価 $60.31 と高額。数量確保より価格インパクト大 | 代替不可（設計の中核） |")
    w("| 8 | `C108573` | LM2664 | LCSC ページ 49,955 / API **0**（SZ 1,620） | Extended | ソース間の乖離 | — |")
    w("")

    w("## JLC Extended 部品（手数料対象）\n")
    ext = [r for r in doc["rows"] if r["jlc_part_class"] == "Extended"]
    w(f"現 BOM の Extended は **{len(ext)} 品番**: "
      + ", ".join(f"`{r['lcsc']}`({r['designators'][0]})" for r in ext) + "\n")
    w("推奨差し替え（`C94221`→`C1017`, `C72043`→`C2286`）はいずれも Basic 品なので、"
      "Extended 品番数は増えない。`C369159`→`C883122` は Extended のままで増減なし。\n")

    w("## BOM 以外に気づいた点（参考・lead 判断用）\n")
    w("> 注: `contract/netlist_from_kicad_pcb.json` は 13:45 のスナップショットで、"
      "その後 `board/Therapia_EEG-HRV.kicad_pcb` が 16:46 に更新された（並行作業）。"
      "以下は **16:47 に基板ファイルを直接読み直した結果**に基づく。\n")
    w("- **ECO-1 は PCB に反映済み（再確認して訂正）**: 本レポート初版では"
      "「TPS72325 の pin3(EN) が `GND` のままで B1 致命バグが残存」と書いたが、"
      "これは 13:45 のネットリストに基づく古い所見だった。"
      "現在の基板ファイルでは **pin3 = `V_NLDO_IN`**（pin1=GND / pin2=V_NLDO_IN / "
      "pin4=TPS_NR / pin5=AVSS）で、ECO-1#1 は適用済み。")
    w("- **ECO-1/ECO-3 の新設・変更部品も配置済み（同上）**: `C_VCAP1_H`(VCAP1-AVSS)、"
      "`C_VCAP2`(VCAP2-AVSS)、`C_VCAP3`(VCAP3-AVSS)、`C_VCAP3_H`(VCAP3-AVSS) の 4 点が "
      "`C0402` で配置・結線済み。`C_VCAP1` と `C_VREFP_10u` も `C_1206_3216Metric` に"
      "差し替わっており ECO-3 の 1206 化も完了している。BOM 135 点と基板の点数は整合する。")
    w("- **D_LED まわりは未変更**: `D_LED` pad1=`GND` / pad2=`LED_A`、"
      "`R_LED` pad1=`STATUS_LED_DRV` / pad2=`LED_A` で、上記 LED の判定はそのまま有効。")
    w("- **DVDD は +3.3V 給電**: FB5 が `VDD_ESP → DVDD`。"
      "`08_simplified_power_design.md` の「AVDD と DVDD を共通 +2.5V」という記述と食い違う。"
      "実回路の 3.3V は ADS1299 の DVDD 定格範囲内で、ESP32 の 3.3V ロジックとも整合するため "
      "回路としては妥当。ドキュメント側が古い。")
    w("- **フェライトビーズの DCR 前提が古い**: `08_simplified_power_design.md` は "
      "BLM18PG600SN1D（DCR 38mΩ / 2.5A）前提で電圧降下 5.7mV としているが、実体の "
      "GZ2012D601TF は **DCR 300mΩ / 定格 500mA**。FB3 は ESP32 系 80–240mA を通すため "
      "降下は 24–72mV（想定の 4〜12 倍）。Rev.A は許容範囲だが、余裕を取るなら低 DCR 品を検討。")
    w("- **ADS1299 PAG にサーマルパッドは無い**: KiCad フットプリントは 64 パッドのみで実体と整合。"
      "`08_simplified_power_design.md` の「ADS1299 の thermal pad 直下に 9 個の via」は成立しない。")
    w("- **USB-C のフットプリント名**: KiCad 側 `USB-C-SMD_TYPE-C-6PIN-2MD-073` は "
      "EasyEDA 側 `…-16PIN-…` の名称欠落。パッド実体（12 SMD + 4 TH）は正しく、"
      "ピン割当も EasyEDA シンボルの pinName と netlist が一致しているため実害なし。")
    w("")
    w("## 変更しなかったもの\n")
    w("本レポートは調査のみ。`data/parts_lcsc.csv`・`board/` は一切編集していない。"
      "差し替えの反映は lead 判断とする。\n")

    a = doc["addendum"]
    led, fb = a["led_polarity"], a["fb_footprint"]
    w("---\n")
    w("# 追記（2026-08-28、追加調査）\n")

    w("## 1. D_LED の代替を確定\n")
    w("### 前提：現基板側の極性\n")
    w(f"- フットプリント: `{led['board_footprint']}`")
    w(f"- パッド実測: {led['board_pad_geometry']}")
    w(f"- **極性: {led['board_polarity']}**")
    w(f"- 根拠: {led['board_polarity_source']}")
    w("")
    w("シルクの向きではなく **EasyEDA シンボルの pinName** を根拠にした（J1 の "
      "ピン割当を確定したのと同じ方法）。`pinNumber` はライブラリ内連番で"
      "データシートと一致しないことがあるため単独では使わない。\n")

    w("### 候補の比較\n")
    w("| | C番号 | MPN / 色 | EasyEDA パッケージ名 | ピン番号→名 | Vf | 330Ω・3.3V での電流 | "
      "JLC 区分 | 在庫(LCSC / SZLCSC) | 判定 |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    w("| **第1候補** | `C72044` | 19-217/R6C-AL1M2VY/3T / 赤 617.5nm | "
      "`LED0603-RD` **完全一致** | **1=C, 2=A**（現基板と一致） | 1.95V @5mA | "
      "**約 4.1mA** | Extended | 215,065 / 902,100 | **採用推奨** |")
    w("| **第2候補** | `C72038` | 19-213/Y2C-CQ2R2L/3T(CY) / 黄 | "
      "`LED0603-RD-YELLOW`（別名） | **1=C, 2=A**（現基板と一致） | 1.7–2.3V @20mA | "
      "約 3.9mA | Extended | 70,862 / 187,040 | 採用可 |")
    w("| 不採用 | `C2286` | KT-0603R / 赤 645nm | `LED-SMD_L1.6-W0.8-R-RD`（別名） | "
      "**1=A, 2=K**（**反転**） | 1.8–2.4V | 約 3.9mA | Basic | 624,750 / 0 | "
      "**NG（逆実装になる）** |")
    w("| 不採用 | `C183844` | 19-217/G7C-AM1N2B/3T / 黄緑 | `LED0603-RD` 一致 | "
      "取得不能 | 取得不能 | — | Extended | 2,920 / 540 | 非推奨（在庫薄） |")
    w("")

    w("### 判定理由\n")
    w("**`C72044` を第 1 候補とする。** 現在の `C72043` と同じ Everlight 19-217 シリーズ・"
      "同じ EasyEDA ライブラリの赤バリアントで、パッケージ名が `LED0603-RD` と完全一致する。"
      "ピン生データも `P~show~1~**1**~...~**C**~end~...` / `P~show~1~**2**~...~**A**~start~...` で "
      "pin1=カソード・pin2=アノード、現基板の pad1=GND(カソード) と一致するため、"
      "**C 番号の差し替えだけで済み、基板の銅箔も配線も触らなくてよい**。"
      "Vf 1.95V に対し (3.3−1.95)/330 = 約 4.1mA で、依頼の 3〜4mA 帯に収まる。\n")
    w("JLC 区分は Extended だが、差し替え前の `C72043` も同シリーズで、"
      "同ページに Basic バッジが出ていないため区分は実質変わらないと見込まれる"
      "（`C72043` の区分は 3 URL とも表示されず取得不能のままなので、断定はしない）。\n")
    w("**`C72038`（黄）を第 2 候補とする。** ピン番号→名は `1=C / 2=A` で現基板と一致し、"
      "BOM の value `LED_Y`（黄）とも色が揃う。輝度も 90–180mcd@20mA と `C72044` の "
      "11.5–28.5mcd@5mA より高く、ステータス表示としては見やすい。"
      "唯一の引っかかりはパッケージ名が `LED0603-RD-YELLOW` と別名である点で、"
      "0603 ランド自体は同等と見られるが名称一致の条件を厳密には満たさないため第 2 候補とした。"
      "採用する場合はカート投入時に JLC のプレビューで外形と向きを確認すること。\n")
    w("**`C2286`（前回の推奨）は撤回する。** EasyEDA シンボルのピン生データを読むと "
      "`0~1~-5~0~**A**~end~~~#800^^0~9~-9~0~**1**~start` と "
      "`0~**K**~start~~~#800^^0~-9~-9~0~**2**~end` で、**A=pin1 / K=pin2**。"
      "現基板は pad1 がカソードなので、そのまま置換すると LED が逆実装になる。"
      "Basic かつ在庫潤沢という利点はあるが、極性が合わないので採用しない。\n")

    w("## 2. C1017（GZ2012D601TF）のフットプリント整合\n")
    w(f"- 基板側: `{fb['board_footprint']}`")
    w(f"- パッド実測: {fb['board_pad_geometry']}")
    w(f"- 部品側: {fb['part_package']}")
    w(f"- **判定: {fb['verdict']}**")
    w(f"- 理由: {fb['reason']}")
    w("")
    w("`grep -o 'footprint \"[^\"]*\"'` の結果でも `ProPrj_The-easyedapro:L0805` はちょうど "
      "5 個で、FB1–FB5 の 5 点と一致する。他の 0805 系（`C0805` 8 個・`R0805` 6 個）とは"
      "別フットプリントとして分かれており、取り違えは起きていない。\n")

    bc, en = a["bias_cap"], a["en_rc_cap"]
    w("---\n")
    w("# 追記 2（2026-08-28、追加調査その 2）\n")

    w("## 3. BIAS 帰還用 1.5nF 0402（ECO-5）\n")
    w("### 現基板の該当箇所\n")
    for k, v in bc["board_now"].items():
        w(f"- `{k}`: {v}")
    w(f"- ECO-5 でこの `C_BIAS_INV` の pad2 を `GND` から `BIAS_OUT_INT` に移し 1.5nF にすると、"
      f"TI 推奨の 1MΩ ∥ 1.5nF になる。極は {bc['pole_hz_with_1n5']}。")
    w("")
    w("### 候補\n")
    w("| | C番号 | MPN / メーカー | EasyEDA パッケージ | スペック | JLC 区分 | 在庫(LCSC / SZLCSC) |")
    w("|---|---|---|---|---|---|---|")
    w("| **第1候補** | `C23967` | CL05B152KB5NNNC / Samsung | `C0402` **一致** | "
      "1.5nF **50V X7R ±10%** | Extended | 60,236 / 21,600 |")
    w("| **第2候補** | `C284989` | 0402B152K500NT / FH(風華) | `C0402` **一致** | "
      "1.5nF 50V ±10%(K) | Extended | 19,300 / 95,000 |")
    w("| 不採用 | `C281752` | CC0402JRX7R9BB152 / YAGEO | `C0402` | 1.5nF X7R | Extended | **0 / 0** |")
    w("| 参考(C0G) | `C52037853` | CGA0402C0G152J500GT / HRE | `0402` | "
      "1.5nF 50V **C0G** ±5% | 取得不能 | 2,250 / — |")
    w("")
    w("### 判定理由\n")
    w(f"**Basic は選べない。** {bc['no_basic_option']}"
      " したがって値を妥協する理由がなく、TI 推奨の 1.5nF をそのまま使うのが合理的。\n")
    w("**第 1 候補は `C23967`（Samsung CL05B152KB5NNNC）。** JLC partdetail が "
      "「1.5nF 50V X7R ±10% 0402」と明示しており誘電体まで確定できる唯一の候補で、"
      "EasyEDA パッケージ名 `C0402` は現フットプリント `ProPrj_The-easyedapro:C0402` と完全一致する。"
      "在庫も 60,236 / 21,600 と十分。\n")
    w("**第 2 候補は `C284989`（FH 0402B152K500NT）。** パッケージ名 `C0402` 一致、"
      "SZLCSC 在庫 95,000 と潤沢で、FH は既に `C1546` で BOM に入っているメーカー。"
      "ただし誘電体の明記が取得できなかった（型番の 'B' は FH の X7R 系だが未裏取り）ので第 2 候補とした。"
      "なお EasyEDA API が返す「Voltage Rated 500V」は型番 '...500NT' の誤パースで、"
      "同じ表記体系の `C1546`（0402CG101J500NT）が 50V と確認済みなので 50V と判断している。\n")
    w("**材質について。** C0G が理想ではあるが、X7R でも実害は小さいと判断した。"
      + bc["dielectric_note"] +
      " C0G をどうしても優先するなら `C52037853` だが、在庫 2,250・メーカー実績不明・"
      "個別ページ未取得（検索 API 一覧の値のみ）というリスクを取ることになる。\n")

    w("## 4. `C52923`（ESP32 EN の RC 用、B2）の判定: OK\n")
    w(f"- 現基板: {en['board_now']}")
    w(f"- 実体: {en['part']}")
    w("- 在庫: LCSC 3,790,400 / SZLCSC 3,663,900、jlcOnSale=1（LCSC 商品ページと "
      "EasyEDA API の 2 ソースが一致）")
    w(f"- **判定: {en['verdict']}**")
    w("")
    w(en["reason"] + "\n")
    w("**さらに、部品種類が増えないという利点がある。** " + en["bonus"] + "\n")
    w("- 出典: " + " , ".join(en["sources"]))
    w("")

    w("## 追加調査で参照した URL\n")
    for k in ("C72044", "C72038", "C2286", "C183844", "C1017",
              "C23967", "C284989", "C281752", "C52037853", "C14442", "C52923"):
        urls = " , ".join(url(u, k) for u in FACTS[k]["src"])
        w(f"- `{k}`: {urls}")
    w("")
    return "\n".join(L)


if __name__ == "__main__":
    main()
