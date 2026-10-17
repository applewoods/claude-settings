#!/usr/bin/env bash
# Claude 설정 저장소 자동 동기화 (Claude Code hook에서 호출)
#   sync.sh pull  : 세션 시작 시 원격 변경 받기 (SessionStart)
#   sync.sh push  : 턴이 끝날 때 바뀐 설정을 커밋·푸시 (Stop)
# push 단계에서는 ~/.claude/skills 에 새로 생긴 일반 폴더(링크가 아닌 스킬)를
# 저장소로 옮기고 링크로 바꿔서 함께 관리한다.
# 실패해도 Claude 작업을 막지 않도록 항상 0으로 끝내고, 기록은 로그에 남긴다.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
LOG="$REPO/.sync.log"
MODE="${1:-push}"

log() { echo "$(date '+%F %T') [$MODE] $*" >> "$LOG"; }
cd "$REPO" || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# 동시에 여러 세션이 돌 때 겹치지 않게 잠금
LOCK="$REPO/.git/claude-sync.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  # 10분 넘은 잠금은 비정상 종료로 보고 정리
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +10 2>/dev/null)" ]; then rmdir "$LOCK"; mkdir "$LOCK" || exit 0; else exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

adopt_new_skills() {
  for dir in "$CLAUDE_DIR"/skills/*/; do
    [ -d "$dir" ] || continue
    name="$(basename "$dir")"
    path="$CLAUDE_DIR/skills/$name"
    [ "$name" = "synced" ] && continue          # 앱이 관리하는 폴더
    [ -L "$path" ] && continue                  # 이미 저장소에 연결됨
    [ -f "$path/SKILL.md" ] || continue         # 스킬이 아니면 무시
    if [ -e "$REPO/skills/$name" ]; then log "건너뜀: skills/$name 이 저장소에 이미 있음"; continue; fi
    mv "$path" "$REPO/skills/$name" && ln -s "$REPO/skills/$name" "$path" && log "새 스킬 편입: $name"
  done
  # 서브 에이전트 정의(~/.claude/agents/*.md)도 같은 방식으로 편입
  mkdir -p "$REPO/agents"
  for path in "$CLAUDE_DIR"/agents/*.md; do
    [ -f "$path" ] && [ ! -L "$path" ] || continue
    name="$(basename "$path")"
    if [ -e "$REPO/agents/$name" ]; then log "건너뜀: agents/$name 이 저장소에 이미 있음"; continue; fi
    mv "$path" "$REPO/agents/$name" && ln -s "$REPO/agents/$name" "$path" && log "새 에이전트 편입: $name"
  done
}

case "$MODE" in
  pull)
    if [ -z "$(git status --porcelain)" ]; then
      git pull --ff-only -q >>"$LOG" 2>&1 && log "pull 완료" || log "pull 실패"
    else
      log "로컬 변경이 있어 pull 생략"
    fi
    ;;
  push)
    adopt_new_skills
    [ -z "$(git status --porcelain)" ] && exit 0
    changed="$(git status --porcelain | awk '{print $2}' | sed 's|/.*||' | sort -u | paste -sd, -)"
    git add -A
    git commit -q -m "자동 동기화: ${changed}" >>"$LOG" 2>&1 || { log "커밋 실패"; exit 0; }
    if git push -q >>"$LOG" 2>&1; then
      log "push 완료 ($changed)"
    else
      # 다른 컴퓨터에서 먼저 올린 경우: 받아서 합친 뒤 다시 시도
      git pull --rebase -q >>"$LOG" 2>&1 && git push -q >>"$LOG" 2>&1 && log "rebase 후 push 완료" || log "push 실패 — 수동 확인 필요"
    fi
    ;;
esac
exit 0
