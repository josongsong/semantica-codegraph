# IR & HCG 전체 구조 문서

## 목차

0. [파싱 레이어 (최하위)](#0-파싱-레이어-최하위)
   - Tree-sitter Parsing
   - IRGenerator (언어별)
1. [Structural IR (기본 레이어)](#1-structural-ir-기본-레이어)
   - IRDocument, Node (20종), Edge (23종), Span
   - Occurrence (SCIP), Diagnostic, PackageMetadata, UnifiedSymbol
2. [Semantic IR (의미론 레이어)](#2-semantic-ir-의미론-레이어)
   - Type (TypeFlavor, TypeResolutionLevel)
   - Signature (Visibility)
   - CFG (CFGBlockKind, CFGEdgeKind)
   - BFG (BFGBlockKind, Async/Generator 지원)
   - DFG (VariableEntity, VariableEvent, DataFlowEdge)
   - Expression (ExprKind 14종)
   - Interprocedural Data Flow
3. [Advanced Analysis (고급 분석 레이어)](#3-advanced-analysis-고급-분석-레이어)
   - PDG (DependencyType), Slicing, Taint Analysis
4. [Graph Layer & HCG (통합 그래프 레이어)](#4-graph-layer--hcg-통합-그래프-레이어)
   - GraphDocument, GraphNode (21종), GraphEdge (20종), GraphIndex
   - HCGAdapter
5. [생성 과정 (9-Layer Pipeline)](#5-생성-과정-9-layer-pipeline)
6. [Graph Layer 생성](#6-graph-layer-생성-ir--graphdocument)
7. [전체 데이터 플로우](#7-전체-데이터-플로우)
8. [관계 그래프 예시](#8-관계-그래프-예시)
9. [쿼리 API](#9-쿼리-api)
10. [성능 특성](#10-성능-특성)
11. [증분 업데이트](#11-증분-업데이트)
12. [파일 위치 요약](#12-파일-위치-요약)
13. [핵심 개념 정리](#13-핵심-개념-정리)
14. [주요 특징 및 차별점](#14-주요-특징-및-차별점)
15. [사용 예시](#15-사용-예시)
16. [제한사항 및 향후 계획](#16-제한사항-및-향후-계획)
17. [SCIP 호환성 상세](#17-scip-호환성-상세)
18. [Query DSL 상세](#18-query-dsl-상세)
19. [증분 업데이트 상세](#19-증분-업데이트-상세)
20. [Async/Generator 지원 상세](#20-asyncgenerator-지원-상세)

---

## 개요

CodeGraph는 코드를 다층 구조의 IR(Intermediate Representation)로 변환하여 분석합니다.
전체 구조는 **5개 메인 레이어**로 구성됩니다:

0. **Parsing Layer** - Tree-sitter 파싱 및 언어별 IR 생성 (Generator)
1. **Structural IR** - AST 기반 구조적 표현 (Node, Edge)
2. **Semantic IR** - 의미론적 표현 (Type, Signature, CFG, BFG, DFG, Expression)
3. **Advanced Analysis** - 고급 분석 (PDG, Taint, Slicing)
4. **Graph Layer (HCG)** - 헤테로지니어스 코드 그래프 (통합 그래프)

추가로 **보조 레이어**들이 있습니다:
- **Occurrence Layer** - SCIP 호환 심볼 추적
- **Cross-file Layer** - 프로젝트 전체 컨텍스트 (GlobalContext)
- **Retrieval Layer** - 검색 최적화 인덱스
- **Diagnostics Layer** - LSP 에러/경고
- **Package Layer** - 외부 의존성

---

## 0. 파싱 레이어 (최하위)

### Tree-sitter Parsing

모든 IR 생성의 시작점입니다.

**위치**: `src/contexts/code_foundation/infrastructure/parsing/`

### ParserRegistry

```python
class ParserRegistry:
    """
    Tree-sitter 언어별 파서 레지스트리

    지원 언어:
    - Python
    - TypeScript/JavaScript/TSX
    - Go
    - Java/Kotlin
    - Rust
    - C/C++
    """

    def get_parser(self, language: str) -> Parser | None:
        """언어별 파서 반환"""

    def detect_language(self, file_path: str) -> str | None:
        """파일 확장자로 언어 감지"""
```

### IRGenerator (언어별 구현)

각 언어마다 Tree-sitter AST → IR 변환을 담당합니다.

**위치**:
- `src/contexts/code_foundation/infrastructure/generators/base.py` (기본 클래스)
- `src/contexts/code_foundation/infrastructure/generators/python_generator.py`
- `src/contexts/code_foundation/infrastructure/generators/typescript_generator.py`
- `src/contexts/code_foundation/infrastructure/generators/java_generator.py`

```python
class IRGenerator(ABC):
    """
    언어별 IR 생성기 베이스 클래스
    """

    @abstractmethod
    def generate(self, source: SourceFile, snapshot_id: str) -> IRDocument:
        """
        소스 파일 → IRDocument 변환

        프로세스:
        1. Tree-sitter로 AST 생성
        2. AST 순회하며 Node/Edge 생성
        3. Span, FQN, 관계 추출
        4. IRDocument 반환
        """
        pass

    def generate_content_hash(self, text: str) -> str:
        """SHA256 해시 생성 (증분 업데이트용)"""

    def calculate_cyclomatic_complexity(self, node) -> int:
        """순환 복잡도 계산"""
```

**지원 언어별 Generator**:
- `PythonIRGenerator`: Python AST → IR
- `TypeScriptIRGenerator`: TypeScript/JavaScript AST → IR
- `JavaIRGenerator`: Java AST → IR

**변환 예시**:
```python
# 입력 (Python 소스)
class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b

# Tree-sitter AST → IR
generator = PythonIRGenerator(repo_id="myproject")
ir_doc = generator.generate(source_file, snapshot_id)

# 출력 (IRDocument)
ir_doc.nodes = [
    Node(id="class:Calculator", kind=CLASS, ...),
    Node(id="method:Calculator.add", kind=METHOD, ...),
    Node(id="param:Calculator.add.a", kind=VARIABLE, ...),
    Node(id="param:Calculator.add.b", kind=VARIABLE, ...),
]
ir_doc.edges = [
    Edge(kind=CONTAINS, source="class:Calculator", target="method:Calculator.add"),
    ...
]
```

---

## 1. Structural IR (기본 레이어)

### 위치
- `src/contexts/code_foundation/infrastructure/ir/models/core.py`
- `src/contexts/code_foundation/infrastructure/ir/models/document.py`

### IRDocument (v2.1)

전체 IR의 최상위 컨테이너입니다.

```python
@dataclass
class IRDocument:
    # [Required] Identity
    repo_id: str
    snapshot_id: str
    schema_version: str = "2.1"

    # [Required] Structural IR
    nodes: list[Node]
    edges: list[Edge]

    # [Optional] Semantic IR
    types: list[TypeEntity]
    signatures: list[SignatureEntity]
    cfgs: list[ControlFlowGraph]
    cfg_blocks: list[ControlFlowBlock]
    cfg_edges: list[ControlFlowEdge]
    bfg_graphs: list[BasicFlowGraph]
    bfg_blocks: list[BasicFlowBlock]
    dfg_snapshot: DfgSnapshot | None
    expressions: list[Expression]
    interprocedural_edges: list[InterproceduralDataFlowEdge]

    # [Optional] Occurrence IR (SCIP-compatible)
    occurrences: list[Occurrence]

    # [Optional] Diagnostics
    diagnostics: list[Diagnostic]

    # [Optional] Package Metadata
    packages: list[PackageMetadata]

    # [Optional] Cross-Language Symbols
    unified_symbols: list[UnifiedSymbol]

    # [Advanced] PDG, Slicing, Taint (v2.1)
    pdg_nodes: list[PDGNode]
    pdg_edges: list[PDGEdge]
    taint_findings: list[TaintFinding]
```

### Node (노드)

**NodeKind (20종)**:

```python
class NodeKind(str, Enum):
    # Structural (구조)
    FILE = "File"
    MODULE = "Module"
    CLASS = "Class"
    INTERFACE = "Interface"
    ENUM = "Enum"
    TYPE_ALIAS = "TypeAlias"

    # Callable (호출 가능)
    FUNCTION = "Function"
    METHOD = "Method"
    LAMBDA = "Lambda"
    METHOD_REFERENCE = "MethodReference"  # Java 8+ ::

    # Variable (변수)
    VARIABLE = "Variable"
    FIELD = "Field"
    PROPERTY = "Property"
    CONSTANT = "Constant"
    TYPE_PARAMETER = "TypeParameter"  # Generic <T>

    # Import/Export
    IMPORT = "Import"
    EXPORT = "Export"

    # Control Flow
    BLOCK = "Block"
    CONDITION = "Condition"
    LOOP = "Loop"
    TRY_CATCH = "TryCatch"
```

**Node 구조**:

```python
@dataclass
class Node:
    # [Required] Identity
    id: str                    # logical_id (human-readable)
    kind: NodeKind
    fqn: str                   # Fully Qualified Name

    # [Required] Location
    file_path: str             # Relative to repo root
    span: Span                 # 소스 위치
    language: str              # python, typescript, java, ...

    # [Optional] Identity (tracking)
    stable_id: str | None      # Hash-based stable ID
    content_hash: str | None   # sha256 of code

    # [Optional] Structure
    name: str | None
    module_path: str | None
    parent_id: str | None
    body_span: Span | None

    # [Optional] Metadata
    docstring: str | None
    role: str | None           # controller, service, repo, dto, ...
    is_test_file: bool | None

    # [Optional] Type/Signature refs
    signature_id: str | None
    declared_type_id: str | None

    # [Optional] Control flow
    control_flow_summary: ControlFlowSummary | None

    # [Optional] Language-specific
    attrs: dict[str, Any]
```

### Edge (엣지)

**EdgeKind (23종)**:

```python
class EdgeKind(str, Enum):
    # Structure/Definition
    CONTAINS = "CONTAINS"      # File→Class, Class→Method
    DEFINES = "DEFINES"        # Scope→Symbol

    # Call/Usage
    CALLS = "CALLS"            # Function/method call
    READS = "READS"            # Variable/field read
    WRITES = "WRITES"          # Variable/field write
    REFERENCES = "REFERENCES"  # Type/symbol reference

    # Type/Inheritance
    IMPORTS = "IMPORTS"
    INHERITS = "INHERITS"
    IMPLEMENTS = "IMPLEMENTS"

    # Pattern
    DECORATES = "DECORATES"
    INSTANTIATES = "INSTANTIATES"
    OVERRIDES = "OVERRIDES"

    # Resource/State
    USES = "USES"
    READS_RESOURCE = "READS_RESOURCE"
    WRITES_RESOURCE = "WRITES_RESOURCE"

    # Exception/Control
    THROWS = "THROWS"
    ROUTE_TO = "ROUTE_TO"
    USES_REPO = "USES_REPO"

    # Closure
    CAPTURES = "CAPTURES"      # Lambda → Variable
    ACCESSES = "ACCESSES"      # Anonymous class → Outer field
    SHADOWS = "SHADOWS"        # Inner → Outer (name collision)
```

**Edge 구조**:

```python
@dataclass
class Edge:
    id: str              # e.g., "edge:call:plan→_search_vector@1"
    kind: EdgeKind
    source_id: str       # Caller, Referrer, Owner
    target_id: str       # Callee, Referenced, Imported
    span: Span | None
    attrs: dict[str, Any]
```

### Span (위치 정보)

```python
@dataclass
class Span:
    start_line: int
    start_col: int
    end_line: int
    end_col: int
```

### Occurrence (SCIP-compatible)

**위치**: `src/contexts/code_foundation/infrastructure/ir/models/occurrence.py`

코드에서 심볼이 사용되는 위치를 추적합니다 (SCIP 표준 호환).

**SymbolRole (Bitflags)**:

```python
class SymbolRole(IntFlag):
    """
    SCIP-compatible symbol roles (비트플래그)

    여러 역할 조합 가능: DEFINITION | TEST
    """

    NONE = 0

    # Primary roles
    DEFINITION = 1          # 정의 (class Foo, def bar)
    IMPORT = 2              # Import (from X import Y)
    WRITE_ACCESS = 4        # 쓰기 (x = 10, x += 1)
    READ_ACCESS = 8         # 읽기 (y = x, foo(x))

    # Metadata roles
    GENERATED = 16          # 생성된 코드 (protobuf, ORM)
    TEST = 32               # 테스트 코드
    FORWARD_DEFINITION = 64 # Forward 선언 (type hints)
```

**Occurrence**:

```python
@dataclass
class Occurrence:
    """
    심볼의 단일 사용 위치

    정의, 참조, 읽기, 쓰기 등 모든 심볼 사용 추적
    """

    id: str                    # occ:def:class:Calculator
    symbol_id: str             # class:Calculator
    span: Span                 # 소스 위치
    roles: SymbolRole          # DEFINITION | READ_ACCESS
    file_path: str

    # Retrieval optimization
    importance_score: float    # 0.0-1.0 (검색 랭킹용)
    parent_symbol_id: str | None  # 부모 심볼 (스코프)

    # Context
    enclosing_range: Span | None  # 감싸는 범위
    syntax_kind: str | None       # AST node type

    attrs: dict[str, Any]
```

**OccurrenceIndex** (빠른 조회):

```python
@dataclass
class OccurrenceIndex:
    """
    Occurrence 빠른 조회를 위한 인덱스

    O(1) 조회:
    - symbol_id → occurrences
    - file_path → occurrences
    - role → occurrences
    """

    # symbol_id → occurrences
    by_symbol: dict[str, list[Occurrence]]

    # file_path → occurrences
    by_file: dict[str, list[Occurrence]]

    # role → occurrences
    by_role: dict[SymbolRole, list[Occurrence]]

    # importance ranking
    by_importance: list[Occurrence]  # Sorted by score

    def get_references(self, symbol_id: str) -> list[Occurrence]:
        """모든 참조 찾기 (정의 + 사용)"""

    def get_definitions(self, symbol_id: str) -> list[Occurrence]:
        """정의만 찾기"""

    def get_usages(self, symbol_id: str, include_definitions=False) -> list[Occurrence]:
        """사용만 찾기 (정의 제외 가능)"""
```

### Diagnostic (LSP Errors/Warnings)

**위치**: `src/contexts/code_foundation/infrastructure/ir/models/diagnostic.py`

LSP 서버나 linter에서 발생한 에러/경고를 추적합니다.

```python
class DiagnosticSeverity(IntEnum):
    ERROR = 1        # 컴파일/타입 에러
    WARNING = 2      # 잠재적 이슈
    INFORMATION = 3  # 정보성 메시지
    HINT = 4         # 제안

@dataclass
class Diagnostic:
    """
    단일 진단 메시지 (SCIP-compatible)

    소스: LSP (Pyright, tsserver), Linter (pylint, eslint)
    """

    id: str
    file_path: str
    span: Span
    severity: DiagnosticSeverity
    message: str

    # Source info
    source: str              # "pyright", "eslint", "mypy"
    code: str | int | None   # Error code (e.g., "E501", "TS2322")

    # Related locations
    related_locations: list[tuple[Span, str]]

    # Tags
    tags: list[str]          # ["deprecated", "unnecessary"]

    attrs: dict[str, Any]
```

**DiagnosticIndex**:

```python
@dataclass
class DiagnosticIndex:
    """진단 메시지 인덱스"""

    by_file: dict[str, list[Diagnostic]]
    by_severity: dict[DiagnosticSeverity, list[Diagnostic]]
    by_source: dict[str, list[Diagnostic]]
```

### UnifiedSymbol (Cross-Language)

**위치**: `src/contexts/code_foundation/domain/models.py`

언어 중립적 심볼 표현으로, SCIP 표준을 완전히 준수합니다.

```python
@dataclass
class UnifiedSymbol:
    """
    언어 중립적 symbol 표현 (SCIP 완전 호환)

    SCIP Format:
    scip-typescript npm package 1.0.0 src/`foo.ts`/`bar`().
    │    │          │   │       │     │   │       │    │
    │    │          │   │       │     │   │       │    ╰── Suffix
    │    │          │   │       │     │   │       ╰─────── Symbol
    │    │          │   │       │     │   ╰───────────── File
    │    │          │   │       │     ╰─────────────── Root
    │    │          │   │       ╰───────────────────── Version
    │    │          │   ╰───────────────────────────── Name
    │    │          ╰───────────────────────────────── Manager
    │    ╰──────────────────────────────────────────── Scheme
    """

    # Core Identity (SCIP required)
    scheme: str              # "python", "java", "typescript"
    manager: str             # "pypi", "maven", "npm"
    package: str             # Package name
    version: str             # Package version

    # Path (SCIP required)
    root: str                # Project root or package root
    file_path: str           # Relative file path

    # Symbol (SCIP required)
    descriptor: str          # Symbol descriptor (class#, method()., etc.)

    # Language-specific (backward compat)
    language_fqn: str        # 원본 FQN
    language_kind: str       # 원본 kind

    # Resolved Info
    signature: str | None    # Canonical signature
    type_info: str | None    # Type information
    generic_params: list[str] | None  # Generic parameters

    # Location
    start_line: int | None
    end_line: int | None
    start_column: int | None
    end_column: int | None

    def to_scip_descriptor(self) -> str:
        """
        완전한 SCIP descriptor 생성

        Examples:
            scip-python pypi requests 2.31.0 /`__init__.py`/`get`().
            scip-java maven com.example 1.0.0 src/`Main.java`/`MyClass#`
            scip-typescript npm @types/node 18.0.0 /`fs.d.ts`/`readFile`().
        """

    def matches(self, other: UnifiedSymbol) -> bool:
        """
        Cross-language matching

        Same descriptor + compatible types
        """

    @classmethod
    def from_simple(
        cls,
        scheme: str,
        package: str,
        descriptor: str,
        language_fqn: str,
        language_kind: str,
        version: str = "unknown",
        file_path: str = "",
    ) -> UnifiedSymbol:
        """Simplified constructor (backward compat)"""
```

**활용 예시**:

```python
# Python symbol
python_sym = UnifiedSymbol(
    scheme="python",
    manager="pypi",
    package="myproject",
    version="1.0.0",
    root="/",
    file_path="src/calc.py",
    descriptor="Calculator#add().",
    language_fqn="calc.Calculator.add",
    language_kind="method",
)

# SCIP descriptor 생성
scip = python_sym.to_scip_descriptor()
# → "scip-python pypi myproject 1.0.0 / `src/calc.py` `Calculator#add().`"

# Cross-language matching
java_sym = UnifiedSymbol(...)
if python_sym.matches(java_sym):
    print("Compatible symbols across languages!")
```

### PackageMetadata (External Dependencies)

**위치**: `src/contexts/code_foundation/infrastructure/ir/models/package.py`

외부 패키지 의존성 정보를 추적합니다.

```python
@dataclass
class PackageMetadata:
    """
    외부 패키지 메타데이터 (SCIP-compatible)

    Python: pip (requests, numpy)
    TypeScript: npm (@types/node)
    Go: go modules
    Java: Maven
    """

    name: str                # "requests", "@types/node"
    version: str             # "2.31.0", "^16.0.0"
    manager: str             # "pip", "npm", "go", "maven"

    # Optional metadata
    registry: str | None     # pypi.org, npmjs.com
    license: str | None      # MIT, Apache-2.0
    homepage: str | None
    description: str | None

    # Import mapping (심볼 해석용)
    import_map: dict[str, str]

    # Dependencies
    dependencies: list[str]  # Transitive deps

    attrs: dict[str, Any]

    def get_moniker(self) -> str:
        """SCIP-style moniker: pypi:requests@2.31.0"""
```

**PackageIndex**:

```python
@dataclass
class PackageIndex:
    """패키지 인덱스"""

    by_name: dict[str, PackageMetadata]
    by_manager: dict[str, list[PackageMetadata]]
    import_to_package: dict[str, str]  # import name → package name
```

---

## 2. Semantic IR (의미론 레이어)

### 위치
- `src/contexts/code_foundation/infrastructure/semantic_ir/`

### SemanticIrSnapshot

```python
@dataclass
class SemanticIrSnapshot:
    # Phase 1: Type + Signature
    types: list[TypeEntity]
    signatures: list[SignatureEntity]

    # Phase 2a: BFG (Basic Flow Graph - blocks without edges)
    bfg_graphs: list[BasicFlowGraph]
    bfg_blocks: list[BasicFlowBlock]

    # Phase 2b: CFG (Control Flow Graph - blocks with edges)
    cfg_graphs: list[ControlFlowGraph]
    cfg_blocks: list[ControlFlowBlock]
    cfg_edges: list[ControlFlowEdge]

    # Phase 2c: Expression IR
    expressions: list[Expression]

    # Phase 3: DFG (Data Flow Graph)
    dfg_snapshot: DfgSnapshot | None
```

### 2.1. Type IR

**위치**: `src/contexts/code_foundation/infrastructure/semantic_ir/typing/models.py`

**TypeFlavor** (타입 분류):

```python
class TypeFlavor(str, Enum):
    """타입 분류"""

    PRIMITIVE = "primitive"    # int, str, bool, float
    BUILTIN = "builtin"        # list, dict, set, tuple
    USER = "user"              # 사용자 정의 클래스/타입
    EXTERNAL = "external"      # 외부 라이브러리 타입
    TYPEVAR = "typevar"        # Generic type variable (T)
    GENERIC = "generic"        # Generic types (List[T])
```

**TypeResolutionLevel** (타입 해석 단계):

```python
class TypeResolutionLevel(str, Enum):
    """타입 해석 단계 (점진적)"""

    RAW = "raw"                # Raw string only
    BUILTIN = "builtin"        # Built-in types 해석됨
    LOCAL = "local"            # 같은 파일 정의
    MODULE = "module"          # 같은 패키지 imports
    PROJECT = "project"        # 전체 프로젝트
    EXTERNAL = "external"      # 외부 의존성
```

**TypeEntity**:

```python
@dataclass(slots=True)
class TypeEntity:
    """
    타입 시스템 표현 (Node와 분리)

    타입 해석은 점진적:
    - Phase 1: raw_only
    - Phase 2: builtin + local + module
    - Phase 3: project
    - Phase 4: external
    """

    # [Required] Identity
    id: str                    # type:RetrievalPlan, type:List[Candidate]
    raw: str                   # 코드에 나타난 그대로

    # [Required] Classification
    flavor: TypeFlavor
    is_nullable: bool
    resolution_level: TypeResolutionLevel

    # [Optional] Resolution
    resolved_target: str | None  # Node.id (Class/Interface/TypeAlias)

    # [Optional] Generics
    generic_param_ids: list[str]  # TypeEntity.id list
```

**TypeIndex** (Structural ↔ Type mapping):

```python
@dataclass
class TypeIndex:
    function_to_param_type_ids: dict[str, list[str]]
    function_to_return_type_id: dict[str, str | None]
    variable_to_type_id: dict[str, str | None]
```

### 2.2. Signature IR

**위치**: `src/contexts/code_foundation/infrastructure/semantic_ir/signature/models.py`

**Visibility** (접근 제어):

```python
class Visibility(str, Enum):
    """접근 제어 (언어별 매핑)"""

    PUBLIC = "public"
    PROTECTED = "protected"
    PRIVATE = "private"
    INTERNAL = "internal"
```

**SignatureEntity**:

```python
@dataclass
class SignatureEntity:
    """
    함수/메서드 시그니처 (인터페이스 변경 감지용 별도 엔티티)
    """

    # [Required] Identity
    id: str                    # sig:HybridRetriever.plan(Query,int)->RetrievalPlan
    owner_node_id: str         # Node.id (Function/Method/Lambda)
    name: str
    raw: str                   # Signature string

    # [Required] Parameters/Return
    parameter_type_ids: list[str]  # TypeEntity.id list
    return_type_id: str | None     # TypeEntity.id

    # [Required] Modifiers
    is_async: bool = False
    is_static: bool = False

    # [Optional] Metadata
    visibility: Visibility | None
    throws_type_ids: list[str]     # Exception TypeEntity.id list
    signature_hash: str | None     # 시그니처 해시 (변경 감지)
    raw_body_hash: str | None      # 함수 본문 해시 (body_sha256:...)
```

**SignatureIndex**:

```python
@dataclass
class SignatureIndex:
    function_to_signature: dict[str, str]  # Function node_id → Signature ID
```

### 2.3. CFG (Control Flow Graph)

**위치**: `src/contexts/code_foundation/infrastructure/semantic_ir/cfg/models.py`

**CFGBlockKind** (블록 종류):

```python
class CFGBlockKind(str, Enum):
    """Control Flow Graph 블록 타입"""

    ENTRY = "Entry"            # 함수 진입점
    EXIT = "Exit"              # 함수 종료점
    BLOCK = "Block"            # 일반 블록
    CONDITION = "Condition"    # if/elif 조건
    LOOP_HEADER = "LoopHeader" # for/while 헤더
    TRY = "Try"                # try 블록
    CATCH = "Catch"            # except/catch 블록
    FINALLY = "Finally"        # finally 블록

    # Async/await support
    SUSPEND = "Suspend"        # await 중단점
    RESUME = "Resume"          # await 재개점

    # Generator/Coroutine support
    DISPATCHER = "Dispatcher"  # Generator 상태 라우터
```

**CFGEdgeKind** (엣지 종류):

```python
class CFGEdgeKind(str, Enum):
    """Control Flow Graph 엣지 타입"""

    NORMAL = "NORMAL"          # 순차 실행
    TRUE_BRANCH = "TRUE_BRANCH"    # 조건 참
    FALSE_BRANCH = "FALSE_BRANCH"  # 조건 거짓
    EXCEPTION = "EXCEPTION"    # 예외 발생
    LOOP_BACK = "LOOP_BACK"    # 루프 백엣지

    # Control flow statements
    BREAK = "Break"            # break 문 (루프 탈출)
    CONTINUE = "Continue"      # continue 문 (루프 헤더로)
    RETURN = "Return"          # return 문 (함수 종료로)
```

**ControlFlowBlock**:

```python
@dataclass
class ControlFlowBlock:
    """CFG 기본 블록"""

    # [Required] Identity
    id: str                    # cfg:plan:block:1
    kind: CFGBlockKind
    function_node_id: str      # Node.id (Function/Method)

    # [Optional] Location
    span: Span | None

    # [Optional] Data Flow (DFG 연결)
    defined_variable_ids: list[str]  # 이 블록에서 정의된 변수들
    used_variable_ids: list[str]     # 이 블록에서 사용된 변수들
```

**ControlFlowEdge**:

```python
@dataclass
class ControlFlowEdge:
    """CFG 엣지 (블록 간 연결)"""

    source_block_id: str
    target_block_id: str
    kind: CFGEdgeKind
```

**ControlFlowGraph**:

```python
@dataclass
class ControlFlowGraph:
    """단일 함수/메서드의 Control Flow Graph"""

    # [Required] Identity
    id: str                    # cfg:HybridRetriever.plan
    function_node_id: str      # Node.id (Function/Method)

    # [Required] Structure
    entry_block_id: str
    exit_block_id: str
    blocks: list[ControlFlowBlock]
    edges: list[ControlFlowEdge]
```

### 2.4. BFG (Basic Flow Graph)

**위치**: `src/contexts/code_foundation/infrastructure/semantic_ir/bfg/models.py`

BFG는 CFG의 기반으로, 블록은 있지만 엣지는 없습니다. CFG 레이어에서 엣지를 추가합니다.

**BFGBlockKind** (블록 종류):

```python
class BFGBlockKind(str, Enum):
    """Basic Flow Graph 블록 타입"""

    ENTRY = "Entry"            # 함수 진입점
    EXIT = "Exit"              # 함수 종료점
    STATEMENT = "Statement"    # 일반 순차 문장
    CONDITION = "Condition"    # if/elif/else 조건
    LOOP_HEADER = "LoopHeader" # for/while 조건
    TRY = "Try"
    CATCH = "Catch"
    FINALLY = "Finally"

    # Async/await support
    SUSPEND = "Suspend"        # await 중단점 (async 호출 시작)
    RESUME = "Resume"          # await 재개점 (async 호출 완료)

    # Generator/Coroutine support
    DISPATCHER = "Dispatcher"  # 상태 머신 디스패처
    YIELD = "Yield"            # yield 지점 (중단 & 값 반환)
    RESUME_YIELD = "ResumeYield"  # yield 이후 재개점
```

**BasicFlowBlock**:

```python
@dataclass
class BasicFlowBlock:
    """
    기본 블록 - 단일 진입/출구를 가진 최대 문장 시퀀스

    ID 형식: bfg:{function_node_id}:block:{index}
    """

    # [Required] Identity
    id: str
    kind: BFGBlockKind
    function_node_id: str      # IR Node.id (Function/Method)

    # [Optional] Location
    span: Span | None

    # [Optional] AST metadata (CFG 엣지 생성용)
    ast_node_type: str | None  # if_statement, for_statement 등
    ast_has_alternative: bool  # else/elif 분기 존재 여부

    # [Optional] Statement content
    statement_count: int       # 블록 내 문장 수

    # [Optional] Data Flow (DFG용)
    defined_variable_ids: list[str]  # 이 블록에서 정의된 변수
    used_variable_ids: list[str]     # 이 블록에서 사용된 변수

    # [Optional] Control Flow Metadata
    is_break: bool             # break 문으로 끝남
    is_continue: bool          # continue 문으로 끝남
    is_return: bool            # return 문으로 끝남
    target_loop_id: str | None # break/continue 대상 루프 ID

    # [Optional] Async/await Metadata
    is_async_call: bool        # await 표현식 포함
    async_target_expression: str | None  # await된 표현식
    resume_from_suspend_id: str | None   # 대응하는 SUSPEND 블록
    async_result_variable: str | None    # await 결과 변수

    # [Optional] Exception handling
    can_throw_exception: bool
    exception_handler_block_ids: list[str]

    # [Optional] Generator/Coroutine Metadata
    generator_dispatch_table: dict[int, str] | None  # State → Block ID
    generator_state_id: int | None       # 현재 상태 번호
    generator_next_state: int | None     # yield 후 다음 상태
    generator_yield_value: str | None    # yield된 값
    generator_all_locals: list[str] | None  # 보존할 지역 변수들
```

**BasicFlowGraph**:

```python
@dataclass
class BasicFlowGraph:
    """
    단일 함수/메서드의 Basic Flow Graph

    블록만 포함, 엣지 없음. CFG 레이어에서 엣지 추가.
    """

    # [Required] Identity
    id: str                    # bfg:{function_node_id}
    function_node_id: str      # IR Node.id (Function/Method)

    # [Required] Structure
    entry_block_id: str
    exit_block_id: str
    blocks: list[BasicFlowBlock]

    # [Optional] Metadata
    total_statements: int      # 함수 내 총 문장 수

    # [Optional] Generator metadata
    is_generator: bool         # yield 포함 여부
    generator_yield_count: int # yield 문 개수
```

### 2.5. DFG (Data Flow Graph)

**DfgSnapshot**:

```python
@dataclass
class DfgSnapshot:
    repo_id: str
    snapshot_id: str

    # Variables
    variables: list[VariableEntity]

    # Events (reads/writes)
    events: list[VariableEvent]

    # Data flow edges
    edges: list[DataFlowEdge]
```

**VariableEntity**:

```python
@dataclass
class VariableEntity:
    id: str                    # var:{repo}:{file}:{func}:{name}@{block}:{shadow}
    repo_id: str
    file_path: str
    function_fqn: str
    name: str
    kind: Literal["param", "local", "captured"]

    # Type info
    type_id: str | None
    inferred_type: str | None
    type_source: str

    # Scope info
    scope_id: str | None
    scope_kind: str | None
    scope_depth: int

    # Declaration location
    decl_block_id: str | None
    decl_span: Span | None

    # Context-sensitive (k=1 call-string)
    context: str | None

    attrs: dict
```

**VariableEvent**:

```python
@dataclass
class VariableEvent:
    id: str                    # evt:{variable_id}:{ir_node_id}
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

**DataFlowEdge**:

```python
@dataclass(slots=True)
class DataFlowEdge:
    """
    변수 간 데이터 흐름 관계

    엣지 종류:
    - alias: a = b (직접 별칭)
    - assign: a = fn(b) (함수 호출 결과 할당)
    - param_to_arg: parameter → argument 흐름
    - return_value: return a
    """

    id: str
    from_variable_id: str      # 소스 변수 ID
    to_variable_id: str        # 타겟 변수 ID
    kind: Literal["alias", "assign", "param_to_arg", "return_value"]
    repo_id: str
    file_path: str
    function_fqn: str
    attrs: dict
```

**DfgSnapshot**:

```python
@dataclass(slots=True)
class DfgSnapshot:
    """
    함수 또는 파일의 완전한 DFG 스냅샷
    """

    variables: list[VariableEntity]  # 모든 변수 엔티티
    events: list[VariableEvent]      # 모든 읽기/쓰기 이벤트
    edges: list[DataFlowEdge]        # 모든 데이터 흐름 엣지
```

### 2.6. Expression IR

**위치**: `src/contexts/code_foundation/infrastructure/semantic_ir/expression/models.py`

**ExprKind** (표현식 종류):

```python
class ExprKind(str, Enum):
    """표현식 타입"""

    # Value access (값 접근)
    NAME_LOAD = "NameLoad"     # 변수 읽기: x
    ATTRIBUTE = "Attribute"    # 속성 접근: obj.attr
    SUBSCRIPT = "Subscript"    # 인덱싱: arr[i]

    # Operations (연산)
    BIN_OP = "BinOp"           # 이항 연산: a + b
    UNARY_OP = "UnaryOp"       # 단항 연산: -a, not x
    COMPARE = "Compare"        # 비교: a < b
    BOOL_OP = "BoolOp"         # 논리 연산: a and b

    # Calls/Creation (호출/생성)
    CALL = "Call"              # 함수 호출: fn(x)
    INSTANTIATE = "Instantiate" # 객체 생성: Class()

    # Literals (리터럴)
    LITERAL = "Literal"        # 상수: 1, "str", True
    COLLECTION = "Collection"  # 컬렉션: [1,2], {a:b}

    # Assignment (할당)
    ASSIGN = "Assign"          # 할당 대상: a = b (좌변)

    # Special (특수)
    LAMBDA = "Lambda"          # 람다 표현식
    COMPREHENSION = "Comprehension"  # 컴프리헨션
```

**Expression**:

```python
@dataclass
class Expression:
    """
    표현식 엔티티 (DFG용 값 수준 노드)

    값을 생성하거나 소비하는 AST의 단일 표현식을 나타냄.

    ID 형식: expr:{repo_id}:{file_path}:{line}:{col}
    """

    # [Required] Identity
    id: str
    kind: ExprKind
    repo_id: str
    file_path: str
    function_fqn: str | None   # None = 모듈 레벨 표현식

    # [Required] Location
    span: Span

    # [Optional] DFG connections
    reads_vars: list[str]      # VariableEntity ID 리스트 (읽는 변수)
    defines_var: str | None    # VariableEntity ID (할당 대상)

    # [Optional] Type information
    type_id: str | None        # TypeEntity ID (annotation에서)
    inferred_type: str | None  # Pyright hover 결과
    inferred_type_id: str | None  # 추론된 타입의 TypeEntity ID

    # [Optional] Symbol linking (cross-file resolution)
    symbol_id: str | None      # 심볼 정의의 IR Node ID
    symbol_fqn: str | None     # 심볼의 FQN

    # [Optional] Expression tree structure
    parent_expr_id: str | None     # 부모 표현식 ID
    child_expr_ids: list[str]      # 자식 표현식 ID 리스트

    # [Optional] CFG block reference
    block_id: str | None       # 이 표현식이 속한 CFGBlock ID

    # [Optional] Expression-specific attributes
    attrs: dict
    # attrs 예시:
    # - BinOp: {"operator": "+", "left_expr_id": "...", "right_expr_id": "..."}
    # - Call: {"callee_id": "...", "arg_expr_ids": [...], "callee_name": "fn"}
    # - Attribute: {"base_expr_id": "...", "attr_name": "field"}
    # - Literal: {"value": 42, "value_type": "int"}
    # - NAME_LOAD: {"var_name": "x"}
```

### 2.7. Interprocedural Data Flow

**위치**: `src/contexts/code_foundation/infrastructure/ir/models/interprocedural.py`

함수 경계를 넘나드는 데이터 흐름을 추적합니다 (Taint 분석, Impact 분석용).

**InterproceduralDataFlowEdge**:

```python
@dataclass
class InterproceduralDataFlowEdge:
    """
    함수 간 데이터 흐름 엣지

    두 가지 타입:
    1. arg_to_param: 호출자 인자 → 피호출자 파라미터
    2. return_to_callsite: 피호출자 리턴 → 호출자 변수

    예시:
        def callee(param):        # param
            return param * 2      # return value

        def caller():
            arg = user_input()    # arg
            result = callee(arg)  # call site

        Edges:
        - arg → param (arg_to_param)
        - return value → result (return_to_callsite)
    """

    id: str
    kind: Literal["arg_to_param", "return_to_callsite"]

    # Data flow endpoints
    from_var_id: str           # Caller arg OR callee return
    to_var_id: str             # Callee param OR caller var

    # Call site context
    call_site_id: str          # Call expression ID
    caller_func_fqn: str
    callee_func_fqn: str

    # Position (for arg_to_param)
    arg_position: int | None   # 0, 1, 2, ...

    # Metadata
    repo_id: str
    file_path: str
    confidence: float          # 0.0-1.0 (동적 호출용)

    # Context-sensitive (k=1 call-string)
    caller_context: str | None
    callee_context: str | None  # = call_site_id
```

**FunctionSummary**:

```python
@dataclass
class FunctionSummary:
    """
    함수 요약 (Inter-procedural 분석용)

    요약 내용:
    - 파라미터 → 리턴 흐름
    - 파라미터 → 전역 변수 영향
    - Side effects
    """

    func_fqn: str

    # Data flow summary
    param_to_return: dict[int, bool]      # {param_idx: flows_to_return}
    param_to_global: dict[int, list[str]] # {param_idx: [global_var_ids]}

    # Side effects
    modifies_globals: list[str]
    calls_external: list[str]
    has_io: bool
```

---

## 3. Advanced Analysis (고급 분석 레이어)

### 위치
- `src/contexts/reasoning_engine/infrastructure/pdg/`
- `src/contexts/code_foundation/infrastructure/analyzers/`
- `src/contexts/reasoning_engine/infrastructure/slicer/`

### 3.1. PDG (Program Dependence Graph)

PDG = CFG + DFG (Control Dependency + Data Dependency)

**PDGNode**:

```python
@dataclass
class PDGNode:
    node_id: str               # func:foo:stmt:3
    statement: str             # Source code statement
    line_number: int

    # Variable info
    defined_vars: list[str]    # Variables written
    used_vars: list[str]       # Variables read

    # Entry/Exit markers
    is_entry: bool
    is_exit: bool

    # Location
    file_path: str
    start_line: int
    end_line: int
```

**PDGEdge**:

```python
@dataclass
class PDGEdge:
    from_node: str
    to_node: str
    dependency_type: DependencyType  # CONTROL, DATA, CONTROL_DATA
    label: str | None          # Variable name for data dependency
```

**DependencyType**:

```python
class DependencyType(Enum):
    CONTROL = "control"        # if, while 등
    DATA = "data"              # def-use chain
    CONTROL_DATA = "both"      # 양쪽 모두
```

### 3.2. Slicing

**Backward Slice**: 이 노드에 영향을 준 모든 코드
**Forward Slice**: 이 노드가 영향을 주는 모든 코드

```python
# IRDocument에서 직접 사용 가능
slice_result = ir_doc.backward_slice(target_node_id, max_depth=50)
slice_result = ir_doc.forward_slice(source_node_id, max_depth=50)
```

**SliceResult**:

```python
@dataclass
class SliceResult:
    target_node_id: str
    slice_type: str            # backward or forward
    slice_nodes: set[str]      # Node IDs in slice
    slice_edges: list[PDGEdge]
    depth: int
```

### 3.3. Taint Analysis

**위치**: `src/contexts/code_foundation/infrastructure/analyzers/taint_engine_full.py`

**TaintVulnerability**:

```python
@dataclass
class TaintVulnerability:
    """
    발견된 보안 취약점

    Taint 분석을 통해 발견된 취약점 정보
    """

    source_function: str       # Source 함수 (user input)
    sink_function: str         # Sink 함수 (eval, SQL, ...)
    path: list[str]            # Taint 전파 경로 (함수 이름들)
    tainted_variables: set[str]  # 오염된 변수들
    severity: str              # high, medium, low
    is_sanitized: bool         # Sanitizer 통과 여부
    line_number: int           # 취약점 위치
```

**TaintLevel**:

```python
class TaintLevel(Enum):
    """오염 레벨"""

    CLEAN = "clean"            # 안전한 값
    TAINTED = "tainted"        # 오염된 값 (위험)
    SANITIZED = "sanitized"    # 정화된 값 (안전)
    UNKNOWN = "unknown"        # 알 수 없음
```

**TaintFact**:

```python
@dataclass
class TaintFact:
    """Taint 사실 (분석 중간 결과)"""

    variable: str              # 변수 이름
    taint_level: TaintLevel    # 오염 레벨
    source: str | None         # Source 함수
    location: tuple[int, int]  # (start_line, end_line)
```

```python
# IRDocument에서 직접 조회
findings = ir_doc.get_taint_findings(severity="high")
# → list[TaintVulnerability]
```

---

## 4. Graph Layer & HCG (통합 그래프 레이어)

### 위치
- `src/contexts/code_foundation/infrastructure/graph/models.py`
- `src/contexts/code_foundation/infrastructure/graph/builder.py`
- `src/contexts/codegen_loop/infrastructure/hcg_adapter.py`

### GraphDocument (Heterogeneous Code Graph)

IR + Semantic IR를 통합한 헤테로지니어스 그래프입니다.

```python
@dataclass
class GraphDocument:
    repo_id: str
    snapshot_id: str

    # Nodes & Edges
    graph_nodes: dict[str, GraphNode]
    graph_edges: list[GraphEdge]
    edge_by_id: dict[str, GraphEdge]

    # Indexes
    indexes: GraphIndex

    # Path index (O(1) lookup)
    _path_index: dict[str, set[str]] | None
```

### GraphNode

**GraphNodeKind (21종)**:

```python
class GraphNodeKind(str, Enum):
    # Structural (from IR)
    FILE = "File"
    MODULE = "Module"
    CLASS = "Class"
    INTERFACE = "Interface"
    FUNCTION = "Function"
    METHOD = "Method"
    VARIABLE = "Variable"
    FIELD = "Field"
    IMPORT = "Import"

    # Semantic (from Semantic IR)
    TYPE = "Type"
    SIGNATURE = "Signature"
    CFG_BLOCK = "CfgBlock"

    # External (lazy created)
    EXTERNAL_MODULE = "ExternalModule"
    EXTERNAL_FUNCTION = "ExternalFunction"
    EXTERNAL_TYPE = "ExternalType"

    # Framework/Architecture
    ROUTE = "Route"
    SERVICE = "Service"
    REPOSITORY = "Repository"
    CONFIG = "Config"
    JOB = "Job"
    MIDDLEWARE = "Middleware"

    # Documentation
    SUMMARY = "Summary"
    DOCUMENT = "Document"
```

**GraphNode 구조**:

```python
@dataclass
class GraphNode:
    id: str
    kind: GraphNodeKind
    repo_id: str
    snapshot_id: str | None
    fqn: str
    name: str
    path: str | None
    span: Span | None
    attrs: dict[str, Any]
```

### GraphEdge

**GraphEdgeKind (20종)**:

```python
class GraphEdgeKind(str, Enum):
    # Structural
    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"
    INHERITS = "INHERITS"
    IMPLEMENTS = "IMPLEMENTS"

    # Call/Reference
    CALLS = "CALLS"
    REFERENCES_TYPE = "REFERENCES_TYPE"
    REFERENCES_SYMBOL = "REFERENCES_SYMBOL"

    # Data Flow
    READS = "READS"
    WRITES = "WRITES"

    # Control Flow
    CFG_NEXT = "CFG_NEXT"
    CFG_BRANCH = "CFG_BRANCH"
    CFG_LOOP = "CFG_LOOP"
    CFG_HANDLER = "CFG_HANDLER"

    # Framework
    ROUTE_HANDLER = "ROUTE_HANDLER"
    HANDLES_REQUEST = "HANDLES_REQUEST"
    USES_REPOSITORY = "USES_REPOSITORY"
    MIDDLEWARE_NEXT = "MIDDLEWARE_NEXT"

    # Object
    INSTANTIATES = "INSTANTIATES"
    DECORATES = "DECORATES"

    # Documentation
    DOCUMENTS = "DOCUMENTS"
    REFERENCES_CODE = "REFERENCES_CODE"
    DOCUMENTED_IN = "DOCUMENTED_IN"
```

**GraphEdge 구조**:

```python
@dataclass
class GraphEdge:
    id: str
    kind: GraphEdgeKind
    source_id: str
    target_id: str
    attrs: dict[str, Any]
```

### GraphIndex

그래프 쿼리 최적화를 위한 역색인입니다.

```python
@dataclass
class GraphIndex:
    # Reverse indexes (target → sources)
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
    decorators_by_target: dict[str, list[str]]
```

### HCGAdapter

Codegen Loop에서 GraphDocument를 사용하기 위한 어댑터입니다.

```python
class HCGAdapter(HCGPort):
    """
    HCG (Heterogeneous Code Graph) Adapter

    QueryEngine을 통한 코드 그래프 쿼리:
    - Scope Selection (Query DSL)
    - Semantic Contract Validation
    - Incremental Update
    - GraphSpec Validation
    """

    def __init__(
        self,
        ir_doc: IRDocument | None,
        query_engine: QueryEngine | None,
    ):
        self.ir_doc = ir_doc
        self.query_engine = query_engine

    async def query_scope(
        self,
        task_description: str,
        max_files: int = 10,
    ) -> list[str]:
        """Query DSL로 관련 파일 찾기"""

    async def validate_semantic_contract(
        self,
        patch: Patch,
        contract: SemanticContract,
    ) -> bool:
        """Semantic contract 검증"""

    async def incremental_update(
        self,
        changed_files: list[str],
    ) -> None:
        """증분 업데이트"""
```

---

## 5. 생성 과정 (9-Layer Pipeline)

### LayeredIRBuilder

전체 IR 생성을 담당하는 9-layer 파이프라인입니다.

**위치**: `src/contexts/code_foundation/infrastructure/ir/layered_ir_builder.py`

### 9개 레이어

```python
class LayeredIRBuilder:
    """
    9-layer IR construction pipeline:

    1. Structural IR (Tree-sitter parsing) - Always on
    2. Occurrence Layer (SCIP-compatible) - Optional
    3. LSP Type Enrichment (selective, Public APIs) - Optional
    4. Cross-file Resolution (global context) - Optional
    5. Semantic IR (CFG/DFG/BFG) - Optional
    6. Advanced Analysis (PDG/Taint/Slicing) - Optional
    7. Retrieval Indexes (fast lookup) - Optional
    8. Diagnostics Collection (LSP) - Optional
    9. Package Analysis (dependencies) - Optional
    """
```

### Layer 1: Structural IR (필수)

**입력**: 소스 코드 파일
**출력**: IRDocument (nodes, edges)

```python
# Tree-sitter parsing
parser = ParserRegistry()
ast_tree = parser.parse(source_file)

# Generate IR nodes and edges
generator = get_generator(language)
nodes, edges = generator.generate(ast_tree)

ir_doc = IRDocument(
    repo_id=repo_id,
    snapshot_id=snapshot_id,
    nodes=nodes,
    edges=edges,
)
```

**생성되는 것**:
- Node (FILE, CLASS, FUNCTION, METHOD, VARIABLE, ...)
- Edge (CONTAINS, CALLS, READS, WRITES, ...)
- Span (소스 위치)

### Layer 2: Occurrence Layer (선택)

**입력**: IRDocument
**출력**: Occurrences (SCIP-compatible)

```python
occurrence_generator = OccurrenceGenerator()
occurrences, occurrence_index = occurrence_generator.generate(ir_doc)

ir_doc.occurrences = occurrences
ir_doc._occurrence_index = occurrence_index
```

**생성되는 것**:
- Occurrence (definition, reference)
- OccurrenceIndex (symbol → occurrences)

### Layer 3: LSP Type Enrichment (선택)

**입력**: IRDocument
**출력**: Type-enriched nodes

```python
type_enricher = SelectiveTypeEnricher(lsp_manager)
enriched_nodes = await type_enricher.enrich_types(
    ir_doc.nodes,
    strategy="public_api_only"  # Only public APIs
)
```

**생성되는 것**:
- Node.declared_type_id (from LSP)
- Enhanced type information

### Layer 4: Cross-file Resolution (선택)

**위치**: `src/contexts/code_foundation/infrastructure/ir/cross_file_resolver.py`

**입력**: Multiple IRDocuments
**출력**: GlobalContext

```python
resolver = CrossFileResolver()
global_ctx = await resolver.resolve(
    ir_docs=ir_docs,
    incremental=True
)
```

**생성되는 것**:
- Symbol → Definition mapping (cross-file)
- Import resolution
- External references
- Dependency graph
- Topological ordering

**GlobalContext 구조**:

```python
@dataclass
class GlobalContext:
    """
    프로젝트 전체 컨텍스트

    포함 내용:
    - Global symbol table (FQN → Node)
    - Import resolution
    - Dependency graph
    - Topological order (검색 랭킹용)
    """

    # FQN → (Node, file_path)
    symbol_table: dict[str, tuple[Node, str]]

    # file → dependencies
    dependencies: dict[str, set[str]]

    # file → dependents (reverse deps)
    dependents: dict[str, set[str]]

    # Topological order
    dep_order: list[str]

    # Stats
    total_symbols: int
    total_files: int

    def register_symbol(self, fqn: str, node: Node, file_path: str):
        """전역 심볼 테이블에 등록"""

    def resolve_symbol(self, fqn: str) -> ResolvedSymbol | None:
        """FQN → Node 해석"""

    def get_dependencies(self, file_path: str) -> set[str]:
        """파일의 의존성 조회"""

    def get_dependents(self, file_path: str) -> set[str]:
        """파일을 의존하는 파일들 조회"""

    def get_topological_order(self) -> list[str]:
        """토폴로지 순서 (의존성 순서)"""
```

**ResolvedSymbol**:

```python
@dataclass
class ResolvedSymbol:
    """해석된 심볼"""

    fqn: str
    node_id: str
    file_path: str
```

**활용 예시**:

```python
# Import 해석
# src/main.py: from calc import Calculator
# src/calc.py: class Calculator

global_ctx = resolver.resolve(ir_docs)

# FQN으로 심볼 찾기
resolved = global_ctx.resolve_symbol("calc.Calculator")
# → ResolvedSymbol(fqn="calc.Calculator", node_id="class:Calculator", file_path="src/calc.py")

# 의존성 조회
deps = global_ctx.get_dependencies("src/main.py")
# → {"src/calc.py"}

# 토폴로지 순서 (의존성 순)
order = global_ctx.get_topological_order()
# → ["src/calc.py", "src/main.py"]
```

### Layer 5: Semantic IR (선택, 814x 속도 향상 가능)

**위치**: `src/contexts/code_foundation/infrastructure/semantic_ir/builder.py`

**입력**: IRDocument
**출력**: SemanticIrSnapshot

```python
semantic_builder = DefaultSemanticIrBuilder()
snapshot, index = semantic_builder.build_full(ir_doc)

# Quick mode: 814x faster!
snapshot, index = semantic_builder.build_full(
    ir_doc,
    mode="quick"  # Skip CFG/DFG, only Type+Signature
)
```

**구성 Builder들**:

1. **TypeIrBuilder**: Type system 구축
   - `src/contexts/code_foundation/infrastructure/semantic_ir/typing/builder.py`
   - 생성: TypeEntity

2. **SignatureIrBuilder**: Function signatures
   - `src/contexts/code_foundation/infrastructure/semantic_ir/signature/builder.py`
   - 생성: SignatureEntity

3. **BfgBuilder**: Basic Flow Graph (blocks without edges)
   - `src/contexts/code_foundation/infrastructure/semantic_ir/bfg/builder.py`
   - 생성: BasicFlowGraph, BasicFlowBlock

4. **CfgBuilder**: Control Flow Graph (blocks with edges)
   - `src/contexts/code_foundation/infrastructure/semantic_ir/cfg/builder.py`
   - 생성: ControlFlowGraph, ControlFlowBlock, ControlFlowEdge

5. **ExpressionBuilder**: Expression IR
   - `src/contexts/code_foundation/infrastructure/semantic_ir/expression/builder.py`
   - 생성: Expression

6. **DfgBuilder**: Data Flow Graph
   - `src/contexts/code_foundation/infrastructure/dfg/builder.py`
   - 생성: DfgSnapshot (VariableEntity, VariableEvent, DataFlowEdge)

7. **InterproceduralDataFlowBuilder**: Inter-procedural edges
   - `src/contexts/code_foundation/infrastructure/ir/interprocedural_builder.py`
   - 생성: InterproceduralDataFlowEdge

**생성되는 것**:
- TypeEntity (type system)
- SignatureEntity (function signatures)
- BasicFlowGraph + BasicFlowBlock (BFG)
- ControlFlowGraph + ControlFlowBlock + ControlFlowEdge (CFG)
- Expression (expression IR)
- DfgSnapshot (VariableEntity, VariableEvent, DataFlowEdge)
- InterproceduralDataFlowEdge (함수 간 데이터 흐름)

**모드**:
- `full`: Type + Signature + CFG + BFG + DFG + Interprocedural (느림)
- `quick`: Type + Signature only (814x 빠름)

### Layer 6: Advanced Analysis (선택)

**입력**: IRDocument + SemanticIrSnapshot
**출력**: PDG, Taint findings

```python
# PDG (Program Dependence Graph)
from src.contexts.reasoning_engine.infrastructure.pdg import PDGBuilder

pdg_builder = PDGBuilder()
pdg_nodes, pdg_edges = pdg_builder.build(
    cfg_nodes=snapshot.cfg_blocks,
    cfg_edges=snapshot.cfg_edges,
    dfg_edges=snapshot.dfg_snapshot.edges
)

ir_doc.pdg_nodes = pdg_nodes
ir_doc.pdg_edges = pdg_edges

# Taint Analysis
from src.contexts.code_foundation.infrastructure.analyzers import TaintAnalyzer

taint_analyzer = TaintAnalyzer()
findings = await taint_analyzer.analyze(ir_doc)

ir_doc.taint_findings = findings

# Slicing (requires PDG)
ir_doc.build_indexes()  # Build PDG index
slice_result = ir_doc.backward_slice(target_node_id)
```

**생성되는 것**:
- PDGNode, PDGEdge
- TaintVulnerability (security vulnerability)
- TaintFact, TaintLevel (taint tracking)
- SliceResult (forward/backward slice)

### Layer 7: Retrieval Indexes (선택)

**위치**: `src/contexts/code_foundation/infrastructure/ir/retrieval_index.py`

**입력**: IRDocument
**출력**: RetrievalOptimizedIndex

```python
retrieval_builder = RetrievalOptimizedIndex()
retrieval_index = retrieval_builder.build(ir_doc)
```

**생성되는 것**:
- Symbol name index (exact + fuzzy)
- FQN index (O(1) lookup)
- Type-based index
- Importance-ranked results
- File-level indexes

**RetrievalOptimizedIndex 구조**:

```python
class RetrievalOptimizedIndex:
    """
    검색 최적화 인덱스

    성능 목표:
    - Symbol lookup (exact): <
    - Symbol lookup (fuzzy): <
    - Find-references: <
    - Type-based queries: <
    """

    def __init__(self):
        # Exact name → node IDs
        self._name_index: dict[str, list[str]] = {}

        # FQN → node ID (O(1))
        self._fqn_index: dict[str, str] = {}

        # Type-based index
        self._type_index: dict[str, list[str]] = {}

        # File-level indexes
        self._file_indexes: dict[str, FileIndex] = {}

        # Fuzzy matcher
        self._fuzzy_matcher: FuzzyMatcher = FuzzyMatcher()

        # Importance ranking
        self._importance_scores: dict[str, float] = {}

    def index_ir_document(self, ir_doc: IRDocument):
        """IRDocument 인덱싱"""

    def search_symbol(
        self,
        query: str,
        fuzzy: bool = False,
        limit: int = 10
    ) -> list[tuple[Node, float]]:
        """
        심볼 검색 (exact or fuzzy)

        Returns:
            List of (node, relevance_score)
        """

    def find_by_fqn(self, fqn: str) -> Node | None:
        """FQN으로 노드 찾기 (O(1))"""

    def find_by_type(self, type_name: str) -> list[Node]:
        """타입으로 노드 찾기"""

    def get_file_symbols(self, file_path: str) -> list[Node]:
        """파일의 모든 심볼"""
```

**FuzzyMatcher** (퍼지 검색):

```python
class FuzzyMatcher:
    """
    퍼지 문자열 매칭

    Edit distance 기반 유사도 계산
    """

    def add(self, name: str, item_id: str):
        """아이템 추가"""

    def search(self, query: str, limit: int = None) -> list[tuple[str, float]]:
        """
        퍼지 검색

        Returns:
            List of (item_id, similarity_score)
        """
```

**FileIndex** (파일별 인덱스):

```python
@dataclass
class FileIndex:
    """파일별 인덱스"""

    file_path: str
    nodes: list[Node]
    node_ids: set[str]
```

**활용 예시**:

```python
# Exact search
results = index.search_symbol("Calculator", fuzzy=False)
# → [(Node(name="Calculator", ...), 1.0)]

# Fuzzy search
results = index.search_symbol("Calculater", fuzzy=True)  # 오타
# → [(Node(name="Calculator", ...), 0.9)]

# FQN lookup (O(1))
node = index.find_by_fqn("calc.Calculator")
# → Node(fqn="calc.Calculator", ...)

# Type-based search
nodes = index.find_by_type("int")
# → [Node(declared_type_id="type:int", ...), ...]

# File symbols
symbols = index.get_file_symbols("src/calc.py")
# → [Node("Calculator"), Node("add"), Node("subtract")]
```

### Layer 8: Diagnostics Collection (선택)

**입력**: IRDocument
**출력**: Diagnostics

```python
diagnostic_collector = DiagnosticCollector(lsp_manager)
diagnostics, diag_index = await diagnostic_collector.collect(ir_doc)

ir_doc.diagnostics = diagnostics
ir_doc._diagnostic_index = diag_index
```

**생성되는 것**:
- Diagnostic (error, warning, info)
- DiagnosticIndex (file → diagnostics)

### Layer 9: Package Analysis (선택)

**입력**: IRDocument
**출력**: PackageMetadata

```python
package_analyzer = PackageAnalyzer()
packages, pkg_index = await package_analyzer.analyze(ir_doc)

ir_doc.packages = packages
ir_doc._package_index = pkg_index
```

**생성되는 것**:
- PackageMetadata (dependencies)
- PackageIndex (package → files)

---

## 6. Graph Layer 생성 (IR → GraphDocument)

### GraphBuilder

**입력**: IRDocument + SemanticIrSnapshot
**출력**: GraphDocument

```python
from src.contexts.code_foundation.infrastructure.graph.builder import GraphBuilder

graph_builder = GraphBuilder()
graph_doc = graph_builder.build_full(
    ir_doc=ir_doc,
    semantic_snapshot=semantic_snapshot
)
```

### 변환 과정

**Phase 1: Node Conversion**
```
IR Node → GraphNode
  - FILE → GraphNode(FILE)
  - CLASS → GraphNode(CLASS)
  - FUNCTION → GraphNode(FUNCTION)
  - METHOD → GraphNode(METHOD)
  - VARIABLE → GraphNode(VARIABLE)
  - ...

TypeEntity → GraphNode(TYPE)
SignatureEntity → GraphNode(SIGNATURE)
ControlFlowBlock → GraphNode(CFG_BLOCK)
```

**Phase 2: Edge Conversion**
```
IR Edge → GraphEdge
  - CONTAINS → GraphEdge(CONTAINS)
  - CALLS → GraphEdge(CALLS)
  - READS → GraphEdge(READS)
  - WRITES → GraphEdge(WRITES)
  - ...

CFG Edge → GraphEdge(CFG_NEXT, CFG_BRANCH, ...)
DFG Edge → GraphEdge(READS, WRITES)
```

**Phase 3: External Node Creation**
```
Unresolved references → GraphNode(EXTERNAL_*)
  - External import → GraphNode(EXTERNAL_MODULE)
  - External function → GraphNode(EXTERNAL_FUNCTION)
  - External type → GraphNode(EXTERNAL_TYPE)
```

**Phase 4: Index Building**
```
Build GraphIndex:
  - called_by (reverse call graph)
  - imported_by (reverse imports)
  - contains_children (containment hierarchy)
  - type_users (type usage)
  - reads_by / writes_by (data flow)
  - outgoing / incoming (adjacency)
```

---

## 7. 전체 데이터 플로우

```
소스 코드 (Python, TypeScript, Java, ...)
    ↓
[Layer 0] Parsing
├─ ParserRegistry (Tree-sitter)
│   ├─ Python Parser
│   ├─ TypeScript Parser
│   └─ Java Parser
│
└─ IRGenerator (언어별)
    ├─ PythonIRGenerator
    ├─ TypeScriptIRGenerator
    └─ JavaIRGenerator
    ↓
IRDocument (Structural IR)
  - nodes: Node[] (20종)
  - edges: Edge[] (23종)
  - spans: Span[]
    ↓
[Layer 2] Occurrence Generation (SCIP)
  - occurrences: Occurrence[]
  - occurrence_index: OccurrenceIndex
    ↓
[Layer 3] LSP Type Enrichment (선택)
  - enriched types from LSP
    ↓
[Layer 4] Cross-file Resolution
    ↓
GlobalContext
  - symbol_table: FQN → Node
  - dependencies: file → deps
  - dep_order: topological order
    ↓
[Layer 5] Semantic IR Building
    ↓
SemanticIrSnapshot
  - types: TypeEntity[]
  - signatures: SignatureEntity[]
  - cfg: ControlFlowGraph[] + ControlFlowBlock[] + ControlFlowEdge[]
  - bfg: BasicFlowGraph[] + BasicFlowBlock[]
  - dfg: DfgSnapshot (VariableEntity, VariableEvent, DataFlowEdge)
  - expressions: Expression[]
  - interprocedural_edges: InterproceduralDataFlowEdge[]
    ↓
[Layer 6] Advanced Analysis
    ↓
PDG + Taint + Slicing
  - pdg_nodes: PDGNode[]
  - pdg_edges: PDGEdge[]
  - taint_findings: TaintVulnerability[]
  - slice_results: SliceResult[]
    ↓
[Layer 7] Retrieval Indexes
    ↓
RetrievalOptimizedIndex
  - name_index (exact + fuzzy)
  - fqn_index (O(1))
  - type_index
  - file_indexes
    ↓
[Layer 8] Diagnostics Collection (LSP)
    ↓
Diagnostics
  - diagnostics: Diagnostic[]
  - diagnostic_index: DiagnosticIndex
    ↓
[Layer 9] Package Analysis
    ↓
Packages
  - packages: PackageMetadata[]
  - package_index: PackageIndex
    ↓
[GraphBuilder] IR → Graph Conversion
    ↓
GraphDocument (HCG)
  - graph_nodes: GraphNode[] (21종)
  - graph_edges: GraphEdge[] (20종)
  - indexes: GraphIndex
  - path_index: file → nodes (O(1))
    ↓
[HCGAdapter] Query DSL
    ↓
Application
  - Codegen Loop
  - Security Analysis
  - Code Search
  - Impact Analysis
  - ...
```

---

## 8. 관계 그래프 예시

### Structural IR 관계

```
File "main.py"
  ├─ [CONTAINS] → Class "Calculator"
  │                ├─ [CONTAINS] → Method "add"
  │                │                ├─ [CALLS] → Function "validate"
  │                │                ├─ [READS] → Field "precision"
  │                │                └─ [WRITES] → Variable "result"
  │                │
  │                ├─ [CONTAINS] → Method "subtract"
  │                └─ [INHERITS] → Class "BaseCalculator"
  │
  ├─ [CONTAINS] → Function "validate"
  └─ [IMPORTS] → Module "math"
```

### Semantic IR 관계

```
Function "add"
  ├─ SignatureEntity
  │   ├─ param_names: ["a", "b"]
  │   ├─ param_type_ids: ["type:int", "type:int"]
  │   └─ return_type_id: "type:int"
  │
  ├─ ControlFlowGraph
  │   ├─ entry_block: Block@0
  │   ├─ Block@0 → Block@1 (sequential)
  │   ├─ Block@1 → Block@2 (branch: true)
  │   ├─ Block@1 → Block@3 (branch: false)
  │   └─ Block@2, Block@3 → exit_block
  │
  └─ DfgSnapshot
      ├─ VariableEntity "a" (param)
      ├─ VariableEntity "b" (param)
      ├─ VariableEntity "result" (local)
      ├─ Event: write(result) @ Block@1
      ├─ Event: read(a) @ Block@1
      ├─ Event: read(b) @ Block@1
      └─ DataFlowEdge: write(result) → read(result)
```

### Graph Layer 관계

```
GraphNode(FILE) "main.py"
  ├─ [CONTAINS] → GraphNode(CLASS) "Calculator"
  │                ├─ [CONTAINS] → GraphNode(METHOD) "add"
  │                │                ├─ [CALLS] → GraphNode(FUNCTION) "validate"
  │                │                ├─ [READS] → GraphNode(FIELD) "precision"
  │                │                ├─ [REFERENCES_TYPE] → GraphNode(TYPE) "int"
  │                │                └─ [CFG_NEXT] → GraphNode(CFG_BLOCK)
  │                │
  │                └─ [INHERITS] → GraphNode(EXTERNAL_TYPE) "BaseCalculator"
  │
  └─ [IMPORTS] → GraphNode(EXTERNAL_MODULE) "math"
```

---

## 9. 쿼리 API

### IRDocument 쿼리

```python
# Node 조회
node = ir_doc.get_node(node_id)
nodes = ir_doc.find_nodes_by_name("add")
nodes = ir_doc.find_nodes_by_kind(NodeKind.METHOD)

# Edge 조회
edges = ir_doc.get_edges_from(source_id)

# File 조회
nodes = ir_doc.get_file_nodes(file_path)

# Occurrence 조회 (SCIP)
refs = ir_doc.find_references(symbol_id)
defs = ir_doc.find_definitions(symbol_id)
usages = ir_doc.find_usages(symbol_id)

# PDG 조회
pdg = ir_doc.get_pdg_builder()

# Slicing
slice = ir_doc.backward_slice(target_node_id, max_depth=50)
slice = ir_doc.forward_slice(source_node_id, max_depth=50)

# Taint 조회
findings = ir_doc.get_taint_findings(severity="high")

# Dataflow path
path = ir_doc.find_dataflow_path(from_node_id, to_node_id)

# Statistics
stats = ir_doc.get_stats()
```

### GraphDocument 쿼리

```python
# Node 조회
node = graph_doc.get_node(node_id)
nodes = graph_doc.get_nodes_by_kind(GraphNodeKind.FUNCTION)

# Edge 조회
edges = graph_doc.get_edges_by_kind(GraphEdgeKind.CALLS)
edges = graph_doc.get_edges_from(source_id)
edges = graph_doc.get_edges_to(target_id)

# Path 조회 (O(1))
node_ids = graph_doc.get_node_ids_by_path(file_path)
node_ids = graph_doc.get_node_ids_by_paths([file1, file2, ...])

# Index 조회
callers = graph_doc.indexes.get_callers(function_id)
importers = graph_doc.indexes.get_importers(module_id)
children = graph_doc.indexes.get_children(parent_id)
type_users = graph_doc.indexes.get_type_users(type_id)
readers = graph_doc.indexes.get_readers(variable_id)
writers = graph_doc.indexes.get_writers(variable_id)

# Framework 조회
routes = graph_doc.indexes.get_routes_by_path("/api/users")
services = graph_doc.indexes.get_services_by_domain("auth")
flow = graph_doc.indexes.get_request_flow(route_id)
decorators = graph_doc.indexes.get_decorators(target_id)

# Statistics
stats = graph_doc.stats()
```

### GlobalContext 쿼리

```python
# Symbol resolution
resolved = global_ctx.resolve_symbol("calc.Calculator")
# → ResolvedSymbol(fqn="calc.Calculator", node_id="...", file_path="src/calc.py")

# Dependencies
deps = global_ctx.get_dependencies("src/main.py")
# → {"src/calc.py", "src/utils.py"}

# Dependents (reverse)
dependents = global_ctx.get_dependents("src/calc.py")
# → {"src/main.py", "src/test_calc.py"}

# Topological order
order = global_ctx.get_topological_order()
# → ["src/utils.py", "src/calc.py", "src/main.py"]

# Statistics
stats = global_ctx.get_stats()
# → {"total_symbols": 150, "total_files": 10, ...}
```

### RetrievalOptimizedIndex 쿼리

```python
# Exact search
results = retrieval_index.search_symbol("Calculator", fuzzy=False, limit=10)
# → [(Node(...), 1.0), ...]

# Fuzzy search (오타 허용)
results = retrieval_index.search_symbol("Calculater", fuzzy=True, limit=10)
# → [(Node(name="Calculator", ...), 0.9), ...]

# FQN lookup (O(1))
node = retrieval_index.find_by_fqn("calc.Calculator")
# → Node(fqn="calc.Calculator", ...)

# Type-based search
nodes = retrieval_index.find_by_type("int")
# → [Node(declared_type_id="type:int", ...), ...]

# File symbols
symbols = retrieval_index.get_file_symbols("src/calc.py")
# → [Node("Calculator"), Node("add"), Node("subtract")]

# High-importance symbols
important = retrieval_index.get_high_importance_symbols(min_score=0.8)
# → [(Node(...), 0.95), (Node(...), 0.85), ...]
```

### Query DSL (HCGAdapter)

```python
from src.contexts.code_foundation.domain.query import Q, E

# Find functions
query = Q.Func() >> Q.Any()
results = query_engine.execute(query)

# Find callers
query = Q.Func("add") >> E.CalledBy() >> Q.Func()
callers = query_engine.execute(query)

# Find type users
query = Q.Type("User") >> E.UsedBy() >> Q.Any()
users = query_engine.execute(query)

# Complex query
query = (
    Q.Func("login")
    >> E.Calls()
    >> Q.Func()
    >> E.Reads()
    >> Q.Variable("password")
)
results = query_engine.execute(query)
```

---

## 10. 성능 특성

### Structural IR (Layer 1)
- Small repo (<100 files): <2s
- Medium repo (100-1K files): <20s
- Large repo (1K+ files): <2min

### Semantic IR (Layer 5)
- **Full mode** (Type+Sig+CFG+BFG+DFG): 느림
- **Quick mode** (Type+Sig only): **814x faster!**

### Advanced Analysis (Layer 6)
- PDG: CFG + DFG 필요 (Medium cost)
- Taint: PDG 필요 (High cost)
- Slicing: PDG 필요 (Low cost per query)

### Graph Layer
- Conversion: O(N + E) where N=nodes, E=edges
- Index building: O(N + E)
- Query: O(1) with indexes

---

## 11. 증분 업데이트

### Structural IR
```python
# Incremental build
ir_docs, global_ctx, retrieval_index, diag_idx, pkg_idx = await builder.build_incremental(
    changed_files=[Path("src/calc.py")],
    existing_irs=ir_docs,
    global_ctx=global_ctx,
    retrieval_index=retrieval_index,
)
```

### Semantic IR
```python
# Apply delta
snapshot, index = semantic_builder.apply_delta(
    ir_doc=updated_ir_doc,
    existing_snapshot=old_snapshot,
    existing_index=old_index,
)
```

### Graph Layer
```python
# HCGAdapter를 통한 증분 업데이트
await hcg_adapter.incremental_update(
    changed_files=["src/calc.py"]
)
```

---

## 12. 파일 위치 요약

```
src/contexts/code_foundation/
├── infrastructure/
│   ├── parsing/
│   │   └── parser_registry.py       # ParserRegistry (Tree-sitter)
│   ├── generators/
│   │   ├── base.py                  # IRGenerator (abstract)
│   │   ├── python_generator.py      # Python IR 생성
│   │   ├── typescript_generator.py  # TypeScript IR 생성
│   │   ├── java_generator.py        # Java IR 생성
│   │   └── cached_generator.py      # 캐싱 래퍼
│   ├── ir/
│   │   ├── models/
│   │   │   ├── core.py              # Node, Edge, Span
│   │   │   ├── document.py          # IRDocument
│   │   │   ├── occurrence.py        # Occurrence, SymbolRole, OccurrenceIndex
│   │   │   ├── diagnostic.py        # Diagnostic, DiagnosticSeverity
│   │   │   ├── package.py           # PackageMetadata, PackageIndex
│   │   │   └── interprocedural.py   # InterproceduralDataFlowEdge
│   │   ├── layered_ir_builder.py    # 9-layer pipeline
│   │   ├── occurrence_generator.py  # Layer 2: Occurrence 생성
│   │   ├── type_enricher.py         # Layer 3: LSP Type Enrichment
│   │   ├── cross_file_resolver.py   # Layer 4: GlobalContext
│   │   ├── retrieval_index.py       # Layer 7: RetrievalOptimizedIndex
│   │   ├── diagnostic_collector.py  # Layer 8: Diagnostics
│   │   └── package_analyzer.py      # Layer 9: Package Analysis
│   ├── semantic_ir/
│   │   ├── builder.py               # SemanticIrBuilder
│   │   ├── context.py               # SemanticIrSnapshot, SemanticIndex
│   │   ├── typing/
│   │   │   ├── models.py            # TypeEntity
│   │   │   └── builder.py           # TypeIrBuilder
│   │   ├── signature/
│   │   │   ├── models.py            # SignatureEntity
│   │   │   └── builder.py           # SignatureIrBuilder
│   │   ├── cfg/
│   │   │   ├── models.py            # ControlFlowGraph, ControlFlowBlock
│   │   │   └── builder.py           # CfgBuilder
│   │   ├── bfg/
│   │   │   ├── models.py            # BasicFlowGraph, BasicFlowBlock
│   │   │   └── builder.py           # BfgBuilder
│   │   └── expression/
│   │       ├── models.py            # Expression
│   │       └── builder.py           # ExpressionBuilder
│   ├── dfg/
│   │   ├── builder.py               # DfgBuilder
│   │   └── models.py                # VariableEntity, VariableEvent, DataFlowEdge
│   └── graph/
│       ├── models.py                # GraphDocument, GraphNode, GraphEdge, GraphIndex
│       └── builder.py               # GraphBuilder
├── domain/
│   ├── models.py                    # UnifiedSymbol (SCIP)
│   └── ports/
│       └── ir_port.py               # IRDocumentPort (interface)

src/contexts/reasoning_engine/
└── infrastructure/
    ├── pdg/
    │   ├── pdg_builder.py           # PDG (Control + Data Dependency)
    │   ├── models.py                # PDGNode, PDGEdge, DependencyType
    │   ├── control_dependency.py    # Control dependency 분석
    │   └── data_dependency.py       # Data dependency 분석
    └── slicer/
        └── slicer.py                # ProgramSlicer (Forward/Backward)

src/contexts/codegen_loop/
└── infrastructure/
    └── hcg_adapter.py               # HCGAdapter (Query DSL)
```

---

## 13. 핵심 개념 정리

### Parsing Layer (Layer 0)
- **역할**: 소스 코드 → AST → IR 변환
- **구성**: ParserRegistry (Tree-sitter), IRGenerator (언어별)
- **특징**: 다언어 지원 (Python, TypeScript, Java, Go, Rust, C/C++), 언어 중립적 IR 생성

### Structural IR (Layer 1)
- **역할**: 코드의 구조적 표현 (AST → IR)
- **구성**: Node (20종), Edge (23종), Span
- **특징**: 언어 중립적, 모든 분석의 기반
- **추가**: Occurrence (SCIP 호환), Diagnostic (LSP), PackageMetadata

### Semantic IR (Layer 5)
- **역할**: 코드의 의미론적 표현
- **구성**: Type, Signature, CFG, BFG, DFG, Expression, InterproceduralDataFlow
- **특징**: 정적 분석 기반, 타입/제어흐름/데이터흐름
- **모드**: Full (느림) vs Quick (814x 빠름)

### Cross-file Layer (Layer 4)
- **역할**: 프로젝트 전체 컨텍스트
- **구성**: GlobalContext (symbol_table, dependencies, dep_order)
- **특징**: Import 해석, 의존성 그래프, 토폴로지 순서

### Retrieval Layer (Layer 7)
- **역할**: 검색 최적화
- **구성**: RetrievalOptimizedIndex (exact + fuzzy search)
- **특징**: O(1) 조회, importance ranking, 파일별 인덱스

### Advanced Analysis (Layer 6)
- **역할**: 고급 프로그램 분석
- **구성**: PDG (Control+Data Dependency), Taint, Slicing
- **특징**: Semantic IR 기반, 보안/디버깅/최적화

### Graph Layer (HCG)
- **역할**: 통합 그래프 (Heterogeneous Code Graph)
- **구성**: GraphNode (21종), GraphEdge (20종), GraphIndex
- **특징**: IR + Semantic IR 통합, Query DSL, 프레임워크 인식

### 9-Layer Pipeline
0. **Parsing** (Tree-sitter + IRGenerator) - 필수
1. **Structural IR** (Node, Edge) - 필수
2. **Occurrence** (SCIP) - 선택
3. **LSP Type Enrichment** - 선택
4. **Cross-file Resolution** (GlobalContext) - 선택
5. **Semantic IR** (Type, CFG, DFG) - 선택 (814x 속도 향상 가능)
6. **Advanced Analysis** (PDG/Taint/Slicing) - 선택
7. **Retrieval Indexes** - 선택
8. **Diagnostics** (LSP) - 선택
9. **Package Analysis** - 선택

---

## 14. 주요 특징 및 차별점

### SCIP 호환성
- **Occurrence**: SCIP 표준 호환 심볼 추적
- **SymbolRole**: SCIP bitflags (DEFINITION, IMPORT, READ_ACCESS, WRITE_ACCESS)
- **PackageMetadata**: SCIP moniker 지원
- **UnifiedSymbol**: Cross-language 심볼 매칭

### 다언어 지원
- **Tree-sitter**: 모든 주요 언어 지원
- **언어별 Generator**: Python, TypeScript, Java, Go, Rust, C/C++
- **통합 IR**: 언어 중립적 표현

### 증분 업데이트
- **Content Hash**: SHA256 기반 변경 감지
- **Delta Application**: SemanticIrDelta로 효율적 업데이트
- **Incremental Resolution**: GlobalContext 증분 해석

### 성능 최적화
- **Quick Mode**: Semantic IR 814x 속도 향상
- **O(1) 조회**: FQN, file path, symbol lookup
- **Fuzzy Search**: Edit distance 기반 유사 검색
- **Importance Ranking**: 검색 결과 순위화

### Inter-procedural 분석
- **InterproceduralDataFlowEdge**: 함수 간 데이터 흐름
- **FunctionSummary**: 함수 효과 요약
- **Context-sensitive**: k=1 call-string

### 확장성
- **Pluggable Architecture**: Generator, Analyzer 추가 가능
- **Layer Selection**: 필요한 레이어만 활성화
- **Adaptive Configuration**: 프로젝트 크기별 최적화

---

## 15. 사용 예시

### 기본 IR 생성

```python
from pathlib import Path
from src.contexts.code_foundation.infrastructure.ir.layered_ir_builder import (
    LayeredIRBuilder, LayeredIRConfig
)

# Configuration
config = LayeredIRConfig(
    max_concurrent_files=50,
    enable_incremental_resolve=True,
)

# Builder
builder = LayeredIRBuilder(
    project_root=Path("myproject"),
    config=config,
)

# Full build (모든 레이어)
ir_docs, global_ctx, retrieval_index, diag_idx, pkg_idx = await builder.build_full(
    files=[Path("src/calc.py"), Path("src/main.py")],
    enable_semantic_ir=True,
    semantic_mode="quick",  # 814x faster!
    enable_advanced_analysis=True,
)
```

### 증분 업데이트

```python
# Incremental update
ir_docs, global_ctx, retrieval_index, diag_idx, pkg_idx = await builder.build_incremental(
    changed_files=[Path("src/calc.py")],
    existing_irs=ir_docs,
    global_ctx=global_ctx,
    retrieval_index=retrieval_index,
)
```

### 검색 및 분석

```python
# Symbol search
results = retrieval_index.search_symbol("Calculator", fuzzy=True, limit=10)

# Find references
refs = ir_doc.find_references("class:Calculator")

# Backward slice
slice_result = ir_doc.backward_slice("method:Calculator.add")

# Taint analysis
findings = ir_doc.get_taint_findings(severity="high")

# Graph query
graph_doc = graph_builder.build_full(ir_doc, semantic_snapshot)
callers = graph_doc.indexes.get_callers("function:calculate")
```

### HCG 쿼리

```python
from src.contexts.codegen_loop.infrastructure.hcg_adapter import HCGAdapter
from src.contexts.code_foundation.domain.query import Q, E

# Create adapter
hcg = HCGAdapter(ir_doc=ir_doc)

# Query DSL
query = Q.Func("login") >> E.Calls() >> Q.Func()
results = hcg.query_engine.execute(query)

# Scope selection
files = await hcg.query_scope(
    task_description="Implement user authentication",
    max_files=10,
)
```

---

## 16. 제한사항 및 향후 계획

### 현재 제한사항
- **Dynamic typing**: 동적 타입 완전 지원 제한 (추론 기반)
- **Macro expansion**: C/C++ 매크로 확장 미지원
- **Reflection**: Java/Python reflection 일부 제한
- **Dynamic imports**: 동적 import 해석 제한

### 향후 계획
- **Multi-language cross-references**: 언어 간 참조 완전 지원
- **Enhanced taint analysis**: 더 정교한 오염 추적
- **ML-based type inference**: 머신러닝 기반 타입 추론
- **Distributed indexing**: 대규모 프로젝트 분산 인덱싱
- **Real-time updates**: 파일 변경 실시간 추적

---

## 17. SCIP 호환성 상세

### SCIP란?

**SCIP** (Semantic Code Intelligence Protocol)은 Sourcegraph에서 만든 코드 인텔리전스 표준입니다.
언어 중립적인 방식으로 심볼, 참조, 타입 정보를 표현합니다.

### SCIP Descriptor 형식

```
scip-{scheme} {manager} {package} {version} {root}`{file_path}`/`{descriptor}`
```

**예시**:
```
scip-python pypi requests 2.31.0 /`__init__.py`/`get`().
scip-java maven com.example 1.0.0 src/`Main.java`/`MyClass#`
scip-typescript npm @types/node 18.0.0 /`fs.d.ts`/`readFile`().
```

### Descriptor 규칙

| 심볼 타입 | Suffix | 예시 |
|----------|--------|------|
| Package/Module | `/` | `src/utils/` |
| Class | `#` | `Calculator#` |
| Method | `().` | `add().` |
| Field | `.` | `count.` |
| Parameter | `(param)` | `(x)` |
| Type Parameter | `[T]` | `[T]` |

### 우리 시스템에서의 SCIP 구현

```python
# UnifiedSymbol → SCIP Descriptor
symbol = UnifiedSymbol(
    scheme="python",
    manager="pypi",
    package="myproject",
    version="1.0.0",
    root="/",
    file_path="src/calc.py",
    descriptor="Calculator#add().",
    language_fqn="calc.Calculator.add",
    language_kind="method",
)

scip = symbol.to_scip_descriptor()
# → "scip-python pypi myproject 1.0.0 / `src/calc.py` `Calculator#add().`"
```

---

## 18. Query DSL 상세

### 기본 개념

Query DSL은 그래프 쿼리를 선언적으로 표현합니다.

**기본 구성요소**:
- `Q.{NodeType}()`: 노드 매처
- `E.{EdgeType}()`: 엣지 매처
- `>>`: 체이닝 연산자

### 노드 매처 (Q)

```python
Q.Func()          # 모든 함수
Q.Func("login")   # 이름이 "login"인 함수
Q.Class()         # 모든 클래스
Q.Method()        # 모든 메서드
Q.Variable()      # 모든 변수
Q.Type()          # 모든 타입
Q.Any()           # 모든 노드
```

### 엣지 매처 (E)

```python
E.Calls()         # 호출 관계
E.CalledBy()      # 역방향 호출
E.Contains()      # 포함 관계 (Class → Method)
E.ContainedBy()   # 역방향 포함
E.Imports()       # Import 관계
E.ImportedBy()    # 역방향 Import
E.Reads()         # 읽기 관계
E.Writes()        # 쓰기 관계
E.Inherits()      # 상속 관계
E.UsedBy()        # 사용 관계
```

### 쿼리 예시

```python
from src.contexts.code_foundation.domain.query import Q, E

# login 함수가 호출하는 모든 함수
query = Q.Func("login") >> E.Calls() >> Q.Func()

# Calculator 클래스의 모든 메서드
query = Q.Class("Calculator") >> E.Contains() >> Q.Method()

# password 변수를 읽는 모든 함수
query = Q.Variable("password") >> E.ReadBy() >> Q.Func()

# 복합 쿼리: login → 호출 → 함수 → 읽기 → password
query = (
    Q.Func("login")
    >> E.Calls()
    >> Q.Func()
    >> E.Reads()
    >> Q.Variable("password")
)

# 실행
results = query_engine.execute(query)
for node in results:
    print(f"{node.kind}: {node.name} @ {node.file_path}")
```

---

## 19. 증분 업데이트 상세

### 변경 감지 메커니즘

```python
# Content Hash로 변경 감지
# SHA256 해시 형식: sha256:{hex}
old_hash = node.content_hash  # "sha256:a1b2c3d4..."
new_hash = generator.generate_content_hash(new_source)

if old_hash != new_hash:
    # 파일 변경됨 → 재분석 필요
    pass
```

### Body Hash (Signature)

```python
# SignatureEntity.raw_body_hash 형식
# body_sha256:{16 hex chars}
signature.raw_body_hash = "body_sha256:1234567890abcdef"

# 함수 본문 변경 감지
if old_sig.raw_body_hash != new_sig.raw_body_hash:
    # 함수 구현 변경됨
    pass
```

### 증분 업데이트 프로세스

```
1. 변경된 파일 목록 수집
     ↓
2. Content Hash 비교
     ↓
3. 변경된 파일만 재파싱 (Layer 1: Structural IR)
     ↓
4. 영향받는 Semantic IR 재생성 (Layer 5)
     ↓
5. GlobalContext 증분 업데이트 (Layer 4)
     ↓
6. 인덱스 증분 업데이트 (Layer 7)
     ↓
7. 의존하는 파일들 전파 분석
```

### 코드 예시

```python
# 증분 업데이트
ir_docs, global_ctx, retrieval_index, diag_idx, pkg_idx = await builder.build_incremental(
    changed_files=[Path("src/calc.py")],
    existing_irs=ir_docs,
    global_ctx=global_ctx,
    retrieval_index=retrieval_index,
)

# Semantic IR Delta 적용
new_snapshot, new_index = semantic_builder.apply_delta(
    ir_doc=updated_ir_doc,
    existing_snapshot=old_snapshot,
    existing_index=old_index,
)
```

---

## 20. Async/Generator 지원 상세

### Async/Await 모델링

```python
async def fetch_data(url):
    # SUSPEND 블록: await 시작
    response = await http_client.get(url)
    # RESUME 블록: await 완료

    return response.json()
```

**CFG 변환**:
```
ENTRY
  ↓
SUSPEND (await http_client.get(url))
  ↓
RESUME (response = ...)
  ↓
EXIT
```

**BFG 메타데이터**:
```python
suspend_block = BasicFlowBlock(
    kind=BFGBlockKind.SUSPEND,
    is_async_call=True,
    async_target_expression="http_client.get(url)",
)

resume_block = BasicFlowBlock(
    kind=BFGBlockKind.RESUME,
    resume_from_suspend_id=suspend_block.id,
    async_result_variable="response",
)
```

### Generator/Coroutine 모델링

```python
def fibonacci():
    a, b = 0, 1
    while True:
        yield a  # YIELD 블록 (State 1)
        a, b = b, a + b  # RESUME_YIELD 블록
```

**CFG 변환** (상태 머신):
```
DISPATCHER (State Router)
  ├─ State 0 → ENTRY
  ├─ State 1 → YIELD (yield a)
  └─ State N → ...
```

**BFG 메타데이터**:
```python
dispatcher_block = BasicFlowBlock(
    kind=BFGBlockKind.DISPATCHER,
    generator_dispatch_table={
        0: entry_block.id,
        1: yield_block.id,
    },
)

yield_block = BasicFlowBlock(
    kind=BFGBlockKind.YIELD,
    generator_state_id=1,
    generator_next_state=1,  # 다시 자기로
    generator_yield_value="a",
    generator_all_locals=["a", "b"],  # 보존할 변수
)
```
