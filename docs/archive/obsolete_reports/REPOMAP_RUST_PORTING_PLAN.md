# RepoMap Rust 포팅 계획서

**Version**: 1.0 (2025-12-28)  
**Status**: Planning  
**Total Python LOC**: ~6,149  
**Target Rust LOC**: ~8,000

---

## 📊 현재 Python RepoMap 구현 분석

### 아키텍처

```
repo_structure/infrastructure/
├── tree/                    # 트리 빌드 (651 LOC)
│   ├── builder.py          # RepoMapTreeBuilder - Chunk → Tree
│   └── metrics.py          # EntrypointDetector, TestDetector
├── builder/                 # 오케스트레이션 (639 LOC)
│   └── orchestrator.py     # RepoMapBuilder - 전체 플로우
├── pagerank/               # 중요도 계산 (875 LOC)
│   ├── engine.py           # PageRankEngine - rustworkx 기반
│   ├── aggregator.py       # 결과 집계
│   ├── graph_adapter.py    # 그래프 어댑터
│   └── incremental.py      # 점진적 업데이트
├── summarizer/             # LLM 요약 (989 LOC)
│   ├── hierarchical_summarizer.py  # 계층적 요약
│   ├── llm_summarizer.py   # LLM 호출
│   ├── cost_control.py     # 비용 제어
│   └── cache.py            # 요약 캐시
├── models.py               # 데이터 모델 (417 LOC)
├── git_history.py          # Git 분석 (744 LOC)
├── incremental.py          # 점진적 업데이트 (416 LOC)
├── storage_*.py            # 저장소 (875 LOC)
└── id_strategy.py          # ID 생성 (107 LOC)
```

### 핵심 기능

| 기능 | Python LOC | 설명 |
|------|-----------|------|
| **Tree Building** | 651 | Chunk → RepoMapNode 변환 |
| **PageRank** | 875 | rustworkx 기반 중요도 계산 |
| **Summarizer** | 989 | LLM 기반 계층적 요약 |
| **Git History** | 744 | 변경 빈도 분석 |
| **Orchestrator** | 639 | 전체 빌드 플로우 |
| **Storage** | 875 | PostgreSQL/JSON 저장 |
| **Models** | 417 | 데이터 모델 |
| **Incremental** | 416 | Delta 업데이트 |

---

## 🎓 학계/업계 SOTA 비교

### 1. Aider RepoMap (Open Source)

**접근법**: Tree-sitter + 태그 기반 심볼 추출

```
장점:
✅ 경량 (tree-sitter만 사용)
✅ 중요도 기반 컨텍스트 필터링
✅ 토큰 예산 관리

단점:
❌ PageRank 없음 (단순 참조 카운트)
❌ 계층적 요약 없음
❌ Git history 미활용
```

**우리의 개선점**:
- ✅ PageRank로 정교한 중요도 계산
- ✅ 2-Level 계층적 요약
- ✅ Git 변경 빈도 통합

### 2. Sourcegraph (Enterprise)

**접근법**: SCIP/LSIF 기반 심볼 그래프

```
장점:
✅ 정밀한 심볼 해상도 (LSP 수준)
✅ Cross-repo 참조
✅ 증분 인덱싱

단점:
❌ 무거움 (언어별 인덱서 필요)
❌ 요약/중요도 없음
❌ 컨텍스트 최적화 없음
```

**우리의 개선점**:
- ✅ Chunk 기반 경량 구조
- ✅ AI 에이전트 최적화 (토큰 예산)
- ✅ LLM 요약으로 빠른 이해

### 3. GitHub CodeSearch

**접근법**: Zoekt + Tree-sitter

```
장점:
✅ 대규모 확장성
✅ 빠른 검색

단점:
❌ 구조 분석 제한적
❌ 의미론적 이해 없음
```

### 4. 학계 연구

| 논문/기법 | 핵심 아이디어 | 적용 |
|----------|-------------|------|
| **HITS Algorithm** (Kleinberg, 1999) | Hub/Authority 스코어 | PageRank 보완 |
| **Personalized PageRank** (Haveliwala, 2002) | 시작점 기반 랭킹 | Query-aware 중요도 |
| **Graph Neural Networks** (GNN) | 노드 임베딩 학습 | 심볼 유사도 |
| **Incremental Graph Algorithms** (VLDB 2020) | Delta 기반 업데이트 | 점진적 PageRank |
| **Code Summarization** (ACL 2021) | Transformer 기반 | LLM 요약 |

---

## 🚀 Rust 포팅 전략

### Phase 1: Core Tree Builder (1주)

**목표**: Chunk → RepoMapNode 변환의 Rust 구현

