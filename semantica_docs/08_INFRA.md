# Infra 모듈

**최종 업데이트**: 2025-12-01

## 개요
외부 서비스 어댑터: DB, Cache, Vector, Graph, LLM, Observability.

## OpenTelemetry (NEW)

**구현**: `src/infra/observability/otel_setup.py`, `auto_instrumentation.py`

**자동 계측**: FastAPI, AsyncPG, HTTPX, Redis
**Export**: Prometheus (`/metrics`), OTLP (선택)
**메트릭**: `src/infra/llm/metrics.py`, `src/contexts/retrieval_search/infrastructure/metrics.py`, `src/contexts/indexing_pipeline/infrastructure/metrics.py`

**설정**: `settings.observability.otel_enabled=true`

## Rate Limiter (NEW)

**구현**: `src/infra/llm/rate_limiter.py`
**알고리즘**: Token Bucket
**제한**: Global (10k/min), Per-tenant (1k/min), Per-model (설정 가능), Max concurrent (10)

## Embedding Cache (NEW)

**구현**: `src/infra/llm/embedding_cache.py`
**Storage**: Redis (TTL 7일)
**설정**: `settings.llm.enable_embedding_cache` (벤치마킹 시 false)

## 서브모듈

### config
- `Settings`: Pydantic BaseSettings 기반 설정
- 환경 변수로 모든 연결 정보 관리

### db
- `PostgresStore`: asyncpg 연결 풀
- min=5, max=20, timeout=30s

### cache
- `RedisAdapter`: 비동기 Redis 캐시 **(버그 수정 2025-12-01)**
- `DistributedLock`: Redlock 기반 분산 잠금
- `NoOpLock`: 테스트/단일 프로세스용 Lock **(NEW 2025-12-01)**

### vector
- `QdrantAdapter`: 벡터 저장/검색
- 배치 업서트 (256 크기, 병렬)
- gRPC 프로토콜
- **버전 호환성 (2025-11-29)**: `check_compatibility=False` (클라이언트/서버 버전 차이 허용)

### graph
- `MemgraphGraphStore`: 그래프 저장/쿼리
- UNWIND 기반 배치 저장
- 모드: create, merge, upsert
- **파일 기반 쿼리 (2025-11-29)**: `get_callers_by_file()`, `get_subclasses_by_file()`, `get_superclasses_by_file()`

### search
- `ZoektAdapter`: HTTP 기반 렉시컬 검색
  - **성공 판정 개선 (2025-11-29)**: stderr 메시지 기반 ("finished shard", "files processed")

### llm
- `LiteLLMAdapter`: 다중 제공자 통합
- `OllamaAdapter`: 로컬 모델 게이트웨이
- Factory 함수들

### metadata
- `PostgresIndexingMetadataStore`: 버전 정보 관리

### git
- `GitCLIAdapter`: GitPython 래퍼

### observability
- **logging**: structlog 기반 구조화 로깅
- **metrics**: OpenTelemetry 호환 메트릭
- **tracing**: Span 기반 추적
- **alerting**: 규칙 기반 알림
- **cost_tracking**: LLM/API 비용 추적

## 외부 서비스

| 서비스 | 포트 (외부→내부) | 용도 |
|--------|------------------|------|
| PostgreSQL | 7201→5432 | 메타데이터, 청크, 메모리 |
| Redis | 7202→6379 | 캐시, 분산 잠금 |
| Qdrant | 7203/7204→6333/6334 | 벡터 검색 |
| Zoekt | 7205→6070 | 렉시컬 검색 |
| Memgraph | 7208/7209→7687/7444 | 그래프 쿼리 |
| Prometheus | 7206→9090 | 메트릭 수집 |
| Grafana | 7207→3000 | 대시보드 |
| API Server | 7200→8000 | HTTP API |
| Ollama | 8000 | 로컬 LLM (선택) |

## 주요 설정

```python
# 인덱싱 모드
INDEXING_ENABLE_LEXICAL = True
INDEXING_ENABLE_VECTOR = True
INDEXING_ENABLE_SYMBOL = True
INDEXING_ENABLE_FUZZY = True
INDEXING_ENABLE_DOMAIN = True

# 검색 가중치
RETRIEVER_WEIGHT_LEXICAL = 0.3
RETRIEVER_WEIGHT_VECTOR = 0.3
RETRIEVER_WEIGHT_SYMBOL = 0.2
RETRIEVER_WEIGHT_FUZZY = 0.1
RETRIEVER_WEIGHT_GRAPH = 0.1

# LLM
LLM_PROVIDER = "litellm"
LLM_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"
```

