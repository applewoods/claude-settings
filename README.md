# Claude Code 개인 설정

여러 컴퓨터에서 Claude Code가 똑같이 동작하도록, 전역 지침(`CLAUDE.md`)과 업무별 매뉴얼(스킬)을 모아 둔 저장소입니다.

**원칙:** 에이전트는 하나만 두고, 업무마다 매뉴얼(스킬)을 쌓는다. 매뉴얼은 인터뷰로 만들고, 결과가 틀리면 채팅이 아니라 매뉴얼을 고친다.

---

## 빠른 설치

```bash
git clone https://github.com/applewoods/cluade-settings.git ~/cluade-settings
cd ~/cluade-settings
./install.sh
```

설치가 끝나면 **새로 시작하는 Claude Code 세션부터** 적용됩니다.

### 필요한 것
| 항목 | 용도 | 없으면 |
|---|---|---|
| git | 저장소 받기·동기화 | 필수 |
| Claude Code (CLI 또는 데스크톱 앱) | 설정을 읽는 주체 | 필수 |
| Node.js 22 이상 | `design-taste-frontend`의 검사 스크립트 | 그 스크립트만 실행 안 됨 |
| Chrome / Edge / Chromium | 같은 스크립트의 화면 검사 | 위와 같음 |

---

## 🤖 AI 에이전트를 위한 설치 지침

이 README를 읽고 사용자의 컴퓨터에 설정을 적용하는 AI는 아래 순서를 따르세요.

1. **저장소 위치 확인**: `~/cluade-settings`가 있으면 `git -C ~/cluade-settings pull`, 없으면 위 "빠른 설치"의 `git clone`을 실행한다.
2. **기존 설정 확인**: `~/.claude/CLAUDE.md`와 `~/.claude/skills/`에 이 저장소와 이름이 같은 항목이 있는지 본다. 있으면 사용자에게 알린다. `install.sh`가 기존 항목을 `~/.claude/backups/install-<시각>/`으로 옮기고(삭제하지 않음) 링크를 건다.
3. **설치 실행**: `./install.sh`를 실행한다. macOS·Linux는 그대로, Windows는 아래 "Windows" 절을 따른다.
4. **검증**:
   - `ls -l ~/.claude/CLAUDE.md ~/.claude/skills/`로 각 항목이 이 저장소를 가리키는 심볼릭 링크인지 확인한다.
   - 스킬 폴더마다 `SKILL.md`가 있고, 첫 부분에 `name:`과 `description:`이 있는지 확인한다.
   - 새 세션에서 사용 가능한 스킬 목록에 아래 "구성" 표의 스킬들이 보이는지 확인한다.
5. **선택 확인**: `node -v`가 22 이상인지, Chrome 계열 브라우저가 있는지 확인하고, 없으면 사용자에게 알린다(설치는 사용자 동의 후).
6. **하지 말 것**: `~/.claude/settings.json`, 인증 정보, `~/.claude/skills/synced/`(앱이 관리하는 폴더)는 건드리지 않는다. 사용자 확인 없이 기존 파일을 지우지 않는다.

### Windows
심볼릭 링크에 관리자 권한이나 개발자 모드가 필요합니다. 링크가 어려우면 복사로 설치하세요(대신 `git pull` 후 다시 복사해야 반영됨).

```powershell
$claude = "$env:USERPROFILE\.claude"
New-Item -ItemType Directory -Force "$claude\skills" | Out-Null
Copy-Item .\CLAUDE.md "$claude\CLAUDE.md" -Force
Get-ChildItem .\skills -Directory | ForEach-Object { Copy-Item $_.FullName "$claude\skills\" -Recurse -Force }
```

---

## 구성

```
cluade-settings/
├── CLAUDE.md          # 전역 지침 → ~/.claude/CLAUDE.md (모든 세션에서 항상 읽힘)
├── install.sh         # ~/.claude 에 심볼릭 링크 연결
└── skills/            # 업무별 매뉴얼 → ~/.claude/skills/<이름>/ (관련 작업일 때만 읽힘)
```

