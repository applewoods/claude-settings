# 인덱스와 쿼리

> 언제 읽나: 쿼리가 느릴 때, 인덱스를 추가·삭제할 때, 목록·검색 API를 만들 때, ORM 코드에서 쿼리 수가 많아 보일 때.

## 1. 원칙

- **측정 먼저.** "느릴 것 같다"로 인덱스를 만들지 않는다. `pg_stat_statements`(총 시간 순)로 가장 비싼 쿼리를 찾고 `EXPLAIN (ANALYZE, BUFFERS)`로 원인을 본다.
- **인덱스는 공짜가 아니다.** 인덱스마다 INSERT/UPDATE가 느려지고(HOT 업데이트 기회도 줄어듦) 디스크·캐시를 먹는다. 쓰기 많은 테이블에 인덱스 5~6개 이상이면 하나씩 정당화해 본다(경험칙).
- **안 쓰는 인덱스는 지운다.** `pg_stat_user_indexes.idx_scan = 0`이 통계 리셋 이후 충분히 긴 기간(최소 한 업무 주기) 유지되고, unique/PK/제약용이 아니면 삭제 후보. 복제본(replica)에서만 쓰는 인덱스가 있을 수 있으니 확인.

## 2. 인덱스 종류 선택

| 종류 | 언제 | 예 |
|---|---|---|
| **B-tree**(기본) | `=`, 범위, 정렬, `LIKE 'abc%'`(C collation 또는 `text_pattern_ops`) | 거의 모든 경우 |
| **GIN** | 한 행에 값이 여러 개: JSONB `@>`, 배열 `@>`/`&&`, 전문 검색 `tsvector`, `pg_trgm`(부분 문자열 `LIKE '%abc%'`, 유사도) | 태그 검색, 이름 부분 검색 |
| **GiST** | 범위·기하·겹침, 배제 제약, 최근접(KNN) | 예약 기간 겹침, PostGIS |
| **BRIN** | 수천만 행 이상 + 물리 순서와 값이 상관(append-only 시계열의 `created_at`) | 로그·센서 데이터. 크기가 B-tree의 수백분의 1 수준이지만 상관이 깨지면 무용 |
| **HNSW/IVFFlat** | 벡터 근사 최근접 | `pgvector.md` |
| Hash | 사실상 쓰지 않는다. B-tree가 `=`도 충분히 빠르다 | — |

**모양 선택**
- **복합 인덱스 컬럼 순서**: 등호 조건 컬럼 → 범위/정렬 컬럼. `WHERE user_id = ? ORDER BY created_at DESC` → `(user_id, created_at DESC)`. 다중 테넌트는 `tenant_id`가 맨 앞.
  - `(a, b)` 인덱스가 있으면 `(a)` 단독 인덱스는 보통 중복이다. PG18의 B-tree skip scan으로 선두 컬럼 조건 없이 `b`만 쓰는 경우도 일부 쓰일 수 있지만, 선두 컬럼의 고유값이 적을 때만 효과적이다.
- **부분 인덱스**: 조건이 항상 붙는 쿼리. `WHERE status = 'pending'`(전체의 1%) → `CREATE INDEX ... WHERE status = 'pending'`. 소프트 삭제의 `WHERE deleted_at IS NULL`.
- **표현식 인덱스**: `WHERE lower(email) = ?` → `(lower(email))`. 쿼리의 식과 **정확히 같은 식**이어야 쓰인다.
- **커버링(INCLUDE)**: `(user_id) INCLUDE (status, total)`로 index-only scan. 단 visibility map이 최신이어야(VACUUM이 잘 돌아야) 테이블 방문을 건너뛴다.

## 3. EXPLAIN ANALYZE 읽는 법

