# アナログ配線の差分（S7b）

取り込み直後の基板（git `22513e4`）と現在の基板を、アナログ 40 ネットについて 1 アイテムずつ突き合わせた結果。

`kicad_pcb` の uuid は S5 で 2,625 個を採番し直しているので**幾何（ネット・層・座標・寸法）を鍵に**比較している。uuid で突き合わせると全アイテムが「変更」に見える。

| | |
|---|---|
| アナログ系アイテム | 770 → 846 |
| 差分 | 271 |
| 説明できない差分 | **0** |
| 入力・電極ネットの差分 | **0** |

## 触っていないことを要求するネット

`IN1P`〜`IN8N`（差動 8 対）、`SRB1`、`*_ELEC` 11 本 ＝ コネクタから ADC までの信号路。**差分 0 件**

つまり **1 件も無い**。S4a〜S7a の修理はどれも入力系の銅に触れていない。

**例外は S7v（via-in-pad の是正、2026-09-23）だけ**で、次の 52 件はすべて `logs/viapad_fix.json` に同じ座標で記録された via と配線。IN1P〜IN8N の ADC〜入力抵抗の経路長は変わっておらず、P/N の長さ差も広がっていない（`gates/S7v.json`）。

```
added    trk  IN1N           B.Cu          (132.8505, 112.1310) -> (133.5255, 112.1310) w0.2540
added    trk  IN1N           F.Cu          (132.4335, 112.1310) -> (132.8505, 112.1310) w0.2540
added    trk  IN1N           F.Cu          (132.8505, 112.1310) -> (133.5255, 112.1310) w0.2540
added    via  IN1N           (132.8505, 112.1310) d0.6095/0.3050
removed  trk  IN1N           F.Cu          (132.4335, 112.1310) -> (133.5255, 112.1310) w0.2540
removed  via  IN1N           (133.5255, 112.1310) d0.6095/0.3050
added    trk  IN2N           B.Cu          (132.8505, 109.1340) -> (133.5255, 109.1340) w0.2540
added    trk  IN2N           F.Cu          (132.4335, 109.1340) -> (132.8505, 109.1340) w0.2540
added    trk  IN2N           F.Cu          (132.8505, 109.1340) -> (133.5255, 109.1340) w0.2540
added    via  IN2N           (132.8505, 109.1340) d0.6095/0.3050
removed  trk  IN2N           F.Cu          (132.4335, 109.1340) -> (133.5255, 109.1340) w0.2540
removed  via  IN2N           (133.5255, 109.1340) d0.6095/0.3050
added    trk  IN3N           B.Cu          (132.8505, 106.1365) -> (133.5255, 106.1365) w0.2540
added    trk  IN3N           F.Cu          (132.4335, 106.1365) -> (132.8505, 106.1365) w0.2540
added    trk  IN3N           F.Cu          (132.8505, 106.1365) -> (133.5255, 106.1365) w0.2540
added    via  IN3N           (132.8505, 106.1365) d0.6095/0.3050
removed  trk  IN3N           F.Cu          (132.4335, 106.1365) -> (133.5255, 106.1365) w0.2540
removed  via  IN3N           (133.5255, 106.1365) d0.6095/0.3050
added    trk  IN4N           B.Cu          (132.8505, 103.1395) -> (133.5255, 103.1395) w0.2540
added    trk  IN4N           F.Cu          (132.4335, 103.1395) -> (132.8505, 103.1395) w0.2540
added    trk  IN4N           F.Cu          (132.8505, 103.1395) -> (133.5255, 103.1395) w0.2540
added    via  IN4N           (132.8505, 103.1395) d0.6095/0.3050
removed  trk  IN4N           F.Cu          (132.4335, 103.1395) -> (133.5255, 103.1395) w0.2540
removed  via  IN4N           (133.5255, 103.1395) d0.6095/0.3050
added    trk  IN5N           B.Cu          (132.8505, 100.1420) -> (133.5255, 100.1420) w0.2540
added    trk  IN5N           F.Cu          (132.4335, 100.1420) -> (132.8505, 100.1420) w0.2540
added    trk  IN5N           F.Cu          (132.8505, 100.1420) -> (133.5255, 100.1420) w0.2540
added    via  IN5N           (132.8505, 100.1420) d0.6095/0.3050
removed  trk  IN5N           F.Cu          (132.4335, 100.1420) -> (133.5255, 100.1420) w0.2540
removed  via  IN5N           (133.5255, 100.1420) d0.6095/0.3050
added    trk  IN6N           B.Cu          (132.8505, 97.1450) -> (133.5255, 97.1450) w0.2540
added    trk  IN6N           F.Cu          (132.4335, 97.1450) -> (132.8505, 97.1450) w0.2540
added    trk  IN6N           F.Cu          (132.8505, 97.1450) -> (133.5255, 97.1450) w0.2540
added    via  IN6N           (132.8505, 97.1450) d0.6095/0.3050
removed  trk  IN6N           F.Cu          (132.4335, 97.1450) -> (133.5255, 97.1450) w0.2540
removed  via  IN6N           (133.5255, 97.1450) d0.6095/0.3050
added    trk  IN7N           B.Cu          (132.8505, 94.1480) -> (133.5255, 94.1480) w0.2540
added    trk  IN7N           F.Cu          (132.4335, 94.1480) -> (132.8505, 94.1480) w0.2540
added    trk  IN7N           F.Cu          (132.8505, 94.1480) -> (133.5255, 94.1480) w0.2540
added    via  IN7N           (132.8505, 94.1480) d0.6095/0.3050
removed  trk  IN7N           F.Cu          (132.4335, 94.1480) -> (133.5255, 94.1480) w0.2540
removed  via  IN7N           (133.5255, 94.1480) d0.6095/0.3050
added    trk  IN8N           B.Cu          (132.8505, 91.1505) -> (133.5255, 91.1505) w0.2540
added    trk  IN8N           F.Cu          (132.4335, 91.1505) -> (132.8505, 91.1505) w0.2540
added    trk  IN8N           F.Cu          (132.8505, 91.1505) -> (133.5255, 91.1505) w0.2540
added    via  IN8N           (132.8505, 91.1505) d0.6095/0.3050
removed  trk  IN8N           F.Cu          (132.4335, 91.1505) -> (133.5255, 91.1505) w0.2540
removed  via  IN8N           (133.5255, 91.1505) d0.6095/0.3050
added    trk  SRB1           B.Cu          (130.1600, 89.1440) -> (130.6002, 89.2376) w0.2540
added    trk  SRB1           F.Cu          (130.1600, 89.1440) -> (130.6002, 89.2376) w0.2032
added    via  SRB1           (130.6002, 89.2376) d0.6095/0.3050
removed  via  SRB1           (130.1600, 89.1440) d0.6095/0.3050
```

