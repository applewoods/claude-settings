# 스키마 설계

> 언제 읽나: 새 테이블을 만들 때, 키·타입·제약조건을 고를 때, 소프트 삭제·감사 로그·다중 테넌트·JSONB를 고민할 때.
> 기준 버전: PostgreSQL 18(2025-09 출시, 문서 18.x). 버전 표기가 없는 내용은 PG 13+ 공통.

## 1. 정규화와 의도적 비정규화

**기본은 3정규형.** 같은 사실이 두 곳에 있으면 언젠가 어긋난다. 비정규화는 "측정한 병목"이 있을 때만 하고, 그때도 원본이 어디인지(source of truth)를 문서에 적는다.

| 상황 | 판단 |
|---|---|
| 목록 화면에 `comment_count`를 매번 `COUNT(*)` | 행이 수만 건 이하면 그냥 COUNT + 인덱스. 느린 게 측정되면 카운터 컬럼 + 같은 트랜잭션에서 갱신(`SET n = n + 1`) |
| 주문 당시 가격·주소 | **비정규화가 정답.** 이건 중복이 아니라 "그 시점의 사실"(스냅샷)이다. `orders.shipping_address`처럼 복사해 둔다 |
| 리포트·대시보드 집계 | 원본 테이블에 컬럼을 추가하지 말고 materialized view(`REFRESH MATERIALIZED VIEW CONCURRENTLY`는 unique index 필요) 또는 별도 집계 테이블 |
| 검색용 파생값(소문자 이메일, tsvector) | generated column. PG18부터 기본이 VIRTUAL(조회 시 계산). 검색용이면 `STORED`로 명시하거나 원본 식에 표현식 인덱스를 건다(virtual 컬럼 자체에는 인덱스를 못 거는 것으로 알려짐 [확인 필요: PG18 CREATE INDEX 문서]) |

흔한 실수: "조인이 느리다"는 추측으로 처음부터 비정규화. 조인 키에 인덱스가 있고 결과 행이 적으면 큰 테이블 조인도 대개 충분히 빠르다. 웹 서비스에서 느린 쿼리의 흔한 원인은 조인 자체보다 인덱스 누락·N+1이다(경험칙 — `EXPLAIN`으로 확인, `indexing-and-queries.md`).

## 2. 키 전략: bigint identity vs UUID

| | `bigint GENERATED ALWAYS AS IDENTITY` | UUID v7 (`uuidv7()`, PG18+) | UUID v4 (`gen_random_uuid()`) |
|---|---|---|---|
| 크기 | 8바이트 | 16바이트 | 16바이트 |
| B-tree 삽입 지역성 | 순차 → 좋음 | 시간순 → 좋음 | 무작위 → 페이지 분할·캐시 미스·WAL 증가 |
| 외부 노출 | ID 추측·건수 노출(`/users/1024`) | 추측 어려움. 단 생성 시각이 드러남(`uuid_extract_timestamp`) | 추측 어려움, 정보 없음 |
| 클라이언트·오프라인 생성, DB 병합 | 불가 | 가능 | 가능 |

**결정 기준**
- 내부 테이블, 연구 데모, 외부에 ID가 안 보이는 경우 → **bigint identity**. 가장 작고 빠르다.
- URL·API에 ID가 노출되는 출시 서비스, 클라이언트가 ID를 먼저 만들어야 하는 경우, 여러 DB를 합칠 수 있는 경우 → **UUID v7**.
- 생성 시각이 노출되면 안 되는 ID(예: 가입 시점이 민감한 경우) → UUID v4, 또는 내부 bigint PK + 외부용 무작위 `public_id`(unique) 이중 키.
- PG17 이하라면 `uuidv7()`이 없다. 앱에서 v7을 생성(Python `uuid6`/`uuid-utils` 패키지, JS `uuidv7` 패키지)하거나 PG 확장을 쓴다 [확인 필요: 사용하는 라이브러리 버전에서 v7 지원].
- `serial`은 쓰지 않는다. identity가 표준이고 권한·시퀀스 소유 문제가 적다.
- 자연키(이메일, 사업자번호)를 PK로 쓰지 않는다. 바뀔 수 있고 FK로 퍼진다. 대신 `UNIQUE` 제약을 건다.

## 3. 타입 선택 — 흔한 실수 위주

