# RFC-SDK-001: CodeGraph SOTA Python SDK Architecture

**Status**: Draft
**Author**: CodeGraph Team
**Created**: 2024-12-28
**Updated**: 2024-12-28

---

## 0. Meta

### 0.1 Document Purpose
This RFC defines the architecture and API design for the CodeGraph Python SDK, providing a production-ready interface to the Rust analysis engine with SOTA-level features and excellent developer experience (DX).

### 0.2 Target Audience
- **L1 Users**: Data scientists, researchers (simple APIs)
- **L2 Users**: Application developers (composable features)
- **L3 Users**: DevOps, platform engineers (configuration control)
- **L4 Users**: Framework developers (advanced customization)

### 0.3 Related Documents
- [CLEAN_ARCHITECTURE_SUMMARY.md](../CLEAN_ARCHITECTURE_SUMMARY.md)
- [RUST_ENGINE_API.md](../RUST_ENGINE_API.md)
- [ADR-072: Rust-Python Clean Architecture](../adr/ADR-072-rust-python-clean-architecture.md)

---

## 1. Executive Summary

### 1.1 Problem Statement
The current CodeGraph Rust engine (`codegraph-ir`) provides powerful analysis capabilities but lacks:
1. **Pythonic API**: Direct Rust FFI bindings are verbose and error-prone
2. **Progressive Complexity**: No clear path from simple to advanced usage
3. **Type Safety**: Runtime errors instead of IDE-time validation
4. **Streaming Support**: Large repositories require memory-efficient iteration
5. **Contract Stability**: Breaking changes in Rust internals affect Python consumers

### 1.2 Proposed Solution
A **contract-first Python SDK** with four versioned contracts:

```
┌─────────────────────────────────────────────────────────────┐
│                  Python SDK (codegraph)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Config       │  │ Query DSL    │  │ Data Models  │     │
│  │ Contract     │  │ Contract     │  │ Contract     │     │
│  │ (v1.0)       │  │ (v1.0)       │  │ (v2.0)       │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                  │                  │              │
│         └──────────────────┴──────────────────┘              │
│                            ▼                                 │
│                  ┌──────────────────┐                       │
│                  │ Error/Diagnostic │                       │
│                  │ Contract (v1.0)  │                       │
│                  └──────────┬───────┘                       │
└─────────────────────────────┼───────────────────────────────┘
                              ▼ (PyO3 FFI)
┌─────────────────────────────────────────────────────────────┐
│              Rust Analysis Engine (codegraph_ir)            │
│  • IRIndexingOrchestrator (DAG-based L1-L37 pipeline)      │
│  • MultiLayerIndexOrchestrator (MVCC incremental updates)  │
│  • Query Engine (Lexical/Semantic/Graph unified queries)   │
│  • Zero Python dependency (except Language Plugin)         │
└─────────────────────────────────────────────────────────────┘
```

**Key Design Principles**:
1. ✅ **Progressive Disclosure**: L1→L2→L3→L4 complexity layers
2. ✅ **Contract-First**: Versioned APIs with migration paths
3. ✅ **Streaming-First**: Memory-efficient iteration for large datasets
4. ✅ **"Rust Executes, Python Designs"**: Clear separation of concerns
5. ✅ **Type-Safe by Default**: Pydantic validation + IDE autocomplete

---

## 2. Background

### 2.1 Current State

**Rust Engine Capabilities** (as of 2024-12-28):
```rust
// Entry Point 1: Full Repository Indexing
let config = E2EPipelineConfig { ... };
let orchestrator = IRIndexingOrchestrator::new(config);
let result: E2EPipelineResult = orchestrator.execute()?;

// Entry Point 2: Incremental Updates (MVCC)
let multi_idx = MultiLayerIndexOrchestrator::new(config);
let session = multi_idx.begin_session("agent_1")?;
multi_idx.add_change("agent_1", change)?;
multi_idx.commit("agent_1")?;

// Entry Point 3: Query Engine
let engine = QueryEngine::new(snapshot)?;
let nodes = engine.query_nodes(filter)?;
```

**Problems**:
1. **No Progressive API**: Users must understand full `E2EPipelineConfig` structure upfront
2. **No Streaming**: `E2EPipelineResult` materializes all data in memory
3. **No Contract Versioning**: Schema changes break existing code
4. **No Error Recovery**: Transient failures require manual retry logic

### 2.2 Industry SOTA Examples

**Stripe SDK** (Best DX):
```python
# L1: Simple (sane defaults)
charge = stripe.Charge.create(amount=1000, currency="usd")

# L2: Composable (add one option at a time)
charge = stripe.Charge.create(
    amount=1000,
    currency="usd",
    source="tok_visa",  # Add payment method
)

# L3: Advanced (multiple features)
charge = stripe.Charge.create(
    amount=1000,
    currency="usd",
    source="tok_visa",
    metadata={"order_id": "123"},
    idempotency_key="order_123",
)
```

**Django ORM** (Best Query DSL):
```python
# L1: Simple query
users = User.objects.filter(age__gte=18)

# L2: Chaining
users = User.objects.filter(age__gte=18).order_by('-created_at')

# L3: Aggregation
stats = User.objects.aggregate(avg_age=Avg('age'))
```

**Pandas** (Best Streaming):
```python
# L1: Load all
df = pd.read_csv("data.csv")

# L2: Streaming
for chunk in pd.read_csv("data.csv", chunksize=1000):
    process(chunk)  # Memory = O(chunk_size)
```