## 비용 추적

```python
# 가격 테이블 예시
GPT-4 Turbo: $0.01/$0.03 (input/output per 1K tokens)
Embedding-3-small: $0.02 per 1M tokens

# 추적 메서드
record_llm_cost()
record_embedding_cost()
record_vector_search_cost()
```

---

## 최근 개선 사항 (2025-11-29)

### 1. Zoekt 성공 판정 로직 개선

**파일**: `src/contexts/multi_index/infrastructure/lexical/adapter_zoekt.py`

**문제**: Zoekt는 성공 시에도 진행 상황을 stderr로 출력하고 non-zero exit code를 반환할 수 있음

**해결**:
```python
# stderr 내용 기반 성공 판정
stderr_lower = result.stderr.lower() if result.stderr else ""
is_success = (
    result.returncode == 0 or 
    "finished shard" in stderr_lower or
    "files processed" in stderr_lower
)
```

**효과**:
- 대용량 레포지토리 인덱싱 시 false negative 제거
- "6990 files processed" 같은 성공 메시지 인식

### 2. PostgreSQL Cleanup 안정성

**파일**: `.benchmark/run_benchmark_indexing.py`

**개선**: 테이블 missing 시 graceful degradation

```python
try:
    result = await conn.execute("DELETE FROM chunk_to_ir_mappings ...")
except asyncpg.UndefinedTableError:
    # 테이블 없으면 skip
    pass
```

**효과**:
- 초기 벤치마크 실행 시 에러 방지
- DB 스키마 migration 중에도 동작

### 3. MemgraphGraphStore API 개선

**파일**: `src/infra/graph/memgraph.py`

**개선**: 내부 `_conn` 접근 금지, 공식 API 사용

```python
# Before (잘못된 방식)
graph_store._conn.execute("MATCH (n) ...")

# After (올바른 방식)
graph_store.delete_repo(repo_id)
```

**추가 메서드**:
- `delete_repo(repo_id)`: 레포지토리 전체 삭제
- `delete_snapshot(repo_id, snapshot_id)`: 스냅샷 삭제
- `get_callers_by_file(repo_id, file_path)`: 파일 기반 호출자 조회
- `get_subclasses_by_file(repo_id, file_path)`: 파일 기반 서브클래스 조회
- `get_superclasses_by_file(repo_id, file_path)`: 파일 기반 부모 클래스 조회

### 4. Qdrant 버전 경고 억제

**파일**: `.benchmark/run_benchmark_indexing.py`

```python
# 버전 불일치 경고 억제
client = QdrantClient(host="localhost", port=7203, check_compatibility=False)
```

**효과**:
- 클라이언트 v1.14.3, 서버 v1.12.5 조합에서도 정상 동작
- 벤치마크 로그 깔끔하게 유지

### 6. RedisAdapter 확장 (2025-12-02)

**파일**: `src/infra/cache/redis.py`

**문제**: DistributedLock과 3-tier 캐시를 위한 메서드 부족

**추가된 기능**:
```python
# 1. set()에 ex, nx 파라미터 추가
await redis.set(key, value, ex=300, nx=True)

# 2. exists() 메서드
exists = await redis.exists(key)

# 3. ttl() 메서드  
ttl = await redis.ttl(key)

# 4. eval() 메서드 (Lua 스크립트)
result = await redis.eval(script, keys=[key], args=[value])

# 5. get_bytes() / set_bytes() (바이너리 데이터)
await redis.set_bytes(key, binary_data)
data = await redis.get_bytes(key)
```

**효과**:
- ✅ DistributedLock 완전 호환
- ✅ CachedIRGenerator 바이너리 지원 (pickle 직렬화)
- ✅ 원자적 잠금 해제 (Lua 스크립트)
- ✅ base64 인코딩으로 Redis 호환성 유지

### 7. NoOpLock 구현 (2025-12-02)

**파일**: `src/infra/cache/lock.py`

**용도**: 테스트 및 단일 프로세스 환경용 락 구현

```python
class NoOpLock:
    """No-operation lock for testing"""
    async def acquire(self, blocking=True, timeout=None):
        return True  # 항상 성공
    
    async def release(self):
        pass  # No-op
    
    async def extend(self, additional_ttl):
        pass  # No-op
```