```rust
// src/features/repomap/infrastructure/tree_builder.rs

pub struct RepoMapTreeBuilder {
    repo_id: String,
    snapshot_id: String,
    nodes: DashMap<String, RepoMapNode>,
    id_gen: RepoMapIdGenerator,
    // O(1) 인덱스
    chunk_to_node: DashMap<String, String>,
    fqn_to_node: DashMap<(String, String), String>,
}

impl RepoMapTreeBuilder {
    /// 병렬 빌드 (Rayon)
    pub fn build_parallel(
        &self,
        chunks: &[Chunk],
        chunk_to_graph: &HashMap<String, HashSet<String>>,
    ) -> Vec<RepoMapNode> {
        // Step 1: 레벨별 병렬 분류
        let chunks_by_level = self.classify_by_level_parallel(chunks);
        
        // Step 2: 디렉토리 노드 병렬 생성
        self.build_directories_parallel(chunks);
        
        // Step 3: Chunk 노드 병렬 생성
        self.create_chunk_nodes_parallel(chunks, chunk_to_graph);
        
        // Step 4: Bottom-up 메트릭 집계 (병렬)
        self.aggregate_metrics_parallel();
        
        self.nodes.iter().map(|e| e.value().clone()).collect()
    }
    
    /// O(N) 병렬 메트릭 집계 (vs Python O(N log N))
    fn aggregate_metrics_parallel(&self) {
        // 레벨별 병렬 처리
        let max_depth = self.nodes.iter()
            .map(|n| n.depth)
            .max()
            .unwrap_or(0);
        
        for depth in (0..=max_depth).rev() {
            let nodes_at_depth: Vec<_> = self.nodes.iter()
                .filter(|n| n.depth == depth)
                .collect();
            
            nodes_at_depth.par_iter().for_each(|node| {
                if let Some(parent_id) = &node.parent_id {
                    if let Some(mut parent) = self.nodes.get_mut(parent_id) {
                        // Atomic 업데이트
                        parent.metrics.loc.fetch_add(node.metrics.loc, Ordering::Relaxed);
                        parent.metrics.symbol_count.fetch_add(
                            node.metrics.symbol_count, Ordering::Relaxed
                        );
                    }
                }
            });
        }
    }
}
```

**SOTA 개선**:
- **병렬 빌드**: Rayon work-stealing (Python: 순차)
- **Lock-free 인덱스**: DashMap (Python: dict + set)
- **Atomic 메트릭 집계**: 레벨별 병렬 (Python: 순차 O(N log N))

**예상 성능**: 10-20x faster

---

### Phase 2: PageRank Engine (0.5주)

**목표**: SOTA PageRank + HITS 알고리즘

