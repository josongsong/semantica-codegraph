# Pyright 통합 아키텍처

## 설계 원칙

### 1. 의존성 분리
- **ExpressionBuilder**: Pyright와 직접 통신, Typed Expression IR 생성
- **DfgBuilder**: Expression IR만 소비, Pyright 몰라도 됨
- **GraphBuilder**: Expression IR + DFG만 소비

### 2. 간접 참조
- Pyright 결과를 직접 박지 않음
- `type_id: TypeEntityId` 형태로 간접 참조
- `inferred_type: str` (원본 저장용, 디버깅/로그)

### 3. 선택적 승격
- 모든 Expression이 GraphNode가 되는 건 아님
- 중요 Expression만 GraphNode로 승격:
  - Call (함수 호출)
  - Lambda (클로저)
  - Comprehension (복잡한 표현)
  - Name (중요 변수만)

---

## 구현 레이어

### Layer 1: Pyright LSP 통합 (외부 의존)

```python
# src/foundation/ir/external_analyzers/pyright_lsp.py
class PyrightLSPClient:
    """JSON-RPC over stdio 통신"""

    def __init__(self, project_root: Path):
        # pyright-langserver 프로세스 시작
        self._server_process = subprocess.Popen(
            ["pyright-langserver", "--stdio"],
            stdin=PIPE, stdout=PIPE
        )

        # 백그라운드 스레드로 응답 읽기
        self._reader_thread.start()

        # LSP initialize
        self._send_initialize()

    def hover(self, file: Path, line: int, col: int) -> dict:
        """textDocument/hover 요청"""
        # 1. 파일 열기 (didOpen)
        self._ensure_document_opened(file)

        # 2. hover 요청 전송
        response = self._send_request("textDocument/hover", {
            "textDocument": {"uri": file.as_uri()},
            "position": {"line": line - 1, "character": col}
        })

        # 3. 응답 파싱
        return {"type": "int", "docs": "..."}

    def definition(self, file: Path, line: int, col: int) -> Location:
        """textDocument/definition 요청"""
        response = self._send_request("textDocument/definition", ...)
        return Location(...)

    def references(self, file: Path, line: int, col: int) -> list[Location]:
        """textDocument/references 요청"""
        response = self._send_request("textDocument/references", ...)
        return [Location(...), ...]
```

**책임**: Pyright LSP 서버와 JSON-RPC 통신만

**주요 기능**:
- ✅ LSP initialize/initialized 프로토콜
- ✅ textDocument/didOpen (파일 열기)
- ✅ textDocument/hover (타입 정보)
- ✅ textDocument/definition (정의 위치)
- ✅ textDocument/references (참조 위치)
- ✅ 응답 캐싱
- ✅ 백그라운드 스레드로 응답 읽기

---

### Layer 2: Expression IR 생성 (Pyright 매핑)

```python
# src/foundation/semantic_ir/expression/builder.py
class ExpressionBuilder:
    def __init__(self, external_analyzer=None):
        self.pyright = external_analyzer

    def build_from_statement(...) -> list[Expression]:
        # AST 순회
        for node in ast:
            expr = Expression(...)

            # Pyright로 타입 채우기
            if self.pyright:
                hover = self.pyright.hover(...)
                expr.inferred_type = hover['type']
                expr.inferred_type_id = self._resolve_type_id(hover['type'])

        return expressions
```

**책임**:
- AST → Expression 변환
- Pyright 결과를 Expression.inferred_type에 매핑
- TypeEntity 간접 참조 (inferred_type_id)

**출력**: `list[Expression]` (타입 정보 포함)

---

### Layer 3: DFG 구성 (Expression IR 소비)

```python
# src/foundation/dfg/builder.py
class DfgBuilder:
    def __init__(self, analyzer_registry):
        # ❌ external_analyzer 없음!
        self.analyzer_registry = analyzer_registry

    def build_full(
        ir_doc,
        bfg_blocks,
        expressions: list[Expression],  # ← 이미 타입 채워진 Expression
    ) -> DfgSnapshot:
        # Expression에서 reads_vars/defines_var 읽어서 DFG 구성
        for expr in expressions:
            if expr.kind == ExprKind.NAME_LOAD:
                # 변수 읽기
                var_id = expr.attrs['var_name']
                dfg_edge = DataFlowEdge(
                    from_variable_id=var_id,
                    to_expr_id=expr.id
                )
```

