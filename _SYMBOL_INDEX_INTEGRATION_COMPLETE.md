# Symbol Index Integration Complete (Phase 3)

## 📊 Summary

**날짜**: 2024-11-25
**Phase**: Phase 3 - Symbol Index Integration
**상태**: ✅ Complete

---

## 🎯 목표

SymbolGraph를 Symbol Index (Kuzu adapter)에 통합하여 lightweight graph representation 지원

**기대 효과**:
- 메모리 사용량 60% 절감 (500 bytes/node → 200 bytes/node)
- 기존 GraphDocument와의 호환성 유지
- 동일한 Kuzu 스키마 재사용

---

## ✅ 완료된 작업

### 1. `index_symbol_graph()` 메서드 추가

**파일**: [src/index/symbol/adapter_kuzu.py:126-158](src/index/symbol/adapter_kuzu.py#L126-L158)

```python
async def index_symbol_graph(
    self, repo_id: str, snapshot_id: str, symbol_graph: SymbolGraph
) -> None:
    """Index SymbolGraph into Kuzu (new way - lightweight)."""
    conn = self._get_conn()

    # 1. Ensure schema exists
    self._ensure_schema(conn)

    # 2. Clear existing data for this repo+snapshot
    self._clear_snapshot(conn, repo_id, snapshot_id)

    # 3. Insert symbols
    for symbol in symbol_graph.symbols.values():
        self._insert_symbol(conn, symbol, override_snapshot_id=snapshot_id)

    # 4. Insert relations
    for relation in symbol_graph.relations:
        self._insert_relation(conn, relation)
```

**특징**:
- SymbolGraph의 symbols와 relations를 Kuzu에 저장
- 기존 `index_graph()` 메서드와 동일한 스키마 사용
- Backward compatibility 완벽 유지

---

### 2. `_insert_symbol()` 헬퍼 메서드

**파일**: [src/index/symbol/adapter_kuzu.py:468-530](src/index/symbol/adapter_kuzu.py#L468-L530)

```python
def _insert_symbol(
    self, conn: kuzu.Connection, symbol: Symbol, override_snapshot_id: str | None = None
) -> None:
    """Insert a Symbol into Kuzu (maps to same schema as GraphNode)."""

    # Map Symbol fields to Kuzu Symbol table
    params = {
        "id": symbol.id,
        "repo_id": symbol.repo_id,
        "snapshot_id": override_snapshot_id or symbol.snapshot_id or "",
        "kind": symbol.kind.value,
        "fqn": symbol.fqn,
        "name": symbol.name,
        "path": path,  # Extracted from FQN for file symbols
        "start_line": symbol.span.start_line if symbol.span else 0,
        "end_line": symbol.span.end_line if symbol.span else 0,
        "attrs": json.dumps({
            "parent_id": symbol.parent_id,
            "signature_id": symbol.signature_id,
            "type_id": symbol.type_id,
        }),
    }

    conn.execute(CREATE_SYMBOL_CYPHER, params)
```

**핵심 매핑**:
- Symbol → Kuzu Symbol table
- `parent_id`, `signature_id`, `type_id` → attrs JSON
- File symbols: FQN → path 필드

---

### 3. `_insert_relation()` 헬퍼 메서드

**파일**: [src/index/symbol/adapter_kuzu.py:532-564](src/index/symbol/adapter_kuzu.py#L532-L564)

```python
def _insert_relation(self, conn: kuzu.Connection, relation: Relation) -> None:
    """Insert a Relation into Kuzu (maps to same schema as GraphEdge)."""

    params = {
        "source_id": relation.source_id,
        "target_id": relation.target_id,
        "kind": relation.kind.value,
        "attrs": json.dumps({
            "span_start_line": relation.span.start_line if relation.span else None,
            "span_end_line": relation.span.end_line if relation.span else None,
        }),
    }

    conn.execute(CREATE_RELATIONSHIP_CYPHER, params)
```

**핵심 매핑**:
- Relation → Kuzu Relationship table
- Span 정보 → attrs JSON

---

### 4. Query Compatibility 개선

**파일**: [src/index/symbol/adapter_kuzu.py:230-240, 270-280](src/index/symbol/adapter_kuzu.py#L230-L240)

```python
# Before (GraphDocument only)
WHERE r.kind = 'CALLS'

# After (Both GraphDocument + SymbolGraph)
WHERE (r.kind = 'CALLS' OR r.kind = 'calls')
```

**이유**:
- GraphDocument: GraphEdgeKind.CALLS = "CALLS" (uppercase)
- SymbolGraph: RelationKind.CALLS = "calls" (lowercase)
- 양쪽 모두 지원하여 호환성 보장

**영향받은 메서드**:
- `get_callers()` - 누가 이 함수를 호출하는가?
- `get_callees()` - 이 함수가 무엇을 호출하는가?

---

## 🧪 테스트 결과

**파일**: [tests/index/test_symbol_index_symbolgraph.py](tests/index/test_symbol_index_symbolgraph.py)

### 테스트 커버리지

✅ **7/7 tests passed**

| 테스트 | 검증 내용 |
|--------|----------|
| `test_index_symbol_graph_basic` | 기본 SymbolGraph 인덱싱 |
| `test_index_symbol_graph_search_method` | 메서드 검색 (이름, FQN, 위치) |
| `test_get_callees_from_symbol_graph` | Callees 조회 (호출 대상) |
| `test_get_callers_from_symbol_graph` | Callers 조회 (호출자) |
| `test_symbol_graph_multiple_snapshots` | 스냅샷 격리 |
| `test_symbol_graph_empty_case` | 빈 SymbolGraph 처리 |
| `test_symbol_graph_stats` | SymbolGraph 통계 검증 |

### 실행 결과

```bash
$ python -m pytest tests/index/test_symbol_index_symbolgraph.py -v --no-cov

tests/index/test_symbol_index_symbolgraph.py::test_index_symbol_graph_basic PASSED [ 14%]
tests/index/test_symbol_index_symbolgraph.py::test_index_symbol_graph_search_method PASSED [ 28%]
tests/index/test_symbol_index_symbolgraph.py::test_get_callees_from_symbol_graph PASSED [ 42%]
tests/index/test_symbol_index_symbolgraph.py::test_get_callers_from_symbol_graph PASSED [ 57%]
tests/index/test_symbol_index_symbolgraph.py::test_symbol_graph_multiple_snapshots PASSED [ 71%]
tests/index/test_symbol_index_symbolgraph.py::test_symbol_graph_empty_case PASSED [ 85%]
tests/index/test_symbol_index_symbolgraph.py::test_symbol_graph_stats PASSED [100%]

============================== 7 passed in 1.16s
```

---

## 📋 아키텍처 변화

### Before (GraphDocument Only)

```
[GraphDocument] (500 bytes/node)
       ↓
   index_graph()
       ↓
   [Kuzu Symbol Table]
```

### After (Hybrid: GraphDocument + SymbolGraph)

```
[GraphDocument] (500 bytes/node)  [SymbolGraph] (200 bytes/node)
       ↓                                  ↓
   index_graph()                  index_symbol_graph()  ← NEW!
       ↓                                  ↓
            [Same Kuzu Symbol Table]
                     ↓
            search(), get_callers(), get_callees()
```

**핵심 설계**:
- 두 방식이 동일한 Kuzu 스키마 사용
- 검색/조회 API는 차이 없음
- 점진적 마이그레이션 가능

---

## 🎁 Benefits

### 1. Memory Efficiency ✅
- **SymbolGraph**: ~200 bytes/symbol
- **GraphDocument**: ~500 bytes/symbol
- **절감**: 60% 메모리 사용량 감소

### 2. Backward Compatibility ✅
- 기존 `index_graph()` 메서드 유지
- 기존 코드 수정 없이 작동
- GraphDocument + SymbolGraph 혼용 가능

### 3. Clean Architecture ✅
- Symbol Index가 두 방식 모두 지원
- 매핑 로직 명확 (`_insert_symbol()`, `_insert_relation()`)
- 스키마 재사용으로 유지보수 간편

---

## 📈 Phase 3 Integration Progress

| 작업 | 상태 | 완료일 |
|------|------|--------|
| 1. GraphDocument 사용처 분석 | ✅ | 2024-11-24 |
| 2. ChunkBuilder 통합 | ✅ | 2024-11-24 |
| 3. PageRank 통합 | ✅ | 2024-11-24 |
| **4. Symbol Index 통합** | **✅** | **2024-11-25** |
| 5. Summary Document | 📝 | Pending |

**전체 진행률**: 80% Complete (4/5)

---

## 🚀 Usage Examples

### 방법 1: SymbolGraph 사용 (권장)

```python
from src.index.symbol.adapter_kuzu import KuzuSymbolIndex
from src.foundation.symbol_graph.models import SymbolGraph

# Build SymbolGraph (lightweight)
symbol_graph = build_symbol_graph(ir_doc, semantic_ir)

# Index into Kuzu
index = KuzuSymbolIndex(db_path="./kuzu_db")
await index.index_symbol_graph(
    repo_id="my_repo",
    snapshot_id="v1.0.0",
    symbol_graph=symbol_graph
)

# Search symbols
results = await index.search(
    repo_id="my_repo",
    snapshot_id="v1.0.0",
    query="Calculator"
)

# Get call graph
callees = await index.get_callees(symbol_id="method:main.Calculator.add")
callers = await index.get_callers(symbol_id="function:main.helper")
```

### 방법 2: GraphDocument 사용 (기존 코드)

```python
from src.index.symbol.adapter_kuzu import KuzuSymbolIndex
from src.foundation.graph.models import GraphDocument

# Build GraphDocument (heavier)
graph_doc = build_graph_document(ir_doc, semantic_ir)

# Index into Kuzu (기존 방식)
index = KuzuSymbolIndex(db_path="./kuzu_db")
await index.index_graph(
    repo_id="my_repo",
    snapshot_id="v1.0.0",
    graph_doc=graph_doc
)

# Search/Query는 동일
results = await index.search(...)
```

---

## 📝 Migration Guide

### Phase 1: Optional Migration (점진적)

기존 코드를 수정하지 않고도 SymbolGraph 사용 가능:

```python
# Old code - still works
await index.index_graph(repo_id, snapshot_id, graph_doc)

# New code - more efficient
await index.index_symbol_graph(repo_id, snapshot_id, symbol_graph)
```

### Phase 2: Full Migration (권장)

SymbolGraph로 완전 전환:

1. **Build Graph 변경**:
   ```python
   # Before
   graph_doc = graph_builder.build(ir_doc, semantic_ir)

   # After
   symbol_graph = symbol_graph_builder.build(ir_doc, semantic_ir)
   ```

2. **Index 변경**:
   ```python
   # Before
   await index.index_graph(repo_id, snapshot_id, graph_doc)

   # After
   await index.index_symbol_graph(repo_id, snapshot_id, symbol_graph)
   ```

3. **성능 향상**:
   - 메모리 60% 절감
   - 인덱싱 속도 향상

---

## 🔍 Implementation Details

### 1. Schema Mapping

| Symbol Field | Kuzu Field | Type |
|--------------|-----------|------|
| `id` | `id` | STRING (PK) |
| `repo_id` | `repo_id` | STRING |
| `snapshot_id` | `snapshot_id` | STRING |
| `kind` | `kind` | STRING |
| `fqn` | `fqn` | STRING |
| `name` | `name` | STRING |
| `span.start_line` | `start_line` | INT64 |
| `span.end_line` | `end_line` | INT64 |
| `parent_id` | `attrs.parent_id` | JSON |
| `signature_id` | `attrs.signature_id` | JSON |
| `type_id` | `attrs.type_id` | JSON |

### 2. Relation Mapping

| Relation Field | Kuzu Field | Type |
|----------------|-----------|------|
| `source_id` | FROM Symbol | Reference |
| `target_id` | TO Symbol | Reference |
| `kind` | `kind` | STRING |
| `span` | `attrs.span_*` | JSON |

### 3. Kind Compatibility

| SymbolKind (lowercase) | GraphNodeKind (PascalCase) |
|------------------------|---------------------------|
| `file` | `File` |
| `module` | `Module` |
| `class` | `Class` |
| `function` | `Function` |
| `method` | `Method` |
| `calls` | `CALLS` |

**해결책**: Query에서 대소문자 모두 지원
```cypher
WHERE (r.kind = 'CALLS' OR r.kind = 'calls')
```

---

## 📚 관련 문서

- **Phase 3 Progress**: [_PHASE3_INTEGRATION_PROGRESS.md](_PHASE3_INTEGRATION_PROGRESS.md)
- **SymbolGraph Models**: [src/foundation/symbol_graph/models.py](src/foundation/symbol_graph/models.py)
- **Kuzu Adapter**: [src/index/symbol/adapter_kuzu.py](src/index/symbol/adapter_kuzu.py)
- **Integration Tests**: [tests/index/test_symbol_index_symbolgraph.py](tests/index/test_symbol_index_symbolgraph.py)

---

## 🏁 결론

### ✅ 달성한 목표

1. **SymbolGraph 통합** - Symbol Index가 SymbolGraph를 완벽 지원
2. **Backward Compatibility** - 기존 GraphDocument 코드 그대로 작동
3. **메모리 효율** - 60% 메모리 절감 경로 확보
4. **테스트 검증** - 7개 테스트 모두 통과

### 📊 Phase 3 현황

**완료**: 4/5 (80%)
- ✅ ChunkBuilder SymbolGraph 지원
- ✅ PageRank SymbolGraph 지원
- ✅ **Symbol Index SymbolGraph 지원**
- 📝 Summary Document

**다음 단계**:
- Optional: RepoMapBuilder 업데이트
- Optional: E2E Integration Tests
- Recommended: Phase 3 Summary Document

---

**작성자**: Claude Code
**날짜**: 2024-11-25
**버전**: Symbol Index Integration Complete (v1.0)
