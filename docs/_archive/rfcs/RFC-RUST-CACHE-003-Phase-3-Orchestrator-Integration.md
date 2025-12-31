# RFC-RUST-CACHE-003: Phase 3 - Orchestrator Cache Integration

**Status**: Planning
**Author**: Claude Code
**Date**: 2025-12-29
**Depends On**: RFC-RUST-CACHE-002 (Phases 1 & 2)

## Executive Summary

Phase 3 integrates the SOTA Rust cache system into the pipeline orchestrator to enable **incremental builds** with dependency-aware invalidation. This unlocks 10-100x speedups for incremental analysis workflows.

### Goals
1. **Incremental Execution**: Only reprocess changed files + dependents
2. **Dependency Graph**: Track file→file dependencies for propagation
3. **Cache Integration**: Use TieredCache in pipeline orchestrator
4. **MVCC Sessions**: Multi-agent isolation with session-local changes
5. **BFS Propagation**: Efficient dependency invalidation

## Phase 3 Scope

### What's In Scope
- ✅ DependencyGraph integration (file→file edges)
- ✅ `execute_incremental()` method in orchestrator
- ✅ Cache lookup before IR generation
- ✅ Dependency propagation (BFS traversal)
- ✅ Integration tests (incremental scenarios)

### What's Out of Scope (Future Work)
- ⏭️ Multi-agent MVCC (Phase 4)
- ⏭️ Background cache warming
- ⏭️ Distributed cache (Redis/multi-machine)
- ⏭️ Cache compression optimization
- ⏭️ Cache garbage collection

## Architecture

### Current State (Phase 2)

```rust
// IRBuilder has cache support
let cache = Arc::new(TieredCache::new(config, &registry)?);
let builder = IRBuilder::new(repo_id, path, lang, module)
    .with_cache(cache, content);
let ir_doc = builder.build_with_cache().await?;
```

**Limitation**: No orchestrator integration → Full rebuild every time

### Target State (Phase 3)

```rust
// Orchestrator with incremental execution
let orchestrator = IRIndexingOrchestrator::new(config)
    .with_cache(cache)?;

// Initial build (populates cache)
let result1 = orchestrator.execute().await?;

// Incremental build (only changed files)
let changed_files = vec!["src/foo.py", "src/bar.py"];
let result2 = orchestrator.execute_incremental(changed_files).await?;
// ← Only foo.py, bar.py, and dependents reprocessed!
```

**Benefit**: 10-100x speedup for incremental builds (90%+ cache hit rate)

## Design

### 1. DependencyGraph Enhancement

**Current**: Basic file→file dependency tracking exists in `cache/dependency_graph.rs`

**Enhancement**: Integrate with IR pipeline to track imports

```rust
// In L1: IR Build stage
for edge in &ir_doc.edges {
    if edge.kind == EdgeKind::Import {
        let source_file = ir_doc.file_path.clone();
        let target_file = resolve_import_path(&edge.target_id);
        dependency_graph.add_edge(source_file, target_file)?;
    }
}
```

**Output**: Directed graph of file dependencies

```
src/main.py → src/utils.py
src/main.py → src/models.py
src/utils.py → src/helpers.py
```

### 2. Orchestrator Cache Integration

**Modification**: `pipeline/end_to_end_orchestrator.rs`

```rust
pub struct IRIndexingOrchestrator {
    config: E2EPipelineConfig,

    // RFC-RUST-CACHE-003: Phase 3 additions
    #[cfg(feature = "cache")]
    cache: Option<Arc<TieredCache<IRDocument>>>,
    #[cfg(feature = "cache")]
    dependency_graph: Option<Arc<Mutex<DependencyGraph>>>,
}

impl IRIndexingOrchestrator {
    #[cfg(feature = "cache")]
    pub fn with_cache(mut self, cache: Arc<TieredCache<IRDocument>>) -> Result<Self> {
        self.cache = Some(cache.clone());
        self.dependency_graph = Some(Arc::new(Mutex::new(DependencyGraph::new())));
        Ok(self)
    }

    #[cfg(feature = "cache")]
    pub async fn execute_incremental(
        &self,
        changed_files: Vec<String>
    ) -> Result<E2EPipelineResult> {
        // 1. Compute affected files (BFS from changed files)
        let affected_files = self.compute_affected_files(&changed_files)?;

        // 2. Invalidate cache for affected files
        for file in &affected_files {
            let key = CacheKey::from_file_id(FileId::from_path_str(file, Language::Python));
            self.cache.as_ref().unwrap().invalidate(&key).await?;
        }

        // 3. Execute pipeline (only affected files)
        self.execute_with_file_filter(Some(affected_files)).await
    }
}
```

