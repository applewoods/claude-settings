#!/usr/bin/env python3
"""가상 인터뷰 응답 중 고르기·척도 질문을 집계하고, 모델 간·실제 조사와의 차이를 계산한다.

사용법:
  python3 aggregate.py --dir docs/research [--by 변수이름] [--reference reference.json] [--out aggregate.md]

- 입력: <dir>/responses_*.json, <dir>/personas.json
- 모델 간 비교: 카이제곱 동질성 검정(p<0.05면 분포 차이가 유의), KL-divergence(0에 가까울수록 비슷).
- --reference: 실제 조사 분포가 있으면 비교한다. {"Q2": {"선택지A": 30, "선택지B": 70}, ...}
  값의 합이 1.5보다 크면 응답 수(동질성 검정), 아니면 비율(적합도 검정)로 본다. 척도는 {"1": .., "5": ..}.
- --by: 페르소나 변수별로 나눠 응답을 보여 준다(하위집단 과장 확인용).
- 쏠림 경고: 한 선택지가 90% 이상이면 표시한다(무해성·고정관념 편향 가능성).
열린 질문은 집계하지 않는다(종합은 사람이·오케스트레이터가 한다).
"""
import argparse, json, math
from collections import Counter, defaultdict
from pathlib import Path

EPS = 0.5  # KL 계산용 평활(빈 칸 0 방지)

# --- 카이제곱 p-value (정규화 불완전 감마 함수 Q) ---
def _gser(a, x):
    s = term = 1.0 / a
    n = a
    for _ in range(500):
        n += 1; term *= x / n; s += term
        if abs(term) < abs(s) * 1e-12:
            break
    return s * math.exp(-x + a * math.log(x) - math.lgamma(a))

def _gcf(a, x):
    b = x + 1 - a; c = 1e300; d = 1 / b; h = d
    for i in range(1, 500):
        an = -i * (i - a); b += 2
        d = an * d + b; d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c; c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d; delta = d * c; h *= delta
        if abs(delta - 1) < 1e-12:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h

def chi2_sf(stat, df):
    if df <= 0 or stat <= 0:
        return 1.0
    a, x = df / 2, stat / 2
    return 1 - _gser(a, x) if x < a + 1 else _gcf(a, x)

def chi2_homogeneity(c1, c2, cats):
    n1, n2 = sum(c1.get(k, 0) for k in cats), sum(c2.get(k, 0) for k in cats)
    used = [k for k in cats if c1.get(k, 0) + c2.get(k, 0) > 0]
    if n1 == 0 or n2 == 0 or len(used) < 2:
        return None
    stat = 0.0
    for k in used:
        tot = c1.get(k, 0) + c2.get(k, 0)
        for c, n in ((c1, n1), (c2, n2)):
            e = tot * n / (n1 + n2)
            stat += (c.get(k, 0) - e) ** 2 / e
    return stat, chi2_sf(stat, len(used) - 1)

def chi2_gof(counts, probs, cats):
    n = sum(counts.get(k, 0) for k in cats)
    used = [k for k in cats if probs.get(k, 0) > 0]
    if n == 0 or len(used) < 2:
        return None
    stat = sum((counts.get(k, 0) - n * probs[k]) ** 2 / (n * probs[k]) for k in used)
    return stat, chi2_sf(stat, len(used) - 1)

def kl(p_counts, q_counts, cats):
    p = {k: p_counts.get(k, 0) + EPS for k in cats}; q = {k: q_counts.get(k, 0) + EPS for k in cats}
    sp, sq = sum(p.values()), sum(q.values())
    return sum((p[k] / sp) * math.log((p[k] / sp) / (q[k] / sq)) for k in cats)

def categories(q):
    if q["type"] == "scale":
        return [str(v) for v in range(q["min"], q["max"] + 1)]
    return q["options"]

def counts_for(q, key, responses, ids=None):
    c, invalid = Counter(), 0
    for r in responses:
        if ids is not None and r["id"] not in ids:
            continue
        a = r["answers"].get(key, {})
        if a.get("invalid"):
            invalid += 1; continue
        v = a.get("value")
        for x in (v if q["type"] == "multi" else [v]):
            c[str(x)] += 1
    return c, invalid

