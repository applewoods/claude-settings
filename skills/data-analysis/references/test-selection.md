# 통계 검정 선택·효과 크기·다중 비교·검정력

언제 읽나: 통계 검정을 고를 때, 효과 크기·CI·다중 비교 보정·표본 크기 계산이 필요할 때.
함수 이름은 scipy 1.17 / statsmodels 0.15 기준으로 확인했다.

## 1. 먼저 세 가지를 정한다
1. **질문**: 집단 차이 / 두 변수의 연관 / 예측 / 인과.
2. **설계**: 독립 집단 / 대응(같은 대상 전후, 짝지은 표본) / 반복측정·군집(한 대상이 여러 번).
3. **결과 변수 유형**: 연속 / 순서 / 이진·범주 / 횟수 / 생존(시간-사건).

반복측정·군집이면 아래 "단순 검정" 표보다 혼합효과 모형·GEE가 우선이다(`regression-mixed-causal.md`).
대안: 피험자별로 먼저 평균을 낸 뒤(분석 단위 = 피험자) 단순 검정을 한다. 단순하고 방어하기 쉽다.

## 2. 선택표 (단순 설계)
| 질문 · 설계 | 결과 유형 | 기본 선택 | 대안·주의 | Python |
|---|---|---|---|---|
| 두 독립 집단 | 연속 | **Welch t-검정** | 심한 치우침·이상치: Mann–Whitney U 또는 부트스트랩 CI(평균 차) | `scipy.stats.ttest_ind(a, b, equal_var=False)`, `mannwhitneyu` |
| 두 독립 집단 | 순서 | Mann–Whitney U | 분산이 다르면 U 검정은 "중앙값 비교"가 아님 → Brunner–Munzel | `mannwhitneyu`, `brunnermunzel` |
| 대응 두 조건 | 연속 | 대응 t-검정 | 차이가 심하게 치우침: Wilcoxon 부호순위 | `ttest_rel`, `wilcoxon` |
| 3개 이상 독립 집단 | 연속 | Welch ANOVA 또는 일원 ANOVA | 순위 기반: Kruskal–Wallis. 사후: Games–Howell(이분산), Tukey HSD(등분산) | `f_oneway`, `kruskal`, `scipy.stats.tukey_hsd` |
| 3개 이상 반복 조건 | 연속 | 혼합효과 모형(권장) 또는 반복측정 ANOVA | 구형성 위반 시 Greenhouse–Geisser 보정. 순위: Friedman | `statsmodels` `AnovaRM`, `friedmanchisquare` |
| 2요인 이상 | 연속 | 요인 ANOVA = 선형 모형 | 불균형 설계면 제곱합 유형(II/III)을 밝힌다 | `smf.ols` + `sm.stats.anova_lm(typ=2)` |
| 두 범주 변수 연관 | 범주 | 카이제곱 독립성 검정 | 기대빈도 < 5 칸이 많으면 Fisher 정확 검정(2×2) | `chi2_contingency`, `fisher_exact` |
| 대응 이진(같은 대상 두 조건) | 이진 | McNemar | 불일치 쌍이 적으면 exact=True | `statsmodels.stats.contingency_tables.mcnemar` |
| 두 연속 변수 연관 | 연속 | Pearson r(선형) | 단조·이상치: Spearman ρ, Kendall τ | `pearsonr`, `spearmanr`, `kendalltau` |
| 결과 예측·통제 | 연속 | 선형 회귀 | 진단 필수 | `smf.ols` |
| 결과 예측·통제 | 이진 | 로지스틱 회귀 | 완전 분리 시 패널티(Firth 등) | `smf.logit` |
| 결과 예측·통제 | 횟수 | 포아송 회귀 | 과산포면 음이항, 0 과다면 영과잉 모형 | `smf.poisson`, `smf.negativebinomial` |
| 시간-사건 | 생존 | Kaplan–Meier + 로그순위, Cox 회귀 | 비례위험 가정 확인 | `lifelines` [설치 필요] |

분포 가정을 피하고 싶으면 **순열 검정**(`scipy.stats.permutation_test`)과 **부트스트랩 CI**(`scipy.stats.bootstrap`)가 범용 대안이다. 단, 교환 가능성(exchangeability)이 성립하는 단위로 섞어야 한다(군집 데이터는 군집 단위로).

