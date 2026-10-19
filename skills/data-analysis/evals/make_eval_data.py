"""data-analysis 평가 사례용 합성 데이터 생성 (표준 라이브러리만 사용, 시드 고정).

모든 데이터는 평가용으로 만든 가짜 데이터다. 각 파일에는 스킬이 잡아내야 할 함정이 하나씩 들어 있다.
  rt_repeated.csv      : 피험자 20명 × 조건 2 × 시행 15. 시행 단위 t-검정은 의사반복(pseudoreplication).
  sensor_windows.csv   : 피험자 8명의 시간 순 센서 윈도우 특징. 무작위 분할은 누수, 양성 비율 약 12%.
  model_results.csv    : 모델 A·B × 데이터셋 3 × 시드 5. 평균 차이는 작고 데이터셋마다 방향이 다름.
  survey_missing.csv   : 두 집단 설문 점수. 결측이 B 집단의 저점수 응답자에 몰려 있음(MNAR).
실행: python3 make_eval_data.py  (files/ 아래에 덮어쓰지 않고, 이미 있으면 건너뜀)
"""
import csv
import math
import os
import random

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files")


def write(name, header, rows):
    path = os.path.join(OUT, name)
    if os.path.exists(path):
        print(f"skip (exists): {name}")
        return
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"wrote {name}: {len(rows)} rows")


def rt_repeated(rng):
    rows = []
    for s in range(1, 21):
        subj = rng.gauss(0, 60)  # 피험자 간 차이가 큼
        for cond, effect in (("A", 0.0), ("B", 12.0)):  # 작은 조건 효과
            for t in range(1, 16):
                rt = 520 + subj + effect + rng.gauss(0, 40)
                rows.append([f"S{s:02d}", cond, t, round(rt, 1)])
    return rows


def sensor_windows(rng):
    rows = []
    for s in range(1, 9):
        offset = rng.gauss(0, 1.0)  # 피험자별 기준선 차이 → 무작위 분할 시 누수
        drift = 0.0
        for w in range(1, 151):
            drift += rng.gauss(0, 0.05)  # 시간에 따른 드리프트(자기상관)
            event = 1 if rng.random() < 0.12 else 0
            mean_acc = offset + drift + (0.6 if event else 0.0) + rng.gauss(0, 0.5)
            std_acc = abs(0.8 + 0.3 * offset + (0.4 if event else 0.0) + rng.gauss(0, 0.3))
            energy = mean_acc ** 2 + std_acc ** 2 + rng.gauss(0, 0.2)
            rows.append([f"P{s}", w, round(mean_acc, 4), round(std_acc, 4), round(energy, 4), event])
    return rows


def model_results(rng):
    rows = []
    true_gap = {"D1": 0.012, "D2": -0.004, "D3": 0.006}
    base = {"D1": 0.78, "D2": 0.71, "D3": 0.84}
    for d in ("D1", "D2", "D3"):
        for seed in range(5):
            shared = rng.gauss(0, 0.01)  # 같은 시드 = 같은 분할 → 쌍체 구조
            a = base[d] + shared + rng.gauss(0, 0.004)
            b = base[d] + true_gap[d] + shared + rng.gauss(0, 0.004)
            rows.append(["A", d, seed, round(a, 4)])
            rows.append(["B", d, seed, round(b, 4)])
    return rows


def survey_missing(rng):
    rows = []
    rid = 0
    for group, mu in (("A", 3.4), ("B", 3.1)):
        for _ in range(60):
            rid += 1
            score = min(5.0, max(1.0, rng.gauss(mu, 0.7)))
            age = rng.randint(20, 65)
            # B 집단에서 점수가 낮을수록 응답 누락이 많다
            p_miss = 0.03 if group == "A" else (0.45 if score < 2.8 else 0.08)
            shown = "" if rng.random() < p_miss else round(score, 2)
            rows.append([rid, group, age, shown])
    return rows


def sensor_windows_v2(rng):
    """피험자마다 event 비율과 기준선이 함께 다르다 → 무작위 분할이면 '누구인지'로 맞혀 점수가 크게 부푼다."""
    rows = []
    for s in range(1, 11):
        rate = 0.02 + 0.03 * (s - 1)          # 2% ~ 29%
        offset = 4.0 * rate + rng.gauss(0, 0.05)  # 기준선이 event 비율과 연동
        for w in range(1, 121):
            event = 1 if rng.random() < rate else 0
            mean_acc = offset + (0.25 if event else 0.0) + rng.gauss(0, 0.35)
            std_acc = abs(0.6 + 2.0 * rate + (0.15 if event else 0.0) + rng.gauss(0, 0.2))
            energy = mean_acc ** 2 + std_acc ** 2 + rng.gauss(0, 0.1)
            rows.append([f"P{s:02d}", w, round(mean_acc, 4), round(std_acc, 4), round(energy, 4), event])
    return rows


def task_time(rng):
    """오른쪽으로 크게 치우친 과제 수행 시간(로그정규). B는 꼬리가 더 길다."""
    rows = []
    pid = 0
    for group, mu, sigma, n in (("A", 3.3, 0.45, 35), ("B", 3.4, 0.75, 40)):
        for _ in range(n):
            pid += 1
            rows.append([pid, group, round(math.exp(rng.gauss(mu, sigma)), 1)])
    return rows


def site_outcomes(rng):
    """12개 기관 × 처치 여부. 실제 처치 효과는 어디에도 없다(우연한 명목 유의만 생김)."""
    rows = []
    pid = 0
    for site in range(1, 13):
        site_mean = 50 + rng.gauss(0, 4)
        for _ in range(34):
            pid += 1
            treat = rng.randint(0, 1)
            rows.append([pid, f"S{site:02d}", treat, round(site_mean + rng.gauss(0, 10), 1)])
    return rows


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    rng = random.Random(20261019)
    write("rt_repeated.csv", ["subject", "condition", "trial", "rt_ms"], rt_repeated(rng))
    write("sensor_windows.csv", ["subject", "window_idx", "mean_acc", "std_acc", "energy", "event"], sensor_windows(rng))
    write("model_results.csv", ["model", "dataset", "seed", "macro_f1"], model_results(rng))
    write("survey_missing.csv", ["respondent_id", "group", "age", "satisfaction"], survey_missing(rng))

    # v2 (2차 평가): 함정을 강화한 데이터. v1과 시드를 분리해 v1 파일은 그대로 재현된다.
    rng2 = random.Random(20261020)
    write("sensor_windows_v2.csv", ["subject", "window_idx", "mean_acc", "std_acc", "energy", "event"], sensor_windows_v2(rng2))
    write("task_time.csv", ["participant", "group", "task_time_s"], task_time(rng2))
    write("site_outcomes.csv", ["participant", "site", "treatment", "score"], site_outcomes(rng2))
