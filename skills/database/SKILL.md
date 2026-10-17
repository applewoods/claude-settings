---
name: database
description: 데이터베이스 매뉴얼. 테이블·스키마를 설계하거나 바꿀 때, 마이그레이션을 만들거나 운영 DB에 적용할 때, 쿼리를 작성·최적화하거나 느린 쿼리를 분석할 때, 트랜잭션·동시성(재고·결제·작업 큐)을 다룰 때, 벡터 검색(RAG, pgvector)을 붙일 때, DB 백업·복구·커넥션·VACUUM 등 운영을 다룰 때, DB 권한·RLS·개인정보 보존을 설계할 때, DB 변경을 리뷰할 때 사용.
---

# 데이터베이스 매뉴얼

> **팀으로 진행:** 여러 단계이거나 검증이 중요한 일은 `team-orchestration` 스킬의 "개발" 팀 구성(scout·builder·expert·verifier)으로 나눠 맡긴다. 각 팀원은 이 매뉴얼을 따른다.

API·인증·비밀번호 해시 알고리즘·서버 배포는 `backend` 스킬 소관이다. 여기서는 DB 계층만 다룬다.

## 기본 스택 (사용자 결정)
- **DB**: PostgreSQL. 로컬과 운영 모두 Docker로 띄운다. 기준 버전 PostgreSQL 18.
- **벡터 검색**: pgvector. 별도 벡터 DB는 측정으로 필요가 확인될 때만 제안한다.
- **ORM·마이그레이션**: 백엔드 스택에 맞춘다. Python(FastAPI) → SQLAlchemy + Alembic / TypeScript(Next.js) → Drizzle 또는 Prisma.

## 적용 범위 구분
연구 데모부터 출시 서비스까지 만든다. 규칙마다 범위가 다르다.
- **[필수]** 모든 경우: 마이그레이션, 제약조건, 파라미터 바인딩, 개인정보 최소화, 운영 변경 전 확인.
- **[출시]** 실제 사용자 데이터가 있는 서비스: 무중단 마이그레이션, PITR 백업·복구 리허설, 최소 권한 역할, RLS, 모니터링.
- 범위가 애매하면 사용자에게 "데모인지 출시 서비스인지" 한 번 묻고 진행한다.

## 핵심 원칙
1. **스키마는 마이그레이션으로만 바꾼다.** DB에 직접 `ALTER`하지 않는다. 자동 생성된 마이그레이션은 초안이다 — 반드시 읽고 고친다(Alembic은 이름 변경을 drop+add로 만든다).
2. **운영 DB는 바꾸기 전에 묻는다.** 데이터 수정·삭제, 스키마 변경, 마이그레이션 적용, 세션 종료·재시작, `docker compose down -v` 전에 무엇이 바뀌는지(영향 행 수, 예상 락·시간, 백업 시점)를 보여 주고 확인받는다. 되돌리기 어려운 변경은 백업부터.
3. **무결성은 DB가 지킨다.** NOT NULL·UNIQUE·FK·CHECK를 기본으로 건다. 앱의 "조회 후 삽입"은 동시 요청에서 깨진다.
4. **측정하고 고친다.** 인덱스·비정규화·캐시는 `EXPLAIN (ANALYZE, BUFFERS)`와 `pg_stat_statements`로 병목을 확인한 뒤에. 운영과 비슷한 데이터량에서 본다.
5. **트랜잭션은 짧게.** 트랜잭션 안에서 외부 API·LLM·파일 업로드를 호출하지 않는다.
6. **락을 의식한다.** 운영 DDL에는 `SET lock_timeout`을 건다. 락을 기다리는 DDL 하나가 그 뒤의 모든 쿼리를 막는다.
7. **개인정보는 최소로, 기한을 정해서.** 필요한 것만 저장, 비밀번호는 해시로만, 민감정보 암호화 검토, 보존 기간·파기를 설계 단계에서 정한다. 로그·테스트 데이터에 실제 개인정보를 넣지 않는다.
8. **복구해 보지 않은 백업은 백업이 아니다.** [출시]
9. **스키마 문서를 유지한다.** `docs/database.md`에 테이블 설명, ERD(Mermaid `erDiagram`), 보존 기간, 예외 결정(비정규화·JSONB·소프트 삭제)의 이유를 두고 스키마와 함께 고친다.

