# 캐싱 전략

**최종 업데이트**: 2025-12-02

## 개요
다계층 캐싱: Redis(분산), In-Memory(LRU), File(영속), Content-Hash(증분).

## Embedding Cache (NEW)

**구현**: `src/infra/llm/embedding_cache.py`
**Storage**: Redis (TTL 7일)
**Key**: `embedding:{model}:{hash(text)}`
**Enable/Disable**: `settings.llm.enable_embedding_cache` (벤치마킹 시 false)
**메트릭**: `retrieval.cache.hits/misses`

**최신 상태 (2025-12-02)**:
- ✅ 3-tier 통합 캐시 시스템 (L1 LRU + L2 Redis + L3 DB/Re-compute)
- ✅ **Graph/Chunk: 3-tier 캐싱 활성화 (enable_three_tier=True)**
- ✅ **IR: 3-tier 캐싱 완전 연결 (2025-12-02)**
  - FoundationContainer 통합 완료
  - Redis 바이너리 지원 (base64 인코딩)
  - Event Loop 안전 처리
  - Multi-repo 지원 (`create_ir_builder(repo_id)`)
- ✅ Container 통합 (FoundationContainer에서 제공)
- ✅ Snapshot GC 자동 정리 (1시간 주기)

**IR 캐싱 활성화 조건** (SOTA 기반 Trade-off):
- `enable_three_tier=True`: IR Generator를 CachedIRGenerator로 래핑
- 작은 레포 (<100파일): 파싱 충분히 빠름 (0.9ms/파일), 캐싱 오버헤드 > 이득
- 큰 레포 (>1000파일): 캐싱 효과 유의미, 특히 Impact Pass 재인덱싱 시

## 캐싱 계층

```
┌─────────────────────────────────────────────────────┐
│                  Application Layer                  │
├─────────────────────────────────────────────────────┤
│ L1: In-Memory LRU Cache (ms 단위)                   │
│   - RetrieverV3Cache (쿼리/의도/RRF)               │
│   - InMemoryEmbeddingCache (임베딩)                │
│   - InMemoryLLMScoreCache (LLM 점수)               │
├─────────────────────────────────────────────────────┤
│ L2: Redis (분산, 100ms 단위)                        │
│   - 분산 잠금 (DistributedLock)                    │
│   - 세션 캐시                                       │
│   - 공유 상태                                       │
├─────────────────────────────────────────────────────┤
│ L3: File/DB (영속, 디스크)                          │
│   - FileBasedEmbeddingCache                        │
│   - FileBasedLLMScoreCache                         │
│   - PostgreSQL (메타데이터)                        │
└─────────────────────────────────────────────────────┘
```

## 1. Retriever V3 Cache (3-tier)

### 구조
```python
RetrieverV3Cache:
  ├─ Tier 1: query_results (쿼리 → 결과)
  │     maxsize=1000, ttl=300s
  ├─ Tier 2: intent_probs (쿼리 → 의도)
  │     maxsize=500, ttl=300s
  └─ Tier 3: rrf_scores (히트 fingerprint → RRF)
        maxsize=500, ttl=300s
```

### 성능
- Cache hit: ~0.1ms
- Cache miss: ~20ms (전체 검색)
- 예상 hit rate: 30-40%
- 평균 지연 감소: -6ms

### 키 생성
```python
# 쿼리 키 (SHA256)
key = f"{repo_id}:{snapshot_id}:{query}:{strategy_config}"

# RRF 키 (히트 fingerprint)
fingerprint = f"repo:{repo_id}:{snapshot_id}|{strategy}:{chunk_ids}"
```

## 2. 임베딩 캐시 (Late Interaction)

### 목적
ColBERT 스타일 토큰 임베딩 재사용

### 구현
```python
InMemoryEmbeddingCache:
  maxsize=10000
  캐시 단위: chunk_id → (num_tokens, dim) 배열

FileBasedEmbeddingCache:
  디렉토리 기반 pickle 저장
  파일명: {chunk_id}.pkl
```

### 성능
- Latency: -90% (cache hit)
- Cost: -80% (임베딩 계산 감소)
- Memory: -50% (quantization 사용 시)

