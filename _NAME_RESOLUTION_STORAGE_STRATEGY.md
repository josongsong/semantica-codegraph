# Name Resolution Graph - 저장 전략

**Date:** 2024-11-24

---

## 🤔 질문: "IR에 저장? 그래프에?"

**답:** **Hybrid 접근** - 둘 다!

---

## 📊 현재 구조

### 1. IR Document (메모리 + JSON)

```python
@dataclass
class IRDocument:
    repo_id: str
    snapshot_id: str

    # Structural IR
    nodes: list[Node]        # 파일, 클래스, 함수, 변수
    edges: list[Edge]        # CONTAINS, CALLS, IMPORTS 등

    # Semantic IR
    types: list[TypeEntity]
    signatures: list[SignatureEntity]
    cfgs: list[ControlFlowGraph]

    # NEW: Name Resolution (추가 예정)
    # name_bindings: list[NameBinding] = []
    # definition_sites: list[DefinitionSite] = []
    # reference_sites: list[ReferenceSite] = []
```

**용도:**
- 메모리 상의 전체 뷰
- JSON 직렬화 (snapshot 저장)
- 전체 데이터 전송 (API)

---

### 2. Graph DB (Kuzu)

```cypher
// Nodes
CREATE (n:Node {
    id: "class:User",
    kind: "class",
    name: "User",
    fqn: "models.user.User"
})

// Edges
CREATE (a)-[:IMPORTS]->(b)
CREATE (a)-[:CALLS]->(b)
CREATE (a)-[:CONTAINS]->(b)

// NEW: Name Resolution Edges
CREATE (a)-[:DEFINES {name: "User"}]->(b)
CREATE (a)-[:REFERENCES {name: "User"}]->(b)
```

**용도:**
- 빠른 그래프 쿼리
- "누가 이 함수를 호출?"
- "이 클래스의 모든 사용처"
- 경로 찾기 (Path finding)

---

## 🎯 Name Resolution Graph 저장 전략

### ✅ **Hybrid Approach (추천)**

**원칙:**
1. **IR Document** - 모든 데이터 저장 (source of truth)
2. **Graph DB** - 쿼리 최적화용 인덱스

---

## 📦 구체적인 저장 방식

### 1️⃣ IR Document에 저장

```python
@dataclass
class IRDocument:
    # ... 기존 필드 ...

    # Name Resolution Graph (NEW!)
    name_bindings: list[NameBinding] = field(default_factory=list)
    definition_sites: list[DefinitionSite] = field(default_factory=list)
    reference_sites: list[ReferenceSite] = field(default_factory=list)


@dataclass
class NameBinding:
    """Name → Definition 매핑"""
    id: str                     # "binding:main.py:5:User"
    name: str                   # "User"
    scope_node_id: str          # "function:create_user"
    definition_node_id: str     # "class:User"
    source_location: Span       # where binding occurs
    binding_kind: str           # "local" | "imported" | "builtin"


@dataclass
class DefinitionSite:
    """심볼 정의 위치"""
    node_id: str                # IR Node ID (class:User)
    symbol_name: str            # "User"
    file_path: str              # "src/models/user.py"
    span: Span                  # 정의 위치


@dataclass
class ReferenceSite:
    """심볼 참조 위치"""
    id: str                     # "ref:main.py:5:User"
    definition_node_id: str     # "class:User"
    file_path: str              # "src/main.py"
    span: Span                  # 참조 위치
    context: str                # "read" | "write" | "call"
```

**저장:**
- IRDocument → JSON 직렬화
- Postgres `ir_documents` 테이블 (JSONB)

**장점:**
- ✅ 전체 데이터 유지
- ✅ 버전 관리 가능 (snapshot)
- ✅ 백업/복원 쉬움

**단점:**
- ❌ 쿼리 느림 (JSON 파싱)
- ❌ "누가 이 함수 호출?" 같은 역방향 쿼리 어려움

---

### 2️⃣ Graph DB에 저장

```cypher
// Definition Node
CREATE (def:Definition {
    id: "class:User",
    symbol: "User",
    file: "src/models/user.py",
    line: 2
})

// Reference Nodes
CREATE (ref1:Reference {
    id: "ref:main.py:2",
    file: "src/main.py",
    line: 2
})

// DEFINES Edge
CREATE (scope)-[:DEFINES {name: "User"}]->(def)

// REFERENCES Edge
CREATE (ref1)-[:REFERENCES]->(def)
```

**저장:**
- Kuzu Graph DB
- Node table: `Definition`, `Reference`
- Edge table: `DEFINES`, `REFERENCES`

**장점:**
- ✅ 빠른 그래프 쿼리
- ✅ 역방향 쿼리 쉬움 (`MATCH (d)<-[:REFERENCES]-(r)`)
- ✅ 경로 찾기 효율적

**단점:**
- ❌ 별도 스키마 관리
- ❌ 동기화 필요 (IR ↔ Graph)

---

## 🏗️ 최종 아키텍처

