# IR SOTA 최종 계획: Retrieval-Optimized, SCIP-Level IR

**작성일**: 2025-12-04  
**상태**: ✅ Final Plan for Implementation  
**목표**: SCIP 수준의 IR, Retrieval 엔진 최적화

---

## 🎯 목표 및 범위

### 핵심 목표
```
SCIP 수준의 IR을 구축하되,
Retrieval 시스템에 최적화된 형태로

- SCIP .scip 파일: 필요 없음 (외부 도구 연동 불필요)
- 용도: 코드레벨 retriever 시스템의 핵심 엔진
- 품질: SOTA급 (State-of-the-Art)
```

### SCIP의 핵심 기능 (우리가 구현할 것)
```
1. ✅ Symbol Occurrence Tracking
   - 모든 symbol 사용처 추적
   - Role 구분 (definition, reference, import, write/read)
   
2. ✅ Cross-file Relationships
   - Import resolution
   - Cross-module references
   - Dependency tracking

3. ✅ Type Information (selective)
   - Public APIs
   - Key symbols
   - LSP-enhanced (multi-language)

4. ✅ Fast Retrieval Indexes
   - by_symbol: O(1) lookup
   - by_file: O(1) file symbols
   - by_type: Type-based queries
   - by_role: Definition/reference filtering
```

### SCIP를 넘어서는 부분 (Retrieval 최적화)
```
⭐ Ranking Signals
   - Symbol importance scores
   - Usage frequency
   - Context relevance

⭐ Hierarchical Structure
   - 6-level chunk hierarchy
   - Parent-child relationships
   - Scope awareness

⭐ Performance Optimization
   - Incremental updates
   - Smart caching
   - Background processing
```

---

## 📊 현재 상태 분석

### ✅ 이미 잘 구현된 부분 (유지)

#### 1. Structural IR (AST-based)
```python
# src/contexts/code_foundation/infrastructure/ir/
✅ Node/Edge 기반 그래프 구조
✅ 16+ EdgeKind (CALLS, READS, WRITES, IMPORTS, etc.)
✅ Multi-language 지원 (Python, TypeScript, Go, Rust, Java, C++)
✅ Incremental parsing (Tree-sitter)
✅ Content hashing

평가: SOTA급, 그대로 유지
```

#### 2. Chunking System
```python
# src/contexts/code_foundation/infrastructure/chunk/builder.py
✅ 6-level hierarchy (Repo → Project → Module → File → Class → Function)
✅ 10+ chunk types (docstring, skeleton, usage, etc.)
✅ Parent-child relationships
✅ Incremental refresh

평가: SOTA급, 그대로 유지
```

#### 3. Graph Document
```python
# src/contexts/code_foundation/infrastructure/graph/
✅ Semantic relationships
✅ Dependency graph
✅ Call graph (basic)
✅ Inheritance/implements

평가: 좋음, 그대로 유지
```

### 🟡 개선 필요한 부분

#### 1. Occurrence Tracking (SCIP 핵심!)
```python
현재 상태:
- Edge로 relationship 표현 ✅
- 하지만 SCIP의 SymbolRole 없음 ❌
- Occurrence index 없음 ❌

개선 필요:
→ Phase 1에서 구현
```

#### 2. Type Information
```python
현재 상태:
- TypeEntity, SignatureEntity 있음 ✅
- 하지만 AST-based만 (LSP 통합 없음) ❌
- Type resolution이 제한적 ❌

개선 필요:
→ Phase 2에서 LSP 통합 (선택적)
```

#### 3. Cross-file Resolution
```python
현재 상태:
- Import edges 있음 ✅
- 하지만 target resolution이 약함 ❌
- Cross-module references 불완전 ❌

개선 필요:
→ Phase 3에서 강화
```

### ❌ 우선순위 낮추거나 제외할 부분

#### CFG/DFG (Control/Data Flow Graph)
```
현재:
✅ 이미 구현되어 있음
❌ 하지만 Retrieval에서 사용 안 됨
❌ Agent에서도 사용 안 됨

결론:
→ 현재 구현 유지 (코드 삭제 안 함)
→ 하지만 SOTA 계획에서 우선순위 낮춤
→ Phase 1-3에서 개선 안 함
→ 실제 사용 사례 발견 시 Phase 4+에서 재고려
```

---

## 🏗️ SOTA IR 아키텍처

### 4-Layer Architecture (Retrieval 최적화)