**효과**:
- ✅ 통합 테스트에서 Redis 의존성 제거
- ✅ 단일 프로세스 환경에서 오버헤드 제거
- ✅ 동일한 인터페이스 유지 (호환성)

---

## 3-Tier 캐시 인프라 (NEW - 2025-11-29)

### 통합 캐시 시스템

**파일**: `src/infra/cache/three_tier_cache.py`

모든 데이터 타입(IR, Graph, Chunk)을 위한 통합 3-tier 캐시:

```python
class ThreeTierCache[T]:
    """
    Read: L1 → L2 → L3
    Write: L3 (persistent) + optional L1/L2 populate
    """
    
    async def get(key) -> T:
        # L1: In-memory (fastest)
        if value := l1.get(key):
            return value
        
        # L2: Redis (fast, shared)
        if value := await l2.get(key):
            l1.set(key, value)  # Populate L1
            return value
        
        # L3: Database/Re-parse (slow)
        if value := await l3.load(key):
            l1.set(key, value)
            await l2.set(key, value)
            return value
        
        return None
```

**기능**:
- ✅ LRU eviction
- ✅ TTL expiration
- ✅ 크기 추적
- ✅ Hit/miss 통계
- ✅ Thread-safe
- ✅ Graceful degradation (Redis 장애 시)

### Store별 캐시 구현

| Store | 파일 | L1 | L2 | L3 | TTL |
|-------|------|----|----|----|----|
| **CachedChunkStore** | `src/contexts/code_foundation/infrastructure/chunk/cached_store.py` | ✅ | ✅ | PostgreSQL | 300s |
| **CachedGraphStore** | `src/infra/graph/cached_store.py` | ✅ | ✅ | Memgraph | 600s |
| **CachedIRGenerator** | `src/contexts/code_foundation/infrastructure/generators/cached_generator.py` | ✅ | ✅ | Re-parse | 600s |

### 설정

**파일**: `src/infra/config/groups.py`

```python
class CacheConfig(BaseModel):
    # 전역 스위치
    enable_three_tier: bool = True
    
    # L1 크기 (In-Memory)
    l1_chunk_maxsize: int = 1000
    l1_graph_node_maxsize: int = 5000
    l1_graph_relation_maxsize: int = 2000
    l1_ir_maxsize: int = 500
    
    # TTL (초)
    chunk_ttl: int = 300   # Chunk: 5분
    graph_ttl: int = 600   # Graph: 10분
    ir_ttl: int = 600      # IR: 10분
    
    # Redis 연결
    host: str = "localhost"
    port: int = 6379
```

### Container 통합

**파일**: `src/container.py`

```python
@cached_property
def chunk_store(self):
    base = PostgresChunkStore(...)
    
    if settings.cache.enable_three_tier:
        return CachedChunkStore(
            chunk_store=base,
            redis_client=self.redis.client,
            l1_maxsize=settings.cache.l1_chunk_maxsize,
            ttl=settings.cache.chunk_ttl,
        )
    
    return base

@cached_property
def graph_store(self):
    base = MemgraphGraphStore(...)
    
    if settings.cache.enable_three_tier:
        return CachedGraphStore(
            graph_store=base,
            redis_client=self.redis.client,
            l1_node_maxsize=settings.cache.l1_graph_node_maxsize,
            l1_relation_maxsize=settings.cache.l1_graph_relation_maxsize,
            ttl=settings.cache.graph_ttl,
        )
    
    return base
```

**투명성**: 기존 코드 수정 불필요 (API 100% 호환)

### 성능 메트릭

**OpenTelemetry**:
```python
# 자동 기록됨
cache_get_latency_ms{tier="l1", namespace="chunks"}
cache_get_latency_ms{tier="l2", namespace="chunks"}
cache_get_latency_ms{tier="l3", namespace="chunks"}
```

**Stats API**:
```python
stats = container.chunk_store.stats()
# {
#   "l1": {
#     "hits": 1000,
#     "misses": 300,
#     "hit_rate": 76.9,
#     "size": 800,
#     "maxsize": 1000,
#     "evictions": 50,
#   },
#   "l2": {"hits": 200, "misses": 100, "hit_rate": 66.7},
#   "l3": {"hits": 100, "misses": 0, "hit_rate": 100.0}
# }
```

---

## OpenTelemetry 메트릭 수정 (NEW - 2025-11-29)

