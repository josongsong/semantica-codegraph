# RFC-071: Analysis Primitives API

| 항목 | 내용 |
|------|------|
| **상태** | Draft |
| **작성일** | 2025-12-27 |
| **작성자** | Semantica Team |
| **관련 RFC** | RFC-062 (Cross-File), ADR-070 (Rust Migration) |

## 1. Executive Summary

현재 Rust `codegraph-ir` 엔진은 강력한 분석 기능(DFG, SSA, PDG, Points-to, Taint)을 보유하고 있으나, **PyO3 노출율이 약 25%**에 불과합니다. Python QueryDSL이 Rust 엔진의 모든 기능을 활용하려면 체계적인 인터페이스가 필요합니다.

본 RFC는 **수학적으로 완전하고 최소한인 5개의 Analysis Primitives**를 정의하고, 이를 통해 모든 코드 분석을 표현할 수 있는 UseCase API를 설계합니다.

### 핵심 목표
1. **수학적 완전성**: 5개 primitive로 모든 분석 표현 가능
2. **수학적 최소성**: 5개 primitive가 서로 환원 불가능
3. **5년 안정성**: 수학 정리 기반으로 언어/도구 변화에 불변
4. **100% Rust 활용**: 모든 Rust 분석 기능을 Python에서 사용 가능

---

## 2. Background & Problem Statement

### 2.1 현재 PyO3 노출 현황

| Feature | Rust 내부 | PyO3 노출 | 커버리지 |
|---------|-----------|-----------|----------|
| Parsing (L1) | 15+ types | 없음 | 0% |
| IR Generation (L2) | 8+ types | 일부 | ~20% |
| Flow Graph (L3a) | 8+ types | 요약만 | ~40% |
| Type Resolution (L3b) | 7+ types | 요약만 | ~30% |
| Data Flow (L4) | 6+ types | count만 | ~15% |
| SSA (L5) | 7+ types | count만 | ~15% |
| PDG (L6) | 5+ types | count만 | ~10% |
| Taint Analysis (L6) | 6+ types | count만 | ~10% |
| Slicing (L6) | 5+ types | 요약만 | ~10% |
| Cross-File | 9+ types | 완전 | 100% |
| Chunking | 8+ types | 없음 | 0% |
| Points-to | 12+ types | 없음 | 0% |

**전체 커버리지: ~25%**

### 2.2 문제점

```
Python QueryDSL이 못하는 것들:

1. DFG 그래프 순회
   Q: "A → B로 데이터가 흐르는가?" → 불가능

2. SSA 변수 추적
   Q: "x_1, x_2 버전 관계" → 불가능

3. PDG 순회
   Q: "제어/데이터 의존성 경로" → 불가능

4. Taint Flow 경로
   Q: "어떤 경로로 오염되었나?" → 불가능

5. Points-to 분석
   Q: "p가 가리키는 객체들" → 완전 불가능
```

### 2.3 설계 원칙

**UseCase 단위 노출** (Port/Adapter 패턴 유지)
- 내부 그래프 구조 직접 노출 ❌
- 수학적으로 정의된 연산만 노출 ✅
- 캡슐화 유지, Python-Rust 경계 단순화

---

## 3. Theoretical Foundation

### 3.1 수학적 기초

5개의 Analysis Primitives는 다음 학술적 기반에 근거합니다:

| Primitive | 수학적 기초 | 논문/연도 | 안정성 |
|-----------|------------|-----------|--------|
| **REACH** | 그래프 이론 | Euler 1736 | 289년 |
| **FIXPOINT** | Tarski 고정점 정리 | Tarski 1955 | 70년 |
| **PROPAGATE** | 추상 해석 | Cousot & Cousot 1977 | 48년 |
| **CONTEXT** | k-CFA | Shivers 1991 | 34년 |
| **RESOLVE** | 람다 계산 | Church 1936 | 89년 |

**이 연산들은 수학 정리이므로 언어나 도구가 바뀌어도 변하지 않습니다.**

### 3.2 완전성 증명

모든 정적 분석은 5개 primitive의 조합으로 표현 가능합니다:

```
┌────────────────────────────────────────────────────────────┐
│                  Analysis Algebra                          │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ∀ analysis A, ∃ composition C of {P1, P2, P3, P4, P5}    │
│  such that A ≡ C                                          │
│                                                            │
│  where:                                                    │
│    P1 = REACH (Graph Reachability)                        │
│    P2 = FIXPOINT (Monotone Framework)                     │
│    P3 = PROPAGATE (Abstract Interpretation)               │
│    P4 = CONTEXT (k-CFA)                                   │
│    P5 = RESOLVE (Symbol Resolution)                       │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 3.3 최소성 증명

5개 primitive는 서로 환원 불가능합니다:

```
REACH ↛ {FIXPOINT, PROPAGATE, CONTEXT, RESOLVE}
  - 그래프 도달가능성은 lattice 연산으로 표현 불가

FIXPOINT ↛ {REACH, PROPAGATE, CONTEXT, RESOLVE}
  - 무한 반복 수렴은 단순 도달가능성으로 표현 불가

PROPAGATE ↛ {REACH, FIXPOINT, CONTEXT, RESOLVE}
  - 추상 도메인 transfer는 concrete 연산으로 표현 불가

CONTEXT ↛ {REACH, FIXPOINT, PROPAGATE, RESOLVE}
  - 호출 컨텍스트는 심볼 해석만으로 구분 불가

RESOLVE ↛ {REACH, FIXPOINT, PROPAGATE, CONTEXT}
  - 스코프 체인은 그래프 구조가 아님
```

---

## 4. Proposed Solution

### 4.1 Design Principles

#### 4.1.1 실무적 고려사항

RFC 초안에서 발견된 3가지 성능 병목:

| 문제 | 원인 | 영향 |
|------|------|------|
| **직렬화 오버헤드** | 매 호출마다 `ir_bytes` 복사/파싱 | 10MB IR → ~50ms/호출 |
| **결과값 폭발** | 전역 분석 결과 전체 반환 | 100K 노드 → OOM 위험 |
| **FFI 반복** | Primitive 조합시 경계 반복 | 5번 조합 = 5× 오버헤드 |

#### 4.1.2 해결 전략

```
┌─────────────────────────────────────────────────────────────┐
│  3-Layer Solution                                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Layer 1: AnalysisSession (Stateful Handle)                │
│           → IR을 Rust 메모리에 유지, session_id로 참조      │
│                                                             │
│  Layer 2: Recipe Execution (Batch Processing)              │
│           → 여러 Primitive를 Rust에서 한 번에 실행          │
│                                                             │
│  Layer 3: Lazy Iteration (On-Demand Results)               │
│           → 큰 결과는 필요한 부분만 조회                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Core Architecture: AnalysisSession

```rust
// ═══════════════════════════════════════════════════════════════
// RFC-071: Stateful Analysis Session
// Eliminates serialization overhead by keeping IR in Rust memory
// ═══════════════════════════════════════════════════════════════

/// Rust 메모리에 IR과 분석 결과를 유지하는 세션 핸들
///
/// Python은 session 객체만 들고 있고, 실제 데이터는 Rust에 존재
/// → 직렬화 오버헤드 제거
#[pyclass]
pub struct AnalysisSession {
    session_id: String,
    ir: Arc<IRDocument>,              // Rust 메모리에 유지
    graphs: RwLock<GraphCache>,       // CFG/DFG/PDG lazy 빌드 & 캐시
    results: RwLock<AnalysisCache>,   // 분석 결과 캐시
    config: SessionConfig,
}

#[pymethods]
impl AnalysisSession {
    /// 세션 생성 - IR 로드 (한 번만 수행)
    ///
    /// # Performance
    /// - IR 파싱: 1회만
    /// - 이후 모든 분석은 메모리 내 IR 사용
    #[staticmethod]
    #[pyo3(signature = (ir_bytes, config = None))]
    fn load(ir_bytes: Vec<u8>, config: Option<Vec<u8>>) -> PyResult<Self>;

    /// 세션 ID 반환 (디버깅/로깅용)
    fn session_id(&self) -> String;

    /// 메모리 사용량 조회
    fn memory_usage(&self) -> PyResult<SessionStats>;

    /// 캐시 무효화
    fn invalidate_cache(&self, scope: Option<&str>) -> PyResult<()>;
}
```

### 4.3 Five Analysis Primitives (Session Methods)

