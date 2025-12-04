# SOTA급 IR 구현 계획 (SCIP 호환)

**목표**: 확장성, 구조성 모두 SOTA급이며 SCIP와 동일한 기능을 제공하는 차세대 IR 구축

**Timeline**: 8주 (4 Phases)  
**Status**: 🟡 Planning (2025-12-04)

---

## 📊 현재 상태 평가

### ✅ 잘 구현된 부분 (70%)
```
✓ 기본 구조: Node, Edge, Span
✓ 의미론적 IR: TypeEntity, SignatureEntity, CFG, BFG, DFG
✓ Cross-file linking: Import resolution, External symbols
✓ LSP 통합: Pyright (hover, definition, references)
✓ 계층적 청킹: 6-level chunk hierarchy
✓ 증분 업데이트: Incremental parsing
```

### ❌ SCIP 대비 부족 (30%)
```
✗ Occurrence Roles: definition/reference 구분 없음
✗ Diagnostics: 에러/경고 저장 안 됨
✗ Symbol Metadata: deprecated, visibility, test-only 등
✗ Hover Content: IR에 저장 안 됨
✗ Relationship Metadata: Edge 역할 구분 없음
✗ Package Metadata: 외부 패키지 정보 없음
✗ Moniker: Cross-project 심볼 식별자 없음
✗ SCIP Format: 표준 descriptor 호환 불가
```

---

## 🎯 SCIP 기능 매핑표

| SCIP 기능 | 현재 상태 | 구현 우선순위 | Phase |
|-----------|----------|-------------|-------|
| **Symbol** | ✅ Node | - | Done |
| **Occurrence** | ⚠️ Edge만 존재 | P0 (Critical) | Phase 1 |
| **SymbolRole** (def/ref/import) | ❌ 없음 | P0 (Critical) | Phase 1 |
| **Diagnostic** (error/warning) | ❌ 없음 | P0 (Critical) | Phase 1 |
| **Relationship** | ✅ Edge | P1 (추가 메타데이터) | Phase 2 |
| **SymbolMetadata** | ⚠️ 부분적 | P1 (High) | Phase 2 |
| **Document** | ✅ IRDocument | P2 (확장) | Phase 3 |
| **Moniker** (external) | ❌ 없음 | P2 (Medium) | Phase 3 |
| **Package** | ❌ 없음 | P2 (Medium) | Phase 3 |
| **SymbolDescriptor** | ⚠️ Custom FQN | P3 (Nice) | Phase 4 |

---

## 🏗️ Architecture: Enhanced IR v2.0

```
┌─────────────────────────────────────────────────────────────────┐
│                       IRDocument v2.0                            │
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Layer 1: Structural IR (Syntax Tree)                        │ │
│ │   • Nodes (Symbol definitions)                              │ │
│ │   • Edges (Relationships)                                   │ │
│ │   • Spans (Source locations)                                │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Layer 2: Semantic IR (Type System + Control Flow)          │ │
│ │   • TypeEntities (Type system)                              │ │
│ │   • SignatureEntities (Function signatures)                 │ │
│ │   • CFG/BFG/DFG (Control/data flow)                        │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Layer 3: Occurrence IR (SCIP-compatible) ⭐ NEW             │ │
│ │   • Occurrences (All symbol usages with roles)              │ │
│ │   • SymbolRoles (DEFINITION | REFERENCE | IMPORT...)        │ │
│ │   • Diagnostics (Errors, warnings, hints)                   │ │
│ │   • HoverContent (Formatted documentation)                  │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Layer 4: Cross-Project IR (External References) ⭐ NEW      │ │
│ │   • Monikers (Cross-project symbol IDs)                     │ │
│ │   • PackageMetadata (External dependencies)                 │ │
│ │   • ExternalSymbols (Standard library, 3rd party)           │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Layer 5: Index & Query (Fast Access) ⭐ ENHANCED            │ │
│ │   • Symbol Index (FQN → Symbol)                             │ │
│ │   • Occurrence Index (Location → Occurrences)               │ │
│ │   • Diagnostic Index (File → Diagnostics)                   │ │
│ │   • Reference Index (Symbol → All usages)                   │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📋 Phase별 구현 계획

### Phase 1: Occurrence & Diagnostics (2주) ⭐ Critical

**목표**: SCIP 핵심 기능인 occurrence role과 diagnostics 구현

#### 1.1 Occurrence System

```python
# src/contexts/code_foundation/infrastructure/ir/models/occurrence.py

from dataclasses import dataclass, field
from enum import IntFlag