## 変化した銅箔の画像

`scripts/64_copper_xor.py` が同じ枠・同じ倍率で両方の基板をラスタ化し、画素ごとにどちらに銅があるかを塗り分けたもの。**灰＝両方（不変）／緑＝現在のみ（追加）／赤＝取り込み時のみ（削除）**。

| 層 | 画像 | 不変 [px] | 追加 [px] | 削除 [px] | 変化率 |
|---|---|---|---|---|---|
| F.Cu | `reports/copper_xor_f_cu.png` | 264201 | 29443 | 11794 | 13.50% |
| B.Cu | `reports/copper_xor_b_cu.png` | 107755 | 17686 | 16103 | 23.87% |

> F.Cu の画像で、**基板左半分（12 ピンヘッダ・入力抵抗 16 個・CM コンデンサ 16 個・そこから ADS1299 までの配線）が一様に灰色**であることが、上の「差分 0 件」の目視版。赤緑が固まっているのは ADS1299 北側（VCAP 系）、中央下（BIAS/ECO-5）、右下（AMS1117 の移設と USB-C 周り）の 3 箇所だけ。

> B.Cu の左上にある赤緑の対は L2（CHASSIS_GND を H1 の外へ引き直した）そのもの。赤が穴を貫いていた旧経路、緑が新経路。

## 差分の内訳

| 由来 | 件数 |
|---|---|
| ECO-1#1 TPS72325 EN | 7 |
| ECO-1#2 RESV1 | 3 |
| ECO-1#4/5 VCAP2, VCAP3 | 77 |
| ECO-3#11 VCAP1 to 1206 | 34 |
| ECO-3#12 VREFP 10u to 1206 | 11 |
| ECO-5 BIAS feedback | 19 |
| S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) | 14 |
| S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) | 14 |
| S5_L5 repair: clearance Track+Via nets=AVDD,AVSS at (143.919,109.058) (144.415,107.648) | 6 |
| S5_L5 repair: clearance Track+Via nets=AVDD,GND at (145.908,114.490) (146.111,115.103) | 4 |
| drc_import repair: clearance AVDD,AVSS at (150.887,93.309) (151.407,92.700) | 4 |
| eco_apply repair: eco_apply recorded touching AVDD at (149.108,109.159) | 3 |
| viapad_fix repair: viapad_fix recorded touching AVDD at (140.219,109.883) | 3 |
| viapad_fix repair: viapad_fix recorded touching AVDD at (140.463,93.691) | 3 |
| viapad_fix repair: viapad_fix recorded touching AVDD at (143.351,91.929) | 6 |
| viapad_fix repair: viapad_fix recorded touching AVDD at (147.708,92.700) | 6 |
| viapad_fix repair: viapad_fix recorded touching AVDD at (148.283,92.700) (147.708,92.700) | 2 |
| viapad_fix repair: viapad_fix recorded touching BIAS_OUT_INT at (130.790,87.722) | 3 |
| viapad_fix repair: viapad_fix recorded touching IN1N at (132.851,112.131) | 6 |
| viapad_fix repair: viapad_fix recorded touching IN2N at (132.851,109.134) | 6 |
| viapad_fix repair: viapad_fix recorded touching IN3N at (132.851,106.136) | 6 |
| viapad_fix repair: viapad_fix recorded touching IN4N at (132.851,103.139) | 6 |
| viapad_fix repair: viapad_fix recorded touching IN5N at (132.851,100.142) | 6 |
| viapad_fix repair: viapad_fix recorded touching IN6N at (132.851,97.145) | 6 |
| viapad_fix repair: viapad_fix recorded touching IN7N at (132.851,94.148) | 6 |
| viapad_fix repair: viapad_fix recorded touching IN8N at (132.851,91.150) | 6 |
| viapad_fix repair: viapad_fix recorded touching SRB1 at (130.600,89.238) | 4 |

## 宣言済みの変更

| id | ネット | 部品 | 内容 |
|---|---|---|---|
| ECO-1#2 RESV1 | AVDD, GND | U_ADS | U_ADS pin 31 (RESV1) moves from AVDD to GND: the AVDD stub comes out and an L to pad 33 goes in |
| ECO-1#4/5 VCAP2, VCAP3 | VCAP2, VCAP3, AVSS | U_ADS, C_VCAP2, C_VCAP3, C_VCAP3_H | VCAP2 and VCAP3 do not exist on the imported board at all; the nets, the three capacitors and their routing are all new |
| ECO-3#11 VCAP1 to 1206 | VCAP1, AVSS | C_VCAP1, C_VCAP1_H, U_ADS | C_VCAP1 becomes a 1206 and turns 90 degrees to fit; C_VCAP1_H is new |
| ECO-3#12 VREFP 10u to 1206 | VREFP, AVSS | C_VREFP_10u | C_VREFP_10u becomes a 1206 and turns 90 degrees |
| ECO-1#1 TPS72325 EN | V_NLDO_IN, GND, TPS_NR, VNEG5 | TPS72325 | pin 3 (EN) moves from GND to V_NLDO_IN and is tied to pin 2 -- the B1 fatal bug |
| ECO-5 BIAS feedback | BIAS_OUT_INT, BIAS_INV, GND | C_BIAS_INV, R_BIAS_FB | C_BIAS_INV pad 2 moves from GND to BIAS_OUT_INT and drops to the B.Cu trunk |
| S5 L5 nudge C_AVSS_B | AVSS, GND | C_AVSS_B | moved +0.15 mm in x to clear a pad-to-pad clearance |
| S5 L5 nudge C_VREFP_10n | VREFP, AVSS | C_VREFP_10n | moved +0.05 mm in x to clear a pad-to-pad clearance |
| S7c VCAP3 bypass | VCAP3, AVSS | C_VCAP3_H, C_VCAP3, U_ADS | C_VCAP3_H moves to 2.10 mm of ADS pin 55 and reaches it with an L on F.Cu, replacing a 5.95 mm path through two vias -- DS 12.1 forbids a via between a bypass capacitor and the device |

