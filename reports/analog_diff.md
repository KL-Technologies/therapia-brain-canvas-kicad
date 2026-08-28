# アナログ配線の差分（S7b）

取り込み直後の基板（git `22513e4`）と現在の基板を、アナログ 40 ネットについて 1 アイテムずつ突き合わせた結果。

`kicad_pcb` の uuid は S5 で 2,625 個を採番し直しているので**幾何（ネット・層・座標・寸法）を鍵に**比較している。uuid で突き合わせると全アイテムが「変更」に見える。

| | |
|---|---|
| アナログ系アイテム | 770 → 808 |
| 差分 | 120 |
| 説明できない差分 | **0** |
| 入力・電極ネットの差分 | **0** |

## 触っていないことを要求するネット

`IN1P`〜`IN8N`（差動 8 対）、`SRB1`、`*_ELEC` 11 本 ＝ コネクタから ADC までの信号路。**差分 0 件**

つまり **1 件も無い**。S4a〜S7a の修理はどれも入力系の銅に触れていない。

## 差分の内訳

| 由来 | 件数 |
|---|---|
| ECO-1#1 TPS72325 EN | 2 |
| ECO-1#2 RESV1 | 3 |
| ECO-1#4/5 VCAP2, VCAP3 | 46 |
| ECO-3#11 VCAP1 to 1206 | 21 |
| ECO-3#12 VREFP 10u to 1206 | 9 |
| ECO-5 BIAS feedback | 17 |
| S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) | 6 |
| S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) | 7 |
| drc_import repair: clearance AVDD,AVSS at (150.887,93.309) (151.407,92.700) | 6 |
| eco_apply repair: eco_apply recorded touching AVDD at (149.108,109.159) | 3 |

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

### 削除（38 件）

```
ECO-1#2 RESV1                pad  AVDD           U_ADS.31 (149.4120, 107.6480) 0.280x1.800
ECO-1#4/5 VCAP2, VCAP3       pad  AVSS           C_VCAP1.2 (151.9420, 112.7660) 0.800x0.900
ECO-1#4/5 VCAP2, VCAP3       pad  AVSS           C_VREFP_10n.2 (146.7600, 110.4800) 0.500x0.540
ECO-1#4/5 VCAP2, VCAP3       pad  AVSS           C_VREFP_10u.2 (151.1290, 110.4800) 0.800x0.900
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           B.Cu          (143.9165, 109.2100) -> (144.0790, 109.9720) w0.2540
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (143.9190, 107.6480) -> (143.9190, 109.0575) w0.2030
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (146.7590, 110.4800) -> (146.9115, 110.4800) w0.2030
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (146.9240, 109.7690) -> (146.9240, 110.4800) w0.2030
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (149.2100, 114.5440) -> (149.2100, 115.0900) w0.2540
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (143.9190, 109.0575) d0.6095/0.3050
ECO-3#11 VCAP1 to 1206       pad  AVSS           C_AVSS_B.1 (149.2100, 115.3680) 0.800x0.900
ECO-3#11 VCAP1 to 1206       trk  AVSS           F.Cu          (148.2955, 116.1190) -> (148.4480, 116.2330) w0.1525
ECO-3#11 VCAP1 to 1206       trk  AVSS           F.Cu          (148.4480, 115.9790) -> (148.4480, 116.2330) w0.2030
ECO-3#11 VCAP1 to 1206       trk  AVSS           F.Cu          (149.2100, 115.2170) -> (149.2100, 115.3670) w0.2030
ECO-3#11 VCAP1 to 1206       via  AVSS           (148.2955, 116.1190) d0.6095/0.3050
ECO-3#11 VCAP1 to 1206       pad  VCAP1          C_VCAP1.1 (150.5420, 112.7660) 0.800x0.900
ECO-3#12 VREFP 10u to 1206   pad  VREFP          C_VREFP_10n.1 (145.9200, 110.4800) 0.500x0.540
ECO-3#12 VREFP 10u to 1206   pad  VREFP          C_VREFP_10u.1 (149.7290, 110.4800) 0.800x0.900
ECO-3#12 VREFP 10u to 1206   trk  VREFP          F.Cu          (145.9205, 110.4800) -> (145.9205, 111.4960) w0.2540
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (148.7020, 87.7215) -> (148.8545, 87.8740) w0.2030
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (148.7780, 88.1535) -> (148.9560, 88.1280) w0.1525
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (148.8545, 87.8740) -> (148.9560, 88.0265) w0.2030
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (148.9560, 88.0265) -> (148.9560, 88.1280) w0.2030
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   F.Cu          (148.7780, 88.1535) -> (148.9560, 88.1280) w0.1525
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   F.Cu          (148.9560, 88.1280) -> (148.9560, 89.7535) w0.2030
ECO-5 BIAS feedback          via  BIAS_OUT_INT   (148.7780, 88.1535) d0.6095/0.3050
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) trk  VNEG5          B.Cu          (143.8250, 122.3165) -> (143.8250, 123.5865) w0.2030
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) trk  VNEG5          F.Cu          (143.9270, 122.3165) -> (144.1300, 122.3670) w0.2030
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) via  VNEG5          (143.8250, 122.3165) d0.6095/0.3050
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) trk  AVDD           F.Cu          (144.0410, 110.4800) -> (144.6890, 111.3435) w0.2030
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) trk  AVDD           F.Cu          (144.4145, 107.6480) -> (144.4145, 108.9050) w0.2540
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) via  AVDD           (144.6890, 111.3435) d0.6095/0.3050
drc_import repair: clearance AVDD,AVSS at (150.887,93.309) (151.407,92.700) trk  AVDD           F.Cu          (150.5815, 92.7000) -> (150.8865, 93.0050) w0.2030
drc_import repair: clearance AVDD,AVSS at (150.887,93.309) (151.407,92.700) trk  AVDD           F.Cu          (150.8865, 93.0050) -> (150.8865, 93.3095) w0.2030
drc_import repair: clearance AVDD,AVSS at (150.887,93.309) (151.407,92.700) via  AVDD           (150.8865, 93.3095) d0.6095/0.3050
eco_apply repair: eco_apply recorded touching AVDD at (149.108,109.159) trk  AVDD           F.Cu          (149.1085, 109.0070) -> (149.4080, 108.7020) w0.2540
eco_apply repair: eco_apply recorded touching AVDD at (149.108,109.159) trk  AVDD           F.Cu          (149.4080, 107.6480) -> (149.4080, 108.7020) w0.2540
eco_apply repair: eco_apply recorded touching AVDD at (149.108,109.159) via  AVDD           (149.1085, 109.1590) d0.6095/0.3050
```