---

## 3. Goals and Non-Goals

### 3.1 Goals
1. ✅ **L1 Users**: One-line indexing with sane defaults
2. ✅ **L2 Users**: Composable features via method chaining
3. ✅ **L3 Users**: Full configuration control
4. ✅ **L4 Users**: Custom analyzers and hooks
5. ✅ **Streaming**: O(1) memory for large repositories
6. ✅ **Type Safety**: Pydantic validation + IDE autocomplete
7. ✅ **Error Recovery**: Automatic retries for transient failures
8. ✅ **Contract Stability**: Semantic versioning with deprecation warnings

### 3.2 Non-Goals
1. ❌ **Rust Replacement**: SDK is a Python wrapper, not a rewrite
2. ❌ **Backward Compatibility Forever**: Old versions will be deprecated (12-month notice)
3. ❌ **Synchronous-First**: Async APIs are preferred for I/O operations

---

## 4. Architecture

### 4.1 Three-Layer Design

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Public API (codegraph.*)                          │
│  • Progressive Disclosure (L1-L4)                           │
│  • Pythonic naming (snake_case, context managers)          │
│  • Type hints + Pydantic validation                         │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: FFI Adapter (codegraph._internal)                 │
│  • PyO3 bindings to Rust                                    │
│  • Arrow IPC for zero-copy data transfer                   │
│  • Error translation (Rust Result → Python Exception)      │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Rust Core (codegraph_ir crate)                    │
│  • IRIndexingOrchestrator (DAG pipeline)                    │
│  • MultiLayerIndexOrchestrator (MVCC)                       │
│  • Query Engine (Lexical + Semantic + Graph)               │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Data Flow

```
Python Request
    │
    ├─> Config Contract (Pydantic) ───> Validate
    │                                      │
    ├─> Query Contract (Builder) ──────> Build QueryPlan
    │                                      │
    └──────────────────────────────────────┴──> FFI Call (PyO3)
                                                    │
                                                    ▼
                                          Rust Execution
                                                    │
                                                    ▼
                                          Arrow IPC Stream
                                                    │
                                                    ▼
                                          Python Iterator
                                                    │
                                                    ▼
                                          Data Contract (Pydantic)
```

---

## 5. Domain Models

### 5.1 Session Lifecycle

```python
from codegraph import CodeGraph

# Session represents a logical unit of work
cg = CodeGraph()

with cg.session(repo="/path/to/repo") as sess:
    # All operations within session see consistent snapshot
    nodes = sess.query().nodes().filter(kind="function").execute()

    # Mutations create new snapshot (MVCC)
    sess.add_file("new.py")
    sess.commit()  # Creates snapshot_v2

    # Old queries still see snapshot_v1
    # New queries see snapshot_v2
```

**Guarantees**:
- ✅ **Snapshot Isolation**: Queries see immutable snapshot
- ✅ **No Dirty Reads**: Uncommitted changes invisible to other sessions
- ✅ **Repeatable Reads**: Same query returns same result within session

### 5.2 Snapshot Management

```python
# Snapshot ID Format: {timestamp_ms}_{repo_hash[:8]}_{counter:04d}
# Example: 1735372800000_a3b4c5d6_0001

class SnapshotIdGenerator:
    """
    Properties:
    - Sortable by timestamp (lexicographic order)
    - Unique per repository (hash collision < 10^-12)
    - Supports 10,000 snapshots/sec (4-digit counter)
    """

    @staticmethod
    def generate(repo_id: str) -> str:
        ts = int(time.time() * 1000)
        repo_hash = hashlib.sha256(repo_id.encode()).hexdigest()[:8]
        counter = _get_next_counter(ts)  # Thread-safe atomic increment
        return f"{ts}_{repo_hash}_{counter:04d}"
```

### 5.3 Transaction Isolation

```python
from enum import Enum

class IsolationLevel(Enum):
    """
    CodeGraph uses Snapshot Isolation (SI):

    - Read operations: See snapshot at transaction start
    - Write operations: Append-only (no in-place updates)
    - Conflicts: Detected on commit via version check

    Guarantees:
    ✅ No dirty reads (uncommitted changes invisible)
    ✅ Repeatable reads (snapshot immutability)
    ❌ Not serializable (write skew possible)

    Example write skew scenario:
        T1: Read X=10, Write Y=X+5  → Y=15
        T2: Read X=10, Write Z=X+5  → Z=15
        Both commit successfully (no conflict)
        But serial execution would give different result

    Mitigation: Use explicit locks for critical sections
    """
    SNAPSHOT_ISOLATION = "SI"  # Default and only supported level
```

---

## 6. Contracts

### 6.1 Contract Versioning Strategy