class SymbolRole(IntFlag):
    """SCIP-compatible symbol roles (비트 플래그)"""
    NONE = 0
    DEFINITION = 1           # 심볼 정의
    IMPORT = 2              # import 문
    WRITE_ACCESS = 4        # 변수 할당
    READ_ACCESS = 8         # 변수 읽기
    GENERATED = 16          # 코드 생성
    TEST = 32               # 테스트 코드
    FORWARD_DEFINITION = 64  # 전방 선언

@dataclass(slots=True)
class Occurrence:
    """
    심볼 사용처 (SCIP occurrence).
    
    모든 심볼 참조를 추적하며 정의/참조/임포트 등을 구분.
    """
    id: str                    # occurrence:file:line:col
    symbol_id: str            # 참조하는 심볼 ID
    span: Span                # 위치
    roles: SymbolRole         # 비트 플래그로 역할 표현
    enclosing_range: Span | None = None  # 둘러싼 범위 (함수/클래스)
    
    # 추가 메타데이터
    is_implicit: bool = False  # 암시적 참조 (자동 생성)
    syntax_kind: str | None = None  # "identifier", "import_statement" 등
    
    def is_definition(self) -> bool:
        return bool(self.roles & SymbolRole.DEFINITION)
    
    def is_reference(self) -> bool:
        return bool(self.roles & SymbolRole.READ_ACCESS)
    
    def is_write(self) -> bool:
        return bool(self.roles & SymbolRole.WRITE_ACCESS)

@dataclass
class OccurrenceIndex:
    """Occurrence 고속 검색 인덱스"""
    by_symbol: dict[str, list[str]] = field(default_factory=dict)  # symbol_id → occurrence_ids
    by_file: dict[str, list[str]] = field(default_factory=dict)    # file_path → occurrence_ids
    by_role: dict[SymbolRole, list[str]] = field(default_factory=dict)  # role → occurrence_ids
```

#### 1.2 Diagnostics System

```python
# src/contexts/code_foundation/infrastructure/ir/models/diagnostic.py

from dataclasses import dataclass, field
from enum import Enum

