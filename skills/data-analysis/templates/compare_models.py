"""두 방법의 쌍체 비교. 같은 (seed, fold)에서 나온 점수끼리 짝짓는다.

- corrected_resampled_ttest: 반복 CV/반복 홀드아웃 점수용, Nadeau & Bengio(2003) 분산 보정.
  일반 쌍체 t-검정은 fold들이 학습 데이터를 공유해 너무 낙관적이다.
- paired_bootstrap_ci: 고정 test 세트에서 샘플 단위 예측으로 지표 차이의 CI.
"""
import warnings

import numpy as np
from scipy import stats


def corrected_resampled_ttest(a, b, n_train: int, n_test: int, alpha: float = 0.05):
    """a, b: 같은 순서의 (seed, fold)별 점수 J개. 반환: 평균 차, CI, t, p(양측)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.ndim != 1 or a.shape != b.shape:  # (5,)와 (5,1)이 브로드캐스팅돼 25쌍이 되는 사고 방지
        raise ValueError(f"a, b는 같은 길이의 1차원이어야 한다: {a.shape} vs {b.shape}")
    if a.size < 2 or not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise ValueError("유한한 점수가 2쌍 이상 필요하다")
    if n_train <= 0 or n_test <= 0:
        raise ValueError("n_train, n_test는 양수(fold 하나의 학습·평가 샘플 수)")
    d = a - b
    J = d.size
    var = d.var(ddof=1) * (1 / J + n_test / n_train)
    if var == 0:
        raise ValueError("차이의 분산이 0이다 — 점수가 짝지어졌는지 확인")
    t = d.mean() / np.sqrt(var)
    p = 2 * stats.t.sf(abs(t), df=J - 1)
    half = stats.t.ppf(1 - alpha / 2, df=J - 1) * np.sqrt(var)
    return {"mean_diff": d.mean(), "ci": (d.mean() - half, d.mean() + half), "t": t, "p": p, "J": J}


def paired_bootstrap_ci(y_true, pred_a, pred_b, metric, n_boot: int = 2000, seed: int = 0, alpha: float = 0.05):
    """같은 test 샘플을 재추출해 metric(A) - metric(B)의 백분위 CI. 샘플 = 첫 번째 축.
    그룹(피험자 등)이 있으면 그룹 단위로 재추출해야 한다(이 함수는 샘플 단위).
    재표본에서 지표가 정의되지 않으면(AUC인데 한 클래스만 뽑힘 → NaN·오류) 그 재표본은 버리고 개수를 반환한다.
    버린 비율이 크면(양성이 매우 적음) 이 CI는 믿을 수 없다 → 오류로 멈춘다."""
    rng = np.random.default_rng(seed)
    y_true, pred_a, pred_b = map(np.asarray, (y_true, pred_a, pred_b))
    n = len(y_true)
    if len(pred_a) != n or len(pred_b) != n:
        raise ValueError("y_true, pred_a, pred_b의 샘플 수가 다르다")
    diffs = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        try:
            with warnings.catch_warnings():  # 정의 안 되는 재표본의 경고는 skipped 수로 대신 보고
                warnings.simplefilter("ignore")
                d = metric(y_true[idx], pred_a[idx]) - metric(y_true[idx], pred_b[idx])
        except ValueError:
            continue
        if np.isfinite(d):
            diffs.append(d)
    skipped = n_boot - len(diffs)
    if skipped > 0.05 * n_boot:
        raise ValueError(f"재표본 {skipped}/{n_boot}개에서 지표가 정의되지 않음 — 표본·양성 수가 너무 적다")
    obs = metric(y_true, pred_a) - metric(y_true, pred_b)
    lo, hi = np.quantile(diffs, [alpha / 2, 1 - alpha / 2])
    return {"diff": obs, "ci": (lo, hi), "n_valid": len(diffs), "skipped": skipped}


if __name__ == "__main__":
    from sklearn.datasets import make_classification
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score
    from sklearn.model_selection import RepeatedStratifiedKFold, train_test_split

    X, y = make_classification(n_samples=600, n_features=20, n_informative=6, random_state=0)
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=2, random_state=0)  # 분할도 반복
    sa, sb = [], []
    for tr, te in cv.split(X, y):  # 같은 fold에서 두 모델 → 쌍체
        sa.append(f1_score(y[te], RandomForestClassifier(random_state=0).fit(X[tr], y[tr]).predict(X[te])))
        sb.append(f1_score(y[te], LogisticRegression(max_iter=1000).fit(X[tr], y[tr]).predict(X[te])))
    r = corrected_resampled_ttest(sa, sb, n_train=len(tr), n_test=len(te))
    naive_p = stats.ttest_rel(sa, sb).pvalue
    print(f"corrected: diff={r['mean_diff']:.4f} CI=({r['ci'][0]:.4f}, {r['ci'][1]:.4f}) p={r['p']:.4f} | naive paired p={naive_p:.4f}")

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=0, stratify=y)
    pa = RandomForestClassifier(random_state=0).fit(Xtr, ytr).predict(Xte)
    pb = LogisticRegression(max_iter=1000).fit(Xtr, ytr).predict(Xte)
    print("bootstrap:", paired_bootstrap_ci(yte, pa, pb, f1_score))
