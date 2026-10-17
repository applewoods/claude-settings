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

echo
echo "완료. 새 Claude Code 세션부터 적용됩니다."
command -v node >/dev/null && echo "node $(node -v)" || echo "참고: node가 없어 design-taste-frontend의 검사 스크립트는 실행되지 않습니다(Node 22+ 필요)."