```rust
#[pymethods]
impl AnalysisSession {
    // ═══════════════════════════════════════════════════════════
    // P1: Graph Reachability
    // ═══════════════════════════════════════════════════════════

    /// P1: Graph Reachability
    ///
    /// Mathematical basis: Graph theory (Euler 1736)
    /// Covers: Slicing, impact analysis, dependency traversal
    ///
    /// # Arguments
    /// * `start` - Starting node ID
    /// * `direction` - "forward" | "backward"
    /// * `graph` - "cfg" | "dfg" | "pdg" | "call"
    /// * `max_depth` - Optional depth limit
    /// * `filter` - Optional node kind filter
    ///
    /// # Returns
    /// * msgpack: { nodes: [node_id], edges: [(src, dst, kind)], stats: {...} }
    #[pyo3(signature = (start, direction, graph, max_depth = None, filter = None))]
    fn reach(
        &self,
        py: Python,
        start: String,
        direction: &str,
        graph: &str,
        max_depth: Option<usize>,
        filter: Option<Vec<String>>,
    ) -> PyResult<Vec<u8>>;


    // ═══════════════════════════════════════════════════════════
    // P2: Fixed-Point Iteration
    // ═══════════════════════════════════════════════════════════

    /// P2: Fixed-Point Iteration (Monotone Framework)
    ///
    /// Mathematical basis: Tarski's fixed-point theorem (1955)
    /// Covers: Data flow analysis, type inference, constant propagation
    ///
    /// # Returns
    /// * Analysis ID (결과는 세션에 캐시됨, query_fact()로 조회)
    #[pyo3(signature = (analysis, direction, scope = None))]
    fn fixpoint(
        &self,
        py: Python,
        analysis: &str,     // "reaching_defs" | "live_vars" | "avail_exprs" | "constants"
        direction: &str,    // "forward" | "backward"
        scope: Option<String>,
    ) -> PyResult<String>;  // analysis_id 반환 (결과값 폭발 방지)

    // ═══════════════════════════════════════════════════════════
    // P3: Abstract Value Propagation
    // ═══════════════════════════════════════════════════════════

    /// P3: Abstract Value Propagation
    ///
    /// Mathematical basis: Abstract Interpretation (Cousot & Cousot 1977)
    /// Covers: Taint analysis, null checking, interval analysis
    #[pyo3(signature = (domain, sources, config = None))]
    fn propagate(
        &self,
        py: Python,
        domain: &str,       // "taint" | "null" | "sign" | "interval" | "points_to"
        sources: Vec<String>,
        config: Option<Vec<u8>>,
    ) -> PyResult<String>;  // analysis_id 반환

    // ═══════════════════════════════════════════════════════════
    // P4: Context-Sensitive Analysis
    // ═══════════════════════════════════════════════════════════

    /// P4: Context-Sensitive Analysis
    ///
    /// Mathematical basis: k-CFA (Shivers 1991)
    /// Covers: Precise interprocedural analysis, virtual dispatch
    #[pyo3(signature = (base_analysis, context_type, k_limit))]
    fn with_context(
        &self,
        py: Python,
        base_analysis: &str,    // "taint" | "points_to" | "type"
        context_type: &str,     // "call_string" | "object" | "type"
        k_limit: usize,
    ) -> PyResult<String>;  // analysis_id 반환

    // ═══════════════════════════════════════════════════════════
    // P5: Symbol Resolution
    // ═══════════════════════════════════════════════════════════

    /// P5: Symbol Resolution
    ///
    /// Mathematical basis: Lambda calculus (Church 1936)
    /// Covers: Definition, references, type lookup, scope query
    ///
    /// # Returns
    /// * msgpack: Query-specific result (작은 결과이므로 직접 반환)
    #[pyo3(signature = (query, target))]
    fn resolve(
        &self,
        py: Python,
        query: &str,        // "definition" | "references" | "type" | "scope" | "callers" | "callees"
        target: String,
    ) -> PyResult<Vec<u8>>;
}
```

### 4.4 Lazy Result Access (결과값 폭발 방지)