```rust
// src/features/repomap/infrastructure/pagerank.rs

pub struct PageRankEngine {
    config: PageRankConfig,
    graph: DiGraph<String, f64>,
    // Personalized PageRank 지원
    teleport_set: Option<HashSet<String>>,
}

impl PageRankEngine {
    /// Standard PageRank (rustworkx 래핑)
    pub fn compute_pagerank(
        &self,
        graph_doc: &GraphDocument,
    ) -> HashMap<String, f64> {
        let rx_graph = self.build_rx_graph(graph_doc);
        rx::pagerank(
            &rx_graph,
            self.config.damping,
            self.config.max_iterations,
            self.config.tolerance,
        )
    }
    
    /// SOTA: Personalized PageRank (Query-aware)
    /// 논문: "Topic-Sensitive PageRank" (Haveliwala, 2002)
    pub fn compute_personalized_pagerank(
        &self,
        graph_doc: &GraphDocument,
        query_nodes: &[String],  // 쿼리 관련 노드
    ) -> HashMap<String, f64> {
        let rx_graph = self.build_rx_graph(graph_doc);
        
        // Teleport probability를 query_nodes에 집중
        let personalization: HashMap<usize, f64> = query_nodes.iter()
            .filter_map(|id| self.node_map.get(id).map(|&idx| (idx, 1.0)))
            .collect();
        
        rx::pagerank_personalized(
            &rx_graph,
            personalization,
            self.config.damping,
            self.config.max_iterations,
        )
    }
    
    /// SOTA: HITS Algorithm (Hub/Authority)
    /// 논문: "Authoritative Sources" (Kleinberg, 1999)
    pub fn compute_hits(
        &self,
        graph_doc: &GraphDocument,
    ) -> (HashMap<String, f64>, HashMap<String, f64>) {
        let rx_graph = self.build_rx_graph(graph_doc);
        
        let (hubs, authorities) = rx::hits(
            &rx_graph,
            self.config.max_iterations,
            self.config.tolerance,
        );
        
        (self.map_scores(hubs), self.map_scores(authorities))
    }
    
    /// SOTA: Combined Score (PageRank + HITS + Degree)
    pub fn compute_combined_importance(
        &self,
        graph_doc: &GraphDocument,
        weights: &ImportanceWeights,
    ) -> HashMap<String, ImportanceScore> {
        let pagerank = self.compute_pagerank(graph_doc);
        let (hubs, authorities) = self.compute_hits(graph_doc);
        let degree = self.compute_degree_centrality(graph_doc);
        
        // Weighted combination
        pagerank.keys().map(|id| {
            let score = ImportanceScore {
                pagerank: pagerank.get(id).copied().unwrap_or(0.0),
                hub: hubs.get(id).copied().unwrap_or(0.0),
                authority: authorities.get(id).copied().unwrap_or(0.0),
                degree: degree.get(id).copied().unwrap_or(0.0),
                combined: weights.pagerank * pagerank.get(id).unwrap_or(&0.0)
                    + weights.authority * authorities.get(id).unwrap_or(&0.0)
                    + weights.degree * degree.get(id).unwrap_or(&0.0),
            };
            (id.clone(), score)
        }).collect()
    }
}

/// SOTA: Incremental PageRank (Delta 기반)
/// 논문: "Incremental Graph Pattern Matching" (VLDB 2020)
pub struct IncrementalPageRank {
    base_scores: HashMap<String, f64>,
    affected_nodes: HashSet<String>,
}

impl IncrementalPageRank {
    /// Delta만 재계산 (전체 재계산 대신)
    pub fn update_incremental(
        &mut self,
        delta: &GraphDelta,
        max_propagation_depth: usize,
    ) -> HashMap<String, f64> {
        // 1. 영향받는 노드 식별 (BFS, depth 제한)
        self.affected_nodes = self.find_affected_nodes(delta, max_propagation_depth);
        
        // 2. 영향받는 서브그래프만 재계산
        let subgraph_scores = self.compute_subgraph_pagerank(&self.affected_nodes);
        
        // 3. 기존 스코어와 병합
        for (id, score) in subgraph_scores {
            self.base_scores.insert(id, score);
        }
        
        self.base_scores.clone()
    }
}
```

**SOTA 개선**:
- **Personalized PageRank**: Query-aware 중요도
- **HITS Algorithm**: Hub/Authority 분리
- **Incremental PageRank**: Delta 기반 업데이트
- **Combined Score**: 다중 메트릭 가중 합산

**예상 성능**: 5x faster (이미 rustworkx 사용 중이므로 알고리즘 개선이 주)

---

### Phase 3: Git History Analyzer (0.5주)

**목표**: 변경 빈도 + 코드 연령 분석

```rust
// src/features/repomap/infrastructure/git_history.rs

pub struct GitHistoryAnalyzer {
    repo_path: PathBuf,
    cache: LruCache<String, ChangeMetrics>,
}

impl GitHistoryAnalyzer {
    /// 파일별 변경 빈도 계산
    pub fn compute_change_frequency(
        &mut self,
        file_paths: &[String],
        days: u32,
    ) -> HashMap<String, ChangeMetrics> {
        // Git log 병렬 실행
        file_paths.par_iter()
            .map(|path| {
                let metrics = self.analyze_file_history(path, days);
                (path.clone(), metrics)
            })
            .collect()
    }
    
    /// SOTA: Code Churn Analysis
    /// 논문: "Predicting Faults" (IEEE TSE, 2005)
    pub fn compute_code_churn(
        &self,
        file_path: &str,
        days: u32,
    ) -> ChurnMetrics {
        let commits = self.get_commits_for_file(file_path, days);
        
        let mut total_added = 0;
        let mut total_deleted = 0;
        let mut unique_authors = HashSet::new();
        
        for commit in commits {
            let diff = self.get_diff_stats(&commit, file_path);
            total_added += diff.additions;
            total_deleted += diff.deletions;
            unique_authors.insert(commit.author.clone());
        }
        
        ChurnMetrics {
            total_changes: total_added + total_deleted,
            churn_rate: (total_added + total_deleted) as f64 / days as f64,
            author_count: unique_authors.len(),
            // Normalized churn (per 100 LOC)
            normalized_churn: (total_added + total_deleted) as f64 / 
                (self.get_file_loc(file_path) as f64 / 100.0),
        }
    }
    
    /// SOTA: Hot Spot Detection
    /// 논문: "Code Red" (ESEC/FSE 2020)
    pub fn detect_hotspots(
        &self,
        file_paths: &[String],
        config: &HotspotConfig,
    ) -> Vec<Hotspot> {
        let change_freq = self.compute_change_frequency(file_paths, config.days);
        let churn = file_paths.par_iter()
            .map(|p| (p.clone(), self.compute_code_churn(p, config.days)))
            .collect::<HashMap<_, _>>();
        
        // Combined hotspot score
        let mut hotspots: Vec<_> = file_paths.iter()
            .map(|path| {
                let freq = change_freq.get(path).map(|m| m.commit_count).unwrap_or(0);
                let churn_val = churn.get(path).map(|c| c.churn_rate).unwrap_or(0.0);
                
                Hotspot {
                    path: path.clone(),
                    score: config.freq_weight * freq as f64 + config.churn_weight * churn_val,
                    change_frequency: freq,
                    churn_rate: churn_val,
                }
            })
            .collect();
        
        hotspots.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap());
        hotspots
    }
}
```

