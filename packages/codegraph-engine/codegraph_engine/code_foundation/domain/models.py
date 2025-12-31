"""
Code Foundation Domain Models

AST, IR, Graph, Chunk 등 코드 분석의 기본 모델

DEPRECATION NOTICE:
    IRDocument in this module is DEPRECATED.
    Use infrastructure.ir.models.IRDocument instead.
    - symbols → nodes
    - Symbol → Node
"""

import warnings
from dataclasses import dataclass, field
from enum import Enum

# Re-export GraphDocument for backward compatibility
try:
    from ..infrastructure.graph.models import GraphDocument
except ImportError:
    GraphDocument = None


class Language(str, Enum):
    """지원 언어"""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    CPP = "cpp"
    UNKNOWN = "unknown"


@dataclass
class ASTDocument:
    """AST 문서"""

    file_path: str
    language: Language
    source_code: str
    tree: object  # Tree-sitter Tree object
    metadata: dict[str, str | int] = field(default_factory=dict)


@dataclass
class Symbol:
    """심볼"""

    name: str
    type: str
    start_line: int
    end_line: int
    start_col: int
    end_col: int
    docstring: str | None = None
    metadata: dict[str, str | int] = field(default_factory=dict)


@dataclass
class UnifiedSymbol:
    """
    언어 중립적 symbol 표현 (SCIP 완전 호환)

    SCIP Format:
    scip-typescript npm package 1.0.0 src/`foo.ts`/`bar`().
    │    │          │   │       │     │   │       │    │ │
    │    │          │   │       │     │   │       │    │╰── Suffix
    │    │          │   │       │     │   │       │    ╰──── Signature
    │    │          │   │       │     │   │       ╰─────────  Symbol
    │    │          │   │       │     │   ╰─────────────────  File
    │    │          │   │       │     ╰─────────────────────  Root
    │    │          │   │       ╰───────────────────────────  Version
    │    │          │   ╰───────────────────────────────────  Name
    │    │          ╰───────────────────────────────────────  Manager
    │    ╰──────────────────────────────────────────────────  Scheme
    """

    # Core Identity (SCIP required)
    scheme: str  # "python", "java", "typescript"
    manager: str  # "pypi", "maven", "npm"
    package: str  # Package name
    version: str  # Package version

    # Path (SCIP required)
    root: str  # Project root or package root
    file_path: str  # Relative file path

    # Symbol (SCIP required)
    descriptor: str  # Symbol descriptor (class#, method()., etc.)

    # Language-specific (backward compat)
    language_fqn: str  # 원본 FQN
    language_kind: str  # 원본 kind

    # Resolved Info
    signature: str | None = None  # Canonical signature
    type_info: str | None = None  # Type information
    generic_params: list[str] | None = None  # Generic parameters

    # Location
    start_line: int | None = None
    end_line: int | None = None
    start_column: int | None = None
    end_column: int | None = None

    def to_scip_descriptor(self) -> str:
        """
        완전한 SCIP descriptor 생성

        Examples:
            scip-python pypi requests 2.31.0 /`__init__.py`/`get`().
            scip-java maven com.example 1.0.0 src/`Main.java`/`MyClass#`
            scip-typescript npm @types/node 18.0.0 /`fs.d.ts`/`readFile`().
        """
        parts = [
            f"scip-{self.scheme}",
            self.manager,
            self.package,
            self.version,
            self.root,
            f"`{self.file_path}`",
            f"`{self.descriptor}`",
        ]
        return " ".join(parts)

    def matches(self, other: "UnifiedSymbol") -> bool:
        """
        Cross-language matching

        Same descriptor + compatible types
        """
        if self.descriptor != other.descriptor:
            return False

        # Generic-aware matching
        if self.generic_params and other.generic_params:
            return self._match_generics(other)

        return True

    def _match_generics(self, other: "UnifiedSymbol") -> bool:
        """Generic parameter matching"""
        if not self.generic_params or not other.generic_params:
            return False

        # Same number of parameters
        if len(self.generic_params) != len(other.generic_params):
            return False

        # TODO: Type compatibility check
        return True

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
    ) -> "UnifiedSymbol":
        """
        Simplified constructor (backward compat)
        """
        manager_map = {
            "python": "pypi",
            "java": "maven",
            "typescript": "npm",
            "javascript": "npm",
        }

        return cls(
            scheme=scheme,
            manager=manager_map.get(scheme, "unknown"),
            package=package,
            version=version,
            root="/",
            file_path=file_path,
            descriptor=descriptor,
            language_fqn=language_fqn,
            language_kind=language_kind,
        )


@dataclass
class Reference:
    """참조"""

    name: str
    target: str
    start_line: int
    end_line: int
    ref_type: str = "call"  # call, import, inheritance, etc.


@dataclass
class IRDocument:
    """
    IR(Intermediate Representation) 문서

    DEPRECATED: Use infrastructure.ir.models.IRDocument instead.

    Migration guide:
    - symbols → nodes
    - Symbol → Node
    - from domain.models import IRDocument
      → from infrastructure.ir.models import IRDocument

    This class will be removed in a future version.
    """

    file_path: str
    language: Language
    symbols: list[Symbol] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    metadata: dict[str, str | int] = field(default_factory=dict)

    def __post_init__(self):
        """Emit deprecation warning on instantiation."""
        warnings.warn(
            "domain.models.IRDocument is deprecated. "
            "Use infrastructure.ir.models.IRDocument with 'nodes' field instead. "
            "See migration guide in class docstring.",
            DeprecationWarning,
            stacklevel=3,
        )

    # NOTE: 'nodes' alias 의도적 미제공
    # - Domain IRDocument는 'symbols' 사용
    # - Infrastructure IRDocument는 'nodes' 사용
    # - _get_nodes_or_convert_symbols()에서 타입 구분 필요


@dataclass
class GraphNode:
    """그래프 노드"""

    id: str
    type: str
    name: str
    file_path: str
    start_line: int
    end_line: int
    properties: dict[str, str | int | bool] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """그래프 엣지"""

    source: str
    target: str
    type: str  # CALLS, IMPORTS, CONTAINS, etc.
    properties: dict[str, str | int | bool] = field(default_factory=dict)


@dataclass
class GraphIndex:
    """
    Graph indexes for efficient queries.

    Compatible with infrastructure.graph.models.GraphIndex
    """

    # Adjacency indexes
    outgoing: dict[str, list[str]] = field(default_factory=dict)  # Node → Outgoing edge IDs
    incoming: dict[str, list[str]] = field(default_factory=dict)  # Node → Incoming edge IDs

    # Reverse indexes (for compatibility with SlicerAdapter, ImpactAnalyzer)
    called_by: dict[str, list[str]] = field(default_factory=dict)  # Function → Callers
    imported_by: dict[str, list[str]] = field(default_factory=dict)  # Module → Importers
    contains_children: dict[str, list[str]] = field(default_factory=dict)  # Parent → Children


@dataclass
class Chunk:
    """청크 (검색 및 임베딩 단위)"""

    id: str
    content: str
    file_path: str
    start_line: int
    end_line: int
    chunk_type: str  # function, class, file, etc.
    language: Language
    metadata: dict[str, str | int | float] = field(default_factory=dict)