### 3. BFS Dependency Propagation

**Algorithm**: Breadth-First Search from changed files

```rust
fn compute_affected_files(&self, changed_files: &[String]) -> Result<HashSet<String>> {
    let dep_graph = self.dependency_graph.as_ref().unwrap().lock().unwrap();
    let mut affected = HashSet::new();
    let mut queue = VecDeque::from_iter(changed_files.iter().cloned());

    while let Some(file) = queue.pop_front() {
        if affected.insert(file.clone()) {
            // Add all files that depend on this file (reverse edges)
            for dependent in dep_graph.get_dependents(&file)? {
                queue.push_back(dependent);
            }
        }
    }

    Ok(affected)
}
```

**Example**:
```
Changed: src/utils.py

Dependencies:
  src/main.py → src/utils.py
  src/tests.py → src/utils.py

Affected (BFS):
  1. src/utils.py (changed)
  2. src/main.py (depends on utils)
  3. src/tests.py (depends on utils)
```

### 4. Cache-Aware L1 Stage

**Modification**: L1 IR Build stage checks cache before processing

```rust
// In execute_l1_ir_build()
let results: Vec<ProcessResult> = files.par_iter()
    .map(|file_path| {
        // Check cache first
        #[cfg(feature = "cache")]
        if let Some(cache) = &self.cache {
            let content = std::fs::read(file_path)?;
            let fingerprint = Fingerprint::compute(&content);
            let key = CacheKey::new(
                FileId::from_path_str(file_path, Language::Python),
                fingerprint
            );

            let metadata = FileMetadata {
                mtime_ns: get_mtime_ns(file_path)?,
                size_bytes: content.len() as u64,
                fingerprint,
            };

            if let Some(cached_doc) = cache.get(&key, &metadata).await? {
                // Cache hit! Skip IR generation
                return Ok(ProcessResult::from_ir_document(cached_doc));
            }
        }

        // Cache miss - process file normally
        let result = process_file(file_path, &self.config)?;

        // Store in cache
        #[cfg(feature = "cache")]
        if let Some(cache) = &self.cache {
            // ... (store result in cache)
        }

        Ok(result)
    })
    .collect::<Result<Vec<_>>>()?;
```

### 5. Dependency Graph Updates

**On IR Generation**: Extract import edges and update graph

```rust
// After L1 completes
for process_result in &l1_results {
    let ir_doc = &process_result.ir_document;

    // Extract imports
    for edge in &ir_doc.edges {
        if edge.kind == EdgeKind::Import {
            let source = ir_doc.file_path.clone();
            let target = resolve_import_to_file_path(&edge.target_id)?;

            dep_graph.add_edge(source, target)?;
        }
    }
}
```

## Implementation Plan

### Task 1: DependencyGraph Integration (1 day)
- [ ] Add `get_dependents()` method (reverse edge lookup)
- [ ] Add `remove_file()` method (for deleted files)
- [ ] Add `compute_affected_files()` BFS traversal
- [ ] Unit tests for dependency graph

### Task 2: Orchestrator Cache Fields (0.5 day)
- [ ] Add `cache` and `dependency_graph` fields to `IRIndexingOrchestrator`
- [ ] Add `with_cache()` method (builder pattern)
- [ ] Add conditional compilation `#[cfg(feature = "cache")]`

### Task 3: `execute_incremental()` Method (1 day)
- [ ] Implement BFS affected file computation
- [ ] Implement cache invalidation for affected files
- [ ] Implement filtered execution (only affected files)
- [ ] Handle edge cases (deleted files, new files)

### Task 4: Cache-Aware L1 Stage (1 day)
- [ ] Check cache before processing each file
- [ ] Store results in cache after processing
- [ ] Update dependency graph from import edges
- [ ] Parallel cache access (DashMap concurrency)

### Task 5: Integration Tests (0.5 day)
- [ ] Test: Change 1 file → only 1 file + dependents reprocessed
- [ ] Test: Change leaf file → only that file reprocessed
- [ ] Test: Change root file → all dependents reprocessed
- [ ] Test: Cache hit rate > 90% on incremental build
- [ ] Test: Dependency cycle detection

**Total Estimate**: 4 days

## Performance Targets

### Cache Hit Rate
- **Clean build**: 0% (expected - no cache entries)
- **No-op rebuild**: 100% (expected - nothing changed)
- **Incremental (1 file changed)**: 90-99% (depends on dependency fan-out)

### Latency Improvement
Assuming 100 files, 1 file changed, 10 dependents:

| Metric | Full Build | Incremental | Speedup |
|--------|-----------|-------------|---------|
| Files processed | 100 | 11 (1 + 10) | 9.1x |
| IR generation | 200ms | 22ms | 9.1x |
| Total time | 5s | 500ms | 10x |

