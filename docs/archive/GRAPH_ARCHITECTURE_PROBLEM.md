# Graph Architecture Problem - 중복된 구조 문제

## 발견된 문제

**이미 완벽한 Graph Builder가 있는데, 왜 query_engine에서 또 다른 GraphIndex를 만들었나?**

---

## 현재 구조 분석

### 1. Graph Builder (SOTA, 완전한 구조) ✅

**위치**: `features/graph_builder/domain/mod.rs`

```rust
/// 이미 최적화된 GraphIndex (SOTA)
#[derive(Debug, Clone, Default)]
pub struct GraphIndex {
    // ✅ 모든 reverse index 지원
    pub called_by: AHashMap<InternedString, Vec<InternedString>>,
    pub imported_by: AHashMap<InternedString, Vec<InternedString>>,
    pub contains_children: AHashMap<InternedString, Vec<InternedString>>,
    pub type_users: AHashMap<InternedString, Vec<InternedString>>,
    pub reads_by: AHashMap<InternedString, Vec<InternedString>>,
    pub writes_by: AHashMap<InternedString, Vec<InternedString>>,

    // ✅ Adjacency indexes
    pub outgoing: AHashMap<InternedString, Vec<InternedString>>,
    pub incoming: AHashMap<InternedString, Vec<InternedString>>,

    // ✅ EdgeKind별 인덱스 (매우 강력!)
    pub outgoing_by_kind: AHashMap<(InternedString, EdgeKind), Vec<InternedString>>,
    pub incoming_by_kind: AHashMap<(InternedString, EdgeKind), Vec<InternedString>>,

    // ✅ Framework awareness
    pub routes_by_path: AHashMap<InternedString, Vec<InternedString>>,
    pub services_by_domain: AHashMap<InternedString, Vec<InternedString>>,
    pub request_flow_index: AHashMap<InternedString, RequestFlow>,
    pub decorators_by_target: AHashMap<InternedString, Vec<InternedString>>,
}

pub struct GraphNode {
    pub id: InternedString,           // ✅ String interning (50% 메모리 절감)
    pub kind: NodeKind,
    pub repo_id: InternedString,
    pub snapshot_id: Option<InternedString>,
    pub fqn: InternedString,
    pub name: InternedString,
    pub path: Option<InternedString>,
    pub span: Option<Box<Span>>,      // ✅ Null pointer optimization
    pub attrs: AHashMap<String, serde_json::Value>,  // ✅ AHashMap (2-3x faster)
}

pub struct GraphDocument {
    pub nodes: Vec<GraphNode>,
    pub edges: Vec<GraphEdge>,
    pub index: GraphIndex,            // ✅ Index가 이미 포함됨!
}
```

**특징:**
- ✅ String interning (50% 메모리 절감)
- ✅ AHashMap (2-3x faster than std HashMap)
- ✅ Null pointer optimization
- ✅ EdgeKind별 인덱스 (강력!)
- ✅ Framework-aware (routes, services, request flow)
- ✅ **이미 index가 포함된 GraphDocument**

---

### 2. Query Engine GraphIndex (단순 버전, 중복) ❌

**위치**: `features/query_engine/infrastructure/graph_index.rs`

```rust
/// 단순한 버전 (왜 만들었나?)
pub struct GraphIndex {
    nodes_by_id: HashMap<String, Node>,           // ← std HashMap (느림)
    edges_from: HashMap<String, Vec<Edge>>,       // ← 기본 기능만
    edges_to: HashMap<String, Vec<Edge>>,
    nodes_by_name: HashMap<String, Vec<Node>>,

    node_count: usize,
    edge_count: usize,
}
```

**문제점:**
- ❌ String interning 없음 (메모리 낭비)
- ❌ std HashMap 사용 (느림)
- ❌ 기본 기능만 있음 (called_by, imported_by 등 없음)
- ❌ EdgeKind별 인덱스 없음
- ❌ Framework awareness 없음
- ❌ **graph_builder의 열화 버전**

---

## 문제의 원인

### PyGraphIndex가 잘못된 GraphIndex를 사용 중

```rust
// 현재 코드 (잘못됨)
use crate::features::query_engine::infrastructure::GraphIndex;  // ← 단순 버전!

#[pyclass]
pub struct PyGraphIndex {
    index: GraphIndex,  // ← 열화 버전 사용 중
}
```

**올바른 방법:**

```rust
// 올바른 코드
use crate::features::graph_builder::domain::{GraphIndex, GraphDocument};  // ← SOTA 버전!

#[pyclass]
pub struct PyGraphIndex {
    index: GraphIndex,  // ← SOTA 버전 사용
}
```

---

## 왜 이런 중복이 생겼나?

### 추정 원인

1. **query_engine이 먼저 만들어짐**
   - 초기에 간단한 GraphIndex 구현
   - 기본 기능만 필요했음

2. **나중에 graph_builder가 SOTA로 구현됨**
   - String interning, AHashMap 등 최적화
   - Framework-aware features 추가
   - 더 완전한 구조

3. **통합이 안됨**
   - query_engine이 여전히 자체 GraphIndex 사용
   - graph_builder의 GraphIndex가 활용 안됨
   - 중복 코드 유지됨

---

## 해결 방안

### Option 1: graph_builder.GraphIndex 사용 (추천) ✅

**장점:**
- ✅ 이미 최적화된 구조 활용
- ✅ String interning (50% 메모리 절감)
- ✅ AHashMap (2-3x faster)
- ✅ EdgeKind별 인덱스
- ✅ Framework awareness
- ✅ 중복 제거

