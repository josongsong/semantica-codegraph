# Codegraph IR - Features Overview

## SOTA Features (All Enabled ✅)

### L1-L5: Foundation & Analysis

1. **IR Generation** (L1) - Multi-language AST to IR conversion
   - Python, TypeScript, Java, Kotlin, Rust, Go
   - Tree-sitter based parsing
   - Parallel processing with Rayon

2. **Chunking** (L2) - Hierarchical code chunks for semantic search
   - Repo → Project → Module → File → Function hierarchy
   - Optimized for vector embeddings

3. **Cross-File Resolution** (L3) - Import/Export resolution
   - 12x faster than Python
   - Dependency graph construction

4. **Control Flow** (L4) - CFG and BFG generation
   - Basic Flow Graph (BFG)
   - Control Flow Graph (CFG)
   - Exceptional CFG

5. **Type Resolution** (L5) - Type inference
   - Python type hints
   - TypeScript types
   - Java/Kotlin generics

### L6-L7: Advanced Analysis

6. **Data Flow Analysis** (L6) - DFG construction
   - Def-use chains
   - Reaching definitions
   - Live variable analysis

7. **SSA** (L7) - Static Single Assignment
   - Phi node insertion
   - SSA renaming
   - Dominance frontiers

8. **PDG** (L7) - Program Dependence Graph
   - Control dependencies
   - Data dependencies
   - Petgraph-based implementation

9. **Taint Analysis** (L7) - Security vulnerability detection
   - Source → Sink tracking
   - Interprocedural analysis
   - Custom sanitizers

10. **Slicing** (L7) - Program slicing
    - Forward slicing
    - Backward slicing
    - Thin slicing

### L8: SOTA Security & Analysis

11. **Effect Analysis** ✅ - Purity tracking
    - Pure function detection
    - Side effect inference
    - Interprocedural propagation
    - **Performance**: <50ms per function

12. **SMT Verification** ✅ - Z3-based verification
    - Assertion checking
    - Invariant verification
    - Counterexample generation
    - **Performance**: 90%+ accuracy, <1ms per assertion

13. **Clone Detection** ✅ - 4-tier clone detection
    - **Type-1**: Exact clones (~2M LOC/s)
    - **Type-2**: Renamed clones (~500K LOC/s)
    - **Type-3**: Gapped clones (~50K LOC/s)
    - **Type-4**: Semantic clones (~5K LOC/s)

14. **Heap Analysis** ✅ - Memory safety analysis
    - Use-after-free detection
    - Double-free detection
    - Memory leak detection
    - Null pointer dereference

15. **Security Analysis** ✅ - Deep security scanning
    - SQL injection
    - XSS vulnerabilities
    - Command injection
    - Path traversal
    - CWE classification

### L9: Repository-Wide

16. **Points-to Analysis** ✅ - Pointer analysis
    - 10-50x faster than Python
    - Flow-sensitive
    - Context-sensitive
    - Field-sensitive

### Supporting Features

17. **Query Engine** ✅ - Fluent query DSL
    - Python-like syntax in Rust
    - Type-safe queries
    - Lazy evaluation

18. **Graph Builder** ✅ - IR → Graph conversion
    - 10-20x faster than Python
    - Parallel node conversion
    - Module deduplication

19. **Multi-Index** ✅ - Incremental indexing
    - Selective scope updates
    - Fine-grained invalidation
    - Delta computation

20. **File Watcher** ✅ - Real-time file monitoring
    - notify-based implementation
    - Debouncing
    - Pattern filtering

21. **Git History Analysis** ✅ - Code evolution tracking
    - Blame analysis
    - Churn metrics
    - Co-change detection

22. **Concurrency Analysis** ✅ - Async race detection
    - Deadlock detection
    - Data race detection
    - Async patterns

## Performance Comparison

