# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**codegraph-engine** is the core analysis engine for Semantica v2, responsible for:
- **IR Generation**: Building Intermediate Representations from source code (Python, Java, Kotlin, TypeScript, Rust, Go)
- **Graph Construction**: Control Flow Graphs (CFG), Data Flow Graphs (DFG), Basic Flow Graphs (BFG)
- **Taint Analysis**: SOTA interprocedural taint analysis with Rust acceleration (10-50x speedup)
- **Type Inference**: Multi-level type resolution (tree-sitter → flow inference → Pyright → constraint solving)
- **Code Chunking**: Converting IR to searchable chunks for RAG/semantic search
- **Repository Structure Analysis**: PageRank, dependency analysis

This is part of a monorepo at `../../` (codegraph root). See `../../CLAUDE.md` for project-wide context.

## Architecture

### Hexagonal Architecture + DDD

The codebase follows **Hexagonal (Ports & Adapters) Architecture** with **Domain-Driven Design**:

```
codegraph_engine/
├── code_foundation/       # Primary bounded context (AST → IR → Graphs → Chunks)
│   ├── domain/           # Core models (Symbol, IRDocument, Node, Edge)
│   ├── application/      # Use cases (ParseFile, ProcessFile, TaintAnalysis)
│   ├── infrastructure/   # Implementations (parsers, generators, chunkers)
│   ├── adapters/         # Port adapters (Rust bridge, tree-sitter wrapper)
│   └── di.py            # Dependency Injection container
├── analysis_indexing/    # L1-L4 indexing pipeline
├── reasoning_engine/     # Advanced analysis (slicing, taint, impact)
├── multi_index/          # Multi-index management
├── repo_structure/       # Repository analysis (PageRank, dependencies)
└── shared_kernel/        # Cross-context models (@dataclass, Enum, Protocol only)
```

**Key Pattern**: Each bounded context has a DI container (`di.py`) with `@cached_property` for singleton services.

### Rust Integration (53x Speedup)

Rust is used for performance-critical paths:

**Python → Rust Bridge**:
```python
# infrastructure/generators/rust_adapter.py
from codegraph_ir import process_python_files  # Rust module via PyO3

rust_adapter = get_rust_adapter(repo_id, enable_rust=True)
builder = LayeredIRBuilder(parallel_builder=rust_adapter)
```

**Rust Crate**: `../codegraph-rust/codegraph-ir/`
- **53x faster IR generation** (Django 901 files: 0.166s vs 8.8s)
- **12x faster cross-file resolution** (3.8M symbols/sec)
- **GIL-free parallelism** with Rayon (75% CPU cores)
- **msgpack serialization** (25x faster than Python dicts)

**Features**:
- Multi-language support (Python, Java, Kotlin, TypeScript, Rust, Go)
- L2-L5 layers: BFG, CFG, DFG, SSA, Type Entities
- Zero-copy IPC with Apache Arrow
- 33+ unit tests in Rust

### IR Pipeline Architecture

**9-Layer Pipeline** (being replaced by stage-based pipeline):
```
L0: Cache (fast/slow path with mtime/content hash)
L1: Structural IR (Rust-accelerated parsing)
L2: Occurrence Layer (SCIP-style occurrences)
L3: LSP Type Enrichment (Pyright integration)
L4: Cross-file Resolution (imports, inheritance)
L5: Semantic IR (CFG/DFG/BFG construction)
L6: Analysis Indexes (PDG, taint summaries)
L7: Retrieval Indexes (chunks, embeddings)
L8: Diagnostics Collection
L9: Package Analysis
```

**New IR Pipeline v3** (modern approach):
```python
# infrastructure/ir/pipeline/builder.py
pipeline = (
    PipelineBuilder()
    .with_profile("balanced")  # fast/balanced/full
    .with_structural_ir(use_rust=True, use_msgpack=True)
    .with_cross_file_resolution()
    .with_flow_graphs()
    .build()
)
result = await pipeline.execute()
```

**Performance Targets**:
- Small (<100 files): <10s
- Medium (100-1K files): <90s
- Large (1K+ files): <10min

### Dependency Injection Pattern

Each bounded context has a container:

```python
# code_foundation/di.py
class CodeFoundationContainer:
    @cached_property
    def parser(self) -> ParserPort:
        """Returns TreeSitterParser or FakeParser"""

    @cached_property
    def ir_generator(self) -> IRGeneratorPort:
        """Returns RustIRAdapter or PythonIRGenerator"""

    @cached_property
    def process_file_usecase(self) -> ProcessFileUseCase:
        """Wires all dependencies together"""

# Usage
container = CodeFoundationContainer()
usecase = container.process_file_usecase
result = await usecase.execute(file_path)
```

**Environment Variables**:
- `USE_FAKE_STORES=1`: Use in-memory fakes for testing
- `REPO_ID=<id>`: Set repository ID
- `SEMANTICA_LOG_LEVEL=DEBUG`: Enable debug logging

## Common Development Commands

### Python Testing

