# 배포: 자체 서버 + Docker Compose + 리버스 프록시

> 언제 읽나: Dockerfile·`docker-compose.yml`을 처음 만들거나 고칠 때, 서버에 처음 올릴 때, 배포·롤백·백업 절차를 정할 때.
> **운영 서버 배포, 운영 설정·비밀값·방화벽 변경 전에는 반드시 사용자에게 무엇이 바뀌는지 보여 주고 확인받는다.**

## 1. Docker 이미지 원칙 [모두]
- **멀티 스테이지 빌드**: 빌드 도구·컴파일러는 빌드 단계에만, 실행 이미지는 결과물만. Python은 `python:3.x-slim` 기반(+ `uv`로 의존성 설치), Next.js는 `output: "standalone"`으로 빌드해 `node:xx-slim`/`alpine`에서 실행.
- 베이스 이미지 태그를 고정한다(`python:3.12-slim` ✓, `latest` ✕). 출시 서비스는 다이제스트(`@sha256:...`)까지 고정하고 정기적으로 올린다.
- **루트로 실행하지 않는다**: `USER app`(또는 node 이미지의 `node`). 컨테이너 탈출 시 피해를 줄인다.
- 의존성 파일을 먼저 복사·설치하고 소스는 나중에 복사한다(레이어 캐시). 락 파일(`uv.lock`, `package-lock.json`/`pnpm-lock.yaml`)로 설치해 재현성을 보장한다.
- `.dockerignore`에 `.env`, `.git`, `node_modules`, `__pycache__`, 데이터·모델 파일을 넣는다. 안 넣으면 비밀값이 이미지에 들어간다.
- **비밀값을 이미지에 굽지 않는다.** `ARG`/`ENV`로 넣은 값은 `docker history`로 보인다. 빌드에 꼭 필요하면 BuildKit `--secret`.
- `CMD`는 exec 형식(`["uvicorn", "app.main:app", ...]`). 셸 형식이면 종료 신호(SIGTERM)가 앱에 전달되지 않아 진행 중 요청이 강제로 끊긴다. Compose에 `init: true`를 주면 좀비 프로세스 정리도 된다.
- 앱은 SIGTERM을 받으면 새 요청을 멈추고 진행 중 요청을 마친 뒤 종료(graceful shutdown). uvicorn은 기본 지원, 워커는 진행 중 작업 처리 방식을 확인한다. Compose `stop_grace_period`(기본 10초)를 가장 긴 요청보다 길게.
- 이미지 크기 감각: FastAPI slim 이미지 200~400MB, Next.js standalone 150~300MB 정도면 정상. GPU·PyTorch 이미지는 수 GB가 정상이니 베이스 이미지를 따로 관리한다.
- 이미지 태그는 git SHA로 붙인다(`app:3f2a1c9`). `latest`만 쓰면 롤백할 대상이 없다.

## 2. Compose 운영 [모두]
```yaml
services:
  caddy:
    image: caddy:2            # 태그 고정 권장
    ports: ["80:80", "443:443"]
    volumes: [./Caddyfile:/etc/caddy/Caddyfile:ro, caddy_data:/data, caddy_config:/config]
    restart: unless-stopped
  api:
    image: myapp-api:${APP_VERSION}
    env_file: .env
    expose: ["8000"]          # 외부 공개 안 함. caddy만 접근
    depends_on: { db: { condition: service_healthy } }
    healthcheck: { test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"], interval: 10s, timeout: 3s, retries: 3, start_period: 20s }
    restart: unless-stopped
    init: true
    logging: { driver: json-file, options: { max-size: "10m", max-file: "5" } }
  db:
    image: postgres:17        # 버전은 database 스킬 기준
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck: { test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER}"], interval: 5s, retries: 10 }
    restart: unless-stopped
volumes: { pgdata: {}, caddy_data: {}, caddy_config: {} }
```
- **DB 포트를 `ports:`로 열지 않는다.** Docker가 연 포트는 호스트 방화벽(ufw)을 **우회**한다(Docker가 iptables 규칙을 직접 넣기 때문). 꼭 필요하면 `127.0.0.1:5432:5432`로 로컬에만 묶고 SSH 터널로 접속한다.
- slim 이미지에는 `curl`이 없을 수 있어 헬스체크는 앱 런타임(python/node)으로 하거나 설치한다.
- `depends_on`만으로는 "시작됨"까지만 기다린다. `condition: service_healthy`를 써야 DB가 실제로 준비될 때까지 기다린다.
- 개발용과 운영용 차이는 `compose.override.yml`(개발: 소스 마운트, 핫 리로드, 포트 공개)로 나누고, 운영은 `-f compose.yml -f compose.prod.yml`처럼 명시한다.
- 마이그레이션은 앱 시작 명령에 섞지 말고 배포 절차의 별도 단계(`docker compose run --rm api alembic upgrade head`)로 실행한다. 컨테이너를 여러 개 띄우면 동시에 마이그레이션이 돌기 때문이다. 세부는 `database` 스킬.
- 리소스 제한(`mem_limit`, `cpus` 또는 `deploy.resources`)을 둬서 한 컨테이너의 메모리 누수가 서버 전체를 죽이지 않게 한다 **[출시]**.

