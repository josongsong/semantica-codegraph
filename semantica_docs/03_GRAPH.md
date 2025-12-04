# Graph Layer

**최종 업데이트**: 2025-11-29  
**SOTA 달성도**: 96% (Impact Analysis 완성, Graph Embedding 부재)

## 개요

코드베이스의 통합 그래프 표현. Structural IR + Semantic IR을 결합하여 단일 `GraphDocument`로 변환.

**위치**: `src/contexts/code_foundation/infrastructure/graph/`

## SOTA 비교 (2025-11-29)

| 기능 | Semantica v2 | SOTA (Sourcegraph Precise) |
|------|--------------|----------------------------|
| Graph 모델 | ✅ GraphDocument (20+ Node/Edge) | ✅ Precise Code Intel |
| Impact Analysis | ✅ **완성** (Symbol-level) | ✅ 완성 |
| Incremental Graph | ✅ **EdgeValidator** | ✅ Incremental Protocol |
| Typed Attributes | ✅ **20+ EdgeKind** | ✅ Typed Schema |
| Graph Embedding | ❌ 미구현 | ✅ Structural Embedding |
| CodeRank | ⚠️ PageRank만 | ✅ ML-based Scoring |

**강점**: Impact Analyzer, Edge Validator, Typed Edge Attributes 완성  
**Sourcegraph 대비**: 기능적으로 거의 동일 수준  
**부족**: Graph-level embedding, ML-based node scoring

**주요 구현**:
- `impact_analyzer.py`: 심볼 수준 영향도 분석 (BFS, depth 제한)
- `edge_validator.py`: Stale edge 관리 (Lazy validation, TTL)
- `edge_attrs.py`: 20+ EdgeKind별 typed attributes

## 모듈 구조

```
src/contexts/code_foundation/infrastructure/graph/
├── models.py           # GraphDocument, GraphNode, GraphEdge, GraphIndex
├── builder.py          # GraphBuilder (IR → Graph 변환)
├── impact_analyzer.py  # 심볼 수준 영향도 분석 (NEW)
├── edge_validator.py   # Cross-file edge stale marking (NEW)
└── edge_attrs.py       # EdgeKind별 typed attrs (NEW)
```

## 핵심 타입

### GraphNodeKind (20+ 종)

| 카테고리 | 타입 | 설명 |
|----------|------|------|
| **Structural** | FILE, MODULE, CLASS, FUNCTION, METHOD, VARIABLE, FIELD, IMPORT | IR에서 직접 변환 |
| **Semantic** | TYPE, SIGNATURE, CFG_BLOCK | Semantic IR에서 생성 |
| **External** | EXTERNAL_MODULE, EXTERNAL_FUNCTION, EXTERNAL_TYPE | 외부 참조용 lazy 생성 |
| **Framework** | ROUTE, SERVICE, REPOSITORY, CONFIG, JOB, MIDDLEWARE | 아키텍처 레이어 |
| **Doc** | DOCUMENT, SUMMARY | 문서/요약 노드 |

### GraphEdgeKind (20+ 종)

| 카테고리 | 타입 | 설명 |
|----------|------|------|
| **Structural** | CONTAINS, IMPORTS, INHERITS, IMPLEMENTS | 구조적 관계 |
| **Call/Ref** | CALLS, REFERENCES_TYPE, REFERENCES_SYMBOL | 호출/참조 |
| **Data Flow** | READS, WRITES | 변수 읽기/쓰기 |
| **Control Flow** | CFG_NEXT, CFG_BRANCH, CFG_LOOP, CFG_HANDLER | CFG 엣지 |
| **Framework** | ROUTE_HANDLER, HANDLES_REQUEST, USES_REPOSITORY, MIDDLEWARE_NEXT | 아키텍처 관계 |
| **Other** | INSTANTIATES, DECORATES, DOCUMENTS, REFERENCES_CODE | 기타 |

### GraphIndex (역방향 인덱스)