```rust
#[pymethods]
impl AnalysisSession {
    /// 분석 결과에서 특정 노드의 fact만 조회
    ///
    /// fixpoint/propagate 결과가 100K 노드일 때,
    /// 전체를 Python으로 복사하지 않고 필요한 것만 조회
    fn query_fact(&self, analysis_id: &str, node_id: &str) -> PyResult<Vec<u8>>;

    /// 분석 결과의 노드 ID 목록만 조회
    fn list_nodes(&self, analysis_id: &str) -> PyResult<Vec<String>>;

    /// 특정 조건을 만족하는 노드만 필터링
    fn filter_nodes(&self, analysis_id: &str, predicate: &str) -> PyResult<Vec<String>>;

    /// 분석 결과 요약 통계
    fn analysis_stats(&self, analysis_id: &str) -> PyResult<Vec<u8>>;
}
```

### 4.5 Recipe System (FFI 최소화)

```rust
#[pymethods]
impl AnalysisSession {
    /// Recipe JSON 실행 - 여러 Primitive를 Rust 내부에서 한 번에 실행
    ///
    /// # Recipe Format
    /// ```json
    /// {
    ///   "steps": [
    ///     {"id": "s1", "op": "propagate", "domain": "taint", "sources": ["$input"]},
    ///     {"id": "s2", "op": "with_context", "base": "$s1", "type": "call_string", "k": 1},
    ///     {"id": "s3", "op": "reach", "start": "$sinks", "direction": "backward", "graph": "pdg"},
    ///     {"id": "s4", "op": "intersect", "a": "$s2", "b": "$s3"}
    ///   ],
    ///   "output": {"mode": "paths", "format": "msgpack"}
    /// }
    /// ```
    ///
    /// # Operators
    /// - 5 primitives: `reach`, `fixpoint`, `propagate`, `with_context`, `resolve`
    /// - Set ops: `intersect`, `union`, `difference`
    /// - Transforms: `filter`, `map`
    fn execute_recipe(&self, py: Python, recipe_json: &str) -> PyResult<Vec<u8>>;

    /// 미리 정의된 빌트인 레시피 실행
    ///
    /// # Built-in Recipes
    /// - "security_taint": Context-sensitive taint + sink reachability
    /// - "null_safety": Null propagation + deref check
    /// - "impact_analysis": Forward slice + transitive deps
    /// - "dead_code": Reachability complement
    fn execute_builtin(&self, py: Python, recipe_name: &str, params: Option<Vec<u8>>) -> PyResult<Vec<u8>>;
}
```

### 4.6 Recipe DSL Example

```python
# Python에서 Security Taint Recipe 정의
SECURITY_TAINT_RECIPE = {
    "name": "security_taint_analysis",
    "steps": [
        {"id": "taint", "op": "propagate", "domain": "taint", "sources": "$sources"},
        {"id": "ctx", "op": "with_context", "base": "$taint", "type": "call_string", "k": 1},
        {"id": "slice", "op": "reach", "start": "$sinks", "direction": "backward", "graph": "pdg"},
        {"id": "vuln", "op": "intersect", "a": "$ctx", "b": "$slice"},
    ],
    "output": {"mode": "paths", "from": "$sources", "to": "$sinks"}
}

# 사용 (FFI 1회만)
session = AnalysisSession.load(ir_bytes)
result = session.execute_recipe(json.dumps(SECURITY_TAINT_RECIPE))

# 또는 빌트인
result = session.execute_builtin("security_taint", msgpack.packb({
    "sources": ["user_input"],
    "sinks": ["eval", "exec"]
}))
```

### 4.7 Composition Examples

모든 고수준 분석은 primitive 조합으로 표현됩니다:

| 분석 | Primitive 조합 |
|------|---------------|
| **Backward Slice** | `reach(node, "backward", "pdg")` |
| **Forward Slice** | `reach(node, "forward", "pdg")` |
| **Taint Analysis** | `propagate(ir, "taint", sources)` |
| **Context-Sensitive Taint** | `with_context(ir, "taint", "call_string", 1)` |
| **Type Inference** | `fixpoint(ir, "types", "forward")` |
| **Null Check** | `propagate(ir, "null", [])` |
| **Points-to** | `propagate(ir, "points_to", [])` |
| **Call Graph** | `reach(entry, "forward", "call")` |
| **Impact Analysis** | `reach(node, "forward", "pdg")` + `with_context(..., 1)` |
| **Go-to-Definition** | `resolve(ir, "definition", symbol)` |
| **Find References** | `resolve(ir, "references", symbol)` |
| **Virtual Dispatch** | `resolve(ir, "callees", call)` + `with_context("type", 1)` |
| **Dead Code** | `reach(entry, "forward", "cfg")` → complement |
| **Constant Propagation** | `fixpoint(ir, "constants", "forward")` |

### 4.3 Python QueryDSL Integration

```python
# packages/codegraph-engine/codegraph_engine/code_foundation/domain/ports/analysis.py