```bash
# Run tests (from monorepo root ../../)
pytest tests/ -v                    # Excludes slow tests
pytest tests/ -m ""                 # All tests including slow
pytest -m unit                      # Unit tests only
pytest -m integration               # Integration tests only
pytest tests/ -v --cov=packages     # With coverage

# Run specific test file
pytest tests/unit/test_foo.py -v

# Run determinism tests (this package)
pytest test_determinism.py -v

# Test markers
# @pytest.mark.slow        - Tests > 5 seconds
# @pytest.mark.integration - Requires external services
# @pytest.mark.unit        - Pure unit tests
# @pytest.mark.asyncio     - Async tests
```

### Rust Testing

```bash
# Build Rust module
cd ../codegraph-rust/codegraph-ir
make build-python              # or: maturin develop --release

# Run Rust tests
make test                      # Excludes slow tests
make test-all                  # All tests including slow
make test-unit                 # Rust unit tests only
make test-integration          # Rust integration tests
make test-python               # Python integration tests

# Benchmarks
make bench                     # Run all benchmarks
make bench-parsing            # Parsing benchmarks only
make bench-baseline           # Save baseline
make bench-compare            # Compare against baseline

# Code quality
make fmt                      # Format Rust code
make lint                     # Run clippy lints
make check                    # Format + lint + test
make ci                       # Full CI simulation

# Coverage
make coverage                 # Generate HTML coverage report
make coverage-open            # Generate and open report

# Shortcuts
make t                        # Test
make b                        # Build
make f                        # Format
make w                        # Watch mode
```

### Formatting & Linting

```bash
# From monorepo root (../../)
just format                   # Black + Ruff
just lint                     # Ruff + Pyright

# Manual
black codegraph_engine tests
ruff check codegraph_engine tests --fix
pyright codegraph_engine
```

## Key Domain Concepts

### IRDocument

The central abstraction for code analysis:

```python
@dataclass
class IRDocument:
    repo_id: str
    snapshot_id: str
    nodes: list[Node]        # Functions, classes, variables
    edges: list[Edge]        # Relationships (CALLS, CONTAINS, INHERITS)
    types: list[TypeEntity]  # Type information

    # L2-L5 enrichments (Rust-generated)
    bfg_graphs: list[BasicFlowGraph]  # Control flow
    cfg_edges: list[dict]
    dfg_graphs: list[dict]            # Data flow
    ssa_graphs: list[dict]            # SSA form
```

**Node Kinds**: FUNCTION, METHOD, CLASS, MODULE, VARIABLE, PARAMETER, ATTRIBUTE, IMPORT, DECORATOR

**Edge Kinds**: CALLS, CONTAINS, INHERITS, WRITES, READS, DEFINES, USES, THROWS

### Chunks

Searchable units for RAG/semantic search:

```python
@dataclass
class Chunk:
    id: str
    file_path: str
    content: str
    kind: ChunkKind  # FUNCTION, CLASS, MODULE, IMPORT
    metadata: dict
    embedding: Optional[list[float]]
```

**Chunking Strategy**:
- Function-level granularity (primary)
- Class-level for large classes
- Context overlap for better search

### Taint Analysis

**Multi-mode taint analysis** (RFC-024):

```python
# Create analyzer pipeline
analyzer = container.create_analyzer_pipeline(
    ir_doc,
    mode=AnalyzerMode.AUDIT  # REALTIME/PR/AUDIT/COST
)

# Modes:
# - REALTIME: <500ms (SCCP only, for IDE)
# - PR: <5s (SCCP + Taint lite, for PR comments)
# - AUDIT: minutes (SCCP + Taint full + Null + Z3, for security audit)
# - COST: <1s (SCCP + Cost analysis, for performance)
```

**Rust-accelerated taint engine**:
- Inter-procedural analysis (function summaries with LRU cache)
- Type-aware matching (exact/structural/semantic)
- Source/sink/sanitizer detection
- Path-sensitive analysis
- Context-sensitive analysis (call stack)
- 10-50x speedup with rustworkx + Bloom filter invalidation

### Type Inference

**Multi-level type resolution**:

```python
class TypeResolutionLevel(Enum):
    RAW = "raw"              # As-written in code
    INFERRED = "inferred"    # Flow-based inference
    PYRIGHT = "pyright"      # LSP-enhanced
    CONSTRAINT = "constraint" # Constraint-based

class TypeFlavor(Enum):
    BUILTIN = "builtin"      # int, str, list
    USER = "user"            # User-defined classes
    EXTERNAL = "external"    # Third-party libraries
```

**Type inference stack**:
1. Tree-sitter AST extraction
2. Local flow inference (SSA-based)
3. Pyright LSP (for public APIs)
4. Constraint solving (for complex cases)
5. Cached type configs for builtins

## Testing Conventions

### Test Structure

```
tests/
└── unit/              # Unit tests (fast, isolated)

# Additional tests at package root:
test_determinism.py    # RFC-RUST-ENGINE determinism tests
```

### Test Patterns