## 移動したパッド

| 部品.パッド | ネット | 位置 [mm] | 寸法 [mm] | 移動 [mm] | 由来 |
|---|---|---|---|---|---|
| C_VCAP1.1 | VCAP1 | (150.542, 112.766) → (152.258, 116.527) | 0.80×0.90 → 1.15×1.80 | 4.1340 | ECO-3#11 VCAP1 to 1206 |
| C_VREFP_10u.2 | AVSS | (151.129, 110.480) → (150.937, 108.751) | 0.80×0.90 → 1.15×1.80 | 1.7396 | ECO-1#4/5 VCAP2, VCAP3 |
| C_VREFP_10u.1 | VREFP | (149.729, 110.480) → (150.937, 111.701) | 0.80×0.90 → 1.15×1.80 | 1.7176 | ECO-3#12 VREFP 10u to 1206 |
| C_VCAP1.2 | AVSS | (151.942, 112.766) → (152.258, 113.577) | 0.80×0.90 → 1.15×1.80 | 0.8704 | ECO-1#4/5 VCAP2, VCAP3 |
| C_AVSS_B.1 | AVSS | (149.210, 115.368) → (149.360, 115.368) | 0.80×0.90 → 0.80×0.90 | 0.1500 | ECO-3#11 VCAP1 to 1206 |
| C_VREFP_10n.1 | VREFP | (145.920, 110.480) → (145.970, 110.480) | 0.50×0.54 → 0.50×0.54 | 0.0500 | ECO-3#12 VREFP 10u to 1206 |
| C_VREFP_10n.2 | AVSS | (146.760, 110.480) → (146.810, 110.480) | 0.50×0.54 → 0.50×0.54 | 0.0500 | ECO-1#4/5 VCAP2, VCAP3 |

## 追加・削除された銅

### 削除（95 件）