### 최적화
- **GPU 가속**: torch.cuda 사용 시 MaxSim 10배 빠름
- **Quantization**: int8 양자화로 메모리 50% 감소
- **Pre-compute**: 인덱싱 시점에 미리 계산

```python
# 인덱싱 시 미리 계산
optimizer.precompute_embeddings(chunks, batch_size=100)
```

## 3. LLM Reranker 캐시

### 목적
LLM API 호출 비용 절감

### 구현
```python
InMemoryLLMScoreCache:
  maxsize=10000
  default_ttl=3600 (1시간)

FileBasedLLMScoreCache:
  디렉토리 기반 pickle 저장
```

### 캐시 키 구성
```python
key = hash(f"{normalized_query}|{chunk_id}|{content_hash}|{prompt_version}")
```

### 성능
- Cache hit: ~1ms (vs 500ms LLM 호출)
- Cost 감소: 70%
- 예상 hit rate: 60-80%

### 캐시 무효화
- `content_hash`: 청크 내용 변경 감지
- `prompt_version`: 프롬프트 변경 시 무효화

## 4. Redis 캐시

### 용도
- **분산 잠금**: 동시 편집 제어
- **세션 캐시**: 공유 상태
- **JSON 자동 직렬화**

### 주요 메서드
```python
# 기본 연산
await redis.get(key)
await redis.set(key, value, expire_seconds=300)
await redis.delete(key)
await redis.exists(key)

# 키 검색 (SCAN 사용 - 논블로킹)
await redis.keys(pattern="user:*", use_scan=True)

# 헬스체크
await redis.ping()
```

### 분산 잠금 (DistributedLock)
```python
lock = DistributedLock(redis, lock_key, ttl=300)

# 획득 (blocking + timeout)
acquired = await lock.acquire(blocking=True, timeout=60)

# 연장 (장시간 작업)
await lock.extend(additional_ttl=60)

# 해제 (Lua 스크립트로 원자성)
await lock.release()
```

## 5. Content Hash 캐싱

### 용도
증분 인덱싱에서 변경 감지

### 구현 위치
- `Chunk.content_hash`: 청크 내용 해시
- `ChunkIncrementalRefresher`: 해시 비교로 변경 감지

```python
# 청크 변경 감지
if old_chunk.content_hash != new_chunk.content_hash:
    upsert(new_chunk)  # 변경됨
else:
    skip()  # 변경 없음 - 기존 유지
```

### RepoMap Summary 캐시
```python
SummaryCache:
  key: content_hash
  value: LLM 생성 요약

# 동일 코드는 요약 재생성 안 함
cached = cache.get(content_hash)
if cached:
    return cached
else:
    summary = await llm.summarize(code)
    cache.set(content_hash, summary)
```

## 6. 캐시 통계

### RetrieverV3Cache
```python
stats = cache.stats()
# {
#   "query_results": {"size": 500, "hits": 1000, "hit_rate": 45.2},
#   "intent_probs": {"size": 200, "hits": 800, "hit_rate": 60.0},
#   "rrf_scores": {"size": 300, "hits": 600, "hit_rate": 55.0}
# }
```

### LRU Cache 공통 통계
```python
{
  "size": 현재 항목 수,
  "maxsize": 최대 항목 수,
  "hits": 캐시 히트 수,
  "misses": 캐시 미스 수,
  "hit_rate": 히트율 (%),
  "ttl": TTL (초)
}
```

## 7. 캐시 전략 요약

| 캐시 | 저장소 | TTL | 용도 |
|------|--------|-----|------|
| RetrieverV3Cache | In-Memory | 300s | 검색 결과/의도/RRF |
| EmbeddingCache | In-Memory/File | 무제한 | 토큰 임베딩 |
| LLMScoreCache | In-Memory/File | 3600s | LLM 재랭킹 점수 |
| Redis | Redis | 가변 | 분산 잠금/세션 |
| SummaryCache | In-Memory | 무제한 | LLM 요약 |
| ContentHash | 없음 (비교용) | - | 증분 변경 감지 |

## 8. 캐시 무효화 전략

| 이벤트 | 무효화 대상 |
|--------|-----------|
| 청크 내용 변경 | content_hash 변경 → 임베딩/요약 재생성 |
| 스냅샷 변경 | snapshot_id 포함 캐시 키 무효화 |
| 프롬프트 변경 | prompt_version 변경 → LLM 캐시 무효화 |
| TTL 만료 | 자동 제거 (LRU eviction) |

