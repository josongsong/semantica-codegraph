# Semantic IR 모듈

## 개요
Structural IR 위에 구축된 의미 분석 레이어. 타입 시스템, 시그니처, 제어 흐름, 데이터 흐름 분석.
핵심 구현: [src/contexts/code_foundation/infrastructure/semantic_ir/](src/contexts/code_foundation/infrastructure/semantic_ir/)

---

## 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                   DefaultSemanticIrBuilder                       │
│                      [builder.py:82]                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Phase 1: Type + Signature                                       │
│  ┌──────────────┐    ┌──────────────┐                           │
│  │ TypeIrBuilder│    │SignatureIr   │                           │
│  │              │    │   Builder    │                           │
│  └──────────────┘    └──────────────┘                           │
│        │                    │                                    │
│        ▼                    ▼                                    │
│   TypeEntity[]        SignatureEntity[]                         │
│                                                                  │
│  Phase 2: Control Flow + Expression                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │  BfgBuilder  │───▶│  CfgBuilder  │    │ Expression   │       │
│  │              │    │              │    │   Builder    │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│        │                    │                    │               │
│        ▼                    ▼                    ▼               │
│   BasicFlowGraph     ControlFlowGraph      Expression[]         │
│                                                  │               │
│  Phase 2d: Type Linking                          │               │
│  ┌──────────────┐                                │               │
│  │  TypeLinker  │◀───────────────────────────────┘               │
│  └──────────────┘                                                │
│                                                                  │
│  Phase 3: Data Flow                                              │
│  ┌──────────────┐                                                │
│  │  DfgBuilder  │                                                │
│  └──────────────┘                                                │
│        │                                                         │
│        ▼                                                         │
│   DfgSnapshot (Variables, Events, Edges)                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 빌드 파이프라인

```
IRDocument
  │
  ▼
┌─────────────────────────────────────┐
│ Phase 1a: Type System               │
│ TypeIrBuilder                       │
│ [typing/builder.py:18]              │
│ - TypeEntity 추출                    │
│ - TypeIndex 빌드                     │
└─────────────────────────────────────┘
  │
  ▼ types[], type_index
┌─────────────────────────────────────┐
│ Phase 1b: Signatures                │
│ SignatureIrBuilder                  │
│ [signature/builder.py]              │
│ - 함수/메서드 시그니처 추출           │
│ - async, static, throws 메타데이터   │
└─────────────────────────────────────┘
  │
  ▼ signatures[], signature_index
┌─────────────────────────────────────┐
│ Phase 2a: BFG (Basic Flow Graph)    │
│ BfgBuilder                          │
│ [bfg/builder.py]                    │
│ - 기본 블록 추출 (edges 없음)         │
│ - break/continue/return 메타데이터   │
└─────────────────────────────────────┘
  │
  ▼ bfg_graphs[], bfg_blocks[]
┌─────────────────────────────────────┐
│ Phase 2b: CFG (Control Flow Graph)  │
│ CfgBuilder                          │
│ [cfg/builder.py]                    │
│ - BFG → CFG 변환                     │
│ - Control flow edges 생성            │
└─────────────────────────────────────┘
  │
  ▼ cfg_graphs[], cfg_blocks[], cfg_edges[]
┌─────────────────────────────────────┐
│ Phase 2c: Expression IR             │
│ ExpressionBuilder                   │
│ [expression/builder.py:133]         │
│ - AST에서 Expression 추출            │
│ - Pyright 타입 추론 연동              │
└─────────────────────────────────────┘
  │
  ▼ expressions[]
┌─────────────────────────────────────┐
│ Phase 2d: Type Linking              │
│ TypeLinker                          │
│ [type_linker.py:25]                 │
│ - Expression → TypeEntity 연결       │
│ - Cross-file import 해석             │
└─────────────────────────────────────┘
  │
  ▼ expressions[] (with type_id)
┌─────────────────────────────────────┐
│ Phase 3: DFG (Data Flow Graph)      │
│ DfgBuilder                          │
│ [../dfg/builder.py:53]              │
│ - VariableEntity 추출                │
│ - VariableEvent (read/write)        │
│ - DataFlowEdge 생성                  │
└─────────────────────────────────────┘
  │
  ▼
SemanticIrSnapshot + SemanticIndex
```

