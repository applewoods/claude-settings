---
name: backend
description: 백엔드 개발 매뉴얼. API 서버를 설계·구현할 때, 로그인·인증·권한을 붙일 때, 서버 배포(Docker, 자체 서버)를 구성할 때, FastAPI나 Next.js 서버 기능(Route Handlers, Server Actions)을 작업할 때 사용.
---

# 백엔드 매뉴얼

> **팀으로 진행:** 여러 단계이거나 검증이 중요한 일은 `team-orchestration` 스킬의 "개발" 팀 구성(scout·builder·expert·verifier)으로 나눠 맡긴다. 각 팀원은 이 매뉴얼을 따른다.

## 스택 선택: 상황에 따라 추천
프로젝트를 시작할 때 아래 기준으로 추천하고, 이유를 한두 줄로 설명한 뒤 확정한다.
- **화면 중심·단순 CRUD** → Next.js 서버 기능(Route Handlers / Server Actions). FE와 한 프로젝트로 관리.
- **AI 모델·데이터 처리·Python 코드가 많음** → FastAPI(Python). FE(Next.js)와 분리.
- 둘 다 해당하면: Next.js가 화면과 일반 API를, FastAPI가 AI·무거운 처리를 맡는 구성을 검토한다.

## 인증: 상황에 따라 추천
- 직접 구현하지 않는다. 검증된 라이브러리를 쓴다.
  - Next.js 중심 → Auth.js
  - FastAPI 중심 → FastAPI용 인증 라이브러리, 또는 표준 OAuth2/JWT 방식
- 비밀번호를 직접 저장해야 하면 argon2·bcrypt로 해시한다.
- 자체 서버 배포가 기본이라 외부 인증 서비스를 쓸지는 비용·운영 부담을 비교해 제안한다.

## 기본 규칙
- **비밀값은 `.env`로.** API 키·DB 비밀번호·토큰을 코드에 넣지 않는다. `.env`는 `.gitignore`에 넣고, 필요한 키 목록은 `.env.example`에 값 없이 적는다.
- **입력 검증·권한 확인.** 모든 API에서 입력을 스키마(FastAPI는 Pydantic, TS는 Zod)로 검증하고, 요청한 사용자가 그 데이터에 접근할 권한이 있는지 확인한다.
- **테스트 작성.** 핵심 API는 테스트와 함께 만든다(FastAPI: pytest, TS: Vitest). 권한 없는 접근이 막히는지도 테스트한다.
- **API 문서.** FastAPI는 자동 OpenAPI 문서(`/docs`)를 유지한다. Next.js는 `docs/api.md`에 엔드포인트·입출력을 정리한다.

## 배포: 자체 서버 + Docker
- `Dockerfile`과 `docker-compose.yml`로 앱·DB·리버스 프록시를 함께 띄운다.
- HTTPS는 리버스 프록시(Caddy 또는 Nginx)로 처리한다.
- DB 데이터는 볼륨으로 유지하고, 백업 방법을 문서에 적는다.
- 운영 서버에 배포하거나 운영 설정을 바꾸기 전에는 반드시 묻는다.

## 완료 기준
- [ ] 테스트가 실제로 실행돼 통과했다.
- [ ] 새 API에 입력 검증과 권한 확인이 있다.
- [ ] 코드와 git에 비밀값이 없다(`.env.example`만 있음).
- [ ] API 문서가 최신이다.
- [ ] `docker compose up`으로 로컬에서 실제로 떴다(배포 구성을 바꾼 경우).
