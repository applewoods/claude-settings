#!/usr/bin/env bash
# 평가 사례 하나를 with_skill / without_skill로 한 번 실행한다.
# 사용: run.sh <사례 이름> <with_skill|without_skill> <결과 루트>
# 결과: <결과 루트>/<사례>/<변형>/ 에 실행 폴더, transcript.jsonl, timing.json
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASE="$1"; VARIANT="$2"; ROOT="$3"
RUN="$ROOT/$CASE/$VARIANT"
mkdir -p "$RUN"
python3 "$HERE/setup_case.py" "$CASE" "$RUN" >/dev/null || exit 1

SETTINGS='{}'
[ "$VARIANT" = "without_skill" ] && SETTINGS='{"skillOverrides":{"server-ops":"off"}}'
echo '{"mcpServers":{}}' > "$RUN/empty-mcp.json"

start=$(date +%s)
cd "$RUN/work" || exit 1
FAKE_ROOT="$RUN" PATH="$RUN/bin:$PATH" GH_TOKEN="invalid-eval-token" GH_HOST="github.eval.invalid" \
  claude -p "$(cat "$RUN/prompt.txt")" \
    --output-format stream-json --verbose \
    --permission-mode acceptEdits \
    --allowedTools "Bash" "Read" "Glob" "Grep" "Skill" "Write" "Edit" \
    --settings "$SETTINGS" \
    --mcp-config "$RUN/empty-mcp.json" --strict-mcp-config \
    --no-session-persistence \
    > "$RUN/transcript.jsonl" 2> "$RUN/stderr.txt"
code=$?
end=$(date +%s)
printf '{"exit_code": %d, "seconds": %d}\n' "$code" "$((end-start))" > "$RUN/timing.json"
echo "$CASE/$VARIANT exit=$code ${$((end-start))}s" 2>/dev/null || echo "$CASE/$VARIANT exit=$code $((end-start))s"
