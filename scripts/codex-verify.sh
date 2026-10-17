#!/usr/bin/env bash
# Codex CLI(OpenAI 모델)로 근거 기반·비판적 독립 검증을 실행한다.
# Claude와 다른 모델이 결과를 따로, 반증을 시도하는 태도로 검사하게 하려는 것.
#
# 사용법:
#   codex-verify.sh <검사할 폴더> <브리핑 파일 | -> [옵션]
#
# 옵션:
#   -t 유형     업무 유형별 비판 질문 추가. paper | data | dev | design | plan (쉼표로 여러 개)
#   --run       원본을 건드리지 않는 임시 복사본에서 실행 권한을 주고 검증 (테스트·분석 재실행용)
#   --web       웹 검색 허용 (인용 실존·출처 확인용)
#   -e 강도     Codex 추론 강도: low | medium | high | xhigh (기본 high)
#   -m 모델     Codex 모델 지정 (기본: ~/.codex/config.toml 설정)
#   --label 이름 기록 파일 이름에 붙일 짧은 이름
#   --no-save   검증 기록을 저장하지 않음 (기본: <검사할 폴더>/docs/verification/ 에 저장)
#
# 브리핑에는 검증 대상, 완료 기준, 참고 파일을 적는다. "-"이면 표준입력에서 읽는다.
# 결과를 표준출력으로 내보낸다. Codex가 없거나 실패하면 0이 아닌 코드로 끝난다.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUIDE="$REPO/verification"

usage() { sed -n '5,18p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
[ $# -ge 2 ] || usage
DIR="$(cd "$1" 2>/dev/null && pwd)" || { echo "검사할 폴더가 없습니다: $1" >&2; exit 2; }
BRIEF="$2"; shift 2

TYPES=""; RUN=0; WEB=0; EFFORT="high"; MODEL=""; LABEL="verify"; SAVE=1
need() { [ -n "${2:-}" ] && [ "${2#-}" = "$2" ] || { echo "옵션 $1 에 값이 필요합니다." >&2; usage; }; }
while [ $# -gt 0 ]; do
  case "$1" in
    -t|-e|-m|--label) need "$1" "${2:-}" ;;
  esac
  case "$1" in
    -t) TYPES="$2"; shift 2 ;;
    --run) RUN=1; shift ;;
    --web) WEB=1; shift ;;
    -e) EFFORT="$2"; shift 2 ;;
    -m) MODEL="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    --no-save) SAVE=0; shift ;;
    *) echo "알 수 없는 옵션: $1" >&2; usage ;;
  esac
done

command -v codex >/dev/null || { echo "CODEX_UNAVAILABLE: codex CLI가 설치돼 있지 않습니다 (npm i -g @openai/codex)." >&2; exit 3; }
if [ "$BRIEF" = "-" ]; then
  BRIEF_TEXT="$(cat)"
else
  [ -r "$BRIEF" ] || { echo "브리핑 파일을 읽을 수 없습니다: $BRIEF" >&2; exit 2; }
  BRIEF_TEXT="$(cat "$BRIEF")"
fi
[ -n "$(printf '%s' "$BRIEF_TEXT" | tr -d '[:space:]')" ] || { echo "브리핑이 비어 있습니다. 검증 대상과 완료 기준을 적어 주세요." >&2; exit 2; }
case "$EFFORT" in low|medium|high|xhigh) ;; *) echo "추론 강도는 low|medium|high|xhigh 중 하나: $EFFORT" >&2; exit 2 ;; esac
LABEL="$(printf '%s' "$LABEL" | tr -c 'A-Za-z0-9가-힣._-' '-' )"

TMP="$(mktemp -d -t codex-verify)"
trap 'rm -rf "$TMP"' EXIT

