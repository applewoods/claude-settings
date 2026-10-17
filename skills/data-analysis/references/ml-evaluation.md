# ML/DL 평가 설계

언제 읽나: 학습·평가 계획을 세울 때(분할, CV, 튜닝, 베이스라인, 지표, 보정, 애블레이션, 오류 분석, 비용 보고). scikit-learn 1.9 기준으로 클래스 이름을 확인했다.

## 1. 분할 방식: "무엇으로 일반화하는가"가 정한다
| 일반화 대상 | 분할 | sklearn |
|---|---|---|
| 같은 분포의 새 샘플(i.i.d.) | 무작위(분류는 층화) | `train_test_split(stratify=y)`, `StratifiedKFold` |
| 새 사람·기기·문서 출처 | 그룹 분할 | `GroupKFold`, `StratifiedGroupKFold`, `GroupShuffleSplit`, `LeaveOneGroupOut` |
| 미래 시점 | 시간순 분할(+gap) | `TimeSeriesSplit(n_splits, gap=...)` |
| 미래 시점 + 새 사람 | 시간순과 그룹을 함께 | 직접 구현(피험자를 나눈 뒤 각 쪽에서 시간순) |

- 일반화 대상과 분할이 어긋나면 성능이 과대 추정된다. 논문에 "어떤 일반화를 평가했는지" 한 문장으로 쓴다.
- 데이터가 작을수록(수백 개 이하) 단일 홀드아웃 점수는 분산이 커서 믿기 어렵다 → 반복 CV.
- 층화는 분류에서 클래스 비율 유지용. 그룹 분할과 동시에 필요하면 `StratifiedGroupKFold`.
- `GroupKFold`는 그룹 수가 적으면 fold 간 분산이 크다. 그룹 수와 fold별 그룹 수를 보고한다.

## 2. 홀드아웃 · CV · 중첩 CV 선택
- **데이터가 크다(수만 이상)**: train/val/test 홀드아웃. 튜닝은 val, 최종 1회는 test.
- **데이터가 작거나 중간**: 테스트를 떼어 두고 train 안에서 CV로 튜닝 → test 1회. 또는
- **중첩 CV**: 바깥 루프는 성능 추정, 안쪽 루프는 튜닝. 바깥 fold마다 고른 하이퍼파라미터가 다를 수 있다(정상). 보고하는 점수는 바깥 fold 점수다. CV로 튜닝하고 같은 CV 점수를 보고하면 선택 편향으로 낙관적이다(Varma & Simon 2006; Cawley & Talbot 2010).
  - sklearn(그룹 없음): `cross_val_score(GridSearchCV(pipe, grid, cv=inner), X, y, cv=outer)`.
  - **그룹이 있으면 안쪽 CV에도 그룹이 전달돼야 한다.** sklearn 1.9에서 `cross_val_score(..., groups=g)`만 쓰면 안쪽 `GroupKFold`가 groups를 받지 못해 모든 fit이 실패한다(직접 확인). 방법: `sklearn.set_config(enable_metadata_routing=True)` 후 `cross_val_score(GridSearchCV(pipe, grid, cv=GroupKFold(3)), X, y, cv=GroupKFold(5), params={"groups": g})`. 더 단순하게는 바깥 fold 루프를 직접 쓰고 안쪽에서 `GridSearchCV(cv=GroupKFold()).fit(X_tr, y_tr, groups=g_tr)`.
- **딥러닝**: 보통 고정 val로 조기 종료·튜닝 + test 1회 + 여러 시드. 데이터가 작으면 fold × 시드 반복.
- 조기 종료 기준(epoch)도 하이퍼파라미터다. test로 정하지 않는다.

## 3. 하이퍼파라미터 탐색 공정성
- 제안 모델과 베이스라인 모두 **같은 탐색 예산**(시도 횟수 또는 GPU 시간), **같은 검증 방식**으로 튜닝한다. 베이스라인을 기본값·논문 보고값으로 두고 제안 모델만 튜닝한 비교는 심사에서 거절 사유가 된다.
- 탐색 공간(범위·분포), 방법(grid/random/Bayesian), 시도 횟수, 최종 선택값을 부록 표로 보고한다.
- 무작위 탐색은 같은 예산에서 grid보다 효율적인 경우가 많다(Bergstra & Bengio 2012).
- 탐색 중 val 점수를 수백 번 보면 val에도 과적합된다. 그래서 test는 따로 둔다.