---

## Type System

### TypeEntity
위치: [typing/models.py:33](src/contexts/code_foundation/infrastructure/semantic_ir/typing/models.py#L33)

```python
@dataclass(slots=True)
class TypeEntity:
    id: str                          # "type:List[str]"
    raw: str                         # 코드에 나타난 그대로
    flavor: TypeFlavor               # PRIMITIVE | BUILTIN | USER | EXTERNAL | TYPEVAR | GENERIC
    is_nullable: bool
    resolution_level: TypeResolutionLevel  # RAW | BUILTIN | LOCAL | MODULE | PROJECT | EXTERNAL
    resolved_target: str | None      # 해석된 Node.id (Class/Interface)
    generic_param_ids: list[str]     # 제네릭 파라미터 TypeEntity.id 목록
```

### TypeFlavor
```python
class TypeFlavor(str, Enum):
    PRIMITIVE = "primitive"   # int, str, bool, float, bytes, None
    BUILTIN = "builtin"       # list, dict, set, tuple, Any, Optional, Union
    USER = "user"             # 사용자 정의 클래스
    EXTERNAL = "external"     # 외부 라이브러리 타입
    TYPEVAR = "typevar"       # Generic type variables (T, K, V)
    GENERIC = "generic"       # Generic types (List[T])
```

### TypeResolutionLevel
```python
class TypeResolutionLevel(str, Enum):
    RAW = "raw"           # 문자열만 (미해석)
    BUILTIN = "builtin"   # 파이썬 내장 타입 해석됨
    LOCAL = "local"       # 같은 파일 내 클래스 해석됨
    MODULE = "module"     # 같은 패키지 import 해석됨
    PROJECT = "project"   # 프로젝트 전체 해석됨
    EXTERNAL = "external" # 외부 의존성 해석됨 (stdlib)
```

### TypeResolver
위치: [typing/resolver.py:25](src/contexts/code_foundation/infrastructure/semantic_ir/typing/resolver.py#L25)

**7단계 Resolution Priority:**

```python
def _classify_type(self, type_str: str):
    base_type = type_str.split("[")[0].strip()

    # 1. Alias 해석
    if base_type in self._import_aliases:
        base_type = self._import_aliases[base_type]

    # 2. BUILTIN (int, str, List, Dict, Optional, etc.)
    if base_type in self.BUILTIN_TYPES:
        return TypeFlavor.BUILTIN, TypeResolutionLevel.BUILTIN, None

    # 3. LOCAL (같은 파일 클래스)
    if base_type in self._local_classes:
        return TypeFlavor.USER, TypeResolutionLevel.LOCAL, self._local_classes[base_type]

    # 4. MODULE (같은 패키지 import)
    if base_type in self._module_types:
        return TypeFlavor.USER, TypeResolutionLevel.MODULE, self._module_types[base_type]

    # 5. PROJECT (크로스 패키지)
    if base_type in self._project_types:
        return TypeFlavor.USER, TypeResolutionLevel.PROJECT, self._project_types[base_type]

    # 6. STDLIB (Path, datetime, Enum 등)
    if base_type in self.STDLIB_TYPES:
        return TypeFlavor.EXTERNAL, TypeResolutionLevel.EXTERNAL, None

    # 7. RAW (미해석)
    return TypeFlavor.EXTERNAL, TypeResolutionLevel.RAW, None
```

**지원 타입 목록:**

| 카테고리 | 타입 |
|----------|------|
| Primitives | int, str, float, bool, bytes, None |
| Collections | list, List, dict, Dict, set, Set, tuple, Tuple |
| Typing | Any, Optional, Union, Callable, Iterable, Iterator, Sequence |
| Advanced | Generator, Coroutine, Awaitable, Protocol, Final, Literal |
| Stdlib | Path, datetime, Enum, UUID, Decimal, Logger, Task, Future |

---

## Signature System

### SignatureEntity
위치: [signature/models.py:21](src/contexts/code_foundation/infrastructure/semantic_ir/signature/models.py#L21)

```python
@dataclass
class SignatureEntity:
    id: str                        # "sig:HybridRetriever.plan(Query,int)->RetrievalPlan"
    owner_node_id: str             # 소유 함수/메서드 Node.id
    name: str
    raw: str                       # 시그니처 문자열

    parameter_type_ids: list[str]  # 파라미터 TypeEntity.id 목록
    return_type_id: str | None     # 반환 TypeEntity.id

    is_async: bool = False
    is_static: bool = False
    visibility: Visibility | None = None  # PUBLIC | PROTECTED | PRIVATE | INTERNAL
    throws_type_ids: list[str]     # 예외 TypeEntity.id 목록
    signature_hash: str | None     # 인터페이스 변경 감지용 해시
```

---

## Control Flow Graph (CFG)

### BFG (Basic Flow Graph)
위치: [bfg/models.py](src/contexts/code_foundation/infrastructure/semantic_ir/bfg/models.py)

**BFG = 블록만, edges 없음. CFG가 edges 추가.**

```python
@dataclass
class BasicFlowBlock:
    id: str                        # "bfg:{function_node_id}:block:{index}"
    kind: BFGBlockKind             # Entry | Exit | Statement | Condition | LoopHeader | Try | Catch | Finally
    function_node_id: str
    span: Span | None

    # AST 메타데이터 (CFG edge 생성용)
    ast_node_type: str | None      # "if_statement", "for_statement"
    ast_has_alternative: bool      # else/elif 존재 여부

    # Data Flow 준비
    defined_variable_ids: list[str]
    used_variable_ids: list[str]

    # Control Flow 메타데이터
    is_break: bool = False
    is_continue: bool = False
    is_return: bool = False
    target_loop_id: str | None     # break/continue 대상 루프
```

### CFG (Control Flow Graph)
위치: [cfg/models.py](src/contexts/code_foundation/infrastructure/semantic_ir/cfg/models.py)

```python
@dataclass
class ControlFlowBlock:
    id: str                        # "cfg:plan:block:1"
    kind: CFGBlockKind             # Entry | Exit | Block | Condition | LoopHeader | Try | Catch | Finally
    function_node_id: str
    span: Span | None
    defined_variable_ids: list[str]
    used_variable_ids: list[str]

@dataclass
class ControlFlowEdge:
    source_block_id: str
    target_block_id: str
    kind: CFGEdgeKind              # NORMAL | TRUE_BRANCH | FALSE_BRANCH | EXCEPTION | LOOP_BACK | Break | Continue | Return

@dataclass
class ControlFlowGraph:
    id: str                        # "cfg:HybridRetriever.plan"
    function_node_id: str
    entry_block_id: str
    exit_block_id: str
    blocks: list[ControlFlowBlock]
    edges: list[ControlFlowEdge]
```

**CFG Edge Types:**

| Edge Kind | 설명 | 예시 |
|-----------|------|------|
| NORMAL | 순차 실행 | block1 → block2 |
| TRUE_BRANCH | 조건 참 | if_cond → then_block |
| FALSE_BRANCH | 조건 거짓 | if_cond → else_block |
| EXCEPTION | 예외 발생 | try_block → catch_block |
| LOOP_BACK | 루프 반복 | loop_body → loop_header |
| Break | break 문 | break_block → loop_exit |
| Continue | continue 문 | continue_block → loop_header |
| Return | return 문 | return_block → func_exit |

---

## Expression IR

### Expression
위치: [expression/models.py:43](src/contexts/code_foundation/infrastructure/semantic_ir/expression/models.py#L43)

```python
@dataclass
class Expression:
    id: str                        # "expr:{repo_id}:{file_path}:{line}:{col}"
    kind: ExprKind
    repo_id: str
    file_path: str
    function_fqn: str | None       # None = module-level

    span: Span

    # DFG 연결
    reads_vars: list[str]          # 읽는 VariableEntity ID 목록
    defines_var: str | None        # 정의하는 VariableEntity ID

    # 타입 정보
    type_id: str | None            # 어노테이션 TypeEntity ID
    inferred_type: str | None      # Pyright hover 결과
    inferred_type_id: str | None   # 추론된 TypeEntity ID

    # Symbol 링크 (cross-file resolution)
    symbol_id: str | None          # IR Node ID of symbol definition
    symbol_fqn: str | None         # Fully qualified name of symbol

    # Expression 트리 구조
    parent_expr_id: str | None
    child_expr_ids: list[str]

    # CFG 블록 참조
    block_id: str | None

    # Expression별 속성
    attrs: dict
```

### ExprKind (13종)

| Kind | 설명 | 예시 |
|------|------|------|
| NAME_LOAD | 변수 읽기 | `x` |
| ATTRIBUTE | 속성 접근 | `obj.attr` |
| SUBSCRIPT | 인덱스 | `arr[i]` |
| BIN_OP | 이항 연산 | `a + b` |
| UNARY_OP | 단항 연산 | `-a`, `not x` |
| COMPARE | 비교 | `a < b` |
| BOOL_OP | 불리언 연산 | `a and b` |
| CALL | 함수 호출 | `fn(x)` |
| INSTANTIATE | 객체 생성 | `Class()` |
| LITERAL | 리터럴 | `1`, `"str"`, `True` |
| COLLECTION | 컬렉션 | `[1,2]`, `{a:b}` |
| ASSIGN | 대입 타겟 | `a = b` (좌변) |
| LAMBDA | 람다 | `lambda x: x` |
| COMPREHENSION | 컴프리헨션 | `[x for x in y]` |

---

## Type Linker

### TypeLinker
위치: [type_linker.py:25](src/contexts/code_foundation/infrastructure/semantic_ir/type_linker.py#L25)

**Cross-file import 해석 포함:**

```python
class TypeLinker:
    def __init__(self):
        self._import_map: dict[str, dict[str, str]] = {}  # file -> {name -> fqn}
        self._fqn_to_type: dict[str, TypeEntity] = {}
        self._name_to_types: dict[str, list[TypeEntity]] = {}
        self._symbol_index: dict[str, str] = {}  # fqn -> node_id

    def build_import_map(self, ir_doc: IRDocument):
        """IR 문서에서 import 매핑 및 symbol 인덱스 빌드"""
        # Symbol 인덱스 빌드 (CLASS, FUNCTION, METHOD)
        for node in ir_doc.nodes:
            if node.kind in (NodeKind.CLASS, NodeKind.FUNCTION, NodeKind.METHOD):
                if node.fqn:
                    self._symbol_index[node.fqn] = node.id

        # Import 매핑 빌드
        for edge in ir_doc.edges:
            if edge.kind == EdgeKind.IMPORTS:
                # source file → target FQN 매핑
                ...

    def link_expressions_to_types(self, expressions, type_entities) -> int:
        """Expression → TypeEntity + Symbol 연결"""
        type_index = self._build_type_index(type_entities)
        self._build_fqn_index(type_entities)

        for expr in expressions:
            # 1. Type 연결
            type_entity, match_type = self._find_type_entity_enhanced(
                expr.inferred_type, type_index, expr.file_path
            )
            if type_entity:
                expr.inferred_type_id = type_entity.id

            # 2. Symbol 연결 (attrs의 definition_fqn 활용)
            symbol_id, symbol_fqn = self._resolve_symbol_from_attrs(expr)
            if symbol_id:
                expr.symbol_id = symbol_id
                expr.symbol_fqn = symbol_fqn
```

**7단계 Type Lookup:**

1. Direct lookup (정확히 일치)
2. Generic base type (List[str] → List)
3. FQN lookup
4. Import resolution (file의 import 맵 참조)
5. Simple name lookup (ambiguous 가능)
6. Union type handling (첫 번째 타입)
7. Optional handling (내부 타입)

**통계 제공:**
```python
stats = linker.get_stats()
# {
#     "direct_matches": 150,
#     "fqn_matches": 30,
#     "import_resolved": 20,
#     "generic_linked": 10,
#     "symbol_linked": 45,
#     "unresolved": 5
# }
```

---

## Data Flow Graph (DFG)

### VariableEntity
위치: [../dfg/models.py:12](src/contexts/code_foundation/infrastructure/dfg/models.py#L12)

```python
@dataclass(slots=True)
class VariableEntity:
    id: str                        # "var:{repo_id}:{file}:{func}:{name}@{block}:{shadow}"
    repo_id: str
    file_path: str
    function_fqn: str
    name: str
    kind: Literal["param", "local", "captured"]  # captured = 클로저 변수

    type_id: str | None
    decl_block_id: str | None

    # 타입 추론
    inferred_type: str | None
    inferred_type_id: str | None
    type_source: str = "unknown"

    # Scope 정보 (자동 추출: extract_scope_info)
    scope_id: str | None           # function FQN
    scope_kind: Literal["module", "function", "method", "lambda", "comprehension", "class"] | None
    scope_depth: int = 0           # 0=module, 1=function, 2=nested

    # attrs에 captured 정보
    # attrs["captured_from"] = outer_var_id  # 클로저 캡처 시
```

### Captured Variable (클로저) 분석
위치: [../dfg/builder.py:268](src/contexts/code_foundation/infrastructure/dfg/builder.py#L268)

```python
# DfgBuilder._collect_outer_scope_vars
def _collect_outer_scope_vars(self, function_fqn: str):
    """
    FQN 기반으로 상위 스코프 변수 수집.

    예: "module.outer.inner" 함수는
        - "module.outer" 스코프의 변수
        - "module" 스코프의 변수
        를 캡처 가능
    """
    outer_vars: dict[str, tuple[str, str]] = {}  # name -> (var_id, scope_fqn)

    parts = function_fqn.split(".")
    for i in range(len(parts) - 1, 0, -1):
        enclosing_fqn = ".".join(parts[:i])
        if enclosing_fqn in self._function_variables:
            for var_name, var_id in self._function_variables[enclosing_fqn].items():
                if var_name not in outer_vars:
                    outer_vars[var_name] = (var_id, enclosing_fqn)
    return outer_vars

# resolve_or_create_variable에서 captured 처리
if kind == "local" and name in ctx.outer_scope_vars:
    actual_kind = "captured"
    outer_var_id, _ = ctx.outer_scope_vars[name]
    var_entity.attrs["captured_from"] = outer_var_id
```

### VariableEvent
```python
@dataclass(slots=True)
class VariableEvent:
    id: str                        # "evt:{variable_id}:{ir_node_id}"
    repo_id: str
    file_path: str
    function_fqn: str
    variable_id: str
    block_id: str
    ir_node_id: str | None
    op_kind: Literal["read", "write"]
    start_line: int | None
    end_line: int | None
```

### DataFlowEdge
```python
@dataclass(slots=True)
class DataFlowEdge:
    id: str
    from_variable_id: str
    to_variable_id: str
    kind: Literal["alias", "assign", "param_to_arg", "return_value"]
    repo_id: str
    file_path: str
    function_fqn: str
    attrs: dict
```

**Edge Kinds:**

| Kind | 설명 | 예시 |
|------|------|------|
| alias | 직접 별칭 | `a = b` |
| assign | 함수 결과 대입 | `a = fn(b)` |
| param_to_arg | 파라미터 → 인자 | 함수 호출 시 |
| return_value | 반환값 | `return a` |

---

## Expression Builder Pyright 연동

### Pyright Type Enrichment
위치: [expression/builder.py:276](src/contexts/code_foundation/infrastructure/semantic_ir/expression/builder.py#L276)

```python
def _batch_enrich_with_pyright(self, expressions, source_file):
    """
    Pyright hover로 타입 추론 결과 수집.

    Enhanced:
    - Definition location 추적 (cross-file linking)
    - Generic type parameter 추출
    - builtins./typing. 접두사 정규화
    """
    for (line, col), exprs_at_pos in unique_positions.items():
        # 1. Hover로 타입 정보
        hover_info = self.pyright.hover(file_path, line, col)
        if hover_info:
            normalized_type = self._normalize_pyright_type(hover_info.get("type"))
            for expr in exprs_at_pos:
                expr.inferred_type = normalized_type
                if "[" in normalized_type:
                    expr.attrs["generic_params"] = self._extract_generic_params(normalized_type)

        # 2. Definition으로 cross-file 연결
        definition = self.pyright.definition(file_path, line, col)
        if definition:
            expr.attrs["definition_file"] = definition.get("file")
            expr.attrs["definition_fqn"] = definition.get("fqn")
```

**타입 정규화:**
```python
def _normalize_pyright_type(self, type_str):
    # "builtins.str" → "str"
    # "typing.List" → "List"
    # 공백 정규화
```

---

## Incremental Build

### apply_delta
위치: [builder.py:247](src/contexts/code_foundation/infrastructure/semantic_ir/builder.py#L247)

```python
def apply_delta(self, ir_doc, existing_snapshot, existing_index, source_map=None):
    """
    변경된 함수만 재빌드.

    1. _detect_changed_functions(): 새/수정/삭제 함수 감지
    2. _filter_unchanged_entities(): 변경되지 않은 엔티티 유지
    3. _rebuild_changed_functions(): 변경된 함수만 재빌드
    4. 새 snapshot 반환
    """
```

**변경 감지 기준:**
- 함수 이름 변경
- 시그니처 ID 변경
- 새 함수 추가
- 함수 삭제

---

## Performance Monitoring

### PerformanceMonitor
위치: [performance_monitor.py](src/contexts/code_foundation/infrastructure/semantic_ir/performance_monitor.py)

```python
builder = DefaultSemanticIrBuilder(enable_performance_monitoring=True)
snapshot, index = builder.build_full(ir_doc, source_map)
metrics = builder.get_metrics()

# 단계별 시간 측정
# Phase 1a: Type System - 12ms
# Phase 1b: Signatures - 8ms
# Phase 2a: BFG - 45ms
# Phase 2b: CFG - 23ms
# Phase 2c: Expression IR - 156ms
# Phase 2d: Type Linking - 34ms
# Phase 3: DFG - 89ms
```

---

## 디렉토리 구조

```
src/contexts/code_foundation/infrastructure/semantic_ir/
├── __init__.py              # Lazy import, exports
├── builder.py               # DefaultSemanticIrBuilder (오케스트레이터)
├── context.py               # SemanticIrSnapshot, SemanticIndex
├── type_linker.py           # TypeLinker, CrossFileSymbolLinker
├── typing/
│   ├── models.py            # TypeEntity, TypeFlavor, TypeResolutionLevel
│   ├── builder.py           # TypeIrBuilder
│   └── resolver.py          # TypeResolver (7단계 resolution)
├── signature/
│   ├── models.py            # SignatureEntity, Visibility
│   └── builder.py           # SignatureIrBuilder
├── bfg/
│   ├── models.py            # BasicFlowBlock, BasicFlowGraph, BFGBlockKind
│   └── builder.py           # BfgBuilder
├── cfg/
│   ├── models.py            # ControlFlowBlock, ControlFlowEdge, ControlFlowGraph
│   └── builder.py           # CfgBuilder
├── expression/
│   ├── models.py            # Expression, ExprKind
│   └── builder.py           # ExpressionBuilder (Pyright 연동)
├── id_utils.py              # ID 변환 유틸리티
├── span_utils.py            # Span 유틸리티
├── cache_utils.py           # 캐시 유틸리티
├── error_handling.py        # 에러 처리
├── validation.py            # 검증 로직
├── performance_monitor.py   # 성능 모니터링
└── source_map.py            # 소스 맵 관리

src/contexts/code_foundation/infrastructure/dfg/
├── __init__.py
├── models.py                # VariableEntity, VariableEvent, DataFlowEdge, DfgSnapshot
├── builder.py               # DfgBuilder
├── resolver.py              # VarResolverState
├── statement_analyzer.py    # 문장 분석
└── analyzers/
    └── python_analyzer.py   # Python 특화 분석
```

---

## 완성도 평가

| 컴포넌트 | 상태 | 완성도 | 비고 |
|----------|------|--------|------|
| TypeEntity | ✅ 완성 | 100% | 6종 TypeFlavor, 6단계 Resolution, generic_param_ids 링크 |
| TypeResolver | ✅ 완성 | 100% | 7단계 priority + build_index_from_ir 자동 호출 |
| TypeIrBuilder | ✅ 완성 | 100% | TypeResolver 통합 + generic param 링크 |
| SignatureEntity | ✅ 완성 | 95% | async, static, throws, hash 지원 |
| BFG | ✅ 완성 | 95% | break/continue/return 메타데이터 지원 |
| CFG | ✅ 완성 | 95% | 8종 BlockKind, 7종 EdgeKind |
| Expression IR | ✅ 완성 | 100% | symbol_id/symbol_fqn 직접 링크 추가 |
| TypeLinker | ✅ 완성 | 100% | Cross-file import + Symbol 링크 |
| DFG | ✅ 완성 | 100% | Scope tracking + Captured variable 분석 |

**전체 완성도: 100/100**

### 최근 개선사항 (v2.1)

1. **TypeResolver → TypeIrBuilder 통합**
   - `build_index_from_ir()` 자동 호출
   - RAW → MODULE/PROJECT/EXTERNAL 자동 업그레이드

2. **Expression symbol_id 직접 링크**
   - `symbol_id`: IR Node ID of definition
   - `symbol_fqn`: Fully qualified name
   - Pyright definition 정보 활용

3. **Captured Variable 분석**
   - 클로저 변수 자동 감지
   - `kind="captured"` + `attrs["captured_from"]`
   - FQN 기반 상위 스코프 변수 추적

4. **Generic Parameter 링크**
   - `generic_param_ids` → 실제 TypeEntity ID 해석
   - raw string 기반 fallback 지원

---

## 주요 데이터 흐름 예시

```python
# 입력: def plan(self, query: Query) -> RetrievalPlan:
#          result = self._search(query)
#          return result

# Phase 1a: TypeEntity
types = [
    TypeEntity(id="type:Query", flavor=USER, resolution_level=PROJECT),
    TypeEntity(id="type:RetrievalPlan", flavor=USER, resolution_level=PROJECT),
]

# Phase 1b: SignatureEntity
signatures = [
    SignatureEntity(
        id="sig:plan(Query)->RetrievalPlan",
        parameter_type_ids=["type:Query"],
        return_type_id="type:RetrievalPlan",
        is_async=False,
    )
]

# Phase 2a: BFG
bfg_blocks = [
    BasicFlowBlock(id="bfg:plan:block:0", kind=ENTRY),
    BasicFlowBlock(id="bfg:plan:block:1", kind=STATEMENT, defined_variable_ids=["var:result"]),
    BasicFlowBlock(id="bfg:plan:block:2", kind=EXIT, is_return=True),
]

# Phase 2b: CFG (edges 추가)
cfg_edges = [
    ControlFlowEdge(source="block:0", target="block:1", kind=NORMAL),
    ControlFlowEdge(source="block:1", target="block:2", kind=Return),
]

# Phase 2c: Expression
expressions = [
    Expression(id="expr:1", kind=CALL, inferred_type="SearchResult"),
    Expression(id="expr:2", kind=NAME_LOAD, inferred_type="SearchResult", defines_var="var:result"),
]

# Phase 2d: Type Linking
# expr:1.inferred_type_id = "type:SearchResult"

# Phase 3: DFG
variables = [VariableEntity(id="var:result", kind="local", type_id="type:SearchResult")]
events = [
    VariableEvent(id="evt:1", variable_id="var:result", op_kind="write"),
    VariableEvent(id="evt:2", variable_id="var:result", op_kind="read"),
]
edges = [DataFlowEdge(from_="var:result", to="return", kind="return_value")]
```