---

## 9. 3-Tier 통합 캐시 시스템 (NEW - 2025-11-29)

### 개요

**파일**: `src/infra/cache/three_tier_cache.py`

모든 주요 데이터 타입(IR, Graph, Chunk)에 대한 통합 3-tier 캐싱:

```
┌─────────────────────────────────────────────────────┐
│ L1: In-Memory LRU                                   │
│   - Latency: ~0.1ms                                 │
│   - Size: 500-5000 items                            │
│   - Thread-safe, TTL support                        │
├─────────────────────────────────────────────────────┤
│ L2: Redis                                           │
│   - Latency: ~1-2ms                                 │
│   - Shared across instances                         │
│   - Pickle serialization                            │
├─────────────────────────────────────────────────────┤
│ L3: Database                                        │
│   - PostgreSQL (Chunks)                             │
│   - Memgraph (Graph nodes)                          │
│   - Re-parse (IR)                                   │
│   - Latency: ~10-50ms                               │
└─────────────────────────────────────────────────────┘
```

### 구현된 캐시

#### 1. **CachedChunkStore**

**파일**: `src/contexts/code_foundation/infrastructure/chunk/cached_store.py`

```python
from src.foundation.chunk.cached_store import CachedChunkStore

cached_store = CachedChunkStore(
    chunk_store=postgres_chunk_store,
    redis_client=redis,
    l1_maxsize=1000,
    ttl=300,  # 5분
)

# 투명한 API (기존 ChunkStore와 동일)
chunk = await cached_store.get_by_id(chunk_id)  # L1 → L2 → L3
await cached_store.save(chunk)  # Write-through
```

**성능**:
- L1 hit: ~0.1ms (vs 10-50ms DB)
- Expected hit rate: 40-60%
- API 100% 호환

#### 2. **CachedGraphStore**

**파일**: `src/infra/graph/cached_store.py`

```python
from src.infra.graph.cached_store import CachedGraphStore

cached_store = CachedGraphStore(
    graph_store=memgraph_store,
    redis_client=redis,
    l1_node_maxsize=5000,
    l1_relation_maxsize=2000,
    ttl=600,  # 10분
)

# 노드 조회 (3-tier)
node = await cached_store.query_node_by_id_async(node_id)

# 관계 조회 (L1 only)
callers = cached_store.get_callers_by_file(repo_id, file_path)
```

**캐시 전략**:
- **노드**: 3-tier (자주 조회)
- **관계**: L1 only (동적 쿼리)
- **저장**: 캐시 무효화

#### 3. **CachedIRGenerator** ✅ (2025-12-02 완전 연결 완료)

**파일**: `src/contexts/code_foundation/infrastructure/generators/cached_generator.py`

**상태**: ✅ **FoundationContainer 통합 완료 + Redis 바이너리 지원**

```python
# 사용법 (Container를 통해 자동 제공)
from src.container import container

# enable_three_tier=True이면 자동으로 CachedIRGenerator
ir_builder = container._foundation.ir_builder

# IndexingOrchestrator가 자동으로 사용
# (src/contexts/analysis_indexing/infrastructure/di.py:254)
ir_builder = self._foundation.ir_builder  # CachedIRGenerator or PythonIRGenerator
```

**캐시 키**: `file_path:content_hash:snapshot_id`
- content_hash로 파일 변경 감지
- 동일 파일은 재파싱 안 함

**활성화 조건**:
- `settings.cache.enable_three_tier=True` (기본값)
- 작은 레포 (<100파일): 캐싱 오버헤드 > 이득 (파싱 0.9ms vs Redis 1-2ms)
- 큰 레포 (>1000파일): 캐싱 효과 유의미

**SOTA Trade-off 참고**:
- Zoekt/Sourcegraph: IR 캐싱 없음 (Fast recomputation)
- rust-analyzer/TS Server: IR 캐싱 있음 (Query-based incremental)
- Codegraph: **Zoekt 스타일 + Optional Caching** (유연성)

### Container 통합 (2025-12-02 업데이트)

**파일**: `src/contexts/code_foundation/infrastructure/di.py` (FoundationContainer)

