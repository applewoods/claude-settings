# 운영

> 언제 읽나: Docker로 DB를 처음 띄울 때, 출시 전 백업·복구를 준비할 때, 커넥션 에러·DB 느려짐·디스크 증가를 만났을 때, PostgreSQL 버전을 올릴 때.
> 적용 범위: 1(Docker)과 2의 "최소" 줄은 연구 데모 포함 모든 경우. 나머지는 **출시 서비스일 때**.

## 1. Docker 운영

```yaml
services:
  db:
    image: pgvector/pgvector:pg18      # pgvector 포함 이미지. 운영은 태그를 구체적으로 고정 [확인 필요: 사용 시점의 태그 목록]
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app_owner
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password   # 또는 .env의 POSTGRES_PASSWORD (backend 스킬의 비밀값 규칙)
    volumes:
      - pgdata:/var/lib/postgresql     # PG18+ 이미지: /var/lib/postgresql. PG17 이하: /var/lib/postgresql/data
    shm_size: 256mb                    # 기본 64MB는 병렬 쿼리·큰 정렬에서 부족할 수 있음
    stop_grace_period: 60s             # 정상 종료(체크포인트) 시간 확보. 강제 종료는 복구 과정을 유발
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app_owner -d app"]
    # ports: 운영에서는 열지 않는다. 같은 compose 네트워크의 앱만 접근
volumes:
  pgdata:
```
- **볼륨 경로가 PG18 이미지에서 바뀌었다.** 공식 `postgres` 이미지는 18부터 `PGDATA=/var/lib/postgresql/18/docker`, VOLUME은 `/var/lib/postgresql`. 17 이하 방식(`/var/lib/postgresql/data`)으로 마운트하면 컨테이너를 다시 만들 때 데이터가 사라질 수 있다. 이미지 버전을 바꾸기 전 반드시 확인. pgvector 이미지도 공식 이미지 기반이다 [확인 필요: pgvector 이미지가 같은 경로 규칙을 따르는지].
- `docker-entrypoint-initdb.d` 스크립트와 `POSTGRES_*` 환경변수는 **데이터 디렉터리가 비어 있을 때만** 적용된다. 이미 초기화된 볼륨에서 비밀번호 환경변수를 바꿔도 비밀번호는 안 바뀐다(`ALTER ROLE`로).
- **`docker compose down -v`는 볼륨을 지운다 = 데이터 삭제.** 사용자 확인 없이 실행 금지.
- **메이저 버전 업그레이드는 이미지 태그만 바꾸면 안 된다.** 데이터 파일 형식이 다르다. `pg_dump`/`pg_restore`(작은 DB, 다운타임 허용) 또는 `pg_upgrade`/논리 복제(큰 DB). 마이너 버전(18.x → 18.y)은 태그 교체 + 재시작으로 충분하지만 릴리스 노트의 재색인 안내를 확인.
- `5432`를 `0.0.0.0`으로 공개하면 인터넷 스캐너에 바로 노출된다. 로컬 개발에서 포트를 열 때도 `127.0.0.1:5432:5432`로.
- macOS 로컬은 bind mount보다 named volume이 빠르고 권한 문제가 적다.
- 기본 설정은 작은 기계 기준이다. 운영 시 최소 조정(PostgreSQL 문서의 출발점): `shared_buffers` ≈ RAM의 25%, `effective_cache_size` ≈ 50~75%, `work_mem`은 연결 수 × 동시 정렬 수를 고려해 작게(수 MB~수십 MB). 컨테이너 메모리 제한이 있으면 RAM이 아니라 **제한값** 기준.

## 2. 백업·PITR·복구 리허설

| 수준 | 방법 | 복구 가능 시점 | 언제 |
|---|---|---|---|
| 최소 | `pg_dump -Fc` 정기 실행(cron) + 다른 장소로 복사 | 마지막 덤프 시점(하루 단위 손실 가능) | 연구 데모, 초기 서비스, 수 GB 이하 |
| 권장(출시) | 물리 백업 + WAL 아카이빙: **pgBackRest** 또는 **WAL-G** | 임의 시점(PITR, 초~분 단위) | 실제 사용자 데이터가 있는 서비스 |
| 매니지드 | 클라우드 DB의 자동 백업 | 제공사 기준 | 직접 운영 부담을 줄이고 싶을 때 (단 사용자 결정은 Docker 자체 운영) |

