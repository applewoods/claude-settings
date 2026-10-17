# 보안·개인정보

> 언제 읽나: DB 역할·권한을 만들 때, 다중 테넌트 격리를 설계할 때, 개인정보·민감정보 컬럼을 추가할 때, 보존 기간·파기·탈퇴 처리를 설계할 때.
> 로그인·세션·비밀번호 해시 알고리즘·API 권한 검사는 `backend` 스킬 소관이다. 여기서는 DB 계층만 다룬다.

## 1. 역할과 최소 권한

**앱이 superuser나 테이블 소유자로 접속하지 않는다.** Docker 이미지의 `POSTGRES_USER`는 superuser다 — 그대로 앱에 쓰는 게 가장 흔한 실수다.

| 역할 | 권한 | 용도 |
|---|---|---|
| `app_owner` | 스키마·테이블 소유(`NOLOGIN` 권장, 마이그레이션 시 `SET ROLE`) | 마이그레이션 |
| `app_rw` | 필요한 테이블에 `SELECT, INSERT, UPDATE, DELETE`, 시퀀스 `USAGE` | 앱 런타임 |
| `app_ro` | `SELECT` | 리포트·분석·읽기 전용 도구 |
| (superuser) | 전부 | 사람이 비상시에만 |

```sql
CREATE ROLE app_rw LOGIN PASSWORD '...';   -- 비밀번호는 .env/secret으로, 코드·마이그레이션 파일에 넣지 않는다
GRANT USAGE ON SCHEMA public TO app_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;   -- 이후 생성 테이블에도 적용
REVOKE CREATE ON SCHEMA public FROM PUBLIC;   -- PG15+는 기본으로 제거됨. 이전 버전에서 업그레이드한 DB는 확인
```
- 감사 로그 테이블은 `app_rw`에 INSERT만(`schema-design.md` 6절).
- 적용 범위: 연구 데모는 superuser 1개로도 되지만, **실제 사용자 데이터를 받는 순간부터** 역할 분리.
- 인증 방식은 `scram-sha-256`. MD5 비밀번호 인증은 PG18에서 폐지 예정(deprecated)으로 표시됐다.
- DB 포트를 외부에 열지 않는다(`operations.md` 1절). 원격 접속이 필요하면 SSH 터널·VPN.

## 2. RLS(Row Level Security)

다중 테넌트에서 앱 코드의 `WHERE tenant_id = ?` 누락을 DB가 막는 **이중 방어**다.

```sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;   -- 소유자에게도 적용(없으면 테이블 소유자는 RLS를 우회)
CREATE POLICY tenant_isolation ON documents
  USING (tenant_id = current_setting('app.tenant_id')::bigint)
  WITH CHECK (tenant_id = current_setting('app.tenant_id')::bigint);
-- 앱: 요청마다 트랜잭션 시작 직후
SELECT set_config('app.tenant_id', $1, true);   -- true = 트랜잭션 로컬(PgBouncer transaction 모드에서 안전)
```
**함정**
- superuser와 `BYPASSRLS` 역할은 항상 우회한다. 앱 역할은 둘 다 아니어야 한다.
- `current_setting('app.tenant_id')`가 설정 안 됐을 때 에러가 나는 게 안전하다. `current_setting(..., true)`(missing_ok)를 쓰면 NULL → 정책이 거짓이 되어 빈 결과(조용한 실패)가 된다. 어느 쪽인지 의도적으로 고른다.
- 세션 단위 `SET`을 쓰면 커넥션 풀에서 다른 요청이 이전 테넌트 값을 물려받는다 → 반드시 트랜잭션 로컬.
- 정책의 조건 컬럼(`tenant_id`)에 인덱스가 없으면 모든 쿼리가 느려진다. 정책 안에서 함수·서브쿼리를 쓰면 행마다 실행될 수 있다(`STABLE` 함수 + 단순 비교 유지).
- 뷰는 기본적으로 뷰 소유자 권한으로 실행돼 RLS를 우회할 수 있다 → PG15+ `WITH (security_invoker = true)`.
- 테스트: 테넌트 A로 설정하고 B의 행을 SELECT/UPDATE/INSERT 시도 → 실패하는지 자동 테스트로 남긴다.

적용 범위: 단일 사용자·단일 조직 앱에는 불필요. B2B 다중 테넌트 출시 서비스에서 권장.

## 3. 암호화

| 계층 | 막는 것 | 방법 |
|---|---|---|
| 전송 | 네트워크 도청 | DB가 다른 호스트에 있으면 TLS(`sslmode=verify-full`). 같은 Docker 네트워크 내부는 위험이 낮아 선택 |
| 저장(디스크) | 디스크·백업 파일 탈취 | 호스트 디스크 암호화(LUKS 등), 백업 파일 암호화. PostgreSQL 자체 TDE는 커뮤니티 버전에 없다 |
| **컬럼(앱 계층)** | DB 덤프 유출, 과도한 내부 접근 | 민감 필드를 앱에서 암호화해 저장. 키는 DB 밖(환경변수·secret manager·KMS) |

