# pgvector (벡터 검색·RAG)

> 언제 읽나: 임베딩 테이블을 설계할 때, 벡터 인덱스를 만들거나 튜닝할 때, 필터와 벡터 검색을 함께 쓸 때, 임베딩 모델을 바꿀 때.
> 기준: pgvector 0.8.x(README 확인 시점 0.8.7). 0.8.0 미만이면 iterative scan이 없다 → `SELECT extversion FROM pg_extension WHERE extname = 'vector';`로 먼저 확인.

## 1. 저장 설계

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, tenant_id bigint NOT NULL,
                        title text NOT NULL, source_uri text, created_at timestamptz NOT NULL DEFAULT now(),
                        UNIQUE (tenant_id, id));   -- 자식의 복합 FK 대상

CREATE TABLE chunks (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  document_id bigint NOT NULL,
  tenant_id   bigint NOT NULL,             -- 필터용 중복 저장(조인 없이 거르기)
  chunk_index int    NOT NULL,
  content     text   NOT NULL,
  content_hash text  NOT NULL,             -- 같은 내용 재임베딩 방지
  embedding_model text NOT NULL,           -- 예: 'text-embedding-3-small'
  embedding   vector(1536) NOT NULL,
  UNIQUE (document_id, chunk_index),
  -- 복합 FK: 청크의 tenant_id가 부모 문서의 tenant_id와 다르면 DB가 거부한다
  FOREIGN KEY (tenant_id, document_id) REFERENCES documents (tenant_id, id) ON DELETE CASCADE
);
-- 위 예시는 "청크당 임베딩 1개(모델 1개)" 구조다. 모델 교체·비교가 잦으면 아래 별도 테이블 구조를 쓴다.
```
**판단 기준**
- **모델 이름을 행마다 저장한다.** 모델이 다른 벡터끼리 비교하면 결과가 무의미한데 에러는 안 난다. 모델 교체 시 어떤 행이 옛 모델인지 알아야 한다.
- 차원은 컬럼 타입에 고정(`vector(1536)`). 차원 미지정 `vector` 컬럼에는 인덱스를 직접 만들 수 없다(고정 차원으로 캐스트한 표현식 인덱스는 가능).
- 모델을 자주 바꾸거나 여러 모델을 동시에 비교(연구)한다면 임베딩을 별도 테이블로: `chunk_embeddings(chunk_id, model, embedding, PRIMARY KEY (chunk_id, model))`, 모델별 부분 인덱스(차원이 다르면 모델별 테이블 또는 차원 미지정 컬럼 + 모델별 표현식 인덱스 [확인 필요]).
- 벡터는 크다(1536차원 float4 ≈ 6KB/행). `SELECT *`로 목록을 가져오지 않는다. 원문·메타데이터 조회와 벡터 검색 쿼리를 분리.
- 청크 원문과 출처(문서 ID, 페이지, 위치)를 함께 저장해야 답변 근거를 보여 줄 수 있다.
- 원문 문서가 바뀌면 `content_hash`로 바뀐 청크만 재임베딩.

## 2. 타입과 차원 한계

| 타입 | 저장 | 인덱스 가능 차원(HNSW/IVFFlat) | 언제 |
|---|---|---|---|
| `vector` | float4 | 2,000 | 기본 |
| `halfvec` | float2(절반 크기) | 4,000 | 2,000차원 초과 모델(예: 3072차원), 메모리 절약 |
| `bit` | 1bit | 64,000 | 이진 양자화(재정렬과 함께) |
| `sparsevec` | 희소 | HNSW만, 0이 아닌 원소 1,000개 | 희소 임베딩(SPLADE 등) |

- 3072차원 모델: 저장은 `vector(3072)`로 하고 인덱스는 표현식으로 `halfvec`에 걸 수 있다:
  ```sql
  CREATE INDEX ON chunks USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops);
  -- 쿼리도 같은 식이어야 인덱스를 쓴다: ORDER BY embedding::halfvec(3072) <=> $1::halfvec(3072)
  ```
  또는 모델이 지원하면 차원 축소 옵션(예: OpenAI `dimensions` 파라미터)으로 1536 이하를 받는 게 더 단순하다 [확인 필요: 사용하는 모델의 차원 축소 지원·품질 영향].

## 3. 거리 함수

| 연산자 | 거리 | 인덱스 opclass | 언제 |
|---|---|---|---|
| `<=>` | 코사인 거리 | `vector_cosine_ops` | 기본 선택. 대부분 텍스트 임베딩 모델이 코사인 기준 |
| `<#>` | **음의** 내적 | `vector_ip_ops` | 벡터가 길이 1로 정규화돼 있으면 코사인과 순위가 같고 더 빠름(README 권장) |
| `<->` | L2(유클리드) | `vector_l2_ops` | 모델이 L2 기준으로 학습된 경우, 이미지 특징 등 |
| `<+>` | L1 | `vector_l1_ops` | 드묾 |
| `<~>`, `<%>` | 해밍, 자카드 | `bit_hamming_ops`, `bit_jaccard_ops` | bit 벡터 |

