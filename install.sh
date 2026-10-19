#!/usr/bin/env bash
# Claude Code 설정 설치 스크립트
# 이 저장소의 CLAUDE.md와 skills/*를 ~/.claude 아래에 심볼릭 링크로 연결한다.
# 링크 방식이라 저장소에서 git pull 하면 설정이 바로 반영된다.
# 이미 같은 이름의 파일/폴더가 있으면 ~/.claude/backups/<시각>/ 으로 옮긴 뒤 연결한다(삭제하지 않음).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
BACKUP="$CLAUDE_DIR/backups/install-$(date +%Y%m%d-%H%M%S)"

mkdir -p "$CLAUDE_DIR/skills"

link() {
  local src="$1" dst="$2"
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
    echo "  = $dst (이미 연결됨)"
    return
  fi
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    mkdir -p "$BACKUP"
    mv "$dst" "$BACKUP/"
    echo "  ↪ 기존 $(basename "$dst") → $BACKUP/"
  fi
  ln -s "$src" "$dst"
  echo "  + $dst → $src"
}

echo "CLAUDE.md"
link "$REPO/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"

echo "skills"
for dir in "$REPO"/skills/*/; do
  name="$(basename "$dir")"
  link "$REPO/skills/$name" "$CLAUDE_DIR/skills/$name"
done

echo "agents"
mkdir -p "$CLAUDE_DIR/agents"
for file in "$REPO"/agents/*.md; do
  [ -e "$file" ] || continue
  link "$file" "$CLAUDE_DIR/agents/$(basename "$file")"
done

echo "settings.json (env, auto-sync hooks, overwrite guard, ask rules)"
# ~/.claude/settings.json 에 hook과 권한 규칙을 추가한다(기존 설정은 유지, 중복 추가 안 함).
#   SessionStart → sync.sh pull : 세션 시작 시 다른 컴퓨터의 변경 받기
#   Stop         → sync.sh push : 턴이 끝날 때 바뀐 설정 커밋·푸시
#   PreToolUse(Write) → guard-overwrite.sh : 기존 파일 덮어쓰기 전에 묻기
#   permissions.ask   : 삭제·push·reset --hard·clean·compose down·패키지 설치는 항상 묻기
SETTINGS="$CLAUDE_DIR/settings.json" SYNC="$REPO/scripts/sync.sh" REPO="$REPO" python3 - <<'PY'
import json, os
path, sync = os.environ["SETTINGS"], os.environ["SYNC"]
data = json.load(open(path)) if os.path.exists(path) and os.path.getsize(path) else {}
# 스킬·문서가 저장소 위치를 찾을 수 있게 환경 변수로 등록
data.setdefault("env", {})["CLAUDE_SETTINGS_DIR"] = os.environ["REPO"]
print(f"  env CLAUDE_SETTINGS_DIR={os.environ['REPO']}")
hooks = data.setdefault("hooks", {})
wanted = {
    "SessionStart": {"type": "command", "command": f'"{sync}" pull', "timeout": 30},
    "Stop": {"type": "command", "command": f'"{sync}" push', "async": True, "timeout": 60},
}
for event, hook in wanted.items():
    groups = hooks.setdefault(event, [])
    # 저장소 위치가 바뀌었으면 예전 경로의 sync.sh hook은 지운다
    for g in groups:
        old = [h for h in g.get("hooks", []) if "/scripts/sync.sh" in h.get("command", "") and h.get("command") != hook["command"]]
        for h in old:
            print(f"  - {event}: {h['command']} (예전 경로)")
        g["hooks"] = [h for h in g.get("hooks", []) if h not in old]
    groups[:] = [g for g in groups if g.get("hooks")]
    if any(h.get("command") == hook["command"] for g in groups for h in g.get("hooks", [])):
        print(f"  = {event} (이미 등록됨)")
        continue
    groups.append({"hooks": [hook]})
    print(f"  + {event}: {hook['command']}")

# 기존 파일 덮어쓰기 전에 묻기 (PreToolUse, Write)
guard = f'"{os.environ["REPO"]}/scripts/guard-overwrite.sh"'
groups = hooks.setdefault("PreToolUse", [])
if any(h.get("command") == guard for g in groups for h in g.get("hooks", [])):
    print("  = PreToolUse(Write) 덮어쓰기 확인 (이미 등록됨)")
else:
    groups.append({"matcher": "Write", "hooks": [{"type": "command", "command": guard, "timeout": 10}]})
    print(f"  + PreToolUse(Write): {guard}")

# 되돌리기 어려운 명령은 항상 묻기 (기존 ask 규칙은 유지)
ask = data.setdefault("permissions", {}).setdefault("ask", [])
for rule in ["Bash(rm *)", "Bash(git push *)", "Bash(git reset --hard *)", "Bash(git clean *)",
             "Bash(docker compose down *)", "Bash(pip install *)", "Bash(pip3 install *)", "Bash(conda install *)"]:
    if rule not in ask:
        ask.append(rule)
        print(f"  + permissions.ask: {rule}")
tmp = path + ".tmp"
json.dump(data, open(tmp, "w"), ensure_ascii=False, indent=2)
os.replace(tmp, path)
PY

echo
echo "완료. 새 Claude Code 세션부터 적용됩니다."
command -v node >/dev/null && echo "node $(node -v)" || echo "참고: node가 없어 design-taste-frontend의 검사 스크립트는 실행되지 않습니다(Node 22+ 필요)."
