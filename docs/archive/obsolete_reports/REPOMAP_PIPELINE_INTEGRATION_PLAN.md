# RepoMap Rust 파이프라인 통합 계획

**Version**: 1.0
**Date**: 2025-12-28
**Status**: Planning → Implementation
**Focus**: Pure Rust Pipeline Integration (Python bindings excluded)

---

## 📊 현재 Rust 파이프라인 구조 분석

### 현재 Rust 파이프라인 (L1-L15)

```rust
// packages/codegraph-rust/codegraph-ir/src/pipeline/end_to_end_orchestrator.rs

┌─────────────────────────────────────────────────────────────────┐
│         IRIndexingOrchestrator::execute()                       │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 1: Foundation                                            │
│   L1: IR Build (parallel per-file) - nodes, edges, types       │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 2: Basic Analysis (parallel after L1)                    │
│   L2: Chunking - Hierarchical chunks                           │
│   L3: CrossFile - Import resolution                            │
│   L4: FlowGraph - CFG, BFG per function                        │
│   L5: Types - Type inference                                   │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 3: Advanced Analysis (parallel after Phase 2)            │
│   L6: DataFlow - DFG per function                              │
│   L7: SSA - Static Single Assignment                           │
│   L8: Symbols - Navigation symbols                             │
│   L9: Occurrences - SCIP occurrences                           │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 4: Repository-Wide (after Phase 3)                       │
│   L10: Points-to - Alias analysis                              │
│   L11: PDG - Program Dependence Graph                          │
│   L12: Heap Analysis - Memory safety                           │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 5: Security & Quality (after Phase 4)                    │
│   L13: Slicing - Program slicing                               │
│   L14: Taint - Interprocedural taint                           │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 6: Performance Analysis (parallel with Phase 5)          │
│   L15: Cost Analysis - Complexity analysis                     │
└─────────────────────────────────────────────────────────────────┘
```

### RepoMap 의존성 분석

RepoMap은 다음 데이터를 필요로 함:

1. **Chunks** (L2 Chunking) - Tree 빌드 기반
2. **GraphDocument** (L3 CrossFile) - PageRank 계산용
3. **Git History** (Optional) - 변경 빈도 추적

→ **Phase 3 이후에 실행 가능**

---

## 🎯 RepoMap 파이프라인 통합 전략

### L16: RepoMap Stage (New)

```
PHASE 7: Repository Structure (after Phase 3)
├── L16: RepoMap - Repository Map Generation
│   ├── Tree Builder (Chunk → RepoMapNode)
│   ├── PageRank Engine (GraphDocument → Importance)
│   ├── Git History (Optional - Change frequency)
│   └── Incremental Update (Merkle Hash based)
```

**위치**: Phase 3 이후, Phase 4와 병렬 실행 가능

**이유**:
- L2 Chunking 결과 필요 → Phase 2 완료 필수
- L3 CrossFile GraphDocument 필요 → Phase 3 완료 필수
- L10 Points-to 불필요 → Phase 4와 독립적

---

## 🚀 구현 계획

### Step 1: StageControl 확장 (1시간)

```rust
// packages/codegraph-rust/codegraph-ir/src/pipeline/end_to_end_config.rs

#[derive(Debug, Clone)]
pub struct StageControl {
    // ... 기존 스테이지들 ...

    // ═══════════════════════════════════════════════════════════
    // PHASE 7: Repository Structure (after Phase 3)
    // ═══════════════════════════════════════════════════════════

    /// L16: RepoMap - Repository structure and importance map
    pub enable_repomap: bool,
}

impl Default for StageControl {
    fn default() -> Self {
        Self {
            // ... 기존 설정 ...
            enable_repomap: true,  // 기본 활성화
        }
    }
}
```

---

### Step 2: RepoMapConfig 추가 (1시간)