흔한 실수
- **인덱스 opclass와 쿼리 연산자가 다르면 인덱스를 안 쓴다**(`vector_cosine_ops`로 만들고 `<->`로 검색 → 전체 스캔).
- `<#>`는 음수를 돌려준다: 유사도로 보여 줄 때 `-(a <#> b)`, 코사인 유사도는 `1 - (a <=> b)`.
- 모델 문서에서 권장 거리와 정규화 여부를 확인한다 [확인 필요: 모델별].

## 4. 인덱스 선택: 없음 vs HNSW vs IVFFlat

| | 인덱스 없음(정확 검색) | **HNSW** | IVFFlat |
|---|---|---|---|
| 결과 | 정확(recall 100%) | 근사 | 근사 |
| 속도-재현율 | 행 수에 비례해 느려짐 | 가장 좋음 | HNSW보다 낮음 |
| 빌드 | — | 느림, 메모리 많음 | 빠름, 메모리 적음 |
| 빈 테이블에 생성 | — | 가능(학습 단계 없음) | **데이터를 넣은 뒤** 만들어야 함(lists 학습) |
| 데이터 변화 | — | 삽입에 강함 | 분포가 바뀌면 재생성 필요 |

**결정 기준**
- 벡터가 수만 개 이하이거나, 필터 후 후보가 적거나, 정확한 결과가 필요한 연구 평가 → **인덱스 없이** 시작하고 지연을 측정한다(정확 검색이 충분히 빠른 경우가 많다. 기준 수치는 하드웨어·차원에 따라 다르므로 측정).
- 기본 추천 → **HNSW**. 데이터가 계속 추가되는 서비스, 높은 재현율이 필요할 때.
- 빌드 시간·메모리가 제약이고 데이터가 한 번에 적재되는 정적 코퍼스 → IVFFlat.

**HNSW 파라미터**(기본값: `m`=16, `ef_construction`=64, 검색 시 `hnsw.ef_search`=40)
- 먼저 기본값으로 만들고 **재현율을 측정한 뒤** 조정한다.
- 재현율 부족 → 먼저 `SET hnsw.ef_search = 100`(쿼리 시점, 재빌드 불필요). 그래도 부족하면 `m`·`ef_construction`을 올려 재빌드(빌드 시간·크기 증가).
- `ef_search`는 반환 가능한 최대 후보 수이기도 하다: `LIMIT 100`인데 `ef_search=40`이면 최대 40개만 나올 수 있다 → `ef_search ≥ LIMIT`.
- 트랜잭션 단위로만 바꾸려면 `SET LOCAL hnsw.ef_search = ...`(PgBouncer transaction 모드에서도 안전).

**IVFFlat 파라미터**: `lists`는 100만 행까지 `행 수 / 1000`, 그 이상은 `sqrt(행 수)`에서 시작. 검색 시 `ivfflat.probes`(기본 1)는 `sqrt(lists)`에서 시작.

**빌드 운영**
- 초기 대량 적재 후 인덱스를 만든다(적재하면서 인덱스 유지보다 훨씬 빠름).
- HNSW 그래프가 `maintenance_work_mem`에 들어가면 훨씬 빠르다(넘으면 NOTICE 출력). 세션 단위로 올리되 서버 메모리를 고갈시키지 않게. 병렬 빌드는 `max_parallel_maintenance_workers`(기본 2).
- 운영 테이블에는 `CREATE INDEX CONCURRENTLY`(`migrations.md` 3절).
- HNSW 인덱스가 있는 테이블의 VACUUM은 느릴 수 있다. README는 `REINDEX INDEX CONCURRENTLY` 후 VACUUM을 제시한다.

## 5. 재현율 측정 — 튜닝의 근거

근사 인덱스는 조용히 결과를 빠뜨린다. "검색이 잘 된다"는 느낌이 아니라 숫자로 본다.
```sql
-- 샘플 쿼리 50~100개에 대해: 정확 결과(인덱스 끔)와 근사 결과의 top-k 겹침 비율
BEGIN; SET LOCAL enable_indexscan = off;  -- 정확 검색
SELECT id FROM chunks ORDER BY embedding <=> $1 LIMIT 10;
COMMIT;
-- 같은 쿼리를 인덱스로 실행해 recall@k = |교집합| / |정확 결과 수| (필터로 정확 결과가 k보다 적을 수 있으므로 분모는 k가 아니라 정확 결과 수. 정확 결과 0개인 쿼리는 평가에서 제외하고 따로 센다)
```
목표 재현율은 서비스가 정한다(RAG면 보통 0.9~0.95 이상을 목표로 잡는 경우가 많다 — 경험칙). 연구 논문에서 검색 성능을 보고한다면 근사 인덱스 사용 여부와 파라미터를 함께 적는다.