### CLAUDE.md (항상 적용, 짧게 유지)
나에 대해 · 소통 방식(한국어, 결론 먼저) · 꼭 지킬 것(인용·수치 지어내지 않기, 삭제 전 확인, 완료 전 직접 확인) · 일하는 방식(스킬 운영 원칙, 새 프로젝트는 인터뷰부터) · 모델 선택(haiku / sonnet / opus 기준).

### 스킬
| 스킬 | 언제 쓰이나 | 출처 |
|---|---|---|
| `project-interview` | 새 프로젝트 폴더(루트에 CLAUDE.md 없음)에서 첫 작업 전 인터뷰 → 프로젝트 CLAUDE.md 작성 | 직접 작성 |
| `paper-writing` | 논문 작성·교정·인용 (인용 확인, 원문→수정안 형식) | 직접 작성 |
| `data-analysis` | 데이터 분석·ML/DL 실험 (누수 방지, 재현성, 실행한 결과만 보고) | 직접 작성 |
| `service-planning` | 웹·앱 서비스 기획 (PRD, 유저 스토리, 화면 흐름, HTML 목업, MVP) | 직접 작성 |
| `ux-ui-design` | 디자인 기준(`docs/DESIGN.md`)과 어떤 디자인 스킬을 언제 쓸지 | 직접 작성 |
| `frontend` | Next.js · React Native(Expo) · Tailwind + shadcn/ui | 직접 작성 |
| `backend` | FastAPI 또는 Next.js 서버, 인증, Docker 자체 서버 배포 | 직접 작성 |
| `database` | PostgreSQL + pgvector, 마이그레이션, 개인정보 보호 | 직접 작성 |
| `design-taste-frontend` | 랜딩·소개 페이지의 "AI 티" 제거 (앱 화면용 아님) | [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) (MIT), 원본 그대로 |
| `web-design-guidelines` | 배포 전 UI 코드 검사(접근성, 포커스, 폼 등) | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) (MIT), 수정본 ↓ |

**`web-design-guidelines` 수정 사항:** 원본은 실행할 때마다 원격 규칙을 받아와 따릅니다. 검토하지 않은 내용이 적용되지 않도록, 2026-10-17에 검토한 규칙을 `skills/web-design-guidelines/guidelines.md`로 고정했습니다. 한국어 화면에서는 영어 문구 규칙을 건너뛰도록 했습니다.

### 함께 쓰는 다른 스킬 (이 저장소에 없음)
`ux-ui-design`은 `design:design-critique`, `design:ux-copy`, `design:accessibility-review`(Anthropic design 플러그인)를 참조합니다. 다른 컴퓨터에 이 플러그인이 없으면 해당 단계는 건너뛰거나, Claude 앱에서 design 플러그인을 켜세요.

---

## 설정을 바꾸고 동기화하기

설치는 링크 방식이라 `~/.claude/` 쪽을 고치면 곧 이 저장소의 파일을 고치는 것입니다.

```bash
# 이 컴퓨터에서 바꾼 내용 올리기
cd ~/cluade-settings && git add -A && git commit -m "스킬 수정: ..." && git push
```

```bash
# 다른 컴퓨터에서 받기
cd ~/cluade-settings && git pull
```

- **새 스킬을 추가하면** `skills/<이름>/SKILL.md`를 만든 뒤 `./install.sh`를 다시 실행해 링크를 겁니다.
- **외부 스킬을 추가할 때는** `SKILL.md`와 포함된 스크립트를 먼저 읽고 검토한 뒤 넣습니다. 라이선스 파일도 함께 둡니다.
- `CLAUDE.md`에는 항상 필요한 규칙만 둡니다. 특정 업무의 세부 규칙은 스킬로 보냅니다.

## 되돌리기
링크를 지우고 백업을 되돌리면 됩니다.

```bash
rm ~/.claude/CLAUDE.md && ls ~/.claude/backups/
```