```
┌────────────────────────────────────────────────────────────┐
│         Layer 4: Retrieval Indexes (Fast Lookup)           │
│                                                             │
│  SymbolIndex:                                              │
│  • by_symbol: symbol_id → List[Occurrence]                 │
│  • by_file: file_path → List[Symbol]                       │
│  • by_type: type_name → List[Symbol]                       │
│  • by_role: role → List[Occurrence]                        │
│  • by_importance: score → List[Symbol]                     │
│                                                             │
│  ChunkIndex:                                               │
│  • by_id: O(1) chunk lookup                                │
│  • by_file: O(1) file chunks                               │
│  • by_symbol: symbol → containing chunks                   │
│  • by_parent: hierarchical queries                         │
│                                                             │
│  TypeIndex:                                                │
│  • by_name: type_name → TypeEntity                         │
│  • by_kind: TypeKind → List[Type]                          │
│  • hierarchy: inheritance/implements                       │
└──────────────────┬─────────────────────────────────────────┘
                   │
┌──────────────────┴─────────────────────────────────────────┐
│      Layer 3: Cross-file IR (Project-wide Context)        │
│                                                             │
│  CrossFileRefs:                                            │
│  • Import resolution (module → file)                       │
│  • Symbol resolution (name → definition)                   │
│  • Dependency graph (file → dependencies)                  │
│  • Export tracking (public APIs)                           │
│                                                             │
│  GlobalSymbolTable:                                        │
│  • FQN → Symbol mapping                                    │
│  • Namespace management                                    │
│  • Conflict detection                                      │
└──────────────────┬─────────────────────────────────────────┘
                   │
┌──────────────────┴─────────────────────────────────────────┐
│        Layer 2: Semantic IR (Type + Occurrence)            │
│                                                             │
│  Occurrence Layer (SCIP-compatible): ⭐ NEW                │
│  • Every symbol usage tracked                              │
│  • Roles: Definition, Reference, Import, Write, Read       │
│  • Enclosing range (for context)                           │
│  • Fast lookup: O(1) find all references                   │
│                                                             │
│  Type Layer (LSP-enhanced): ⭐ ENHANCED                    │
│  • TypeEntity (inferred types)                             │
│  • SignatureEntity (function signatures)                   │
│  • Hover content (public APIs) - from LSP                  │
│  • Diagnostics (errors/warnings) - from LSP                │
│                                                             │
│  Ranking Layer: ⭐ NEW                                     │
│  • Symbol importance scores                                │
│  • Usage frequency                                         │
│  • Export status (public/private)                          │
└──────────────────┬─────────────────────────────────────────┘
                   │
┌──────────────────┴─────────────────────────────────────────┐
│         Layer 1: Structural IR (AST-based) ✅              │
│                                                             │
│  • Tree-sitter parsing (multi-language)                    │
│  • Node: Symbol definitions                                │
│  • Edge: Relationships (16+ kinds)                         │
│  • Span: Source locations                                  │
│  • Content hash: Change detection                          │
│  • Incremental parsing                                     │
└────────────────────────────────────────────────────────────┘
```

---

## 🚀 Phase별 구현 계획 (6주)

### Phase 1: Occurrence Layer (SCIP 핵심) - 2주 ⭐

**목표**: SCIP-level occurrence tracking with retrieval optimization

#### 1.1 Occurrence Models (Week 1, Day 1-2)