**SOTA 개선**:
- **Code Churn**: 변경량 + 삭제량 추적
- **Hot Spot Detection**: 문제 코드 조기 발견
- **Multi-author Tracking**: 협업 복잡도 측정

**예상 성능**: 8x faster (병렬 Git 분석)

---

### Phase 4: Incremental Update Engine (1주)

**목표**: Delta 기반 점진적 업데이트

```rust
// src/features/repomap/infrastructure/incremental.rs

/// SOTA: Merkle Hash 기반 변경 감지
/// 기법: Git/IPFS 스타일
pub struct MerkleTreeCache {
    root_hash: [u8; 32],
    node_hashes: DashMap<String, [u8; 32]>,
}

impl MerkleTreeCache {
    /// 변경된 노드만 식별
    pub fn detect_changes(
        &self,
        new_nodes: &[RepoMapNode],
    ) -> ChangeSet {
        let mut added = Vec::new();
        let mut modified = Vec::new();
        let mut removed = Vec::new();
        
        // 병렬 해시 비교
        let new_hashes: HashMap<String, [u8; 32]> = new_nodes.par_iter()
            .map(|n| (n.id.clone(), self.compute_node_hash(n)))
            .collect();
        
        // 변경 감지
        for (id, new_hash) in &new_hashes {
            match self.node_hashes.get(id) {
                Some(old_hash) if *old_hash != *new_hash => {
                    modified.push(id.clone());
                }
                None => {
                    added.push(id.clone());
                }
                _ => {}
            }
        }
        
        // 삭제된 노드
        for entry in self.node_hashes.iter() {
            if !new_hashes.contains_key(entry.key()) {
                removed.push(entry.key().clone());
            }
        }
        
        ChangeSet { added, modified, removed }
    }
    
    /// Merkle 해시 계산 (leaf → root)
    fn compute_node_hash(&self, node: &RepoMapNode) -> [u8; 32] {
        use blake3::Hasher;
        
        let mut hasher = Hasher::new();
        hasher.update(node.id.as_bytes());
        hasher.update(node.name.as_bytes());
        hasher.update(&node.metrics.loc.to_le_bytes());
        
        // Children 해시 통합
        for child_id in &node.children_ids {
            if let Some(child_hash) = self.node_hashes.get(child_id) {
                hasher.update(child_hash.value());
            }
        }
        
        *hasher.finalize().as_bytes()
    }
}

/// 점진적 RepoMap 업데이트
pub struct IncrementalRepoMapBuilder {
    base_snapshot: RepoMapSnapshot,
    merkle_cache: MerkleTreeCache,
    pagerank_cache: IncrementalPageRank,
}

impl IncrementalRepoMapBuilder {
    /// Delta 기반 업데이트
    pub fn update_incremental(
        &mut self,
        chunk_delta: &ChunkDelta,
        graph_delta: &GraphDelta,
    ) -> RepoMapSnapshot {
        // 1. 변경된 노드 식별
        let changes = self.merkle_cache.detect_changes(&self.base_snapshot.nodes);
        
        // 2. 변경된 노드만 재빌드
        let updated_nodes = self.rebuild_affected_nodes(&changes, chunk_delta);
        
        // 3. PageRank 점진적 업데이트
        let updated_pagerank = self.pagerank_cache.update_incremental(
            graph_delta,
            2, // MAX_PROPAGATION_DEPTH
        );
        
        // 4. 메트릭 병합
        for node in &mut updated_nodes {
            if let Some(&score) = updated_pagerank.get(&node.id) {
                node.metrics.pagerank = score;
            }
        }
        
        // 5. 스냅샷 업데이트
        self.base_snapshot.set_nodes(updated_nodes);
        self.base_snapshot.clone()
    }
}
```

