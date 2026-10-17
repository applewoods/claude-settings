#!/usr/bin/env python3
"""분포에서 무작위로 가상 사용자(페르소나)를 뽑는다. (Random Silicon Sampling 방식)

사용법:
  python3 sample_personas.py <persona-spec.json> <personas.json> [--search-seed]

persona-spec.json 예:
{
  "count": 40,
  "seed": 42,
  "lang": "ko",
  "fixed": {"거주 국가": "한국"},
  "joint": [
    {"vars": ["과정", "연령대"],
     "dist": {"석사|20대": 0.35, "석사|30대": 0.1, "박사|20대": 0.1, "박사|30대": 0.3, "박사후연구원|30대": 0.15}}
  ],
  "variables": {
    "현재 쓰는 방법": {"Zotero": 0.4, "PDF에 직접 메모": 0.4, "따로 관리 안 함": 0.2}
  },
  "sources": {"과정|연령대": "[가정]", "현재 쓰는 방법": "학과 설문 2025 (n=120)"}
}
- lang: 소개 문장 언어 (ko | en)
- joint: 함께 정해야 하는 변수의 결합 분포. 값은 "|"로 구분한다. 비현실적 조합을 막는다.
- variables: 서로 독립적으로 뽑는 변수
- quotas (선택): 꼭 포함해야 할 교차 집단. [{"where": {"AI 사용": "안 함", "관리 방법": "안 함"}, "min": 3}]
  모자라면 다른 quota에 속하지 않은 페르소나의 해당 속성을 바꿔 채운다(독립 변수만 지정 가능).
분포 합이 1이 아니면 비율로 정규화한다. 완전히 같은 조합은 다시 뽑는다.
--search-seed: 목표 분포에 가장 가까운 seed를 찾아 쓰고 spec에 기록한다(작은 표본에서 권장).
출력에는 실제로 뽑힌 인원 분포를 요약한다.
"""
import json, random, sys
from collections import Counter

INTRO = {
    "ko": lambda a: "나는 " + ", ".join(f"{k}: {v}" for k, v in a.items()) + "인 사람이다.",
    "en": lambda a: "I am a person with these characteristics — " + "; ".join(f"{k}: {v}" for k, v in a.items()) + ".",
}

def check_dist(name, dist):
    total = sum(dist.values())
    if total <= 0 or any(w < 0 for w in dist.values()):
        sys.exit(f"분포가 올바르지 않습니다: {name}")
    if abs(total - 1) > 0.01:
        print(f"참고: '{name}' 분포 합이 {total:.3f} → 비율로 정규화합니다.", file=sys.stderr)

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    count = int(spec.get("count", 40))
    intro = INTRO.get(spec.get("lang", "ko"), INTRO["ko"])
    fixed = spec.get("fixed", {})
    joints = spec.get("joint", [])
    variables = spec.get("variables", {})

    for j in joints:
        name = "|".join(j["vars"])
        check_dist(name, j["dist"])
        for key in j["dist"]:
            if len(key.split("|")) != len(j["vars"]):
                sys.exit(f"결합 분포 '{name}'의 값 '{key}'가 변수 수({len(j['vars'])})와 맞지 않습니다.")
    for name, dist in variables.items():
        check_dist(name, dist)
    names = [v for j in joints for v in j["vars"]] + list(variables)
    if len(names) != len(set(names)):
        sys.exit("같은 변수가 joint와 variables에 중복돼 있습니다.")

    def draw(seed):
        rng = random.Random(seed)
        out, seen = [], set()
        for i in range(1, count + 1):
            for _ in range(50):  # 완전히 같은 조합은 다시 뽑는다(다양성)
                attrs = dict(fixed)
                for j in joints:
                    combo = rng.choices(list(j["dist"]), weights=list(j["dist"].values()))[0]
                    attrs.update(zip(j["vars"], combo.split("|")))
                for name, dist in variables.items():
                    attrs[name] = rng.choices(list(dist), weights=list(dist.values()))[0]
                key = tuple(sorted(attrs.items()))
                if key not in seen:
                    break
            seen.add(key)
            out.append({"id": f"P{i:03d}", "attributes": attrs, "intro": intro(attrs)})
        return out

    def apply_quotas(ps, rng):
        """꼭 포함해야 할 교차 집단(quotas)이 모자라면, 다른 quota에 속하지 않은 페르소나를 골라 속성을 바꾼다."""
        quotas = spec.get("quotas", [])
        match = lambda p, q: all(p["attributes"].get(k) == v for k, v in q["where"].items())
        for q in quotas:
            bad = [k for k in q["where"] if k not in variables]
            if bad:
                sys.exit(f"quotas에는 독립 변수(variables)만 쓸 수 있습니다: {bad}")
            short = q.get("min", 1) - sum(match(p, q) for p in ps)
            pool = [p for p in ps if not any(match(p, o) for o in quotas)]
            for p in rng.sample(pool, min(max(short, 0), len(pool))):
                p["attributes"].update(q["where"])
                p["intro"] = intro(p["attributes"])
        for q in quotas:
            n = sum(match(p, q) for p in ps)
            print(f"quota {q['where']}: {n}명 (최소 {q.get('min', 1)})")

    def deviation(ps):
        """목표 분포와 뽑힌 분포의 차이(변수별 비율 차이 합)."""
        total = 0.0
        groups = [(j["vars"], j["dist"]) for j in joints] + [([n], d) for n, d in variables.items()]
        for vs, dist in groups:
            s = sum(dist.values())
            got = Counter("|".join(p["attributes"][v] for v in vs) for p in ps)
            total += sum(abs(got.get(k, 0) / len(ps) - w / s) for k, w in dist.items())
        return total

    seed = spec.get("seed", 42)
    if "--search-seed" in sys.argv[3:]:
        # 목표 분포에 가장 가까운 seed를 1~500에서 고른다
        seed = min(range(1, 501), key=lambda s_: deviation(draw(s_)))
        spec["seed"] = seed
        json.dump(spec, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"seed 탐색: 목표 분포에 가장 가까운 seed = {seed} (사양 파일에 기록)")
    personas = draw(seed)
    apply_quotas(personas, random.Random(seed + 1))
    print(f"목표 분포와의 차이: {deviation(personas):.3f} (0에 가까울수록 일치)")

    json.dump({"spec": spec, "personas": personas}, open(sys.argv[2], "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"페르소나 {count}명 생성 → {sys.argv[2]}")
    for name in names:
        got = Counter(p["attributes"][name] for p in personas)
        print(f"  {name}: " + ", ".join(f"{k} {n}명" for k, n in got.most_common()))

if __name__ == "__main__":
    main()