def fmt_dist(c, cats, n):
    return " · ".join(f"{k} {c.get(k, 0)} ({c.get(k, 0) / n:.0%})" if n else f"{k} 0" for k in cats)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--by")
    ap.add_argument("--reference")
    ap.add_argument("--out")
    a = ap.parse_args()
    d = Path(a.dir)
    files = sorted(d.glob("responses_*.json"))
    if not files:
        raise SystemExit(f"{d}에 responses_*.json이 없습니다.")
    runs = {f.stem.replace("responses_", ""): json.load(open(f, encoding="utf-8")) for f in files}
    personas = {p["id"]: p["attributes"] for p in json.load(open(d / "personas.json", encoding="utf-8"))["personas"]}
    ref = json.load(open(a.reference, encoding="utf-8")) if a.reference else {}
    questions = next(iter(runs.values()))["questions"]
    models = list(runs)

    L = ["# 가상 인터뷰 집계", "", f"- 모델: " + ", ".join(f"{m} ({runs[m]['model']}, 응답 {len(runs[m]['responses'])}명)" for m in models),
         "- 이 수치는 가상 응답의 분포다. 실제 수요나 비율로 해석하지 않는다.", ""]
    for i, q in enumerate(questions, 1):
        key = f"Q{i}"
        if q["type"] == "open":
            continue
        cats = categories(q)
        L += [f"## {key}. {q['text']}", f"형식: {q['type']}" + (f" (최대 {q['max']}개)" if q["type"] == "multi" else ""), ""]
        per = {}
        for m in models:
            resp = runs[m]["responses"]
            c, inv = counts_for(q, key, resp)
            n = len(resp) - inv
            per[m] = c
            L.append(f"- **{m}** (유효 {n}명{', 형식 오류 ' + str(inv) if inv else ''}): {fmt_dist(c, cats, n)}")
            top = max(cats, key=lambda k: c.get(k, 0))
            if n and q["type"] != "multi" and c.get(top, 0) / n >= 0.9:
                L.append(f"  - ⚠️ 쏠림: '{top}' {c[top] / n:.0%} — 무해성·고정관념 편향 가능성, 근거로 쓰지 말 것")
        if len(models) == 2 and q["type"] != "multi":
            m1, m2 = models
            h = chi2_homogeneity(per[m1], per[m2], cats)
            if h:
                L.append(f"- {m1} vs {m2}: χ²={h[0]:.2f}, p={h[1]:.3f} ({'분포 차이 유의 → 두 모델이 엇갈림' if h[1] < 0.05 else '유의한 차이 없음'}), KL={kl(per[m1], per[m2], cats):.4f}")
        if key in ref and q["type"] != "multi":
            rc = {str(k): v for k, v in ref[key].items()}
            is_counts = sum(rc.values()) > 1.5
            for m in models:
                if is_counts:
                    h = chi2_homogeneity(per[m], rc, cats)
                else:
                    tot = sum(rc.values()); h = chi2_gof(per[m], {k: v / tot for k, v in rc.items()}, cats)
                k_ = kl(rc if is_counts else {k: v * 1000 for k, v in rc.items()}, per[m], cats)
                if h:
                    L.append(f"- 실제 조사 vs {m}: χ²={h[0]:.2f}, p={h[1]:.3f} ({'유의한 차이' if h[1] < 0.05 else '유의한 차이 없음'}), KL={k_:.4f}")
        if a.by:
            groups = defaultdict(set)
            for pid, attrs in personas.items():
                groups[attrs.get(a.by, "(없음)")].add(pid)
            L.append(f"- **{a.by}별**")
            for g, ids in sorted(groups.items()):
                parts = []
                for m in models:
                    c, inv = counts_for(q, key, runs[m]["responses"], ids)
                    n = sum(1 for r in runs[m]["responses"] if r["id"] in ids) - inv
                    flag = ""
                    if n >= 3 and q["type"] != "multi":
                        top = max(cats, key=lambda k: c.get(k, 0))
                        if c.get(top, 0) / n >= 0.95:
                            flag = " ⚠️과장 가능"
                    parts.append(f"{m}: {fmt_dist(c, cats, n)}{flag}")
                L.append(f"  - {g} ({len(ids)}명) — " + " / ".join(parts))
        L.append("")
    text = "\n".join(L)
    out = Path(a.out) if a.out else d / "aggregate.md"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\n[저장] {out}")

if __name__ == "__main__":
    main()
