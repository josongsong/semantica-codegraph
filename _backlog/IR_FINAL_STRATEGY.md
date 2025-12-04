# IR 최종 전략: Pyright-Powered SCIP++

**작성일**: 2025-12-04  
**상태**: ✅ Corrected Strategy

---

## 🎯 핵심 인사이트 (수정)

### ❌ 이전 오해
```
"LSP 호출은 오버헤드다" → 최소화해야 한다
```

### ✅ 올바른 관점
```
Pyright는 이미 핵심 인프라다!
→ 풍부한 타입 정보를 IR의 강점으로 활용
→ SCIP를 넘어서는 Semantic IR 구축
```

---

## 📊 우리 IR의 차별점: SCIP++

### SCIP (Baseline)
```
✓ Symbol
✓ Occurrence (definition/reference)
✓ Relationship (import/inheritance)
✗ Type inference
✗ Control flow
✗ Data flow
✗ Call graph
```

### Semantica IR (SCIP++)
```
✅ Symbol (from AST)
✅ Occurrence (Edge + Role)
✅ Relationship (16+ edge kinds)

⭐ + Pyright Integration
  ✅ Type inference (every expression)
  ✅ Hover info (formatted docs)
  ✅ Diagnostics (real-time errors)
  ✅ Definition/References (cross-file)

⭐ + Advanced Analysis
  ✅ CFG (control flow graph)
  ✅ BFG (basic flow blocks)
  ✅ DFG (data flow graph)
  ✅ Call graph (with context)
  ✅ Dependency graph
```

**결론**: SCIP는 기본 occurrence만, 우리는 **type inference + CFG/DFG까지!**

---

## 🏗️ 아키텍처: Pyright-First Approach

```
┌────────────────────────────────────────────────────────────┐
│                    Pyright LSP (Foundation)                 │
│  • Type inference (every symbol)                           │
│  • Hover info (signatures, docs)                           │
│  • Diagnostics (errors, warnings)                          │
│  • Go-to-definition / Find-references                      │
└──────────────────┬─────────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────────┐
│              Layer 1: Structural IR (AST-based)            │
│  • Tree-sitter parsing                                     │
│  • Nodes (Symbol definitions)                              │
│  • Edges (Syntax relationships)                            │
│  • Spans (Source locations)                                │
└──────────────────┬─────────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────────┐
│        Layer 2: Pyright-Enhanced IR ⭐ KEY LAYER           │
│                                                             │
│  From Pyright:                                             │
│  • TypeEntity (inferred types for ALL symbols)             │
│  • SignatureEntity (function signatures)                   │
│  • Hover content (formatted documentation)                 │
│  • Diagnostics (errors/warnings)                           │
│  • Cross-file references (imports resolved)                │
│                                                             │
│  Integration Strategy:                                     │
│  1. Open file in Pyright LSP                               │
│  2. Query hover at every symbol location                   │
│  3. Extract type information                               │
│  4. Link to IR nodes                                       │
│  5. Store rich metadata                                    │
└──────────────────┬─────────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────────┐
│         Layer 3: Advanced Analysis ⭐ OUR VALUE ADD        │
│                                                             │
│  CFG (Control Flow Graph):                                 │
│  • Function-level control flow                             │
│  • Branch/loop analysis                                    │
│  • Exception handling paths                                │
│                                                             │
│  BFG (Basic Flow Graph):                                   │
│  • Statement-level blocks                                  │
│  • Straight-line code segments                             │
│                                                             │
│  DFG (Data Flow Graph):                                    │
│  • Variable definitions/uses                               │
│  • Value propagation                                       │
│  • Reaching definitions                                    │
│                                                             │
│  Call Graph:                                               │
│  • Function call hierarchy                                 │
│  • Dynamic dispatch resolution                             │
│  • Cross-module calls                                      │
└──────────────────┬─────────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────────────────────┐
│              Layer 4: Smart Edge System                    │
│                                                             │
│  Edge + SCIP Role:                                         │
│  • Every edge has occurrence role                          │
│  • No separate Occurrence storage                          │
│  • Memory efficient                                        │
│                                                             │
│  Enhanced EdgeIndex:                                       │
│  • by_symbol: Find all references                          │
│  • by_role: Filter by definition/reference                 │
│  • by_file: File-level queries                             │
│  • by_type: Type-based navigation                          │
└────────────────────────────────────────────────────────────┘
```

---

## 🔥 Pyright Integration Strategy (수정)

### 현재 구현 상태 확인

```python
# 이미 구현되어 있음!
# src/contexts/code_foundation/infrastructure/ir/external_analyzers/

✅ pyright_lsp.py      - LSP 클라이언트
✅ pyright_adapter.py  - Type 정보 추출
✅ pyright_daemon.py   - Daemon 관리

# 사용 예시
lsp_client.hover(file_path, line, col)
lsp_client.definition(file_path, line, col)
lsp_client.references(file_path, line, col)
```