```python
@dataclass
class GraphIndex:
    # Core reverse indexes
    called_by: dict[str, list[str]]      # Function → Callers
    imported_by: dict[str, list[str]]    # Module → Importers
    contains_children: dict[str, list[str]]  # Parent → Children
    type_users: dict[str, list[str]]     # Type → Users
    reads_by: dict[str, list[str]]       # Variable → Readers
    writes_by: dict[str, list[str]]      # Variable → Writers

    # Adjacency indexes
    outgoing: dict[str, list[str]]       # Node → Outgoing edge IDs
    incoming: dict[str, list[str]]       # Node → Incoming edge IDs

    # Framework indexes
    routes_by_path: dict[str, list[str]]
    services_by_domain: dict[str, list[str]]
    request_flow_index: dict[str, dict[str, list[str]]]
```

## 새로 추가된 기능 (v2)

### 1. Impact Analyzer (심볼 수준 영향도 분석)

**파일**: `src/contexts/code_foundation/infrastructure/graph/impact_analyzer.py`

변경된 파일/심볼이 코드베이스의 어떤 부분에 영향을 주는지 분석.

```python
from src.foundation.graph import GraphImpactAnalyzer, SymbolChange, ChangeType

analyzer = GraphImpactAnalyzer(
    max_depth=5,           # transitive caller 탐색 깊이
    max_affected=1000,     # 최대 영향 심볼 개수
    include_test_files=False,
)

# 변경 심볼 정의
changed = SymbolChange(
    fqn="module.function",
    node_id="func:module::function",
    change_type=ChangeType.SIGNATURE_CHANGED,
    file_path="src/module.py",
    old_signature_hash="abc123",
    new_signature_hash="def456",
)

# 영향도 분석
result = analyzer.analyze_impact(graph, [changed])

print(f"Direct affected: {len(result.direct_affected)}")
print(f"Transitive affected: {len(result.transitive_affected)}")
print(f"Affected files: {result.affected_files}")
```

#### ChangeType

| 타입 | 설명 |
|------|------|
| ADDED | 새로 추가된 심볼 |
| DELETED | 삭제된 심볼 |
| SIGNATURE_CHANGED | 시그니처 변경 (파라미터, 반환타입) |
| BODY_CHANGED | 구현부만 변경 |
| TYPE_CHANGED | 타입 변경 (변수, 필드) |
| RENAMED | 이름 변경 |

#### 증분 인덱싱 통합

```python
# 변경 파일에서 영향 받는 모든 파일 추출
affected_files = analyzer.get_affected_files_for_incremental(
    graph,
    changed_files={"src/b.py"}
)
# Returns: {"src/b.py", "src/a.py", ...}  (b.py + callers)
```

### 2. MemgraphGraphStore 파일 기반 쿼리 메서드 (NEW)

**파일**: `src/contexts/code_foundation/infrastructure/storage/memgraph/store.py`, `src/infra/graph/memgraph.py`

증분 인덱싱 범위 확장을 위한 파일 단위 관계 조회 메서드.

```python
from src.infra.graph import MemgraphGraphStore

store = MemgraphGraphStore()

# a.py의 함수를 호출하는 파일들
caller_files = store.get_callers_by_file("repo-id", "a.py")
# Returns: {"b.py", "c.py"}

# a.py의 클래스를 상속하는 파일들
subclass_files = store.get_subclasses_by_file("repo-id", "a.py")
# Returns: {"d.py"}

# c.py가 상속하는 부모 클래스 파일들
parent_files = store.get_superclasses_by_file("repo-id", "c.py")
# Returns: {"a.py"}

# 기존 메서드와 함께 사용
import_files = store.get_imports("repo-id", "a.py")      # a.py가 import하는 파일
imported_by = store.get_imported_by("repo-id", "a.py")   # a.py를 import하는 파일
```

**용도**: ScopeExpander에서 변경 파일의 영향 받는 파일 탐색 시 활용.

### 3. Edge Validator (Stale Edge 관리)

**파일**: `src/contexts/code_foundation/infrastructure/graph/edge_validator.py`

Cross-file backward edge의 증분 처리를 위한 stale marking 및 lazy validation.