```python
# src/contexts/code_foundation/infrastructure/ir/models/occurrence.py

from enum import IntFlag
from dataclasses import dataclass

class SymbolRole(IntFlag):
    """SCIP-compatible symbol roles"""
    NONE = 0
    DEFINITION = 1      # Symbol is defined here
    IMPORT = 2          # Symbol is imported
    WRITE_ACCESS = 4    # Symbol is written to
    READ_ACCESS = 8     # Symbol is read from
    GENERATED = 16      # Generated code
    TEST = 32           # Test code
    FORWARD_DEFINITION = 64  # Forward declaration

@dataclass(slots=True)
class Occurrence:
    """
    Single occurrence of a symbol.
    
    SCIP-compatible but optimized for retrieval.
    """
    id: str
    symbol_id: str  # Reference to Node.id
    span: Span
    roles: SymbolRole  # Bitflags (can be combined)
    
    # Retrieval optimization
    file_path: str
    enclosing_range: Span | None = None  # Context for snippet
    parent_symbol_id: str | None = None  # Scope context
    
    # Ranking signals
    importance_score: float = 0.0  # 0-1, higher = more important
    
    def is_definition(self) -> bool:
        return bool(self.roles & SymbolRole.DEFINITION)
    
    def is_reference(self) -> bool:
        return bool(self.roles & SymbolRole.READ_ACCESS)
    
    def is_write(self) -> bool:
        return bool(self.roles & SymbolRole.WRITE_ACCESS)

@dataclass
class OccurrenceIndex:
    """
    Fast lookup indexes for occurrences.
    
    Optimized for retrieval queries:
    - "Find all references to symbol X"
    - "Find all definitions in file Y"
    - "Find all write accesses to variable Z"
    """
    by_symbol: dict[str, list[str]] = field(default_factory=dict)
    by_file: dict[str, list[str]] = field(default_factory=dict)
    by_role: dict[SymbolRole, list[str]] = field(default_factory=dict)
    by_id: dict[str, Occurrence] = field(default_factory=dict)
    
    def add(self, occurrence: Occurrence):
        # Add to all indexes
        self.by_symbol.setdefault(occurrence.symbol_id, []).append(occurrence.id)
        self.by_file.setdefault(occurrence.file_path, []).append(occurrence.id)
        self.by_id[occurrence.id] = occurrence
        
        # Add to role-specific indexes (handle bitflags)
        for role in SymbolRole:
            if role != SymbolRole.NONE and occurrence.roles & role:
                self.by_role.setdefault(role, []).append(occurrence.id)
    
    def get_references(self, symbol_id: str) -> list[Occurrence]:
        """O(1) lookup: find all references to symbol"""
        occ_ids = self.by_symbol.get(symbol_id, [])
        return [self.by_id[oid] for oid in occ_ids if oid in self.by_id]
    
    def get_definitions(self, symbol_id: str) -> list[Occurrence]:
        """Find all definitions (usually 1, but can be multiple for overloads)"""
        occs = self.get_references(symbol_id)
        return [o for o in occs if o.is_definition()]
    
    def get_file_occurrences(self, file_path: str) -> list[Occurrence]:
        """O(1) lookup: all occurrences in file"""
        occ_ids = self.by_file.get(file_path, [])
        return [self.by_id[oid] for oid in occ_ids if oid in self.by_id]
```

#### 1.2 Occurrence Generator (Week 1, Day 3-5)

```python
# src/contexts/code_foundation/infrastructure/ir/occurrence_generator.py

class OccurrenceGenerator:
    """
    Generate occurrences from IRDocument.
    
    Maps IR Edges → SCIP Occurrences with roles.
    """
    
    def generate(self, ir_doc: IRDocument) -> tuple[list[Occurrence], OccurrenceIndex]:
        """
        Generate all occurrences from IR.
        
        Strategy:
        1. Scan all nodes → create DEFINITION occurrences
        2. Scan all edges → create REFERENCE/WRITE occurrences
        3. Calculate importance scores
        4. Build indexes
        """
        occurrences = []
        
        # 1. Definitions from nodes
        for node in ir_doc.nodes:
            if self._is_symbol_node(node):
                occ = self._create_definition_occurrence(node)
                occurrences.append(occ)
        
        # 2. References from edges
        for edge in ir_doc.edges:
            occ = self._create_reference_occurrence(edge, ir_doc)
            if occ:
                occurrences.append(occ)
        
        # 3. Calculate importance scores
        self._calculate_importance(occurrences, ir_doc)
        
        # 4. Build indexes
        index = OccurrenceIndex()
        for occ in occurrences:
            index.add(occ)
        
        return occurrences, index
    
    def _create_definition_occurrence(self, node: Node) -> Occurrence:
        """Map Node → Definition occurrence"""
        roles = SymbolRole.DEFINITION
        
        # Add additional roles based on context
        if node.attrs.get("is_test"):
            roles |= SymbolRole.TEST
        
        return Occurrence(
            id=f"occ:def:{node.id}",
            symbol_id=node.id,
            span=node.span,
            roles=roles,
            file_path=node.file_path,
            enclosing_range=node.body_span,
            importance_score=self._estimate_importance(node),
        )
    
    def _create_reference_occurrence(self, edge: Edge, ir_doc: IRDocument) -> Occurrence | None:
        """Map Edge → Reference occurrence"""
        # Determine role from edge kind
        roles = self._edge_kind_to_role(edge.kind)
        if roles == SymbolRole.NONE:
            return None
        
        # Get source node for context
        source_node = ir_doc.get_node(edge.source_id)
        if not source_node:
            return None
        
        return Occurrence(
            id=f"occ:ref:{edge.id}",
            symbol_id=edge.target_id,  # Reference TO target
            span=edge.span or source_node.span,
            roles=roles,
            file_path=source_node.file_path,
            parent_symbol_id=edge.source_id,
            importance_score=0.5,  # References have lower base importance
        )
    
    def _edge_kind_to_role(self, kind: EdgeKind) -> SymbolRole:
        """Map EdgeKind → SymbolRole"""
        role_map = {
            EdgeKind.CALLS: SymbolRole.READ_ACCESS,
            EdgeKind.READS: SymbolRole.READ_ACCESS,
            EdgeKind.WRITES: SymbolRole.WRITE_ACCESS,
            EdgeKind.REFERENCES: SymbolRole.READ_ACCESS,
            EdgeKind.IMPORTS: SymbolRole.IMPORT,
            EdgeKind.INHERITS: SymbolRole.READ_ACCESS,
            EdgeKind.IMPLEMENTS: SymbolRole.READ_ACCESS,
            EdgeKind.INSTANTIATES: SymbolRole.READ_ACCESS,
        }
        return role_map.get(kind, SymbolRole.NONE)
    
    def _calculate_importance(self, occurrences: list[Occurrence], ir_doc: IRDocument):
        """
        Calculate importance scores for ranking.
        
        Factors:
        - Is public API? (exported, not starting with _)
        - Reference count (popular symbols)
        - Depth in hierarchy (top-level > nested)
        - Documentation presence
        """
        # Count references per symbol
        ref_counts = {}
        for occ in occurrences:
            if occ.is_reference():
                ref_counts[occ.symbol_id] = ref_counts.get(occ.symbol_id, 0) + 1
        
        # Update importance scores
        for occ in occurrences:
            node = ir_doc.get_node(occ.symbol_id)
            if not node:
                continue
            
            score = 0.5  # Base score
            
            # Public API bonus (+0.3)
            if self._is_public_api(node):
                score += 0.3
            
            # Reference count bonus (up to +0.2)
            ref_count = ref_counts.get(node.id, 0)
            score += min(ref_count / 100.0, 0.2)
            
            # Documentation bonus (+0.1)
            if node.docstring:
                score += 0.1
            
            # Top-level bonus (+0.1)
            if not node.parent_id:
                score += 0.1
            
            occ.importance_score = min(score, 1.0)
```