```rust
// packages/codegraph-rust/codegraph-ir/src/pipeline/end_to_end_config.rs

/// RepoMap configuration
#[derive(Debug, Clone)]
pub struct RepoMapConfig {
    /// Enable RepoMap building
    pub enabled: bool,

    /// PageRank settings
    pub pagerank: PageRankSettings,

    /// Git history settings
    pub git_history: GitHistorySettings,

    /// Incremental update settings
    pub incremental: IncrementalSettings,

    /// Summarization settings
    pub summarization: SummarizationSettings,
}

#[derive(Debug, Clone)]
pub struct PageRankSettings {
    /// Damping factor (default: 0.85)
    pub damping: f64,

    /// Max iterations (default: 20)
    pub max_iterations: usize,

    /// Convergence tolerance (default: 1e-6)
    pub tolerance: f64,

    /// Enable Personalized PageRank
    pub enable_personalized: bool,

    /// Enable HITS algorithm
    pub enable_hits: bool,

    /// Combined score weights
    pub weights: ImportanceWeights,
}

#[derive(Debug, Clone)]
pub struct ImportanceWeights {
    pub pagerank: f64,      // 0.5
    pub authority: f64,     // 0.3
    pub degree: f64,        // 0.2
}

#[derive(Debug, Clone)]
pub struct GitHistorySettings {
    /// Enable Git history analysis
    pub enabled: bool,

    /// Days to analyze (default: 90)
    pub days: u32,

    /// Enable code churn tracking
    pub enable_churn: bool,

    /// Enable hot spot detection
    pub enable_hotspots: bool,
}

#[derive(Debug, Clone)]
pub struct IncrementalSettings {
    /// Enable incremental updates
    pub enabled: bool,

    /// Merkle cache size (default: 100,000)
    pub merkle_cache_size: usize,

    /// Max propagation depth for incremental PageRank (default: 2)
    pub max_propagation_depth: usize,
}

#[derive(Debug, Clone)]
pub struct SummarizationSettings {
    /// Enable LLM-based summarization
    pub enabled: bool,

    /// Max summary tokens (default: 500)
    pub max_tokens: usize,

    /// Cost limit per repo (default: $1.00)
    pub cost_limit_usd: f64,
}

impl Default for RepoMapConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            pagerank: PageRankSettings {
                damping: 0.85,
                max_iterations: 20,
                tolerance: 1e-6,
                enable_personalized: true,
                enable_hits: true,
                weights: ImportanceWeights {
                    pagerank: 0.5,
                    authority: 0.3,
                    degree: 0.2,
                },
            },
            git_history: GitHistorySettings {
                enabled: true,
                days: 90,
                enable_churn: true,
                enable_hotspots: true,
            },
            incremental: IncrementalSettings {
                enabled: true,
                merkle_cache_size: 100_000,
                max_propagation_depth: 2,
            },
            summarization: SummarizationSettings {
                enabled: false,  // LLM 비용 때문에 기본 비활성화
                max_tokens: 500,
                cost_limit_usd: 1.0,
            },
        }
    }
}

// E2EPipelineConfig에 추가
#[derive(Debug, Clone)]
pub struct E2EPipelineConfig {
    // ... 기존 필드들 ...

    /// RepoMap configuration
    pub repomap_config: RepoMapConfig,
}
```

---

### Step 3: Orchestrator에 L16 RepoMap 통합 (2-3시간)