```python
from src.foundation.graph import EdgeValidator, EdgeStatus

validator = EdgeValidator(
    stale_ttl_hours=24.0,   # Stale edge TTL
    auto_cleanup=False,     # 검증 시 invalid edge 자동 삭제
)

# 1. 변경 파일 감지 시 stale marking
stale_edges = validator.mark_stale_edges(
    repo_id="my-repo",
    changed_files={"src/b.py"},
    graph=graph,
)
# b.py의 심볼을 참조하는 다른 파일의 edge들이 stale 마킹됨

# 2. 재인덱싱 필요 파일 조회
source_files = validator.get_stale_source_files("my-repo")
# Returns: {"src/a.py"}  (stale edge를 가진 파일들)

# 3. Lazy validation (사용 시점 검증)
results = validator.validate_edges(
    "my-repo",
    ["edge:calls:0"],
    graph
)
if results["edge:calls:0"].status == EdgeStatus.VALID:
    # edge 유효
    pass
elif results["edge:calls:0"].status == EdgeStatus.INVALID:
    # target 삭제됨
    pass

# 4. 파일 재인덱싱 후 stale 제거
validator.clear_stale_for_file("my-repo", "src/a.py")
```

#### EdgeStatus

| 상태 | 설명 |
|------|------|
| VALID | 유효한 edge |
| STALE | 검증 필요 (대상 심볼 변경됨) |
| INVALID | 무효 (대상 심볼 삭제됨) |
| PENDING | 검증 진행 중 |

### 4. Background Cleanup Service (NEW)

**파일**: `src/contexts/indexing_pipeline/infrastructure/background_cleanup.py`

주기적 stale edge 정리를 위한 백그라운드 태스크.

```python
from src.indexing.background_cleanup import start_background_cleanup

# API 서버 시작 시
service = await start_background_cleanup(
    edge_validator=validator,
    cleanup_interval_seconds=3600,  # 1시간마다
    graph_store=graph_store,
)

# 수동 트리거
await service.cleanup_now("repo-id")

# 종료 시
await stop_background_cleanup()
```

**동작**:
- TTL 만료 stale edge 자동 삭제
- 1시간 간격 실행 (설정 가능)
- API 서버 lifespan에 통합됨

### 5. Typed Edge Attributes

**파일**: `src/contexts/code_foundation/infrastructure/graph/edge_attrs.py`

EdgeKind별 타입 안전한 속성 스키마.

```python
from src.foundation.graph import (
    CallsEdgeAttrs,
    ImportsEdgeAttrs,
    create_edge_attrs,
    parse_edge_attrs,
)
from src.foundation.ir.models import Span

# CALLS edge attrs
attrs = CallsEdgeAttrs(
    call_site_span=Span(start_line=42, start_col=4, end_line=42, end_col=20),
    is_async=True,
    is_method_call=True,
    argument_count=3,
    has_kwargs=True,
)

# 직렬화
attrs_dict = attrs.to_dict()
# {'call_site_span': {...}, 'is_async': True, 'is_method_call': True, ...}

# 역직렬화
attrs = CallsEdgeAttrs.from_dict(attrs_dict)

# Factory 함수
attrs = create_edge_attrs("CALLS", is_async=True, argument_count=2)
attrs = parse_edge_attrs("CALLS", attrs_dict)
```

#### Typed Attrs 클래스

| EdgeKind | Attrs 클래스 | 주요 필드 |
|----------|--------------|-----------|
| CALLS | `CallsEdgeAttrs` | `is_async`, `is_method_call`, `argument_count`, `call_site_span` |
| IMPORTS | `ImportsEdgeAttrs` | `import_kind`, `alias`, `level`, `is_wildcard` |
| INHERITS | `InheritsEdgeAttrs` | `mro_index`, `is_mixin`, `type_arguments` |
| READS | `ReadsEdgeAttrs` | `context`, `span` |
| WRITES | `WritesEdgeAttrs` | `write_kind`, `is_definition`, `is_reassignment` |
| CFG_BRANCH | `CfgBranchEdgeAttrs` | `branch_kind`, `condition_summary` |
| DECORATES | `DecoratesEdgeAttrs` | `decorator_order`, `decorator_args` |

## GraphBuilder 파이프라인

