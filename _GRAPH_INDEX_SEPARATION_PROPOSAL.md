# SymbolGraph vs SearchIndex Separation Proposal

## 🎯 핵심 아이디어

**현재**: GraphDocument가 모든 역할 담당 (의미 관계 + 검색 최적화)
**제안**: 역할 분리
- **SymbolGraph**: 심볼 간 의미 관계 (가볍게, Chunk/RepoMap용)
- **SearchIndex**: 검색 최적화 (무겁게, Retriever용)

---

## 📊 아키텍처 비교

### Before (현재)
```
IR → GraphDocument (무거움, 500 bytes/node)
     ├─ GraphNode (id, fqn, name, span, attrs)
     ├─ GraphEdge (CALLS, IMPORTS, CONTAINS)
     └─ GraphIndex (called_by, name_to_nodes, ...)
          ↓
     ┌────┴────┐
Chunk      RepoMap      Search
```

### After (분리)
```
IR → SymbolGraph (가벼움, 200 bytes/node)
     ├─ Symbol (id, fqn, name, span)
     ├─ Relation (CALLS, IMPORTS, CONTAINS)
     └─ RelationIndex (caller_to_callees, parent_to_children)
          ↓
     ┌────┴────┐
     │         │
Chunk      RepoMap


IR + SymbolGraph → SearchIndex (무거움, Retriever 전용)
                   ├─ SearchableSymbol (name, call_count, embeddings)
                   ├─ SearchableRelation (frequency, is_critical)
                   └─ QueryIndexes (name, fqn, signature, fuzzy)
                        ↓
                   Retriever
```

---

## 🏗️ 구조 설계

### 1. SymbolGraph (가볍게)

**목적**: 코드 심볼 간의 의미 관계만 표현

```python
@dataclass
class Symbol:
    """Light-weight code symbol"""
    id: str           # FQN-based stable ID
    kind: SymbolKind  # CLASS, FUNCTION, VARIABLE, etc.
    fqn: str          # Fully qualified name
    name: str         # Simple name
    span: Span | None # Source location

    # 필수 관계만 (ID 참조)
    parent_id: str | None      # 부모 심볼
    signature_id: str | None   # 시그니처 (함수만)
    type_id: str | None        # 타입 정보

@dataclass
class Relation:
    """Semantic relationship between symbols"""
    source_id: str        # 시작 심볼
    target_id: str        # 대상 심볼
    kind: RelationKind    # CALLS, IMPORTS, CONTAINS, INHERITS

    # 위치 정보만 (검색용 아님)
    span: Span | None

class SymbolKind(str, Enum):
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    # ... 등

class RelationKind(str, Enum):
    CALLS = "calls"           # A calls B
    IMPORTS = "imports"       # A imports B
    CONTAINS = "contains"     # A contains B
    INHERITS = "inherits"     # A inherits B
    REFERENCES = "references" # A references B

@dataclass
class RelationIndex:
    """Basic indexes for graph traversal"""
    # 관계 탐색용 역색인만 (검색 X)
    parent_to_children: dict[str, list[str]]
    caller_to_callees: dict[str, list[str]]
    callee_to_callers: dict[str, list[str]]

@dataclass
class SymbolGraph:
    """Light-weight semantic graph for code symbols"""
    repo_id: str
    snapshot_id: str
    symbols: dict[str, Symbol]       # All symbols indexed by ID
    relations: list[Relation]        # All relationships
    indexes: RelationIndex           # Basic traversal indexes
```

**특징**:
- ✅ Symbol: 노드당 ~200 bytes (attrs 제거)
- ✅ Relation: 의미 관계만 (CALLS, IMPORTS, CONTAINS)
- ✅ Chunk/RepoMap의 Single Source of Truth
- ✅ In-memory에서 빠른 그래프 탐색
- ✅ 이름이 직관적 (Symbol = 코드 심볼, Relation = 관계)