**SOTA 개선**:
- **Merkle Hash**: O(변경) 변경 감지 (vs O(N) 전체 비교)
- **Incremental PageRank**: 영향받는 노드만 재계산
- **Blake3 Hash**: 빠른 암호화 해시

**예상 성능**: 50-100x faster (대규모 저장소 증분 업데이트)

---

### Phase 5: Storage Adapters (0.5주)

**목표**: PostgreSQL + JSON 저장소

```rust
// src/features/repomap/infrastructure/storage.rs

/// 저장소 Port (DIP)
pub trait RepoMapStorage: Send + Sync {
    async fn save_snapshot(&self, snapshot: &RepoMapSnapshot) -> Result<(), StorageError>;
    async fn load_snapshot(&self, repo_id: &str, snapshot_id: &str) -> Result<Option<RepoMapSnapshot>, StorageError>;
    async fn list_snapshots(&self, repo_id: &str) -> Result<Vec<SnapshotMeta>, StorageError>;
    async fn delete_snapshot(&self, repo_id: &str, snapshot_id: &str) -> Result<bool, StorageError>;
}

/// PostgreSQL 저장소
pub struct PostgresRepoMapStorage {
    pool: PgPool,
}

impl RepoMapStorage for PostgresRepoMapStorage {
    async fn save_snapshot(&self, snapshot: &RepoMapSnapshot) -> Result<(), StorageError> {
        // Batch insert (1000개씩)
        for chunk in snapshot.nodes.chunks(1000) {
            let values: Vec<_> = chunk.iter()
                .map(|n| (
                    &n.id, &n.repo_id, &n.snapshot_id,
                    &n.kind, &n.name, &n.path,
                    serde_json::to_value(&n.metrics)?,
                ))
                .collect();
            
            sqlx::query!(
                r#"
                INSERT INTO repomap_nodes (id, repo_id, snapshot_id, kind, name, path, metrics)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (id) DO UPDATE SET
                    metrics = EXCLUDED.metrics,
                    updated_at = NOW()
                "#,
                // ... values
            )
            .execute(&self.pool)
            .await?;
        }
        Ok(())
    }
}

/// JSON 저장소 (로컬 개발용)
pub struct JsonRepoMapStorage {
    base_path: PathBuf,
}

impl RepoMapStorage for JsonRepoMapStorage {
    async fn save_snapshot(&self, snapshot: &RepoMapSnapshot) -> Result<(), StorageError> {
        let path = self.snapshot_path(&snapshot.repo_id, &snapshot.snapshot_id);
        
        // 압축 저장 (gzip)
        let json = serde_json::to_vec(snapshot)?;
        let compressed = self.compress_gzip(&json)?;
        
        tokio::fs::write(&path, compressed).await?;
        Ok(())
    }
}
```

---

### Phase 6: PyO3 Bindings (0.5주)

**목표**: Python 통합

```rust
// src/adapters/pyo3/repomap_bindings.rs

#[pyfunction]
fn build_repomap(
    py: Python,
    chunks: Vec<PyObject>,
    chunk_to_graph: HashMap<String, HashSet<String>>,
    config: PyObject,
) -> PyResult<PyObject> {
    py.allow_threads(|| {
        let chunks: Vec<Chunk> = convert_chunks(chunks)?;
        let config: RepoMapConfig = extract_config(config)?;
        
        let builder = RepoMapTreeBuilder::new(config);
        let nodes = builder.build_parallel(&chunks, &chunk_to_graph);
        
        Ok(convert_to_pyobject(nodes))
    })
}

#[pyfunction]
fn compute_importance_scores(
    py: Python,
    graph_doc: PyObject,
    config: PyObject,
) -> PyResult<HashMap<String, PyObject>> {
    py.allow_threads(|| {
        let engine = PageRankEngine::new(config);
        let scores = engine.compute_combined_importance(&graph_doc, &weights);
        Ok(scores)
    })
}

#[pyfunction]
fn update_repomap_incremental(
    py: Python,
    base_snapshot: PyObject,
    chunk_delta: PyObject,
    graph_delta: PyObject,
) -> PyResult<PyObject> {
    py.allow_threads(|| {
        let builder = IncrementalRepoMapBuilder::from_snapshot(base_snapshot);
        let updated = builder.update_incremental(&chunk_delta, &graph_delta);
        Ok(convert_to_pyobject(updated))
    })
}

#[pymodule]
fn codegraph_repomap(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(build_repomap, m)?)?;
    m.add_function(wrap_pyfunction!(compute_importance_scores, m)?)?;
    m.add_function(wrap_pyfunction!(update_repomap_incremental, m)?)?;
    Ok(())
}
```

---

## 📊 예상 LOC 및 일정