# 지시문 조립: 공통 원칙 + 업무 유형별 질문 + 실행 환경 + 브리핑
{
  cat "$GUIDE/principles.md"
  IFS=',' read -r -a TYPE_LIST <<< "$TYPES"
  for t in "${TYPE_LIST[@]+"${TYPE_LIST[@]}"}"; do
    t="$(echo "$t" | tr -d ' ')"
    [ -z "$t" ] && continue
    if [ -f "$GUIDE/$t.md" ]; then echo; cat "$GUIDE/$t.md"; else echo "알 수 없는 유형: $t" >&2; fi
  done
  echo
  echo "## Environment"
  if [ "$RUN" = 1 ]; then
    echo "- You are working in a disposable scratch COPY of the project. You may run tests, scripts and analyses here; changes are discarded afterwards. Do not edit source files to make checks pass."
  else
    echo "- Read-only sandbox: you cannot write files. Checks that need writing are [확인 불가]; say so."
  fi
  if [ "$WEB" = 1 ]; then
    echo "- Web search is available. Use it to confirm that cited sources exist and say what is attributed to them. Give the URL as evidence."
  else
    echo "- No web access. Citation existence and external facts are [확인 불가] unless the source is in the project files."
  fi
  echo
  echo "--- BRIEF FROM ORCHESTRATOR ---"
  echo "$BRIEF_TEXT"
} > "$TMP/prompt.md"

# 실행 위치와 권한
if [ "$RUN" = 1 ]; then
  WORK="$TMP/work"
  # APFS에서는 복제(clone)라 빠르고 공간을 거의 쓰지 않는다. 실패하면 일반 복사.
  if ! cp -cR "$DIR" "$WORK" 2>/dev/null; then
    rm -rf "$WORK"
    cp -R "$DIR" "$WORK" || { echo "COPY_FAILED: 임시 복사본을 만들지 못했습니다." >&2; exit 5; }
  fi
  SANDBOX="workspace-write"
else
  WORK="$DIR"
  SANDBOX="read-only"
fi

ARGS=(-C "$WORK" -s "$SANDBOX" --skip-git-repo-check --ephemeral --color never
      -o "$TMP/report.md" -c "model_reasoning_effort=\"$EFFORT\"")
[ -n "$MODEL" ] && ARGS+=(-m "$MODEL")
if [ "$WEB" = 1 ]; then ARGS+=(-c 'web_search="live"'); else ARGS+=(-c 'web_search="disabled"'); fi

codex exec "${ARGS[@]}" - < "$TMP/prompt.md" > /dev/null 2> "$TMP/err.log"
STATUS=$?

if [ $STATUS -ne 0 ] || [ ! -s "$TMP/report.md" ]; then
  echo "CODEX_FAILED (exit $STATUS)" >&2
  tail -20 "$TMP/err.log" >&2
  exit 4
fi

MODE_DESC="$([ "$RUN" = 1 ] && echo '격리 복사본 실행' || echo '읽기 전용')$([ "$WEB" = 1 ] && echo ' + 웹 검색')"
echo "[Codex 독립 검증 결과] 모드: $MODE_DESC · 유형: ${TYPES:-일반} · 추론 강도: $EFFORT"
cat "$TMP/report.md"
echo

# 검증 기록 저장
if [ "$SAVE" = 1 ]; then
  OUTDIR="$DIR/docs/verification"
  if ! mkdir -p "$OUTDIR" 2>/dev/null; then
    echo "[검증 기록 저장 실패] 폴더를 만들 수 없습니다: $OUTDIR" >&2
  else
    FILE="$OUTDIR/$(date +%Y%m%d-%H%M%S)_${LABEL// /-}.md"
    {
      echo "# 독립 검증 기록"
      echo
      echo "- 일시: $(date '+%F %T')"
      echo "- 검증 모델: Codex CLI $(codex --version 2>/dev/null | awk '{print $2}')${MODEL:+ ($MODEL)}, 추론 강도 $EFFORT"
      echo "- 모드: $MODE_DESC"
      echo "- 유형: ${TYPES:-일반}"
      echo
      echo "## 브리핑"
      echo
      echo "$BRIEF_TEXT"
      echo
      echo "## Codex 보고"
      echo
      cat "$TMP/report.md"
      echo
      echo "## 오케스트레이터 처리 기록"
      echo
      echo "(Codex 지적을 수용/기각한 결과와 근거를 여기에 적는다)"
    } > "$FILE" && echo "[검증 기록 저장] $FILE" || echo "[검증 기록 저장 실패] $FILE" >&2
  fi
fi