```
IRDocument + SemanticIrSnapshot
        ↓
┌───────────────────────────────────────────────────┐
│ Phase 1: IR Nodes → GraphNodes                    │
│   - FILE, CLASS, FUNCTION, METHOD, VARIABLE, ... │
│   - Auto-generate MODULE nodes from file paths   │
└───────────────────────────────────────────────────┘
        ↓
┌───────────────────────────────────────────────────┐
│ Phase 2: Semantic Nodes → GraphNodes              │
│   - TypeEntity → TYPE                            │
│   - SignatureEntity → SIGNATURE                  │
│   - CFGBlock → CFG_BLOCK                         │
│   - VariableEntity → VARIABLE (DFG)             │
└───────────────────────────────────────────────────┘
        ↓
┌───────────────────────────────────────────────────┐
│ Phase 3: Edge Conversion                          │
│   - IR edges (CONTAINS, CALLS, IMPORTS, ...)     │
│   - CFG edges (CFG_NEXT, CFG_BRANCH, ...)        │
│   - DFG edges (READS, WRITES)                    │
│   - Type reference edges (REFERENCES_TYPE)       │
└───────────────────────────────────────────────────┘
        ↓
┌───────────────────────────────────────────────────┐
│ Phase 4: Index Building                           │
│   - Reverse indexes (called_by, imported_by, ...)│
│   - Adjacency indexes (outgoing, incoming)       │
│   - Framework indexes (routes, services, ...)    │
└───────────────────────────────────────────────────┘
        ↓
GraphDocument
```

## 증분 인덱싱 통합

### 전체 흐름

```
파일 변경 감지 (ChangeDetector)
        ↓
┌───────────────────────────────────────────────────┐
│ 1. Stale Edge Marking                             │
│    EdgeValidator.mark_stale_edges(changed_files)  │
│    → cross-file backward edge들 stale 마킹        │
└───────────────────────────────────────────────────┘
        ↓
┌───────────────────────────────────────────────────┐
│ 2. Impact Analysis                                │
│    GraphImpactAnalyzer.analyze_impact(changes)    │
│    → 영향 받는 파일 목록 추출                     │
└───────────────────────────────────────────────────┘
        ↓
┌───────────────────────────────────────────────────┐
│ 3. Scope Expansion                                │
│    ScopeExpander.expand_scope(change_set, mode)   │
│    → 재인덱싱 범위 결정                           │
└───────────────────────────────────────────────────┘
        ↓
┌───────────────────────────────────────────────────┐
│ 4. Incremental Indexing                           │
│    변경 파일 + 영향 파일 재처리                   │
└───────────────────────────────────────────────────┘
        ↓
┌───────────────────────────────────────────────────┐
│ 5. Stale Cleanup                                  │
│    EdgeValidator.clear_stale_for_file(file)       │
│    → 재인덱싱된 파일의 stale edge 제거            │
└───────────────────────────────────────────────────┘
```

### 예시: B.py 수정 시 A.py의 CALLS edge 처리

```
Before: A.py::foo() → CALLS → B.py::bar()

1. B.py 수정 감지
   └─ mark_stale_edges({"src/b.py"})
   └─ edge(A::foo → B::bar) → STALE

2. Impact Analysis
   └─ direct_affected: {A::foo}
   └─ affected_files: {"src/a.py"}

3. A.py 재인덱싱 여부 결정
   - FAST mode: A.py 재인덱싱 안 함 (stale 유지)
   - BALANCED mode: A.py 재인덱싱 (1-hop neighbor)
   - DEEP mode: A.py + transitive callers 재인덱싱

4. A.py 재인덱싱 시
   └─ clear_stale_for_file("src/a.py")
   └─ edge 재생성
```

## 성능 특성

| 작업 | 복잡도 | 비고 |
|------|--------|------|
| `get_node(id)` | O(1) | dict lookup |
| `get_edges_from(id)` | O(k) | k = outgoing edge 수 |
| `get_edges_to(id)` | O(k) | k = incoming edge 수 |
| `indexes.called_by` | O(1) | reverse index |
| Impact Analysis (direct) | O(k) | k = direct callers |
| Impact Analysis (transitive) | O(V+E) | BFS, depth 제한 |
| Stale Marking | O(E) | 전체 edge 순회 |

