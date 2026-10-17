#!/usr/bin/env bash
# Claude 설정 저장소 자동 동기화 (Claude Code hook에서 호출)
#   sync.sh pull  : 세션 시작 시 원격 변경 받기 (SessionStart)
#   sync.sh push  : 턴이 끝날 때 바뀐 설정을 커밋·푸시 (Stop)
# push 단계에서는 ~/.claude/skills 에 새로 생긴 일반 폴더(링크가 아닌 스킬)를
# 저장소로 옮기고 링크로 바꿔서 함께 관리한다.
# 실패해도 Claude 작업을 막지 않도록 항상 0으로 끝내고, 기록은 로그에 남긴다.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -n "${CLAUDE_CONFIG_DIR:-}${HOME:-}" ] || exit 0
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

link_repo_items() {
  # 저장소에는 있는데 ~/.claude에 연결되지 않은 스킬·에이전트를 연결한다(다른 컴퓨터에서 추가된 것).
  # 같은 이름의 실제 폴더·파일이 이미 있으면 덮지 않고 로그만 남긴다.
  mkdir -p "$CLAUDE_DIR/skills" "$CLAUDE_DIR/agents"
  for dir in "$REPO"/skills/*/; do
    [ -d "$dir" ] || continue
    name="$(basename "$dir")"; dst="$CLAUDE_DIR/skills/$name"
    if [ -L "$dst" ] || [ ! -e "$dst" ]; then
      [ "$(readlink "$dst" 2>/dev/null)" = "$REPO/skills/$name" ] && continue
      ln -sfn "$REPO/skills/$name" "$dst" && log "스킬 연결: $name"
    else
      log "건너뜀: ~/.claude/skills/$name 이 링크가 아닌 실제 폴더로 있음"
    fi
  done
  for file in "$REPO"/agents/*.md; do
    [ -e "$file" ] || continue
    name="$(basename "$file")"; dst="$CLAUDE_DIR/agents/$name"
    if [ -L "$dst" ] || [ ! -e "$dst" ]; then
      [ "$(readlink "$dst" 2>/dev/null)" = "$file" ] && continue
      ln -sfn "$file" "$dst" && log "에이전트 연결: $name"
    else
      log "건너뜀: ~/.claude/agents/$name 이 링크가 아닌 실제 파일로 있음"
    fi
  done
}

git_busy() {
  # rebase·merge 도중이거나, 브랜치를 벗어났거나, 미해결 충돌 파일이 있으면 그 이유를 출력한다
  local p
  for p in rebase-merge rebase-apply MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD sequencer BISECT_LOG; do
    [ -e "$(git rev-parse --git-path "$p")" ] && { echo "$p 진행 중"; return 0; }
  done
  [ -e "$(git rev-parse --git-path claude-sync-applying)" ] && { echo "자동 rebase 반영이 중간에 끊김(.git/claude-sync-applying 참고)"; return 0; }
  git symbolic-ref -q HEAD >/dev/null || { echo "브랜치가 아닌 상태(detached HEAD)"; return 0; }
  [ -n "$(git diff --name-only --diff-filter=U)" ] && { echo "미해결 충돌 파일 있음"; return 0; }
  return 1
}

notify() {
  # SessionStart hook 출력: 사용자에게 보이는 systemMessage + Claude가 읽는 additionalContext
  [ "$MODE" = pull ] || return 0
  local s="$1"
  s="${s//\\/\\\\}"; s="${s//\"/\\\"}"                          # JSON 문자열 이스케이프
  s="$(printf '%s' "$s" | tr '\000-\037' ' ')"                   # 개행 등 제어 문자는 공백으로
  printf '{"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$s" "$s"
}

if reason="$(git_busy)"; then
  log "동기화 중단: $reason — 수동 확인 필요 ($REPO)"
  notify "[설정 동기화 중단] $REPO 저장소가 $reason 상태입니다. 자동 동기화를 멈췄으니 직접 정리해 주세요 (git status 확인)."
  exit 0
fi

case "$MODE" in
  pull)
    if [ -z "$(git status --porcelain)" ]; then
      if git pull --ff-only -q >>"$LOG" 2>&1; then
        log "pull 완료"
      else
        log "pull 실패"
        # 로컬과 원격이 서로 다른 커밋을 가진 경우(다른 컴퓨터와 같은 곳을 고쳐 자동 합치기 실패 등)
        counts="$(git rev-list --left-right --count 'HEAD...@{u}' 2>/dev/null)"
        ahead="${counts%%[[:space:]]*}"; behind="${counts##*[[:space:]]}"
        if [ "${ahead:-0}" -gt 0 ] && [ "${behind:-0}" -gt 0 ]; then
          log "로컬과 원격이 갈라짐 (로컬 ${ahead}개, 원격 ${behind}개) — 수동 확인 필요"
          notify "[설정 동기화 충돌] $REPO 의 로컬 커밋 ${ahead}개와 원격 커밋 ${behind}개가 갈라져 자동으로 합치지 못했습니다. git pull --rebase 로 직접 합쳐 주세요."
        fi
      fi
    else
      log "로컬 변경이 있어 pull 생략"
    fi
    link_repo_items
    ;;
  push)
    adopt_new_skills
    link_repo_items
    git rev-parse -q --verify '@{u}' >/dev/null 2>&1 || { log "upstream 없음 — push 생략"; exit 0; }
    if [ -n "$(git status --porcelain)" ]; then
      changed="$(git status --porcelain | awk '{print $2}' | sed 's|/.*||' | sort -u | paste -sd, -)"
      git add -A
      git commit -q -m "자동 동기화: ${changed}" >>"$LOG" 2>&1 || { log "커밋 실패"; exit 0; }
    elif [ "$(git rev-list --count '@{u}..HEAD' 2>/dev/null)" = 0 ]; then
      exit 0   # 변경도 미푸시 커밋도 없음 (네트워크 없이 끝냄)
    fi
    # 지난번 push가 네트워크 등으로 실패해 남은 커밋도 여기서 다시 보낸다.
    # 합치기는 작업 트리 밖에서 하고, 성공한 결과만 실제 브랜치에 반영한다
    # (~/.claude가 링크로 읽는 파일에 충돌 표식이 잠깐이라도 생기지 않게).
    for attempt in 1 2; do
      git fetch -q >>"$LOG" 2>&1 || { log "fetch 실패 — 다음 턴에 다시 시도"; exit 0; }
      counts="$(git rev-list --left-right --count 'HEAD...@{u}' 2>>"$LOG")" || { log "커밋 수 조회 실패 — push 건너뜀"; exit 0; }
      ahead="${counts%%[[:space:]]*}"; behind="${counts##*[[:space:]]}"
      [ "${ahead:-0}" -gt 0 ] || exit 0
      if [ "${behind:-0}" -gt 0 ]; then
        up="$(git rev-parse '@{u}')"; orig="$(git rev-parse HEAD)"; branch="$(git symbolic-ref -q HEAD)"
        git merge-tree --write-tree --quiet HEAD "$up" >/dev/null 2>>"$LOG"; rc=$?
        if [ "$rc" -eq 1 ]; then
          log "로컬과 원격이 갈라지고 같은 곳을 고쳐 충돌 (로컬 ${ahead}개, 원격 ${behind}개) — push 건너뜀, 수동 확인 필요"
          exit 0
        elif [ "$rc" -ne 0 ]; then
          log "merge-tree 실행 오류 (코드 $rc) — push 건너뜀"; exit 0
        fi
        # 충돌이 없으면 임시 worktree에서 rebase 한 뒤 결과만 가져온다
        WT="$(mktemp -d 2>/dev/null)" && [ -d "$WT" ] || { log "임시 폴더 생성 실패 — push 건너뜀"; exit 0; }
        trap 'git worktree remove --force "$WT/wt" >/dev/null 2>&1; rm -rf "$WT"; git worktree prune; rmdir "$LOCK" 2>/dev/null' EXIT
        new=""
        if git worktree add -q --detach "$WT/wt" HEAD >>"$LOG" 2>&1; then
          if git -C "$WT/wt" rebase -q --no-update-refs "$up" >>"$LOG" 2>&1; then
            new="$(git -C "$WT/wt" rev-parse HEAD)"
          else
            git -C "$WT/wt" rebase --abort >>"$LOG" 2>&1
          fi
          git worktree remove --force "$WT/wt" >>"$LOG" 2>&1
        fi
        rm -rf "$WT"; git worktree prune
        [ -n "$new" ] || { log "임시 worktree에서 rebase 실패 — push 건너뜀, 수동 확인 필요"; exit 0; }
        # 브랜치는 시작 때 값($orig)일 때만 옮기고(그 사이 커밋·전환이 있으면 실패), 그다음 파일을 바꾼다.
        # read-tree -m -u는 그 사이 고친 파일과 겹치면 아무것도 쓰지 않고 멈추며, 그때는 브랜치를 되돌린다.
        # 반영 도중 끊기거나 되돌리기에 실패하면 표식이 남아, 다음 동기화가 잘못된 커밋을 만들지 않고 멈춘다.
        APPLYING="$(git rev-parse --git-path claude-sync-applying)"
        printf 'branch=%s\norig=%s\nnew=%s\n' "$branch" "$orig" "$new" > "$APPLYING" || { log "반영 표식 생성 실패 — push 건너뜀"; exit 0; }
        if [ "$(git symbolic-ref -q HEAD)" != "$branch" ] || ! git update-ref -m "claude-sync: rebase" "$branch" "$new" "$orig" 2>>"$LOG"; then
          rm -f "$APPLYING"; log "rebase 중 HEAD가 바뀜 — 반영하지 않음, 다음 턴에 다시 시도"; exit 0
        fi
        if ! git read-tree -m -u "$orig" "$new" >>"$LOG" 2>&1; then
          if git update-ref "$branch" "$orig" "$new" 2>>"$LOG"; then
            rm -f "$APPLYING"; log "rebase 결과 반영 실패 (작업 트리가 바뀜) — 되돌림, 다음 턴에 다시 시도"
          else
            log "rebase 결과 반영 실패 후 브랜치 되돌리기도 실패 — 동기화 중단, 수동 확인 필요 ($APPLYING)"
          fi
          exit 0
        fi
        rm -f "$APPLYING"
        log "원격 커밋 ${behind}개와 rebase 완료"
      fi
      if git push -q >>"$LOG" 2>&1; then
        log "push 완료 (커밋 ${ahead}개${changed:+, $changed})"
        exit 0
      fi
      log "push 실패 (시도 $attempt)"
    done
    log "push 실패 — 다음 턴에 다시 시도"
    ;;
esac
exit 0