## 3. 가정 확인: 이렇게 판단한다
- **정규성 사전검정(Shapiro 등) → 결과에 따라 t/비모수 선택**하는 2단계 절차는 쓰지 않는다. 사전검정에 따라 검정을 고르는 조건부 절차는 이득이 없거나 1종 오류율을 왜곡한다는 시뮬레이션 결과가 있다(Rasch, Kubinger & Moder 2011). 설계 단계에서 데이터 성격(순서형? 상한·하한? 치우침?)으로 정한다.
- 등분산 검정(Levene) 후 Student/Welch 선택도 같은 문제(Zimmerman 2004) → Welch를 기본으로 쓴다(Delacre, Lakens & Leys 2017).
- t-검정의 정규성 가정은 **표본평균의 분포**에 대한 것이다. 집단당 n이 수십 이상이고 극단적 치우침이 없으면 대체로 강건하다. n이 작고(<15 정도) 치우치면 순위 검정·순열 검정.
- 가정은 그림으로 본다: 잔차 Q-Q plot, 잔차 vs 적합값, 집단별 상자·바이올린 그림. 큰 n에서 정규성 검정 p<0.05는 실질적 문제를 뜻하지 않는다.
- **독립성 가정이 가장 중요하고 가장 자주 깨진다.** 이것은 검정으로 확인하지 말고 설계로 확인한다(같은 사람·같은 세션·시간 인접 관측).

## 4. 효과 크기 (지표 이름을 밝힌다)
| 상황 | 효과 크기 | 메모 |
|---|---|---|
| 두 독립 집단 평균 | Cohen's d, 작은 n이면 Hedges' g | 어떤 SD로 나눴는지(합동 SD 등) 밝힌다 |
| 대응 두 조건 | d_z(차이의 평균/차이의 SD) 또는 d_av | 둘은 값이 다르므로 이름을 밝힌다 |
| 순위 검정 | 순위양분상관(rank-biserial) 또는 Cliff's δ | |
| ANOVA | partial η², 작은 표본은 ω²가 덜 편향 | |
| 범주 연관 | 오즈비·위험비(+CI), Cramér's V | |
| 상관·회귀 | r, R², 표준화하지 않은 계수(+단위) | 원 단위 계수가 해석에 더 유용한 경우가 많다 |

- 효과 크기에도 **CI**를 붙인다. 공식이 복잡하면 부트스트랩(BCa, `scipy.stats.bootstrap`, 기본 method='BCa').
- Cohen의 small/medium/large(0.2/0.5/0.8) 기준은 분야 맥락 없이 쓰지 않는다. 가능하면 원 단위(예: "정확도 2.1%p", "반응시간 35 ms")로 말한다.

## 5. 다중 비교
- 무엇을 하나의 "검정 묶음(family)"으로 볼지 먼저 정한다(예: 주 가설 3개 = 한 묶음, 탐색적 하위집단 분석 = 다른 묶음).
- **소수의 확증 가설 → Holm**(Bonferroni보다 항상 같거나 강력하고, FWER 통제).
- **다수의 탐색 비교(특성 수십~수천, 여러 채널·주파수) → Benjamini–Hochberg FDR.** 검정 간 음의 상관이 의심되면 Benjamini–Yekutieli.
- 사후(post-hoc) 쌍별 비교는 Tukey HSD·Games–Howell처럼 다중성을 내장한 방법을 쓰거나 Holm으로 보정한다.
- `statsmodels.stats.multitest.multipletests(pvals, method='holm' | 'fdr_bh' | 'fdr_by')`.
- 보고: 묶음 정의, 검정 수, 방법, 보정된 p.
- **분석 유연성(forking paths)**: 여러 전처리·이상치 규칙·공변량 조합을 시도한 뒤 좋은 것만 보고하면 보정으로도 못 고친다. 미리 정하거나, 시도한 경우를 모두 보고(민감도 분석)한다.

## 6. 검정력과 표본 크기
- 확증 연구면 **사전에** 계산한다: 효과 크기(선행 연구·최소 의미 있는 효과 SESOI), α, 목표 검정력(보통 0.8 또는 0.9).
  - `statsmodels.stats.power.TTestIndPower().solve_power(effect_size=0.5, alpha=0.05, power=0.8)` → 집단당 약 64명.
- 선행 연구의 효과 크기는 출판 편향으로 과대 추정되기 쉽다 → 보수적으로 잡는다.
- 혼합효과·복잡한 설계는 시뮬레이션으로 검정력을 계산한다.
- **사후 검정력(관측된 효과로 계산한 power)은 보고하지 않는다.** p-value의 단순 변환이라 새 정보가 없다(Hoenig & Heisey 2001). 대신 CI 폭이나 민감도 분석(이 n으로 탐지 가능한 최소 효과)을 보고한다.

## 7. "차이 없음"을 주장할 때
- 비유의 ≠ 동등. 동등성 범위(±Δ)를 미리 정하고 TOST(`statsmodels.stats.weightstats.ttost_ind`)나 90% CI가 범위 안인지로 보인다.

## 흔한 실수 (심사에서 지적받는 것)
- 한 사람의 여러 시행을 독립 표본으로 넣어 n을 부풀림(의사반복).
- "A 조건에서는 유의, B에서는 비유의 → A와 B가 다르다" 결론. 차이의 차이는 직접 검정(상호작용)해야 한다.
- 순서형(리커트 단일 문항)에 평균·t-검정을 쓰고 해석은 "중앙값"으로.
- p = 0.06을 "경향적 유의"로 포장.
- 같은 데이터로 가설을 만들고 같은 데이터로 검정.