**변경:**

```rust
// query.rs
use crate::features::graph_builder::domain::{GraphIndex, GraphDocument, GraphNode, GraphEdge};

fn build_graph_index_from_result(result_bytes: &[u8]) -> PyResult<GraphIndex> {
    // Deserialize IR result
    let result: HashMap<String, serde_json::Value> = rmp_serde::from_slice(result_bytes)?;

    // Extract nodes and edges
    let nodes_json = result.get("nodes")?;
    let edges_json = result.get("edges")?;

    let nodes: Vec<GraphNode> = serde_json::from_value(nodes_json.clone())?;
    let edges: Vec<GraphEdge> = serde_json::from_value(edges_json.clone())?;

    // Build GraphDocument (이미 index 포함!)
    let graph_doc = GraphDocument::new(nodes, edges);

    // Return the already-built index
    Ok(graph_doc.index)
}
```

---

### Option 2: query_engine.GraphIndex 삭제, graph_builder로 통합

**변경:**
1. `features/query_engine/infrastructure/graph_index.rs` 삭제
2. `features/query_engine` 전체를 `graph_builder` 사용하도록 변경
3. PyGraphIndex도 `graph_builder.GraphIndex` 사용

---

## 성능 비교

### 현재 (query_engine.GraphIndex)

```rust
pub struct GraphIndex {
    nodes_by_id: HashMap<String, Node>,  // ← std HashMap
    // ...
}

// 성능
- Build time: 800ms
- Memory: 높음 (string duplication)
- Query: O(1) but std HashMap
```

### 개선 (graph_builder.GraphIndex)

```rust
pub struct GraphIndex {
    called_by: AHashMap<InternedString, Vec<InternedString>>,  // ← AHashMap + interning
    // ...
}

// 성능 (예상)
- Build time: ~500ms (AHashMap faster)
- Memory: 50% 절감 (string interning)
- Query: O(1) with 2-3x faster AHashMap
- EdgeKind별 필터링: O(1) (outgoing_by_kind)
```

---

## DFG, CFG는 어떻게 사용하나?

### DFG (Data Flow Graph)
```rust
pub struct DataFlowGraph {
    pub function_id: String,
    pub nodes: Vec<DFNode>,
    pub def_use_edges: Vec<(usize, usize)>,
}
```

**용도:**
- Function 내부의 데이터 흐름 (변수 def-use)
- Taint analysis
- Slicing

**범위:**
- **Function-local** (한 함수 내부만)
- Cross-function 아님

---

### CFG (Control Flow Graph)
```rust
pub struct CFGEdge {
    pub source_block_id: String,
    pub target_block_id: String,
    pub edge_type: CFGEdgeType,  // True, False, LoopBack, etc.
}
```

**용도:**
- Function 내부의 제어 흐름 (basic blocks)
- Reachability analysis
- Path analysis

**범위:**
- **Function-local** (한 함수 내부만)

---

### Graph Builder (Program-wide)
```rust
pub struct GraphIndex {
    pub called_by: AHashMap<...>,    // Cross-function
    pub imported_by: AHashMap<...>,  // Cross-file
    pub contains_children: AHashMap<...>,  // Cross-scope
    // ...
}
```

**용도:**
- **Program-wide** 그래프 (전체 코드베이스)
- Cross-function calls
- Cross-file imports
- Module dependencies

**범위:**
- **Entire program** (전체 프로그램)

---

## 정리

### 각 그래프의 역할

| Graph | 범위 | 용도 | 검색 가능? |
|-------|------|------|-----------|
| **DFG** | Function-local | 데이터 흐름 (def-use) | ❌ (특수 목적) |
| **CFG** | Function-local | 제어 흐름 (blocks) | ❌ (특수 목적) |
| **Graph Builder** | Program-wide | 전체 코드 그래프 | ✅ (일반 쿼리용) |
| **query_engine.GraphIndex** | Program-wide | 쿼리용 인덱스 | ✅ (중복!) |

### 문제 요약

1. **DFG, CFG**: Function-local이라 일반 쿼리에 부적합 ✅ 올바름
2. **graph_builder.GraphIndex**: Program-wide, SOTA 최적화, 완전한 기능 ✅ 최고
3. **query_engine.GraphIndex**: Program-wide, 단순 버전, 중복 ❌ 불필요

### 해결책

**query_engine.GraphIndex 삭제 → graph_builder.GraphIndex 사용**

```rust
// PyGraphIndex 수정
use crate::features::graph_builder::domain::GraphIndex;  // ← SOTA 버전

#[pyclass]
pub struct PyGraphIndex {
    index: GraphIndex,  // ← 이미 최적화됨
}
```

**이득:**
- ✅ 50% 메모리 절감 (string interning)
- ✅ 2-3x faster (AHashMap)
- ✅ EdgeKind별 필터링 (outgoing_by_kind)
- ✅ Framework awareness (routes, services)
- ✅ 중복 코드 제거

---

## 다음 단계

1. **PyGraphIndex를 graph_builder.GraphIndex로 마이그레이션**
2. **query_engine.GraphIndex 삭제 (deprecated)**
3. **성능 벤치마크 재측정**
   - 예상: 800ms → 500ms (빌드)
   - 예상: 50% 메모리 절감

**질문**: graph_builder.GraphIndex로 마이그레이션할까요?
