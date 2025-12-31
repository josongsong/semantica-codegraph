# IFDS/IDE Framework Feature Catalog

> **Last Updated**: 2025-01-01
> **Location**: `packages/codegraph-ir/src/features/taint_analysis/infrastructure/`
> **Total LOC**: 5,113
> **Total Tests**: 81

---

## 📦 Module Overview

| File | LOC | Tests | Description |
|------|-----|-------|-------------|
| `ifds_framework.rs` | 590 | 11 | IFDS 핵심 타입 및 트레잇 |
| `ifds_solver.rs` | 1,353 | 20 | IFDS 탭레이션 알고리즘 |
| `ide_framework.rs` | 553 | 10 | IDE 값 전파 프레임워크 |
| `ide_solver.rs` | 1,485 | 20 | IDE 솔버 + Micro/Jump 캐시 |
| `sparse_ifds.rs` | 1,132 | 20 | Sparse IFDS 최적화 (🆕) |

---

## 1️⃣ ifds_framework.rs

IFDS 분석의 핵심 타입과 트레잇 정의.

| Type | Line | Description |
|------|------|-------------|
| `trait DataflowFact` | L39 | 데이터플로우 팩트 추상화 |
| `struct ExplodedNode` | L57 | Exploded supergraph 노드 |
| `enum ExplodedEdgeKind` | L79 | 엣지 종류 (Normal/Call/Return/Summary) |
| `struct ExplodedEdge` | L94 | Exploded supergraph 엣지 |
| `trait FlowFunction` | L108 | 흐름 함수 추상화 |
| `struct IdentityFlowFunction` | L125 | f(d) = {d} |
| `struct KillFlowFunction` | L138 | f(d) = {} |
| `struct GenFlowFunction` | L147 | f(d) = {d, new_fact} |
| `struct ExplodedSupergraph` | L164 | Exploded supergraph 자료구조 |
| `struct PathEdge` | L261 | 경로 엣지 (d1, n, d2) |
| `struct SummaryEdge` | L290 | 요약 엣지 (프로시저 효과) |
| `trait IFDSProblem` | L321 | IFDS 문제 명세 인터페이스 |
| `struct IFDSStatistics` | L380 | 분석 통계 |

**Updated**: 2025-01-01 - `num_summary_reuses` 필드 추가

---

## 2️⃣ ifds_solver.rs

IFDS 탭레이션 알고리즘 구현.

| Type | Line | Description |
|------|------|-------------|
| `struct CFGEdge` | L50 | CFG 엣지 |
| `enum CFGEdgeKind` | L58 | 엣지 종류 (Normal/Call/Return/CallToReturn) |
| `struct CFG` | L116 | Control Flow Graph |
| `struct IFDSSolver` | L181 | IFDS 솔버 |
| `fn solve()` | L227 | 탭레이션 알고리즘 실행 |
| `struct IFDSSolverResult` | L599 | 분석 결과 |

**Key Methods**:
- `process_normal_edge()` - 인트라프로시저 엣지 처리
- `process_call_edge()` - 함수 호출 엣지 + **Summary 재사용** (🔧 Fixed)
- `process_return_edge()` - 함수 반환 엣지 + **정확한 call_flow 추적** (🔧 Fixed)

**Updated**: 2025-01-01
- Return edge 정확성 개선 (call_flow 결과 추적)
- Summary edge 재사용 로직 추가

---

## 3️⃣ ide_framework.rs

IDE 값 전파 프레임워크.

| Type | Line | Description |
|------|------|-------------|
| `trait IDEValue` | L50 | IDE 값 래티스 |
| `trait EdgeFunction` | L110 | 엣지 함수 추상화 |
| `struct IdentityEdgeFunction` | L145 | f(v) = v |
| `struct ConstantEdgeFunction` | L165 | f(v) = c |
| `struct AllTopEdgeFunction` | L192 | f(v) = ⊤ |
| `struct MicroFunction` | L219 | 인트라프로시저 값 변환 |
| `struct JumpFunction` | L241 | 인터프로시저 값 변환 |
| `trait IDEProblem` | L263 | IDE 문제 명세 |
| `struct IDEStatistics` | L400 | 분석 통계 |

**Updated**: 2025-01-01
- Flow function 메서드 추가 (`normal_flow_function`, `call_flow_function` 등)
- `num_micro_function_reuses`, `num_jump_function_reuses` 통계 추가

---

## 4️⃣ ide_solver.rs

IDE 솔버 + 최적화 캐시.

| Type | Line | Description |
|------|------|-------------|
| `struct IDESolver` | L68 | IDE 솔버 |
| `fn solve()` | L117 | IDE 분석 실행 |
| `struct IDESolverResult` | L388 | 분석 결과 |
| `fn get_value()` | L405 | (node, fact) → value 조회 |
| `fn statistics()` | L442 | 통계 조회 |
| `fn get_all_nodes()` | L447 | 모든 노드 조회 |

**Key Features**:
- **Micro Function 캐시** - 엣지 함수 결과 재사용 (🆕)
- **Jump Function 캐시** - 프로시저 요약 재사용 (🆕)
- **Flow Function 통합** - Gen/Kill 지원 (🔧 Fixed)

**Updated**: 2025-01-01
- Micro function 캐시 추가 (`micro_function_results`)
- Jump function 캐시 추가 (`jump_function_cache`)
- Flow function 통합 (identity 고정 제거)

---

## 5️⃣ sparse_ifds.rs (🆕 New)