#### 1.3 Integration with IRDocument (Week 2, Day 1-2)

```python
# src/contexts/code_foundation/infrastructure/ir/models/document.py (수정)

@dataclass
class IRDocument:
    """IR Document with SCIP-level occurrence tracking"""
    
    repo_id: str
    snapshot_id: str
    schema_version: str = "2.0"  # ⭐ 버전 업
    
    # Structural layer
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    
    # Semantic layer (existing)
    types: list[TypeEntity] = field(default_factory=list)
    signatures: list[SignatureEntity] = field(default_factory=list)
    
    # ⭐ NEW: Occurrence layer (SCIP-compatible)
    occurrences: list[Occurrence] = field(default_factory=list)
    
    # Indexes (lazy-built)
    _occurrence_index: OccurrenceIndex | None = None
    _node_index: dict[str, Node] | None = None
    _edge_index: dict[str, list[Edge]] | None = None
    
    def build_indexes(self):
        """Build all indexes for fast lookup"""
        # Node index
        self._node_index = {n.id: n for n in self.nodes}
        
        # Edge index (by source)
        self._edge_index = {}
        for edge in self.edges:
            self._edge_index.setdefault(edge.source_id, []).append(edge)
        
        # Occurrence index
        self._occurrence_index = OccurrenceIndex()
        for occ in self.occurrences:
            self._occurrence_index.add(occ)
    
    # ⭐ Retrieval-optimized queries
    def find_references(self, symbol_id: str) -> list[Occurrence]:
        """O(1): Find all references to symbol"""
        if not self._occurrence_index:
            self.build_indexes()
        return self._occurrence_index.get_references(symbol_id)
    
    def find_definitions(self, symbol_name: str) -> list[Node]:
        """Find all definitions by name"""
        if not self._node_index:
            self.build_indexes()
        return [n for n in self.nodes if n.name == symbol_name]
    
    def get_symbol_occurrences(self, symbol_id: str, role: SymbolRole | None = None) -> list[Occurrence]:
        """Get occurrences with optional role filter"""
        occs = self.find_references(symbol_id)
        if role:
            occs = [o for o in occs if o.roles & role]
        return sorted(occs, key=lambda o: o.importance_score, reverse=True)
```

#### 1.4 Tests & Validation (Week 2, Day 3-5)

```python
# tests/foundation/test_occurrence.py
# tests/foundation/test_occurrence_generator.py
# tests/foundation/test_retrieval_queries.py

def test_occurrence_generation():
    """Test basic occurrence generation"""
    ...

def test_find_references():
    """Test O(1) reference lookup"""
    ...

def test_importance_scoring():
    """Test ranking signals"""
    ...

def test_role_filtering():
    """Test definition/reference filtering"""
    ...
```

---

### Phase 2: LSP Integration (Multi-Language) - 2주

**목표**: Multi-language type information (selective, Public APIs)

#### 2.1 Multi-LSP Adapter (Week 3, Day 1-3)