```python
# Pattern 1: Async tests
@pytest.mark.asyncio
async def test_pipeline():
    pipeline = PipelineBuilder().with_profile("fast").build()
    result = await pipeline.execute()
    assert result.is_success()

# Pattern 2: DI container with fakes
def test_with_fakes():
    container = CodeFoundationContainer(use_fake=True)
    usecase = container.process_file_usecase
    result = usecase.execute(file_path)
    assert result.success

# Pattern 3: Determinism tests
def test_deterministic_ordering():
    ir_doc = IRDocument(repo_id="test", snapshot_id="v1")
    ir_doc.assign_local_seq()
    hash1 = compute_hash(ir_doc)
    # Run 10 times, verify same hash
```

## Code Style

- **Python**: 3.11+ with type hints
- **Line length**: 120 characters
- **Formatter**: Black + Ruff
- **Type checker**: Pyright (strict mode)
- **Import order**: stdlib → third-party → local (enforced by Ruff)

### Import Pattern

```python
# Standard library
from pathlib import Path
from typing import Protocol

# Third-party
import rustworkx as rx
from tree_sitter import Language

# Local packages
from codegraph_engine.shared_kernel.models import Symbol
from codegraph_engine.code_foundation.domain.ports import ParserPort
```

### Port/Adapter Pattern

```python
# Domain port (Protocol)
class IRGeneratorPort(Protocol):
    def generate(self, ast: ASTDocument) -> IRDocument: ...

# Infrastructure adapter
class RustIRAdapter:
    """Adapter wrapping codegraph-ir Rust module"""
    def generate(self, ast: ASTDocument) -> IRDocument:
        # Call Rust via PyO3
        results = codegraph_ir.process_python_files(...)
        return self._convert_to_ir_document(results)
```

## Determinism Requirements

**RFC-RUST-ENGINE Phase 1**: Total ordering for reproducible builds

1. **local_seq assignment**: All nodes/edges get sequential IDs
2. **Deterministic hashing**: Same input → same hash (10 runs)
3. **No ties in ordering**: `(file_path, kind, start_line, name, local_seq)`
4. **Stable serialization**: msgpack with sorted keys

**Test**:
```bash
pytest test_determinism.py -v
```

## Rust-Python Integration

### Using Rust from Python

```python
# Option 1: Direct Rust API
import codegraph_ir

files = [
    ('main.py', code, 'myapp.main'),
    ('utils.py', code2, 'myapp.utils'),
]
results = codegraph_ir.process_python_files(files, repo_id='my-repo')

# Option 2: Via RustIRAdapter
from codegraph_engine.code_foundation.infrastructure.generators.rust_adapter import get_rust_adapter

rust_adapter = get_rust_adapter(repo_id, enable_rust=True)
builder = LayeredIRBuilder(parallel_builder=rust_adapter)
ir_doc = await builder.build(files)

# Option 3: New IR Pipeline v3 (preferred)
pipeline = (
    PipelineBuilder()
    .with_structural_ir(use_rust=True, use_msgpack=True)
    .build()
)
result = await pipeline.execute()
```

### Building Rust Module

```bash
cd ../codegraph-rust/codegraph-ir

# Development build (fast, debug)
maturin develop

# Release build (optimized, for benchmarks)
maturin develop --release

# Or use Makefile
make build-python
```

### Fallback Behavior

- **Rust-first execution**: Try Rust, fall back to Python on error
- **No silent failures**: All errors are logged
- **Complete error reporting**: Python exceptions from Rust are preserved

## Configuration

### Key Settings

All magic numbers are centralized in `../../packages/codegraph-shared/codegraph_shared/infra/jobs/handlers/config.py`:

```python
from codegraph_shared.infra.jobs.handlers import DEFAULT_CONFIG

config = DEFAULT_CONFIG
config.defaults.parallel_workers  # 4
config.timeouts.pipeline          # 600s
config.batch.vector_batch_size    # 100
```

### Error Handling

```python
from codegraph_shared.infra.jobs.handlers import ErrorCategory, ErrorCode

# TRANSIENT: Retriable (temporary failures like network timeout)
# PERMANENT: Not retriable (invalid input, parse errors)
# INFRASTRUCTURE: System issues (DB down, disk full)
```

## Related Documentation

- **Monorepo guide**: `../../CLAUDE.md`
- **Rust architecture**: `../codegraph-rust/README.md`
- **System handbook**: `../../docs/handbook/system-handbook/`
- **Module docs**: `../../docs/handbook/system-handbook/modules/`

## Performance Characteristics

### IR Generation (Rust vs Python)

| Repository | Files | Rust Time | Python Time | Speedup |
|------------|-------|-----------|-------------|---------|
| Django     | 901   | 0.166s    | 8.8s        | 53x     |
| Ansible    | 1,774 | 0.090s    | 17.4s       | 194x    |
| Flask      | 83    | 0.008s    | 0.8s        | 100x    |
| Pydantic   | 398   | 0.088s    | 3.9s        | 44x     |

### Cross-file Resolution

- **12x faster**: 62s → 5s
- **3.8M symbols/sec** throughput
- **Parallel BFS** with rustworkx

### Taint Analysis

- **10-50x speedup** with Rust taint engine
- **LRU cache** for function summaries
- **Bloom filter** for cache invalidation