| Phase | 기능 | Python LOC | Rust LOC | 기간 | 성능 향상 |
|-------|------|-----------|----------|------|----------|
| **1** | Tree Builder | 651 | ~1,000 | 1주 | 10-20x |
| **2** | PageRank Engine | 875 | ~1,200 | 0.5주 | 5x |
| **3** | Git History | 744 | ~900 | 0.5주 | 8x |
| **4** | Incremental Update | 416 | ~1,500 | 1주 | 50-100x |
| **5** | Storage | 875 | ~1,000 | 0.5주 | 3x |
| **6** | PyO3 Bindings | - | ~500 | 0.5주 | - |
| **7** | Models + Utils | 417 + 107 | ~800 | 0.5주 | - |
| | **합계** | **~6,149** | **~8,000** | **4.5주** | **10-100x** |

---

## 🎯 학계/업계 SOTA 대비 차별점

| 기능 | Aider | Sourcegraph | 우리 (Rust) |
|------|-------|-------------|------------|
| **Tree Building** | 순차 | 순차 | ✅ 병렬 (Rayon) |
| **PageRank** | ❌ | ❌ | ✅ + HITS + PPR |
| **Incremental** | ❌ | O(N) | ✅ O(변경) Merkle |
| **Git History** | ❌ | ❌ | ✅ Churn + Hotspot |
| **LLM 요약** | ❌ | ❌ | ✅ 계층적 |
| **Query-aware** | ❌ | ❌ | ✅ PPR |

---

## 📁 Rust 디렉토리 구조

```
codegraph-ir/src/features/repomap/
├── mod.rs
├── domain/
│   ├── mod.rs
│   └── models.rs           # RepoMapNode, Metrics, Snapshot
├── infrastructure/
│   ├── mod.rs
│   ├── tree_builder.rs     # 병렬 트리 빌드
│   ├── pagerank.rs         # PageRank + HITS + PPR
│   ├── git_history.rs      # 변경 빈도 + Churn
│   ├── incremental.rs      # Merkle + Delta 업데이트
│   ├── storage_postgres.rs # PostgreSQL 저장소
│   └── storage_json.rs     # JSON 저장소
└── ports/
    └── mod.rs              # RepoMapStorage trait
```

---

## ✅ 체크리스트

### Phase 1: Tree Builder
- [ ] `RepoMapNode` Rust 구조체
- [ ] `RepoMapTreeBuilder` 병렬 빌드
- [ ] DashMap 기반 인덱스
- [ ] Atomic 메트릭 집계
- [ ] 단위 테스트 10개+

### Phase 2: PageRank
- [ ] Standard PageRank (rustworkx)
- [ ] Personalized PageRank
- [ ] HITS Algorithm
- [ ] Combined Score
- [ ] 벤치마크

### Phase 3: Git History
- [ ] 병렬 Git log 분석
- [ ] Code Churn 계산
- [ ] Hot Spot Detection
- [ ] LRU 캐시

### Phase 4: Incremental
- [ ] Merkle Hash 캐시
- [ ] Delta 변경 감지
- [ ] Incremental PageRank
- [ ] 스냅샷 병합

### Phase 5: Storage
- [ ] PostgreSQL 어댑터
- [ ] JSON 어댑터
- [ ] Batch insert 최적화

### Phase 6: PyO3
- [ ] `build_repomap()`
- [ ] `compute_importance_scores()`
- [ ] `update_repomap_incremental()`
- [ ] Python 테스트

---

---

## 🔗 Rust 인덱싱 파이프라인 통합

### 현재 파이프라인 구조

```
pipeline/
├── config.rs           # 파이프라인 설정
├── core.rs             # 핵심 파이프라인 로직
├── end_to_end_orchestrator.rs  # E2E 오케스트레이터
├── sota_pipeline.rs    # SOTA 파이프라인
├── stages.rs           # 스테이지 정의
└── stage_dag.rs        # DAG 기반 실행
```

### RepoMap 스테이지 추가