Sparse IFDS 최적화 - 2-10x 성능 향상.

| Type | Line | Description |
|------|------|-------------|
| `enum NodeRelevance` | L50 | 노드 관련성 (Generator/Killer/User/Boundary/Irrelevant) |
| `struct SparseNode` | L65 | Sparse CFG 노드 |
| `struct SparseEdge` | L78 | Sparse CFG 엣지 (skipped_nodes 포함) |
| `struct SparseCFG` | L103 | Sparse CFG 자료구조 |
| `struct SparseCFGStats` | L120 | Sparse CFG 통계 |
| `fn from_cfg()` | L150 | 일반 CFG → Sparse CFG 변환 |
| `struct SparseIFDSSolver` | L385 | Sparse IFDS 솔버 |
| `struct SparseIFDSStats` | L407 | Sparse IFDS 통계 |
| `fn solve()` | L444 | Sparse 탭레이션 실행 |
| `fn taint_relevance_function()` | L652 | Taint 분석용 관련성 함수 헬퍼 |

**Key Features**:
- 관련 노드만 분석 (source/sanitizer/sink)
- 중간 노드 건너뛰기 (direct edge)
- 동일 정밀도, 2-10x 성능 향상

**Created**: 2025-01-01

---

## 🔗 Usage Example

```rust
use codegraph_ir::features::taint_analysis::infrastructure::{
    // IFDS
    IFDSSolver, IFDSProblem, DataflowFact, FlowFunction,
    PathEdge, SummaryEdge, IFDSStatistics,

    // IDE
    IDESolver, IDEProblem, IDEValue, EdgeFunction,
    MicroFunction, JumpFunction, IDEStatistics,

    // Sparse IFDS
    SparseCFG, SparseIFDSSolver, NodeRelevance,
    taint_relevance_function,
};

// Sparse IFDS 사용 예시
let sparse_cfg = SparseCFG::from_cfg(&cfg, |node| {
    if is_source(node) { NodeRelevance::Generator }
    else if is_sink(node) { NodeRelevance::User }
    else { NodeRelevance::Irrelevant }
});

let mut solver = SparseIFDSSolver::new(problem, sparse_cfg);
let results = solver.solve();

// 성능 통계 확인
println!("Reduction: {:.1}%", solver.sparse_cfg_stats().reduction_ratio * 100.0);
```

---

## 📚 References

- Reps, Horwitz, Sagiv (1995): "Precise Interprocedural Dataflow Analysis via Graph Reachability"
- Sagiv, Reps, Horwitz (1996): "Precise Interprocedural Dataflow Analysis with Applications to Constant Propagation"
- Ramalingam (1996): "Sparse Interprocedural Dataflow Analysis"
- Naeem, Lhoták, Rodriguez (2010): "Practical Extensions to the IFDS Algorithm"

---

---

## ⚙️ RFC-001 Config System Integration

**Location**: `packages/codegraph-ir/src/config/stage_configs.rs`

### TaintConfig에 추가된 IFDS/IDE 설정

| Setting | Type | Default (Balanced) | Description |
|---------|------|-------------------|-------------|
| `ifds_enabled` | `bool` | `true` | IFDS 기반 분석 활성화 |
| `ifds_max_iterations` | `usize` | `5000` | IFDS 최대 반복 횟수 |
| `ifds_summary_cache_enabled` | `bool` | `true` | Summary edge 캐시 |
| `ide_enabled` | `bool` | `true` | IDE 값 전파 활성화 |
| `ide_micro_cache_enabled` | `bool` | `true` | Micro function 캐시 |
| `ide_jump_cache_enabled` | `bool` | `true` | Jump function 캐시 |
| `sparse_ifds_enabled` | `bool` | `false` | Sparse IFDS 최적화 |
| `sparse_min_reduction_ratio` | `f64` | `0.3` | 최소 축소 비율 |

### Preset별 설정

| Preset | IFDS | IDE | Sparse | Iterations |
|--------|------|-----|--------|------------|
| **Fast** | ❌ | ❌ | ❌ | 100 |
| **Balanced** | ✅ | ✅ | ❌ | 5,000 |
| **Thorough** | ✅ | ✅ | ✅ | 50,000 |

### 사용 예시

```rust
use codegraph_ir::config::{TaintConfig, Preset};

// 90% Use Case: Preset 사용
let config = TaintConfig::from_preset(Preset::Balanced);

// 9% Use Case: IFDS/IDE 미세 조정
let config = TaintConfig::from_preset(Preset::Balanced)
    .ifds_max_iterations(10000)
    .sparse_ifds_enabled(true)
    .sparse_min_reduction_ratio(0.2);

// 1% Use Case: 완전한 제어
let config = TaintConfig::from_preset(Preset::Custom)
    .ifds_enabled(true)
    .ide_enabled(false)  // IFDS만, IDE 없이
    .ifds_summary_cache_enabled(true);
```

---

## 📝 Change Log

| Date | Change |
|------|--------|
| 2025-01-01 | IFDS return edge 정확성 개선 |
| 2025-01-01 | Summary edge 재사용 로직 추가 |
| 2025-01-01 | IDE flow function 통합 |
| 2025-01-01 | Micro/Jump function 캐시 추가 |
| 2025-01-01 | **Sparse IFDS 신규 구현** |
| 2025-01-01 | 테스트 케이스 81개 추가 |
| 2025-01-01 | **RFC-001 Config System 통합** (8개 설정 추가) |
| 2025-01-01 | **Application API 추가** (IFDSTaintService) |
