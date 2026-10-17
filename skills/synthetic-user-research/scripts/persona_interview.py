#!/usr/bin/env python3
"""가상 사용자(페르소나) 인터뷰를 Claude와 Codex(GPT) 두 모델로 각각 실행한다.

사용법:
  python3 persona_interview.py --personas personas.json --service service.md --questions questions.md \
      --out-dir docs/research [--models claude,codex] [--claude-model sonnet] [--codex-model 모델]
      [--batch 1] [--workers 4] [--lang ko|en] [--frame product|survey]

questions.md — 한 줄에 질문 하나. "- " 또는 "1. "로 시작하고, 앞에 형식을 붙일 수 있다.
  - 지금은 이 일을 어떻게 처리하세요?                         (형식 없음 = 열린 질문)
  - [choice: Zotero | PDF 메모 | 안 함] 주로 쓰는 방법은?        (하나 고르기)
  - [multi max=2: 요약 | 메모 모음 | 분류 | 공유] 두 개만 남긴다면?  (여러 개 고르기)
  - [scale 1-5: 전혀 아니다 ~ 매우 그렇다] 지금 방식이 불편하다    (척도)

- 기본은 페르소나 1명당 1번 호출(--batch 1)이다. 여러 명을 한 번에 물으면 답이 서로 닮아갈 수 있다.
- 두 모델은 서로의 답을 보지 않는다.
- 결과: <out-dir>/responses_<모델>.json. 고르기·척도 응답이 선택지에 맞지 않으면 invalid로 표시한다.
- 결과는 가설을 만들기 위한 자료이고, 실제 사용자 조사 결과가 아니다.
"""
import argparse, json, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

FRAMES = {
    "product": """You are role-playing a specific person being interviewed about a product idea. Stay strictly in character.
- Answer as that person would in real life, from their situation, habits and constraints — not as an AI assistant.
- Do not be polite for the sake of it. If the person would not use, pay for, or care about something, say so plainly and why.
- Prefer concrete past behaviour ("last time I ... I did ...") over hypothetical enthusiasm.
- Being unsure, indifferent or negative is fine. Do not invent expertise the person would not have.""",
    "survey": """You are role-playing a specific person answering a survey. Stay strictly in character.
- Answer as that person would, given their background — not as an AI assistant and not with the most socially acceptable answer.
- Do not soften or neutralise opinions the person would plausibly hold. Being unsure or holding minority views is fine.""",
}
LANG = {"ko": "Write all free-text answers and reasons in Korean, 1-4 sentences each.",
        "en": "Write all free-text answers and reasons in English, 1-4 sentences each."}

def parse_questions(text):
    qs = []
    for line in text.splitlines():
        m = re.match(r"^\s*(?:[-*]|\d+[.)])\s+(.*\S)", line)
        if not m:
            continue
        body = m.group(1)
        q = {"type": "open", "text": body}
        t = re.match(r"^\[(choice|multi|scale)([^:\]]*):\s*([^\]]*)\]\s*(.+)$", body)
        if t:
            kind, opts, values, qtext = t.groups()
            q = {"type": kind, "text": qtext.strip()}
            if kind in ("choice", "multi"):
                q["options"] = [v.strip() for v in values.split("|") if v.strip()]
                mx = re.search(r"max\s*=\s*(\d+)", opts)
                if kind == "multi":
                    q["max"] = int(mx.group(1)) if mx else len(q["options"])
            else:
                rng = re.search(r"(\d+)\s*-\s*(\d+)", opts)
                q["min"], q["max"] = (int(rng.group(1)), int(rng.group(2))) if rng else (1, 5)
                q["anchors"] = values.strip()
        qs.append(q)
    return qs

def describe(i, q):
    head = f"Q{i}. {q['text']}"
    if q["type"] == "choice":
        return head + f"\n    → value: exactly one of {json.dumps(q['options'], ensure_ascii=False)}"
    if q["type"] == "multi":
        return head + f"\n    → value: a list of at most {q['max']} items from {json.dumps(q['options'], ensure_ascii=False)}"
    if q["type"] == "scale":
        return head + f"\n    → value: an integer {q['min']}-{q['max']} ({q['anchors']})"
    return head + "\n    → value: free text"

def build_prompt(frame, lang, service, questions, batch):
    people = "\n".join(f"- {p['id']}: {p['intro']}" for p in batch)
    qlist = "\n".join(describe(i + 1, q) for i, q in enumerate(questions))
    return f"""{FRAMES[frame]}
- {LANG[lang]}
- If several people are listed, answer for each one independently; they do not know each other.

## What the interviewer showed you
{service}

## Person(s) to role-play
{people}

## Questions
{qlist}

## Output
Return ONLY a JSON array (no prose, no code fence), one object per person:
[{{"id": "P001", "answers": {{"Q1": {{"value": ..., "reason": "..."}}, "Q2": {{"value": ..., "reason": "..."}}}}}}]
For free-text questions put the answer in "value" and leave "reason" empty."""