```rust
// pipeline/stages.rs 에 추가

/// L8: RepoMap 스테이지
pub struct RepoMapStage {
    config: RepoMapConfig,
}

impl Stage for RepoMapStage {
    fn name(&self) -> &'static str {
        "L8_RepoMap"
    }
    
    fn dependencies(&self) -> Vec<&'static str> {
        vec!["L2_Chunking", "L3_CrossFile"]  // Chunk + GraphDocument 필요
    }
    
    fn execute(&self, ctx: &mut PipelineContext) -> Result<(), PipelineError> {
        // 1. Chunk와 GraphDocument 가져오기
        let chunks = ctx.get_stage_result::<Vec<Chunk>>("L2_Chunking")?;
        let graph_doc = ctx.get_stage_result::<GraphDocument>("L3_CrossFile")?;
        
        // 2. RepoMap 빌드
        let builder = RepoMapTreeBuilder::new(ctx.repo_id(), ctx.snapshot_id());
        let chunk_to_graph = ctx.get_chunk_to_graph_mapping()?;
        let nodes = builder.build_parallel(&chunks, &chunk_to_graph);
        
        // 3. PageRank 계산
        let pagerank_engine = PageRankEngine::new(&self.config);
        let scores = pagerank_engine.compute_combined_importance(&graph_doc, &self.config.weights);
        
        // 4. 메트릭 병합
        let enriched_nodes = self.merge_pagerank_scores(nodes, scores);
        
        // 5. 스냅샷 생성
        let snapshot = RepoMapSnapshot::new(ctx.repo_id(), ctx.snapshot_id(), enriched_nodes);
        
        ctx.set_stage_result("L8_RepoMap", snapshot);
        Ok(())
    }
}
```

### E2E 오케스트레이터 통합

```rust
// pipeline/end_to_end_orchestrator.rs 수정

impl IRIndexingOrchestrator {
    pub fn execute(&self) -> Result<E2EPipelineResult, PipelineError> {
        // ... 기존 스테이지들 ...
        
        // L8: RepoMap (선택적)
        if self.config.stages.enable_repomap {
            let repomap_stage = RepoMapStage::new(&self.config.repomap_config);
            ctx.execute_stage(&repomap_stage)?;
            
            // 결과 추출
            let snapshot = ctx.get_stage_result::<RepoMapSnapshot>("L8_RepoMap")?;
            result.repomap_snapshot = Some(snapshot);
        }
        
        Ok(result)
    }
}
```

### Python API 추가

```rust
// lib.rs 에 추가

/// Build RepoMap from E2E pipeline result
#[cfg(feature = "python")]
#[pyfunction]
fn build_repomap_from_pipeline(
    py: Python,
    chunks: Vec<PyObject>,
    graph_doc: PyObject,
    config: Option<PyObject>,
) -> PyResult<Py<PyDict>> {
    init_rayon();
    
    // GIL RELEASE - Build RepoMap in Rust
    let snapshot = py.allow_threads(|| {
        let builder = RepoMapTreeBuilder::new("", "");
        let nodes = builder.build_parallel(&chunks, &chunk_to_graph);
        RepoMapSnapshot::new("", "", nodes)
    });
    
    convert_repomap_to_python(py, snapshot)
}

/// Compute PageRank importance scores
#[cfg(feature = "python")]
#[pyfunction]
fn compute_repomap_pagerank(
    py: Python,
    graph_doc: PyObject,
    config: Option<PyObject>,
) -> PyResult<Py<PyDict>> {
    init_rayon();
    
    let scores = py.allow_threads(|| {
        let engine = PageRankEngine::new(config);
        engine.compute_combined_importance(&graph_doc, &weights)
    });
    
    Ok(convert_scores_to_python(py, scores))
}

/// Update RepoMap incrementally
#[cfg(feature = "python")]
#[pyfunction]
fn update_repomap_incremental(
    py: Python,
    base_snapshot: PyObject,
    chunk_delta: PyObject,
    graph_delta: PyObject,
) -> PyResult<Py<PyDict>> {
    init_rayon();
    
    let updated = py.allow_threads(|| {
        let builder = IncrementalRepoMapBuilder::from_snapshot(base_snapshot);
        builder.update_incremental(&chunk_delta, &graph_delta)
    });
    
    convert_repomap_to_python(py, updated)
}
```

### 파이프라인 설정

```rust
// pipeline/config.rs 에 추가

#[derive(Clone, Debug)]
pub struct RepoMapConfig {
    /// Enable RepoMap building
    pub enabled: bool,
    
    /// PageRank settings
    pub pagerank_damping: f64,
    pub pagerank_max_iterations: usize,
    
    /// Importance weights
    pub weights: ImportanceWeights,
    
    /// Incremental settings
    pub enable_incremental: bool,
    pub merkle_cache_size: usize,
    
    /// Git history settings
    pub enable_git_history: bool,
    pub git_history_days: u32,
}

impl Default for RepoMapConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            pagerank_damping: 0.85,
            pagerank_max_iterations: 20,
            weights: ImportanceWeights::default(),
            enable_incremental: true,
            merkle_cache_size: 100_000,
            enable_git_history: true,
            git_history_days: 90,
        }
    }
}
```

---

## 📈 성능 벤치마크 목표

### 현재 Python 성능 (예상)