```rust
// packages/codegraph-rust/codegraph-ir/src/pipeline/end_to_end_orchestrator.rs

impl IRIndexingOrchestrator {
    pub fn execute(&self) -> Result<E2EPipelineResult, CodegraphError> {
        // ... 기존 Phase 1-6 실행 ...

        // ═══════════════════════════════════════════════════════════════════
        // PHASE 7: Repository Structure (parallel with Phase 4)
        // ═══════════════════════════════════════════════════════════════════

        let repomap_snapshot = if self.config.stages.enable_repomap {
            let start = Instant::now();
            let snapshot = self.execute_l16_repomap(&chunks, &ir_documents)?;
            stats.record_stage("L16_RepoMap", start.elapsed());
            Some(snapshot)
        } else {
            None
        };

        // ... 결과 반환 ...
        Ok(E2EPipelineResult {
            // ... 기존 필드들 ...
            repomap_snapshot,
            stats,
        })
    }

    /// L16: RepoMap - Build repository structure map
    fn execute_l16_repomap(
        &self,
        chunks: &[Chunk],
        ir_documents: &HashMap<String, CrossFileIRDocument>,
    ) -> Result<RepoMapSnapshot, CodegraphError> {
        use crate::features::repomap::infrastructure::{
            RepoMapTreeBuilder,
            PageRankEngine,
            GitHistoryAnalyzer,
        };

        let config = &self.config.repomap_config;

        // Step 1: Build RepoMap Tree (Chunk → RepoMapNode)
        let tree_start = Instant::now();
        let mut builder = RepoMapTreeBuilder::new(
            self.config.repo_info.repo_name.clone(),
            "snapshot-v1".to_string(),
        );

        // Build chunk-to-graph mapping from ir_documents
        let chunk_to_graph = self.build_chunk_to_graph_mapping(chunks, ir_documents);

        // Parallel tree building
        let nodes = builder.build_parallel(chunks, &chunk_to_graph);
        tracing::info!(
            "L16: Built RepoMap tree with {} nodes in {:?}",
            nodes.len(),
            tree_start.elapsed()
        );

        // Step 2: Compute PageRank importance scores
        let pagerank_start = Instant::now();
        let graph_doc = self.build_graph_document(ir_documents);

        let mut pagerank_engine = PageRankEngine::new(&config.pagerank);
        let importance_scores = pagerank_engine.compute_combined_importance(
            &graph_doc,
            &config.pagerank.weights,
        );
        tracing::info!(
            "L16: Computed importance scores for {} nodes in {:?}",
            importance_scores.len(),
            pagerank_start.elapsed()
        );

        // Step 3: Git History Analysis (optional)
        let change_metrics = if config.git_history.enabled {
            let git_start = Instant::now();
            let mut git_analyzer = GitHistoryAnalyzer::new(
                self.config.repo_info.repo_root.clone(),
            );

            let file_paths: Vec<String> = nodes.iter()
                .filter_map(|n| n.file_path.clone())
                .collect::<std::collections::HashSet<_>>()
                .into_iter()
                .collect();

            let metrics = git_analyzer.compute_change_frequency(
                &file_paths,
                config.git_history.days,
            );
            tracing::info!(
                "L16: Analyzed Git history for {} files in {:?}",
                file_paths.len(),
                git_start.elapsed()
            );
            Some(metrics)
        } else {
            None
        };

        // Step 4: Merge all metrics into nodes
        let enriched_nodes = self.merge_repomap_metrics(
            nodes,
            &importance_scores,
            &change_metrics,
        );

        // Step 5: Create snapshot
        let snapshot = RepoMapSnapshot::new(
            self.config.repo_info.repo_name.clone(),
            "snapshot-v1".to_string(),
            enriched_nodes,
        );

        Ok(snapshot)
    }

    /// Build chunk-to-graph mapping (chunk_id → set of related node IDs)
    fn build_chunk_to_graph_mapping(
        &self,
        chunks: &[Chunk],
        ir_documents: &HashMap<String, CrossFileIRDocument>,
    ) -> HashMap<String, HashSet<String>> {
        use std::collections::HashSet;

        let mut mapping = HashMap::new();

        for chunk in chunks {
            let mut related_nodes = HashSet::new();

            // Find nodes in the same file and span range
            if let Some(ir_doc) = ir_documents.get(&chunk.file_path) {
                for node in &ir_doc.nodes {
                    // Check if node is within chunk span
                    if node.span.start_line >= chunk.start_line as u32
                        && node.span.end_line <= chunk.end_line as u32
                    {
                        related_nodes.insert(node.id.clone());
                    }
                }
            }

            mapping.insert(chunk.id.clone(), related_nodes);
        }

        mapping
    }

    /// Build GraphDocument from IRDocuments
    fn build_graph_document(
        &self,
        ir_documents: &HashMap<String, CrossFileIRDocument>,
    ) -> GraphDocument {
        let mut all_nodes = Vec::new();
        let mut all_edges = Vec::new();

        for ir_doc in ir_documents.values() {
            all_nodes.extend(ir_doc.nodes.clone());
            all_edges.extend(ir_doc.edges.clone());
        }

        GraphDocument {
            nodes: all_nodes,
            edges: all_edges,
        }
    }

    /// Merge importance scores and change metrics into nodes
    fn merge_repomap_metrics(
        &self,
        mut nodes: Vec<RepoMapNode>,
        importance_scores: &HashMap<String, ImportanceScore>,
        change_metrics: &Option<HashMap<String, ChangeMetrics>>,
    ) -> Vec<RepoMapNode> {
        for node in &mut nodes {
            // Add importance score
            if let Some(score) = importance_scores.get(&node.id) {
                node.metrics.pagerank = score.combined;
                node.metrics.authority_score = Some(score.authority);
                node.metrics.hub_score = Some(score.hub);
            }

            // Add change frequency
            if let Some(metrics) = change_metrics {
                if let Some(file_path) = &node.file_path {
                    if let Some(change) = metrics.get(file_path) {
                        node.metrics.change_frequency = Some(change.commit_count as f64);
                        node.metrics.last_modified = change.last_modified;
                    }
                }
            }
        }

        nodes
    }
}
```