**스토리지 (Port-Adapter 패턴)**:
```
In-Memory Graph (Primary) ⭐
├─ Python dict/list 자료구조
├─ symbols: dict[str, Symbol]
├─ relations: list[Relation]
├─ indexes: RelationIndex
└─ Performance: <10ms

SymbolGraphPort (Interface)
├─ save(graph: SymbolGraph) -> None
├─ load(repo_id, snapshot_id) -> SymbolGraph
└─ delete(repo_id, snapshot_id) -> None

PostgreSQLAdapter (Implementation)
├─ symbols 테이블에 저장
├─ relations 테이블에 저장
└─ Performance: 100ms+ (영속성)
```

---

### 2. SearchIndex (검색 최적화)

**목적**: 검색/리트리벌 성능 최적화

```python
@dataclass
class SearchableSymbol:
    """Search-optimized symbol with ranking signals"""
    id: str  # Symbol.id와 동일

    # Text search (정규화)
    search_name: str        # Lowercase, 정규화된 이름
    fqn_parts: list[str]    # FQN 분리 (prefix 매칭용)
    fuzzy_trigrams: set[str]  # Trigram (오타 허용)

    # Ranking signals (검색 순위)
    call_count: int         # 호출 횟수 (인기도)
    reference_count: int    # 참조 횟수
    is_public: bool         # Public API 여부
    is_test: bool           # 테스트 코드 제외
    complexity: int         # 복잡도 (간단한 것 우선)

    # Documentation search (의미 검색)
    docstring: str | None
    doc_embedding: list[float] | None  # Vector search

    # Signature search (타입 기반)
    param_types: list[str] | None  # 함수 파라미터 타입
    return_type: str | None        # 반환 타입

@dataclass
class SearchableRelation:
    """Search-optimized relation with frequency"""
    source_id: str
    target_id: str
    kind: str

    # Ranking signals
    frequency: int      # 호출/참조 빈도 (hot path)
    is_critical: bool   # Critical path 여부

@dataclass
class QueryIndexes:
    """Pre-built query indexes"""
    # Name search
    name_to_symbols: dict[str, list[str]]  # "UserService" → [symbol_ids]

    # FQN prefix search (autocomplete)
    fqn_prefix_to_symbols: dict[str, list[str]]  # "src.services." → symbols

    # Fuzzy search (typo tolerance)
    trigram_to_symbols: dict[str, set[str]]  # "use" → {symbol_ids with "use"}

    # Scope search
    file_to_symbols: dict[str, list[str]]    # File path → symbols
    class_to_members: dict[str, list[str]]   # Class ID → member symbols

    # Signature search (type-based)
    param_type_to_functions: dict[str, list[str]]   # "User" → functions taking User
    return_type_to_functions: dict[str, list[str]]  # "List[User]" → functions

    # Vector search (optional)
    symbol_to_embedding: dict[str, list[float]]

@dataclass
class SearchIndex:
    """Search-optimized index for retrieval"""
    repo_id: str
    snapshot_id: str

    symbols: dict[str, SearchableSymbol]    # Enriched symbols
    relations: list[SearchableRelation]     # Enriched relations
    indexes: QueryIndexes                   # Pre-built query indexes
```

**특징**:
- ✅ SearchableSymbol: 검색 최적화 (name, fqn, signature, fuzzy)
- ✅ QueryIndexes: 미리 만든 인덱스 (O(1) 검색)
- ✅ 랭킹 시그널 (call_count, is_public, complexity)
- ✅ 벡터 임베딩 (의미 검색)
- ⚠️ 심볼당 ~1-2KB (무거움, but 검색 전용이라 OK)
- ✅ 이름이 직관적 (Searchable = 검색 가능, Query = 쿼리용)