from typing import Protocol, runtime_checkable

@runtime_checkable
class AnalysisPrimitives(Protocol):
    """
    RFC-071: Analysis Primitives Port

    5 mathematically complete & minimal operations for all code analysis.
    """

    def reach(
        self,
        start: str,
        direction: Literal["forward", "backward"],
        graph: Literal["cfg", "dfg", "pdg", "call"],
        max_depth: int | None = None,
    ) -> ReachResult:
        """P1: Graph reachability (슬라이싱, 영향분석)"""
        ...

    def fixpoint(
        self,
        analysis: Literal["reaching_defs", "live_vars", "avail_exprs", "constants"],
        direction: Literal["forward", "backward"],
        scope: str | None = None,
    ) -> FixpointResult:
        """P2: Fixed-point iteration (데이터플로우)"""
        ...

    def propagate(
        self,
        domain: Literal["taint", "null", "sign", "interval", "points_to"],
        sources: list[str],
        config: dict | None = None,
    ) -> PropagateResult:
        """P3: Abstract value propagation (테인트, 널체크)"""
        ...

    def with_context(
        self,
        base_analysis: str,
        context_type: Literal["call_string", "object", "type"],
        k_limit: int,
    ) -> ContextResult:
        """P4: Context-sensitive analysis (k-CFA)"""
        ...

    def resolve(
        self,
        query: Literal["definition", "references", "type", "scope", "callers", "callees"],
        target: str,
    ) -> ResolveResult:
        """P5: Symbol resolution (정의, 참조, 타입)"""
        ...
```

### 4.4 QueryDSL High-Level API

```python
# packages/codegraph-engine/codegraph_engine/code_foundation/domain/query/expressions.py

class FlowExpr:
    """
    RFC-071 기반 고수준 쿼리 표현

    내부적으로 5개 primitive로 변환됨
    """

    def backward_slice(self, target: str, max_depth: int = 50) -> PathSet:
        """reach(target, "backward", "pdg", max_depth)"""
        return self._primitives.reach(target, "backward", "pdg", max_depth)

    def forward_slice(self, source: str, max_depth: int = 50) -> PathSet:
        """reach(source, "forward", "pdg", max_depth)"""
        return self._primitives.reach(source, "forward", "pdg", max_depth)

    def taint_from(self, sources: list[str]) -> TaintResult:
        """propagate(ir, "taint", sources)"""
        return self._primitives.propagate("taint", sources)

    def find_null_derefs(self) -> list[Location]:
        """propagate(ir, "null", [])로 nullable 추적 후 deref 위치 반환"""
        null_facts = self._primitives.propagate("null", [])
        return self._find_unsafe_derefs(null_facts)

    def points_to(self, pointer: str) -> set[str]:
        """propagate(ir, "points_to", [pointer])"""
        result = self._primitives.propagate("points_to", [pointer])
        return result.get(pointer, set())
```

---

## 5. Implementation Plan

### Phase 1: Core Primitives (Week 1-2)

```
packages/codegraph-rust/codegraph-ir/src/adapters/pyo3/api/
├── primitives/
│   ├── mod.rs
│   ├── reach.rs        ← P1: Graph Reachability
│   ├── fixpoint.rs     ← P2: Fixed-Point Iteration
│   ├── propagate.rs    ← P3: Abstract Propagation
│   ├── context.rs      ← P4: Context Management
│   └── resolve.rs      ← P5: Symbol Resolution
```

**Deliverables:**
- [ ] `reach()` - CFG/DFG/PDG/CallGraph 순회
- [ ] `resolve()` - 기존 cross_file 확장
- [ ] 단위 테스트 + 벤치마크

### Phase 2: Analysis Primitives (Week 3-4)

**Deliverables:**
- [ ] `fixpoint()` - 워크리스트 알고리즘 노출
- [ ] `propagate()` - 추상 도메인 프레임워크
- [ ] `with_context()` - k-CFA 컨텍스트

### Phase 3: Python Integration (Week 5)

**Deliverables:**
- [ ] `AnalysisPrimitives` 포트 정의
- [ ] `RustAnalysisAdapter` 구현
- [ ] QueryDSL 연동
- [ ] 기존 API 호환 유지

### Phase 4: Verification (Week 6)

**Deliverables:**
- [ ] 완전성 테스트 (모든 분석 → primitive 조합)
- [ ] 최소성 테스트 (primitive 간 비환원성)
- [ ] 성능 벤치마크

---

## 6. Verification Strategy

### 6.1 Completeness Test

```python
# tests/test_primitives_completeness.py