## 6. 필터 + 벡터 검색

근사 인덱스는 **먼저 후보를 뽑고 나중에 WHERE로 거른다.** 기본 `ef_search=40`에서 조건이 10%만 맞으면 평균 4개만 남는다(README 예시) → "결과가 LIMIT보다 적게 나오는" 대표적 버그.

| 상황 | 방법 |
|---|---|
| 필터가 매우 선택적(전체의 소수, 후보 수천 개 이하) | 필터 컬럼 B-tree 인덱스 + **정확 검색**. 플래너가 필터 인덱스를 고르게 두면 결과가 정확하다 |
| 필터 값 종류가 적음(카테고리 몇 개, 모델 이름) | 값별 **부분 인덱스**: `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops) WHERE category = 'faq'` |
| 필터 값 종류가 많음(tenant 수천 개) | tenant로 **파티셔닝**(파티션별 인덱스), 또는 아래 iterative scan |
| 일반적인 경우(0.8.0+) | **iterative index scan**: `SET hnsw.iterative_scan = relaxed_order;` 결과가 모자라면 인덱스를 더 탐색. 상한 `hnsw.max_scan_tuples`(기본 20,000). `relaxed_order`는 재현율이 좋지만 순서가 약간 어긋날 수 있다 → 아래 materialized CTE로 다시 정렬 |
| 0.8.0 미만 | `ef_search`를 크게 올리거나 확장 업그레이드(`ALTER EXTENSION vector UPDATE`) |

relaxed_order 결과를 엄격한 거리순으로 받기(README 패턴):
```sql
SET hnsw.iterative_scan = relaxed_order;   -- 트랜잭션 한정이면 SET LOCAL
WITH relaxed AS MATERIALIZED (
  SELECT id, embedding <=> $1 AS distance FROM chunks
  WHERE tenant_id = $2 ORDER BY distance LIMIT 10
) SELECT * FROM relaxed ORDER BY distance + 0;   -- '+ 0'은 PG17+에서 플래너가 재정렬을 생략하지 않게 하려는 것
```

다중 테넌트 RAG에서 **tenant 필터 누락 = 다른 고객 문서 유출**이다. 벡터 쿼리에도 RLS 또는 강제된 tenant 조건을 적용한다(`security-privacy.md`).

## 7. 하이브리드 검색과 재정렬

- 고유명사·코드·숫자는 임베딩이 약하다. 출시 RAG는 전문 검색(`tsvector` + GIN, 또는 `pg_trgm`)과 벡터 결과를 **RRF(Reciprocal Rank Fusion)** 로 합치는 하이브리드를 검토한다. 한국어 전문 검색은 기본 파서가 형태소 분석을 안 하므로 품질 한계가 있다 [확인 필요: 한국어 형태소 확장 선택].
- 이진 양자화: `binary_quantize(embedding)::bit(n)`에 HNSW를 걸어 후보를 많이 뽑고, 원래 벡터로 재정렬(README는 상위 20개 재정렬 예시). 메모리가 병목일 때만.
- 정확도 개선은 인덱스 튜닝보다 청킹·재정렬 모델(cross-encoder) 쪽 효과가 클 때가 많다 — 검색 품질 문제를 DB 문제로만 보지 않는다.

## 8. 모델 교체·재색인

1. 새 컬럼(`embedding_v2 vector(새 차원)`, 1절의 청크당 1임베딩 구조) 또는 별도 임베딩 테이블에 새 모델 행(`(chunk_id, model)` PK 구조)을 추가 — 기존 검색은 계속 동작(expand). 1절 예시 테이블에 같은 청크를 모델만 바꿔 다시 넣으면 `(document_id, chunk_index)` unique에 막힌다.
2. 배치로 재임베딩(API 비용·속도 제한 고려, 진행 지점 기록, 실패 재시도).
3. 새 인덱스를 `CONCURRENTLY`로 생성.
4. 샘플 쿼리로 재현율·검색 품질 비교 후 쿼리 전환.
5. 옛 컬럼·인덱스 삭제(contract, 사용자 확인).

같은 모델이라도 버전·전처리(정규화, 접두어 프롬프트 등)가 바뀌면 벡터 공간이 달라질 수 있다 → 모델 이름에 버전까지 기록.

## 9. 별도 벡터 DB를 제안할 때

pgvector로 충분한 경우가 대부분이다(트랜잭션·조인·권한·백업을 한 곳에서). 별도 벡터 DB(Qdrant 등)는 다음이 **측정으로** 확인됐을 때만 제안: 벡터 수가 단일 PostgreSQL 메모리로 감당 안 되는 규모(인덱스가 RAM보다 훨씬 큼), 벡터 검색 부하가 OLTP를 방해해 분리가 필요, pgvector에 없는 기능이 필수.