- **시각은 항상 `timestamptz`.** `timestamp`(without time zone)는 서버·세션 타임존이 바뀌면 의미가 깨진다. 저장은 UTC 기준, 표시는 앱에서.
- **문자열은 `text` + 필요하면 `CHECK (char_length(x) <= n)`.** PostgreSQL에서 `varchar(n)`과 `text`는 성능이 같다. 길이 제한을 바꿀 때 CHECK가 더 다루기 쉽다.
- **돈은 `numeric(p,s)` 또는 최소 단위 정수(원, 센트를 `bigint`).** `float`/`real`/`money` 금지(반올림 오차, 로케일 의존).
- **이메일 대소문자 무시 유일성**: `CREATE UNIQUE INDEX ... ON users (lower(email))` 표현식 유니크 인덱스(테이블 제약 `UNIQUE (...)`에는 식을 못 쓴다). `citext` 확장도 되지만 확장 의존이 늘어난다.
- **상태값**: 
  - 값이 거의 안 바뀜 → `text + CHECK (status IN (...))`. 값 추가 시 제약만 교체.
  - PG `ENUM`은 값 추가(`ALTER TYPE ... ADD VALUE`)는 쉽지만 **삭제·이름 변경·순서 변경이 어렵다.** 바뀔 가능성이 있으면 피한다.
  - 값마다 설명·정렬순서·활성 여부 같은 속성이 붙음 → 참조 테이블 + FK.
- **불리언 여러 개로 상태 표현 금지**(`is_paid`, `is_shipped`, `is_cancelled` 동시 true 가능). 상태 컬럼 하나로.
- **배열 컬럼**은 "항상 통째로 읽고 쓰는 작은 목록"(태그 몇 개)에만. 개별 원소로 조인·FK·통계가 필요하면 연결 테이블.

## 4. 제약조건 — DB가 마지막 방어선

앱 검증은 우회된다(스크립트, 관리자 SQL, 버그, 동시 요청). **무결성은 DB 제약으로 강제한다.**

- `NOT NULL`을 기본으로, NULL 허용은 "모른다/해당 없음"이 실제 의미일 때만.
- `UNIQUE`는 앱의 "중복 확인 후 삽입"을 대체한다. 앱에서 SELECT로 확인 후 INSERT하면 동시 요청에서 중복이 생긴다(race condition). 제약을 걸고 `ON CONFLICT` 또는 unique violation(SQLSTATE `23505`)을 잡아 처리한다.
- `FOREIGN KEY`는 기본으로 건다. 빼는 건 측정된 쓰기 병목이 있을 때만. **PostgreSQL은 FK 컬럼에 인덱스를 자동으로 만들지 않는다** → 자식 쪽 FK 컬럼에 인덱스를 직접 만든다(부모 삭제·조인 시 풀스캔 방지).
- `ON DELETE` 선택:
  - `RESTRICT`/`NO ACTION`(기본): 기본값으로 둔다. 실수로 대량 삭제되는 것을 막는다.
  - `CASCADE`: 자식이 부모 없이는 의미가 없는 "구성 요소"일 때만(주문 → 주문항목). 사용자 → 결제 기록 같은 곳에 걸면 사용자 삭제가 회계 기록까지 지운다.
  - `SET NULL`: 관계가 선택적일 때(담당자 퇴사 → 담당자 비움).
- `CHECK`: 범위(`price >= 0`), 상호 조건(`ends_at > starts_at`), 상태별 필수값(`status <> 'shipped' OR shipped_at IS NOT NULL`).
- 겹치면 안 되는 기간(예약): `EXCLUDE USING gist (room_id WITH =, during WITH &&)` (`btree_gist` 확장 필요). PG18은 `PRIMARY KEY/UNIQUE ... WITHOUT OVERLAPS` 시간적(temporal) 제약도 지원한다.
- 운영 중인 큰 테이블에 제약을 추가할 때는 `NOT VALID` → `VALIDATE` 2단계(`migrations.md`).

## 5. 공통 컬럼

- 모든 테이블: PK, `created_at timestamptz NOT NULL DEFAULT now()`, `updated_at timestamptz NOT NULL DEFAULT now()`.
- `updated_at`은 DEFAULT만으로는 UPDATE 시 안 바뀐다. 트리거(`BEFORE UPDATE`)나 ORM 훅(SQLAlchemy `onupdate`, Prisma `@updatedAt`) 중 하나로 통일한다. ORM 훅은 ORM 밖 SQL에서 안 걸린다 → 데이터 정합성이 중요하면 트리거.
- 단순 연결 테이블(N:M)은 복합 PK `(a_id, b_id)`로 충분하다. 역방향 조회가 있으면 `(b_id)` 인덱스 추가.

## 6. 소프트 삭제와 감사 로그

**소프트 삭제(`deleted_at`)는 기본값이 아니다.** 비용이 크다: 모든 쿼리에 `WHERE deleted_at IS NULL`을 빠뜨리는 버그, unique 제약 충돌, FK가 "삭제된" 행을 계속 가리킴, 개인정보 파기 의무와 충돌.