def extract_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < 0:
        raise ValueError("JSON 배열을 찾지 못함")
    return json.loads(text[start:end + 1])

def validate(questions, answers):
    out = {}
    for i, q in enumerate(questions, 1):
        a = answers.get(f"Q{i}", {})
        if not isinstance(a, dict):
            a = {"value": a, "reason": ""}
        v, ok = a.get("value"), True
        if q["type"] == "choice":
            ok = v in q["options"]
        elif q["type"] == "multi":
            if isinstance(v, str):
                v = [s.strip() for s in re.split(r"[,|]", v) if s.strip()]
            ok = isinstance(v, list) and 0 < len(v) <= q["max"] and all(x in q["options"] for x in v)
        elif q["type"] == "scale":
            try:
                v = int(v); ok = q["min"] <= v <= q["max"]
            except (TypeError, ValueError):
                ok = False
        else:
            ok = isinstance(v, str) and v.strip() != ""
        out[f"Q{i}"] = {"value": v, "reason": a.get("reason", ""), **({} if ok else {"invalid": True})}
    return out

def run_claude(prompt, model):
    r = subprocess.run(
        ["claude", "-p", "--model", model, "--no-session-persistence", "--setting-sources", "", "--tools", ""],
        input=prompt, capture_output=True, text=True, timeout=600, cwd=tempfile.gettempdir())
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout)[-500:])
    return r.stdout

def run_codex(prompt, model):
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out.md"
        cmd = ["codex", "exec", "-C", d, "-s", "read-only", "--skip-git-repo-check", "--ephemeral",
               "--color", "never", "-c", 'web_search="disabled"', "-o", str(out)]
        if model:
            cmd += ["-m", model]
        r = subprocess.run(cmd + ["-"], input=prompt, capture_output=True, text=True, timeout=900)
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(r.stderr[-500:])
        return out.read_text()

def interview(runner, model_arg, frame, lang, service, questions, personas, batch_size, workers):
    batches = [personas[i:i + batch_size] for i in range(0, len(personas), batch_size)]
    def one(batch):
        ids = {p["id"] for p in batch}
        err = None
        for _ in range(2):  # 형식 오류면 한 번 더
            try:
                rows = [r for r in extract_json(runner(build_prompt(frame, lang, service, questions, batch), model_arg))
                        if r.get("id") in ids]
                if {r["id"] for r in rows} == ids:
                    return [{"id": r["id"], "answers": validate(questions, r.get("answers", {}))} for r in rows], None
                err = f"답변 누락: {sorted(ids - {r['id'] for r in rows})}"
            except Exception as e:  # noqa: BLE001
                err = str(e)
        return [], f"{sorted(ids)}: {err}"
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for rows, err in ex.map(one, batches):
            results.extend(rows)
            if err:
                errors.append(err)
    return results, errors

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--personas", required=True)
    ap.add_argument("--service", required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--models", default="claude,codex")
    ap.add_argument("--claude-model", default="sonnet")
    ap.add_argument("--codex-model", default="")
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--lang", choices=list(LANG), default="ko")
    ap.add_argument("--frame", choices=list(FRAMES), default="product")
    a = ap.parse_args()

    personas = json.load(open(a.personas, encoding="utf-8"))["personas"]
    service = Path(a.service).read_text(encoding="utf-8")
    questions = parse_questions(Path(a.questions).read_text(encoding="utf-8"))
    if not questions:
        sys.exit("질문을 찾지 못했습니다. 한 줄에 하나씩 '- ' 또는 '1. '로 시작해 주세요.")
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)

    runners = {"claude": (run_claude, a.claude_model), "codex": (run_codex, a.codex_model)}
    failed = False
    for name in [m.strip() for m in a.models.split(",") if m.strip()]:
        if name not in runners:
            sys.exit(f"알 수 없는 모델: {name}")
        if not shutil.which(name):
            print(f"[{name}] CLI가 없어 건너뜀", file=sys.stderr); failed = True; continue
        fn, arg = runners[name]
        print(f"[{name}] 페르소나 {len(personas)}명 × 질문 {len(questions)}개 (묶음 {a.batch}명) 인터뷰 중…", file=sys.stderr)
        rows, errors = interview(fn, arg, a.frame, a.lang, service, questions, personas, a.batch, a.workers)
        invalid = sum(1 for r in rows for v in r["answers"].values() if v.get("invalid"))
        path = out / f"responses_{name}.json"
        json.dump({"model": f"{name}:{arg or 'default'}", "frame": a.frame, "lang": a.lang,
                   "questions": questions, "responses": sorted(rows, key=lambda r: r["id"]), "errors": errors},
                  open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"[{name}] 응답 {len(rows)}/{len(personas)}명 → {path}"
              + (f" · 형식 안 맞는 답 {invalid}개" if invalid else "") + (f" · 오류 {len(errors)}건" if errors else ""))
        for e in errors:
            print(f"  오류: {e}", file=sys.stderr)
        failed |= bool(errors)
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
