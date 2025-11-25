# Pyright 파이프라인 스펙

## 1. 파이프라인 확정

### 1.1 입력/출력 포맷

#### Pyright LSP 입력
```python
# 입력: 파일 경로 + 위치
file_path: Path
line: int        # 1-indexed
column: int      # 0-indexed
```

#### Pyright LSP 출력
```python
# hover 출력
HoverResult = {
    "type": str,      # "int" | "List[User]" | "(x: int, y: str) -> bool"
    "docs": str | None  # Docstring
}

# definition 출력
Location = {
    "file_path": Path,
    "line": int,
    "column": int
}

# references 출력
list[Location]
```

---

### 1.2 Pyright 접근 규칙 (READ-ONLY)

#### ✅ 허용: 오직 IR Builder만
```python
# 1. TypeIrBuilder
class TypeIrBuilder:
    def __init__(self, external_analyzer: ExternalAnalyzer | None):
        self.pyright = external_analyzer  # ✅

    def build_full(self, ir_doc, source_map):
        if self.pyright:
            hover = self.pyright.hover(...)  # ✅

# 2. SignatureIrBuilder
class SignatureIrBuilder:
    def __init__(self, external_analyzer: ExternalAnalyzer | None):
        self.pyright = external_analyzer  # ✅

# 3. ExpressionBuilder
class ExpressionBuilder:
    def __init__(self, external_analyzer: ExternalAnalyzer | None):
        self.pyright = external_analyzer  # ✅
```

#### ❌ 금지: 모든 하위 레이어
```python
# DfgBuilder
class DfgBuilder:
    def __init__(self, analyzer_registry):
        # ❌ self.pyright 없음!
        # Expression IR만 소비

# GraphBuilder
class GraphBuilder:
    # ❌ Pyright 접근 금지
    # Expression/Type/Signature IR만 소비
```

---

### 1.3 데이터 흐름

```
[Pyright LSP Server]
        ↓
┌───────────────────────────────────────┐
│ IR Builders (Pyright READ-ONLY)      │
│ - TypeIrBuilder                       │
│ - SignatureIrBuilder                  │
│ - ExpressionBuilder                   │
└───────────────────────────────────────┘
        ↓
┌───────────────────────────────────────┐
│ Semantic IR (Pyright 결과 저장)      │
│ - TypeEntity: pyright_type            │
│ - SignatureEntity: pyright_signature  │
│ - Expression: inferred_type           │
└───────────────────────────────────────┘
        ↓
┌───────────────────────────────────────┐
│ 하위 레이어 (Pyright 접근 금지)      │
│ - DfgBuilder: Expression IR 소비      │
│ - GraphBuilder: IR만 소비             │
└───────────────────────────────────────┘
```

---

## 2. ExpressionIR 스펙

### 2.1 Expression 노드 정의

#### ExprKind (14종류)
```python
class ExprKind(str, Enum):
    # Value access (3)
    NAME_LOAD = "NameLoad"      # x
    ATTRIBUTE = "Attribute"      # obj.attr
    SUBSCRIPT = "Subscript"      # arr[i]

    # Operations (4)
    BIN_OP = "BinOp"            # a + b
    UNARY_OP = "UnaryOp"        # -a, not x
    COMPARE = "Compare"         # a < b
    BOOL_OP = "BoolOp"          # a and b

    # Calls (2)
    CALL = "Call"               # fn(x)
    INSTANTIATE = "Instantiate" # Class()

    # Literals (2)
    LITERAL = "Literal"         # 1, "str", True
    COLLECTION = "Collection"   # [1,2], {a:b}

    # Special (3)
    ASSIGN = "Assign"           # a = b (left side)
    LAMBDA = "Lambda"           # lambda x: x + 1
    COMPREHENSION = "Comprehension"  # [x for x in lst]
```

#### Expression Entity
```python
@dataclass
class Expression:
    # [Required] Identity
    id: str                      # expr:{repo}:{file}:{line}:{col}:{counter}
    kind: ExprKind
    repo_id: str
    file_path: str
    function_fqn: str | None     # None = module-level

    # [Required] Location
    span: Span

    # [Optional] DFG connections
    reads_vars: list[str]        # VariableEntity IDs
    defines_var: str | None      # VariableEntity ID

    # [Optional] Type (Pyright)
    inferred_type: str | None    # Pyright hover 결과 (원본)
    inferred_type_id: str | None # TypeEntity ID (정규화)

    # [Optional] AST tree
    parent_expr_id: str | None
    child_expr_ids: list[str]

    # [Optional] CFG
    block_id: str | None         # CFGBlock ID

    # [Optional] Attributes
    attrs: dict
```

---

### 2.2 AST → ExpressionIR 매핑