---

### Step 4: E2EPipelineResult 확장 (30분)

```rust
// packages/codegraph-rust/codegraph-ir/src/pipeline/end_to_end_result.rs

#[derive(Debug, Clone, Default)]
pub struct E2EPipelineResult {
    // ... 기존 필드들 ...

    /// L16: RepoMap snapshot
    pub repomap_snapshot: Option<RepoMapSnapshot>,

    pub stats: PipelineStats,
}
```

---

### Step 5: Storage Adapters (1시간)

```rust
// packages/codegraph-rust/codegraph-ir/src/features/repomap/infrastructure/storage.rs

/// Storage trait for RepoMap snapshots
pub trait RepoMapStorage: Send + Sync {
    fn save_snapshot(&self, snapshot: &RepoMapSnapshot) -> Result<(), StorageError>;
    fn load_snapshot(&self, repo_id: &str, snapshot_id: &str)
        -> Result<Option<RepoMapSnapshot>, StorageError>;
    fn list_snapshots(&self, repo_id: &str) -> Result<Vec<SnapshotMeta>, StorageError>;
}

/// JSON file storage (for development/testing)
pub struct JsonRepoMapStorage {
    base_path: PathBuf,
}

impl RepoMapStorage for JsonRepoMapStorage {
    fn save_snapshot(&self, snapshot: &RepoMapSnapshot) -> Result<(), StorageError> {
        let path = self.snapshot_path(&snapshot.repo_id, &snapshot.snapshot_id);
        let json = serde_json::to_vec_pretty(snapshot)?;
        std::fs::write(&path, json)?;
        Ok(())
    }

    fn load_snapshot(&self, repo_id: &str, snapshot_id: &str)
        -> Result<Option<RepoMapSnapshot>, StorageError> {
        let path = self.snapshot_path(repo_id, snapshot_id);
        if !path.exists() {
            return Ok(None);
        }
        let json = std::fs::read(&path)?;
        let snapshot = serde_json::from_slice(&json)?;
        Ok(Some(snapshot))
    }
}

/// In-memory storage (for testing)
pub struct InMemoryRepoMapStorage {
    snapshots: Arc<RwLock<HashMap<String, RepoMapSnapshot>>>,
}

impl RepoMapStorage for InMemoryRepoMapStorage {
    fn save_snapshot(&self, snapshot: &RepoMapSnapshot) -> Result<(), StorageError> {
        let key = format!("{}:{}", snapshot.repo_id, snapshot.snapshot_id);
        self.snapshots.write().unwrap().insert(key, snapshot.clone());
        Ok(())
    }

    fn load_snapshot(&self, repo_id: &str, snapshot_id: &str)
        -> Result<Option<RepoMapSnapshot>, StorageError> {
        let key = format!("{}:{}", repo_id, snapshot_id);
        Ok(self.snapshots.read().unwrap().get(&key).cloned())
    }
}
```

---

## 🔄 증분 인덱싱 파이프라인 통합

### 현재 증분 인덱싱 구조

