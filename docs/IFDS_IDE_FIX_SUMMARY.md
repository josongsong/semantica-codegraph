# IFDS/IDE Framework 수정 사항 (2025-01-01)

## 📊 수정 전 상태 (발견된 결함)

| # | 항목 | 문제점 |
|---|-----|-------|
| 1 | IFDS Return Edge | `d4 == d3` 근사 비교 - call_flow 결과 미확인 |
| 2 | Summary Edge | 저장만 하고 재사용 로직 없음 |
| 3 | IDE Fact Propagation | `target_fact = source_fact.clone()` 고정 (identity only) |
| 4 | Edge Function Composition | compose() 미사용 |
| 5 | Jump Function | 구조체만 정의, 활용 없음 |

---

## ✅ 수정 내용

### 1. IFDS Return Edge 정확성 개선 (`ifds_solver.rs`)

**Before:**
```rust
// 근사 비교 - 부정확
if d4 == &d3 || d4 == &F::zero() { ... }
```

**After:**
```rust
// call_flow 결과를 정확히 확인
let call_flow_produces_d4 = if let Some(ref entry) = callee_entry {
    let call_flow = self.problem.call_flow(call_site, entry);
    let produced_facts = call_flow.compute(&d3);
    produced_facts.contains(d4)
} else {
    d4 == &d3 || d4.is_zero()  // fallback
};
```

**추가된 함수:**
- `find_callee_entry_for_return()`: callee_exit에서 callee_entry 역추적

---

### 2. Summary Edge 재사용 로직 추가 (`ifds_solver.rs`)

**Before:**
```rust
// 저장만 함
self.summary_edges.entry(key).or_insert_with(HashSet::new).insert(return_fact);
```

**After:**
```rust
// Call edge 처리 시 기존 summary 조회 및 재사용
if let Some(return_facts) = self.summary_edges.get(&summary_key).cloned() {
    self.stats.num_summary_reuses += 1;
    for d_return in return_facts {
        // Summary edge로 즉시 propagate (callee 재분석 없음)
        let summary_path_edge = PathEdge::new(d1.clone(), ret_site.clone(), d_return.clone());
        self.add_path_edge(summary_path_edge);
    }
}
```

**추가된 함수:**
- `find_return_site_for_call()`: call site에서 return site 탐색

**추가된 통계:**
- `num_summary_reuses`: Summary edge 재사용 횟수

---

### 3. IDE Solver Fact Propagation 개선 (`ide_solver.rs`, `ide_framework.rs`)

**Before:**
```rust
// identity 고정
let target_fact = source_fact.clone();
```

**After:**
```rust
// Flow function으로 fact 변환 지원
let target_facts = self.problem.normal_flow_function(from_node, to_node, source_fact);
for target_fact in target_facts {
    let edge_fn = self.problem.normal_edge_function(...);
    let target_value = edge_fn.apply(source_value);
    self.add_to_worklist(to_node.to_string(), target_fact, target_value);
}
```

**IDEProblem trait 확장:**
```rust
pub trait IDEProblem<F: DataflowFact, V: IDEValue> {
    // 기존: edge function만
    fn normal_edge_function(...) -> Box<dyn EdgeFunction<V>>;

    // 신규: flow function 추가 (default: identity)
    fn normal_flow_function(&self, _from: &str, _to: &str, source_fact: &F) -> Vec<F> {
        vec![source_fact.clone()]  // 하위 호환
    }
    fn call_flow_function(...) -> Vec<F>;
    fn return_flow_function(...) -> Vec<F>;
    fn call_to_return_flow_function(...) -> Vec<F>;
}
```

---

### 4. Jump Function 캐시 및 활용 (`ide_solver.rs`)

**IDESolver에 jump function 캐시 추가:**
```rust
pub struct IDESolver<F: DataflowFact, V: IDEValue> {
    // 기존 필드...

    /// Jump function cache: procedure summary의 edge function 결과 캐시
    jump_function_cache: FxHashMap<JumpFunctionKey<F>, V>,
}
```

**Return edge에서 캐시 활용:**
```rust
let target_value = if let Some(cached) = self.jump_function_cache.get(&jump_key) {
    self.stats.num_jump_function_reuses += 1;
    cached.clone()
} else {
    let edge_fn = self.problem.return_edge_function(...);
    let computed = edge_fn.apply(source_value);
    self.jump_function_cache.insert(jump_key, computed.clone());
    computed
};
```

**추가된 통계:**
- `num_jump_function_reuses`: Jump function 캐시 재사용 횟수

---

### 5. Micro-Functions 캐시 및 활용 (`ide_solver.rs`)

**IDESolver에 micro function 캐시 추가:**
```rust
/// Micro function key: (from_node, to_node, source_fact, target_fact)
type MicroFunctionKey<F> = (String, String, F, F);

pub struct IDESolver<F: DataflowFact, V: IDEValue> {
    // 기존 필드...

    /// Micro function results: edge function 결과 캐시
    /// (source_value -> target_value) 매핑 저장
    micro_function_results: FxHashMap<MicroFunctionKey<F>, FxHashMap<V, V>>,
}
```

