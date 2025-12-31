# Rust Engine API Reference

**Date**: 2025-12-28
**Status**: Production Ready
**Python Module**: `codegraph_ir`

---

## Overview

Rust Analysis Engine은 Python에 `codegraph_ir` 모듈로 노출됩니다.
모든 API는 PyO3를 통해 구현되며, msgpack 직렬화로 최적화되어 있습니다.

**핵심 원칙**:
- ✅ **Rust = Engine**: 모든 분석 로직
- ✅ **Python = Consumer**: Rust API 호출만
- ✅ **Zero-copy**: msgpack 기반 직렬화
- ✅ **GIL-free**: Rust 내부에서 병렬 처리

---

## Installation

```bash
# Maturin을 통한 설치 (개발)
cd packages/codegraph-rust/codegraph-ir
maturin develop --release

# pip를 통한 설치 (프로덕션)
pip install codegraph-ir
```

---

## API Categories

### 1. Full Repository Indexing

전체 레포지토리 분석 (L1-L8 Pipeline)

### 2. Incremental Indexing

파일 변경 추적 및 증분 업데이트 (MVCC)

### 3. Query & Search

Lexical, Semantic, Graph 검색

### 4. Advanced Analysis

Clone Detection, Taint Analysis, Effect Analysis

---

## 1. Full Repository Indexing

### IRIndexingOrchestrator

**Purpose**: 전체 레포지토리 분석 (L1-L8)

#### Python API

```python
from codegraph_ir import IRIndexingOrchestrator, E2EPipelineConfig

# Configuration
config = E2EPipelineConfig(
    root_path="/path/to/repo",
    parallel_workers=4,
    batch_size=100,
    enable_chunking=True,
    enable_cross_file=True,
    enable_flow=True,
    enable_types=True,
    enable_points_to=False,  # Heavy analysis
    enable_repomap=True,
    enable_effects=False,
    enable_taint=False,
)

# Execute
orchestrator = IRIndexingOrchestrator(config)
result = orchestrator.execute()

# Access results
print(f"Files processed: {result.stats.files_processed}")
print(f"Nodes: {len(result.nodes)}")
print(f"Edges: {len(result.edges)}")
print(f"Chunks: {len(result.chunks)}")
print(f"Duration: {result.stats.total_duration}s")
```

#### E2EPipelineConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `root_path` | `str` | **Required** | Repository root path |
| `parallel_workers` | `int` | `4` | Rayon parallel workers |
| `batch_size` | `int` | `100` | Batch processing size |
| `enable_chunking` | `bool` | `True` | L2: Code chunking |
| `enable_cross_file` | `bool` | `True` | L3: Cross-file resolution |
| `enable_flow` | `bool` | `True` | L4: CFG/DFG/BFG |
| `enable_types` | `bool` | `True` | L5: Type inference |
| `enable_points_to` | `bool` | `False` | L6: Points-to analysis (heavy) |
| `enable_repomap` | `bool` | `True` | L7: RepoMap (tree + PageRank) |
| `enable_effects` | `bool` | `False` | L8: Effect analysis |
| `enable_taint` | `bool` | `False` | L8: Taint analysis |

#### E2EPipelineResult

```python
@dataclass
class E2EPipelineResult:
    # Phase 1: IR (L1)
    nodes: list[Node]           # IR nodes
    edges: list[Edge]           # IR edges
    occurrences: list[Occurrence]  # SCIP occurrences

    # Phase 2: Indexing (L2-L5)
    chunks: list[Chunk]         # Code chunks (L2)
    symbols: list[Symbol]       # Symbols (L3)
    global_context: GlobalContextResult  # Cross-file (L3)

    # Phase 3: Advanced (L6-L8)
    points_to_summary: PointsToSummary | None  # L6
    repomap_snapshot: RepoMapSnapshot | None   # L7
    effects: list[EffectSummary]  # L8

    # Metrics
    stats: PipelineStats
```

#### PipelineStats

```python
@dataclass
class PipelineStats:
    files_processed: int
    total_loc: int
    total_duration: float  # seconds
    stage_durations: dict[str, float]  # {"L1": 1.2, "L2": 0.5, ...}
```