**스토리지**:
```
Zoekt (Lexical 검색용) ⭐ Primary Search
├─ Index: Code content + symbols
├─ Features:
│  ├─ Fuzzy search (typo tolerance)
│  ├─ Regex search
│  ├─ Case-insensitive search
│  └─ Trigram matching
├─ Performance: <10ms for most queries
└─ Indexed data:
   ├─ File content (전체 코드)
   ├─ Symbol names (function, class, variable)
   └─ FQNs

PostgreSQL (Symbol metadata용)
├─ searchable_symbols (테이블)
│  ├─ id, repo_id, snapshot_id
│  ├─ search_name, fqn_parts (text[])
│  ├─ call_count, reference_count, is_public, is_test, complexity
│  ├─ docstring
│  ├─ param_types (text[]), return_type
│  └─ INDEXES:
│      ├─ idx_fqn_prefix (GIN for prefix search)
│      └─ idx_call_count (for ranking)
│
├─ searchable_relations (테이블)
│  ├─ source_id, target_id, kind
│  ├─ frequency, is_critical
│  └─ INDEX: idx_source_target
│
└─ query_indexes (여러 테이블)
   ├─ file_to_symbols: (file_path, symbol_ids)
   ├─ class_to_members: (class_id, member_ids)
   ├─ param_type_to_functions: (type, function_ids)
   └─ return_type_to_functions: (type, function_ids)

Qdrant (벡터 검색용)
└─ Collection: code_symbols
   ├─ vector: doc_embedding (768 dim)
   ├─ payload: {symbol_id, repo_id, name, fqn, kind}
   └─ INDEX: HNSW for similarity search
```

---

## 🔄 파이프라인

### Phase 1: Symbol Graph Construction
```
IR → SymbolGraphBuilder → SymbolGraph (light, 200 bytes/symbol)
     ├─ Symbol (id, fqn, name, span)
     ├─ Relation (CALLS, IMPORTS, CONTAINS)
     └─ RelationIndex (caller_to_callees, ...)
          ↓
     [Storage]
     ├─ Kuzu: Symbol nodes + Relation edges (그래프 쿼리)
     └─ PostgreSQL: symbols + relations 테이블 (영구 저장)
```

### Phase 2: Search Index Construction
```
SymbolGraph + IR → SearchIndexBuilder → SearchIndex (heavy, 1-2KB/symbol)
                   ├─ SearchableSymbol (name, call_count, embeddings)
                   ├─ SearchableRelation (frequency, is_critical)
                   └─ QueryIndexes (name, fqn, signature, fuzzy)
                        ↓
                   [Storage]
                   ├─ PostgreSQL: searchable_symbols + query_indexes (검색 인덱스)
                   └─ Qdrant: doc_embeddings (벡터 검색)
```

### Phase 3: Usage
```
Chunk/RepoMap → SymbolGraph (가벼운 그래프, 빠른 탐색)
                ↓
                Read from: Kuzu (O(1) graph traversal)

Retriever     → SearchIndex (무거운 인덱스, 최적화된 검색)
                ↓
                Read from:
                ├─ PostgreSQL (name, fqn, signature search)
                └─ Qdrant (semantic vector search)
```

---

## 📈 메모리 비교

### 대형 프로젝트 (100,000 lines, 50,000 nodes)

**Before (통합)**:
```
GraphDocument:
  Nodes: 50,000 × 500 bytes = 25MB
  Edges: 100,000 × 100 bytes = 10MB
  Indexes: 20-30MB
  ------------------------
  Total: 55-65MB
```

**After (분리)**:
```
SymbolGraph (light):
  Symbols: 50,000 × 200 bytes = 10MB ✅
  Relations: 100,000 × 100 bytes = 10MB
  RelationIndex: 5MB
  ------------------------
  Total: 25MB ✅ (60% 감소)

SearchIndex (heavy):
  SearchableSymbols: 50,000 × 1.5KB = 75MB
  QueryIndexes: 50MB
  ------------------------
  Total: 125MB (검색 전용이라 OK)
```

**장점**:
- SymbolGraph는 가벼워져서 Chunk/RepoMap이 빠름
- SearchIndex는 무거워도 됨 (검색 전용, 필요시만 로드)

---

## 💾 스토리지 전략