#### tree-sitter node → ExprKind
```python
MAPPING = {
    # Value access
    "identifier": ExprKind.NAME_LOAD,
    "attribute": ExprKind.ATTRIBUTE,
    "subscript": ExprKind.SUBSCRIPT,

    # Operations
    "binary_expression": ExprKind.BIN_OP,
    "unary_expression": ExprKind.UNARY_OP,
    "comparison_operator": ExprKind.COMPARE,
    "boolean_operator": ExprKind.BOOL_OP,

    # Calls
    "call": ExprKind.CALL,

    # Literals
    "integer": ExprKind.LITERAL,
    "float": ExprKind.LITERAL,
    "string": ExprKind.LITERAL,
    "true": ExprKind.LITERAL,
    "false": ExprKind.LITERAL,
    "none": ExprKind.LITERAL,

    # Collections
    "list": ExprKind.COLLECTION,
    "dictionary": ExprKind.COLLECTION,
    "set": ExprKind.COLLECTION,
    "tuple": ExprKind.COLLECTION,

    # Special
    "lambda": ExprKind.LAMBDA,
    "list_comprehension": ExprKind.COMPREHENSION,
}
```

---

### 2.3 ExpressionBuilder 인터페이스

```python
class ExpressionBuilder:
    def __init__(self, external_analyzer: ExternalAnalyzer | None):
        self.pyright = external_analyzer
        self._expr_counter = 0

    def build_from_statement(
        self,
        stmt_node: TSNode,
        block_id: str,
        function_fqn: str | None,
        repo_id: str,
        file_path: str,
        source_file: SourceFile,
    ) -> list[Expression]:
        """
        AST statement → list[Expression]

        Steps:
        1. AST 순회하며 expression 추출
        2. 각 expression에 Pyright hover 호출 (if available)
        3. parent-child 관계 설정
        4. reads_vars/defines_var 추출 (간단한 경우만)
        """
        expressions = []

        def traverse(node: TSNode, parent_expr_id: str | None):
            expr = self._create_expression(node, block_id, ...)
            if expr:
                if self.pyright:
                    self._enrich_with_pyright(expr, source_file)
                expressions.append(expr)
                # Recurse
                for child in node.children:
                    traverse(child, expr.id)

        traverse(stmt_node, None)
        return expressions

    def _enrich_with_pyright(self, expr: Expression, source_file: SourceFile):
        """Pyright hover → Expression.inferred_type"""
        hover = self.pyright.hover(
            Path(expr.file_path),
            expr.span.start_line,
            expr.span.start_col
        )
        if hover:
            expr.inferred_type = hover["type"]
            # TODO: Convert to TypeEntity and link inferred_type_id
```

---

## 3. DfgBuilder 리팩토링

### 3.1 현재 문제
```python
# ❌ 현재: AST 직접 파싱
class DfgBuilder:
    def _process_block(self, block, ...):
        ast_tree = AstTree.parse(source_file)  # ❌ 레이어 위반
        statements = self._find_statements_in_span(...)
        for stmt in statements:
            reads, writes = analyzer.analyze(stmt)  # ❌ AST 직접
```

### 3.2 수정 후
```python
# ✅ 수정 후: Expression IR만 소비
class DfgBuilder:
    def __init__(self, analyzer_registry):
        # ❌ self.pyright 없음
        self.analyzer_registry = analyzer_registry

    def build_full(
        self,
        ir_doc: IRDocument,
        bfg_blocks: list[BasicFlowBlock],
        expressions: list[Expression],  # ← Expression IR 입력
    ) -> DfgSnapshot:
        """
        Expression IR → DFG

        Steps:
        1. Expression.reads_vars → VariableEvent (read)
        2. Expression.defines_var → VariableEvent (write)
        3. DataFlowEdge 생성 (def → use)
        """
        snapshot = DfgSnapshot()

        # Group expressions by block
        exprs_by_block = self._group_expressions_by_block(expressions)

        for block_id, block_exprs in exprs_by_block.items():
            # Extract variables from expressions
            for expr in block_exprs:
                # Read events
                for var_id in expr.reads_vars:
                    event = VariableEvent(
                        id=f"evt:{var_id}:{expr.id}",
                        variable_id=var_id,
                        block_id=block_id,
                        op_kind="read",
                        ...
                    )
                    snapshot.events.append(event)

                # Write events
                if expr.defines_var:
                    event = VariableEvent(
                        id=f"evt:{expr.defines_var}:{expr.id}",
                        variable_id=expr.defines_var,
                        block_id=block_id,
                        op_kind="write",
                        ...
                    )
                    snapshot.events.append(event)

        # Build data flow edges
        self._build_dataflow_edges(snapshot)
        return snapshot
```

---

## 4. TypeIrBuilder Pyright 연동

### 4.1 Pyright 타입 → 내부 타입 매핑

#### 기본 타입
```python
PYRIGHT_TO_INTERNAL = {
    # Primitives
    "int": ("int", TypeFlavor.PRIMITIVE),
    "str": ("str", TypeFlavor.PRIMITIVE),
    "float": ("float", TypeFlavor.PRIMITIVE),
    "bool": ("bool", TypeFlavor.PRIMITIVE),
    "None": ("None", TypeFlavor.PRIMITIVE),

    # Builtins
    "list": ("list", TypeFlavor.BUILTIN),
    "dict": ("dict", TypeFlavor.BUILTIN),
    "set": ("set", TypeFlavor.BUILTIN),
    "tuple": ("tuple", TypeFlavor.BUILTIN),
}
```