#### Example: Basic Usage

```python
import codegraph_ir

# Simple configuration
config = codegraph_ir.E2EPipelineConfig(
    root_path="/repo",
    enable_chunking=True,
    enable_repomap=True,
)

# Execute
orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
result = orchestrator.execute()

# Use results
for chunk in result.chunks:
    print(f"Chunk: {chunk.file_path}:{chunk.start_line}-{chunk.end_line}")

for node in result.nodes[:10]:
    print(f"Node: {node.kind} {node.name}")
```

#### Example: Advanced Analysis

```python
import codegraph_ir

# Enable all stages
config = codegraph_ir.E2EPipelineConfig(
    root_path="/repo",
    parallel_workers=8,
    enable_chunking=True,
    enable_cross_file=True,
    enable_flow=True,
    enable_types=True,
    enable_points_to=True,  # Heavy!
    enable_repomap=True,
    enable_effects=True,
    enable_taint=True,
)

orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
result = orchestrator.execute()

# Access advanced analysis
if result.points_to_summary:
    print(f"Alias sets: {len(result.points_to_summary.alias_sets)}")

if result.repomap_snapshot:
    print(f"Top modules: {result.repomap_snapshot.top_modules[:5]}")

print(f"Effects: {len(result.effects)}")
```

---

## 2. Incremental Indexing (MVCC)

### MultiLayerIndexOrchestrator

**Purpose**: 파일 변경 추적 및 증분 인덱스 업데이트

#### Python API

```python
from codegraph_ir import MultiLayerIndexOrchestrator, IndexOrchestratorConfig

# Configuration
config = IndexOrchestratorConfig(
    vector_skip_threshold=0.001,  # 0.1% 이하 변경 시 vector index 스킵
    full_rebuild_threshold=0.5,   # 50% 이상 변경 시 full rebuild
    max_commit_cost_ms=5000,      # 최대 commit 시간 (ms)
    parallel_updates=True,        # 인덱스 병렬 업데이트
)

# Initialize
orchestrator = MultiLayerIndexOrchestrator(config)

# Register indexes
from codegraph_ir import TantivyLexicalIndex

orchestrator.register_index(TantivyLexicalIndex(index_path="/index/lexical"))
# orchestrator.register_index(QdrantVectorIndex(...))
# orchestrator.register_index(ScipSymbolIndex(...))
```

#### MVCC Workflow

```python
# 1. Begin session (agent starts editing)
session = orchestrator.begin_session("agent_1")
print(f"Session TxnId: {session.txn_id}")

# 2. Add changes
orchestrator.add_change("agent_1", {
    "op": "add_node",
    "node": {
        "id": "node_123",
        "kind": "Function",
        "name": "my_function",
        # ... other fields
    }
})

orchestrator.add_change("agent_1", {
    "op": "update_node",
    "node": {
        "id": "node_456",
        "name": "updated_name",
    }
})

orchestrator.add_change("agent_1", {
    "op": "delete_node",
    "node_id": "node_789",
})

# 3. Commit (all indexes updated automatically)
result = orchestrator.commit("agent_1")

print(f"Success: {result.success}")
print(f"Committed TxnId: {result.committed_txn}")
print(f"Conflicts: {result.conflicts}")
print(f"Index updates: {result.index_updates}")
```

#### IndexOrchestratorConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `vector_skip_threshold` | `float` | `0.001` | Vector index skip threshold (0.1%) |
| `full_rebuild_threshold` | `float` | `0.5` | Full rebuild threshold (50%) |
| `max_commit_cost_ms` | `int` | `5000` | Max commit time (ms) |
| `parallel_updates` | `bool` | `True` | Parallel index updates |
| `lazy_rebuild_enabled` | `bool` | `False` | Lazy rebuild strategy |

#### CommitResult

```python
@dataclass
class CommitResult:
    success: bool
    committed_txn: int  # TxnId
    conflicts: list[str]  # Conflicting changes
    delta: TransactionDelta
    index_updates: dict[str, IndexUpdateResult]  # {index_type: result}
```