### 追加（75 件）

```
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
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (141.2090, 93.9190) -> (141.2090, 95.4440) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (141.2090, 95.4440) -> (141.8320, 95.4440) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (143.9190, 107.6480) -> (143.9190, 109.1845) w0.2030
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (144.1180, 93.8420) -> (144.8285, 93.9190) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (146.8090, 110.4800) -> (146.9115, 110.4800) w0.2030
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (146.9240, 109.7690) -> (146.9740, 110.4800) w0.2030
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (147.8638, 109.7690) -> (147.9120, 109.8460) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (149.2100, 114.5440) -> (149.3600, 115.0900) w0.2540
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (149.5860, 109.1720) -> (149.9085, 109.0070) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (149.9085, 108.8290) -> (150.9370, 108.7510) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  AVSS           F.Cu          (151.7195, 113.2740) -> (152.2580, 113.5770) w0.2032
ECO-1#4/5 VCAP2, VCAP3       via  AVSS           (143.9190, 109.1845) d0.6095/0.3050
ECO-1#4/5 VCAP2, VCAP3       pad  VCAP2          C_VCAP2.1 (148.7460, 109.1720) 0.500x0.540
ECO-1#4/5 VCAP2, VCAP3       pad  VCAP2          U_ADS.30 (148.9120, 107.6480) 0.280x1.800
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP2          F.Cu          (148.7460, 109.1720) -> (148.9120, 107.6480) w0.2032
ECO-1#4/5 VCAP2, VCAP3       pad  VCAP3          C_VCAP3.1 (144.1180, 94.6820) 0.500x0.540
ECO-1#4/5 VCAP2, VCAP3       pad  VCAP3          C_VCAP3_H.1 (146.8320, 94.4480) 0.500x0.540
ECO-1#4/5 VCAP2, VCAP3       pad  VCAP3          U_ADS.55 (146.9120, 96.5480) 0.280x1.800
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP3          B.Cu          (144.1180, 95.1900) -> (146.9120, 97.5640) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP3          F.Cu          (144.1180, 94.6040) -> (144.1180, 94.6820) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP3          F.Cu          (144.1180, 94.6820) -> (144.1180, 95.1900) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP3          F.Cu          (146.8320, 94.4480) -> (146.9120, 94.4480) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP3          F.Cu          (146.9120, 94.4480) -> (146.9120, 96.5480) w0.2032
ECO-1#4/5 VCAP2, VCAP3       trk  VCAP3          F.Cu          (146.9120, 96.5480) -> (146.9120, 97.5640) w0.2032
ECO-1#4/5 VCAP2, VCAP3       via  VCAP3          (144.1180, 95.1900) d0.6096/0.3048
ECO-1#4/5 VCAP2, VCAP3       via  VCAP3          (146.9120, 97.5640) d0.6096/0.3048
ECO-3#11 VCAP1 to 1206       pad  AVSS           C_AVSS_B.1 (149.3600, 115.3680) 0.800x0.900
ECO-3#11 VCAP1 to 1206       trk  AVSS           F.Cu          (148.4225, 115.9920) -> (148.4225, 115.9920) w0.1525
ECO-3#11 VCAP1 to 1206       trk  AVSS           F.Cu          (148.4225, 115.9920) -> (148.4225, 115.9920) w0.2030
ECO-3#11 VCAP1 to 1206       trk  AVSS           F.Cu          (149.2100, 115.2170) -> (149.3600, 115.3670) w0.2030
ECO-3#11 VCAP1 to 1206       via  AVSS           (148.4225, 115.9920) d0.6095/0.3050
ECO-3#11 VCAP1 to 1206       pad  VCAP1          C_VCAP1.1 (152.2580, 116.5270) 1.150x1.800
ECO-3#11 VCAP1 to 1206       pad  VCAP1          C_VCAP1_H.1 (147.9120, 109.0060) 0.500x0.540
ECO-3#11 VCAP1 to 1206       trk  VCAP1          B.Cu          (150.3020, 114.3410) -> (151.7500, 116.5270) w0.2032
ECO-3#11 VCAP1 to 1206       trk  VCAP1          F.Cu          (147.9095, 109.0070) -> (147.9120, 109.0060) w0.2032
ECO-3#11 VCAP1 to 1206       trk  VCAP1          F.Cu          (150.3020, 114.3410) -> (150.8100, 114.3410) w0.2032
ECO-3#11 VCAP1 to 1206       trk  VCAP1          F.Cu          (151.7500, 116.5270) -> (152.2580, 116.5270) w0.2032
ECO-3#11 VCAP1 to 1206       via  VCAP1          (150.3020, 114.3410) d0.6096/0.3048
ECO-3#11 VCAP1 to 1206       via  VCAP1          (151.7500, 116.5270) d0.6096/0.3048
ECO-3#12 VREFP 10u to 1206   pad  VREFP          C_VREFP_10n.1 (145.9700, 110.4800) 0.500x0.540
ECO-3#12 VREFP 10u to 1206   pad  VREFP          C_VREFP_10u.1 (150.9370, 111.7010) 1.150x1.800
ECO-3#12 VREFP 10u to 1206   trk  VREFP          F.Cu          (145.9205, 111.4960) -> (145.9705, 110.4800) w0.2540
ECO-3#12 VREFP 10u to 1206   trk  VREFP          F.Cu          (150.7403, 111.4960) -> (150.9370, 111.7010) w0.2032
ECO-5 BIAS feedback          pad  BIAS_OUT_INT   C_BIAS_INV.2 (142.4400, 90.4140) 0.500x0.540
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (141.8852, 87.7215) -> (141.8852, 90.4140) w0.2032
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (148.7020, 87.7215) -> (148.9050, 88.7885) w0.2030
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (148.9050, 88.7885) -> (148.9050, 88.7885) w0.1525
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   B.Cu          (148.9050, 88.7885) -> (148.9050, 88.7885) w0.2030
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   F.Cu          (141.8852, 90.4140) -> (142.4400, 90.4140) w0.2032
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   F.Cu          (148.9050, 88.7885) -> (148.9050, 88.7885) w0.1525
ECO-5 BIAS feedback          trk  BIAS_OUT_INT   F.Cu          (148.9050, 88.7885) -> (148.9560, 89.7535) w0.2030
ECO-5 BIAS feedback          via  BIAS_OUT_INT   (141.8852, 90.4140) d0.6096/0.3048
ECO-5 BIAS feedback          via  BIAS_OUT_INT   (148.9050, 88.7885) d0.6095/0.3050
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) trk  VNEG5          B.Cu          (143.8250, 122.5705) -> (143.8250, 123.5865) w0.2030
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) trk  VNEG5          F.Cu          (143.8250, 122.5705) -> (144.1300, 122.3670) w0.2030
S5_L1 repair: clearance Track+Via nets=VNEG5,V_NLDO_IN at (141.285,121.961) (143.825,122.317) via  VNEG5          (143.8250, 122.5705) d0.6095/0.3050
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) trk  AVDD           F.Cu          (143.2920, 111.3435) -> (144.0410, 110.4800) w0.2030
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) trk  AVDD           F.Cu          (144.4145, 108.2993) -> (144.4145, 108.9050) w0.2540
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) trk  AVDD           F.Cu          (144.4145, 108.3385) -> (144.4145, 108.9050) w0.2540
S5_L2 repair: clearance Track+Via nets=AVDD,GND at (144.689,111.344) (145.315,110.760) via  AVDD           (143.2920, 111.3435) d0.6095/0.3050
drc_import repair: clearance AVDD,AVSS at (150.887,93.309) (151.407,92.700) trk  AVDD           F.Cu          (150.5815, 92.7000) -> (150.8865, 94.1985) w0.2030
drc_import repair: clearance AVDD,AVSS at (150.887,93.309) (151.407,92.700) trk  AVDD           F.Cu          (150.8865, 94.1985) -> (150.8865, 94.1985) w0.2030
drc_import repair: clearance AVDD,AVSS at (150.887,93.309) (151.407,92.700) via  AVDD           (150.8865, 94.1985) d0.6095/0.3050
```

