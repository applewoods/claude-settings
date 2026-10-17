# 마이그레이션

> 언제 읽나: 마이그레이션 파일을 만들거나 리뷰할 때, 운영 DB에 스키마 변경을 적용할 때, 큰 테이블을 바꿀 때, 배포가 실패해 되돌려야 할 때.
> "운영 DB에 마이그레이션 적용 전 사용자 확인"은 모든 경우에 적용된다.

## 1. 도구별 기본

| 스택 | 도구 | 꼭 알아둘 것 |
|---|---|---|
| Python | Alembic(+SQLAlchemy) | `--autogenerate`는 초안일 뿐이다. **테이블·컬럼 이름 변경을 감지하지 못해 drop + add로 만든다(데이터 소실).** 서버 기본값·enum 값 변경·일부 제약도 놓칠 수 있다 → 생성된 파일을 반드시 읽고 고친다. `CONCURRENTLY`는 `op.get_context().autocommit_block()` 안에서 |
| TS | Drizzle Kit | `drizzle-kit generate`로 SQL 파일을 만들고 리뷰 후 `migrate`. `push`는 마이그레이션 기록 없이 스키마를 맞추므로 **로컬 프로토타입에만** |
| TS | Prisma Migrate | `migrate dev`는 로컬 전용(리셋을 제안할 수 있음), 운영은 `migrate deploy`. 생성 SQL을 직접 고칠 수 있다(`--create-only`). `db push`도 로컬 프로토타입에만 |

- 트랜잭션 DDL: PostgreSQL은 DDL을 트랜잭션 안에서 실행할 수 있어 마이그레이션 중간 실패 시 전체 롤백이 가능하다. **예외**: `CREATE/DROP INDEX CONCURRENTLY`, `ALTER TYPE ... ADD VALUE`(PG12+는 트랜잭션 안에서 가능하나 새 값은 커밋 전에 못 씀), `VACUUM` 등은 트랜잭션 밖에서. Prisma·Drizzle이 마이그레이션 파일을 트랜잭션으로 감싸는지는 도구 버전마다 다르다 [확인 필요: 사용 중인 버전 문서] → `CONCURRENTLY`는 별도 마이그레이션 파일로 분리.
- **마이그레이션은 한 곳에서 한 번만 실행.** 앱 컨테이너가 여러 개일 때 각 컨테이너 시작 시 자동 실행하면 동시 실행 경쟁이 생긴다 → 배포 파이프라인의 별도 단계(일회성 컨테이너/job)로 실행.
- 이미 운영에 적용된 마이그레이션 파일은 **수정하지 않는다.** 새 마이그레이션으로 고친다.
- 스키마 변경과 대량 데이터 변경(백필)은 **다른 마이그레이션/스크립트로 분리**한다.

## 2. 위험도 분류 — 무엇이 테이블을 잠그나

작은 테이블(수만 행 이하)은 대부분 즉시 끝나므로 신경 쓸 필요가 적다. 아래는 **큰 테이블 + 운영 트래픽**일 때의 기준.

| 작업 | 위험 | 안전한 방법 |
|---|---|---|
| `ADD COLUMN` (NULL 허용, 기본값 없음) | 안전(메타데이터만) | — |
| `ADD COLUMN ... DEFAULT 상수` | PG11+ 안전(재작성 없음) | — |
| `ADD COLUMN ... DEFAULT 휘발성 함수`(`gen_random_uuid()`, `clock_timestamp()`) | **테이블 전체 재작성** | 기본값 없이 추가 → 배치 백필 → 이후 DEFAULT 설정 |
| `ALTER COLUMN TYPE` | 대부분 **전체 재작성 + ACCESS EXCLUSIVE** (예외: `varchar(n)`→더 큰 `n`/`text` 같은 binary-compatible 변경) | 새 컬럼 추가 → 이중 쓰기 → 백필 → 읽기 전환 → 옛 컬럼 삭제(expand/contract) |
| `SET NOT NULL` | 전체 스캔 동안 ACCESS EXCLUSIVE | ① `ADD CONSTRAINT c CHECK (col IS NOT NULL) NOT VALID` ② `VALIDATE CONSTRAINT c`(약한 락) ③ `SET NOT NULL`(PG12+는 검증된 CHECK를 보고 스캔 생략) ④ CHECK 삭제 |
| `ADD FOREIGN KEY` | 양쪽 테이블 검사 동안 락 | `NOT VALID`로 추가 → 별도 트랜잭션에서 `VALIDATE CONSTRAINT` |
| `ADD CHECK` | 전체 스캔 | `NOT VALID` → `VALIDATE` |
| `ADD UNIQUE`/PK | 인덱스 생성 동안 쓰기 차단 | `CREATE UNIQUE INDEX CONCURRENTLY` → `ADD CONSTRAINT ... UNIQUE USING INDEX` |
| `CREATE INDEX` | 쓰기 차단 | `CREATE INDEX CONCURRENTLY` |
| `DROP COLUMN` | 메타데이터만(빠름). 단 **코드가 아직 그 컬럼을 쓰면 장애** | 코드에서 먼저 제거 → 배포 확인 → 다음 배포에서 DROP |
| 컬럼/테이블 이름 변경 | 빠름. 단 구버전 코드가 즉시 깨짐 | expand/contract(새 컬럼 + 이중 쓰기) 또는 view로 옛 이름 유지 |
| `VACUUM FULL`, `CLUSTER` | 전체 재작성 + ACCESS EXCLUSIVE | 운영 중에는 금지. 공간 회수가 꼭 필요하면 `pg_repack` 확장 검토 |

