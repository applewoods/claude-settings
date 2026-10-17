# 트랜잭션과 동시성

> 언제 읽나: 돈·재고·좌석·포인트처럼 동시 요청에서 값이 틀리면 안 되는 기능, 작업 큐, 데드락·락 대기·serialization 에러를 만났을 때.

## 1. 트랜잭션 원칙

- **짧게.** 트랜잭션 안에서 외부 API 호출, 파일 업로드, LLM 호출, 사용자 입력 대기를 하지 않는다. 그동안 락을 쥐고, `idle in transaction` 상태로 VACUUM이 오래된 행을 못 치운다.
- 운영 안전장치(출시 서비스일 때): 앱 역할에 `idle_in_transaction_session_timeout`(예: 30s~수 분)과 `statement_timeout`. 둘 다 기본값 0(무제한).
- 하나의 비즈니스 동작(주문 생성 + 재고 차감 + 결제 기록)은 한 트랜잭션. 중간 실패 시 전부 롤백되는지 테스트한다.
- ORM 세션 범위 = 요청 하나. 요청 간에 세션·트랜잭션을 공유하지 않는다.
- 외부 시스템과 DB를 함께 바꿔야 하면(결제 API + DB) 분산 트랜잭션이 아니라 **멱등성 키 + 상태 머신 + 재시도**로 설계한다. "DB 커밋 후 메시지 발행"이 둘 다 성공해야 하면 outbox 패턴(같은 트랜잭션에 outbox 테이블 INSERT → 별도 워커가 발행).

## 2. 격리 수준 (PostgreSQL 기준)

| 수준 | PostgreSQL에서의 실제 동작 | 언제 |
|---|---|---|
| READ UNCOMMITTED | READ COMMITTED와 동일하게 동작(dirty read 없음) | 쓰지 않는다 |
| **READ COMMITTED**(기본) | 각 **문장**이 시작 시점 스냅샷을 본다. 같은 트랜잭션에서 두 번 읽으면 값이 다를 수 있다 | 대부분. 원자적 UPDATE·제약·명시적 락과 함께 |
| REPEATABLE READ | 트랜잭션 전체가 첫 쿼리 시점 스냅샷(snapshot isolation). 동시에 같은 행을 수정하면 나중 쪽이 `40001 serialization_failure` | 일관된 리포트·내보내기(여러 쿼리가 같은 시점을 봐야 할 때) |
| SERIALIZABLE | SSI: 직렬 실행과 같은 결과를 보장, 위반 가능성이 보이면 `40001`로 중단 | 규칙이 여러 행에 걸친 불변식(예: "당직자는 최소 1명")이고 락으로 표현하기 어려울 때 |

- REPEATABLE READ·SERIALIZABLE을 쓰면 **재시도 루프가 필수**다(SQLSTATE `40001`, 데드락 `40P01` 포함). 재시도는 트랜잭션 전체를 처음부터, 횟수 제한(3~5회)·지터 있는 백오프.
- 격리 수준을 올리는 것보다 아래 3의 패턴이 대개 더 단순하고 빠르다.

## 3. 동시성 패턴 — 무엇을 고를까

**잃어버린 갱신(lost update)**: 두 요청이 같은 값을 읽고(`stock=10`) 각자 계산해 쓰면(`9`) 하나가 사라진다. READ COMMITTED에서 앱이 읽고-계산하고-쓰면 반드시 생긴다.

| 상황 | 패턴 |
|---|---|
| 카운터·재고 증감 | **원자적 UPDATE**: `UPDATE items SET stock = stock - 1 WHERE id = $1 AND stock > 0 RETURNING stock;` 영향 행 0이면 품절. 가장 단순하고 빠르다 |
| 없으면 생성, 있으면 갱신 | `INSERT ... ON CONFLICT (key) DO UPDATE/DO NOTHING` (unique 제약 필요) |
| 사용자가 폼을 오래 열어 두고 편집(충돌 드묾) | **낙관적 동시성**: `version int` 컬럼. `UPDATE ... SET ..., version = version + 1 WHERE id = $1 AND version = $2` → 영향 행 0이면 "다른 사람이 먼저 수정" 응답(409). 락을 안 잡는다 |
| 읽은 값으로 복잡한 판단 후 갱신, 충돌 잦음(좌석 배정, 잔액 이체) | **비관적 락**: 트랜잭션 안에서 `SELECT ... FOR UPDATE`로 행을 잠그고 판단·갱신 후 커밋. 짧게 유지 |
| 작업 큐(여러 워커가 다음 작업을 가져감) | `SELECT ... FOR UPDATE SKIP LOCKED LIMIT n` — 다른 워커가 잡은 행은 건너뜀. 소규모 큐는 별도 브로커 없이 이걸로 충분 |
| 행이 아닌 "논리적 자원" 직렬화(사용자별 정산 1개만 동시 실행) | advisory lock: `pg_advisory_xact_lock(hashtext('settle:' || user_id))`. PgBouncer transaction 모드에서는 **xact 버전만** 쓴다(세션 버전은 다른 클라이언트에 새어 나감) |
| 같은 요청 재전송(결제 버튼 두 번, 네트워크 재시도) | **멱등성 키**: 클라이언트가 보낸 키에 unique 제약, 이미 있으면 저장된 결과 반환 |