#### Example: Multi-Agent Concurrent Editing

```python
import codegraph_ir

orchestrator = codegraph_ir.MultiLayerIndexOrchestrator(config)

# Agent A: Edits file1.py
session_a = orchestrator.begin_session("agent_a")
orchestrator.add_change("agent_a", {"op": "update_node", "node": {...}})

# Agent B: Edits file2.py (concurrent)
session_b = orchestrator.begin_session("agent_b")
orchestrator.add_change("agent_b", {"op": "update_node", "node": {...}})

# Both commit - MVCC handles conflicts
result_a = orchestrator.commit("agent_a")  # TxnId: 101
result_b = orchestrator.commit("agent_b")  # TxnId: 102

print(f"Agent A committed: {result_a.success}")
print(f"Agent B committed: {result_b.success}")
```

---

## 3. Query & Search

### QueryEngine

**Purpose**: Lexical, Semantic, Graph 검색

#### Python API

```python
from codegraph_ir import QueryEngine

# Initialize
engine = QueryEngine(index_path="/path/to/index")

# Lexical search (Tantivy)
results = engine.lexical_search(
    query="function",
    limit=10,
    offset=0,
)

for result in results:
    print(f"Match: {result.file_path}:{result.line}")
    print(f"Score: {result.score}")
    print(f"Context: {result.context}")

# Semantic search (Graph)
results = engine.semantic_search(
    embedding=[0.1, 0.2, 0.3, ...],  # 384-dim vector
    limit=10,
)

# Graph query
results = engine.graph_query(
    query={
        "type": "find_callers",
        "target": "my_function",
    }
)
```

#### QueryEngine Methods

| Method | Description | Return Type |
|--------|-------------|-------------|
| `lexical_search(query, limit, offset)` | Full-text search | `list[SearchResult]` |
| `semantic_search(embedding, limit)` | Vector similarity search | `list[SearchResult]` |
| `graph_query(query)` | Graph traversal | `list[GraphNode]` |

#### SearchResult

```python
@dataclass
class SearchResult:
    file_path: str
    line: int
    column: int
    score: float
    context: str  # Surrounding code
    metadata: dict
```

---

## 4. Advanced Analysis

### Clone Detection

```python
from codegraph_ir import CloneDetector, CloneDetectorConfig

# Configuration
config = CloneDetectorConfig(
    min_lines=5,
    min_tokens=20,
    similarity_threshold=0.8,
    enable_type1=True,  # Exact clones
    enable_type2=True,  # Renamed clones
    enable_type3=True,  # Structural clones
)

detector = CloneDetector(config)

# Detect clones
clones = detector.detect_clones(
    nodes=result.nodes,
    edges=result.edges,
)

for clone in clones:
    print(f"Clone Type: {clone.clone_type}")
    print(f"Similarity: {clone.similarity}")
    print(f"Locations: {clone.locations}")
```

### Taint Analysis

```python
from codegraph_ir import TaintAnalyzer

analyzer = TaintAnalyzer()

# Analyze taint flow
taint_results = analyzer.analyze(
    nodes=result.nodes,
    edges=result.edges,
    sources=["request.GET", "request.POST"],
    sinks=["eval", "exec", "os.system"],
)

for taint in taint_results:
    print(f"Source: {taint.source}")
    print(f"Sink: {taint.sink}")
    print(f"Path: {taint.path}")
```

---

## Data Models

### Node

```python
@dataclass
class Node:
    id: str
    kind: str  # "Function", "Class", "Variable", etc.
    name: str
    file_path: str
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    attributes: dict  # Language-specific attributes
    metadata: dict
```

### Edge

```python
@dataclass
class Edge:
    id: str
    kind: str  # "Call", "Inherit", "Import", "DataFlow", etc.
    source_id: str
    target_id: str
    attributes: dict
    metadata: dict
```

### Chunk

```python
@dataclass
class Chunk:
    id: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str
    chunk_type: str  # "Function", "Class", "Module"
    symbols: list[str]  # Referenced symbols
    metadata: dict
```

---

## Performance Characteristics

### IRIndexingOrchestrator

