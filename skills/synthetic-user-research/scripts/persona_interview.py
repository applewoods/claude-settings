#!/usr/bin/env python3
"""가상 사용자(페르소나) 인터뷰를 Claude와 Codex(GPT) 두 모델로 각각 실행한다.

사용법:
  python3 persona_interview.py --personas personas.json --service service.md --questions questions.md \
      --out-dir docs/research [--models claude,codex] [--claude-model sonnet] [--batch 5] [--workers 3]

- service.md : 기획 중인 서비스 설명(문제, 대상, 주요 기능 후보). 페르소나에게 보여 줄 내용만 적는다.
- questions.md: 질문 목록. 한 줄에 하나, "- " 또는 "1. "로 시작.
- 결과: <out-dir>/responses_<모델>.json  (페르소나별·질문별 답변)
각 모델은 서로의 답을 보지 않는다. 결과는 가설을 만들기 위한 자료이고, 실제 사용자 조사 결과가 아니다.
"""
import argparse, json, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SYSTEM = """You are role-playing a specific person in a product research interview. Stay strictly in character.
Rules:
- Answer as that person would in real life, from their situation, habits and constraints — not as an AI assistant.
- Do not be polite for the sake of it. If the person would not use, would not pay for, or would not care about something, say so plainly and say why.
- Prefer concrete past behaviour ("last time I ... I did ...") over hypothetical enthusiasm.
- It is fine to be unsure, indifferent, or negative. Do not invent expertise the person would not have.
- Answer in Korean, 1-4 sentences per question.
- Each persona answers independently; do not let personas agree with each other."""

def parse_questions(text):
    qs = []
    for line in text.splitlines():
        m = re.match(r"^\s*(?:[-*]|\d+[.)])\s+(.*\S)", line)
        if m:
            qs.append(m.group(1))
    return qs

def build_prompt(service, questions, batch):
    people = "\n".join(f"- {p['id']}: {p['intro']}" for p in batch)
    qlist = "\n".join(f"Q{i+1}. {q}" for i, q in enumerate(questions))
    return f"""{SYSTEM}

## The product being researched (what the interviewer showed you)
{service}

## People to role-play (answer separately as each one)
{people}

## Interview questions
{qlist}

## Output
Return ONLY a JSON array, no prose, no code fence. One object per person:
[{{"id": "P001", "answers": {{"Q1": "...", "Q2": "..."}}}}, ...]"""

def extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < 0:
        raise ValueError("JSON 배열을 찾지 못함")
    return json.loads(text[start:end + 1])

def run_claude(prompt, model):
    r = subprocess.run(
        ["claude", "-p", "--model", model, "--no-session-persistence",
         "--setting-sources", "", "--tools", "", "--system-prompt", SYSTEM],
        input=prompt, capture_output=True, text=True, timeout=600, cwd=tempfile.gettempdir())
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:] or r.stdout[-500:])
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

def interview(model_name, runner, model_arg, service, questions, personas, batch_size, workers):
    batches = [personas[i:i + batch_size] for i in range(0, len(personas), batch_size)]
    def one(batch):
        ids = {p["id"] for p in batch}
        last_err = None
        for _ in range(2):  # 형식 오류면 한 번 더 시도
            try:
                rows = extract_json(runner(build_prompt(service, questions, batch), model_arg))
                rows = [r for r in rows if r.get("id") in ids]
                if {r["id"] for r in rows} == ids:
                    return rows, None
                last_err = f"일부 페르소나 답변 누락: {sorted(ids - {r['id'] for r in rows})}"
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
        return [], f"{sorted(ids)}: {last_err}"
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
    ap.add_argument("--batch", type=int, default=5)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()

    data = json.load(open(a.personas, encoding="utf-8"))
    personas = data["personas"]
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
        print(f"[{name}] 페르소나 {len(personas)}명 × 질문 {len(questions)}개 인터뷰 중…", file=sys.stderr)
        rows, errors = interview(name, fn, arg, service, questions, personas, a.batch, a.workers)
        path = out / f"responses_{name}.json"
        json.dump({"model": f"{name}:{arg or 'default'}", "questions": questions,
                   "responses": sorted(rows, key=lambda r: r["id"]), "errors": errors},
                  open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"[{name}] 응답 {len(rows)}/{len(personas)}명 → {path}" + (f" (오류 {len(errors)}건)" if errors else ""))
        for e in errors:
            print(f"  오류: {e}", file=sys.stderr)
        failed |= bool(errors)
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