**컬럼 암호화 판단**
- 대상: 주민등록번호·여권번호 등 고유식별정보, 계좌·카드 정보, 건강 정보 등. 한국 개인정보보호법은 고유식별정보·비밀번호 등에 암호화 의무를 둔다 [확인 필요: 현행 법령·고시의 대상 항목과 알고리즘 기준 — 출시 전 법무/전문가 확인].
- **비밀번호는 암호화가 아니라 단방향 해시**(argon2id/bcrypt 등, 구체 선택은 `backend` 스킬). DB에는 해시 문자열만, 컬럼명 `password_hash`.
- 앱 계층 암호화(AES-GCM 등, 검증된 라이브러리 사용 — 직접 구현 금지)를 기본으로. `pgcrypto`로 DB 안에서 암복호화하면 키가 SQL 문·로그(`log_statement`, `pg_stat_statements`)에 남을 위험이 있다.
- 암호화된 컬럼은 검색·정렬·unique가 안 된다. 정확 일치 검색이 필요하면 **blind index**: `HMAC(별도 키, 정규화된 값)`을 별도 컬럼에 저장하고 거기에 unique/인덱스.
- 키 교체(rotation)를 고려해 암호문에 키 버전을 함께 저장.
- 처음부터 "저장하지 않기"가 최선이다. 주민번호가 정말 필요한가? 생년월일·본인인증 결과(CI 등)로 대체 가능한가?

## 4. 개인정보 최소 수집·보존·파기

**설계 단계 질문**(새 컬럼마다):
1. 이 값이 없으면 기능이 안 되는가? 아니면 수집하지 않는다.
2. 원본이 필요한가, 파생값(나이대, 지역 시·도)이면 충분한가?
3. 언제까지 필요한가? → **보존 기간을 컬럼·테이블 단위로 `docs/database.md`에 적는다.**
4. 누가 볼 수 있어야 하는가? → 역할·마스킹.

**보존·파기 구현**
- 기간이 지난 데이터는 정기 작업(cron/스케줄러)으로 삭제 또는 익명화. 수동 처리에 의존하지 않는다. 한국 법령상 보유기간 경과 후 파기 기한이 정해져 있다 [확인 필요: 현행 기준].
- 탈퇴 처리: 하드 삭제가 기본. 법적 보존 의무(전자상거래 거래기록 등 [확인 필요: 항목별 기간])가 있으면 해당 필드만 별도 테이블로 분리 보관하고 나머지는 삭제. "탈퇴 플래그만 세우고 전부 보관"은 파기 의무 위반 소지가 있다.
- 익명화 vs 가명화: 가명화(ID를 해시로 바꿈)는 여전히 개인정보로 취급될 수 있다. 통계용 보관은 재식별이 불가능하게 집계·일반화.
- 파기 범위에 **복사본도 포함**: 감사 로그, 검색 인덱스·임베딩(청크에 개인정보가 들어간 경우), 캐시, 분석용 덤프, 백업. 백업은 즉시 파기가 어려우므로 백업 보존 기간을 짧게 정하고 문서화한다.
- RAG: 개인정보가 담긴 문서를 임베딩하면 벡터와 청크 원문에 남는다 → 문서 삭제 시 청크·임베딩이 함께 지워지게(FK `ON DELETE CASCADE`).

## 5. 개발·테스트 데이터

- 운영 데이터를 로컬·개발로 복사하지 않는다. 필요하면 가짜 데이터 생성(Faker 등) 또는 마스킹된 추출본.
- 시드·픽스처 파일에 실제 이메일·전화번호 금지(`example.com`, `010-0000-0000` 형식).
- 로그 설정: `log_statement = 'all'`은 파라미터 값(개인정보·비밀번호)까지 남길 수 있다 → 운영은 `ddl` 또는 `none`. 단 **느린 쿼리 로그(`log_min_duration_statement`)와 에러 로그에도 SQL 리터럴과 바인드 값이 남을 수 있다** → `log_parameter_max_length = 0`, `log_parameter_max_length_on_error = 0`으로 값 기록을 끄고, 개인정보를 SQL 리터럴로 넣지 않는다(바인딩). `pg_stat_statements`는 상수를 `$1`로 정규화하지만 로그 파일은 아니다. 로그 파일도 개인정보로 취급해 보존 기간을 정한다.
- 에러 메시지에 SQL 원문·파라미터를 사용자에게 노출하지 않는다(backend 스킬의 에러 처리 규칙과 함께).

## 6. SQL injection (DB 관점)

- 모든 값은 파라미터 바인딩. ORM의 raw SQL(`text()`, `$queryRaw`, `sql`` ``)에서도 템플릿 바인딩을 쓴다. Prisma의 `$queryRawUnsafe`, 문자열 포맷으로 만든 `text(f"...")`는 금지.
- 식별자(테이블·컬럼명·정렬 방향)는 바인딩이 안 되므로 허용 목록에서 고른다.
- 최소 권한(1절)이 injection 피해 범위를 줄인다: 앱 역할이 `DROP`·`TRUNCATE`·다른 스키마 접근을 못 하게.