KNOWN_ANALYSES = [
    "backward_slice", "forward_slice",
    "taint", "null_check", "type_inference",
    "constant_prop", "call_graph", "impact",
    "dead_code", "escape", "points_to"
]

def test_all_analyses_expressible():
    """모든 알려진 분석이 5개 primitive로 표현 가능"""
    for analysis in KNOWN_ANALYSES:
        composition = express_as_primitives(analysis)
        assert composition is not None
        assert all(p in PRIMITIVES for p in composition.primitives)

def test_composition_equivalence():
    """직접 구현과 primitive 조합 결과가 동일"""
    for analysis in KNOWN_ANALYSES:
        direct = run_direct(analysis, TEST_IR)
        composed = run_composed(analysis, TEST_IR)
        assert direct == composed
```

### 6.2 Minimality Test

```python
def test_primitives_irreducible():
    """각 primitive가 다른 것들로 표현 불가능"""
    for p in PRIMITIVES:
        others = PRIMITIVES - {p}
        assert not is_expressible_by(p, others), \
            f"{p} should not be expressible by {others}"
```

### 6.3 Coverage Verification

```python
# tools/verify_rust_coverage.py

def verify_100_percent_coverage():
    """Rust 분석 기능이 100% Python에서 사용 가능"""
    rust_features = extract_rust_public_apis()
    python_accessible = get_primitive_reachable_features()

    coverage = len(python_accessible) / len(rust_features)
    missing = rust_features - python_accessible

    assert coverage == 1.0, f"Missing: {missing}"
```

---

## 7. Performance Targets

| Primitive | Target Latency | Notes |
|-----------|---------------|-------|
| `reach()` | < 10ms | 1000 노드 그래프 |
| `fixpoint()` | < 50ms | 10K 노드 프로그램 |
| `propagate()` | < 100ms | 복잡한 도메인 |
| `with_context()` | < 500ms | k=2 |
| `resolve()` | < 5ms | 캐시 히트 |

**GIL Release**: 모든 primitive는 `py.allow_threads()`로 GIL 해제

---

## 8. Migration Path

### 8.1 기존 API 호환

```python
# 기존 API (유지)
slice_result = codegraph_ir.backward_slice(pdg_bytes, target, depth)

# 내부적으로 primitive 호출로 변환
def backward_slice(pdg_bytes, target, depth):
    return reach(pdg_bytes, target, "backward", "pdg", depth)
```

### 8.2 점진적 마이그레이션

1. **Phase 1**: Primitive API 추가 (기존 API 유지)
2. **Phase 2**: 기존 API를 primitive wrapper로 변환
3. **Phase 3**: 새 코드는 primitive 직접 사용 권장
4. **Phase 4**: (선택) 기존 API deprecation

---

## 9. Future Extensions

5개 primitive는 확장 가능하지만, 핵심 인터페이스는 변경되지 않습니다:

```
확장 예시 (기존 primitive 내부 확장):