`FOR UPDATE` 변형: 키가 아닌 컬럼만 바꿀 거라면 `FOR NO KEY UPDATE` — 자식 INSERT의 FK 검사(`FOR KEY SHARE`)와 충돌하지 않아 경합이 적다(즉 자식 삽입을 **막지 않는다**; 막아야 하면 `FOR UPDATE`). 잠금 대기를 원치 않으면 `NOWAIT`(즉시 에러).

## 4. 락 이해 — 운영에서 문제를 일으키는 것들

- 일반 SELECT는 행을 잠그지 않는다(MVCC: 읽기는 쓰기를, 쓰기는 읽기를 막지 않음).
- UPDATE/DELETE/`FOR UPDATE`는 행 락. 같은 행을 바꾸려는 다른 트랜잭션만 기다린다.
- **DDL이 진짜 위험하다.** `ALTER TABLE` 대부분은 `ACCESS EXCLUSIVE` 락 = 그 테이블의 SELECT까지 전부 막는다. 게다가 **DDL이 락을 기다리는 동안 그 뒤에 오는 모든 쿼리가 줄을 선다**(락 큐). 긴 트랜잭션 하나 + ALTER 하나 = 서비스 전체 정지. → 마이그레이션에 `SET lock_timeout = '5s'`(`migrations.md`).
- 일반 `CREATE INDEX`는 `SHARE` 락으로 쓰기를 막는다 → 운영에서는 `CONCURRENTLY`.
- FK가 있는 자식 INSERT/UPDATE는 부모 행에 `FOR KEY SHARE` 락을 건다. 인기 있는 부모 행(예: 하나의 `tenant`)에 쓰기가 몰리면 경합이 생길 수 있다.

락 대기 확인:
```sql
SELECT pid, state, wait_event_type, now() - xact_start AS xact_age,
       pg_blocking_pids(pid) AS blocked_by, left(query, 80)
FROM pg_stat_activity WHERE datname = current_database() ORDER BY xact_age DESC NULLS LAST;
```
막고 있는 세션을 끊는 것(`pg_cancel_backend` → 안 되면 `pg_terminate_backend`)은 운영 조치다 → 사용자 확인.

## 5. 데드락

두 트랜잭션이 서로 상대가 잡은 락을 기다리면 PostgreSQL이 `deadlock_timeout`(기본 1s) 후 감지해 하나를 `40P01`로 중단시킨다. 데이터는 안전하지만 요청이 실패한다.

예방:
- **같은 순서로 잠근다.** 여러 행을 갱신할 때 항상 PK 오름차순(`ORDER BY id FOR UPDATE`). 계좌 이체는 작은 ID 먼저.
- 트랜잭션을 짧게, 잠그는 행을 적게.
- 대량 갱신은 배치로 나누고 배치 내부도 정렬.
- 그래도 생길 수 있으므로 `40P01`을 재시도 대상에 넣는다.
- 원인 분석: 서버 로그에 데드락 상세(관련 쿼리)가 남는다. `log_lock_waits = on`이면 `deadlock_timeout`보다 오래 기다린 락도 기록된다.

## 6. ORM 주의점

- SQLAlchemy: `with session.begin():` 블록으로 경계를 명확히. `expire_on_commit` 기본 True라 커밋 후 속성 접근 시 재조회가 일어난다(비동기에선 에러) — 응답 직렬화 전에 필요한 값을 읽거나 False로.
- SQLAlchemy `with_for_update()`, Prisma는 `FOR UPDATE`를 직접 지원하지 않아 `$queryRaw` 또는 interactive transaction + raw SQL [확인 필요: 사용하는 Prisma 버전], Drizzle은 `.for('update')`.
- Prisma interactive transaction은 기본 타임아웃이 있다(수 초) [확인 필요: 현재 기본값] — 긴 작업을 넣지 않는다.
