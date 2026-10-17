"""시드·fold별 원 점수(long 형식) → 방법별 평균 ± SD 표(CSV + 마크다운).

입력 CSV 열: method, seed, fold, <지표들...>   (fold가 없으면 0으로)
사용: python aggregate_results.py results/.../metrics.csv --out results/.../summary
빠진 실행·중복·NaN이 있으면 경고하고, 지표별 유효 n을 표에 따로 적는다(조용히 평균에서 빠지지 않게).
"""
import argparse

import pandas as pd


def check_runs(df: pd.DataFrame, metrics: list[str]) -> list[str]:
    """예상 실행(모든 method × 등장한 seed×fold 조합) 대비 누락·중복·NaN 경고 목록."""
    warns = []
    dup = df.duplicated(["method", "seed", "fold"]).sum()
    if dup:
        warns.append(f"중복 (method, seed, fold) {dup}행")
    expected = set(map(tuple, df[["seed", "fold"]].drop_duplicates().values.tolist()))
    for m, g in df.groupby("method", sort=False):
        missing = expected - set(map(tuple, g[["seed", "fold"]].values.tolist()))
        if missing:
            warns.append(f"{m}: 실행 누락 {sorted(missing)}")
        for k in metrics:
            n_nan = g[k].isna().sum()
            if n_nan:
                warns.append(f"{m}: {k} NaN {n_nan}개(평균에서 제외됨)")
    return warns


def summarize(df: pd.DataFrame, metrics: list[str], digits: int = 3):
    g = df.groupby("method", sort=False)[metrics]
    mean, sd, n = g.mean(), g.std(ddof=1), g.count()
    raw = pd.concat([mean.add_suffix("_mean"), sd.add_suffix("_sd"), n.add_suffix("_n")], axis=1)  # CSV용: 반올림 안 함
    rows = ["| method | " + " | ".join(metrics) + " |", "|---|" + "---|" * len(metrics)]
    for m in mean.index:
        cells = [f"{mean.loc[m, k]:.{digits}f} ± {sd.loc[m, k]:.{digits}f} (n={n.loc[m, k]})" for k in metrics]
        rows.append(f"| {m} | " + " | ".join(cells) + " |")
    md = "\n".join(rows) + "\n\n값: 평균 ± 표준편차(SD, ddof=1), n = 해당 지표의 유효 실행 수(시드×fold)"
    return raw, md


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default="summary")
    ap.add_argument("--digits", type=int, default=3)
    args = ap.parse_args()
    df = pd.read_csv(args.csv)
    metrics = [c for c in df.columns if c not in ("method", "seed", "fold")]
    warns = check_runs(df, metrics)
    raw, md = summarize(df, metrics, args.digits)
    if warns:
        md += "\n\n주의: " + "; ".join(warns)
    raw.to_csv(f"{args.out}.csv")
    with open(f"{args.out}.md", "w") as f:
        f.write(md + "\n")
    print(md)