propagate(domain="string_length")   ← 새 추상 도메인 추가
reach(graph="exception")            ← 새 그래프 타입 추가
fixpoint(analysis="shape")          ← 새 분석 타입 추가
```

**핵심 원칙**: 새로운 분석은 기존 5개 primitive의 파라미터로 추가됨

---

## 10. References

1. Weiser, M. (1981). "Program Slicing". IEEE TSE.
2. Kildall, G. (1973). "A Unified Approach to Global Program Optimization". POPL.
3. Cousot, P. & Cousot, R. (1977). "Abstract Interpretation". POPL.
4. Shivers, O. (1991). "Control-Flow Analysis of Higher-Order Languages". CMU PhD Thesis.
5. Andersen, L.O. (1994). "Program Analysis and Specialization for the C Programming Language".
6. Steensgaard, B. (1996). "Points-to Analysis in Almost Linear Time". POPL.

---

## 11. Advanced Features

### 11.1 Session Governance (자원 관리)

```rust
/// 세션 설정 - 자원 제약
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionConfig {
    /// 최대 메모리 사용량 (bytes, 0 = unlimited)
    pub max_memory_bytes: usize,

    /// 세션 TTL (비활성 시 자동 폐기, seconds)
    pub ttl_seconds: u64,

    /// 개별 분석 타임아웃 (seconds)
    pub analysis_timeout_seconds: u64,

    /// k-CFA 컨텍스트 제한 (메모리 폭발 방지)
    pub max_context_limit: usize,

    /// 결과 페이징 임계치 (이상이면 핸들 반환)
    pub result_paging_threshold: usize,
}

impl Default for SessionConfig {
    fn default() -> Self {
        Self {
            max_memory_bytes: 2 * 1024 * 1024 * 1024,  // 2GB
            ttl_seconds: 30 * 60,                       // 30분
            analysis_timeout_seconds: 300,              // 5분
            max_context_limit: 10_000,                  // 컨텍스트 1만개 제한
            result_paging_threshold: 50_000,            // 5만 노드 이상이면 페이징
        }
    }
}
```

### 11.2 Paging & Streaming (대용량 결과 처리)

```rust
#[pymethods]
impl AnalysisSession {
    /// 대용량 결과에 대한 핸들 반환 (메모리 효율)
    ///
    /// 결과가 threshold 이상이면 전체 반환 대신 핸들 반환
    /// Python에서 페이징으로 조회
    fn get_result_handle(&self, analysis_id: &str) -> PyResult<ResultHandle>;
}

#[pyclass]
pub struct ResultHandle {
    session_id: String,
    analysis_id: String,
    total_count: usize,
}

#[pymethods]
impl ResultHandle {
    /// 페이징 조회
    fn fetch(&self, offset: usize, limit: usize) -> PyResult<Vec<u8>>;

    /// 스트리밍 이터레이터
    fn stream(&self, batch_size: usize) -> PyResult<ResultIterator>;

    /// 전체 개수
    fn count(&self) -> usize;

    /// 필터링된 서브셋
    fn filter(&self, predicate: &str) -> PyResult<ResultHandle>;
}
```

### 11.3 Incremental Analysis (증분 분석)

```rust
#[pymethods]
impl AnalysisSession {
    /// IR 부분 업데이트 (수정된 파일만)
    ///
    /// 전체 재로드 없이 변경된 부분만 업데이트
    /// 관련 캐시 자동 무효화
    fn patch_ir(&self, diff_bytes: Vec<u8>) -> PyResult<PatchResult>;

    /// 영향 받는 분석 결과만 재계산
    fn recompute_affected(&self, changed_nodes: Vec<String>) -> PyResult<Vec<String>>;

    /// 무효화된 분석 목록 조회
    fn list_invalidated(&self) -> PyResult<Vec<String>>;
}

#[derive(Debug)]
pub struct PatchResult {
    /// 추가된 노드
    pub added: Vec<String>,
    /// 삭제된 노드
    pub removed: Vec<String>,
    /// 수정된 노드
    pub modified: Vec<String>,
    /// 무효화된 캐시
    pub invalidated_caches: Vec<String>,
}
```

### 11.4 Explainability (설명 가능성)

```rust
#[pymethods]
impl AnalysisSession {
    /// 경로 포함 reach (증거 경로 반환)
    ///
    /// 단순 도달 여부뿐 아니라 실제 경로도 반환
    #[pyo3(signature = (start, direction, graph, max_depth = None, include_paths = false))]
    fn reach_with_paths(
        &self,
        py: Python,
        start: String,
        direction: &str,
        graph: &str,
        max_depth: Option<usize>,
        include_paths: bool,
    ) -> PyResult<Vec<u8>>;  // { nodes, edges, paths: [[node_id]] }

    /// 테인트 흐름 경로 추적
    fn trace_taint_path(
        &self,
        analysis_id: &str,
        from: &str,
        to: &str,
    ) -> PyResult<Vec<u8>>;  // { path: [node_id], edges: [(src, dst)] }