**책임**:
- Expression IR → DFG 변환
- Pyright 몰라도 됨 (Expression.inferred_type만 사용)

**입력**: `list[Expression]` (타입 이미 채워짐)
**출력**: `DfgSnapshot`

---

### Layer 4: Graph 통합 (선택적 승격)

```python
# src/foundation/graph/builder.py
class GraphBuilder:
    def _convert_important_expressions(
        expressions: list[Expression],
        graph: GraphDocument
    ):
        """중요 Expression만 GraphNode로 승격"""

        for expr in expressions:
            # 선택적 승격 규칙
            if self._should_promote_to_node(expr):
                graph_node = GraphNode(
                    id=expr.id,
                    kind=GraphNodeKind.EXPRESSION,
                    attrs={
                        "expr_kind": expr.kind,
                        "inferred_type": expr.inferred_type,
                        "type_id": expr.inferred_type_id,
                    }
                )
                graph.graph_nodes[expr.id] = graph_node

    def _should_promote_to_node(self, expr: Expression) -> bool:
        """승격 기준"""
        # Call, Lambda, Comprehension은 항상 승격
        if expr.kind in (ExprKind.CALL, ExprKind.LAMBDA, ExprKind.COMPREHENSION):
            return True

        # Name은 중요 변수만 (파라미터, 전역변수 등)
        if expr.kind == ExprKind.NAME_LOAD:
            # attrs에서 중요도 판단
            return expr.attrs.get('is_important', False)

        # 나머지는 노드 안 만듦
        return False
```

**책임**:
- 중요 Expression만 GraphNode로 승격
- 나머지는 기존 GraphNode의 attrs에 포함

---

## 파이프라인 통합

### Semantic IR Builder

```python
# src/foundation/semantic_ir/builder.py
class SemanticIrBuilder:
    def build_full(
        ir_doc: IRDocument,
        source_map: dict[str, SourceFile],
        external_analyzer=None,  # ← Pyright는 여기만
    ) -> SemanticIrSnapshot:

        # 1. BFG (Basic Flow Graph)
        bfg_builder = BfgBuilder()
        bfg_graphs, bfg_blocks = bfg_builder.build_full(ir_doc, source_map)

        # 2. Expression IR (with Pyright)
        expr_builder = ExpressionBuilder(external_analyzer)
        all_expressions = []
        for block in bfg_blocks:
            expressions = expr_builder.build_from_block(block, source_map)
            all_expressions.extend(expressions)

        # 3. DFG (Expression IR만 사용, Pyright 의존 없음)
        dfg_builder = DfgBuilder(analyzer_registry)
        dfg_snapshot = dfg_builder.build_full(
            ir_doc,
            bfg_blocks,
            all_expressions  # ← 타입 이미 채워짐
        )

        # 4. CFG
        cfg_builder = CfgBuilder()
        cfg_graphs, cfg_blocks, cfg_edges = cfg_builder.build_from_bfg(bfg_graphs, bfg_blocks)

        return SemanticIrSnapshot(
            expressions=all_expressions,
            dfg_snapshot=dfg_snapshot,
            cfg_blocks=cfg_blocks,
            cfg_edges=cfg_edges,
        )
```

---

## Expression 선택적 승격 규칙

### 항상 GraphNode로
- `Call`: 함수 호출 (call graph 구성)
- `Lambda`: 클로저 (스코프 분석)
- `Comprehension`: 복잡한 표현 (성능 분석)

### 조건부 GraphNode
- `NAME_LOAD`: 중요 변수만
  - 파라미터
  - 전역 변수
  - 클래스 필드
  - 루프 카운터

### GraphNode 안 만듦
- `BinOp`, `UnaryOp`: 단순 연산
- `Literal`: 상수
- `ATTRIBUTE`: 속성 접근 (Call의 자식이면 고려)

---

## 요약

1. **Pyright 의존**: ExpressionBuilder만
2. **DfgBuilder**: Expression IR 소비, Pyright 몰라도 됨
3. **GraphBuilder**: 중요 Expression만 선택적 승격
4. **간접 참조**: `type_id`, `inferred_type_id`로 TypeEntity 참조
5. **원본 보존**: `inferred_type: str` (디버깅/로그용)

이 구조로 레이어 경계가 명확하고, Pyright 없이도 대부분 레이어가 동작 가능함.