## 4. 베이스라인 강도
- **하한 베이스라인**: `DummyClassifier(strategy="most_frequent" | "stratified")`, `DummyRegressor`, 시계열은 naive/계절 naive. 이걸 못 이기면 파이프라인 버그부터 의심한다.
- **강한 베이스라인**: 해당 데이터 유형의 현재 표준.
  - 표 데이터: 튜닝한 GBDT(XGBoost·LightGBM·CatBoost 또는 `HistGradientBoostingClassifier`). 표 데이터에서 GBDT가 딥러닝보다 강한 경우가 많다는 벤치마크가 있다(Grinsztajn et al. 2022).
  - 선형 모델(정규화 로지스틱·릿지)도 넣는다 — 해석 가능한 기준점이고 의외로 강하다.
  - 텍스트·시계열은 `nlp.md`, `timeseries.md`.
- 최신 방법(SOTA)과 비교하면 **같은 분할·같은 전처리**로 다시 돌린다. 논문 보고값을 그대로 가져오면 그렇다고 표시한다.

## 5. 지표 선택
**분류**
- 불균형이면 accuracy 단독 금지. 다수 클래스만 찍어도 높게 나온다.
- **PR-AUC(average precision)**: 양성이 드물 때 ROC-AUC보다 정보가 많다. 무작위 기준선은 양성 비율이다(0.5가 아님, Saito & Rehmsmeier 2015). `average_precision_score`.
- ROC-AUC: 순위 품질. 불균형에서도 쓸 수 있지만 낙관적으로 보일 수 있어 PR-AUC와 함께.
- 임계값 의존 지표(F1, precision, recall): **임계값을 val에서 정한다**(`TunedThresholdClassifierCV` 또는 직접). test에서 최적 임계값을 고르면 누수.
- balanced accuracy, MCC(`matthews_corrcoef`): 불균형에 덜 민감한 단일 요약.
- 다중 클래스: macro(클래스 동등) vs weighted(빈도 가중) vs micro를 밝힌다. 클래스별 표와 혼동 행렬을 함께.
- 의료·안전 문제는 민감도·특이도를 운영 임계값에서 보고한다.

**불균형 처리**
- 먼저 지표·임계값으로 해결을 시도한다. 리샘플링(SMOTE 등)은 **학습 fold 안에서만**(`imblearn.pipeline.Pipeline` [설치 필요]). 리샘플링·클래스 가중치는 확률 보정을 깨뜨릴 수 있다(van den Goorbergh et al. 2022) → 확률을 쓰면 보정을 다시 확인.

**회귀**
- MAE(이상치에 강건, 원 단위), RMSE(큰 오차에 민감), R²(분산 비율, 데이터셋 간 비교 불가), MAPE(실제값 0 근처에서 폭발 — 피한다).

**확률 보정(calibration)**
- 예측 확률을 의사결정·위험도로 쓰면 필수. 정확도·AUC가 높아도 보정은 나쁠 수 있다.
- reliability diagram(`sklearn.calibration.calibration_curve`, `CalibrationDisplay`) + Brier score(`brier_score_loss`) + log loss.
- ECE는 구간(bin) 수·방식에 따라 값이 달라진다 → 설정을 밝히고 단독으로 쓰지 않는다.
- 보정 방법: `CalibratedClassifierCV(method="sigmoid" | "isotonic")`, DL은 temperature scaling. 보정용 데이터는 학습·테스트와 분리. isotonic은 작은 데이터에서 과적합 위험.

## 6. 애블레이션
- 주장하는 구성 요소마다 "그것만 뺀(또는 단순 대체한)" 버전을 **같은 시드·같은 분할·같은 튜닝 예산**으로 돌린다.
- 구성 요소가 상호작용하면 하나씩 빼기만으로는 부족하다 → 하나씩 더하기도 함께 보거나 상호작용을 언급한다.
- 애블레이션 차이도 시드 분산과 비교한다(`model-comparison.md`). 차이가 시드 SD보다 작으면 "기여한다"고 쓰지 않는다.
- 파라미터 수가 늘어서 좋아진 것인지 구분하려면 파라미터 수를 맞춘 대조군을 둔다.

## 7. 오류 분석
- 평균 점수만 보지 않는다. 클래스별·하위집단별(피험자, 기기, 길이, 시간대, 출처)·난이도별 성능을 본다.
- 틀린 사례를 무작위로 수십 개 직접 읽고 유형을 분류한다(텍스트·이미지에서 특히).
- 하위집단 성능 차이를 주장하면 그 차이도 CI·다중 비교 보정 대상이다.
- 공정성이 문제가 되는 데이터(사람 대상)는 집단별 지표 차이를 보고한다.

## 8. 연산 비용 보고
- 하드웨어(GPU 종류·개수), 학습 시간, 추론 지연·처리량, 파라미터 수, (가능하면) FLOPs.
- **튜닝·실패한 실행을 포함한 전체 연산량**도 부록에 적는다. 제안 방법만 많은 연산을 썼으면 비교의 공정성 문제다.