#### Generic 처리
```python
# Pyright: "List[User]"
# → TypeEntity:
#     id: "type:List[User]"
#     raw: "List[User]"
#     flavor: BUILTIN
#     generic_param_ids: ["type:User"]
```

#### Union 처리
```python
# Pyright: "int | str" 또는 "Union[int, str]"
# → TypeEntity:
#     id: "type:Union[int,str]"
#     raw: "int | str"
#     flavor: GENERIC
#     generic_param_ids: ["type:int", "type:str"]
#     is_nullable: False
```

#### Optional 처리
```python
# Pyright: "Optional[User]" 또는 "User | None"
# → TypeEntity:
#     id: "type:User"
#     raw: "User | None"
#     flavor: USER
#     is_nullable: True
```

### 4.2 Overload 처리
```python
# Pyright hover 결과:
# "(x: int) -> str"
# "(x: str) -> int"
#
# → SignatureEntity 여러 개 생성
# signature_1: param_types=[int], return_type=str
# signature_2: param_types=[str], return_type=int
#
# Node.signature_id → primary signature
# Node.attrs["overload_signature_ids"] → 나머지
```

---

## 5. SignatureIrBuilder Pyright 연동

### 5.1 Pyright signature → SignatureEntity

```python
class SignatureIrBuilder:
    def __init__(self, external_analyzer: ExternalAnalyzer | None):
        self.pyright = external_analyzer

    def build_full(self, ir_doc, source_map):
        signatures = []

        for node in ir_doc.nodes:
            if node.kind in (NodeKind.FUNCTION, NodeKind.METHOD):
                sig = self._build_signature(node, source_map)

                # Pyright hover for enhanced signature
                if self.pyright and node.span:
                    hover = self.pyright.hover(
                        Path(node.file_path),
                        node.span.start_line,
                        node.span.start_col
                    )
                    if hover:
                        sig.pyright_signature = hover["type"]
                        sig.pyright_param_docs = self._parse_param_docs(hover["docs"])

                signatures.append(sig)

        return signatures
```

---

## 6. 전체 파이프라인 통합

```python
class DefaultSemanticIrBuilder:
    def __init__(self, external_analyzer: ExternalAnalyzer | None = None):
        self.pyright = external_analyzer

        # IR Builders (Pyright 주입)
        self.type_builder = TypeIrBuilder(self.pyright)
        self.signature_builder = SignatureIrBuilder(self.pyright)
        self.expr_builder = ExpressionBuilder(self.pyright)

        # BFG/CFG (Pyright 불필요)
        self.bfg_builder = BfgBuilder()
        self.cfg_builder = CfgBuilder()

        # DFG (Pyright 의존 없음)
        analyzer_registry = AnalyzerRegistry()
        self.dfg_builder = DfgBuilder(analyzer_registry)

    def build_full(self, ir_doc, source_map):
        # 1. Typing
        types, type_index = self.type_builder.build_full(ir_doc, source_map)

        # 2. Signatures
        signatures, sig_index = self.signature_builder.build_full(ir_doc, source_map)

        # 3. BFG
        bfg_graphs, bfg_blocks = self.bfg_builder.build_full(ir_doc, source_map)

        # 4. Expression IR
        expressions = []
        for block in bfg_blocks:
            if block.file_path in source_map:
                block_exprs = self.expr_builder.build_from_block(
                    block, source_map[block.file_path]
                )
                expressions.extend(block_exprs)

        # 5. CFG
        cfg_graphs, cfg_blocks, cfg_edges = self.cfg_builder.build_from_bfg(
            bfg_graphs, bfg_blocks
        )

        # 6. DFG (Expression 소비)
        dfg_snapshot = self.dfg_builder.build_full(
            ir_doc, bfg_blocks, expressions
        )

        return SemanticIrSnapshot(
            types=types,
            signatures=signatures,
            expressions=expressions,
            cfg_blocks=cfg_blocks,
            cfg_edges=cfg_edges,
            dfg_snapshot=dfg_snapshot,
        ), SemanticIndex(...)
```

---

## 7. 규칙 요약

### ✅ DO
1. Pyright는 오직 IR Builder에서만 호출
2. Pyright 결과는 즉시 IR Entity에 저장
3. 하위 레이어는 IR만 소비
4. 타입 매핑은 명시적 테이블 사용
5. Expression은 AST와 1:1 매핑

### ❌ DON'T
1. DfgBuilder/GraphBuilder에서 Pyright 호출 금지
2. AST를 여러 곳에서 중복 파싱 금지
3. Pyright 타입을 직접 문자열 비교 금지
4. Expression 없이 DFG 생성 금지
5. 레이어 경계 위반 금지

---

## 8. 테스트 전략

### Unit Tests
- `test_expression_builder.py`: AST → Expression
- `test_expression_pyright.py`: Pyright 타입 주입
- `test_dfg_from_expressions.py`: Expression → DFG

### Integration Tests
- `test_semantic_ir_pipeline.py`: 전체 파이프라인
- `test_pyright_e2e.py`: Pyright 있을 때/없을 때

### Performance Tests
- Pyright 캐싱 효과 측정
- Expression 추출 오버헤드 측정