```python
# src/contexts/code_foundation/infrastructure/ir/lsp/adapter.py

class LSPAdapter(Protocol):
    """Unified LSP interface for all languages"""
    
    async def hover(self, file_path: Path, line: int, col: int) -> TypeInfo | None:
        """Get type and docs at position"""
        ...
    
    async def definition(self, file_path: Path, line: int, col: int) -> Location | None:
        """Get definition location"""
        ...
    
    async def diagnostics(self, file_path: Path) -> list[Diagnostic]:
        """Get file diagnostics"""
        ...

class MultiLSPManager:
    """Manage multiple LSP clients"""
    
    def __init__(self):
        self.adapters: dict[str, LSPAdapter] = {}
        self._init_adapters()
    
    def _init_adapters(self):
        """Initialize language-specific adapters"""
        # Python
        self.adapters["python"] = PyrightAdapter()
        
        # TypeScript/JavaScript
        self.adapters["typescript"] = TypeScriptAdapter()
        self.adapters["javascript"] = TypeScriptAdapter()
        
        # Go
        self.adapters["go"] = GoplsAdapter()
        
        # Rust
        self.adapters["rust"] = RustAnalyzerAdapter()
    
    async def get_type_info(
        self,
        language: str,
        file_path: Path,
        line: int,
        col: int,
    ) -> TypeInfo | None:
        """Get type info for any language"""
        adapter = self.adapters.get(language)
        if not adapter:
            return None
        
        return await adapter.hover(file_path, line, col)
```

#### 2.2 Selective Type Enrichment (Week 3, Day 4-5)

```python
# src/contexts/code_foundation/infrastructure/ir/type_enricher.py

class SelectiveTypeEnricher:
    """
    Enrich IR with LSP type information (selective).
    
    Strategy: Public APIs only (80/20 rule)
    """
    
    def __init__(self, lsp_manager: MultiLSPManager):
        self.lsp = lsp_manager
    
    async def enrich(self, ir_doc: IRDocument, language: str) -> IRDocument:
        """
        Enrich IR with type information.
        
        Only targets:
        1. Public APIs (exported, not starting with _)
        2. Class definitions
        3. Function definitions (top-level or methods)
        
        Skips:
        - Private symbols
        - Local variables
        - Temporary expressions
        """
        
        # Filter public symbols
        public_nodes = [
            n for n in ir_doc.nodes
            if self._is_public_api(n)
        ]
        
        logger.info(
            f"Enriching {len(public_nodes)} public symbols "
            f"(out of {len(ir_doc.nodes)} total)"
        )
        
        # Batch queries with concurrency limit
        semaphore = asyncio.Semaphore(20)  # Max 20 concurrent
        
        async def enrich_node(node: Node):
            async with semaphore:
                return await self._enrich_single_node(node, language)
        
        tasks = [enrich_node(n) for n in public_nodes]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Update nodes with type info
        enriched_count = 0
        for node, result in zip(public_nodes, results):
            if isinstance(result, Exception):
                continue
            if result:
                node.attrs["lsp_type"] = result.type_string
                node.attrs["lsp_docs"] = result.documentation
                enriched_count += 1
        
        logger.info(f"Successfully enriched {enriched_count} symbols")
        
        return ir_doc
    
    async def _enrich_single_node(self, node: Node, language: str) -> TypeInfo | None:
        """Enrich single node with LSP"""
        try:
            return await self.lsp.get_type_info(
                language,
                Path(node.file_path),
                node.span.start_line,
                node.span.start_col,
            )
        except Exception as e:
            logger.debug(f"LSP query failed for {node.id}: {e}")
            return None
    
    def _is_public_api(self, node: Node) -> bool:
        """Check if node is public API"""
        if node.kind not in [NodeKind.CLASS, NodeKind.FUNCTION, NodeKind.METHOD]:
            return False
        
        if not node.name:
            return False
        
        # Private if starts with _
        if node.name.startswith("_") and not node.name.startswith("__"):
            return False
        
        # Check export status
        if node.attrs.get("is_exported") is False:
            return False
        
        return True
```

#### 2.3 LSP Adapter Implementations (Week 4, Day 1-5)

```python
# src/contexts/code_foundation/infrastructure/ir/lsp/pyright.py (already exists, refactor)
# src/contexts/code_foundation/infrastructure/ir/lsp/typescript.py (new)
# src/contexts/code_foundation/infrastructure/ir/lsp/gopls.py (new)
# src/contexts/code_foundation/infrastructure/ir/lsp/rust_analyzer.py (new)

# 각 언어별 LSP 클라이언트 구현
# 통합 인터페이스 준수
```

---

### Phase 3: Cross-file Resolution & Indexing - 1주

**목표**: Project-wide context and fast retrieval indexes

#### 3.1 Cross-file Reference Resolver (Week 5, Day 1-3)