| Feature | Python | Rust | Speedup |
|---------|--------|------|---------|
| IR Generation | ~50K LOC/s | ~500K LOC/s | **10x** |
| Cross-File | ~10K files/s | ~120K files/s | **12x** |
| Points-to | ~1K nodes/s | ~50K nodes/s | **50x** |
| Graph Builder | ~20K nodes/s | ~200K nodes/s | **10x** |
| Clone Detection (Type-1) | ~200K LOC/s | ~2M LOC/s | **10x** |
| Effect Analysis | ~10 funcs/s | ~200 funcs/s | **20x** |
| SMT Verification | ~5 funcs/s | ~100 funcs/s | **20x** |

## API Surface

### Python Bindings (PyO3)

All features are exposed to Python via zero-copy msgpack bindings:

```python
import codegraph_ir

# IR Processing
result = codegraph_ir.process_file(file_path, language, enable_all=True)

# Clone Detection
clones = codegraph_ir.detect_clones_all(fragments)
clones = codegraph_ir.detect_clones_type1(fragments, min_tokens=50)
clones = codegraph_ir.detect_clones_type2(fragments, min_similarity=0.95)
clones = codegraph_ir.detect_clones_type3(fragments, max_gap_ratio=0.3)
clones = codegraph_ir.detect_clones_type4(fragments, min_similarity=0.6)

# Effect Analysis
effects = codegraph_ir.analyze_effects(ir_document)

# SMT Verification
results = codegraph_ir.verify_function(function_node)

# Graph Building
graph = codegraph_ir.build_graph(nodes, edges)

# Taint Analysis
taints = codegraph_ir.analyze_taint(pdg, sources, sinks)

# Slicing
slice_nodes = codegraph_ir.slice_backward(pdg, criterion)

# Query Engine
nodes = codegraph_ir.query(graph, query_dsl)
```

### Rust API

Native Rust API for maximum performance:

```rust
use codegraph_ir::prelude::*;

// End-to-end pipeline
let orchestrator = E2EPipelineOrchestrator::new(config);
let result = orchestrator.execute(files)?;

// Individual features
let clone_detector = MultiLevelDetector::new();
let clones = clone_detector.detect_all(&fragments);

let effect_analyzer = EffectAnalyzer::new();
let effects = effect_analyzer.analyze(&ir_document)?;

let smt_verifier = SmtOrchestrator::new();
let verified = smt_verifier.verify(&function_node)?;
```

## Architecture

### Hexagonal Architecture

Each feature follows clean architecture:

```
feature/
├── domain/           # Pure business logic (no dependencies)
├── application/      # Use cases
├── infrastructure/   # External implementations
└── ports/            # Interface definitions
```

### Parallel Processing

- **Rayon**: Data parallelism for CPU-bound tasks
- **Crossbeam**: Lock-free data structures
- **DashMap**: Concurrent HashMap

### Zero-Copy

- **MessagePack**: Binary serialization
- **RKYV**: Zero-copy deserialization (planned)
- **PyO3**: Zero-copy Python↔Rust

## Documentation

- **API Reference**: See [CLONE_DETECTION_API.md](CLONE_DETECTION_API.md)
- **Examples**: See [examples/](../examples/)
- **Benchmarks**: See [benches/](../benches/)
- **Tests**: See [tests/](../tests/)

## Roadmap

### Phase 1 (Complete ✅)
- ✅ All L1-L9 features implemented
- ✅ Clone Detection integrated
- ✅ Effect Analysis integrated
- ✅ SMT Verification integrated
- ✅ Python bindings complete

### Phase 2 (In Progress)
- 🔄 RKYV zero-copy caching
- 🔄 Distributed analysis (multi-machine)
- 🔄 GPU acceleration (CUDA/Metal)
- 🔄 ML-based clone detection (Type-5)

### Phase 3 (Planned)
- 📋 Incremental analysis (file-level)
- 📋 Real-time analysis (IDE integration)
- 📋 Cloud-native deployment
- 📋 Multi-tenant support

## Contributing

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](../../LICENSE) for details.