**Real-world example** (1000 files, 1% change rate):
- Full build: 50s
- Incremental: 2s (assuming 5% dependency fan-out)
- **Speedup**: 25x

## Testing Strategy

### Unit Tests
1. **DependencyGraph BFS**: Verify affected file computation
2. **Cache lookup**: Verify fingerprint-based cache keys
3. **Import edge extraction**: Verify dependency graph population

### Integration Tests
1. **Incremental scenario 1**: Change 1 leaf file
   - Expected: Only that file reprocessed, cache hit rate 99%

2. **Incremental scenario 2**: Change 1 root file
   - Expected: Root + all dependents reprocessed, cache hit rate 80-90%

3. **Incremental scenario 3**: Change 10% of files
   - Expected: 10% + dependents reprocessed, cache hit rate 70-80%

### Benchmark Tests
1. **1000 files, 1% change rate**: Measure speedup
2. **1000 files, 10% change rate**: Measure speedup
3. **1000 files, no changes**: Verify 100% cache hit rate

## Edge Cases

### 1. Deleted Files
**Scenario**: File is deleted from repository

**Handling**:
```rust
// Remove from cache
cache.invalidate(&key).await?;

// Remove from dependency graph
dep_graph.remove_file(file_path)?;

// Invalidate dependents (they now have broken imports)
for dependent in dep_graph.get_dependents(file_path)? {
    cache.invalidate(&dependent_key).await?;
}
```

### 2. New Files
**Scenario**: New file added to repository

**Handling**:
- No cache entry (expected)
- Process normally and cache result
- Update dependency graph with new edges

### 3. Circular Dependencies
**Scenario**: A → B → C → A

**Handling**:
- BFS naturally handles cycles (visited set prevents infinite loop)
- All files in cycle marked as affected
- Dependency graph detects cycles and logs warning

### 4. External Dependencies
**Scenario**: Import from external package (e.g., `import numpy`)

**Handling**:
- Only track internal file→file dependencies
- External imports ignored in dependency graph
- External packages assumed stable (no invalidation)

## Metrics

### New Metrics (Prometheus)
```rust
// Cache performance
cache_hit_rate_total{stage="l1"}
cache_miss_rate_total{stage="l1"}
cache_lookup_latency_seconds{stage="l1"}

// Incremental build performance
incremental_files_changed_total
incremental_files_affected_total
incremental_speedup_ratio

// Dependency graph
dependency_graph_size_total
dependency_graph_avg_out_degree
dependency_graph_cycles_detected_total
```

## Backward Compatibility

### Without Cache Feature
```rust
// Existing code (no cache)
let orchestrator = IRIndexingOrchestrator::new(config);
let result = orchestrator.execute().await?;
// ← Still works! No changes needed
```

### With Cache Feature
```rust
// New code (with cache)
let orchestrator = IRIndexingOrchestrator::new(config)
    .with_cache(cache)?;

// Option 1: Full build (same API)
let result = orchestrator.execute().await?;

// Option 2: Incremental build (new API)
let result = orchestrator.execute_incremental(changed_files).await?;
```

**Result**: 100% backward compatible, opt-in cache usage

## Success Criteria

Phase 3 is complete when:
- ✅ `execute_incremental()` method implemented and tested
- ✅ DependencyGraph integrated with IR pipeline
- ✅ Cache hit rate > 90% on incremental builds (1% change rate)
- ✅ Speedup > 10x on incremental builds (100 files, 1 changed)
- ✅ All integration tests passing (5/5)
- ✅ Build successful with and without cache feature
- ✅ 0 compilation warnings

## Future Work (Phase 4+)

### Phase 4: Multi-Agent MVCC
- Session-local cache isolation
- Commit/rollback for agent sessions
- Optimistic concurrency control

### Phase 5: Advanced Features
- Background cache warming (pre-fetch likely files)
- Cache compression (zstd for L2)
- Distributed cache (Redis backend)
- Cache statistics dashboard

## References

- RFC-RUST-CACHE-001: Phase 1 (Core Cache)
- RFC-RUST-CACHE-002: Phase 2 (IRBuilder Integration)
- [PHASE_1_CACHE_COMPLETION.md](../PHASE_1_CACHE_COMPLETION.md)
- [PHASE_2_IR_BUILDER_COMPLETION.md](../PHASE_2_IR_BUILDER_COMPLETION.md)
- [PHASE_1_2_COMPREHENSIVE_VALIDATION.md](../PHASE_1_2_COMPREHENSIVE_VALIDATION.md)

---

**Status**: Ready to implement 🚀