```python
# 설정으로 제어
SEMANTICA_CACHE_ENABLE_THREE_TIER=true  # 기본값

# FoundationContainer에서 자동 래핑
container.chunk_store        # CachedChunkStore (if enabled)
container.graph_store        # CachedGraphStore (if enabled)
container._foundation.ir_builder  # CachedIRGenerator (if enabled) ✅ NEW
```

**연결 경로**:
```
Container
  └─ FoundationContainer
       ├─ ir_builder (default: repo_id='codegraph')
       │    └─ CachedIRGenerator (if enable_three_tier=True)
       │         ├─ L1: LRU Cache (~0.1ms)
       │         ├─ L2: RedisAdapter (async, ~1-2ms) ✅ FIXED
       │         └─ L3: PythonIRGenerator (re-parse)
       │
       └─ create_ir_builder(repo_id) ✅ NEW
            └─ CachedIRGenerator (dynamic repo_id)

IndexingContainer.indexing_orchestrator
  └─ uses foundation.ir_builder
```

**주요 수정 (2025-12-02)**:
1. ✅ **L2 Redis 연결 수정**: `redis.client` → `redis` (RedisAdapter 전체 전달)
2. ✅ **바이너리 데이터 지원**: `get_bytes()`/`set_bytes()` 메서드 추가 (base64 인코딩)
3. ✅ **Event Loop 안전 처리**: `loop.is_closed()` 체크 추가
4. ✅ **Multi-repo 지원**: `create_ir_builder(repo_id)` 메서드 추가
5. ✅ **Orchestrator 통합**: IndexingOrchestrator가 `foundation.ir_builder` 자동 사용

**성능 검증 결과** (엄격한 비판적 검증 통과):
- L1 (LRU):    ~0.09ms  (350x faster than L3) ✅
- L2 (Redis):  ~0.90ms  (34x faster than L3)  ✅
- L3 (Parse):  ~30ms    (baseline)
- base64 오버헤드: ~0.007ms (무시 가능)

**검증 항목**:
- ✅ Event Loop 에러 해결
- ✅ L1/L2/L3 모든 레이어 작동
- ✅ Cache Hierarchy 올바른 순서 (L1 < L2 < L3)
- ✅ UTF-8 디코딩 에러 해결
- ✅ Redis 실패 시 Fallback 작동

### 설정

**파일**: `src/infra/config/groups.py`

```python
class CacheConfig(BaseModel):
    # 3-tier cache 활성화
    enable_three_tier: bool = True
    
    # L1 크기
    l1_chunk_maxsize: int = 1000
    l1_graph_node_maxsize: int = 5000
    l1_graph_relation_maxsize: int = 2000
    l1_ir_maxsize: int = 500
    
    # TTL
    chunk_ttl: int = 300   # 5분
    graph_ttl: int = 600   # 10분
    ir_ttl: int = 600      # 10분
```

### 성능 비교

| 작업 | Without Cache | L1 Hit | L2 Hit | L3 Hit |
|------|---------------|--------|--------|--------|
| Chunk 조회 | ~20ms | ~0.1ms | ~1ms | ~20ms |
| Graph 노드 조회 | ~30ms | ~0.1ms | ~1ms | ~30ms |
| IR 파싱 | ~50ms | ~0.1ms | ~1ms | ~50ms |
| **평균 개선** | - | **200x** | **20x** | **1x** |

**Expected Hit Rate**: 50-70% (L1+L2 combined)

---

## 10. Snapshot Garbage Collection (NEW - 2025-11-29)

### 개요

**파일**: `src/contexts/indexing_pipeline/infrastructure/snapshot_gc.py`

오래된 스냅샷 자동 정리로 디스크 공간 절약.

### 보관 정책

```python
from src.indexing.snapshot_gc import SnapshotRetentionPolicy

policy = SnapshotRetentionPolicy(
    keep_latest_count=10,  # 최근 10개 유지
    keep_days=30,          # 30일 이내 유지
    keep_tagged=True,      # 태그된 스냅샷 영구 보관
)
```

**삭제 조건**: 다음을 **모두** 만족해야 삭제
1. 최신 N개가 아님
2. N일 이전 생성
3. 태그 없음 (또는 keep_tagged=False)

### GC 서비스

