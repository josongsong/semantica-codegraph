# Benchmarking Guide

Complete guide for benchmarking the Rust IR pipeline with UnifiedOrchestrator.

## Quick Start (1 minute)

### Run benchmark on any repository

```bash
# Benchmark any repository by providing a path
cargo run --example benchmark_large_repos --release -- <repo_path>

# Examples:
cargo run --example benchmark_large_repos --release -- .
cargo run --example benchmark_large_repos --release -- /path/to/your/project
cargo run --example benchmark_large_repos --release -- tools/benchmark/repo-test/small/typer
```

### Run test on small fixture

```bash
cargo test --package codegraph-ir --bench unified_orchestrator_bench bench_small_fixture -- --nocapture
```

## Performance Results

Verified on real-world repositories:

| Repository | Size | Files | Nodes | Edges | Duration | Throughput (nodes/s) | Status |
|------------|------|-------|-------|-------|----------|---------------------|--------|
| **typer** | 0.79 MB | 651 | 6,471 | 33,428 | 0.13s | **49,839** 🚀 | ✅ |
| **rich** | 5.23 MB | 512 | 8,369 | 46,707 | 0.11s | **73,459** 🚀 | ✅ |

**Performance Highlights:**
- 5-7x faster than target (10,000 nodes/sec)
- 100% success rate (0 failures)
- Sub-second indexing for medium repositories

## Pipeline Stages

### Default Stages (L1-L3)

Basic indexing activated by default:

| Stage | Name | Description | Output |
|-------|------|-------------|--------|
| **L1** | IR Build | AST parsing + IR generation | Nodes, Edges |
| **L2** | Chunking | Split code into chunks | Chunks |
| **L3** | Lexical Indexing | Full-text search index | Tantivy Index |

```bash
cargo run --example benchmark_large_repos --release -- <repo_path>
```

**Performance breakdown:**
- L1 IR Build: ~33% of time
- L2 Chunking: ~25% of time
- L3 Lexical: ~42% of time (bottleneck: disk I/O)

### Extended Stages (--all-stages)

Advanced analysis features:

| Stage | Name | Description |
|-------|------|-------------|
| **L4** | Cross-File Resolution | Import resolution & module linking |
| **L5** | Clone Detection | Duplicate code detection |
| **L10** | Symbols | Symbol extraction (definitions, references) |
| **L11** | Effect Analysis | Side-effect analysis (I/O, network) |
| **L13** | Points-to Analysis | Pointer analysis (Andersen's algorithm) |
| **L14** | Taint Analysis | Security taint flow analysis |
| **L16** | RepoMap | Repository importance mapping (PageRank) |

```bash
cargo run --example benchmark_large_repos --release -- <repo_path> --all-stages
```

**Trade-off:**
- Default (L1-L3): Fast (~0.1s), basic analysis
- Extended (L1-L16): Slower (~0.5-2s), complete analysis including security

## Reading Benchmark Reports

### Console Output

Real-time results during execution:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Benchmark Results: typer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Repository Info:
  - Size: 0.79 MB
  - Files: 651

Indexing Results:
  - Nodes: 6,471
  - Edges: 33,428
  - Chunks: 403

Performance:
  - Duration: 0.13s
  - Throughput: 49,839 nodes/sec
  - Throughput: 5,014 files/sec

Pipeline:
  - Stages completed: 3
  - Stages failed: 0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### CSV Results

Summary statistics saved to `target/benchmark_results.csv`:

```bash
cat target/benchmark_results.csv
```

Format:
```
repo_name,size_mb,file_count,nodes,edges,chunks,duration_sec,throughput_nodes_sec,throughput_files_sec,stages_completed,stages_failed
typer,0.79,651,6471,33428,403,0.1298,49839.32,5013.97,3,0
```

### Waterfall Report

Detailed stage-by-stage analysis in `target/benchmark_<repo_name>_waterfall.txt`:

**Default stages (L1-L3):**
```
Timeline: 0ms────────────────────────────130ms
           L1 (33%)  L2 (25%)  L3 (42%)
           █████████ ███████   ████████████
```

**All stages (L1-L16):**
```
Timeline: 0ms──────────────────────────────────────500ms
           L1  L2 L3 L4 L5    L13 (PTA)    L14 (Taint) L16
           ██  █ ██ █ █     ████████████  ██████      ██
```

The waterfall shows:
- Timeline visualization
- Stage duration percentages
- Performance bottlenecks

## Use Cases

### 1. Quick Code Search (Default)

```bash
cargo run --example benchmark_large_repos --release -- <repo_path>
```

**Use for:** Code search, exploration, basic analysis
**Time:** ~0.1s
**Stages:** L1-L3

### 2. Security Analysis (Extended)

```bash
cargo run --example benchmark_large_repos --release -- <repo_path> --all-stages
```

**Use for:** SQL Injection, XSS, memory leaks detection
**Time:** ~0.5-2s
**Stages:** L1-L16

### 3. CI/CD Integration

```yaml
# GitHub Actions example
- name: Benchmark codebase
  run: |
    cargo run --example benchmark_large_repos --release -- ${{ github.workspace }}

- uses: actions/upload-artifact@v3
  with:
    name: benchmark-results
    path: target/benchmark_results.csv
```

### 4. Performance Comparison

```bash
# Before changes
cargo run --example benchmark_large_repos --release -- . > before.txt

# After changes
cargo run --example benchmark_large_repos --release -- . > after.txt

# Compare
diff before.txt after.txt
```

## Testing Repositories

Clone test repositories for benchmarking:

```bash
# Small (quick test)
mkdir -p tools/benchmark/repo-test/small
cd tools/benchmark/repo-test/small
git clone https://github.com/tiangolo/typer.git

# Medium
mkdir -p tools/benchmark/repo-test/medium
cd tools/benchmark/repo-test/medium
git clone https://github.com/Textualize/rich.git

# Large
mkdir -p tools/benchmark/repo-test/large
cd tools/benchmark/repo-test/large
git clone https://github.com/django/django.git
```

Expected times:
- typer (small): ~0.1s
- rich (medium): ~0.1s
- django (large): ~1-2s

## Technical Details

### Technology Stack

- **Rust**: High-performance analysis engine
- **Rayon**: Parallel processing (per-file)
- **tree-sitter**: AST parsing
- **Tantivy**: Full-text search indexing
- **Release mode**: Optimized compilation

### Metrics Collected

**Repository Info:**
- Size (MB)
- File count

**Indexing Results:**
- Total nodes (functions, classes, variables)
- Total edges (calls, references)
- Total chunks (code chunks)
- Total symbols

**Performance:**
- Duration (seconds)
- Throughput (nodes/sec)
- Throughput (files/sec)

**Pipeline Status:**
- Stages completed
- Stages failed

## Files

Benchmark system consists of:

1. **`packages/codegraph-ir/benches/unified_orchestrator_bench.rs`**
   - Cargo bench integration
   - Small fixture tests

2. **`packages/codegraph-ir/examples/benchmark_large_repos.rs`**
   - CLI argument parsing
   - Real repository benchmarking
   - Performance metrics collection
   - CSV export

3. **Documentation**
   - This file (BENCHMARKING.md)
   - See also: [docs/BENCHMARK_GUIDE.md](docs/BENCHMARK_GUIDE.md) for comprehensive details

## See Also

- [CLAUDE.md](CLAUDE.md) - Project overview and architecture
- [docs/RUST_ENGINE_API.md](docs/RUST_ENGINE_API.md) - Rust API reference
- [docs/CLEAN_ARCHITECTURE_SUMMARY.md](docs/CLEAN_ARCHITECTURE_SUMMARY.md) - Architecture design