### 문제점 및 해결

**1. container.indexing_orchestrator() 호출 오류**

**파일**: `server/api_server/main.py:69`

**문제**: `@cached_property`를 함수처럼 호출하여 "object is not callable" 에러 발생

**수정**:
```python
# Before
orchestrator = container.indexing_orchestrator()

# After
orchestrator = container.indexing_orchestrator  # Property 접근
```

**효과**: Background cleanup 정상 시작

---

**2. OTEL Metrics Export Gap**

**파일**: `server/api_server/main.py:156-164`

**문제**: FastAPI `/metrics` 엔드포인트가 `prometheus_client.REGISTRY`만 사용하여 OTEL auto-instrumentation 메트릭 누락

**수정**:
- FastAPI instrumentation 시 `/metrics` 엔드포인트 제외 설정
- `PrometheusMetricReader`가 기본 `prometheus_client.REGISTRY` 사용 확인
- OTEL 메트릭 자동 노출

**효과**:
- HTTP 요청 메트릭 (`http_server_*`)
- HTTP 클라이언트 메트릭 (`http_client_*`)
- DB 쿼리 메트릭 (AsyncPG)
- Redis 메트릭
- 모든 auto-instrumentation 메트릭이 `/metrics`에 노출

---

**3. LLM Metrics 초기화 타이밍**

**파일**: `src/infra/llm/metrics.py`

**문제**: 모듈 import 시점에 `_init_instruments()` 호출 → `setup_otel()` 실행 전이라 meter가 None

**수정**: Lazy initialization 패턴 적용
```python
def _ensure_instruments():
    """Ensure instruments are initialized (lazy)."""
    if _llm_requests_total is None:
        _init_instruments()

def record_llm_request(...):
    _ensure_instruments()  # 호출 시점에 초기화
    if _llm_requests_total is None:
        return
    # ...
```

**효과**:
- `setup_otel()` 후 첫 번째 `record_*()` 호출 시 자동 초기화
- 모든 LLM 메트릭 정상 수집:
  - `llm_requests_total`
  - `llm_tokens_total` (total, input, output)
  - `llm_cost_total`
  - `llm_latency_milliseconds`

### 노출 메트릭

**시스템**:
- `python_gc_*`: GC 통계
- `python_info`: Python 버전 정보

**리소스**:
- `target_info`: service_name, version, deployment_environment

**HTTP**:
- `http_server_active_requests`: 활성 요청 수
- `http_server_duration_milliseconds`: 요청 지연시간
- `http_client_duration_milliseconds`: 외부 호출 지연시간

**LLM**:
- `llm_requests_total`: 요청 수
- `llm_tokens_total`: 토큰 사용량
- `llm_cost_total`: 비용 (USD)
- `llm_latency_milliseconds`: 지연시간

---

## 최근 버그 수정 및 개선 (2025-12-01)

### RedisAdapter 버그 수정 및 확장

**파일**: `src/infra/cache/redis.py`

**발견된 버그**:
1. `set()` 메서드에 `ex`, `nx` 파라미터 미지원
   - `DistributedLock`에서 `set(key, value, ex=ttl, nx=True)` 호출 시 `TypeError`
2. `eval()`, `exists()`, `ttl()` 메서드 없음
   - `DistributedLock.release()`에서 Lua 스크립트 실행 불가

**수정 내용**:

```python
class RedisAdapter:
    async def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,    # TTL (seconds) - NEW
        nx: bool = False,         # SET if Not eXists - NEW
        **kwargs
    ) -> bool | None:
        """
        Set value with optional TTL and NX flag.
        
        Args:
            ex: Expire time in seconds
            nx: Only set if key doesn't exist
            
        Returns:
            - bool if nx=True (True if set, False if already exists)
            - None otherwise
        """
        if nx:
            # SET NX: returns True if set, False if already exists
            return await self._client.set(key, value, ex=ex, nx=nx)
        else:
            await self._client.set(key, value, ex=ex, **kwargs)
            return None
    
    async def exists(self, *keys: str) -> int:
        """Check if keys exist. Returns count of existing keys."""
        return await self._client.exists(*keys)
    
    async def ttl(self, key: str) -> int:
        """Get remaining TTL in seconds. Returns -1 if no TTL, -2 if not exists."""
        return await self._client.ttl(key)
    
    async def eval(
        self,
        script: str,
        numkeys: int,
        *args
    ) -> Any:
        """Execute Lua script."""
        return await self._client.eval(script, numkeys, *args)
```