### Phase 1 (수정): Pyright-Powered IR Generation

```python
# src/contexts/code_foundation/infrastructure/ir/pyright_ir_generator.py

class PyrightPoweredIRGenerator:
    """
    Pyright를 활용한 Rich IR 생성.
    
    Strategy:
    1. AST parsing (Tree-sitter) → Structural IR
    2. Pyright LSP → Type information
    3. Merge → Rich IR with types
    4. CFG/DFG analysis → Complete IR
    
    Pyright 호출은 오버헤드가 아니라 핵심 가치!
    """
    
    def __init__(
        self,
        ast_parser: ParserRegistry,
        pyright_client: PyrightLSPClient,
        ir_generator: PythonIRGenerator,
    ):
        self.ast_parser = ast_parser
        self.pyright = pyright_client
        self.ir_gen = ir_generator
        self.semantic_builder = DefaultSemanticIrBuilder()
    
    async def generate_rich_ir(
        self,
        file_path: str,
        source_code: str,
        snapshot_id: str,
    ) -> RichIRDocument:
        """
        Pyright를 활용한 Rich IR 생성.
        
        Returns:
            RichIRDocument with:
            - Structural IR (AST-based)
            - Type information (Pyright)
            - Hover content (Pyright)
            - Diagnostics (Pyright)
            - CFG/DFG (Our analysis)
        """
        
        # ====================================================
        # Step 1: Structural IR (Tree-sitter AST)
        # ====================================================
        source = SourceFile.from_content(file_path, source_code, "python")
        structural_ir = self.ir_gen.generate(source, snapshot_id)
        
        # ====================================================
        # Step 2: Pyright Type Information ⭐
        # ====================================================
        
        # 2.1 Open file in Pyright
        await self.pyright.open_file(file_path)
        
        # 2.2 Collect type info for ALL symbols
        type_annotations = await self._collect_type_info(
            structural_ir.nodes,
            file_path,
        )
        
        # 2.3 Collect hover for public APIs
        hover_info = await self._collect_hover_info(
            structural_ir.nodes,
            file_path,
        )
        
        # 2.4 Get diagnostics (already computed by Pyright)
        diagnostics = await self.pyright.get_diagnostics(file_path)
        
        # 2.5 Resolve cross-file references
        cross_file_refs = await self._resolve_cross_file_refs(
            structural_ir.edges,
            file_path,
        )
        
        # ====================================================
        # Step 3: Merge Pyright Info into IR ⭐
        # ====================================================
        
        # Enrich nodes with type info
        for node in structural_ir.nodes:
            if node.id in type_annotations:
                type_info = type_annotations[node.id]
                node.declared_type_id = type_info.type_id
                node.attrs["inferred_type"] = type_info.type_string
                node.attrs["is_nullable"] = type_info.is_nullable
                node.attrs["type_source"] = "pyright"
            
            if node.id in hover_info:
                node.hover_content = hover_info[node.id]
        
        # Enrich edges with resolved references
        for edge in structural_ir.edges:
            if edge.id in cross_file_refs:
                resolved = cross_file_refs[edge.id]
                edge.attrs["resolved_target"] = resolved.target_id
                edge.attrs["resolved_file"] = resolved.target_file
        
        # ====================================================
        # Step 4: Build Semantic IR (CFG/DFG) ⭐
        # ====================================================
        
        semantic_snapshot, semantic_index = self.semantic_builder.build_full(
            structural_ir,
            source_map={file_path: source},
        )
        
        # ====================================================
        # Step 5: Assemble Rich IR
        # ====================================================
        
        rich_ir = RichIRDocument(
            # Structural
            repo_id=structural_ir.repo_id,
            snapshot_id=snapshot_id,
            nodes=structural_ir.nodes,
            edges=structural_ir.edges,
            
            # Pyright-enhanced ⭐
            type_annotations=type_annotations,
            hover_info=hover_info,
            diagnostics=self._convert_diagnostics(diagnostics, file_path),
            cross_file_references=cross_file_refs,
            
            # Semantic analysis ⭐
            types=semantic_snapshot.types,
            signatures=semantic_snapshot.signatures,
            cfg_blocks=semantic_snapshot.cfg_blocks,
            cfg_edges=semantic_snapshot.cfg_edges,
            dfg_snapshot=semantic_snapshot.dfg_snapshot,
        )
        
        # Build enhanced indexes
        rich_ir.build_all_indexes()
        
        return rich_ir
    
    async def _collect_type_info(
        self,
        nodes: list[Node],
        file_path: str,
    ) -> dict[str, TypeAnnotation]:
        """
        모든 심볼의 타입 정보 수집.
        
        Pyright는 이미 파일 전체를 분석했으므로,
        각 symbol 위치에서 hover만 호출하면 됨.
        """
        type_annotations = {}
        
        # Public APIs first (prioritize)
        public_nodes = [n for n in nodes if self._is_public(n)]
        private_nodes = [n for n in nodes if not self._is_public(n)]
        
        # Batch processing
        batch_size = 50
        
        for nodes_batch in [public_nodes, private_nodes]:
            for i in range(0, len(nodes_batch), batch_size):
                batch = nodes_batch[i:i+batch_size]
                
                # Parallel queries
                tasks = [
                    self._query_type_info(node, file_path)
                    for node in batch
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for node, result in zip(batch, results):
                    if isinstance(result, Exception):
                        logger.debug(f"Type query failed for {node.id}: {result}")
                        continue
                    
                    type_annotations[node.id] = result
        
        return type_annotations
    
    async def _query_type_info(
        self,
        node: Node,
        file_path: str,
    ) -> TypeAnnotation:
        """단일 노드의 타입 정보 쿼리"""
        hover_result = await self.pyright.hover(
            Path(file_path),
            node.span.start_line,
            node.span.start_col,
        )
        
        if not hover_result or not hover_result.get("type"):
            return TypeAnnotation(
                node_id=node.id,
                type_string="Unknown",
                is_nullable=False,
            )
        
        type_string = hover_result["type"]
        
        return TypeAnnotation(
            node_id=node.id,
            type_string=type_string,
            type_id=self._generate_type_id(type_string),
            is_nullable="None" in type_string or "Optional" in type_string,
            is_union="|" in type_string,
            source_location=node.span,
        )
```