### SymbolGraph 스토리지 (Port-Adapter 패턴)
```
1. In-Memory Graph (Primary) ⭐
   - Usage: 모든 그래프 쿼리 (탐색, call chain, k-hop)
   - Structure:
     class SymbolGraph:
       symbols: dict[str, Symbol]      # O(1) lookup
       relations: list[Relation]        # Edge list
       indexes: RelationIndex           # Reverse indexes

   - Performance: <10ms for all operations
   - No persistence (ephemeral)

2. SymbolGraphPort (Interface)
   ```python
   class SymbolGraphPort(Protocol):
       def save(self, graph: SymbolGraph) -> None:
           """Save graph to persistent storage"""

       def load(self, repo_id: str, snapshot_id: str) -> SymbolGraph:
           """Load graph from persistent storage"""

       def delete(self, repo_id: str, snapshot_id: str) -> None:
           """Delete graph from storage"""
   ```

3. PostgreSQLSymbolGraphAdapter (Implementation)
   - Usage: 영구 저장, 스냅샷 히스토리
   - Schema:
     CREATE TABLE symbols (
       id TEXT PRIMARY KEY,
       repo_id TEXT, snapshot_id TEXT,
       kind TEXT, fqn TEXT, name TEXT,
       span_json JSONB,
       parent_id TEXT, signature_id TEXT, type_id TEXT,
       created_at TIMESTAMP
     );
     CREATE TABLE relations (
       id TEXT PRIMARY KEY,
       repo_id TEXT, snapshot_id TEXT,
       kind TEXT,
       source_id TEXT, target_id TEXT,
       span_json JSONB
     );
     CREATE INDEX idx_symbols_repo_snapshot ON symbols(repo_id, snapshot_id);
     CREATE INDEX idx_relations_repo_snapshot ON relations(repo_id, snapshot_id);

   - Performance: 100ms+ (bulk insert/load)
```

### SearchIndex 스토리지
```
1. PostgreSQL (Primary)
   - Usage: 모든 검색 쿼리 (name, fqn, signature)
   - Schema:
     CREATE TABLE searchable_symbols (
       id TEXT PRIMARY KEY,
       repo_id TEXT, snapshot_id TEXT,
       search_name TEXT,  -- lowercase normalized
       fqn_parts TEXT[],  -- for prefix matching
       call_count INT, reference_count INT,
       is_public BOOLEAN, is_test BOOLEAN,
       complexity INT,
       docstring TEXT,
       param_types TEXT[], return_type TEXT
     );

     -- Trigram index for fuzzy search
     CREATE INDEX idx_search_name_trgm ON searchable_symbols
       USING gin(search_name gin_trgm_ops);

     -- Prefix index for autocomplete
     CREATE INDEX idx_fqn_prefix ON searchable_symbols
       USING gin(fqn_parts);

     -- Ranking index
     CREATE INDEX idx_call_count ON searchable_symbols(call_count DESC);

2. Qdrant (Vector Search)
   - Usage: 의미 기반 검색 (semantic similarity)
   - Collection:
     {
       "vectors": {
         "size": 768,
         "distance": "Cosine"
       },
       "payload": {
         "symbol_id": "text",
         "repo_id": "text",
         "name": "text",
         "fqn": "text",
         "kind": "text"
       }
     }
   - Performance: <50ms for top-k similarity search
```

### 스토리지 역할 요약

**SymbolGraph 스토리지:**
| Storage | 용도 | Data | Performance | Size |
|---------|------|------|-------------|------|
| **In-Memory** | Graph queries (Primary) | Symbol + Relation Graph | <10ms | 25MB |
| **PostgreSQL (Adapter)** | Persistence (via Port) | symbols + relations tables | 100ms+ | 50-100MB |

**SearchIndex 스토리지:**
| Storage | 용도 | Data | Performance | Size |
|---------|------|------|-------------|------|
| **Zoekt** | Lexical search | text + trigram index | <20ms | varies |
| **Qdrant** | Vector search | embeddings | <50ms | 100-200MB |

---

## ✅ 구현 계획

### Phase 1: SymbolGraph 경량화 + 스토리지 (2-3일)
1. **모델 리팩토링**
   - `GraphNode` → `Symbol` (attrs 제거, 핵심 필드만)
   - `GraphEdge` → `Relation`
   - `GraphIndex` → `RelationIndex`

2. **Port-Adapter 패턴**
   - Port: `SymbolGraphPort` 인터페이스 정의
   - Adapter: `PostgreSQLSymbolGraphAdapter` 구현

3. **PostgreSQL 스키마**
   - Migration: `001_create_symbol_tables.sql`
   - Tables: `symbols`, `relations`
   - Indexes: `idx_symbols_fqn`, `idx_relations_source_target`