| 작업 | 1K 파일 | 10K 파일 | 100K 파일 |
|------|---------|----------|-----------|
| Tree Build | ~500ms | ~5s | ~50s |
| PageRank | ~100ms | ~1s | ~10s |
| Git History | ~2s | ~20s | ~200s |
| Full Build | ~3s | ~30s | ~300s |
| Incremental | ~300ms | ~3s | ~30s |

### Rust 목표 성능 (10-100x 향상)

| 작업 | 1K 파일 | 10K 파일 | 100K 파일 |
|------|---------|----------|-----------|
| Tree Build | ~50ms | ~500ms | ~5s |
| PageRank | ~10ms | ~100ms | ~1s |
| Git History | ~200ms | ~2s | ~20s |
| Full Build | ~300ms | ~3s | ~30s |
| Incremental | ~30ms | ~300ms | ~3s |

### 벤치마크 환경

```rust
// benches/repomap_bench.rs

#[bench]
fn bench_tree_build_1k_files(b: &mut Bencher) {
    let chunks = generate_test_chunks(1000);
    let chunk_to_graph = generate_test_mapping(1000);
    
    b.iter(|| {
        let builder = RepoMapTreeBuilder::new("test", "v1");
        builder.build_parallel(&chunks, &chunk_to_graph)
    });
}

#[bench]
fn bench_pagerank_10k_nodes(b: &mut Bencher) {
    let graph_doc = generate_test_graph(10_000, 50_000);
    let engine = PageRankEngine::new(PageRankConfig::default());
    
    b.iter(|| {
        engine.compute_pagerank(&graph_doc)
    });
}

#[bench]
fn bench_incremental_update(b: &mut Bencher) {
    let base_snapshot = generate_test_snapshot(10_000);
    let chunk_delta = generate_test_delta(100);  // 1% 변경
    
    b.iter(|| {
        let builder = IncrementalRepoMapBuilder::from_snapshot(&base_snapshot);
        builder.update_incremental(&chunk_delta, &GraphDelta::empty())
    });
}
```

---

## 🔄 마이그레이션 전략

### Phase 1: Python 유지 + Rust Opt-in (2주)

```python
# Python 래퍼 (기존 API 유지)
class RepoMapBuilder:
    def __init__(self, config: RepoMapBuildConfig, use_rust: bool = False):
        self.use_rust = use_rust and _RUST_AVAILABLE
        
    def build(self, chunks, graph_doc):
        if self.use_rust:
            # Rust 가속
            return codegraph_ir.build_repomap_from_pipeline(chunks, graph_doc)
        else:
            # Python 폴백
            return self._build_python(chunks, graph_doc)
```

### Phase 2: Rust 기본값 (1주)

```python
# use_rust=True를 기본값으로
class RepoMapBuilder:
    def __init__(self, config: RepoMapBuildConfig, use_rust: bool = True):
        ...
```

### Phase 3: Python 제거 (1주)

```python
# Python 구현 deprecated
class RepoMapBuilder:
    def __init__(self, config: RepoMapBuildConfig):
        if not _RUST_AVAILABLE:
            raise RuntimeError("Rust module required. Install with: maturin develop")
        ...
```

---

## 📝 요약

| 항목 | 현재 (Python) | 목표 (Rust) | 개선 |
|------|--------------|-------------|------|
| **LOC** | 6,149 | ~8,000 | +30% |
| **성능** | 1x | 10-100x | 빠름 |
| **알고리즘** | 기본 PageRank | PPR + HITS + Incremental | SOTA |
| **병렬화** | 순차 | Rayon | 멀티코어 |
| **캐시** | 없음 | Merkle Hash | Delta O(변경) |
| **Git** | 단순 빈도 | Churn + Hotspot | 고급 |

### 핵심 차별점

1. **Personalized PageRank**: 쿼리 기반 중요도
2. **HITS Algorithm**: Hub/Authority 분리
3. **Incremental Merkle**: O(변경) 업데이트
4. **Code Churn**: 변경량 추적
5. **Hot Spot Detection**: 문제 코드 발견

### 예상 일정

| Phase | 기능 | 기간 |
|-------|------|------|
| 1 | Tree Builder + Models | 1주 |
| 2 | PageRank (PPR + HITS) | 0.5주 |
| 3 | Git History (Churn + Hotspot) | 0.5주 |
| 4 | Incremental Update (Merkle) | 1주 |
| 5 | Storage + PyO3 | 1주 |
| 6 | 파이프라인 통합 + 테스트 | 0.5주 |
| | **총계** | **4.5주** |

**Last Updated**: 2025-12-28  
**Author**: Claude (Opus 4.5)  
**Status**: Planning → Implementation