```python
# src/contexts/code_foundation/infrastructure/ir/cross_file_resolver.py

class CrossFileResolver:
    """
    Resolve cross-file references.
    
    Uses:
    1. Import edges → resolve to actual files
    2. LSP definition lookup → cross-file definitions
    3. Symbol table → FQN resolution
    """
    
    def resolve(self, ir_docs: dict[str, IRDocument]) -> GlobalContext:
        """
        Resolve all cross-file references.
        
        Args:
            ir_docs: file_path → IRDocument mapping
        
        Returns:
            GlobalContext with:
            - Global symbol table (FQN → Node)
            - Import resolution (import → file)
            - Dependency graph (file → dependencies)
        """
        
        global_ctx = GlobalContext()
        
        # 1. Build global symbol table
        for file_path, ir_doc in ir_docs.items():
            for node in ir_doc.nodes:
                if node.fqn:
                    global_ctx.register_symbol(node.fqn, node, file_path)
        
        # 2. Resolve imports
        for file_path, ir_doc in ir_docs.items():
            import_edges = [e for e in ir_doc.edges if e.kind == EdgeKind.IMPORTS]
            
            for edge in import_edges:
                target_fqn = edge.attrs.get("imported_name")
                if not target_fqn:
                    continue
                
                # Resolve FQN → actual file
                resolved = global_ctx.resolve_symbol(target_fqn)
                if resolved:
                    edge.attrs["resolved_file"] = resolved.file_path
                    edge.attrs["resolved_node_id"] = resolved.node_id
                    
                    # Add dependency
                    global_ctx.add_dependency(file_path, resolved.file_path)
        
        # 3. Build dependency graph
        global_ctx.build_dependency_graph()
        
        return global_ctx

@dataclass
class GlobalContext:
    """Project-wide context"""
    
    # FQN → (Node, file_path)
    symbol_table: dict[str, tuple[Node, str]] = field(default_factory=dict)
    
    # file → dependencies
    dependencies: dict[str, set[str]] = field(default_factory=dict)
    
    # Dependency graph (topological order)
    dep_order: list[str] = field(default_factory=list)
    
    def register_symbol(self, fqn: str, node: Node, file_path: str):
        """Register symbol in global table"""
        self.symbol_table[fqn] = (node, file_path)
    
    def resolve_symbol(self, fqn: str) -> ResolvedSymbol | None:
        """Resolve FQN → Node"""
        if fqn not in self.symbol_table:
            return None
        node, file_path = self.symbol_table[fqn]
        return ResolvedSymbol(
            fqn=fqn,
            node_id=node.id,
            file_path=file_path,
        )
    
    def add_dependency(self, from_file: str, to_file: str):
        """Add file dependency"""
        self.dependencies.setdefault(from_file, set()).add(to_file)
    
    def build_dependency_graph(self):
        """Build topological order (for retrieval ranking)"""
        # Topological sort
        from collections import deque
        
        in_degree = {f: 0 for f in self.dependencies}
        for deps in self.dependencies.values():
            for dep in deps:
                in_degree[dep] = in_degree.get(dep, 0) + 1
        
        queue = deque([f for f in in_degree if in_degree[f] == 0])
        order = []
        
        while queue:
            file = queue.popleft()
            order.append(file)
            
            for dep in self.dependencies.get(file, []):
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)
        
        self.dep_order = order
```

#### 3.2 Enhanced Retrieval Indexes (Week 5, Day 4-5)