class Severity(str, Enum):
    """진단 심각도"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HINT = "hint"

@dataclass(slots=True)
class DiagnosticRelatedInformation:
    """관련 정보 (다른 위치 참조)"""
    location: Span
    file_path: str
    message: str

@dataclass(slots=True)
class Diagnostic:
    """
    코드 진단 정보 (에러, 경고, 힌트).
    
    LSP 및 linter 출력을 표준화하여 저장.
    """
    id: str                    # diagnostic:file:line:col:source:code
    severity: Severity
    span: Span
    file_path: str
    message: str
    source: str               # "pyright", "ruff", "eslint", "mypy" 등
    code: str | None = None   # "type-error", "unused-import", "E501" 등
    
    # 추가 정보
    related_information: list[DiagnosticRelatedInformation] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)  # "deprecated", "unnecessary" 등
    fix_available: bool = False
    
    def is_error(self) -> bool:
        return self.severity == Severity.ERROR

@dataclass
class DiagnosticIndex:
    """Diagnostic 고속 검색 인덱스"""
    by_file: dict[str, list[str]] = field(default_factory=dict)      # file → diagnostic_ids
    by_severity: dict[Severity, list[str]] = field(default_factory=dict)  # severity → ids
    by_source: dict[str, list[str]] = field(default_factory=dict)    # source → ids
```

#### 1.3 IRDocument v2 확장

```python
# src/contexts/code_foundation/infrastructure/ir/models/document.py (수정)

@dataclass
class IRDocument:
    """
    Complete IR snapshot v2.0 (SCIP-compatible)
    """
    # [Required] Identity
    repo_id: str
    snapshot_id: str
    schema_version: str = "2.0.0"  # ⬆️ 버전 업
    
    # [Layer 1] Structural IR
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    
    # [Layer 2] Semantic IR
    types: list[TypeEntity] = field(default_factory=list)
    signatures: list[SignatureEntity] = field(default_factory=list)
    cfgs: list[ControlFlowGraph] = field(default_factory=list)
    
    # [Layer 3] Occurrence IR ⭐ NEW
    occurrences: list[Occurrence] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    
    # [Indexes]
    indexes: IRIndexes = field(default_factory=IRIndexes)
    
    # [Metadata]
    meta: dict[str, Any] = field(default_factory=dict)

@dataclass
class IRIndexes:
    """모든 인덱스를 하나로 통합"""
    # 기존 인덱스
    node_by_id: dict[str, Node] = field(default_factory=dict)
    edge_by_id: dict[str, Edge] = field(default_factory=dict)
    
    # 새 인덱스 ⭐
    occurrence_index: OccurrenceIndex = field(default_factory=OccurrenceIndex)
    diagnostic_index: DiagnosticIndex = field(default_factory=DiagnosticIndex)
```

#### 1.4 Occurrence Generator

```python
# src/contexts/code_foundation/infrastructure/ir/occurrence_generator.py

class OccurrenceGenerator:
    """
    Node/Edge에서 Occurrence를 생성하는 변환기.
    
    기존 IR에서 모든 심볼 사용처를 추출하고 역할을 부여.
    """
    
    def generate(self, ir_doc: IRDocument) -> list[Occurrence]:
        """IRDocument에서 모든 occurrence 생성"""
        occurrences: list[Occurrence] = []
        
        # 1. Node → Definition occurrences
        for node in ir_doc.nodes:
            if node.kind in (NodeKind.CLASS, NodeKind.FUNCTION, NodeKind.METHOD):
                occ = Occurrence(
                    id=f"occ:{node.id}:def",
                    symbol_id=node.id,
                    span=node.span,
                    roles=SymbolRole.DEFINITION,
                    enclosing_range=node.span,
                )
                occurrences.append(occ)
        
        # 2. Edge → Reference occurrences
        for edge in ir_doc.edges:
            if edge.kind == EdgeKind.CALLS:
                # 함수 호출 = READ_ACCESS
                occ = Occurrence(
                    id=f"occ:{edge.id}:ref",
                    symbol_id=edge.target_id,
                    span=edge.span,
                    roles=SymbolRole.READ_ACCESS,
                )
                occurrences.append(occ)
            
            elif edge.kind == EdgeKind.IMPORTS:
                # Import = IMPORT
                occ = Occurrence(
                    id=f"occ:{edge.id}:import",
                    symbol_id=edge.target_id,
                    span=edge.span,
                    roles=SymbolRole.IMPORT,
                )
                occurrences.append(occ)
            
            elif edge.kind == EdgeKind.WRITES:
                # 변수 할당 = WRITE_ACCESS
                occ = Occurrence(
                    id=f"occ:{edge.id}:write",
                    symbol_id=edge.target_id,
                    span=edge.span,
                    roles=SymbolRole.WRITE_ACCESS,
                )
                occurrences.append(occ)
            
            elif edge.kind == EdgeKind.READS:
                # 변수 읽기 = READ_ACCESS
                occ = Occurrence(
                    id=f"occ:{edge.id}:read",
                    symbol_id=edge.target_id,
                    span=edge.span,
                    roles=SymbolRole.READ_ACCESS,
                )
                occurrences.append(occ)
        
        return occurrences
```

#### 1.5 Diagnostic Collector

```python
# src/contexts/code_foundation/infrastructure/ir/diagnostic_collector.py

class DiagnosticCollector:
    """
    다양한 소스에서 Diagnostic을 수집.
    
    Sources:
    - Pyright LSP
    - Ruff (Python linter)
    - ESLint (TypeScript/JavaScript)
    - Validation errors (IR 자체 검증)
    """
    
    def __init__(self):
        self.pyright_client: PyrightLSPClient | None = None
        self.ruff_enabled = False
        self.eslint_enabled = False
    
    async def collect_all(
        self,
        file_paths: list[str],
        ir_doc: IRDocument,
    ) -> list[Diagnostic]:
        """모든 소스에서 진단 정보 수집"""
        diagnostics: list[Diagnostic] = []
        
        # 1. Pyright diagnostics
        if self.pyright_client:
            for file_path in file_paths:
                pyright_diags = await self._collect_pyright(file_path)
                diagnostics.extend(pyright_diags)
        
        # 2. Ruff diagnostics (Python)
        if self.ruff_enabled:
            python_files = [f for f in file_paths if f.endswith('.py')]
            ruff_diags = await self._collect_ruff(python_files)
            diagnostics.extend(ruff_diags)
        
        # 3. IR validation errors
        validation_diags = self._collect_validation_errors(ir_doc)
        diagnostics.extend(validation_diags)
        
        return diagnostics
    
    async def _collect_pyright(self, file_path: str) -> list[Diagnostic]:
        """Pyright LSP에서 진단 정보 가져오기"""
        # LSP textDocument/publishDiagnostics 사용
        raw_diags = await self.pyright_client.get_diagnostics(file_path)
        
        return [
            Diagnostic(
                id=f"diag:{file_path}:{d['range']['start']['line']}:pyright:{d.get('code', 'unknown')}",
                severity=self._map_severity(d['severity']),
                span=self._convert_lsp_range(d['range']),
                file_path=file_path,
                message=d['message'],
                source="pyright",
                code=str(d.get('code')),
            )
            for d in raw_diags
        ]
```

**Deliverables** (Phase 1):
```
✓ occurrence.py: Occurrence, SymbolRole, OccurrenceIndex
✓ diagnostic.py: Diagnostic, Severity, DiagnosticIndex
✓ occurrence_generator.py: Node/Edge → Occurrence 변환
✓ diagnostic_collector.py: LSP/Linter → Diagnostic 수집
✓ Tests: 50+ test cases
✓ Migration script: v1 → v2 변환
```

---

### Phase 2: Symbol Metadata & Hover (2주)

**목표**: 심볼 메타데이터와 hover content 강화

#### 2.1 Symbol Metadata

```python
# src/contexts/code_foundation/infrastructure/ir/models/metadata.py

from enum import Enum

class Visibility(str, Enum):
    """심볼 가시성"""
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    INTERNAL = "internal"

@dataclass(slots=True)
class SymbolMetadata:
    """
    SCIP-compatible symbol metadata.
    
    심볼의 속성을 표현 (deprecated, abstract, static 등).
    """
    # 상태 플래그
    is_deprecated: bool = False
    is_abstract: bool = False
    is_readonly: bool = False
    is_static: bool = False
    is_final: bool = False
    is_test_only: bool = False
    is_async: bool = False
    
    # 가시성
    visibility: Visibility | None = None
    
    # Deprecation
    deprecation_message: str | None = None
    since_version: str | None = None
    
    # Framework annotations (Django, FastAPI 등)
    framework_tags: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)

# Node 모델 확장
@dataclass(slots=True)
class Node:
    # ... 기존 필드 ...
    
    # ⭐ NEW: Metadata
    metadata: SymbolMetadata | None = None
    
    # ⭐ NEW: Hover content (LSP hover 결과 저장)
    hover_content: str | None = None  # Markdown formatted
```

#### 2.2 Metadata Extractor

```python
# src/contexts/code_foundation/infrastructure/ir/metadata_extractor.py

class MetadataExtractor:
    """
    AST + LSP에서 Symbol Metadata 추출.
    """
    
    def extract(self, node: Node, ast_node: TSNode, lsp_client: PyrightLSPClient | None) -> SymbolMetadata:
        """심볼의 메타데이터 추출"""
        metadata = SymbolMetadata()
        
        # 1. Decorators에서 추출
        decorators = node.attrs.get("decorators", [])
        metadata.decorators = decorators
        
        # @deprecated, @abstractmethod 등
        if "deprecated" in decorators or "Deprecated" in decorators:
            metadata.is_deprecated = True
        
        if "abstractmethod" in decorators or "abc.abstractmethod" in decorators:
            metadata.is_abstract = True
        
        if "staticmethod" in decorators:
            metadata.is_static = True
        
        # pytest 마커
        if any(d.startswith("pytest.") for d in decorators):
            metadata.is_test_only = True
        
        # 2. Visibility (Python convention)
        if node.name:
            if node.name.startswith("__") and not node.name.endswith("__"):
                metadata.visibility = Visibility.PRIVATE
            elif node.name.startswith("_"):
                metadata.visibility = Visibility.INTERNAL
            else:
                metadata.visibility = Visibility.PUBLIC
        
        # 3. async
        if node.attrs.get("is_async"):
            metadata.is_async = True
        
        # 4. Framework tags (FastAPI, Django 등)
        metadata.framework_tags = self._extract_framework_tags(node, decorators)
        
        return metadata
    
    def _extract_framework_tags(self, node: Node, decorators: list[str]) -> list[str]:
        """프레임워크 태그 추출"""
        tags = []
        
        # FastAPI
        if any(d.startswith("app.") for d in decorators):
            tags.append("fastapi")
            if "app.get" in decorators:
                tags.append("route:GET")
            elif "app.post" in decorators:
                tags.append("route:POST")
        
        # Django
        if "login_required" in decorators:
            tags.append("django")
            tags.append("auth_required")
        
        return tags
```

#### 2.3 Hover Content Generator

```python
# src/contexts/code_foundation/infrastructure/ir/hover_generator.py

class HoverContentGenerator:
    """
    LSP hover + docstring을 결합하여 Markdown hover content 생성.
    """
    
    def __init__(self, lsp_client: PyrightLSPClient | None = None):
        self.lsp_client = lsp_client
    
    async def generate(self, node: Node, source_code: str) -> str:
        """Hover content 생성"""
        parts = []
        
        # 1. Signature (from LSP or IR)
        if self.lsp_client and node.span:
            hover_result = await self.lsp_client.hover(
                Path(node.file_path),
                node.span.start_line,
                node.span.start_col,
            )
            if hover_result and hover_result.get("type"):
                parts.append(f"```python\n{hover_result['type']}\n```")
        
        # 2. Docstring
        if node.docstring:
            parts.append(node.docstring)
        
        # 3. Metadata badges
        if node.metadata:
            badges = []
            if node.metadata.is_deprecated:
                badges.append("⚠️ **Deprecated**")
            if node.metadata.is_test_only:
                badges.append("🧪 **Test Only**")
            if node.metadata.is_abstract:
                badges.append("🔷 **Abstract**")
            
            if badges:
                parts.append(" ".join(badges))
        
        # 4. Framework info
        if node.metadata and node.metadata.framework_tags:
            parts.append(f"*Framework*: {', '.join(node.metadata.framework_tags)}")
        
        return "\n\n".join(parts)
```

**Deliverables** (Phase 2):
```
✓ metadata.py: SymbolMetadata, Visibility
✓ metadata_extractor.py: AST → Metadata
✓ hover_generator.py: LSP + Docstring → Markdown
✓ Node 확장: metadata, hover_content 필드
✓ Tests: 30+ test cases
```

---

### Phase 3: Cross-Project References (2주)

**목표**: 외부 패키지 및 cross-project 참조 지원

#### 3.1 Moniker System

```python
# src/contexts/code_foundation/infrastructure/ir/models/moniker.py

class MonikerKind(str, Enum):
    """Moniker 종류"""
    IMPORT = "import"  # 이 프로젝트에서 import하는 외부 심볼
    EXPORT = "export"  # 이 프로젝트에서 export하는 심볼

class MonikerScheme(str, Enum):
    """패키지 매니저 scheme"""
    PYPI = "pypi"
    NPM = "npm"
    MAVEN = "maven"
    GO = "go"
    CARGO = "cargo"

@dataclass(slots=True)
class Moniker:
    """
    Cross-project symbol identifier.
    
    외부 패키지의 심볼을 고유하게 식별.
    
    Example:
        pypi:requests:2.28.0::Session
        npm:@types/react:18.0.0::FC
    """
    id: str
    scheme: MonikerScheme
    identifier: str  # "package:version::symbol_path"
    kind: MonikerKind
    
    @staticmethod
    def parse(moniker_str: str) -> "Moniker":
        """문자열에서 Moniker 파싱"""
        scheme, rest = moniker_str.split(":", 1)
        return Moniker(
            id=moniker_str,
            scheme=MonikerScheme(scheme),
            identifier=rest,
            kind=MonikerKind.IMPORT,  # 기본값
        )
    
    def to_string(self) -> str:
        """SCIP 형식 문자열"""
        return f"{self.scheme.value}:{self.identifier}"
```

#### 3.2 Package Metadata

```python
# src/contexts/code_foundation/infrastructure/ir/models/package.py

@dataclass
class PackageMetadata:
    """
    외부 패키지 메타데이터.
    
    패키지 정보, 버전, 라이선스 등.
    """
    id: str  # "pypi:requests:2.28.0"
    manager: str  # "pip", "npm", "maven"
    name: str
    version: str
    
    # Optional
    license: str | None = None
    homepage: str | None = None
    description: str | None = None
    
    # Dependencies
    dependencies: list[str] = field(default_factory=list)
    
    # Import tracking
    imported_symbols: set[str] = field(default_factory=set)
    import_count: int = 0

# IRDocument 확장
@dataclass
class IRDocument:
    # ... 기존 필드 ...
    
    # ⭐ NEW: Cross-project
    monikers: dict[str, Moniker] = field(default_factory=dict)  # symbol_id → Moniker
    packages: dict[str, PackageMetadata] = field(default_factory=dict)  # package_id → Metadata
```

#### 3.3 External Symbol Resolver

```python
# src/contexts/code_foundation/infrastructure/ir/external_resolver.py

class ExternalSymbolResolver:
    """
    외부 심볼 해석 및 Moniker 생성.
    
    import 구문을 분석하여 외부 패키지 심볼에 moniker 부여.
    """
    
    def __init__(self):
        self.stdlib_modules = self._load_stdlib_modules()
        self.installed_packages = self._scan_installed_packages()
    
    def resolve(self, import_node: Node, ir_doc: IRDocument) -> Moniker | None:
        """Import node에서 Moniker 생성"""
        module_name = import_node.attrs.get("module")
        if not module_name:
            return None
        
        # 1. Standard library인지 확인
        if module_name in self.stdlib_modules:
            # stdlib는 moniker 불필요 (언어 자체 일부)
            return None
        
        # 2. Installed package 확인
        package_info = self._find_package(module_name)
        if not package_info:
            return None
        
        # 3. Moniker 생성
        symbol_path = import_node.attrs.get("imported_names", [])
        identifier = f"{package_info['name']}:{package_info['version']}::{'.'.join(symbol_path)}"
        
        moniker = Moniker(
            id=f"moniker:{identifier}",
            scheme=MonikerScheme.PYPI,  # Python 예시
            identifier=identifier,
            kind=MonikerKind.IMPORT,
        )
        
        # 4. IRDocument에 등록
        ir_doc.monikers[import_node.id] = moniker
        
        # 5. Package metadata 업데이트
        package_id = f"pypi:{package_info['name']}:{package_info['version']}"
        if package_id not in ir_doc.packages:
            ir_doc.packages[package_id] = PackageMetadata(
                id=package_id,
                manager="pip",
                name=package_info['name'],
                version=package_info['version'],
            )
        
        ir_doc.packages[package_id].import_count += 1
        ir_doc.packages[package_id].imported_symbols.add('.'.join(symbol_path))
        
        return moniker
    
    def _find_package(self, module_name: str) -> dict | None:
        """설치된 패키지에서 모듈 찾기"""
        # pip show, package.json 등에서 패키지 정보 가져오기
        for pkg in self.installed_packages:
            if module_name.startswith(pkg['name']):
                return pkg
        return None
```

**Deliverables** (Phase 3):
```
✓ moniker.py: Moniker, MonikerScheme, MonikerKind
✓ package.py: PackageMetadata
✓ external_resolver.py: Import → Moniker 해석
✓ IRDocument 확장: monikers, packages 필드
✓ Tests: 25+ test cases
```

---

### Phase 4: SCIP Compatibility & Optimization (2주)

**목표**: SCIP 표준 포맷 지원 및 성능 최적화

#### 4.1 SCIP Descriptor Format

```python
# src/contexts/code_foundation/infrastructure/ir/scip_formatter.py

class SCIPDescriptor:
    """
    SCIP standard descriptor format.
    
    Format: scip-<language> <manager> <name> <version> <path>/<symbol>#
    Example: scip-python pypi semantica v1.0.0 src/foundation/`ir.py`/IRDocument#
    """
    
    @staticmethod
    def format_symbol(node: Node, repo_id: str, version: str) -> str:
        """Node → SCIP descriptor"""
        # 언어
        lang = f"scip-{node.language}"
        
        # 패키지 정보
        manager = "local"  # 로컬 프로젝트
        name = repo_id
        ver = version
        
        # 경로 (백틱으로 escape)
        path = node.file_path.replace("/", "/")
        
        # 심볼 경로
        symbol_path = node.fqn.replace(".", "/")
        
        # 심볼 종류에 따른 suffix
        suffix = "#"  # class/function
        if node.kind == NodeKind.METHOD:
            suffix = "#()."  # method
        elif node.kind == NodeKind.FIELD:
            suffix = "#"  # field
        
        return f"{lang} {manager} {name} {ver} {path}/{symbol_path}{suffix}"
    
    @staticmethod
    def parse_descriptor(descriptor: str) -> dict:
        """SCIP descriptor → dict 파싱"""
        parts = descriptor.split()
        if len(parts) < 5:
            raise ValueError(f"Invalid SCIP descriptor: {descriptor}")
        
        return {
            "language": parts[0].replace("scip-", ""),
            "manager": parts[1],
            "package": parts[2],
            "version": parts[3],
            "path": parts[4].split("/")[0],
            "symbol": parts[4].split("/")[1] if "/" in parts[4] else "",
        }
```

#### 4.2 SCIP Export

```python
# src/contexts/code_foundation/infrastructure/ir/scip_exporter.py

class SCIPExporter:
    """
    IRDocument → SCIP format (.scip 파일) 변환.
    
    SCIP 도구와 호환되는 포맷으로 내보내기.
    """
    
    def export(self, ir_doc: IRDocument, output_path: Path):
        """SCIP 프로토콜 버퍼 형식으로 export"""
        import scip_pb2  # SCIP protobuf
        
        scip_index = scip_pb2.Index()
        scip_index.metadata.version = scip_pb2.ProtocolVersion.UnstableVersion
        scip_index.metadata.project_root = f"file://{ir_doc.repo_id}"
        
        # Document 변환
        for file_path in self._get_unique_files(ir_doc):
            doc = self._convert_document(ir_doc, file_path)
            scip_index.documents.append(doc)
        
        # 파일 저장
        with open(output_path, "wb") as f:
            f.write(scip_index.SerializeToString())
    
    def _convert_document(self, ir_doc: IRDocument, file_path: str) -> scip_pb2.Document:
        """파일별 SCIP Document 생성"""
        doc = scip_pb2.Document()
        doc.relative_path = file_path
        doc.language = self._detect_language(file_path)
        
        # Occurrences 변환
        file_occurrences = [
            occ for occ in ir_doc.occurrences
            if self._get_file_from_span(occ.span) == file_path
        ]
        
        for occ in file_occurrences:
            scip_occ = self._convert_occurrence(occ, ir_doc)
            doc.occurrences.append(scip_occ)
        
        # Symbols 변환
        file_nodes = [n for n in ir_doc.nodes if n.file_path == file_path]
        for node in file_nodes:
            symbol_info = self._convert_symbol_info(node, ir_doc)
            doc.symbols.append(symbol_info)
        
        return doc
```

#### 4.3 Performance Optimization

```python
# src/contexts/code_foundation/infrastructure/ir/optimizer.py

class IROptimizer:
    """
    IR 성능 최적화.
    
    - 인덱스 재구축
    - 중복 제거
    - 메모리 압축
    """
    
    def optimize(self, ir_doc: IRDocument) -> IRDocument:
        """IRDocument 최적화"""
        
        # 1. 인덱스 재구축 (O(n) → O(1) lookup)
        self._rebuild_indexes(ir_doc)
        
        # 2. 중복 occurrence 제거
        ir_doc.occurrences = self._deduplicate_occurrences(ir_doc.occurrences)
        
        # 3. Span 정규화 (메모리 절약)
        self._normalize_spans(ir_doc)
        
        # 4. Diagnostic 중복 제거
        ir_doc.diagnostics = self._deduplicate_diagnostics(ir_doc.diagnostics)
        
        return ir_doc
    
    def _rebuild_indexes(self, ir_doc: IRDocument):
        """모든 인덱스 재구축"""
        # Node index
        ir_doc.indexes.node_by_id = {n.id: n for n in ir_doc.nodes}
        
        # Occurrence index
        ir_doc.indexes.occurrence_index.by_symbol.clear()
        for occ in ir_doc.occurrences:
            ir_doc.indexes.occurrence_index.by_symbol.setdefault(occ.symbol_id, []).append(occ.id)
        
        # Diagnostic index
        ir_doc.indexes.diagnostic_index.by_file.clear()
        for diag in ir_doc.diagnostics:
            ir_doc.indexes.diagnostic_index.by_file.setdefault(diag.file_path, []).append(diag.id)
```

**Deliverables** (Phase 4):
```
✓ scip_formatter.py: SCIP descriptor 포맷 변환
✓ scip_exporter.py: IRDocument → .scip 파일
✓ optimizer.py: 성능 최적화
✓ Benchmark: 10,000+ 심볼 처리 < 5초
✓ Tests: 20+ test cases
```

---

## 📈 성능 목표 (Benchmarks)

### Indexing Performance
```
작은 프로젝트 (< 100 files):
  ✓ Full indexing: < 10 seconds
  ✓ Occurrence generation: < 2 seconds
  ✓ Diagnostic collection: < 3 seconds

중형 프로젝트 (100-1000 files):
  ✓ Full indexing: < 60 seconds
  ✓ Incremental: < 5 seconds
  ✓ Memory: < 2GB

대형 프로젝트 (1000-10000 files):
  ✓ Full indexing: < 10 minutes
  ✓ Incremental: < 30 seconds
  ✓ Memory: < 8GB
```

### Query Performance
```
✓ Find references: < 100ms (10K symbols)
✓ Find definitions: < 50ms
✓ Symbol search: < 200ms
✓ Diagnostic lookup: < 10ms (per file)
```

---

## 🧪 검증 방법

### 1. Unit Tests
```bash
# 각 Phase별 50+ tests
pytest tests/ir/test_occurrence.py -v
pytest tests/ir/test_diagnostic.py -v
pytest tests/ir/test_metadata.py -v
pytest tests/ir/test_moniker.py -v
```

### 2. Integration Tests
```bash
# 실제 오픈소스 프로젝트로 검증
pytest tests/integration/test_ir_sota.py --real-repos
```

### 3. SCIP Compatibility Test
```bash
# SCIP 도구로 검증
scip print --to=json output.scip
scip stats output.scip
```

### 4. Performance Benchmark
```bash
# 성능 벤치마크
python benchmark/ir_benchmark.py --size=large
```

---

## 🔄 Migration Strategy

### v1 → v2 Migration

```python
# scripts/migrate_ir_v1_to_v2.py

class IRMigrator:
    """IR v1 → v2 마이그레이션"""
    
    def migrate(self, old_ir: IRDocumentV1) -> IRDocumentV2:
        """v1 → v2 변환"""
        new_ir = IRDocumentV2(
            repo_id=old_ir.repo_id,
            snapshot_id=old_ir.snapshot_id,
            schema_version="2.0.0",
            
            # Copy existing data
            nodes=old_ir.nodes,
            edges=old_ir.edges,
            types=old_ir.types,
            signatures=old_ir.signatures,
            cfgs=old_ir.cfgs,
        )
        
        # Generate new data
        occurrence_gen = OccurrenceGenerator()
        new_ir.occurrences = occurrence_gen.generate(new_ir)
        
        metadata_extractor = MetadataExtractor()
        for node in new_ir.nodes:
            node.metadata = metadata_extractor.extract(node, None, None)
        
        # Build indexes
        optimizer = IROptimizer()
        new_ir = optimizer.optimize(new_ir)
        
        return new_ir
```

### Backward Compatibility

```python
# v2 IR은 v1 API와 호환
class BackwardCompatLayer:
    """v1 API 호환성 레이어"""
    
    @staticmethod
    def get_references_v1(ir_doc: IRDocumentV2, symbol_id: str) -> list[Edge]:
        """v1 API: Edge 반환"""
        # v2의 Occurrence → v1의 Edge 변환
        occurrences = [
            occ for occ in ir_doc.occurrences
            if occ.symbol_id == symbol_id and occ.is_reference()
        ]
        
        return [
            Edge(
                id=f"edge:{occ.id}",
                kind=EdgeKind.REFERENCES,
                source_id=occ.enclosing_range,  # 근사값
                target_id=occ.symbol_id,
                span=occ.span,
            )
            for occ in occurrences
        ]
```

---

## 📊 Progress Tracking

### Weekly Milestones

**Week 1-2: Phase 1**
- [ ] Occurrence models & generator
- [ ] Diagnostic models & collector
- [ ] Unit tests (50+)
- [ ] Integration with existing pipeline

**Week 3-4: Phase 2**
- [ ] Symbol metadata extractor
- [ ] Hover content generator
- [ ] Node model extensions
- [ ] Unit tests (30+)

**Week 5-6: Phase 3**
- [ ] Moniker system
- [ ] Package metadata
- [ ] External symbol resolver
- [ ] Unit tests (25+)

**Week 7-8: Phase 4**
- [ ] SCIP formatter & exporter
- [ ] Performance optimization
- [ ] Migration scripts
- [ ] Final benchmarks & docs

---

## 🎯 Success Criteria

### Functional Requirements
```
✓ SCIP 호환: .scip 파일 export 가능
✓ Occurrence 구분: definition/reference/import 명확히 구분
✓ Diagnostics: 모든 linter/LSP 에러 저장
✓ Cross-project: Moniker로 외부 패키지 참조
✓ Hover content: Markdown 형식 저장
✓ Backward compat: v1 API 지원
```

### Non-Functional Requirements
```
✓ Performance: 1000 files < 60초
✓ Memory: 1000 files < 2GB
✓ Query speed: Find refs < 100ms
✓ Scalability: 10K files 처리 가능
✓ Test coverage: > 90%
```

---

## 📚 References

- [SCIP Specification](https://github.com/sourcegraph/scip)
- [LSP Specification](https://microsoft.github.io/language-server-protocol/)
- [Tree-sitter Documentation](https://tree-sitter.github.io/)
- [Pyright LSP](https://github.com/microsoft/pyright)

---

**Status**: 📋 Ready for implementation  
**Owner**: Semantica v2 Team  
**Last Updated**: 2025-12-04