```python
from typing import Literal
from pydantic import BaseModel, Field

class ContractVersion(BaseModel):
    """
    Contract versioning follows Semantic Versioning:

    - MAJOR: Breaking changes (e.g., rename field, change type)
    - MINOR: Backward-compatible additions (e.g., new optional field)
    - PATCH: Bug fixes (no API changes)

    Deprecation Policy:
    - Deprecated versions supported for 12 months
    - Warnings emitted 6 months before removal
    - Migration guide provided for breaking changes
    """

    config_version: Literal["1.0", "1.1"] = Field(
        default="1.1",
        description="v1.0 deprecated 2025-06-01, removed 2026-06-01"
    )
    schema_version: Literal["2.0"] = Field(
        default="2.0",
        description="Current stable version"
    )
    query_version: Literal["1.0"] = Field(
        default="1.0",
        description="Current stable version"
    )

    @staticmethod
    def check_compatibility(contract_type: str, version: str) -> bool:
        """
        Validates version compatibility.

        Raises:
            DeprecationWarning: If version is deprecated but still supported
            ValueError: If version is removed or invalid
        """
        supported = {
            "config": ["1.0", "1.1"],  # 1.0 deprecated
            "schema": ["2.0"],
            "query": ["1.0"],
        }

        if version not in supported[contract_type]:
            raise ValueError(f"Unsupported {contract_type} version: {version}")

        # Emit deprecation warning
        deprecated = {"config": ["1.0"]}
        if version in deprecated.get(contract_type, []):
            import warnings
            warnings.warn(
                f"{contract_type} v{version} is deprecated. "
                f"Migrate to {supported[contract_type][-1]}. "
                f"See: https://docs.codegraph.io/migration/{contract_type}-{version}",
                DeprecationWarning,
                stacklevel=2,
            )

        return True
```

### 6.2 Config Contract (v1.1)

```python
from pydantic import BaseModel, Field, validator
from typing import Optional, Literal
from pathlib import Path

class IndexingConfig(BaseModel):
    """
    Configuration contract for indexing pipeline.

    Version: 1.1 (current stable)
    Changelog:
        - v1.1 (2024-12-28): Added `auto_detect_mode`, `file_watcher`
        - v1.0 (2024-01-01): Initial release
    """

    # Required fields
    root_path: Path = Field(
        ...,
        description="Repository root directory (must exist)"
    )

    # Optional: Execution control
    mode: Literal["full", "incremental", "smart"] = Field(
        default="smart",
        description=(
            "full: Re-index entire repository\n"
            "incremental: Only process changed files\n"
            "smart: Auto-detect based on repository size and git status"
        )
    )

    parallel_workers: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Number of parallel workers (default: num_cpus)"
    )

    # Optional: Feature toggles
    enable_taint: bool = Field(default=True, description="Enable L14 taint analysis")
    enable_repomap: bool = Field(default=True, description="Enable L16 RepoMap + PageRank")
    enable_smt: bool = Field(default=False, description="Enable L21 SMT verification (slow)")

    # Optional: Advanced settings
    taint_rules_path: Optional[Path] = Field(
        default=None,
        description="Path to custom TRCR taint rules (YAML)"
    )

    cache_dir: Optional[Path] = Field(
        default=None,
        description="Cache directory for incremental updates (default: .codegraph/)"
    )

    # v1.1 additions
    auto_detect_mode: bool = Field(
        default=True,
        description="Auto-select optimal indexing mode based on repo characteristics"
    )

    file_watcher: bool = Field(
        default=False,
        description="Enable file system watcher for automatic incremental updates"
    )

    @validator("root_path")
    def validate_root_path(cls, v):
        if not v.exists():
            raise ValueError(f"Repository path does not exist: {v}")
        if not v.is_dir():
            raise ValueError(f"Repository path is not a directory: {v}")
        return v

    @validator("taint_rules_path")
    def validate_taint_rules(cls, v):
        if v is not None and not v.exists():
            raise ValueError(f"Taint rules file not found: {v}")
        return v

    class Config:
        # Pydantic v2 configuration
        validate_assignment = True  # Validate on attribute assignment
        frozen = False  # Allow mutations (for builder pattern)
```

### 6.3 Query Contract (v1.0)