```
ECO-1#1 TPS72325 EN          trk  TPS_NR         F.Cu          (155.0520, 114.3660) -> (155.0520, 114.5440) w0.2030
ECO-1#1 TPS72325 EN          via  VNEG5          (148.8545, 122.2150) d0.6095/0.3050
ECO-1#2 RESV1                pad  AVDD           U_ADS.31 (149.4120, 107.6480) 0.280x1.800
ECO-1#4/5 VCAP2, VCAP3       pad  AVSS           C_VCAP1.2 (151.9420, 112.7660) 0.800x0.900
ECO-1#4/5 VCAP2, VCAP3       pad  AVSS           C_VREFP_10n.2 (146.7600, 110.4800) 0.500x0.540
ECO-1#4/5 VCAP2, VCAP3       pad  AVSS           C_VREFP_10u.2 (151.1290, 110.4800) 0.800x0.900
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           B.Cu          (143.9165, 109.2100) -> (144.0790, 109.9720) w0.2540
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           B.Cu          (149.9085, 109.0070) -> (151.4960, 110.9880) w0.2540
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (141.0820, 93.9190) -> (141.2090, 93.9190) w0.3050
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (143.9190, 107.6480) -> (143.9190, 109.0575) w0.2030
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (145.4125, 95.3670) -> (145.4125, 95.4940) w0.2540
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (145.9130, 95.3670) -> (145.9130, 95.4940) w0.2540
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (146.7590, 110.4800) -> (146.9115, 110.4800) w0.2030
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (146.9240, 109.7690) -> (146.9240, 110.4800) w0.2030
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (147.9910, 93.9190) -> (148.7020, 93.9190) w0.3050
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (149.1210, 92.7000) -> (149.1210, 93.9190) w0.2540
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (149.2100, 114.5440) -> (149.2100, 115.0900) w0.2540
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (149.2100, 114.5440) -> (149.5275, 114.0360) w0.2540
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (149.5275, 112.4865) -> (149.5275, 114.0360) w0.2540
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (151.4070, 92.7000) -> (151.4070, 93.9190) w0.2540
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (143.9190, 109.0575) d0.6095/0.3050
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (145.9205, 112.7660) d0.6095/0.3050
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (146.9115, 110.4800) d0.6095/0.3050
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (148.7910, 110.4800) d0.6095/0.3050
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (148.8670, 112.7660) d0.6095/0.3050
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (149.9085, 109.0070) d0.6095/0.3050
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (151.4960, 113.7820) d0.6095/0.3050
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (152.5755, 112.7660) d0.6095/0.3050
ECO-3#11 VCAP1 to 1206       pad  AVSS           C_AVSS_B.1 (149.2100, 115.3680) 0.800x0.900
ECO-3#11 VCAP1 to 1206       trk  AVSS           F.Cu          (148.2955, 116.1190) -> (148.4480, 116.2330) w0.1525
ECO-3#11 VCAP1 to 1206       trk  AVSS           F.Cu          (148.4480, 115.9790) -> (148.4480, 116.2330) w0.2030
ECO-3#11 VCAP1 to 1206       trk  AVSS           F.Cu          (149.2100, 115.2170) -> (149.2100, 115.3670) w0.2030
ECO-3#11 VCAP1 to 1206       trk  AVSS           F.Cu          (153.8835, 120.3350) -> (153.9850, 120.3350) w0.2030
ECO-3#11 VCAP1 to 1206       via  AVSS           (142.1615, 112.7660) d0.6095/0.3050
ECO-3#11 VCAP1 to 1206       via  AVSS           (148.2955, 116.1190) d0.6095/0.3050
ECO-3#11 VCAP1 to 1206       via  AVSS           (149.2100, 115.2170) d0.6095/0.3050
ECO-3#11 VCAP1 to 1206       pad  VCAP1          C_VCAP1.1 (150.5420, 112.7660) 0.800x0.900
ECO-3#11 VCAP1 to 1206       trk  VCAP1          F.Cu          (150.8100, 113.1725) -> (150.8100, 114.3410) w0.2540
ECO-3#11 VCAP1 to 1206       via  VCAP1          (147.9095, 109.0070) d0.6095/0.3050
ECO-3#12 VREFP 10u to 1206   pad  VREFP          C_VREFP_10n.1 (145.9200, 110.4800) 0.500x0.540
ECO-3#12 VREFP 10u to 1206   pad  VREFP          C_VREFP_10u.1 (149.7290, 110.4800) 0.800x0.900
ECO-3#12 VREFP 10u to 1206   trk  VREFP          F.Cu          (145.7810, 111.4960) -> (145.9205, 111.4960) w0.3050
ECO-3#12 VREFP 10u to 1206   trk  VREFP          F.Cu          (145.9205, 110.4800) -> (145.9205, 111.4960) w0.2540
ECO-3#12 VREFP 10u to 1206   trk  VREFP          F.Cu          (149.7305, 110.4800) -> (149.7305, 111.4960) w0.2540
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (130.4900, 87.7215) -> (148.7020, 87.7215) w0.2540
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (148.7020, 87.7215) -> (148.8545, 87.8740) w0.2030
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (148.7780, 88.1535) -> (148.9560, 88.1280) w0.1525
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (148.8545, 87.8740) -> (148.9560, 88.0265) w0.2030
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (148.9560, 88.0265) -> (148.9560, 88.1280) w0.2030
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   F.Cu          (148.7780, 88.1535) -> (148.9560, 88.1280) w0.1525
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   F.Cu          (148.9560, 88.1280) -> (148.9560, 89.7535) w0.2030
ECO-5 BIAS feedback          via  BIAS_OUT_INT   (148.7780, 88.1535) d0.6095/0.3050
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) trk  VNEG5          B.Cu          (143.8250, 122.3165) -> (143.8250, 123.5865) w0.2030
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) trk  VNEG5          F.Cu          (143.9270, 122.3165) -> (144.1300, 122.3670) w0.2030
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) via  VNEG5          (139.1010, 122.9260) d0.6095/0.3050
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) via  VNEG5          (143.8250, 122.3165) d0.6095/0.3050
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) via  V_NLDO_IN      (141.0310, 122.6720) d0.6095/0.3050
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) trk  AVDD           F.Cu          (144.0410, 110.4800) -> (144.6890, 111.3435) w0.2030
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) trk  AVDD           F.Cu          (144.4145, 107.6480) -> (144.4145, 108.9050) w0.2540
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) trk  AVDD           F.Cu          (144.4170, 109.4640) -> (144.4170, 109.7690) w0.2030
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) via  AVDD           (144.6890, 111.3435) d0.6095/0.3050
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) via  AVDD           (145.0315, 112.7660) d0.6095/0.3050
S5_L5 repair: clearance Track+Via nets=AVDD,AVSS at (143.919,109.058) (144.415,107.648) trk  AVDD           F.Cu          (142.1615, 110.7595) -> (142.1615, 111.0895) w0.2540
S5_L5 repair: clearance Track+Via nets=AVDD,AVSS at (143.919,109.058) (144.415,107.648) via  AVDD           (142.1615, 110.4800) d0.6095/0.3050
S5_L5 repair: clearance Track+Via nets=AVDD,GND at (145.908,114.490) (146.111,115.103) via  AVDD           (144.1300, 116.8810) d0.6095/0.3050
drc_import repair: clearance AVDD,AVSS at (150.887,93.309) (151.407,92.700) trk  AVDD           F.Cu          (150.8865, 93.0050) -> (150.8865, 93.3095) w0.2030
drc_import repair: clearance AVDD,AVSS at (150.887,93.309) (151.407,92.700) via  AVDD           (150.8865, 93.3095) d0.6095/0.3050
eco_apply repair: eco_apply recorded touching AVDD at (149.108,109.159) trk  AVDD           F.Cu          (149.1085, 109.0070) -> (149.4080, 108.7020) w0.2540
eco_apply repair: eco_apply recorded touching AVDD at (149.108,109.159) trk  AVDD           F.Cu          (149.4080, 107.6480) -> (149.4080, 108.7020) w0.2540
eco_apply repair: eco_apply recorded touching AVDD at (149.108,109.159) via  AVDD           (149.1085, 109.1590) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching AVDD at (140.219,109.883) via  AVDD           (140.2820, 110.4800) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching AVDD at (140.463,93.691) via  AVDD           (140.5230, 93.1190) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching AVDD at (143.351,91.929) via  AVDD           (141.9965, 92.9795) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching AVDD at (143.351,91.929) via  AVDD           (143.4315, 92.7000) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching AVDD at (147.708,92.700) via  AVDD           (145.9970, 92.7000) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching AVDD at (147.708,92.700) via  AVDD           (148.2830, 92.7000) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching AVDD at (148.283,92.700) (147.708,92.700) trk  AVDD           F.Cu          (150.5815, 92.7000) -> (150.8865, 93.0050) w0.2030
viapad_fix repair: viapad_fix recorded touching BIAS_OUT_INT at (130.790,87.722) via  BIAS_OUT_INT   (130.4900, 87.7215) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN1N at (132.851,112.131) trk  IN1N           F.Cu          (132.4335, 112.1310) -> (133.5255, 112.1310) w0.2540
viapad_fix repair: viapad_fix recorded touching IN1N at (132.851,112.131) via  IN1N           (133.5255, 112.1310) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN2N at (132.851,109.134) trk  IN2N           F.Cu          (132.4335, 109.1340) -> (133.5255, 109.1340) w0.2540
viapad_fix repair: viapad_fix recorded touching IN2N at (132.851,109.134) via  IN2N           (133.5255, 109.1340) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN3N at (132.851,106.136) trk  IN3N           F.Cu          (132.4335, 106.1365) -> (133.5255, 106.1365) w0.2540
viapad_fix repair: viapad_fix recorded touching IN3N at (132.851,106.136) via  IN3N           (133.5255, 106.1365) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN4N at (132.851,103.139) trk  IN4N           F.Cu          (132.4335, 103.1395) -> (133.5255, 103.1395) w0.2540
viapad_fix repair: viapad_fix recorded touching IN4N at (132.851,103.139) via  IN4N           (133.5255, 103.1395) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN5N at (132.851,100.142) trk  IN5N           F.Cu          (132.4335, 100.1420) -> (133.5255, 100.1420) w0.2540
viapad_fix repair: viapad_fix recorded touching IN5N at (132.851,100.142) via  IN5N           (133.5255, 100.1420) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN6N at (132.851,97.145) trk  IN6N           F.Cu          (132.4335, 97.1450) -> (133.5255, 97.1450) w0.2540
viapad_fix repair: viapad_fix recorded touching IN6N at (132.851,97.145) via  IN6N           (133.5255, 97.1450) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN7N at (132.851,94.148) trk  IN7N           F.Cu          (132.4335, 94.1480) -> (133.5255, 94.1480) w0.2540
viapad_fix repair: viapad_fix recorded touching IN7N at (132.851,94.148) via  IN7N           (133.5255, 94.1480) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN8N at (132.851,91.150) trk  IN8N           F.Cu          (132.4335, 91.1505) -> (133.5255, 91.1505) w0.2540
viapad_fix repair: viapad_fix recorded touching IN8N at (132.851,91.150) via  IN8N           (133.5255, 91.1505) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching SRB1 at (130.600,89.238) via  SRB1           (130.1600, 89.1440) d0.6095/0.3050
```