## 3. 리버스 프록시: Caddy 우선
| | Caddy | Nginx |
|---|---|---|
| HTTPS | 자동 발급·갱신(Let's Encrypt) | certbot 등 별도 구성 |
| 설정 | 짧음 | 길지만 세밀함, 자료 많음 |
| 추천 | **기본값**. 단일 서버·소규모 | 이미 Nginx 운영 중이거나 세밀한 캐시·레이트 리밋 설정이 필요할 때 |
- 공통 설정: HTTP → HTTPS 리다이렉트, 요청 본문 크기 제한, 업스트림 타임아웃(앱 타임아웃보다 길게, `architecture.md` 4절), `X-Forwarded-For/Proto` 전달 + 앱에서 신뢰 프록시 설정, gzip/zstd 압축.
- SSE·스트리밍: Caddy는 `text/event-stream` 응답을 즉시 흘려보낸다(공식 문서, 2026-10 확인). Nginx는 버퍼링을 끄거나(`proxy_buffering off;`) 앱이 `X-Accel-Buffering: no` 헤더를 보내야 한다. 안 하면 스트리밍이 끝에 한꺼번에 나온다.
- 서버 방화벽: 22(가능하면 SSH 키 전용, 비밀번호 로그인 끔), 80, 443만 연다.

## 4. 시크릿 관리
| 단계 | 방법 |
|---|---|
| 데모·내부 | 서버의 `.env`(권한 `600`, 소유자만 읽기). 깃에는 `.env.example`만 |
| 출시 | 위 + Compose `secrets:`(컨테이너 안 `/run/secrets/*` 파일로 마운트, 환경변수보다 노출 경로가 적음) 또는 SOPS/age로 암호화한 파일을 깃에 두고 배포 시 복호화. 키 교체 절차를 문서화 |
- 환경변수는 `docker inspect`, 에러 리포트, 자식 프로세스로 새기 쉽다. 그래서 출시 서비스는 파일 마운트를 검토한다.
- 개발·스테이징·운영의 비밀값을 서로 다르게 쓴다. 운영 DB 비밀번호가 개발자 노트북에 있으면 안 된다.
- LLM API 키는 서비스별·환경별로 따로 발급하고, 공급자 콘솔에서 사용 한도를 걸어 둔다(키 유출 시 피해 상한).

## 5. 배포 절차와 무중단
- 기본 절차: (1) CI 또는 로컬에서 테스트 통과 → (2) 이미지 빌드·태그(git SHA) → (3) 레지스트리 푸시(GHCR 등) → (4) 서버에서 `APP_VERSION=<sha> docker compose pull && docker compose up -d` → (5) 헬스체크·스모크 테스트 → (6) 실패 시 롤백. 서버에서 직접 `git pull && build`는 데모까지만.
- `docker compose up -d`로 이미지를 바꾸면 컨테이너가 **교체되는 몇 초 동안 끊긴다.** 판단:
  - 데모·내부 도구: 몇 초 중단 허용. 사용자 적은 시간에 배포.
  - 출시 서비스: 블루-그린(같은 서비스를 `api_blue`/`api_green` 두 벌 두고, 새 쪽이 healthy가 되면 Caddy 업스트림을 바꾼 뒤 리로드, 옛 쪽 종료) 또는 `docker rollout` 같은 Compose 플러그인 [확인 필요: 플러그인 유지 상태]. 이 이상(자동 확장·다중 서버)이 필요해지면 그때 오케스트레이터(Kubernetes 등)나 관리형 플랫폼을 검토한다. 미리 가지 않는다.
- 무중단 배포의 진짜 어려움은 **DB 스키마**다. 새 코드와 옛 코드가 동시에 도는 순간이 있으므로 마이그레이션은 확장 → 코드 배포 → 축소 순서로(`database` 스킬).
- 배포 기록: 언제, 어떤 SHA, 누가, 마이그레이션 여부를 `docs/deploy-log.md`나 깃 태그로 남긴다.

## 6. 롤백
- 롤백 = 이전 SHA 이미지로 `APP_VERSION` 바꿔 다시 `up -d`. 이게 1분 안에 되도록 이전 이미지를 서버·레지스트리에 남겨 둔다(최근 5개 정도).
- 마이그레이션이 포함된 배포는 코드만 되돌리면 깨질 수 있다. 그래서 마이그레이션은 **옛 코드와도 호환되게** 만든다(컬럼 삭제는 다음 배포에서). 되돌릴 수 없는 마이그레이션 전에는 백업.
- 롤백 기준을 배포 전에 정한다: 예) 배포 후 10분 안에 5xx 비율이 평소의 2배 이상, 또는 핵심 흐름 스모크 테스트 실패 → 원인 분석 전에 먼저 롤백.

## 7. 백업 [모두, 실제 사용자 데이터가 있으면]
- DB 백업 방법·주기·보존·복구 절차의 세부는 `database` 스킬을 따른다. 백엔드 쪽에서 챙길 것:
  - DB 외 상태도 백업 대상인지 확인: 업로드 파일 볼륨, Caddy 인증서 볼륨(재발급 가능하지만 발급 한도 주의), `.env`(별도 안전한 곳에).
  - **3-2-1 원칙**: 사본 3개, 매체 2종, 1개는 서버 밖(다른 지역 객체 저장소). 같은 서버 디스크의 백업은 서버가 죽으면 같이 사라진다.
  - 복구를 실제로 해 본 적 없는 백업은 백업이 아니다. 출시 서비스는 정기적으로(예: 월 1회) 빈 환경에 복구 테스트.
  - 백업 성공·실패를 알림에 연결(`observability.md` 6절).

## 8. 서버 기본 보안 [출시]
- OS 보안 업데이트 자동 적용(unattended-upgrades), SSH 비밀번호 로그인·root 로그인 끔, fail2ban 검토.
- Docker 그룹에 들어간 사용자는 사실상 root다. 배포 계정을 최소화한다.
- 운영 서버에서 직접 코드를 고치지 않는다. 모든 변경은 깃 → 이미지 → 배포로.
