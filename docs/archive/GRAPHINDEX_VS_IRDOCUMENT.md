# GraphIndex vs IRDocument - 구조 설명

## 질문: "GraphBuilder통해서 만들어진 그래프 안쓰고 HashMap으로 변환한다는거?"

**답변: IRDocument와 GraphIndex는 다른 목적으로 사용됩니다.**

---

## 1. 데이터 구조 비교

### IRDocument (원본 그래프 데이터)

```rust
pub struct IRDocument {
    pub file_path: String,
    pub nodes: Vec<Node>,      // ← Linear array (순서 보존)
    pub edges: Vec<Edge>,      // ← Linear array (순서 보존)
}
```

**목적:**
- IR 생성 결과를 저장
- 순서가 중요한 경우 (코드 순서대로)
- Python으로 전달하기 위한 직렬화

**특징:**
- ✅ 메모리 효율적 (compact layout)
- ✅ 순서 보존 (insertion order)
- ❌ 검색 느림 (O(n) linear search)
- ❌ 특정 노드 찾기 느림

**사용 예:**
```rust
// IR 생성
let ir_doc = IRDocument {
    nodes: vec![node1, node2, node3, ...],
    edges: vec![edge1, edge2, edge3, ...],
};

// 특정 노드 찾기 (느림!)
let node = ir_doc.nodes.iter().find(|n| n.id == "target_id");  // O(n)
```

---

### GraphIndex (검색용 인덱스)

```rust
pub struct GraphIndex {
    // HashMap indexes for O(1) lookups
    nodes_by_id: HashMap<String, Node>,           // ID → Node
    edges_from: HashMap<String, Vec<Edge>>,       // source_id → outgoing edges
    edges_to: HashMap<String, Vec<Edge>>,         // target_id → incoming edges
    nodes_by_name: HashMap<String, Vec<Node>>,    // name → nodes
}
```

**목적:**
- 빠른 쿼리 수행 (O(1) lookup)
- 그래프 순회 (traverse)
- 노드/엣지 검색

**특징:**
- ✅ 검색 빠름 (O(1) hash lookup)
- ✅ 순회 빠름 (edge indexes)
- ❌ 메모리 많이 사용 (multiple HashMaps)
- ❌ 순서 보장 안됨

**사용 예:**
```rust
// GraphIndex 빌드 (IRDocument로부터)
let index = GraphIndex::new(&ir_doc);  // 800ms (HashMap 생성)

// 특정 노드 찾기 (빠름!)
let node = index.get_node("target_id");  // O(1)

// 이름으로 찾기 (빠름!)
let nodes = index.find_nodes_by_name("build_index");  // O(1)

// 엣지 순회 (빠름!)
let outgoing = index.get_outgoing_edges("node_id");  // O(1)
```

---

## 2. 왜 둘 다 필요한가?

### 시나리오: 코드 분석 파이프라인

```
┌─────────────────────────────────────────────────────────────┐
│ Phase 1: IR Generation (파싱 & 그래프 생성)                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Tree-sitter Parse                                          │
│       ↓                                                      │
│  IRDocument { nodes: Vec<Node>, edges: Vec<Edge> }          │
│       ↓                                                      │
│  Python으로 전달 (msgpack serialization)                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Phase 2: Query Execution (검색 & 순회)                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  IRDocument (Vec<Node>, Vec<Edge>)                          │
│       ↓                                                      │
│  GraphIndex::new() - HashMap 생성 (800ms)                   │
│       ↓                                                      │
│  GraphIndex { nodes_by_id, edges_from, ... }                │
│       ↓                                                      │
│  Fast Queries (O(1) lookups, 3ms per query)                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 문제 상황 (Before PyGraphIndex)

### Old Approach: 매번 HashMap 재생성 ❌

```python
# Python
result = run_ir_indexing_pipeline(...)
# result = {"nodes": [...], "edges": [...]}  ← IRDocument (Vec형태)

# Query 1
query_nodes(result, filter1)
    ↓
# Rust에서 매번 GraphIndex 재생성!
fn query_nodes(result_bytes) {
    let ir_doc = deserialize(result_bytes);          // IRDocument (Vec)
    let index = GraphIndex::new(&ir_doc);            // 800ms ← HashMap 생성
    let results = index.find_nodes_by_name("foo");   // 3ms
    return results;
}  // ← index 파괴!

# Query 2
query_nodes(result, filter2)
    ↓
# 또 GraphIndex 재생성!
fn query_nodes(result_bytes) {
    let ir_doc = deserialize(result_bytes);          // IRDocument (Vec)
    let index = GraphIndex::new(&ir_doc);            // 800ms ← 또 HashMap 생성!
    let results = index.find_nodes_by_name("bar");   // 3ms
    return results;
}  // ← index 파괴!
```

**문제점:**
- IRDocument (Vec)는 Python에 저장됨
- 매 쿼리마다 Rust에서 GraphIndex (HashMap) 재생성
- 800ms 낭비 × N개 쿼리 = 엄청난 낭비!

---

## 4. 해결책 (PyGraphIndex)

### New Approach: HashMap을 Rust 메모리에 캐싱 ✅

```python
# Python
result = run_ir_indexing_pipeline(...)
# result = {"nodes": [...], "edges": [...]}  ← IRDocument (Vec형태)