4. **벤치마크**: 심볼당 200-250 bytes 목표

### Phase 2: SearchIndex 신규 생성 + 스토리지 (4-6일)
1. **모델 설계**
   - `SearchableSymbol` (search_name, call_count, embeddings)
   - `SearchableRelation` (frequency, is_critical)
   - `QueryIndexes` (name, fqn, signature, fuzzy)

2. **PostgreSQL 스키마**
   - Migration: `002_create_search_index_tables.sql`
   - Tables: `searchable_symbols`, `searchable_relations`, `query_indexes_*`
   - Indexes: GIN trigram, GIN prefix, ranking

3. **Qdrant 스키마**
   - Collection: `code_symbols`
   - Vector: 768-dim embeddings
   - Payload: symbol metadata

4. **SearchIndexBuilder 구현**
   - SymbolGraph → SearchableSymbol (call_count 계산)
   - PostgreSQL 벌크 insert
   - Qdrant 벡터 업로드

### Phase 3: 통합 + 마이그레이션 (3-4일)
1. **Chunk/RepoMap 마이그레이션**
   - GraphDocument → SymbolGraph
   - Kuzu에서 Symbol/Relation 읽기

2. **Retriever 마이그레이션**
   - GraphDocument → SearchIndex
   - PostgreSQL 검색 쿼리 구현
   - Qdrant 벡터 검색 통합

3. **E2E 테스트**
   - 파이프라인 전체 실행
   - 성능 벤치마크
   - 스토리지 크기 측정

---

## 🎯 예상 효과

### 성능
- **SymbolGraph**: 60% 메모리 감소 (25MB vs 65MB @ 50K symbols)
- **Chunk/RepoMap**: 빠른 그래프 탐색 (가벼운 구조)
- **Retriever**: 최적화된 검색 (전용 인덱스)

### 아키텍처
- ✅ 관심사 명확히 분리 (의미 관계 vs 검색)
- ✅ Single Responsibility Principle
- ✅ 확장 가능 (SearchIndex에 새 쿼리 인덱스 추가 쉬움)

### 유지보수
- ✅ SymbolGraph는 안정적 (의미 관계만 표현)
- ✅ SearchIndex는 실험 가능 (검색 알고리즘 변경 쉬움)

### 네이밍
- ✅ **직관적**: Symbol (코드 심볼), Relation (관계), Searchable (검색 가능)
- ✅ **명확한 역할**: SymbolGraph (관계 표현), SearchIndex (검색 최적화)
- ✅ **일관성**: Symbol/Relation/Index 접미어 통일

### 스토리지
- ✅ **계층적 전략**: In-Memory (hot) → Kuzu (warm) → PostgreSQL (cold)
- ✅ **역할 분리**: Kuzu (그래프 쿼리), PostgreSQL (검색 + 영구 저장), Qdrant (벡터)
- ✅ **성능**: Hot path <10ms, Search 10-50ms, Graph 50-200ms

---

## 🤔 대안: Lazy Search Index (선택)

SearchIndex 전체를 만들지 않고, 필요한 쿼리 인덱스만 선택적으로 생성:

```python
class LazySearchIndex:
    def __init__(self, symbol_graph: SymbolGraph):
        self.graph = symbol_graph
        self._name_index = None
        self._signature_index = None

    @property
    def name_to_symbols(self):
        """Name 검색이 필요할 때만 빌드"""
        if self._name_index is None:
            self._name_index = self._build_name_index()
        return self._name_index
```

**장점**: 필요한 인덱스만 메모리에 로드
**단점**: 첫 번째 검색이 느림 (빌드 시간)

---

## 🎉 결론

**추천**: **SymbolGraph vs SearchIndex 분리 구현**

**이유**:
1. ✅ **SymbolGraph** 가볍게 → Chunk/RepoMap 빠름
2. ✅ **SearchIndex** 무겁게 → Retriever 검색 최적화
3. ✅ 관심사 명확히 분리 (의미 관계 vs 검색)
4. ✅ **직관적 네이밍** (Symbol, Relation, Searchable)
5. ✅ 확장 가능한 아키텍처

**다음 단계**: Phase 1 (SymbolGraph 경량화) 구현?
