# codegraph-ir: Rust IR Engine

**Status**: Production Ready
**Last Updated**: 2025-12-28

High-performance intermediate representation (IR) engine for code analysis, written in pure Rust.

## Features

### Core IR Pipeline
- **Multi-language parsing**: Python, TypeScript/JavaScript, Go, Rust, Java, Kotlin
- **IR Generation**: AST → Graph (nodes, edges, types)
- **Cross-file analysis**: Import resolution, type inference
- **Incremental updates**: Fast delta processing

### Advanced Analysis
- **Points-to Analysis**: Andersen/Steensgaard algorithms (10-50x faster than Python)
- **Taint Analysis**: IFDS/IDE framework for security analysis
- **Effect Analysis**: Biabduction for side-effect tracking
- **Clone Detection**: Type 1-4 clone detection (7,328 LOC)
- **SMT Solving**: Z3 integration for constraint solving

### Indexing & Search
- **Lexical Search**: Tantivy-based full-text search (29.6x faster, see [LEXICAL_SEARCH_COMPLETE_SUMMARY.md](LEXICAL_SEARCH_COMPLETE_SUMMARY.md))
- **RepoMap**: Repository structure with PageRank scoring (see [REPOMAP_COMPLETE_SUMMARY.md](REPOMAP_COMPLETE_SUMMARY.md))
- **Chunking**: Hierarchical code chunking for semantic search
- **Graph Query**: Fluent DSL for code graph queries

### Performance
- **Parallel Processing**: Rayon-based parallelism
- **Lock-free**: DashMap for concurrent access
- **Zero-copy**: Efficient data sharing between stages
- **GIL-free**: Single GIL release for entire repository

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│          IRIndexingOrchestrator (Pipeline)              │
├─────────────────────────────────────────────────────────┤
│  L1: IR Build (parsing + graph construction)           │
│  L2: Chunking (hierarchical code chunks)                │
│  L3: Cross-file (import resolution, type inference)     │
│  L4: Lexical (Tantivy full-text indexing)              │
│  L5: RepoMap (structure + importance scoring)           │
│  L6: Advanced (taint, clone, points-to, effects)        │
└─────────────────────────────────────────────────────────┘
```

## Usage

### Python API

```python
from codegraph_ir import IRIndexingOrchestrator, E2EPipelineConfig

# Configure pipeline
config = E2EPipelineConfig(
    root_path="/path/to/repo",
    parallel_workers=4,
    enable_lexical=True,
    enable_repomap=True,
)

# Execute full pipeline
orchestrator = IRIndexingOrchestrator(config)
result = orchestrator.execute()

# Access results
print(f"Processed {len(result.nodes)} nodes")
print(f"Found {len(result.edges)} edges")
print(f"Indexed {len(result.chunks)} chunks")
```

### Rust API

```rust
use codegraph_ir::pipeline::{IRIndexingOrchestrator, E2EPipelineConfig};

let config = E2EPipelineConfig {
    root_path: "/path/to/repo".into(),
    parallel_workers: 4,
    enable_lexical: true,
    enable_repomap: true,
    ..Default::default()
};

let orchestrator = IRIndexingOrchestrator::new(config);
let result = orchestrator.execute()?;
```

## Project Structure

```
codegraph-ir/
├── src/
│   ├── features/           # Core analysis features
│   │   ├── parsing/        # Multi-language parsers
│   │   ├── chunking/       # Code chunking
│   │   ├── cross_file/     # Cross-file analysis
│   │   ├── lexical/        # Tantivy-based search
│   │   ├── repomap/        # Repository structure
│   │   ├── taint_analysis/ # Security analysis
│   │   ├── effect_analysis/# Side-effect tracking
│   │   ├── clone_detection/# Clone detection
│   │   ├── points_to/      # Alias analysis
│   │   └── smt/            # SMT solving
│   ├── pipeline/           # Pipeline orchestration
│   ├── shared/             # Shared models
│   └── adapters/           # PyO3 bindings
├── tests/                  # Integration tests
├── benches/                # Benchmarks
└── examples/               # Usage examples
```

## Building

### Development Build
```bash
cargo build
maturin develop
```

### Release Build
```bash
cargo build --release
maturin build --release
```

### Run Tests
```bash
cargo test
```

### Run Benchmarks
```bash
cargo bench
```

## Documentation

### API & Reference
- **Query DSL**: [QUERY_DSL.md](docs/QUERY_DSL.md) - Graph query language
- **Clone Detection API**: [CLONE_DETECTION_API.md](docs/CLONE_DETECTION_API.md) - Type 1-4 clone detection
- **Graph Builder**: [GRAPH_BUILDER_README.md](docs/GRAPH_BUILDER_README.md) - IR graph construction

### Features
- **Lexical Search**: [LEXICAL_SEARCH_COMPLETE_SUMMARY.md](docs/LEXICAL_SEARCH_COMPLETE_SUMMARY.md) - Tantivy full-text search
- **RepoMap**: [REPOMAP_COMPLETE_SUMMARY.md](docs/REPOMAP_COMPLETE_SUMMARY.md) - Repository structure & PageRank
- **Features Overview**: [FEATURES_OVERVIEW.md](docs/FEATURES_OVERVIEW.md) - All analysis features

### Implementation
- **Incremental Updates**: [INCREMENTAL_UPDATE_IMPLEMENTATION.md](docs/INCREMENTAL_UPDATE_IMPLEMENTATION.md) - Delta processing
- **Expression & Storage**: [EXPRESSION_AND_STORAGE_IMPLEMENTATION.md](docs/EXPRESSION_AND_STORAGE_IMPLEMENTATION.md) - IR expression system
- **PostgreSQL Backend**: [POSTGRES_QUICK_START.md](docs/POSTGRES_QUICK_START.md) - Storage backend setup

### Architecture
- **Storage Backend**: [RFC-074-Storage-Backend-Architecture.md](docs/rfcs/RFC-074-Storage-Backend-Architecture.md)
- **Benchmarks**: [BENCHMARK_RESULTS_FINAL.md](docs/BENCHMARK_RESULTS_FINAL.md) - Performance metrics

## Performance Benchmarks

| Feature | Python | Rust | Speedup |
|---------|--------|------|---------|
| IR Build | 100 files/s | 1000+ files/s | **10x** |
| Lexical Index | 40 files/s | 1184 files/s | **29.6x** |
| Cross-file | 50 files/s | 600 files/s | **12x** |
| Points-to | 10 files/s | 100-500 files/s | **10-50x** |
| Lexical Search (p95) | 15ms | 1.25ms | **12x** |

## License

MIT