---

## 📊 비교: SCIP vs Semantica IR

### SCIP Index (.scip 파일)
```protobuf
// Symbol definition
symbol: "scip-python pypi myproject v1.0.0 src/`main.py`/Calculator#"

// Occurrences
occurrences: [
  {
    range: [10, 4, 10, 14]
    symbol: "..."
    symbol_roles: 1  // DEFINITION
  },
  {
    range: [20, 8, 20, 18]
    symbol: "..."
    symbol_roles: 8  // REFERENCE
  }
]

// ❌ No type information
// ❌ No CFG/DFG
// ❌ No hover content
```

### Semantica IR (PostgreSQL + Indexes)
```python
# Node (Symbol definition)
Node(
    id="class:myproject::src/main.py::Calculator",
    kind=NodeKind.CLASS,
    fqn="src.main.Calculator",
    span=Span(10, 4, 50, 0),
    
    # ⭐ Pyright-enhanced
    declared_type_id="type:myproject::Calculator",
    hover_content="""
```python
class Calculator:
    \"\"\"Simple calculator for arithmetic operations\"\"\"
```
    
**Methods**:
- `add(a: int, b: int) -> int`: Add two numbers
- `subtract(a: int, b: int) -> int`: Subtract two numbers
    """,
    attrs={
        "inferred_type": "Type[Calculator]",
        "is_nullable": False,
        "type_source": "pyright",
        "visibility": "public",
        "is_test": False,
    },
)

# Edge (with SCIP role)
Edge(
    id="edge:call:main→calculator_add:1",
    kind=EdgeKind.CALLS,
    source_id="function:myproject::src/main.py::main",
    target_id="method:myproject::src/main.py::Calculator::add",
    span=Span(20, 8, 20, 18),
    
    # ⭐ SCIP-compatible role
    occurrence_roles=SymbolRole.READ_ACCESS,
    
    # ⭐ Pyright-enhanced
    attrs={
        "resolved_target": "method:Calculator::add",
        "resolved_file": "src/main.py",
        "call_type": "instance_method",
        "inferred_return_type": "int",
    },
)

# TypeEntity (from Pyright)
TypeEntity(
    id="type:myproject::Calculator",
    raw="Calculator",
    flavor=TypeFlavor.CLASS,
    resolution_level=TypeResolutionLevel.FULLY_RESOLVED,
    resolved_target="class:myproject::src/main.py::Calculator",
)

# CFG Block (our analysis)
ControlFlowBlock(
    id="cfg:main:block:1",
    kind=CFGBlockKind.NORMAL,
    span=Span(15, 4, 18, 0),
    function_node_id="function:main",
    
    # Data flow
    defined_variable_ids=["var:result"],
    used_variable_ids=["var:calc", "var:a", "var:b"],
)

# Diagnostic (from Pyright)
Diagnostic(
    severity=Severity.ERROR,
    message="Argument of type 'str' cannot be assigned to parameter of type 'int'",
    span=Span(25, 15, 25, 18),
    source="pyright",
    code="type-mismatch",
)
```