```python
# src/contexts/code_foundation/infrastructure/ir/retrieval_index.py

class RetrievalOptimizedIndex:
    """
    Fast indexes for retrieval queries.
    
    Optimized for:
    - Symbol lookup by name (fuzzy)
    - File-level queries
    - Type-based queries
    - Importance-ranked results
    """
    
    def __init__(self):
        # Symbol indexes
        self.by_symbol_name: dict[str, list[Node]] = {}
        self.by_fqn: dict[str, Node] = {}
        self.by_type: dict[str, list[Node]] = {}
        
        # Occurrence indexes
        self.occurrence_index: OccurrenceIndex = OccurrenceIndex()
        
        # File indexes
        self.by_file: dict[str, FileIndex] = {}
        
        # Fuzzy search
        self.fuzzy_matcher: FuzzyMatcher = FuzzyMatcher()
    
    def index_ir_document(self, ir_doc: IRDocument):
        """Index entire IR document"""
        
        # Index nodes
        for node in ir_doc.nodes:
            if node.name:
                self.by_symbol_name.setdefault(node.name, []).append(node)
            
            if node.fqn:
                self.by_fqn[node.fqn] = node
            
            if type_name := node.attrs.get("lsp_type"):
                self.by_type.setdefault(type_name, []).append(node)
            
            # Fuzzy index
            self.fuzzy_matcher.add(node.name or "", node.id)
        
        # Index occurrences
        for occ in ir_doc.occurrences:
            self.occurrence_index.add(occ)
        
        # Index file
        file_index = FileIndex.from_ir_doc(ir_doc)
        self.by_file[ir_doc.file_path] = file_index
    
    def search_symbol(
        self,
        query: str,
        fuzzy: bool = True,
        limit: int = 20,
    ) -> list[tuple[Node, float]]:
        """
        Search symbols with ranking.
        
        Returns:
            List of (Node, relevance_score) sorted by relevance
        """
        
        if fuzzy:
            # Fuzzy matching
            matches = self.fuzzy_matcher.search(query, limit=limit * 2)
            node_ids = [m.id for m in matches]
            nodes = [self.by_fqn.get(nid) for nid in node_ids if nid in self.by_fqn]
        else:
            # Exact matching
            nodes = self.by_symbol_name.get(query, [])
        
        # Calculate relevance scores
        scored = []
        for node in nodes:
            score = self._calculate_relevance(node, query)
            scored.append((node, score))
        
        # Sort by relevance
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return scored[:limit]
    
    def _calculate_relevance(self, node: Node, query: str) -> float:
        """
        Calculate relevance score.
        
        Factors:
        - Name match quality
        - Importance score (from occurrence)
        - Documentation presence
        - Public API status
        """
        score = 0.0
        
        # Name match (fuzzy distance)
        name_match = self._fuzzy_similarity(node.name or "", query)
        score += name_match * 0.4
        
        # Importance (from occurrence layer)
        importance = node.attrs.get("importance_score", 0.5)
        score += importance * 0.3
        
        # Documentation
        if node.docstring:
            score += 0.2
        
        # Public API
        if not (node.name or "").startswith("_"):
            score += 0.1
        
        return min(score, 1.0)
```

---

### Phase 4: Integration & Optimization - 1주

**목표**: End-to-end pipeline and performance optimization

#### 4.1 Unified IR Builder (Week 6, Day 1-3)

```python
# src/contexts/code_foundation/infrastructure/ir/sota_ir_builder.py

class SOTAIRBuilder:
    """
    SOTA IR Builder: Complete pipeline.
    
    Layers:
    1. Structural IR (Tree-sitter)
    2. Semantic IR (Type + Occurrence)
    3. Cross-file IR (Global context)
    4. Retrieval Indexes (Fast lookup)
    """
    
    def __init__(
        self,
        parser_registry: ParserRegistry,
        lsp_manager: MultiLSPManager,
    ):
        self.parser = parser_registry
        self.lsp = lsp_manager
        
        self.occurrence_gen = OccurrenceGenerator()
        self.type_enricher = SelectiveTypeEnricher(lsp_manager)
        self.cross_file_resolver = CrossFileResolver()
    
    async def build_full(
        self,
        repo_path: Path,
        files: list[Path],
    ) -> tuple[dict[str, IRDocument], GlobalContext, RetrievalOptimizedIndex]:
        """
        Build complete SOTA IR.
        
        Returns:
            (ir_documents, global_context, retrieval_index)
        """
        
        logger.info(f"Building SOTA IR for {len(files)} files")
        
        # ===============================================
        # Layer 1: Structural IR (parallel)
        # ===============================================
        structural_irs = await self._build_structural_ir_parallel(files)
        
        # ===============================================
        # Layer 2: Semantic IR (Occurrence + Type)
        # ===============================================
        
        # 2.1 Generate occurrences (fast, no I/O)
        for file_path, ir_doc in structural_irs.items():
            occurrences, occ_index = self.occurrence_gen.generate(ir_doc)
            ir_doc.occurrences = occurrences
            ir_doc._occurrence_index = occ_index
        
        # 2.2 Enrich with LSP types (selective, parallel)
        await self._enrich_types_parallel(structural_irs)
        
        # ===============================================
        # Layer 3: Cross-file Resolution
        # ===============================================
        global_ctx = self.cross_file_resolver.resolve(structural_irs)
        
        # ===============================================
        # Layer 4: Build Retrieval Indexes
        # ===============================================
        retrieval_index = RetrievalOptimizedIndex()
        for ir_doc in structural_irs.values():
            retrieval_index.index_ir_document(ir_doc)
        
        logger.info("SOTA IR build complete")
        
        return structural_irs, global_ctx, retrieval_index
    
    async def build_incremental(
        self,
        changed_files: list[Path],
        existing_irs: dict[str, IRDocument],
        global_ctx: GlobalContext,
        retrieval_index: RetrievalOptimizedIndex,
    ) -> tuple[dict[str, IRDocument], GlobalContext, RetrievalOptimizedIndex]:
        """
        Incremental update (fast path).
        
        Strategy:
        1. Rebuild structural IR for changed files only
        2. Regenerate occurrences
        3. Re-enrich types (public APIs only, background)
        4. Update global context (affected symbols only)
        5. Update indexes (incremental)
        """
        
        # ... incremental logic
        pass
```