```rust
// packages/codegraph-rust/codegraph-ir/src/features/query_engine/infrastructure/incremental_index.rs

pub struct IncrementalIndexManager {
    // 파일 변경 감지
    // Delta 계산
    // 증분 업데이트
}
```

### RepoMap 증분 업데이트 통합

```rust
// packages/codegraph-rust/codegraph-ir/src/pipeline/end_to_end_orchestrator.rs

impl IRIndexingOrchestrator {
    /// Execute incremental update (only changed files)
    pub fn execute_incremental(
        &self,
        changed_files: &[PathBuf],
        base_snapshot: Option<RepoMapSnapshot>,
    ) -> Result<E2EPipelineResult, CodegraphError> {
        let total_start = Instant::now();
        let mut stats = PipelineStats::new();

        // Step 1: Process only changed files (L1-L6)
        let delta_result = self.execute_delta_pipeline(changed_files)?;

        // Step 2: L16 RepoMap Incremental Update
        let repomap_snapshot = if self.config.stages.enable_repomap {
            if let Some(base) = base_snapshot {
                let start = Instant::now();

                // Build deltas
                let chunk_delta = ChunkDelta {
                    added: delta_result.chunks.clone(),
                    modified: Vec::new(),
                    removed: Vec::new(),
                };

                let graph_delta = GraphDelta {
                    added_nodes: delta_result.nodes.clone(),
                    added_edges: delta_result.edges.clone(),
                    removed_nodes: Vec::new(),
                    removed_edges: Vec::new(),
                };

                // Incremental update
                let mut builder = IncrementalRepoMapBuilder::from_snapshot(base);
                let updated = builder.update_incremental(&chunk_delta, &graph_delta);

                stats.record_stage("L16_RepoMap_Incremental", start.elapsed());
                Some(updated)
            } else {
                // No base snapshot - do full build
                let start = Instant::now();
                let snapshot = self.execute_l16_repomap(
                    &delta_result.chunks,
                    &delta_result.ir_documents,
                )?;
                stats.record_stage("L16_RepoMap_Full", start.elapsed());
                Some(snapshot)
            }
        } else {
            None
        };

        stats.total_duration = total_start.elapsed();

        Ok(E2EPipelineResult {
            nodes: delta_result.nodes,
            edges: delta_result.edges,
            chunks: delta_result.chunks,
            repomap_snapshot,
            stats,
            ..Default::default()
        })
    }
}
```

---

## 📈 성능 목표

### 전체 인덱싱 (Full Mode)

| 저장소 크기 | Python (현재) | Rust 목표 | 개선 |
|------------|--------------|-----------|------|
| **1K 파일** | ~3s | ~300ms | 10x |
| **10K 파일** | ~30s | ~3s | 10x |
| **100K 파일** | ~300s | ~30s | 10x |

### 증분 인덱싱 (Incremental Mode)

| 변경 파일 | Python (현재) | Rust 목표 | 개선 |
|----------|--------------|-----------|------|
| **10 파일** | ~300ms | ~30ms | 10x |
| **100 파일** | ~3s | ~300ms | 10x |
| **1K 파일** | ~30s | ~3s | 10x |

**핵심**: Merkle Hash 기반 Delta 감지로 **O(변경)** 복잡도 달성

---

## 📁 디렉토리 구조

```
packages/codegraph-rust/codegraph-ir/src/
├── features/
│   └── repomap/
│       ├── mod.rs
│       ├── domain/
│       │   ├── mod.rs
│       │   ├── models.rs           # RepoMapNode, Metrics, Snapshot
│       │   └── config.rs           # RepoMapConfig, PageRankSettings
│       ├── infrastructure/
│       │   ├── mod.rs
│       │   ├── tree_builder.rs     # 병렬 트리 빌드 (Rayon)
│       │   ├── pagerank.rs         # PageRank + HITS + PPR
│       │   ├── git_history.rs      # 변경 빈도 + Churn
│       │   ├── incremental.rs      # Merkle + Delta 업데이트
│       │   ├── storage_postgres.rs # PostgreSQL 저장소
│       │   └── storage_json.rs     # JSON 저장소
│       └── ports/
│           └── mod.rs              # RepoMapStorage trait
├── pipeline/
│   ├── end_to_end_orchestrator.rs  # L16 RepoMap 통합
│   ├── end_to_end_config.rs        # RepoMapConfig 추가
│   └── end_to_end_result.rs        # repomap_snapshot 필드
└── adapters/
    └── pyo3/
        └── api/
            └── repomap.rs           # Python API
```