```python
from src.indexing.snapshot_gc import SnapshotGarbageCollector

gc = SnapshotGarbageCollector(
    postgres_store=postgres,
    graph_store=memgraph_store,
    policy=policy,
)

# 수동 실행
result = await gc.cleanup_repo(repo_id="my-repo")
print(f"Deleted {result['snapshots_deleted']} snapshots")
print(f"Freed {result['chunks_deleted']} chunks")

# Dry run (삭제 안 함)
result = await gc.cleanup_repo(repo_id="my-repo", dry_run=True)

# 모든 레포지토리 정리
result = await gc.cleanup_all_repos()
```

### Cascade 삭제

스냅샷 삭제 시 관련 데이터 자동 정리:
1. ✅ Chunk mappings (IR, Graph)
2. ✅ Chunks (soft delete)
3. ✅ Graph nodes/edges (Memgraph)
4. ✅ Pyright snapshots
5. ✅ RepoMap nodes

### 백그라운드 실행

**파일**: `src/contexts/indexing_pipeline/infrastructure/background_cleanup.py`

```python
# BackgroundCleanupService에 통합됨
service = await start_background_cleanup(
    edge_validator=edge_validator,
    cleanup_interval_seconds=3600,  # 1시간
    graph_store=graph_store,
    snapshot_gc=container.snapshot_gc,  # NEW
)

# API 서버 시작 시 자동 실행됨 (server/api_server/main.py)
```

**실행 주기**: 1시간 (설정 가능)

### 통계

```python
{
    "snapshots_deleted": 5,
    "snapshot_ids": ["snap1", "snap2", ...],
    "chunks_deleted": 1500,
    "nodes_deleted": 800,
}
```

### OpenTelemetry 메트릭

- `snapshot_gc_runs_total`: GC 실행 횟수
- `snapshot_gc_snapshots_deleted_total`: 삭제된 스냅샷 수

---

## 11. 전체 캐시 아키텍처 (Updated)

```
Application
    │
    ├─ CachedChunkStore (3-tier)
    │   ├─ L1: LRU (1000 items, 300s TTL)
    │   ├─ L2: Redis (shared)
    │   └─ L3: PostgreSQL
    │
    ├─ CachedGraphStore (3-tier)
    │   ├─ Nodes: L1+L2+L3 (5000 items, 600s TTL)
    │   ├─ Relations: L1 only (2000 items, 300s TTL)
    │   └─ L3: Memgraph
    │
    ├─ CachedIRGenerator (3-tier)
    │   ├─ L1: LRU (500 items, 600s TTL)
    │   ├─ L2: Redis (shared)
    │   └─ L3: Re-parse
    │
    ├─ RetrieverV3Cache (3-tier)
    │   └─ (기존과 동일)
    │
    └─ SnapshotGC (Background)
        └─ 24시간마다 자동 실행
```

### 캐시 활성화 제어

```bash
# .env 또는 환경 변수
SEMANTICA_CACHE_ENABLE_THREE_TIER=true  # 기본값

# L1 크기 조정
SEMANTICA_CACHE_L1_CHUNK_MAXSIZE=1000
SEMANTICA_CACHE_L1_GRAPH_NODE_MAXSIZE=5000
SEMANTICA_CACHE_L1_GRAPH_RELATION_MAXSIZE=2000
SEMANTICA_CACHE_L1_IR_MAXSIZE=500

# TTL 조정
SEMANTICA_CACHE_CHUNK_TTL=300   # 5분
SEMANTICA_CACHE_GRAPH_TTL=600   # 10분
SEMANTICA_CACHE_IR_TTL=600      # 10분
```

### 통계 모니터링

```python
# Chunk 캐시 통계
stats = container.chunk_store.stats()
print(f"L1 hit rate: {stats['l1']['hit_rate']:.1f}%")
print(f"L2 hit rate: {stats['l2']['hit_rate']:.1f}%")

# Graph 캐시 통계
stats = container.graph_store.stats()
print(f"Nodes: {stats['nodes']['l1']['size']} items")
print(f"Relations: {stats['relations']['size']} items")

# Snapshot GC 수동 실행
result = await container.snapshot_gc.cleanup_repo("my-repo", dry_run=True)
print(f"Will delete {result['snapshots_deleted']} snapshots")
```
