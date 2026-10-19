# 실험 결과 (최종)

Table 2. Macro-F1 (mean ± SD over 5 seeds), subject-wise split

| Method | SisFall | MobiAct |
|---|---|---|
| Threshold (Bourke-style) | 0.712 ± 0.000 | 0.684 ± 0.000 |
| CNN-LSTM | 0.861 ± 0.011 | 0.832 ± 0.014 |
| Ours (contrastive + linear head) | 0.893 ± 0.009 | 0.845 ± 0.017 |

Table 3. False alarms per 24h of daily-living recording (lower is better)

| Method | Daily-living set (n = 12 participants) |
|---|---|
| CNN-LSTM | 4.1 |
| Ours | 3.7 |

Table 4. Ablation on SisFall (Macro-F1, mean ± SD over 5 seeds)

| Variant | Macro-F1 |
|---|---|
| Ours (full) | 0.893 ± 0.009 |
| w/o contrastive pretraining (random init + linear head) | 0.802 ± 0.015 |
| w/o subject-wise negative sampling | 0.884 ± 0.012 |

# 메모
- 모델 크기 0.4M params
- 통계 검정은 아직 안 함