---

## ✅ 구현 체크리스트

### Phase 1: 설정 및 구조 (2시간)
- [ ] `StageControl`에 `enable_repomap` 추가
- [ ] `RepoMapConfig` 구조체 정의
- [ ] `E2EPipelineConfig`에 `repomap_config` 추가
- [ ] `E2EPipelineResult`에 `repomap_snapshot` 필드 추가

### Phase 2: Core 구현 (2주)
- [ ] `RepoMapTreeBuilder` - 병렬 트리 빌드
- [ ] `PageRankEngine` - PageRank + HITS + PPR
- [ ] `GitHistoryAnalyzer` - 변경 빈도 분석
- [ ] `IncrementalRepoMapBuilder` - Merkle Delta

### Phase 3: 파이프라인 통합 (1일)
- [ ] `execute_l16_repomap()` 구현
- [ ] `build_chunk_to_graph_mapping()` 구현
- [ ] `merge_repomap_metrics()` 구현
- [ ] 증분 인덱싱 `execute_incremental()` 통합

### Phase 4: Storage (1시간)
- [ ] `RepoMapStorage` trait
- [ ] `JsonRepoMapStorage` 구현
- [ ] `InMemoryRepoMapStorage` 구현
- [ ] Snapshot 직렬화/역직렬화

### Phase 5: 테스트 (2일)
- [ ] Unit tests (각 컴포넌트)
- [ ] Integration tests (파이프라인 E2E)
- [ ] Performance benchmarks (1K, 10K, 100K 파일)
- [ ] Incremental update tests

### Phase 6: 문서화 (1일)
- [ ] Rust API 문서 (rustdoc)
- [ ] 사용 예제 (examples/)
- [ ] 성능 벤치마크 결과
- [ ] 아키텍처 문서

---

## 🔗 기존 파이프라인과의 차이점

### Python 파이프라인 (현재)

```python
# L1-L4: Python IR 빌드
# L5: Python RepoMap (별도 실행)
#   - Tree Builder (순차)
#   - PageRank (rustworkx)
#   - Git History (순차)
```

**문제점**:
- RepoMap이 파이프라인 외부에서 별도 실행
- Python 오버헤드 (순차 처리)
- 증분 업데이트 미지원

### Rust 파이프라인 (목표)

```rust
// L1-L15: Rust IR 빌드 (병렬)
// L16: RepoMap (파이프라인 통합)
//   - Tree Builder (병렬)
//   - PageRank (rustworkx + HITS + PPR)
//   - Git History (병렬)
//   - Incremental (Merkle Delta)
```

**개선점**:
- 파이프라인에 완전 통합
- 전체 병렬 처리 (Rayon)
- 증분 업데이트 지원 (O(변경))
- 10x 성능 향상

---

## 📊 데이터 흐름

```
┌─────────────┐
│  L1: IR     │
│  (Nodes,    │
│   Edges)    │
└──────┬──────┘
       │
       ├──────────────────────────────────┐
       │                                  │
       v                                  v
┌──────────────┐                   ┌──────────────┐
│ L2: Chunking │                   │ L3: CrossFile│
│  (Chunks)    │                   │ (GraphDoc)   │
└──────┬───────┘                   └──────┬───────┘
       │                                  │
       └────────────┬─────────────────────┘
                    │
                    v
             ┌──────────────┐
             │ L16: RepoMap │
             │              │
             │ 1. Tree      │──> RepoMapNode[]
             │ 2. PageRank  │──> ImportanceScore{}
             │ 3. Git       │──> ChangeMetrics{}
             │ 4. Merge     │──> RepoMapSnapshot
             └──────────────┘
```

---

## 🎯 예상 성능

### Tree Building (병렬 vs 순차)

