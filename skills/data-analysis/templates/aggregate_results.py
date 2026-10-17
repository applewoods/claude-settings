"""시드·fold별 원 점수(long 형식) → 방법별 평균 ± SD 표(CSV + 마크다운).

입력 CSV 열: method, seed, fold, <지표들...>   (fold가 없으면 0으로)
사용: python aggregate_results.py results/.../metrics.csv --out results/.../summary
"""
import argparse

import pandas as pd


def summarize(df: pd.DataFrame, metrics: list[str], digits: int = 3):
    g = df.groupby("method", sort=False)[metrics]
    mean, sd, n = g.mean(), g.std(ddof=1), g.count()
    raw = pd.concat([mean.add_suffix("_mean"), sd.add_suffix("_sd"), n.add_suffix("_n")], axis=1)  # CSV용: 반올림 안 함
    rows = ["| method | " + " | ".join(metrics) + " | n |",
            "|---|" + "---|" * len(metrics) + "---|"]
    for m in mean.index:
        cells = [f"{mean.loc[m, k]:.{digits}f} ± {sd.loc[m, k]:.{digits}f}" for k in metrics]
        rows.append(f"| {m} | " + " | ".join(cells) + f" | {int(n.loc[m, metrics[0]])} |")
    md = "\n".join(rows) + "\n\n값: 평균 ± 표준편차(SD, ddof=1), n = 시드×fold 실행 수"
    return raw, md


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default="summary")
    ap.add_argument("--digits", type=int, default=3)
    args = ap.parse_args()
    df = pd.read_csv(args.csv)
    metrics = [c for c in df.columns if c not in ("method", "seed", "fold")]
    raw, md = summarize(df, metrics, args.digits)
    raw.to_csv(f"{args.out}.csv")
    with open(f"{args.out}.md", "w") as f:
        f.write(md + "\n")
    print(md)