### 追加（169 件）

```
ECO-1#1 TPS72325 EN          trk  VNEG5          B.Cu          (148.1922, 122.5099) -> (148.8545, 122.2150) w0.2030
ECO-1#1 TPS72325 EN          trk  VNEG5          F.Cu          (148.1922, 122.5099) -> (148.8545, 122.2150) w0.3048
ECO-1#1 TPS72325 EN          via  VNEG5          (148.1922, 122.5099) d0.6095/0.3050
ECO-1#1 TPS72325 EN          pad  V_NLDO_IN      TPS72325.3 (153.0500, 117.9120) 1.100x0.600
ECO-1#1 TPS72325 EN          trk  V_NLDO_IN      F.Cu          (153.0500, 117.9120) -> (153.0500, 118.8620) w0.2032
ECO-1#2 RESV1                trk  AVDD           F.Cu          (144.4145, 107.6480) -> (144.4145, 108.2993) w0.2540
ECO-1#2 RESV1                trk  AVDD           F.Cu          (144.4145, 107.6480) -> (144.4145, 108.3385) w0.2540
ECO-1#4/5 VCAP2, VCAP3       pad  AVSS           C_VCAP1.2 (152.2580, 113.5770) 1.150x1.800
ECO-1#4/5 VCAP2, VCAP3       pad  AVSS           C_VCAP1_H.2 (147.9120, 109.8460) 0.500x0.540
ECO-1#4/5 VCAP2, VCAP3       pad  AVSS           C_VCAP2.2 (149.5860, 109.1720) 0.500x0.540
ECO-1#4/5 VCAP2, VCAP3       pad  AVSS           C_VCAP3.2 (144.1180, 93.8420) 0.500x0.540
ECO-1#4/5 VCAP2, VCAP3       pad  AVSS           C_VCAP3_H.2 (145.9920, 94.4480) 0.500x0.540
ECO-1#4/5 VCAP2, VCAP3       pad  AVSS           C_VREFP_10n.2 (146.8100, 110.4800) 0.500x0.540
ECO-1#4/5 VCAP2, VCAP3       pad  AVSS           C_VREFP_10u.2 (150.9370, 108.7510) 1.150x1.800
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           B.Cu          (143.9190, 109.1845) -> (144.0790, 109.9720) w0.2540
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           B.Cu          (150.4088, 109.6313) -> (151.4960, 110.9880) w0.2540
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           B.Cu          (151.4960, 113.7820) -> (151.5692, 114.4782) w0.2540
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (143.9190, 107.6480) -> (143.9190, 109.1845) w0.2030
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (144.1180, 93.8420) -> (144.8285, 93.9190) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (145.9205, 112.7660) -> (146.1136, 113.3604) w0.3048
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (146.8090, 110.4800) -> (146.9115, 110.4800) w0.2030
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (146.9240, 109.7690) -> (146.9740, 110.4800) w0.2030
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (147.8638, 109.7690) -> (147.9120, 109.8460) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (148.8670, 112.7660) -> (148.9297, 113.3627) w0.3048
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (149.1499, 114.6452) -> (149.2100, 115.2170) w0.3048
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (149.2100, 114.5440) -> (149.3600, 115.0900) w0.2540
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (149.5860, 109.1720) -> (149.9085, 109.0070) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (149.9085, 108.8290) -> (150.9370, 108.7510) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (149.9085, 109.0070) -> (149.9210, 109.0070) w0.2030
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (149.9085, 109.0070) -> (150.4088, 109.6313) w0.3048
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (151.4960, 113.7820) -> (151.5692, 114.4782) w0.3048
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (151.7195, 113.2740) -> (152.2580, 113.5770) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (152.5128, 112.1693) -> (152.5755, 112.7660) w0.3048
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (143.9190, 109.1845) d0.6095/0.3050
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (146.1136, 113.3604) d0.6095/0.3050
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (148.9297, 113.3627) d0.6095/0.3050
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (149.1499, 114.6452) d0.6095/0.3050
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (150.4088, 109.6313) d0.6095/0.3050
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (151.5692, 114.4782) d0.6095/0.3050
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (152.5128, 112.1693) d0.6095/0.3050
ECO-1#4/5 VCAP2, VCAP3       pad  VCAP2          C_VCAP2.1 (148.7460, 109.1720) 0.500x0.540
ECO-1#4/5 VCAP2, VCAP3       pad  VCAP2          U_ADS.30 (148.9120, 107.6480) 0.280x1.800
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP2          F.Cu          (148.7460, 109.1720) -> (148.9120, 107.6480) w0.2032
ECO-1#4/5 VCAP2, VCAP3       pad  VCAP3          C_VCAP3.1 (144.1180, 94.6820) 0.500x0.540
ECO-1#4/5 VCAP2, VCAP3       pad  VCAP3          C_VCAP3_H.1 (146.8320, 94.4480) 0.500x0.540
ECO-1#4/5 VCAP2, VCAP3       pad  VCAP3          U_ADS.55 (146.9120, 96.5480) 0.280x1.800
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP3          B.Cu          (144.1180, 95.1900) -> (146.9120, 97.5640) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP3          B.Cu          (146.9120, 97.5640) -> (147.0047, 97.8493) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP3          F.Cu          (144.1180, 94.6040) -> (144.1180, 94.6820) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP3          F.Cu          (144.1180, 94.6820) -> (144.1180, 95.1900) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP3          F.Cu          (146.8320, 94.4480) -> (146.9120, 94.4480) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP3          F.Cu          (146.9120, 94.4480) -> (146.9120, 96.5480) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP3          F.Cu          (146.9120, 96.5480) -> (146.9120, 97.5640) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP3          F.Cu          (146.9120, 97.5640) -> (147.0047, 97.8493) w0.2540
ECO-1#4/5 VCAP2, VCAP3       via  VCAP3          (144.1180, 95.1900) d0.6096/0.3048
ECO-1#4/5 VCAP2, VCAP3       via  VCAP3          (147.0047, 97.8493) d0.6096/0.3048
ECO-3#11 VCAP1 to 1206       pad  AVSS           C_AVSS_B.1 (149.3600, 115.3680) 0.800x0.900
ECO-3#11 VCAP1 to 1206       trk  AVSS           F.Cu          (142.0988, 112.1693) -> (142.1615, 112.7660) w0.3048
ECO-3#11 VCAP1 to 1206       trk  AVSS           F.Cu          (148.3650, 116.5390) -> (148.4225, 115.9920) w0.3048
ECO-3#11 VCAP1 to 1206       trk  AVSS           F.Cu          (148.4225, 115.9920) -> (148.4225, 115.9920) w0.1525
ECO-3#11 VCAP1 to 1206       trk  AVSS           F.Cu          (148.4225, 115.9920) -> (148.4225, 115.9920) w0.2030
ECO-3#11 VCAP1 to 1206       trk  AVSS           F.Cu          (149.2100, 115.2170) -> (149.3600, 115.3670) w0.2030
ECO-3#11 VCAP1 to 1206       via  AVSS           (142.0988, 112.1693) d0.6095/0.3050
ECO-3#11 VCAP1 to 1206       via  AVSS           (148.3650, 116.5390) d0.6095/0.3050
ECO-3#11 VCAP1 to 1206       pad  VCAP1          C_VCAP1.1 (152.2580, 116.5270) 1.150x1.800
ECO-3#11 VCAP1 to 1206       pad  VCAP1          C_VCAP1_H.1 (147.9120, 109.0060) 0.500x0.540
ECO-3#11 VCAP1 to 1206       trk  VCAP1          B.Cu          (147.9095, 106.4070) -> (147.9095, 109.0070) w0.2540
ECO-3#11 VCAP1 to 1206       trk  VCAP1          B.Cu          (150.3020, 114.3410) -> (151.7500, 116.5270) w0.2032
ECO-3#11 VCAP1 to 1206       trk  VCAP1          B.Cu          (151.0500, 116.5270) -> (151.7500, 116.5270) w0.2032
ECO-3#11 VCAP1 to 1206       trk  VCAP1          F.Cu          (147.9095, 106.4070) -> (147.9095, 109.0070) w0.2540
ECO-3#11 VCAP1 to 1206       trk  VCAP1          F.Cu          (147.9095, 109.0070) -> (147.9120, 109.0060) w0.2032
ECO-3#11 VCAP1 to 1206       trk  VCAP1          F.Cu          (150.3020, 114.3410) -> (150.8100, 114.3410) w0.2032
ECO-3#11 VCAP1 to 1206       trk  VCAP1          F.Cu          (151.0500, 116.5270) -> (151.7500, 116.5270) w0.3048
ECO-3#11 VCAP1 to 1206       trk  VCAP1          F.Cu          (151.7500, 116.5270) -> (152.2580, 116.5270) w0.2032
ECO-3#11 VCAP1 to 1206       via  VCAP1          (147.9095, 106.4070) d0.6095/0.3050
ECO-3#11 VCAP1 to 1206       via  VCAP1          (150.3020, 114.3410) d0.6096/0.3048
ECO-3#11 VCAP1 to 1206       via  VCAP1          (151.0500, 116.5270) d0.6096/0.3048
ECO-3#12 VREFP 10u to 1206   pad  VREFP          C_VREFP_10n.1 (145.9700, 110.4800) 0.500x0.540
ECO-3#12 VREFP 10u to 1206   pad  VREFP          C_VREFP_10u.1 (150.9370, 111.7010) 1.150x1.800
ECO-3#12 VREFP 10u to 1206   trk  VREFP          F.Cu          (145.9205, 111.4960) -> (145.9705, 110.4800) w0.2540
ECO-3#12 VREFP 10u to 1206   trk  VREFP          F.Cu          (150.7403, 111.4960) -> (150.9370, 111.7010) w0.2032
ECO-5 BIAS feedback          pad  BIAS_OUT_INT   C_BIAS_INV.2 (142.4400, 90.4140) 0.500x0.540
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (130.7900, 87.7215) -> (148.7020, 87.7215) w0.2540
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (141.8852, 87.7215) -> (141.8852, 90.4140) w0.2032
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (148.7020, 87.7215) -> (148.9050, 88.7885) w0.2030
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (148.9050, 88.7885) -> (148.9050, 88.7885) w0.1525
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (148.9050, 88.7885) -> (148.9050, 88.7885) w0.2030
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   F.Cu          (141.8852, 90.4140) -> (142.4400, 90.4140) w0.2032
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   F.Cu          (148.9050, 88.7885) -> (148.9050, 88.7885) w0.1525
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   F.Cu          (148.9050, 88.7885) -> (148.9560, 89.7535) w0.2030
ECO-5 BIAS feedback          via  BIAS_OUT_INT   (141.8852, 90.4140) d0.6096/0.3048
ECO-5 BIAS feedback          via  BIAS_OUT_INT   (148.9050, 88.7885) d0.6095/0.3050
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) trk  VNEG5          B.Cu          (139.1010, 122.9260) -> (139.1794, 123.6719) w0.2030
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) trk  VNEG5          B.Cu          (143.8250, 122.5705) -> (143.8250, 123.5865) w0.2030
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) trk  VNEG5          F.Cu          (139.1010, 122.9260) -> (139.1794, 123.6719) w0.3048
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) trk  VNEG5          F.Cu          (143.8250, 122.5705) -> (144.1300, 122.3670) w0.2030
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) via  VNEG5          (139.1794, 123.6719) d0.6095/0.3050
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) via  VNEG5          (143.8250, 122.5705) d0.6095/0.3050
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) trk  V_NLDO_IN      B.Cu          (141.0310, 122.6720) -> (141.8380, 122.8435) w0.2030
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) trk  V_NLDO_IN      F.Cu          (141.0310, 122.6720) -> (141.8380, 122.8435) w0.3048
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) via  V_NLDO_IN      (141.8380, 122.8435) d0.6095/0.3050
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) trk  AVDD           B.Cu          (145.0315, 112.7660) -> (145.0445, 112.7660) w0.2030
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) trk  AVDD           B.Cu          (145.0315, 112.7660) -> (145.0445, 112.9185) w0.2030
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) trk  AVDD           B.Cu          (145.0315, 112.7660) -> (145.0591, 113.3403) w0.2030
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) trk  AVDD           F.Cu          (143.2920, 111.3435) -> (144.0410, 110.4800) w0.2030
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) trk  AVDD           F.Cu          (144.4145, 108.2993) -> (144.4145, 108.9050) w0.2540
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) trk  AVDD           F.Cu          (144.4145, 108.3385) -> (144.4145, 108.9050) w0.2540
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) trk  AVDD           F.Cu          (145.0315, 112.7660) -> (145.0591, 113.3403) w0.3048
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) via  AVDD           (143.2920, 111.3435) d0.6095/0.3050
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) via  AVDD           (145.0591, 113.3403) d0.6095/0.3050
S5_L5 repair: clearance Track+Via nets=AVDD,AVSS at (143.919,109.058) (144.415,107.648) trk  AVDD           F.Cu          (142.1615, 110.4800) -> (142.1615, 110.7595) w0.2540
S5_L5 repair: clearance Track+Via nets=AVDD,AVSS at (143.919,109.058) (144.415,107.648) trk  AVDD           F.Cu          (142.1615, 110.7595) -> (142.1615, 111.0050) w0.2540
S5_L5 repair: clearance Track+Via nets=AVDD,AVSS at (143.919,109.058) (144.415,107.648) trk  AVDD           F.Cu          (142.1615, 111.0050) -> (142.1615, 111.0895) w0.2540
S5_L5 repair: clearance Track+Via nets=AVDD,AVSS at (143.919,109.058) (144.415,107.648) via  AVDD           (142.1615, 111.0050) d0.6095/0.3050
S5_L5 repair: clearance Track+Via nets=AVDD,GND at (145.908,114.490) (146.111,115.103) trk  AVDD           B.Cu          (144.1300, 116.8810) -> (144.3307, 117.1039) w0.2030
S5_L5 repair: clearance Track+Via nets=AVDD,GND at (145.908,114.490) (146.111,115.103) trk  AVDD           F.Cu          (144.1300, 116.8810) -> (144.3307, 117.1039) w0.3048
S5_L5 repair: clearance Track+Via nets=AVDD,GND at (145.908,114.490) (146.111,115.103) via  AVDD           (144.3307, 117.1039) d0.6095/0.3050
drc_import repair: clearance AVDD,AVSS at (150.887,93.309) (151.407,92.700) trk  AVDD           F.Cu          (150.8865, 94.1985) -> (150.8865, 94.1985) w0.2030
drc_import repair: clearance AVDD,AVSS at (150.887,93.309) (151.407,92.700) via  AVDD           (150.8865, 94.1985) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching AVDD at (140.219,109.883) trk  AVDD           F.Cu          (140.2193, 109.8833) -> (140.2820, 110.4800) w0.3048
viapad_fix repair: viapad_fix recorded touching AVDD at (140.219,109.883) via  AVDD           (140.2193, 109.8833) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching AVDD at (140.463,93.691) trk  AVDD           F.Cu          (140.4629, 93.6908) -> (140.5230, 93.1190) w0.3048
viapad_fix repair: viapad_fix recorded touching AVDD at (140.463,93.691) via  AVDD           (140.4629, 93.6908) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching AVDD at (143.351,91.929) trk  AVDD           F.Cu          (141.9965, 92.9795) -> (142.5715, 92.9795) w0.3048
viapad_fix repair: viapad_fix recorded touching AVDD at (143.351,91.929) trk  AVDD           F.Cu          (143.3505, 91.9292) -> (143.4315, 92.7000) w0.3048
viapad_fix repair: viapad_fix recorded touching AVDD at (143.351,91.929) via  AVDD           (142.5715, 92.9795) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching AVDD at (143.351,91.929) via  AVDD           (143.3505, 91.9292) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching AVDD at (147.708,92.700) trk  AVDD           F.Cu          (145.9970, 92.7000) -> (146.0597, 93.2967) w0.3048
viapad_fix repair: viapad_fix recorded touching AVDD at (147.708,92.700) trk  AVDD           F.Cu          (147.7080, 92.7000) -> (148.2830, 92.7000) w0.3048
viapad_fix repair: viapad_fix recorded touching AVDD at (147.708,92.700) via  AVDD           (146.0597, 93.2967) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching AVDD at (147.708,92.700) via  AVDD           (147.7080, 92.7000) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching AVDD at (148.283,92.700) (147.708,92.700) trk  AVDD           F.Cu          (150.5815, 92.7000) -> (150.8865, 94.1985) w0.2030
viapad_fix repair: viapad_fix recorded touching BIAS_OUT_INT at (130.790,87.722) trk  BIAS_OUT_INT   F.Cu          (130.4900, 87.7215) -> (130.7900, 87.7215) w0.2032
viapad_fix repair: viapad_fix recorded touching BIAS_OUT_INT at (130.790,87.722) via  BIAS_OUT_INT   (130.7900, 87.7215) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN1N at (132.851,112.131) trk  IN1N           B.Cu          (132.8505, 112.1310) -> (133.5255, 112.1310) w0.2540
viapad_fix repair: viapad_fix recorded touching IN1N at (132.851,112.131) trk  IN1N           F.Cu          (132.4335, 112.1310) -> (132.8505, 112.1310) w0.2540
viapad_fix repair: viapad_fix recorded touching IN1N at (132.851,112.131) trk  IN1N           F.Cu          (132.8505, 112.1310) -> (133.5255, 112.1310) w0.2540
viapad_fix repair: viapad_fix recorded touching IN1N at (132.851,112.131) via  IN1N           (132.8505, 112.1310) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN2N at (132.851,109.134) trk  IN2N           B.Cu          (132.8505, 109.1340) -> (133.5255, 109.1340) w0.2540
viapad_fix repair: viapad_fix recorded touching IN2N at (132.851,109.134) trk  IN2N           F.Cu          (132.4335, 109.1340) -> (132.8505, 109.1340) w0.2540
viapad_fix repair: viapad_fix recorded touching IN2N at (132.851,109.134) trk  IN2N           F.Cu          (132.8505, 109.1340) -> (133.5255, 109.1340) w0.2540
viapad_fix repair: viapad_fix recorded touching IN2N at (132.851,109.134) via  IN2N           (132.8505, 109.1340) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN3N at (132.851,106.136) trk  IN3N           B.Cu          (132.8505, 106.1365) -> (133.5255, 106.1365) w0.2540
viapad_fix repair: viapad_fix recorded touching IN3N at (132.851,106.136) trk  IN3N           F.Cu          (132.4335, 106.1365) -> (132.8505, 106.1365) w0.2540
viapad_fix repair: viapad_fix recorded touching IN3N at (132.851,106.136) trk  IN3N           F.Cu          (132.8505, 106.1365) -> (133.5255, 106.1365) w0.2540
viapad_fix repair: viapad_fix recorded touching IN3N at (132.851,106.136) via  IN3N           (132.8505, 106.1365) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN4N at (132.851,103.139) trk  IN4N           B.Cu          (132.8505, 103.1395) -> (133.5255, 103.1395) w0.2540
viapad_fix repair: viapad_fix recorded touching IN4N at (132.851,103.139) trk  IN4N           F.Cu          (132.4335, 103.1395) -> (132.8505, 103.1395) w0.2540
viapad_fix repair: viapad_fix recorded touching IN4N at (132.851,103.139) trk  IN4N           F.Cu          (132.8505, 103.1395) -> (133.5255, 103.1395) w0.2540
viapad_fix repair: viapad_fix recorded touching IN4N at (132.851,103.139) via  IN4N           (132.8505, 103.1395) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN5N at (132.851,100.142) trk  IN5N           B.Cu          (132.8505, 100.1420) -> (133.5255, 100.1420) w0.2540
viapad_fix repair: viapad_fix recorded touching IN5N at (132.851,100.142) trk  IN5N           F.Cu          (132.4335, 100.1420) -> (132.8505, 100.1420) w0.2540
viapad_fix repair: viapad_fix recorded touching IN5N at (132.851,100.142) trk  IN5N           F.Cu          (132.8505, 100.1420) -> (133.5255, 100.1420) w0.2540
viapad_fix repair: viapad_fix recorded touching IN5N at (132.851,100.142) via  IN5N           (132.8505, 100.1420) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN6N at (132.851,97.145) trk  IN6N           B.Cu          (132.8505, 97.1450) -> (133.5255, 97.1450) w0.2540
viapad_fix repair: viapad_fix recorded touching IN6N at (132.851,97.145) trk  IN6N           F.Cu          (132.4335, 97.1450) -> (132.8505, 97.1450) w0.2540
viapad_fix repair: viapad_fix recorded touching IN6N at (132.851,97.145) trk  IN6N           F.Cu          (132.8505, 97.1450) -> (133.5255, 97.1450) w0.2540
viapad_fix repair: viapad_fix recorded touching IN6N at (132.851,97.145) via  IN6N           (132.8505, 97.1450) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN7N at (132.851,94.148) trk  IN7N           B.Cu          (132.8505, 94.1480) -> (133.5255, 94.1480) w0.2540
viapad_fix repair: viapad_fix recorded touching IN7N at (132.851,94.148) trk  IN7N           F.Cu          (132.4335, 94.1480) -> (132.8505, 94.1480) w0.2540
viapad_fix repair: viapad_fix recorded touching IN7N at (132.851,94.148) trk  IN7N           F.Cu          (132.8505, 94.1480) -> (133.5255, 94.1480) w0.2540
viapad_fix repair: viapad_fix recorded touching IN7N at (132.851,94.148) via  IN7N           (132.8505, 94.1480) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching IN8N at (132.851,91.150) trk  IN8N           B.Cu          (132.8505, 91.1505) -> (133.5255, 91.1505) w0.2540
viapad_fix repair: viapad_fix recorded touching IN8N at (132.851,91.150) trk  IN8N           F.Cu          (132.4335, 91.1505) -> (132.8505, 91.1505) w0.2540
viapad_fix repair: viapad_fix recorded touching IN8N at (132.851,91.150) trk  IN8N           F.Cu          (132.8505, 91.1505) -> (133.5255, 91.1505) w0.2540
viapad_fix repair: viapad_fix recorded touching IN8N at (132.851,91.150) via  IN8N           (132.8505, 91.1505) d0.6095/0.3050
viapad_fix repair: viapad_fix recorded touching SRB1 at (130.600,89.238) trk  SRB1           B.Cu          (130.1600, 89.1440) -> (130.6002, 89.2376) w0.2540
viapad_fix repair: viapad_fix recorded touching SRB1 at (130.600,89.238) trk  SRB1           F.Cu          (130.1600, 89.1440) -> (130.6002, 89.2376) w0.2032
viapad_fix repair: viapad_fix recorded touching SRB1 at (130.600,89.238) via  SRB1           (130.6002, 89.2376) d0.6095/0.3050
```