# GraphIndex를 Rust 메모리에 한 번만 생성
graph_index = PyGraphIndex(result)
    ↓
# Rust
#[pyclass]
pub struct PyGraphIndex {
    index: GraphIndex,  // ← HashMap이 Rust 메모리에 저장됨!
}

impl PyGraphIndex {
    fn new(result_bytes) {
        let ir_doc = deserialize(result_bytes);      // IRDocument (Vec)
        let index = GraphIndex::new(&ir_doc);        // 800ms ← 한 번만!
        Self { index }  // ← Rust 메모리에 저장
    }
}

# Query 1 - 캐시된 HashMap 재사용
graph_index.query_nodes(filter1)
    ↓
fn query_nodes(&self, filter) {
    // ✅ 이미 만들어진 HashMap 사용!
    let results = self.index.find_nodes_by_name("foo");  // 3ms (no rebuild!)
    return results;
}

# Query 2 - 캐시된 HashMap 재사용
graph_index.query_nodes(filter2)
    ↓
fn query_nodes(&self, filter) {
    // ✅ 이미 만들어진 HashMap 사용!
    let results = self.index.find_nodes_by_name("bar");  // 3ms (no rebuild!)
    return results;
}
```

**해결:**
- IRDocument (Vec)는 한 번만 GraphIndex (HashMap)로 변환
- GraphIndex는 Rust 메모리에 캐싱 (PyGraphIndex 내부)
- 모든 쿼리가 캐시된 HashMap 재사용
- 800ms 비용을 1회만 지불!

---

## 5. 메모리 레이아웃

### Before (Old Approach)

```
Python Heap:
  result = {
    "nodes": [node1, node2, ...],    ← Vec (메모리 효율적)
    "edges": [edge1, edge2, ...]     ← Vec (메모리 효율적)
  }

Rust Stack (per query):
  query_nodes() {
      ir_doc = IRDocument { nodes: Vec, edges: Vec }
      index = GraphIndex {                          ← 800ms 생성
          nodes_by_id: HashMap,
          edges_from: HashMap,
          edges_to: HashMap,
          nodes_by_name: HashMap
      }
      // ... use index ...
  }  ← index 파괴! (800ms 낭비)

  query_nodes() {
      ir_doc = IRDocument { nodes: Vec, edges: Vec }
      index = GraphIndex { ... }                    ← 800ms 또 생성!
      // ... use index ...
  }  ← index 파괴! (800ms 낭비)
```

### After (PyGraphIndex)

```
Python Heap:
  result = {
    "nodes": [node1, node2, ...],    ← Vec (원본 유지)
    "edges": [edge1, edge2, ...]     ← Vec (원본 유지)
  }

  graph_index = PyGraphIndex(...)    ← Rust 객체에 대한 handle

Rust Heap (persistent):
  PyGraphIndex {
      index: GraphIndex {                           ← 800ms (한 번만!)
          nodes_by_id: HashMap,       ← 캐시됨 (persist)
          edges_from: HashMap,        ← 캐시됨 (persist)
          edges_to: HashMap,          ← 캐시됨 (persist)
          nodes_by_name: HashMap      ← 캐시됨 (persist)
      }
  }

Rust Stack (per query):
  query_nodes(&self) {
      // ✅ self.index (HashMap) 재사용!
      results = self.index.find_nodes_by_name(...)  ← 3ms (no rebuild)
  }
```

---

## 6. 정리

### IRDocument (Vec<Node>, Vec<Edge>)
- **역할**: IR 생성 결과 저장, 직렬화, Python 전달
- **장점**: 메모리 효율적, 순서 보존
- **단점**: 검색/순회 느림 (O(n))
- **사용 시점**: IR 생성, 저장, 전송

### GraphIndex (HashMap<...>)
- **역할**: 빠른 쿼리/순회를 위한 인덱스
- **장점**: O(1) 검색, 빠른 순회
- **단점**: 메모리 많이 사용, 생성 비용 800ms
- **사용 시점**: 쿼리 수행

### PyGraphIndex (GraphIndex 캐싱)
- **역할**: GraphIndex를 Rust 메모리에 캐싱
- **해결**: 매 쿼리마다 GraphIndex 재생성 방지
- **성능**: 800ms × N → 800ms × 1 (229배 speedup)

---

## 결론

**"GraphBuilder통해서 만들어진 그래프 안쓰고 HashMap으로 변환한다는거?"**

**정확히는:**

1. **IR 생성 시**: IRDocument (Vec<Node>, Vec<Edge>) 생성
   - 메모리 효율적, 직렬화 가능
   - Python으로 전달

2. **쿼리 시**: IRDocument → GraphIndex (HashMap) 변환
   - Vec → HashMap 변환 (800ms)
   - O(1) 검색을 위한 인덱스

3. **문제**: 매 쿼리마다 Vec → HashMap 재변환 (800ms 낭비)

4. **해결**: PyGraphIndex로 HashMap을 Rust 메모리에 캐싱
   - 한 번만 변환 (800ms × 1)
   - 모든 쿼리가 캐시된 HashMap 재사용 (3ms per query)

**Vec과 HashMap은 complementary:**
- Vec: 저장/전송용 (compact, serializable)
- HashMap: 검색용 (fast lookups)
- PyGraphIndex: HashMap 캐싱 (avoid rebuilding)