```
┌─────────────────────────────────────────┐
│         IR Document (JSON)              │
│  ┌────────────────────────────────┐     │
│  │ nodes: [...]                   │     │
│  │ edges: [...]                   │     │
│  │ types: [...]                   │     │
│  │ signatures: [...]              │     │
│  │                                │     │
│  │ name_bindings: [...]  ← NEW!  │     │
│  │ definition_sites: [...] ← NEW!│     │
│  │ reference_sites: [...] ← NEW! │     │
│  └────────────────────────────────┘     │
└──────────────┬──────────────────────────┘
               │
               │ Serialize & Store
               ├──────────────────────┐
               ▼                      ▼
    ┌──────────────────┐    ┌──────────────────┐
    │ Postgres (JSONB) │    │ File System      │
    │                  │    │ (JSON files)     │
    │ ir_documents     │    │ snapshots/       │
    │   - id           │    │   commit-123.json│
    │   - repo_id      │    └──────────────────┘
    │   - snapshot_id  │
    │   - data (JSONB) │
    └──────────────────┘
               │
               │ Index for Queries
               ▼
    ┌──────────────────────────────────┐
    │     Kuzu Graph DB                │
    │                                  │
    │  Nodes:                          │
    │    - Node (from IR)              │
    │    - Definition ← NEW!           │
    │    - Reference ← NEW!            │
    │                                  │
    │  Edges:                          │
    │    - CONTAINS, CALLS, IMPORTS    │
    │    - DEFINES ← NEW!              │
    │    - REFERENCES ← NEW!           │
    └──────────────────────────────────┘
```

---

## 🔄 데이터 흐름

### Write Path (인덱싱)

```
1. Source Code
   ↓
2. IRGenerator + Pyright
   ↓
3. IRDocument (memory)
   - nodes, edges
   - name_bindings ← Pyright.get_definition()
   - reference_sites ← Pyright.get_references()
   ↓
4. Store to Postgres (JSONB)
   ↓
5. Index to Kuzu (Graph)
   - Create Definition/Reference nodes
   - Create DEFINES/REFERENCES edges
```

### Read Path (검색)

```
Query: "User 클래스의 모든 사용처는?"

Option 1: IR Document (Postgres)
  SELECT data->>'reference_sites' FROM ir_documents
  WHERE data->'definition_sites' @> '{"symbol": "User"}'
  → Slow (JSON scan)

Option 2: Graph DB (Kuzu) ✅
  MATCH (def:Definition {symbol: "User"})<-[:REFERENCES]-(ref)
  RETURN ref.file, ref.line
  → Fast! (indexed)
```

---

## 📝 구현 순서

### Phase 1: IR Document 확장 ✅

```python
# src/foundation/ir/models/name_resolution.py
@dataclass
class NameBinding:
    ...

@dataclass
class DefinitionSite:
    ...

@dataclass
class ReferenceSite:
    ...

# src/foundation/ir/models/document.py
@dataclass
class IRDocument:
    # ... existing ...
    name_bindings: list[NameBinding] = field(default_factory=list)
    definition_sites: list[DefinitionSite] = field(default_factory=list)
    reference_sites: list[ReferenceSite] = field(default_factory=list)
```

### Phase 2: Builder 구현

```python
# src/foundation/semantic_ir/name_resolution/builder.py
class NameResolutionBuilder:
    def build(
        self,
        ir_doc: IRDocument,
        external_analyzer: ExternalAnalyzer | None
    ) -> tuple[list[NameBinding], list[DefinitionSite], list[ReferenceSite]]:
        # 1. Self-resolution (IMPORTS/CONTAINS Edge)
        # 2. Pyright enhancement (get_definition/get_references)
        ...
```

### Phase 3: Postgres 저장

```sql
-- Already exists!
CREATE TABLE ir_documents (
    id UUID PRIMARY KEY,
    repo_id VARCHAR,
    snapshot_id VARCHAR,
    data JSONB  -- IRDocument.to_json()
);

-- Index for name resolution queries
CREATE INDEX idx_name_bindings
ON ir_documents USING GIN ((data->'name_bindings'));

CREATE INDEX idx_definition_sites
ON ir_documents USING GIN ((data->'definition_sites'));
```

### Phase 4: Kuzu Graph 저장

```python
# src/foundation/storage/kuzu/name_resolution.py
class NameResolutionGraphStore:
    def store_definitions(self, definitions: list[DefinitionSite]):
        # CREATE (d:Definition {...})
        ...

    def store_references(self, references: list[ReferenceSite]):
        # CREATE (r:Reference {...})
        # CREATE (r)-[:REFERENCES]->(d)
        ...
```

---

## 🎯 정리

### 저장 위치:

| 데이터 | IR Document | Postgres | Kuzu Graph | 용도 |
|-------|-------------|----------|------------|------|
| **NameBinding** | ✅ Primary | ✅ JSONB | 🟡 Optional | Name → Definition 매핑 |
| **DefinitionSite** | ✅ Primary | ✅ JSONB | ✅ Node | 정의 위치 |
| **ReferenceSite** | ✅ Primary | ✅ JSONB | ✅ Node + Edge | 사용 위치 |

### 쿼리 전략:

| 쿼리 유형 | 사용할 저장소 | 이유 |
|----------|-------------|------|
| "전체 IR 가져오기" | **Postgres** | 한 번에 모든 데이터 |
| "심볼 정의 찾기" | **IR (캐시)** | 단순 조회 |
| "모든 사용처 찾기" | **Kuzu** | 역방향 그래프 쿼리 |
| "호출 체인 추적" | **Kuzu** | 경로 찾기 |

---

## ✅ 결론

**Q: IR에 저장? 그래프에?**

**A: 둘 다!** (Hybrid)

1. **IR Document** (Primary)
   - 모든 데이터 저장
   - Source of truth
   - Postgres JSONB

2. **Graph DB** (Index)
   - 쿼리 최적화
   - 그래프 연산
   - Kuzu

**흐름:**
```
Source → IR Document → Postgres (primary)
                     ↘ Kuzu (index)
```

**쿼리:**
- 단순 조회: IR Document (Postgres)
- 복잡한 그래프: Kuzu
