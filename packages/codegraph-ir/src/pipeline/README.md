# Pipeline Module

This module contains two different pipeline implementations:

## 1. Single-File IR Pipeline (Existing)

**Files**: `processor.rs`, `config.rs`, `result.rs`

**Purpose**: Process a single file through IR generation stages
- Used by: `process_python_file()` function
- Scope: L1 IR build for one file
- Output: `ProcessResult` (nodes, edges, occurrences)

## 2. End-to-End Repository Pipeline (New)

**Files**: `end_to_end_*.rs`

**Purpose**: Process entire repository through all indexing stages
- Used by: `analyze_repository_pipeline()` Python binding
- Scope: L1-L5 (IR → Chunk → Cross-file → Occurrence)
- Output: `E2EPipelineResult` (aggregated results + stats)

### Key Differences

| Feature | Single-File | End-to-End |
|---------|-------------|------------|
| Input | 1 file content | N file paths |
| Parallelism | None | Rayon parallel |
| Caching | None | Redis cache |
| Cross-file | No | Yes (DashMap) |
| Chunking | No | Yes (parallel) |
| Python GIL | Released per file | Released once for all |
| Target | IR generation | Full indexing |

### Performance Target

**Current (Python Orchestrator)**: 88s for 1.95M LOC
**Goal (Rust E2E)**: 25s for 1.95M LOC (3.5x faster)

### Usage

```rust
// Single-file (existing)
let result = process_python_file(content, repo_id, file_path, module_path);

// End-to-end (new)
let config = E2EPipelineConfig::new(repo_id, repo_path);
let orchestrator = E2EOrchestrator::new(config)?;
let result = orchestrator.execute(file_paths)?;
```

