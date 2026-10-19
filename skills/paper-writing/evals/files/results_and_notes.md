<!-- 평가용 자료. 수치는 평가를 위해 만든 가상 값이다. -->

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

# 내 메모
- 교수님이 초록에 "false alarm 15% 감소"를 넣자고 하심
- 기여: 손목 가속도계에 contrastive pretraining 적용, 경량 모델(0.4M params)
- 통계 검정은 아직 안 함