**Normal edge에서 캐시 활용:**
```rust
let target_value = if let Some(cached_results) = self.micro_function_results.get(&micro_key) {
    if let Some(cached_value) = cached_results.get(source_value) {
        // 캐시 히트!
        self.stats.num_micro_function_reuses += 1;
        cached_value.clone()
    } else {
        // 새 입력 값 - 계산 후 캐시
        let edge_fn = self.problem.normal_edge_function(...);
        edge_fn.apply(source_value)
    }
} else {
    // 캐시 엔트리 없음 - 계산 후 캐시 생성
    let edge_fn = self.problem.normal_edge_function(...);
    edge_fn.apply(source_value)
};

// 캐시 업데이트
self.micro_function_results
    .entry(micro_key)
    .or_insert_with(FxHashMap::default)
    .insert(source_value.clone(), target_value.clone());
```

**추가된 통계:**
- `num_micro_function_reuses`: Micro function 캐시 재사용 횟수

---

### 6. Sparse IFDS 구현 (`sparse_ifds.rs` - 신규 파일)

**핵심 구조체:**

```rust
/// 노드 관련성 타입
pub enum NodeRelevance {
    Generator,   // fact 생성 (source)
    Killer,      // fact 제거 (sanitizer)
    User,        // fact 사용 (sink)
    Boundary,    // procedure entry/exit
    Irrelevant,  // identity 변환만
}

/// Sparse CFG: 관련 노드만 포함
pub struct SparseCFG {
    pub nodes: FxHashMap<String, SparseNode>,
    pub edges: FxHashMap<String, Vec<SparseEdge>>,
    pub stats: SparseCFGStats,
}

/// Sparse CFG edge: 관련 노드 간 직접 연결
pub struct SparseEdge {
    pub from: String,
    pub to: String,
    pub skipped_nodes: usize,  // 건너뛴 노드 수
    pub kind: CFGEdgeKind,
}
```

**SparseCFG 생성:**
```rust
// 관련성 함수로 Sparse CFG 생성
let sparse_cfg = SparseCFG::from_cfg(&cfg, |node| {
    if is_source(node) { NodeRelevance::Generator }
    else if is_sanitizer(node) { NodeRelevance::Killer }
    else if is_sink(node) { NodeRelevance::User }
    else { NodeRelevance::Irrelevant }
});

// 성능 통계 확인
println!("Reduction: {:.1}%", sparse_cfg.stats.reduction_ratio * 100.0);
```

**SparseIFDSSolver:**
```rust
pub struct SparseIFDSSolver<F: DataflowFact> {
    problem: Box<dyn IFDSProblem<F>>,
    sparse_cfg: SparseCFG,
    path_edges: FxHashMap<String, FxHashSet<PathEdge<F>>>,
    summary_edges: FxHashMap<(String, F), FxHashSet<F>>,
    stats: SparseIFDSStats,
}

impl<F: DataflowFact> SparseIFDSSolver<F> {
    /// Sparse tabulation 알고리즘
    pub fn solve(&mut self) -> FxHashMap<String, FxHashSet<F>> {
        // Sparse CFG 위에서만 IFDS 실행
        // 중간 노드 건너뛰기 → 성능 향상
    }
}
```

**헬퍼 함수:**
```rust
/// Taint 분석용 관련성 함수 생성
pub fn taint_relevance_function<'a>(
    sources: &'a [&'a str],
    sanitizers: &'a [&'a str],
    sinks: &'a [&'a str],
) -> impl Fn(&str) -> NodeRelevance + 'a
```

**성능 기대치:**
- 일반적인 프로그램: 2-10x 속도 향상
- Identity 노드가 많을수록 효과 증가
- 정밀도 손실 없음 (동일 결과)

---

## 📈 개선된 상태

| # | 항목 | Before | After |
|---|-----|--------|-------|
| 1 | IFDS Return Edge | ⚠️ 근사 | ✅ 정확 |
| 2 | Summary Edge | ⚠️ 저장만 | ✅ 재사용 |
| 3 | IDE Fact Propagation | ❌ identity 고정 | ✅ flow function 지원 |
| 4 | Jump Function | ❌ 미사용 | ✅ 캐시 활용 |
| 5 | Micro-Functions | ❌ 미활용 | ✅ 캐시 활용 |
| 6 | Sparse IFDS | ❌ 미구현 | ✅ 완전 구현 |

---

## 🧪 테스트

기존 35개 테스트는 모두 호환됩니다:
- `IFDSStatistics::num_summary_reuses` 필드 추가 (Default로 0)
- `IDEStatistics::num_jump_function_reuses` 필드 추가 (Default로 0)
- IDEProblem flow function은 default implementation으로 identity 반환

---

## 📁 수정된 파일

1. `packages/codegraph-ir/src/features/taint_analysis/infrastructure/ifds_solver.rs`
2. `packages/codegraph-ir/src/features/taint_analysis/infrastructure/ifds_framework.rs`
3. `packages/codegraph-ir/src/features/taint_analysis/infrastructure/ide_solver.rs`
4. `packages/codegraph-ir/src/features/taint_analysis/infrastructure/ide_framework.rs`
5. `packages/codegraph-ir/src/features/taint_analysis/infrastructure/sparse_ifds.rs` (**신규**)
6. `packages/codegraph-ir/src/features/taint_analysis/infrastructure/mod.rs` (export 추가)

---

## 📚 참고 문헌

- Reps, Horwitz, Sagiv (1995): "Precise Interprocedural Dataflow Analysis via Graph Reachability"
- Sagiv, Reps, Horwitz (1996): "Precise Interprocedural Dataflow Analysis with Applications to Constant Propagation"
- Naeem, Lhoták, Rodriguez (2010): "Practical Extensions to the IFDS Algorithm"