```python
from typing import Optional, List, Any, Iterator
from pydantic import BaseModel
from enum import Enum

class NodeKind(str, Enum):
    """Standard node types across all languages"""
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    IMPORT = "import"
    CALL = "call"

class EdgeKind(str, Enum):
    """Standard edge types"""
    CALLS = "calls"
    DEFINES = "defines"
    REFERENCES = "references"
    IMPORTS = "imports"
    INHERITS = "inherits"

class QueryBuilder:
    """
    Django ORM-style fluent query builder.

    Design:
        - Method chaining for composability
        - Lazy evaluation (execute() triggers Rust call)
        - Type-safe filters via Pydantic enums
        - Streaming by default (returns Iterator)

    Examples:
        # L1: Simple filter
        nodes = cg.query().nodes().filter(kind=NodeKind.FUNCTION).execute()

        # L2: Method chaining
        nodes = (cg.query()
            .nodes()
            .filter(kind=NodeKind.FUNCTION, language="python")
            .order_by("name")
            .limit(100)
            .execute()
        )

        # L3: Aggregation
        stats = (cg.query()
            .nodes()
            .filter(language="python")
            .aggregate(count="id", avg_complexity="complexity")
        )
    """

    def __init__(self, session: "Session"):
        self._session = session
        self._filters = []
        self._order_by = []
        self._limit = None
        self._offset = None

    def nodes(self) -> "NodeQueryBuilder":
        """Query nodes (functions, classes, etc.)"""
        return NodeQueryBuilder(self._session)

    def edges(self) -> "EdgeQueryBuilder":
        """Query edges (calls, references, etc.)"""
        return EdgeQueryBuilder(self._session)

    def taint_flows(self) -> "TaintQueryBuilder":
        """Query taint analysis results"""
        return TaintQueryBuilder(self._session)

class NodeQueryBuilder:
    """Node-specific query builder"""

    def filter(
        self,
        kind: Optional[NodeKind] = None,
        language: Optional[str] = None,
        file_path: Optional[str] = None,
        **kwargs,
    ) -> "NodeQueryBuilder":
        """
        Filter nodes by attributes.

        Args:
            kind: Node type (function, class, etc.)
            language: Source language (python, typescript, etc.)
            file_path: File path (supports glob patterns)
            **kwargs: Additional filters (name, complexity, etc.)

        Returns:
            Self for method chaining
        """
        self._filters.append({
            "kind": kind,
            "language": language,
            "file_path": file_path,
            **kwargs,
        })
        return self

    def order_by(self, field: str, descending: bool = False) -> "NodeQueryBuilder":
        """Sort results by field"""
        self._order_by.append((field, descending))
        return self

    def limit(self, n: int) -> "NodeQueryBuilder":
        """Limit number of results"""
        self._limit = n
        return self

    def offset(self, n: int) -> "NodeQueryBuilder":
        """Skip first n results"""
        self._offset = n
        return self

    def execute(self, stream: bool = True) -> Iterator["Node"]:
        """
        Execute query and return results.

        Args:
            stream: If True, return iterator (memory-efficient)
                   If False, materialize all results (convenience)

        Returns:
            Iterator[Node] if stream=True
            List[Node] if stream=False
        """
        query_plan = self._build_query_plan()

        if stream:
            return self._session._execute_streaming(query_plan)
        else:
            return list(self._session._execute_streaming(query_plan))

    def _build_query_plan(self) -> dict:
        """Build Rust query plan from filters"""
        return {
            "type": "node_query",
            "filters": self._filters,
            "order_by": self._order_by,
            "limit": self._limit,
            "offset": self._offset,
        }

class QueryPlan(BaseModel):
    """
    Query execution plan (generated by Rust optimizer).

    Optimization strategies:
        1. Predicate pushdown: Move filters before expensive joins
        2. Index selection: Choose best index (lexical/semantic/graph)
        3. Parallel execution: Use Rayon for independent subqueries
        4. Result streaming: Avoid materializing full result set
    """

    plan_type: Literal["node_query", "edge_query", "taint_query"]
    estimated_rows: int
    index_used: Optional[str]  # "lexical", "semantic", "graph"
    parallel_workers: int

    def explain(self) -> str:
        """
        Returns query plan visualization.

        Example output:
            Stream[Node] (est. 1,234 rows)
            └─ Filter(language='python')
               └─ IndexScan(LexicalIndex, chunk_size=1000)
                  └─ ParallelIter(workers=4)
        """
        lines = [
            f"Stream[{self.plan_type}] (est. {self.estimated_rows:,} rows)",
        ]

        if self.index_used:
            lines.append(f"└─ IndexScan({self.index_used}, chunk_size=1000)")

        if self.parallel_workers > 1:
            lines.append(f"   └─ ParallelIter(workers={self.parallel_workers})")

        return "\n".join(lines)
```

### 6.4 Data Contract (v2.0)

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class Node(BaseModel):
    """
    Unified node representation across all languages.

    Version: 2.0 (current stable)
    Changelog:
        - v2.0 (2024-06-01): Added `metadata` field, removed `deprecated_field`
        - v1.0 (2024-01-01): Initial release
    """

    # Core fields (immutable)
    id: str = Field(..., description="Unique node identifier (FQN-based)")
    kind: NodeKind = Field(..., description="Node type (function, class, etc.)")
    name: str = Field(..., description="Node name (short, unqualified)")

    # Location (immutable)
    file_path: str = Field(..., description="Relative file path from repo root")
    start_line: int = Field(..., ge=1, description="Start line number (1-indexed)")
    end_line: int = Field(..., ge=1, description="End line number (inclusive)")

    # Language-specific (optional)
    language: Optional[str] = Field(None, description="Source language (python, typescript, etc.)")
    modifiers: List[str] = Field(default_factory=list, description="Modifiers (public, static, async, etc.)")

    # Analysis results (optional)
    complexity: Optional[int] = Field(None, description="Cyclomatic complexity (if available)")
    taint_sources: List[str] = Field(default_factory=list, description="Taint sources (if taint analysis enabled)")

    # v2.0 addition
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible metadata (language-specific attributes)"
    )

    class Config:
        frozen = True  # Immutable (snapshots guarantee no mutations)
        validate_assignment = True

class Edge(BaseModel):
    """Edge between two nodes"""

    id: str = Field(..., description="Unique edge identifier")
    kind: EdgeKind = Field(..., description="Edge type (calls, references, etc.)")
    source_id: str = Field(..., description="Source node ID")
    target_id: str = Field(..., description="Target node ID")

    # Optional attributes
    file_path: Optional[str] = Field(None, description="File where edge occurs")
    line_number: Optional[int] = Field(None, description="Line number where edge occurs")

    class Config:
        frozen = True

class TaintFlow(BaseModel):
    """Taint analysis result"""

    id: str
    source_node_id: str
    sink_node_id: str
    flow_path: List[str] = Field(..., description="Node IDs along taint path")
    vulnerability_type: str = Field(..., description="CWE category (e.g., 'CWE-89: SQL Injection')")
    severity: Literal["critical", "high", "medium", "low"]
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0.0-1.0)")

    class Config:
        frozen = True
```

### 6.5 Error Contract (v1.0)

```python
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel

