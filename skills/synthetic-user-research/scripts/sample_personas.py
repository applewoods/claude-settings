#!/usr/bin/env python3
"""변수별 분포에서 무작위로 가상 사용자(페르소나)를 뽑는다. (Random Silicon Sampling 방식)

사용법:
  python3 sample_personas.py <spec.json> <personas.json>

spec.json 예:
{
  "count": 30,
  "seed": 42,
  "fixed": {"거주 국가": "한국"},
  "variables": {
    "연령대": {"20대": 0.3, "30대": 0.4, "40대": 0.2, "50대 이상": 0.1},
    "현재 쓰는 방법": {"엑셀": 0.5, "종이 메모": 0.2, "다른 앱": 0.3},
    "기술 친숙도": {"낮음": 0.2, "보통": 0.5, "높음": 0.3}
  },
  "sources": {"연령대": "통계청 2025 경제활동인구조사", "현재 쓰는 방법": "[가정]"}
}
각 변수의 값은 독립적으로 뽑는다(실제 결합 분포를 알면 변수를 합쳐서 하나로 적는다).
"""
import json, random, sys

def main():
    if len(sys.argv) != 3:
        print(__doc__); sys.exit(2)
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    rng = random.Random(spec.get("seed", 42))
    count = int(spec.get("count", 30))
    fixed = spec.get("fixed", {})
    variables = spec["variables"]
    for name, dist in variables.items():
        total = sum(dist.values())
        if total <= 0:
            sys.exit(f"분포 합이 0 이하: {name}")
        if abs(total - 1) > 0.01:
            print(f"참고: '{name}' 분포 합이 {total:.3f} → 비율로 정규화합니다.", file=sys.stderr)
    personas = []
    for i in range(1, count + 1):
        attrs = dict(fixed)
        for name, dist in variables.items():
            attrs[name] = rng.choices(list(dist), weights=list(dist.values()))[0]
        intro = "나는 " + ", ".join(f"{k}이(가) {v}" for k, v in attrs.items()) + "인 사람이다."
        personas.append({"id": f"P{i:03d}", "attributes": attrs, "intro": intro})
    json.dump({"spec": spec, "personas": personas}, open(sys.argv[2], "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    # 뽑힌 분포 요약 (목표 분포와 비교용)
    print(f"페르소나 {count}명 생성 → {sys.argv[2]}")
    for name, dist in variables.items():
        got = {k: sum(p["attributes"][name] == k for p in personas) for k in dist}
        print(f"  {name}: " + ", ".join(f"{k} {got[k]}명" for k in dist))

if __name__ == "__main__":
    main()