```sql
EXPLAIN (ANALYZE, BUFFERS) SELECT ...;   -- PG18은 ANALYZE에 BUFFERS가 기본 포함
```
- `EXPLAIN ANALYZE`는 **실제로 실행한다.** UPDATE/DELETE를 분석할 때는 `BEGIN; EXPLAIN ANALYZE ...; ROLLBACK;`. 운영 DB에서 무거운 쿼리를 ANALYZE로 돌리는 것도 부하다 → 사용자 확인.
- 아래에서 위로, 안쪽에서 바깥으로 읽는다. 시간은 노드 누적이다.

| 신호 | 뜻 | 조치 |
|---|---|---|
| `rows=`(추정) vs `actual rows=` 차이 10배 이상 | 통계가 틀림 → 잘못된 조인 방식·순서 | `ANALYZE 테이블`; 상관된 컬럼은 `CREATE STATISTICS`(extended stats); 편향이 큰 컬럼은 `ALTER COLUMN ... SET STATISTICS 1000` |
| `loops=N`이 큼 | 안쪽 노드가 N번 실행. 표시 시간은 1회 평균이라 × loops 해야 실제 | Nested Loop 안쪽에 인덱스가 있는지, 추정 오류로 Nested Loop가 선택됐는지 |
| `Rows Removed by Filter`가 반환 행보다 훨씬 큼 | 많이 읽고 많이 버림 | 필터 컬럼 인덱스 또는 부분 인덱스 |
| `Seq Scan` | 테이블 전체 읽기 | **항상 나쁜 건 아니다.** 작은 테이블이나 결과가 전체의 상당 비율(대략 5~10% 이상, 경험칙)이면 seq scan이 더 빠르다 |
| `Sort Method: external merge  Disk:` | 정렬이 `work_mem`을 넘어 디스크 사용 | 정렬 순서와 맞는 인덱스, 또는 해당 세션만 `SET work_mem` 증가 |
| `Buffers: shared read=` 큼 | 캐시에 없어 디스크에서 읽음 | 첫 실행인지(콜드 캐시) 반복 실행으로 확인 |
| `Heap Fetches:` 큼(Index Only Scan) | visibility map이 오래됨 | VACUUM 상태 점검 |

함정: 개발 DB에 데이터가 수백 건이면 플래너는 무조건 seq scan을 고른다. **운영과 비슷한 분포의 데이터**(`generate_series`로 생성)에서 계획을 봐야 의미가 있다.

## 4. N+1 문제

목록 N건을 가져온 뒤 각 행마다 연관 데이터를 1번씩 조회 → 쿼리 N+1번. ORM의 지연 로딩(lazy loading)이 주범.

- 발견: 개발 중 SQL 로그를 켠다(SQLAlchemy `echo=True`, Prisma `log: ['query']`). 한 요청에 비슷한 쿼리가 반복되면 N+1. 테스트에서 요청당 쿼리 수 상한을 단언하면 회귀를 막는다.
- SQLAlchemy: `selectinload()`(1:N, 쿼리 2번 — 기본 추천), `joinedload()`(N:1, 단건). 기본 관계를 `lazy="raise"`로 두면 실수로 지연 로딩할 때 에러가 나서 바로 드러난다. 비동기 세션에서는 지연 로딩 자체가 에러(`MissingGreenlet`)가 나므로 명시적 로딩이 필수.
- Prisma: `include`/`select`로 함께 가져온다. Drizzle: relational query의 `with`, 또는 직접 join.
- 집계가 필요하면 루프 대신 `GROUP BY` 한 번.

## 5. 페이지네이션

| 방식 | 언제 |
|---|---|
| `OFFSET/LIMIT` | 관리자 화면, 전체 수천 건 이하, "n페이지로 이동"이 필요할 때 |
| **keyset(커서)** | 무한 스크롤, API, 큰 테이블. 기본 추천 |

`OFFSET 100000`은 앞의 10만 행을 읽고 버린다 → 뒤로 갈수록 느려지고, 그 사이 삽입·삭제가 있으면 중복·누락이 생긴다.