    /// 분석 결과 설명 생성
    fn explain(
        &self,
        analysis_id: &str,
        node_id: &str,
    ) -> PyResult<String>;  // 사람이 읽을 수 있는 설명
}
```

### 11.5 Custom Domain Configuration (언어별 의미론 확장)

```rust
/// 추상 도메인 커스텀 설정
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DomainConfig {
    /// 기본 도메인 타입
    pub base: String,  // "taint" | "null" | etc.

    /// Transfer function 오버라이드
    pub transfer_overrides: HashMap<String, TransferRule>,

    /// 소스 패턴 (정규식)
    pub source_patterns: Vec<String>,

    /// 싱크 패턴
    pub sink_patterns: Vec<String>,

    /// 새니타이저 패턴
    pub sanitizer_patterns: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransferRule {
    /// 함수/메서드 패턴
    pub pattern: String,

    /// 입력 → 출력 매핑
    /// "propagate": 테인트 전파
    /// "sanitize": 테인트 제거
    /// "taint": 새 테인트 추가
    pub action: String,

    /// 영향 받는 인자 인덱스
    pub affected_args: Vec<usize>,
}
```

```python
# Python에서 커스텀 도메인 설정 예시
django_taint_config = {
    "base": "taint",
    "source_patterns": [
        r"request\.GET\[.*\]",
        r"request\.POST\[.*\]",
    ],
    "sink_patterns": [
        r"cursor\.execute\(.*\)",
        r"render\(.*\)",
    ],
    "sanitizer_patterns": [
        r"escape\(.*\)",
        r"quote\(.*\)",
    ],
    "transfer_overrides": {
        "django.utils.html.escape": {
            "pattern": "escape",
            "action": "sanitize",
            "affected_args": [0]
        }
    }
}

# 커스텀 설정으로 분석
session.propagate("taint", sources, config=msgpack.packb(django_taint_config))
```

### 11.6 Async Support (비동기 지원)

```rust
#[pymethods]
impl AnalysisSession {
    /// 비동기 분석 시작 (Python asyncio 호환)
    ///
    /// 장시간 분석을 백그라운드에서 실행
    /// Python에서 await로 결과 대기
    fn start_async(&self, py: Python, recipe_json: &str) -> PyResult<AsyncHandle>;

    /// 진행 상황 조회
    fn poll_progress(&self, handle: &AsyncHandle) -> PyResult<ProgressInfo>;

    /// 분석 취소
    fn cancel(&self, handle: &AsyncHandle) -> PyResult<bool>;
}

#[pyclass]
pub struct AsyncHandle {
    task_id: String,
    started_at: u64,
}

#[pymethods]
impl AsyncHandle {
    /// Python asyncio 호환 awaitable
    fn __await__(&self, py: Python) -> PyResult<PyObject>;

    /// 완료 여부
    fn is_done(&self) -> bool;

    /// 결과 조회 (완료 시)
    fn result(&self) -> PyResult<Vec<u8>>;
}
```

```python
# Python 비동기 사용 예시
import asyncio

async def analyze_large_codebase(session):
    # 비동기로 분석 시작
    handle = session.start_async(json.dumps(SECURITY_TAINT_RECIPE))

    # 진행 상황 모니터링
    while not handle.is_done():
        progress = session.poll_progress(handle)
        print(f"Progress: {progress.percent}%")
        await asyncio.sleep(1)

    # 결과 수집
    return handle.result()

# 여러 분석 병렬 실행
results = await asyncio.gather(
    analyze_large_codebase(session1),
    analyze_large_codebase(session2),
)
```

---

## 12. Appendix: Abstract Domain Catalog

`propagate()`에서 사용 가능한 추상 도메인:

| Domain | Lattice | Transfer | Use Case |
|--------|---------|----------|----------|
| `taint` | P(sources) | union | 보안 분석 |
| `null` | {null, non-null, maybe} | rules | NPE 탐지 |
| `sign` | {+, -, 0, ±, ⊥, ⊤} | arithmetic | 범위 검증 |
| `interval` | [lo, hi] | widening | 버퍼 오버플로우 |
| `points_to` | P(locations) | subset | 포인터 분석 |
| `type` | Type lattice | subtyping | 타입 추론 |
| `const` | {⊥} ∪ Constants ∪ {⊤} | eval | 상수 전파 |