| 필요 | 방법 |
|---|---|
| 사용자가 "휴지통에서 복구" | 소프트 삭제 + `UNIQUE ... WHERE deleted_at IS NULL` 부분 유니크 인덱스 + 활성 행만 보는 view 또는 ORM 기본 필터 |
| "누가 언제 무엇을 바꿨나" 추적 | 소프트 삭제가 아니라 **감사 로그 테이블** |
| 법적 보존 + 개인정보 파기 | 원본은 지우고, 보존 대상 필드만 분리 테이블로(`security-privacy.md`) |
| 그 외 | 그냥 하드 삭제 |

감사 로그 설계:
- 단순: `audit_log(id, table_name, row_id, action, actor_id, changed_at, old jsonb, new jsonb)`를 트리거로 기록. PG18의 `RETURNING OLD/NEW`로 앱에서 기록하는 방법도 있다.
- 감사 로그는 **append-only**: 앱 역할에 INSERT만 주고 UPDATE/DELETE 권한을 주지 않는다.
- 감사 로그에도 개인정보가 들어간다 → 보존 기간·마스킹 대상에 포함.
- 출시 서비스일 때만: 쌓이는 양이 크면 월별 파티션으로 나눠 오래된 파티션을 `DETACH`/`DROP`.

## 7. 다중 테넌트(B2B·조직 단위 서비스)

| 방식 | 언제 | 주의 |
|---|---|---|
| **공유 테이블 + `tenant_id` 컬럼** | 기본값. 테넌트 수가 많고 스키마가 같을 때 | 모든 쿼리에 tenant 조건 누락 = 데이터 유출. RLS로 이중 방어(`security-privacy.md`). 인덱스·unique는 `tenant_id`를 **맨 앞**에: `UNIQUE (tenant_id, email)` |
| 스키마 분리(tenant별 schema) | 테넌트 수십 개 이하, 테넌트별 커스터마이즈가 필요할 때 | 마이그레이션을 N번 실행, 수천 개면 카탈로그·도구가 버거움 |
| DB 분리 | 규제·계약상 분리 요구, 대형 고객 소수 | 운영 비용 최고. 연결 풀도 테넌트 수만큼. **같은 인스턴스의 DB·스키마 분리는 논리 분리일 뿐**이다 — 물리 격리(별도 인스턴스·호스트·저장소)가 요구되면 인스턴스 분리 |

- 자식 테이블에도 `tenant_id`를 중복 저장하고 FK를 `(tenant_id, parent_id)` 복합으로 걸면 다른 테넌트 부모를 가리키는 행을 DB가 막는다.
- 연구 데모·단일 사용자 앱에는 테넌트 개념을 넣지 않는다(과설계).

## 8. JSONB를 쓸 때와 말 때

**쓴다**
- 외부 API 응답 원문, 웹훅 페이로드 보관(조회는 드묾).
- 사용자 정의 필드·설정처럼 키가 행마다 다르고 조건 검색이 드문 데이터.
- 실험 메타데이터(하이퍼파라미터 등)처럼 스키마가 자주 바뀌는 연구용 데이터.

**쓰지 않는다**
- 모든 행에 같은 키가 있다 → 그건 컬럼이다.
- FK·unique·NOT NULL이 필요한 값 → JSONB 안에서는 제약을 걸기 어렵다.
- 자주 WHERE·JOIN·ORDER BY하는 값 → 컬럼으로 승격(통계가 없어 계획이 틀어진다. JSONB 내부 값에는 컬럼 통계가 없어 선택도를 기본값으로 추정).
- 부분 갱신이 잦은 큰 문서 → JSONB는 한 키만 바꿔도 행 전체를 새로 쓴다(MVCC). 큰 문서면 TOAST까지 다시 쓴다.

인덱스: 포함 검색(`@>`)은 `GIN (col jsonb_path_ops)`(작고 빠름, `@>`류만 지원), 키 존재(`?`)까지 필요하면 기본 `jsonb_ops`. 특정 키 하나만 자주 찾으면 표현식 B-tree `((col->>'key'))`가 더 작다.
`json`이 아니라 `jsonb`를 쓴다(`json`은 원문 그대로 저장, 인덱스·연산이 약함). 키 순서·중복 키 보존이 필요할 때만 `json`.

## 9. 대용량·시계열 판단 (출시 서비스일 때만)

- 파티셔닝은 크기보다 **데이터 수명주기**로 판단한다: "오래된 데이터를 기간 단위로 지운다/보관한다"면 시간 범위 파티션이 이득(DELETE 대신 파티션 DROP). 단순히 행이 많다는 이유만으로는 인덱스가 먼저다.
- 파티션 키가 쿼리 WHERE에 없으면 모든 파티션을 뒤진다. PK·unique에 파티션 키가 포함돼야 한다.
- 파일·이미지·큰 바이너리는 DB에 넣지 않는다(`bytea` 수 MB 이상 → 객체 스토리지 + DB에는 경로·해시·크기).
