# infra (Config / Storage / Observability / Jobs / LLM)

**Scope:** 모든 컨텍스트가 공유하는 인프라 계층(설정/스토리지/관측/잡/LLM)
**Source of Truth:** `packages/codegraph-shared/codegraph_shared/infra/`

---

## What it does

- **config**: settings/groups/profiles/logging
- **storage/db**: sqlite/postgres/auto, schema
- **observability**: logging/metrics/tracing/otel
- **jobs**: worker/handler/queue/SemanticaTaskEngine 통합
- **llm/vector**: LLM adapters, embedding proxy/cache, qdrant

## Key paths

- `packages/codegraph-shared/codegraph_shared/infra/`

## Interfaces / I/O

- (각 컨텍스트가 참조하는 설정/스토리지/LLM 어댑터 인터페이스는 코드가 source of truth)

---

## Jobs: Indexing Pipeline Handlers

SemanticaTaskEngine과 통합된 병렬 인덱싱 파이프라인:

```
┌───────────┐     ┌─────────────┐
│ L1: IR    │     │ L3: Lexical │  ← 병렬 실행 (파일 경로만 필요)
└─────┬─────┘     └─────────────┘
      │
┌─────┴─────┐
│ L2: Chunk │  ← L1 완료 후 실행 (IR 필요)
└─────┬─────┘
      │
┌─────┴─────┐
│ L4: Vector│  ← L2 완료 후 실행 (Chunk 필요)
└───────────┘
```

### Job Types

| Job Type | Handler | 의존성 | 설명 |
|----------|---------|--------|------|
| `BUILD_IR` | `IRBuildHandler` | 없음 | LayeredIRBuilder로 IR 빌드 |
| `LEXICAL_INDEX` | `LexicalIndexHandler` | 없음 | Tantivy 렉시컬 인덱싱 |
| `BUILD_CHUNK` | `ChunkBuildHandler` | L1 | IR → Chunk 변환 |
| `VECTOR_INDEX` | `VectorIndexHandler` | L2 | Chunk → Vector 임베딩 |

### 중앙화된 설정 (IndexingConfig)

모든 매직넘버/하드코딩을 제거하고 `IndexingConfig`로 중앙화:

```python
from codegraph_shared.infra.jobs.handlers import (
    DEFAULT_CONFIG,
    IndexingConfig,
    ErrorCategory,
    ErrorCode,
    JobType,
    JobState,
)

# 설정 접근 예시
config = DEFAULT_CONFIG
config.defaults.parallel_workers  # 4
config.timeouts.pipeline  # 600초
config.batch.vector_batch_size  # 100
config.priority.ir_build  # 10
config.exclude_patterns.get_ir_excludes()  # ["venv", ".venv", ...]
config.cache_keys.make_ir_key("repo-123", "main")  # "ir:repo-123:main"
```

### Config 구조

| Config Class | 주요 설정 |
|--------------|----------|
| `DefaultValues` | `snapshot_id`, `semantic_tier`, `parallel_workers`, `file_patterns`, `embedding_model`, `db_path`, `tantivy_index_dir` |
| `TimeoutConfig` | `pipeline`, `ir_build`, `chunk_build`, `vector_index`, `lexical_index` |
| `BatchConfig` | `vector_batch_size`, `lexical_batch_size` |
| `JobPriority` | `ir_build`, `chunk_build`, `lexical_index`, `vector_index` |
| `ExcludePatterns` | `default`, `ir_build` + `get_ir_excludes()`, `get_lexical_excludes()` |
| `MetricsConfig` | `min_duration_epsilon` (division by zero 방지) |
| `LexicalConfig` | `indexing_mode`, `file_read_errors` |
| `IRBuildDefaults` | `occurrences`, `cross_file`, `retrieval_index` |
| `CacheKeyConfig` | `ir_prefix`, `chunk_prefix` + `make_ir_key()`, `make_chunk_key()` |

### 에러 분류 (Error Classification)

```python
class ErrorCategory(str, Enum):
    TRANSIENT = "TRANSIENT"      # 재시도 가능 (일시적 오류)
    PERMANENT = "PERMANENT"      # 재시도 불가 (영구적 오류)
    INFRASTRUCTURE = "INFRASTRUCTURE"  # 인프라 오류 (알림 필요)

class ErrorCode(str, Enum):
    # Common
    INVALID_PAYLOAD, PATH_NOT_FOUND, OUT_OF_MEMORY
    # IR Build
    IR_BUILD_ERROR, FILE_ACCESS_ERROR, PARSE_ERROR
    # Chunk Build
    CHUNK_BUILD_ERROR, IR_CACHE_MISS, DB_LOCKED, DB_ERROR
    # Lexical Index
    LEXICAL_INDEX_ERROR, INDEX_LOCKED, INDEX_CORRUPTED, IO_ERROR, DISK_FULL
    # Vector Index
    VECTOR_INDEX_ERROR, CHUNK_CACHE_MISS, RATE_LIMITED, NETWORK_ERROR, QDRANT_ERROR, INVALID_MODEL
```

### 사용 예시

```python
from codegraph_shared.infra.jobs.handlers import (
    ParallelIndexingOrchestrator,
    IRBuildHandler,
    DEFAULT_CONFIG,
)

# Orchestrator 사용
orchestrator = ParallelIndexingOrchestrator(adapter)
result = await orchestrator.index_repository(
    repo_path="/path/to/repo",
    repo_id="repo-123",
    snapshot_id="main",
    semantic_tier="FULL",
    skip_vector=False,
)

# 개별 Handler 사용
handler = IRBuildHandler(ir_cache={}, config=DEFAULT_CONFIG)
result = await handler.execute({
    "repo_path": "/path/to/repo",
    "repo_id": "repo-123",
    "semantic_tier": "FULL",
})
```

### 테스트

```bash
pytest tests/infra/jobs/handlers/ -v
```