```rust
// Python (순차): O(N log N)
for chunk in chunks:
    node = build_node(chunk)
    aggregate_metrics(node)  # O(log N)

// Rust (병렬): O(N / cores)
chunks.par_iter().map(|chunk| {
    build_node(chunk)
}).collect()

// 레벨별 병렬 메트릭 집계: O(depth)
```

**예상**: **10-20x faster**

### PageRank (알고리즘 개선)

```rust
// Python: Standard PageRank only
pagerank(graph)

// Rust: PageRank + HITS + PPR
pagerank + hits + personalized_pagerank
// Combined score with weighted fusion
```

**예상**: 속도 유사, **정확도 향상**

### Incremental Update (Merkle vs Full)

```rust
// Python: Full rebuild - O(N)
rebuild_all_nodes()

// Rust: Merkle Delta - O(변경)
detect_changes_merkle()  // O(변경)
rebuild_affected_nodes()  // O(변경)
```

**예상**: **50-100x faster** (1% 변경 시)

---

---

## 📊 성능 벤치마크 계획

### 테스트 저장소

| 저장소 | 파일 수 | LOC | 설명 |
|--------|---------|-----|------|
| **Small** | 100 | 10K | 단위 테스트 |
| **Medium** | 1K | 100K | 통합 테스트 |
| **Large** | 10K | 1M | 성능 테스트 |
| **XLarge** | 100K | 10M | Stress 테스트 |

### 측정 메트릭

1. **Tree Build Time** (ms)
2. **PageRank Time** (ms)
3. **Git History Time** (ms)
4. **Total Time** (ms)
5. **Memory Usage** (MB)
6. **Incremental Update Time** (ms)

---

## 🚀 Rust 실행 예제

### 파이프라인에서 사용

```rust
let config = E2EPipelineConfig {
    stages: StageControl {
        enable_repomap: true,
        ..Default::default()
    },
    repomap_config: RepoMapConfig {
        pagerank: PageRankSettings {
            enable_personalized: true,
            enable_hits: true,
            ..Default::default()
        },
        ..Default::default()
    },
    ..Default::default()
};

let orchestrator = IRIndexingOrchestrator::new(config);
let result = orchestrator.execute()?;

if let Some(snapshot) = result.repomap_snapshot {
    println!("RepoMap built with {} nodes", snapshot.nodes.len());
}
```

---

### 직접 RepoMap만 실행

```rust
use codegraph_ir::features::repomap::infrastructure::{
    RepoMapTreeBuilder,
    PageRankEngine,
    IncrementalRepoMapBuilder,
};

// Full build
let mut builder = RepoMapTreeBuilder::new("repo".to_string(), "v1".to_string());
let chunk_to_graph = build_chunk_to_graph_mapping(&chunks, &graph_doc);
let nodes = builder.build_parallel(&chunks, &chunk_to_graph);

// Compute importance
let mut engine = PageRankEngine::new(&config.pagerank);
let scores = engine.compute_combined_importance(&graph_doc, &weights);

// Create snapshot
let snapshot = RepoMapSnapshot::new("repo".to_string(), "v1".to_string(), nodes);

// Incremental update
let mut incremental = IncrementalRepoMapBuilder::from_snapshot(snapshot);
let updated = incremental.update_incremental(&chunk_delta, &graph_delta);
```

---

## 📋 요약

| 항목 | 내용 |
|------|------|
| **위치** | Phase 7 (L16 RepoMap) - Phase 3 이후 |
| **의존성** | L2 Chunking, L3 CrossFile |
| **병렬화** | Phase 4와 병렬 실행 가능 |
| **구현 기간** | 2.5주 (Core 2주 + 통합 0.5주) |
| **성능 목표** | 10-100x faster |
| **증분 지원** | Merkle Hash - O(변경) |

**핵심 장점**:
1. **파이프라인 완전 통합** - 별도 실행 불필요
2. **병렬 처리** - Rayon work-stealing
3. **증분 업데이트** - Merkle Delta (50-100x)
4. **SOTA 알고리즘** - PPR + HITS + Combined
5. **Pure Rust** - Zero Python overhead

**Last Updated**: 2025-12-28
**Author**: Claude Sonnet 4.5
**Status**: Ready for Implementation
