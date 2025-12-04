"""
Code Foundation Domain Models

AST, IR, Graph, Chunk 등 코드 분석의 기본 모델
"""

from dataclasses import dataclass, field
from enum import Enum


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
class Reference:
    """참조"""

    name: str
    target: str
    start_line: int
    end_line: int
    ref_type: str = "call"  # call, import, inheritance, etc.


@dataclass
class IRDocument:
    """IR(Intermediate Representation) 문서"""

    file_path: str
    language: Language
    symbols: list[Symbol] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    metadata: dict[str, str | int] = field(default_factory=dict)


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
class GraphDocument:
    """그래프 문서"""

    file_path: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)


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