## 깊은 내용: references/ (필요할 때만 읽는다)
| 파일 | 언제 읽나 |
|---|---|
| `references/schema-design.md` | 새 테이블, 키·타입·제약 선택, 정규화/비정규화, 소프트 삭제·감사 로그, 다중 테넌트, JSONB 판단 |
| `references/indexing-and-queries.md` | 느린 쿼리, 인덱스 추가·삭제, EXPLAIN 읽기, N+1, 페이지네이션, 흔한 느린 패턴 |
| `references/transactions.md` | 재고·결제·좌석 등 동시성, 작업 큐, 격리 수준, 락 대기·데드락·serialization 에러 |
| `references/migrations.md` | 마이그레이션 작성·리뷰·운영 적용, 큰 테이블 변경, CONCURRENTLY, expand/contract, 백필, 롤백 |
| `references/operations.md` | Docker 구성·버전 업그레이드, 백업·PITR·복구 리허설, 커넥션 풀·PgBouncer, VACUUM, 모니터링, 장애 대응 |
| `references/pgvector.md` | 임베딩 테이블, 벡터 인덱스(HNSW/IVFFlat), 거리 함수, 필터+벡터, 재현율 측정, 모델 교체 |
| `references/security-privacy.md` | DB 역할·권한, RLS, 컬럼 암호화, 개인정보 보존·파기·탈퇴, 테스트 데이터 |
| `references/review-checklist.md` | DB 변경 리뷰, verifier 브리핑에 붙일 체크리스트 |

## 작업 절차
1. **파악**: 기존 스키마(`docs/database.md`, 모델·마이그레이션 폴더), ORM, PostgreSQL·pgvector 버전(`SELECT version();`, `pg_extension`), 데모/출시 범위를 확인한다.
2. **설계**: 요구사항을 엔터티·관계·제약으로 옮긴다. 아래 결정 기준표로 고르고, 표에 없는 판단은 해당 reference를 읽는다. 스키마 설계·동시성 설계처럼 틀리면 비용이 큰 결정은 expert에게.
3. **구현**: ORM 모델 + 마이그레이션 생성 → 생성 파일을 읽고 수정 → 로컬 적용.
4. **확인**: `upgrade → downgrade → upgrade` 실행, 핵심 쿼리의 `EXPLAIN`, 동시성 로직은 동시 요청 테스트, 제약 위반 케이스 테스트.
5. **문서**: `docs/database.md`의 ERD·설명·보존 기간 갱신.
6. **운영 적용** (해당 시): `migrations.md` 7절 절차 — 위험도 분류 → 사용자 확인 → `lock_timeout` 걸고 적용 → 적용 후 확인.