| Stage | Throughput | Notes |
|-------|------------|-------|
| L1 (IR Build) | 1000+ files/s | Rayon parallel |
| L2 (Chunking) | 600 files/s | Rayon parallel |
| L3 (Cross-File) | 12x faster | vs Python |
| L6 (Points-To) | 10-50x faster | vs Python |
| L7 (RepoMap) | Parallel | Tree + PageRank |

### MultiLayerIndexOrchestrator

| Operation | Latency | Notes |
|-----------|---------|-------|
| `begin_session` | <1ms | Lock-free snapshot |
| `add_change` | <0.1ms | In-memory append |
| `commit` (small) | 50-300ms | Delta update (3 indexes) |
| `commit` (large) | 2-10s | Full rebuild if >50% |
| `query` | 1-5ms | Index-specific |

---

## Error Handling

All Rust errors are converted to Python exceptions:

```python
from codegraph_ir import CodegraphError

try:
    result = orchestrator.execute()
except CodegraphError as e:
    print(f"Error: {e}")
    print(f"Code: {e.error_code}")
    print(f"Category: {e.error_category}")
```

### Error Categories

- `TRANSIENT`: Retriable (network, file lock, etc.)
- `PERMANENT`: Not retriable (invalid input, etc.)
- `INFRASTRUCTURE`: System issues (memory, disk, etc.)

---

## Best Practices

### 1. Use Appropriate Pipeline

```python
# ✅ Full repository indexing
orchestrator = IRIndexingOrchestrator(config)
result = orchestrator.execute()

# ✅ Incremental updates
multi_idx = MultiLayerIndexOrchestrator(config)
multi_idx.begin_session("agent")
multi_idx.commit("agent")

# ❌ Don't use full indexing for incremental updates
# (slow and wasteful)
```

### 2. Configure Parallel Workers

```python
import os

# Set based on CPU cores
num_cores = os.cpu_count()

config = E2EPipelineConfig(
    root_path="/repo",
    parallel_workers=num_cores - 1,  # Leave 1 core for OS
)
```

### 3. Enable Only Required Stages

```python
# ✅ For chunking only
config = E2EPipelineConfig(
    root_path="/repo",
    enable_chunking=True,
    enable_cross_file=False,  # Disable heavy stages
    enable_points_to=False,
    enable_effects=False,
)

# ❌ Don't enable all stages unnecessarily
# (slow and memory-intensive)
```

### 4. Reuse Orchestrators

```python
# ✅ Create once, reuse
orchestrator = IRIndexingOrchestrator(config)

for repo_path in repos:
    config.root_path = repo_path
    result = orchestrator.execute()

# ❌ Don't create new orchestrator for each repo
# (initialization overhead)
```

---

## Migration from Python

### Before (Python LayeredIRBuilder)

```python
from codegraph_engine.infrastructure.ir.layered_ir_builder import LayeredIRBuilder
from codegraph_engine.infrastructure.ir.build_config import BuildConfig

config = BuildConfig(
    semantic_tier=SemanticTier.FULL,
    enable_cross_file=True,
)

builder = LayeredIRBuilder(config)
result = await builder.build_all(repo_path)
```

### After (Rust Engine)

```python
import codegraph_ir

config = codegraph_ir.E2EPipelineConfig(
    root_path=repo_path,
    enable_chunking=True,
    enable_cross_file=True,
)

orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
result = orchestrator.execute()  # Sync, no await needed
```

---

## Examples

See full examples in:
- [packages/codegraph-rust/codegraph-ir/examples/](../../packages/codegraph-rust/codegraph-ir/examples/)
- [packages/codegraph-rust/codegraph-ir/tests/python/](../../packages/codegraph-rust/codegraph-ir/tests/python/)

---

## References

- [RUST_INTEGRATED_ARCHITECTURE.md](../../packages/codegraph-rust/docs/RUST_INTEGRATED_ARCHITECTURE.md)
- [ADR-072: Clean Rust-Python Architecture](../adr/ADR-072-clean-rust-python-architecture.md)
- [PyO3 Documentation](https://pyo3.rs/)

---

**Last Updated**: 2025-12-28
**Status**: Production Ready