**효과**:
- ✅ `DistributedLock` 정상 작동 (Lock 획득/해제)
- ✅ Native Redis client 호환성 확보
- ✅ Lua 스크립트 실행 가능 (원자적 연산)

**검증**:
```python
# Lock 획득 (NX 사용)
acquired = await redis.set("lock:repo:abc", "owner-id", ex=60, nx=True)
assert acquired is True  # 처음 획득 성공

# TTL 확인
ttl = await redis.ttl("lock:repo:abc")
assert 0 < ttl <= 60

# Lua 스크립트로 원자적 해제
script = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""
result = await redis.eval(script, 1, "lock:repo:abc", "owner-id")
assert result == 1  # 성공적으로 삭제
```

---

### PostgresChunkStore Pool 공유

**파일**: `src/contexts/code_foundation/infrastructure/chunk/store_postgres.py`

**문제**: 
- 각 `PostgresChunkStore` 인스턴스가 독립적인 connection pool 생성
- 동일한 DB에 대해 여러 pool 생성 → 리소스 낭비

**개선**:

```python
class PostgresChunkStore:
    def __init__(
        self,
        postgres_store: PostgresStore | None = None,  # NEW: pool 재사용
        db_url: str | None = None,  # 기존 방식 (하위 호환)
        table_name: str = "chunks",
    ):
        if postgres_store:
            # Pool 공유 (권장)
            self._postgres = postgres_store
            self._owns_pool = False
        elif db_url:
            # 독립 pool 생성 (하위 호환)
            self._postgres = PostgresStore(db_url)
            self._owns_pool = True
        else:
            raise ValueError("Either postgres_store or db_url required")
    
    async def close(self):
        """Close connection pool (only if owned)"""
        if self._owns_pool:
            await self._postgres.close()
```

**FoundationContainer 통합**:

```python
@cached_property
def chunk_store(self) -> PostgresChunkStore:
    # 공유 PostgresStore 주입
    return PostgresChunkStore(
        postgres_store=self.infra.postgres_store,  # Pool 재사용
        table_name="chunks"
    )
```

**효과**:
- ✅ Connection pool 재사용 (메모리/연결 절약)
- ✅ 여러 store가 동일 pool 공유
- ✅ 하위 호환성 유지 (`db_url` 방식도 작동)

**성능 개선**:
| 지표 | 기존 (독립 pool) | 개선 (공유 pool) |
|------|----------------|----------------|
| DB 연결 수 | 20 × N stores | 20 (고정) |
| Pool 초기화 시간 | ~100ms × N | ~100ms (1회) |
| 메모리 사용량 | ~10MB × N | ~10MB (1회) |

---

### NoOpLock (테스트용)

**파일**: `src/infra/cache/noop_lock.py`

**용도**: 테스트 및 단일 프로세스 환경에서 Lock 오버헤드 제거

```python
class NoOpLock:
    """
    No-op distributed lock for testing/single-process environments.
    
    항상 Lock 획득 성공, 실제 잠금 없음.
    """
    
    def __init__(self, *args, **kwargs):
        pass
    
    async def acquire(self, blocking: bool = True, timeout: float | None = None) -> bool:
        """Always succeeds immediately."""
        return True
    
    async def release(self):
        """No-op."""
        pass
    
    async def extend(self):
        """No-op."""
        pass
    
    async def __aenter__(self):
        await self.acquire()
        return self
    
    async def __aexit__(self, *args):
        await self.release()
```

**사용 예시**:

```python
# 환경 변수로 제어
SEMANTICA_ENABLE_DISTRIBUTED_LOCK=false

# Container에서 자동 선택
@cached_property
def distributed_lock_factory(self):
    if settings.enable_distributed_lock:
        return lambda key, ttl: DistributedLock(self.redis, key, ttl)
    else:
        return lambda key, ttl: NoOpLock()

# 테스트에서 Lock 무시
async def test_indexing_without_lock():
    lock = NoOpLock()
    async with lock:  # 즉시 통과
        await index_repository(...)
```

**효과**:
- ✅ 테스트 속도 향상 (Lock 대기 시간 제거)
- ✅ 단일 프로세스 환경에서 불필요한 Redis 의존성 제거
- ✅ 프로덕션에서는 실제 `DistributedLock` 사용