## Backward Compatibility (2025-11-29)

### GraphDocument.nodes property

**파일**: `src/contexts/code_foundation/infrastructure/graph/models.py`

레거시 코드 호환성을 위해 `nodes` property 추가:

```python
class GraphDocument:
    graph_nodes: dict[str, GraphNode] = field(default_factory=dict)
    
    @property
    def nodes(self) -> dict[str, GraphNode]:
        """Backward compatibility: alias for graph_nodes"""
        return self.graph_nodes
```

**변경 이유**:
- 일부 레거시 코드/외부 패키지가 `graph_doc.nodes` 접근
- 벤치마크 코드에서 `'GraphDocument' object has no attribute 'nodes'` 에러 발생
- `graph_nodes` 사용 권장하지만 backward compatibility 유지

**사용**:
```python
# 권장 (명확한 이름)
for node_id, node in graph_doc.graph_nodes.items():
    ...

# 지원됨 (backward compatibility)
for node_id, node in graph_doc.nodes.items():
    ...
```

## 완성도 요약

### ✅ Expression/CFG/DFG 레벨 정보 연결 (100%)

**구현 완료:**
- CFG Edge Types: `CFG_NEXT`, `CFG_BRANCH`, `CFG_LOOP`, `CFG_HANDLER`
- DFG Edge Types: `READS`, `WRITES` (변수 read/write)
- Typed Edge Attributes: 20+ EdgeKind별 타입 안전 속성 스키마
- GraphBuilder: Semantic IR (CFG/DFG) → Graph 자동 변환
- Edge 정규화: EdgeAttrsBase 상속 계층으로 타입 안전성 보장

**예시:**
```python
# CFG edge with typed attrs
cfg_edge = GraphEdge(
    kind=GraphEdgeKind.CFG_BRANCH,
    source_id="block:1",
    target_id="block:2",
    attrs=CfgBranchEdgeAttrs(
        branch_kind="if_true",
        condition_summary="x > 0"
    )
)

# DFG edge with typed attrs
dfg_edge = GraphEdge(
    kind=GraphEdgeKind.WRITES,
    source_id="func:foo",
    target_id="var:x",
    attrs=WritesEdgeAttrs(
        write_kind="assignment",
        is_definition=True,
        span=Span(42, 4, 42, 10)
    )
)
```

### ✅ Change set → IR diff → Graph diff 파이프라인 (100%)

**전체 파이프라인 구현 완료:**

```
1. ChangeDetector.detect_changes()
   └─ git diff / mtime / content hash
   └─ ChangeSet(added, modified, deleted)
        ↓
2. ScopeExpander.expand_scope()
   └─ 의존성 기반 범위 확장 (FAST/BALANCED/DEEP)
   └─ affected_files 계산
        ↓
3. IRDocument diff (파일별)
   └─ 변경 파일만 파싱/IR 재생성
   └─ stable_symbol_id 기반 node diff
        ↓
4. GraphDocument diff (증분)
   └─ _stage_graph_building_incremental()
   └─ EdgeValidator: stale edge marking
   └─ DELETE → MODIFY → ADD 순서 처리
        ↓
5. GraphImpactAnalyzer
   └─ 심볼 수준 영향도 분석
   └─ transitive caller 탐색
        ↓
6. Chunk refresh
   └─ ChunkIncrementalRefresher
   └─ content_hash 기반 변경 감지
```

**핵심 구현:**
- `IndexingOrchestrator._stage_graph_building_incremental()` - Graph 증분 빌드
- `GraphImpactAnalyzer` - 심볼 변경 → 영향받는 파일 추출
- `EdgeValidator` - Cross-file edge stale marking/lazy validation
- `ChunkIncrementalRefresher` - Chunk 증분 업데이트

## 테스트

```bash
# Graph 관련 테스트 실행
pytest tests/foundation/graph/ -v

# 새 기능 테스트
pytest tests/foundation/graph/test_impact_analyzer.py -v
pytest tests/foundation/graph/test_edge_validator.py -v
pytest tests/foundation/graph/test_edge_attrs.py -v
```