**모든 운영 DDL 앞에:**
```sql
SET lock_timeout = '5s';        -- 락을 못 잡으면 기다리지 말고 실패 → 한가할 때 재시도
SET statement_timeout = '0';    -- (CONCURRENTLY·VALIDATE처럼 오래 걸리는 정당한 작업만) 필요시 별도 설정
```
락 대기 중인 DDL 뒤로 모든 쿼리가 줄을 서기 때문에(`transactions.md` 4절), `lock_timeout` 없이 ALTER를 돌리는 게 가장 흔한 운영 장애 원인이다.

## 3. CONCURRENTLY 주의

- 트랜잭션 블록 안에서 못 쓴다.
- 테이블을 두 번 스캔하고 진행 중인 트랜잭션이 끝나길 기다리므로 일반 생성보다 느리다. 긴 트랜잭션이 있으면 계속 기다린다.
- **실패하면 `INVALID` 인덱스가 남는다.** 쓰기 비용은 계속 내면서 조회에는 안 쓰인다. 확인 후 `DROP INDEX CONCURRENTLY` → 재시도:
  ```sql
  SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;
  ```
- unique 인덱스를 CONCURRENTLY로 만들다 중복 데이터 때문에 실패하는 경우가 흔하다 → 사전에 중복 조회.
- 진행률: `pg_stat_progress_create_index`.

## 4. 무중단 변경: expand / contract

구버전 코드와 신버전 코드가 **동시에** 같은 DB를 쓰는 순간이 반드시 있다(롤링 배포, 롤백). 그래서 한 배포에서 "깨는 변경"을 하지 않는다.

예: `users.name`을 `first_name`/`last_name`으로 분리
1. **Expand**(마이그레이션): 새 컬럼 추가(NULL 허용). 구 코드는 영향 없음.
2. **이중 쓰기**(배포 1): 신 코드가 옛 컬럼과 새 컬럼 모두에 쓴다. 읽기는 아직 옛 컬럼.
3. **백필**(스크립트): 기존 행을 배치로 채운다.
4. **읽기 전환**(배포 2): 새 컬럼에서 읽는다. 검증 기간을 둔다.
5. **Contract**(배포 3 + 마이그레이션): 옛 컬럼 쓰기 중단 → 다음 배포에서 DROP, 필요하면 NOT NULL.

적용 범위: 이 단계 전부는 **출시 서비스 + 무중단이 필요할 때**. 연구 데모·사용자 없는 서비스·점검 시간을 공지할 수 있는 서비스는 한 번에 바꾸되(점검 모드에서), 백업과 확인 절차는 그대로 지킨다.

## 5. 대용량 백필

```sql
-- 배치 하나(앱 스크립트에서 반복). 1천~1만 행 단위, 각 배치 별도 트랜잭션으로 커밋.
UPDATE users SET first_name = split_part(name, ' ', 1)
WHERE id IN (
  SELECT id FROM users WHERE first_name IS NULL AND id > $last_id ORDER BY id LIMIT 5000
)
RETURNING id;
```
- 한 트랜잭션에 수백만 행 UPDATE 금지: 긴 락, WAL 폭증(복제 지연·디스크), 죽은 튜플이 VACUUM 전까지 쌓여 테이블 팽창.
- 배치 사이 짧은 대기(수십~수백 ms)로 부하·복제 지연을 조절. 배치 크기는 배치당 1초 안팎이 되도록 조정(경험칙).
- 진행 지점(`last_id`)을 기록해 중단 후 이어서 실행할 수 있게. 재실행해도 결과가 같게(멱등) 작성.
- 끝나면 `ANALYZE 테이블`.

## 6. 롤백 전략

- **down 마이그레이션을 맹신하지 않는다.** 컬럼 DROP의 down은 컬럼을 다시 만들 뿐 데이터는 돌아오지 않는다. 데이터 파괴적 변경의 down은 "되돌림"이 아니다.
- 원칙은 **roll-forward**: 문제가 생기면 이전 코드로 되돌리고(expand 단계는 구 코드와 호환되므로 안전), 스키마는 새 마이그레이션으로 고친다.
- 데이터 파괴적 변경(DROP, 타입 축소, 대량 UPDATE/DELETE) 전에는:
  1. 영향 행 수를 먼저 조회해 사용자에게 보여 준다.
  2. 백업 시점 확인 또는 대상 데이터를 별도 테이블로 복사(`CREATE TABLE backup_x AS SELECT ...`) — 보관 기간과 삭제 시점을 정한다(개인정보 포함 시 특히).
  3. 사용자 확인 후 적용.
- 로컬·CI에서 `upgrade → downgrade → upgrade`를 실제로 돌려 down이 최소한 실행은 되는지 확인한다(완료 기준).

## 7. 운영 적용 절차 (사용자 확인 포함)

1. 마이그레이션 SQL 확인(Alembic `upgrade --sql`, Prisma/Drizzle 생성 SQL)과 위 2절 위험도 분류.
2. 운영과 비슷한 데이터량의 스테이징(또는 운영 백업 복원본)에서 실행 시간 측정 — 출시 서비스일 때.
3. 사용자에게 보고: 무엇이 바뀌는지, 락·소요 예상, 실패 시 대응, 백업 시점. **확인받기.**
4. 적용(트래픽 적은 시간, `lock_timeout` 설정). 진행 중 `pg_stat_activity`로 락 대기 관찰.
5. 적용 후 확인: 마이그레이션 버전 테이블, 새 인덱스 `indisvalid`, 에러 로그, 핵심 쿼리 지연.
6. `docs/database.md` ERD 갱신.