**결론**: Semantica IR는 **SCIP + Pyright + CFG/DFG** 모두 포함!

---

## 🎯 최종 구현 전략 (수정)

### Phase 1: Pyright-Powered Core (2주)
```python
✓ PyrightPoweredIRGenerator
  - Structural IR (Tree-sitter)
  - Type info (Pyright hover)
  - Hover content (Pyright)
  - Diagnostics (Pyright)

✓ Edge + SymbolRole
  - SCIP-compatible occurrence roles
  - Memory efficient (Edge 확장)

✓ Enhanced EdgeIndex
  - by_symbol, by_role, by_type
  - O(1) find-references
```

### Phase 2: Semantic Analysis (2주)
```python
✓ CFG Builder (already exists!)
  - Control flow graph
  - Branch/loop analysis

✓ BFG Builder (already exists!)
  - Basic flow blocks

✓ DFG Builder (already exists!)
  - Data flow graph
  - Reaching definitions

✓ Integration with Pyright types
  - Type-aware data flow
  - Narrowing analysis
```

### Phase 3: Cross-File Intelligence (2주)
```python
✓ Cross-file type resolution
  - Pyright definition lookup
  - Import chain tracking

✓ Call graph with types
  - Type-based dispatch resolution
  - Generic instantiation

✓ Dependency graph
  - Module-level dependencies
  - Package metadata
```

### Phase 4: Query & LSP (2주)
```python
✓ Enhanced queries
  - Find references (by type)
  - Call hierarchy (with types)
  - Type hierarchy

✓ LSP Server
  - Go-to-definition
  - Find-references
  - Hover (rich with CFG/DFG info)
  - Diagnostics
```

---

## 💡 핵심 가치 제안

### SCIP는 기본 occurrence만
```
✓ Definition
✓ Reference
✓ Import
✗ Types
✗ Control flow
✗ Data flow
```

### Semantica IR는 완전한 분석
```
✅ Occurrence (Edge + Role)
✅ Types (Pyright inference)
✅ Hover (rich documentation)
✅ Diagnostics (real-time)
✅ CFG (control flow)
✅ DFG (data flow)
✅ Call graph (typed)
✅ Cross-file resolution
```

**Use Cases**:
1. **Code Search**: Type-aware search
2. **Refactoring**: Safe with type checking
3. **Analysis**: Impact analysis with CFG/DFG
4. **AI Agent**: Rich context for LLM
5. **IDE**: Full LSP support

---

## 📊 성능 전략 (수정)

### Pyright 호출 최적화

**❌ 이전 오해**: "LSP 호출 최소화"
**✅ 올바른 접근**: "LSP 호출 효율화"

```python
# 전략 1: 파일 단위 배치 처리
# Pyright는 파일 전체를 이미 분석했음
# 여러 symbol을 순차적으로 query

async def collect_all_types_in_file(file_path: str):
    # 1. Pyright에 파일 열기 (한번)
    await pyright.open_file(file_path)
    
    # 2. 모든 symbol 위치 수집
    symbols = extract_all_symbols(file_path)
    
    # 3. 배치 쿼리 (병렬)
    tasks = [
        pyright.hover(file_path, s.line, s.col)
        for s in symbols
    ]
    results = await asyncio.gather(*tasks)
    
    # Total: 1 file open + N parallel hovers
    # vs Sequential: N file opens + N hovers

# 전략 2: 캐싱
# 파일 content_hash 기반 캐싱
# 동일 파일 → 캐시 히트

cache_key = f"pyright:{content_hash}:{symbol_id}"
if cached := redis.get(cache_key):
    return cached

result = await pyright.hover(...)
redis.set(cache_key, result, ttl=3600)

# 전략 3: Incremental
# 파일 수정 시 변경된 symbol만 재쿼리

for symbol in affected_symbols:
    type_info = await pyright.hover(...)
```

---

## ✅ 수정된 결론

### 이전 비판의 오류
```
❌ "LSP 호출은 오버헤드다"
→ Pyright는 이미 필수 인프라
→ 풍부한 정보의 원천
```

### 올바른 전략
```
✅ Pyright를 IR의 핵심으로
✅ Type inference를 모든 symbol에
✅ CFG/DFG로 추가 가치
✅ = SCIP++: Best-in-class IR
```

### 차별화 포인트
```
SCIP:           Occurrence만
LSP:            Type + Basic navigation
Semantica IR:   Type + CFG/DFG + Call graph + Rich metadata
                ⬆️ SOTA급!
```

---

**Status**: ✅ Strategy Finalized  
**Key Insight**: Pyright는 오버헤드가 아니라 핵심 가치!  
**Next**: Phase 1 구현 - Pyright-Powered IR Generator