## 결정 기준표
| 질문 | 기본 선택 | 다른 선택을 할 때 |
|---|---|---|
| PK 타입 | `bigint GENERATED ALWAYS AS IDENTITY` | URL·API에 ID 노출, 클라이언트 생성, DB 병합 → UUID v7(`uuidv7()`, PG18+). 생성 시각 노출이 문제 → v4 또는 내부 bigint + 외부 `public_id` |
| 문자열 / 시각 / 돈 | `text`(+CHECK 길이) / `timestamptz` / `numeric` 또는 최소 단위 정수 | — (`timestamp`, `float`, `money`는 쓰지 않는다) |
| 상태값 | `text + CHECK` | 값에 속성이 붙음 → 참조 테이블. 절대 안 바뀜 → ENUM |
| 반구조 데이터 | 컬럼 | 키가 행마다 다르고 조건 검색이 드묾(원문 페이로드, 사용자 정의 필드) → JSONB |
| 삭제 | 하드 삭제 | 사용자 복구 기능 → 소프트 삭제 + 부분 unique. 변경 추적 → 감사 로그 테이블 |
| 다중 테넌트 | 공유 테이블 + `tenant_id`(+[출시] RLS) | 규제상 물리 분리 → 스키마/DB 분리 |
| 인덱스 종류 | B-tree(등호 → 범위·정렬 순 복합) | JSONB·배열·전문검색·부분문자열 → GIN, 범위 겹침 → GiST, 거대 append-only 시계열 → BRIN |
| 페이지네이션 | keyset(`(created_at, id) <`) | 관리자 화면·소량·페이지 번호 필요 → OFFSET |
| 동시 갱신 | 원자적 UPDATE(`SET n = n - 1 WHERE n > 0`), `ON CONFLICT` | 폼 편집 충돌 → 낙관적(version). 복잡한 판단 → `FOR UPDATE`. 작업 큐 → `FOR UPDATE SKIP LOCKED` |
| 격리 수준 | READ COMMITTED | 여러 쿼리가 같은 시점 → REPEATABLE READ. 여러 행 불변식 → SERIALIZABLE(둘 다 재시도 필수) |
| 큰 테이블 스키마 변경 | [출시] expand/contract, CONCURRENTLY, NOT VALID→VALIDATE | 데모·점검 시간 가능 → 한 번에(백업·확인은 유지) |
| 백업 | 데모: `pg_dump` 정기 + 외부 사본 | [출시] pgBackRest/WAL-G로 PITR + 복원 리허설 |
| 커넥션 | 앱 풀(인스턴스 수 × 풀 크기 ≤ DB 한도) | 인스턴스·워커가 많거나 서버리스 → PgBouncer(transaction 모드 제약 확인) |
| 벡터 인덱스 | 수만 개 이하 → 인덱스 없이 측정 | 기본 HNSW(`m`16/`ef_construction`64, `ef_search`로 튜닝). 정적 코퍼스·빌드 제약 → IVFFlat |
| 벡터 거리 | 코사인 `<=>` + `vector_cosine_ops` | 정규화된 벡터 → 내적 `<#>`. 모델이 L2 기준 → `<->`. 연산자와 opclass 일치 필수 |
| 민감정보 | 수집하지 않기 | 필요하면 앱 계층 암호화(키는 DB 밖) + 검색용 blind index |

## 하지 말 것
- 운영 DB에서 확인 없이 `DELETE`/`UPDATE`/`DROP`/`TRUNCATE`, `docker compose down -v`, 세션 강제 종료.
- `lock_timeout` 없는 운영 DDL, 운영 중 일반 `CREATE INDEX`·`VACUUM FULL`.
- 이미 적용된 마이그레이션 파일 수정, 운영에 `db push`/`migrate dev`.
- 앱을 superuser(Docker의 `POSTGRES_USER`)로 접속시키기, DB 포트 외부 공개.
- 메이저 버전 업그레이드를 이미지 태그 교체만으로 하기(데이터 형식이 다르다).
- 문자열을 이어 붙여 SQL 만들기.

## 완료 기준
- [ ] 스키마 변경이 마이그레이션 파일로 남아 있고, 생성 파일을 검토했으며, 로컬에서 적용·되돌리기·재적용을 실제로 해 봤다.
- [ ] 제약조건(NOT NULL·UNIQUE·FK·CHECK)과 FK 인덱스가 있고, 키·타입이 결정 기준표에 맞다(벗어나면 이유를 문서에 적었다).
- [ ] 새 쿼리 패턴에 맞는 인덱스가 있고, N+1이 없으며, [출시] 핫패스는 운영 규모 데이터로 `EXPLAIN`을 확인했다.
- [ ] 동시성이 걸린 로직은 원자적 갱신·락·멱등성 중 하나로 처리했고 동시 요청 테스트를 했다.
- [ ] 운영 DB 변경은 사용자 확인을 받았고, [출시] 큰 테이블 변경은 `migrations.md`의 안전한 방법을 썼다.
- [ ] 개인정보 저장 방식(최소 수집·해시·암호화 검토·보존 기간)이 규칙에 맞다.
- [ ] `docs/database.md`의 ERD·설명·보존 기간이 최신이다.
- [ ] 검증이 중요한 변경은 `references/review-checklist.md`로 점검했다(해당 없는 항목은 "해당 없음" 표시).