keyset:
```sql
-- 정렬 키는 유일해야 한다: created_at만으로는 동률 시 누락 → id를 붙인다
SELECT * FROM posts
WHERE (created_at, id) < ($last_created_at, $last_id)
ORDER BY created_at DESC, id DESC
LIMIT 20;
-- 인덱스: (created_at DESC, id DESC)  (필터가 있으면 필터 컬럼을 앞에)
```
- 커서는 클라이언트에 불투명 문자열(base64 등)로 준다.
- 전체 건수(`COUNT(*)`)는 큰 테이블에서 비싸다(PostgreSQL은 MVCC 때문에 카운트를 캐시하지 않음). "약 1.2만 건"이면 충분한 화면은 `pg_class.reltuples` 추정치나 `EXPLAIN` 추정치를 쓰거나 "더 보기"만 둔다.

## 6. 흔한 느린 쿼리 패턴

| 패턴 | 왜 느린가 | 고치기 |
|---|---|---|
| `WHERE lower(email) = ?`, `WHERE date(created_at) = ?` | 컬럼에 함수 → 일반 인덱스 못 씀 | 표현식 인덱스, 또는 범위로 바꾸기: `created_at >= '2026-10-01' AND created_at < '2026-10-02'` |
| `LIKE '%검색어%'` | 앞이 와일드카드 → B-tree 불가 | `pg_trgm` + GIN. 한국어 형태소 검색이 필요하면 전문 검색 엔진·확장 검토 [확인 필요: 한국어 형태소 분석 확장 선택] |
| 타입 불일치(`bigint` 컬럼에 문자열 파라미터, `varchar` vs `text` 조인 시 캐스트) | 암묵 캐스트로 인덱스 무시 가능 | 파라미터 타입을 컬럼과 맞춘다 |
| `WHERE a = ? OR b = ?` | 단일 인덱스로 처리 곤란 | 각 컬럼 인덱스(BitmapOr가 자동). 분기로 나누려면 `UNION`(중복 제거). `UNION ALL`은 두 조건이 상호 배타적일 때만 — 아니면 같은 행이 두 번 나온다 |
| `NOT IN (서브쿼리)` | 서브쿼리에 NULL이 하나라도 있으면 결과가 비어버림(정확성 버그) + 느림 | `NOT EXISTS` |
| `SELECT *` | 불필요한 큰 컬럼(TOAST된 텍스트·JSONB·벡터)까지 읽음, index-only scan 불가 | 필요한 컬럼만 |
| 큰 `IN (...)` 목록(수천 개) | 파싱·계획 비용 | `= ANY($1::bigint[])` 배열 파라미터, 또는 임시 테이블 조인 |
| 대량 DELETE/UPDATE 한 번에 | 긴 트랜잭션, 락, WAL 폭증, 복제 지연 | 1천~1만 행 배치로 나눠 커밋(`migrations.md` 백필) |
| `ORDER BY random() LIMIT n` | 전체 정렬 | `TABLESAMPLE` 또는 ID 범위 샘플링 |
| 루프 안에서 단건 INSERT | 왕복 N번 | 배치 INSERT, `COPY`(대량 적재 시 가장 빠름) |
| 프리페어드 문장이 generic plan으로 바뀐 뒤 느려짐 | 처음 5회는 custom plan, 이후 generic plan의 추정 비용이 custom plan 평균보다 크게 나쁘지 않으면 generic으로 전환 → 값 분포가 편향되면 나쁜 계획이 고정될 수 있음 | `plan_cache_mode = force_custom_plan`(해당 쿼리/역할 한정) |

## 7. 쿼리 작성 규칙

- **항상 파라미터 바인딩.** 문자열 이어붙이기로 SQL을 만들지 않는다(SQL injection). 동적 정렬 컬럼은 허용 목록(whitelist)에서 고른다.
- 운영에서 쿼리 무한 대기를 막는다: 앱 역할에 `statement_timeout`(예: API는 수 초~30초, 배치는 별도 역할로 길게)을 건다. 기본값 0은 "무제한"이다.
- ORM이 만든 SQL을 신뢰하지 말고, 핫패스 쿼리는 로그에서 실제 SQL을 한 번 본다.