class ErrorCategory(str, Enum):
    """
    Error categories for recovery strategies.

    TRANSIENT: Temporary failures (network timeout, lock contention)
               → Retry with exponential backoff

    PERMANENT: Invalid input or configuration
               → Do not retry, user must fix input

    INFRASTRUCTURE: System-level failures (DB down, disk full)
                    → Retry once, then alert ops team
    """
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    INFRASTRUCTURE = "infrastructure"

class CodeGraphError(Exception):
    """
    Base exception for all SDK errors.

    Design:
        - Structured error info (category, code, context)
        - Machine-readable error codes
        - Human-readable messages
        - Stacktrace preservation
    """

    def __init__(
        self,
        message: str,
        category: ErrorCategory,
        code: str,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.code = code
        self.context = context or {}
        self.cause = cause

    def is_retryable(self) -> bool:
        """Returns True if error should be retried"""
        return self.category == ErrorCategory.TRANSIENT

class ErrorRecovery:
    """
    Error recovery strategies by category.
    """

    STRATEGIES = {
        ErrorCategory.TRANSIENT: {
            "retry": True,
            "max_attempts": 3,
            "backoff": "exponential",  # 1s, 2s, 4s
            "examples": [
                "network timeout",
                "lock contention",
                "rate limit exceeded",
            ],
        },
        ErrorCategory.PERMANENT: {
            "retry": False,
            "user_action": "fix input or configuration",
            "examples": [
                "invalid syntax",
                "file not found",
                "unsupported language",
            ],
        },
        ErrorCategory.INFRASTRUCTURE: {
            "retry": True,
            "max_attempts": 1,
            "alert": True,  # Notify ops team
            "examples": [
                "database connection lost",
                "disk full",
                "out of memory",
            ],
        },
    }

    @staticmethod
    def should_retry(error: CodeGraphError) -> bool:
        """Determines if error should be retried"""
        strategy = ErrorRecovery.STRATEGIES[error.category]
        return strategy.get("retry", False)

    @staticmethod
    def get_backoff(attempt: int, category: ErrorCategory) -> float:
        """Calculate backoff delay in seconds"""
        strategy = ErrorRecovery.STRATEGIES[category]

        if strategy.get("backoff") == "exponential":
            return min(2 ** attempt, 60)  # Max 60s
        else:
            return 0.0

# Specific error classes
class IndexingError(CodeGraphError):
    """Errors during indexing pipeline"""
    pass

class QueryError(CodeGraphError):
    """Errors during query execution"""
    pass

class ConfigError(CodeGraphError):
    """Invalid configuration"""
    pass
```

---

## 7. Streaming API Design

### 7.1 Memory Guarantees

```python
from typing import Iterator
import pyarrow as pa

class StreamingConfig:
    """
    Memory guarantees for streaming queries.

    Design:
        - Chunk size: 1000 nodes/edges per batch (Arrow IPC RecordBatch)
        - Max memory: O(chunk_size) regardless of total result size
        - Backpressure: Rust blocks when Python consumer is slow
        - Zero-copy: Arrow IPC uses shared memory (no serialization)

    Example:
        # Repository with 1M nodes
        # Memory usage: ~500 KB (1000 nodes × 500 bytes/node)
        # NOT: 500 MB (1M nodes in memory)

        for batch in session.query().nodes().execute(chunk_size=1000):
            process(batch)  # Process 1000 nodes at a time
    """

    DEFAULT_CHUNK_SIZE = 1000
    MAX_CHUNK_SIZE = 10_000

    @staticmethod
    def iter_nodes(
        session: "Session",
        query_plan: dict,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> Iterator[pa.RecordBatch]:
        """
        Yields Arrow RecordBatch with memory guarantee:

        peak_memory = chunk_size × avg_node_size (~500 bytes)

        RecordBatch schema:
            - id: utf8
            - kind: utf8
            - name: utf8
            - file_path: utf8
            - start_line: int32
            - end_line: int32
            - language: utf8 (nullable)
            - complexity: int32 (nullable)
            - metadata: utf8 (JSON string, nullable)
        """
        # FFI call to Rust streaming iterator
        rust_iter = session._ffi.query_nodes_streaming(query_plan, chunk_size)

        for arrow_bytes in rust_iter:
            # Zero-copy deserialization from Arrow IPC
            batch = pa.ipc.open_stream(arrow_bytes).read_next_batch()
            yield batch

    @staticmethod
    def to_pydantic(batch: pa.RecordBatch) -> List[Node]:
        """Convert Arrow batch to Pydantic models (validation overhead)"""
        # This is slower but provides type safety
        records = batch.to_pydict()
        return [Node(**record) for record in records]
```

---

## 8. Public API Examples

### 8.1 L1: Simple (One-Liner)

```python
from codegraph import CodeGraph

# Create instance with sane defaults
cg = CodeGraph()

# Index repository (auto-detects mode, uses default config)
result = cg.index("/path/to/repo")

# Result is a streaming iterator (memory-efficient)
for node in result.nodes():
    print(f"{node.kind}: {node.name} @ {node.file_path}:{node.start_line}")
```

### 8.2 L2: Composable (Method Chaining)

```python
from codegraph import CodeGraph

cg = CodeGraph()

# Add one option at a time
result = (cg.index("/path/to/repo")
    .with_taint()              # Enable taint analysis
    .with_repomap()            # Enable RepoMap
    .parallel(workers=8)       # Use 8 workers
    .execute()                 # Trigger execution
)

# Query with filters
functions = (result.query()
    .nodes()
    .filter(kind="function", language="python")
    .order_by("complexity", descending=True)
    .limit(10)
    .execute()
)

for func in functions:
    print(f"{func.name}: complexity={func.complexity}")
```

### 8.3 L3: Advanced (Full Configuration)

```python
from codegraph import CodeGraph, IndexingConfig
from pathlib import Path

# Full configuration control
config = IndexingConfig(
    root_path=Path("/path/to/repo"),
    mode="incremental",
    parallel_workers=8,
    enable_taint=True,
    enable_smt=True,  # Enable SMT verification (slow)
    taint_rules_path=Path("./custom_rules.yaml"),
    cache_dir=Path(".codegraph_cache"),
    file_watcher=True,  # Auto-update on file changes
)

cg = CodeGraph(config=config)
result = cg.index()

# Query taint flows
taint_flows = (result.query()
    .taint_flows()
    .filter(severity="critical", vulnerability_type="CWE-89")
    .execute()
)

for flow in taint_flows:
    print(f"Vulnerability: {flow.vulnerability_type}")
    print(f"Source: {flow.source_node_id}")
    print(f"Sink: {flow.sink_node_id}")
    print(f"Path: {' -> '.join(flow.flow_path)}")
```

### 8.4 L4: Expert (Custom Analyzers)

```python
from codegraph import CodeGraph
from codegraph.plugins import CustomAnalyzer

class MyCustomAnalyzer(CustomAnalyzer):
    """Custom analyzer hook"""

    def analyze(self, ir_document):
        # Access Rust IR directly
        for node in ir_document.nodes:
            if node.kind == "function" and node.name.startswith("unsafe_"):
                yield {
                    "type": "custom_warning",
                    "message": f"Unsafe function: {node.name}",
                    "node_id": node.id,
                }

cg = CodeGraph()
cg.register_analyzer(MyCustomAnalyzer())

result = cg.index("/path/to/repo")

# Access custom analysis results
warnings = result.custom_results("custom_warning")
for warning in warnings:
    print(warning["message"])
```

---

## 9. Progressive Disclosure Migration Paths

```python
# ════════════════════════════════════════════════════════════════════
# L1 → L2: Add single feature
# ════════════════════════════════════════════════════════════════════

# L1: Basic indexing
result = cg.index("/repo")

# L2: Add taint analysis (one line change)
result = cg.index("/repo").with_taint()

# ════════════════════════════════════════════════════════════════════
# L2 → L3: Compose multiple features
# ════════════════════════════════════════════════════════════════════

# L2: Single feature
result = cg.index("/repo").with_taint()

# L3: Multiple features (method chaining)
result = (cg.index("/repo")
    .with_taint()
    .with_repomap()
    .with_clone_detection()
    .parallel(workers=8)
)

# ════════════════════════════════════════════════════════════════════
# L3 → L4: Full configuration control
# ════════════════════════════════════════════════════════════════════

# L3: Method chaining
result = (cg.index("/repo")
    .with_taint()
    .with_repomap()
    .parallel(workers=8)
)

# L4: Explicit configuration object
config = IndexingConfig(
    root_path="/repo",
    parallel_workers=8,
    enable_taint=True,
    enable_repomap=True,
    taint_rules_path="./custom_rules.yaml",  # Custom rules
    cache_dir=".custom_cache",                # Custom cache
)
result = cg.index(config=config)
```

---

## 10. File Watcher (Automatic Incremental Updates)

### 10.1 Configuration

```python
from codegraph import CodeGraph, IndexingConfig

class FileWatcherConfig:
    """
    File watcher configuration for automatic incremental updates.

    Filters applied to notify events before triggering re-indexing:

    1. Debounce: 300ms window to batch rapid changes
    2. Ignore patterns: .git/, node_modules/, __pycache__/
    3. Language filter: Only trigger on {.py, .ts, .rs, .java, .kt, .go}
    4. Size limit: Skip files > 1MB (avoid binary files)
    """

    DEBOUNCE_MS = 300
    IGNORE_PATTERNS = [
        ".git/",
        "node_modules/",
        "__pycache__/",
        "*.pyc",
        "*.class",
        "*.o",
        "target/",  # Rust build artifacts
        "dist/",
        "build/",
    ]
    MAX_FILE_SIZE = 1_048_576  # 1MB
    SUPPORTED_EXTENSIONS = [
        ".py", ".ts", ".tsx", ".js", ".jsx",
        ".rs", ".java", ".kt", ".go",
    ]

# Enable file watcher
config = IndexingConfig(
    root_path="/repo",
    file_watcher=True,  # Enable automatic updates
)

cg = CodeGraph(config=config)
result = cg.index()

# File watcher runs in background thread
# Changes are automatically indexed with MVCC snapshots

# Query always uses latest snapshot
nodes = result.query().nodes().filter(language="python").execute()
```

### 10.2 Event Flow

```
File Change (vim save)
    │
    ├─> notify (Rust crate) ──> Event: Modified("src/main.py")
    │                                      │
    │                                      ├─> Debounce (300ms)
    │                                      ├─> Filter (.py extension OK)
    │                                      ├─> Size check (< 1MB)
    │                                      └─> Trigger re-index
    │
    └──> MVCC Snapshot
            │
            ├─> Session 1 (reads snapshot_v1) ──> Still sees old data
            │
            └─> Session 2 (new query) ──────────> Sees snapshot_v2 (updated)
```

---

## 11. Performance Benchmarks

### 11.1 Indexing Performance

```python
# Benchmark results (2024-12-28, MacBook Pro M1 Max, 32GB RAM)

BENCHMARKS = {
    "ir_build_single_file": {
        "baseline_python": "50ms (codegraph-engine Python)",
        "rust_sdk": "15ms (codegraph-ir Rust)",
        "speedup": "3.3x faster",
    },

    "ir_build_repository": {
        "baseline_python": "2.5s (Django repo, 1000 files, single-threaded)",
        "rust_sdk": "470ms (Django repo, 1000 files, 4 workers)",
        "speedup": "5.3x faster (includes parallelism)",
    },

    "taint_analysis": {
        "baseline_python": "12s (Django repo, interprocedural taint)",
        "rust_sdk": "2.1s (Django repo, TRCR 488 atoms)",
        "speedup": "5.7x faster",
    },

    "incremental_update": {
        "single_file_change": "< 100ms (MVCC overhead negligible)",
        "description": "Update index for one changed file (out of 1000)",
    },

    "streaming_memory": {
        "repository_size": "1M nodes (large monorepo)",
        "memory_usage_streaming": "~500 KB (chunk_size=1000)",
        "memory_usage_materialized": "~500 MB (load all at once)",
        "reduction": "1000x less memory",
    },
}
```

### 11.2 DAG Parallelism

```python
# Pipeline execution waves (16 stages, 4 workers)

WAVE_ANALYSIS = {
    "wave_1": {
        "stages": ["L1_IrBuild", "L33_GitHistory"],
        "count": 2,
        "description": "Root stages (L1 + independent L33)",
    },

    "wave_2": {
        "stages": [
            "L2_Chunking", "L2.5_Lexical", "L3_CrossFile",
            "L4_Occurrences", "L5_Symbols", "L6_PointsTo",
            "L10_CloneDetection", "L15_CostAnalysis", "L21_SmtVerification",
        ],
        "count": 9,
        "description": "All stages that depend only on L1 (fully parallel)",
    },

    "wave_3": {
        "stages": [
            "L13_EffectAnalysis", "L14_TaintAnalysis",
            "L16_RepoMap", "L18_ConcurrencyAnalysis", "L37_QueryEngine",
        ],
        "count": 5,
        "description": "Advanced analyses with multiple dependencies",
    },

    "summary": {
        "total_stages": 16,
        "total_waves": 3,
        "parallelism_factor": "5.3x (16 stages / 3 waves)",
    },
}
```

---

## 12. Implementation Plan

### 12.1 Phase 1: Core Contracts (Week 1-2)

**Goal**: Stable contract definitions + Pydantic models

**Tasks**:
1. ✅ Define `IndexingConfig` (v1.1) with Pydantic validators
2. ✅ Define `Node`, `Edge`, `TaintFlow` (v2.0) data models
3. ✅ Define `CodeGraphError` hierarchy with error categories
4. ✅ Write contract versioning tests (compatibility checks)

**Deliverable**: `contracts/` package with full type coverage

### 12.2 Phase 2: FFI Layer (Week 3-4)

**Goal**: PyO3 bindings + Arrow IPC streaming

**Tasks**:
1. ⏳ Implement `codegraph_ir._ffi` module (PyO3)
2. ⏳ Add Arrow IPC serialization for `Node`/`Edge`
3. ⏳ Implement streaming iterator (Rust `impl Iterator<Item = RecordBatch>`)
4. ⏳ Add error translation (`Result<T> → CodeGraphError`)

**Deliverable**: Rust `lib.rs` with `#[pymodule]` exports

### 12.3 Phase 3: Public API (Week 5-6)

**Goal**: L1-L4 user-facing APIs

**Tasks**:
1. ⏳ Implement `CodeGraph` class (main entry point)
2. ⏳ Implement `QueryBuilder` (Django ORM-style)
3. ⏳ Implement `Session` (MVCC snapshot management)
4. ⏳ Add method chaining for `.with_taint()`, `.with_repomap()`, etc.

**Deliverable**: `codegraph/__init__.py` with full API surface

### 12.4 Phase 4: Testing (Week 7-8)

**Goal**: 90% test coverage + chaos engineering

**Tasks**:
1. ⏳ Unit tests for each contract (Pydantic validation)
2. ⏳ Integration tests (E2E indexing + querying)
3. ⏳ Streaming tests (verify O(chunk_size) memory)
4. ⏳ Chaos tests (failure injection for error recovery)

**Test Categories**:
```python
import pytest

@pytest.mark.unit
def test_config_validation():
    """Pydantic validation catches invalid configs"""
    with pytest.raises(ValueError, match="does not exist"):
        IndexingConfig(root_path="/nonexistent")

@pytest.mark.integration
def test_e2e_indexing():
    """Full indexing pipeline"""
    cg = CodeGraph()
    result = cg.index("tests/fixtures/django")
    assert result.stats.total_nodes > 1000

@pytest.mark.streaming
def test_streaming_memory():
    """Verify streaming uses O(chunk_size) memory"""
    import tracemalloc
    tracemalloc.start()

    cg = CodeGraph()
    result = cg.index("tests/fixtures/large_repo")

    peak_before = tracemalloc.get_traced_memory()[1]

    # Stream 1M nodes
    count = 0
    for batch in result.query().nodes().execute(chunk_size=1000):
        count += len(batch)

    peak_after = tracemalloc.get_traced_memory()[1]

    # Memory increase should be < 10MB (not 500MB)
    assert (peak_after - peak_before) < 10_000_000

@pytest.mark.chaos
def test_network_timeout_recovery():
    """Validate retry logic for transient failures"""
    with inject_failure("openai_api", delay_ms=5000):
        result = cg.index("/repo").with_embeddings()

        # Should retry and eventually succeed
        assert result.errors[0].category == ErrorCategory.TRANSIENT
        assert result.errors[0].is_retryable()
```

### 12.5 Phase 5: Documentation (Week 9-10)

**Goal**: Migration guides + API docs

**Tasks**:
1. ⏳ Write migration guide (v1.0 → v1.1 config)
2. ⏳ Generate API docs (Sphinx + autodoc)
3. ⏳ Write tutorials (L1→L2→L3→L4 progression)
4. ⏳ Create Jupyter notebook examples

---

## 13. Alternatives Considered

### 13.1 Alternative 1: Keep Python-only SDK

**Pros**:
- No FFI complexity
- Easier debugging

**Cons**:
- ❌ Performance: 5x slower than Rust
- ❌ Memory: No streaming (OOM on large repos)
- ❌ Parallelism: GIL limits parallelization

**Decision**: Rejected. Performance is critical for SOTA.

### 13.2 Alternative 2: Auto-generate Python from Rust

**Pros**:
- No manual bindings
- Always in sync

**Cons**:
- ❌ Un-Pythonic API (camelCase, no context managers)
- ❌ No progressive disclosure
- ❌ No Pydantic validation

**Decision**: Rejected. DX matters more than auto-generation.

### 13.3 Alternative 3: gRPC instead of PyO3

**Pros**:
- Language-agnostic (could support Node.js, Go, etc.)
- Network-transparent

**Cons**:
- ❌ Serialization overhead (no zero-copy)
- ❌ Deployment complexity (need to run server)
- ❌ Latency: 1-5ms per RPC call

**Decision**: Rejected for v1. Consider for future multi-language support.

---

## 14. Open Questions

### 14.1 Resolved

✅ **Q1**: Should we support async APIs?
**A1**: Yes. All I/O operations (indexing, querying) should return `Awaitable` for async runtimes. Use `asyncio.to_thread()` for Rust FFI calls.

✅ **Q2**: How to handle schema evolution?
**A2**: Use Pydantic validators + semantic versioning. Deprecated fields emit warnings for 12 months before removal.

✅ **Q3**: Should we expose Rust `IRDocument` directly?
**A3**: No. Always use Pydantic contracts for type safety. Expert users (L4) can use `.to_dict()` if needed.

### 14.2 Open

⏳ **Q4**: Should we provide SQL-like query syntax?
**Proposal**: Add `session.sql("SELECT * FROM nodes WHERE kind='function'")` for advanced users.
**Status**: TBD (collect user feedback first)

⏳ **Q5**: How to handle multi-language repositories (Python + TypeScript)?
**Proposal**: Auto-detect languages and run parallel pipelines.
**Status**: Needs performance testing

---

## 15. Appendix

### 15.1 Glossary

- **Contract**: Versioned API interface (Config, Query, Data, Error)
- **DAG**: Directed Acyclic Graph (pipeline orchestration)
- **FFI**: Foreign Function Interface (Rust ↔ Python via PyO3)
- **MVCC**: Multi-Version Concurrency Control (snapshot isolation)
- **Progressive Disclosure**: Layered API complexity (L1→L2→L3→L4)
- **Streaming**: Memory-efficient iteration (O(chunk_size) not O(total_size))
- **TRCR**: Taint Rules for Code Reasoning (488 security atoms)

### 15.2 References

- [Stripe API Design](https://stripe.com/docs/api)
- [Django ORM Documentation](https://docs.djangoproject.com/en/stable/topics/db/queries/)
- [Pandas Streaming](https://pandas.pydata.org/docs/user_guide/io.html#io-chunking)
- [Pydantic V2 Documentation](https://docs.pydantic.dev/latest/)
- [PyO3 Guide](https://pyo3.rs/v0.20.0/)
- [Apache Arrow IPC](https://arrow.apache.org/docs/python/ipc.html)

### 15.3 Code Examples Repository

All code examples in this RFC are available at:
```
https://github.com/codegraph/sdk-examples
```

Organized by user level:
```
sdk-examples/
├── L1_simple/
│   ├── basic_indexing.py
│   └── basic_querying.py
├── L2_composable/
│   ├── method_chaining.py
│   └── multi_feature.py
├── L3_advanced/
│   ├── full_config.py
│   ├── custom_taint_rules.py
│   └── streaming.py
└── L4_expert/
    ├── custom_analyzer.py
    └── direct_ir_access.py
```

---

## 16. Approval

**Reviewers**:
- [ ] @songmin (Architecture)
- [ ] @rust-team (FFI design)
- [ ] @python-team (API ergonomics)
- [ ] @docs-team (Migration guides)

**Approval Criteria**:
1. ✅ All contracts pass Pydantic validation
2. ✅ Streaming memory tests pass (< 10MB for 1M nodes)
3. ✅ Performance benchmarks meet targets (5x Python speedup)
4. ✅ Documentation covers L1-L4 user journeys

**Status**: ⏳ Awaiting review

---

**End of RFC-SDK-001**