- **복구해 보지 않은 백업은 백업이 아니다.** 출시 서비스는 정기적으로(최소 분기 1회, 경험칙) 백업을 별도 컨테이너에 실제 복원하고, 행 수·최근 데이터·앱 접속을 확인한다. 복구에 걸린 시간을 기록 → 이게 실제 RTO.
- 목표를 먼저 정한다: **RPO**(얼마만큼의 데이터 손실을 감수하나), **RTO**(얼마나 빨리 복구해야 하나). "하루치 손실 괜찮음"이면 pg_dump로 충분, "5분 이내"면 WAL 아카이빙 필수.
- 3-2-1: 사본 3개, 매체 2종, 1개는 다른 장소(같은 서버의 다른 디렉터리는 백업이 아니다). 백업 파일도 개인정보다 → 암호화·접근 제한·보존 기간.
- `pg_dump`는 논리 백업이라 PITR이 안 된다. 대신 버전 간 이동·일부 테이블 복원에 유용하다. 큰 DB는 `-Fd -j N`(디렉터리 형식 병렬).
- 볼륨 디렉터리를 DB 실행 중에 `cp`/`tar`하는 건 일관성 없는 백업이다(파일시스템 스냅샷 + 적절한 절차가 아니면 금지).
- 복제본(replica)은 백업이 아니다. `DELETE` 실수도 즉시 복제된다.

## 3. 커넥션과 PgBouncer

- PostgreSQL 연결 하나 = 서버 프로세스 하나(수 MB 메모리 + 컨텍스트 스위칭). `max_connections` 기본 100. 연결 수를 늘린다고 처리량이 늘지 않고, 일정 수준을 넘으면 오히려 줄어든다.
- 활성 연결 적정치의 출발점: CPU 코어 수 × 2~4 수준(경험칙, HikariCP 문서의 `코어×2 + 디스크 수` 공식이 널리 쓰임). 측정으로 조정.
- **앱 측 풀**: SQLAlchemy `pool_size`/`max_overflow`, Prisma `connection_limit`. 앱 인스턴스 수 × 풀 크기 ≤ DB가 감당할 연결 수. 워커·replica를 늘릴 때 이 곱셈을 잊는 게 흔한 실수(`too many clients already`).
- **PgBouncer가 필요한 때**: 앱 인스턴스·워커가 많아 합계 연결이 수백을 넘을 때, 서버리스/짧은 프로세스가 연결을 자주 열고 닫을 때. 단일 FastAPI 인스턴스 + 앱 풀이면 불필요.
- PgBouncer 모드:
  - `session`(기본): 클라이언트 연결 동안 서버 연결 점유. 안전하지만 연결 절약 효과 적음.
  - `transaction`: 트랜잭션이 끝나면 반납. 연결 절약 효과가 크지만 **세션 기능을 쓰면 안 된다**: 세션 단위 `SET`(→ `SET LOCAL`), 세션 advisory lock(→ xact 버전), `LISTEN`, 세션 임시 테이블, `WITH HOLD` 커서.
  - 프로토콜 수준 prepared statement는 `max_prepared_statements`(기본 200, 0이면 비활성)로 transaction 모드에서도 지원된다. SQL `PREPARE` 문은 추적되지 않는다. 드라이버(asyncpg 등)의 statement cache 설정과 함께 확인 [확인 필요: 사용하는 드라이버·PgBouncer 버전 조합].
  - RLS에서 테넌트 ID를 세션 변수로 넘기면 transaction 모드에서 다른 요청에 새어 나간다 → 트랜잭션 안에서 `set_config('app.tenant_id', $1, true)`(= `SET LOCAL`).
- 마이그레이션·`pg_dump`·`LISTEN`이 필요한 작업은 PgBouncer를 거치지 않고 DB에 직접 연결.

## 4. VACUUM과 autovacuum

MVCC에서 UPDATE/DELETE는 옛 행(dead tuple)을 남긴다. VACUUM이 이를 재사용 가능하게 만들고, 통계(ANALYZE)와 visibility map, 트랜잭션 ID 동결(freeze)을 처리한다.