#### 4.2 Performance Optimization (Week 6, Day 4-5)

```python
# Caching strategy
# Background processing
# Benchmark tests
# Memory optimization
```

---

## 📊 성능 목표

### Initial Indexing (Cold Start)

```
Small repo (< 100 files):
- Structural IR: < 2 seconds
- Occurrence generation: < 500ms
- LSP enrichment (public APIs): < 5 seconds
- Total: < 10 seconds ✅

Medium repo (100-1000 files):
- Structural IR: < 20 seconds
- Occurrence generation: < 5 seconds
- LSP enrichment: < 60 seconds
- Total: < 90 seconds ✅

Large repo (1000+ files):
- Structural IR: < 3 minutes
- Occurrence generation: < 30 seconds
- LSP enrichment: < 5 minutes
- Total: < 10 minutes ✅
```

### Incremental Update (Hot Path)

```
Single file change:
- Structural IR: < 100ms
- Occurrence regeneration: < 50ms
- Index update: < 50ms
- Total: < 200ms (real-time) ✅

LSP re-enrichment:
- Background (async)
- Non-blocking
- Completes within 5 seconds
```

### Retrieval Query

```
Symbol lookup:
- By name (exact): < 1ms
- By name (fuzzy): < 10ms
- Find references: < 5ms (O(1) index lookup)
- Cross-file navigation: < 10ms

All queries: < 50ms P99 ✅
```

---

## ✅ 최종 deliverables

### Code Artifacts

```
src/contexts/code_foundation/infrastructure/ir/
├── models/
│   ├── occurrence.py                 ⭐ NEW (Phase 1)
│   ├── document.py                   ⭐ UPDATED (v2.0)
│   └── ...
├── occurrence_generator.py           ⭐ NEW (Phase 1)
├── lsp/
│   ├── adapter.py                    ⭐ NEW (Phase 2)
│   ├── manager.py                    ⭐ NEW (Phase 2)
│   ├── typescript.py                 ⭐ NEW (Phase 2)
│   ├── gopls.py                      ⭐ NEW (Phase 2)
│   └── rust_analyzer.py              ⭐ NEW (Phase 2)
├── type_enricher.py                  ⭐ NEW (Phase 2)
├── cross_file_resolver.py            ⭐ NEW (Phase 3)
├── retrieval_index.py                ⭐ NEW (Phase 3)
└── sota_ir_builder.py                ⭐ NEW (Phase 4)

tests/foundation/
├── test_occurrence.py                ⭐ NEW
├── test_occurrence_generator.py      ⭐ NEW
├── test_lsp_integration.py           ⭐ NEW
├── test_cross_file_resolution.py     ⭐ NEW
└── test_retrieval_queries.py         ⭐ NEW
```

### Documentation

```
semantica_docs/
├── IR_V2_ARCHITECTURE.md             ⭐ NEW
├── OCCURRENCE_LAYER.md               ⭐ NEW
├── LSP_INTEGRATION.md                ⭐ NEW
└── RETRIEVAL_OPTIMIZATION.md         ⭐ NEW
```

---

## 🎯 성공 기준

### SCIP-Level Features ✅

```
1. ✅ Symbol Occurrence Tracking
   - Every symbol usage tracked
   - Role-based (definition, reference, import, write, read)
   - O(1) find-references

2. ✅ Cross-file Relationships
   - Import resolution
   - Cross-module references
   - Dependency graph

3. ✅ Type Information
   - Public APIs enriched with LSP
   - Multi-language support
   - Hover content & diagnostics

4. ✅ Fast Retrieval
   - Symbol lookup < 10ms
   - Find-references < 5ms
   - Fuzzy search < 10ms
```

### Beyond SCIP (Retrieval Optimization) ⭐

```
1. ✅ Ranking Signals
   - Importance scores
   - Usage frequency
   - Context relevance

2. ✅ Hierarchical Structure
   - 6-level chunk hierarchy
   - Parent-child relationships
   - Scope awareness

3. ✅ Performance
   - Incremental updates < 200ms
   - Background LSP enrichment
   - Smart caching
```

---

**Status**: ✅ Ready for Implementation  
**Timeline**: 6 weeks  
**Team Size**: 1-2 engineers  
**Risk**: Low (iterative, testable)  
**ROI**: Very High (core retrieval engine)