- **autovacuum은 끄지 않는다.** 꺼서 생기는 팽창·통계 노후화·XID wraparound 위험이 훨씬 크다.
- 기본 트리거: dead tuple이 `50 + 테이블 행 수 × 0.2`(`autovacuum_vacuum_scale_factor` 0.2) 넘으면. 1억 행 테이블이면 2천만 개가 쌓여야 돈다 → **큰·쓰기 많은 테이블은 테이블 단위로 낮춘다**:
  ```sql
  ALTER TABLE events SET (autovacuum_vacuum_scale_factor = 0.02, autovacuum_analyze_scale_factor = 0.01);
  ```
- VACUUM이 효과가 없는 흔한 원인: **오래 열린 트랜잭션**(`idle in transaction` 포함), 방치된 replication slot, 오래된 prepared transaction. 이들이 잡고 있는 시점 이후의 dead tuple은 못 지운다.
- 일반 VACUUM은 공간을 OS에 돌려주지 않고 재사용만 한다. 디스크가 줄지 않는 건 정상이다. `VACUUM FULL`은 테이블을 잠그므로 운영 중 금지(`pg_repack` 검토).
- 대량 적재·대량 삭제 직후에는 수동 `VACUUM (ANALYZE) 테이블`이 도움이 된다.
- XID wraparound: `age(datfrozenxid)`가 `autovacuum_freeze_max_age`(기본 2억)에 다가가면 강제 freeze vacuum이 돌고, 방치해 약 20억에 가까워지면 DB가 쓰기를 거부한다. 모니터링 대상.

## 5. 모니터링 지표 (출시 서비스)

`pg_stat_statements` 확장을 켠다(`shared_preload_libraries` 설정 필요 — Docker는 `command: postgres -c shared_preload_libraries=pg_stat_statements`).

| 지표 | 확인 방법 | 경보 기준(출발점, 서비스에 맞게 조정) |
|---|---|---|
| 느린 쿼리 | `pg_stat_statements` `total_exec_time` 상위, `log_min_duration_statement`(예: 500ms~1s) | 상위 쿼리의 평균 시간 급증 |
| 연결 수 | `pg_stat_activity` count / `max_connections` | 80% 이상 |
| 오래된 트랜잭션 | `now() - xact_start` 최대값 | 수 분 이상(OLTP 기준) |
| 락 대기 | `pg_stat_activity.wait_event_type = 'Lock'` | 지속 발생 |
| 캐시 적중률 | `pg_stat_database` `blks_hit / (blks_hit + blks_read)` | OLTP에서 99% 미만이면 메모리·쿼리 점검(경험칙. 분석성 워크로드는 낮을 수 있음) |
| dead tuple·마지막 autovacuum | `pg_stat_user_tables` `n_dead_tup`, `last_autovacuum` | 큰 테이블에서 오래 안 돎 |
| XID 나이 | `SELECT max(age(datfrozenxid)) FROM pg_database` | 5억 이상 조사, 10억 이상 긴급(경험칙) |
| 디스크 | 볼륨 사용률, WAL 디렉터리 크기 | 80% 이상. 방치된 replication slot이 WAL을 무한히 쌓는 경우 확인 |
| 백업 | 마지막 성공 시각, WAL 아카이브 실패 | 주기 초과 시 즉시 |
| 복제 지연(복제 시) | `pg_stat_replication` | 서비스 허용치 초과 |

Docker 환경에서는 `postgres_exporter` + Prometheus/Grafana가 흔한 조합. 소규모는 위 쿼리를 주기적으로 돌리는 스크립트로 시작해도 된다.

## 6. 장애 시 첫 5분

1. `pg_stat_activity`로 실행 중·대기 중 쿼리, 막고 있는 PID 확인(`transactions.md` 4절 쿼리).
2. 디스크 여유 확인(가득 차면 PostgreSQL은 쓰기 불가 상태로 멈춘다). WAL을 지우는 수작업은 금지 — 복구 불가 손상의 원인.
3. 서버 로그 확인(`docker compose logs db`).
4. 세션 종료·재시작·설정 변경 같은 조치는 사용자에게 상황과 영향을 보고하고 확인 후.
