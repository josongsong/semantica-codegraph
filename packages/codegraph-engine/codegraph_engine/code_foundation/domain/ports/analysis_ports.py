"""
Analysis Ports - Hexagonal Architecture

RFC-052: 외부 분석 엔진(Slicer, CallGraph)에 대한 Port 정의

Hexagonal Architecture:
- Domain Layer: 이 Port 인터페이스 정의
- Infrastructure/Adapter: 구현 (reasoning_engine, multi_index)
- Application Layer: DI로 Port 주입받아 사용

SOLID Principles:
- DIP: 상위 레이어(reasoning_engine)에 의존하지 않음
- ISP: 최소 인터페이스만 정의
- OCP: Port 확장 가능
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

# ============================================================
# Slicer Port (Program Slicing)
# ============================================================


class SliceDirection(Enum):
    """Slice direction enum"""

    BACKWARD = "backward"
    FORWARD = "forward"
    BOTH = "both"


@dataclass(frozen=True)
class CodeFragment:
    """
    Code fragment in slice result.

    Immutable data structure (SOLID: Immutability)
    """

    file_path: str
    start_line: int
    end_line: int
    code: str
    node_id: str | None = None


@dataclass
class SliceResult:
    """
    Slice result container.

    Contains:
    - slice_nodes: Set of affected node IDs
    - code_fragments: Actual code pieces
    """

    slice_nodes: set[str] = field(default_factory=set)
    code_fragments: list[CodeFragment] = field(default_factory=list)
    anchor: str = ""
    direction: SliceDirection = SliceDirection.BACKWARD


@runtime_checkable
class SlicerPort(Protocol):
    """
    Port for Program Slicing operations.

    Hexagonal: Domain defines interface, reasoning_engine implements.

    Example:
        ```python
        class SliceUseCase:
            def __init__(self, slicer: SlicerPort):
                self.slicer = slicer

            async def execute(self, anchor: str) -> SliceResult:
                return self.slicer.backward_slice(anchor, max_depth=5)
        ```
    """

    def backward_slice(self, anchor: str, max_depth: int = 5) -> SliceResult:
        """
        Backward slice: 이 노드에 영향을 준 모든 코드.

        Args:
            anchor: Target node ID or symbol name
            max_depth: Maximum dependency depth

        Returns:
            SliceResult with affected nodes and code fragments
        """
        ...

    def forward_slice(self, anchor: str, max_depth: int = 5) -> SliceResult:
        """
        Forward slice: 이 노드가 영향을 주는 모든 코드.

        Args:
            anchor: Source node ID or symbol name
            max_depth: Maximum dependency depth

        Returns:
            SliceResult with affected nodes and code fragments
        """
        ...


# ============================================================
# CallGraph Query Port
# ============================================================


@dataclass(frozen=True)
class CallerInfo:
    """Caller information (immutable)"""

    caller_name: str
    file_path: str
    line: int
    call_type: str = "direct"  # direct | indirect


@dataclass(frozen=True)
class CalleeInfo:
    """Callee information (immutable)"""

    callee_name: str
    file_path: str
    line: int


@runtime_checkable
class CallGraphQueryPort(Protocol):
    """
    Port for CallGraph query operations.

    Hexagonal: Domain defines interface, multi_index implements.

    Example:
        ```python
        class GetCallersUseCase:
            def __init__(self, call_graph: CallGraphQueryPort):
                self.call_graph = call_graph

            async def execute(self, symbol: str) -> list[CallerInfo]:
                return await self.call_graph.get_callers(symbol)
        ```
    """

    async def get_callers(
        self,
        repo_id: str,
        snapshot_id: str,
        symbol_name: str,
        limit: int = 20,
    ) -> list[CallerInfo]:
        """
        Get functions that call a given symbol.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            symbol_name: Target symbol name
            limit: Max results

        Returns:
            List of CallerInfo
        """
        ...

    async def get_callees(
        self,
        repo_id: str,
        snapshot_id: str,
        symbol_name: str,
        limit: int = 20,
    ) -> list[CalleeInfo]:
        """
        Get functions called by a given symbol.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            symbol_name: Source symbol name
            limit: Max results

        Returns:
            List of CalleeInfo
        """
        ...


# ============================================================
# Index Document Port (for document indexing)
# ============================================================


@dataclass
class IndexDocumentDTO:
    """
    Index document data transfer object.

    Domain-level representation (decoupled from multi_index.IndexDocument)
    """

    id: str
    chunk_id: str
    repo_id: str
    snapshot_id: str
    file_path: str
    language: str
    content: str
    identifiers: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)
    start_line: int = 0
    end_line: int = 0
    symbol_id: str | None = None
    symbol_name: str | None = None
    created_at: str | None = None


@runtime_checkable
class IndexAdapterPort(Protocol):
    """
    Port for index document conversion.

    Hexagonal: Domain defines interface, multi_index provides implementation.
    """

    def to_index_document(self, dto: IndexDocumentDTO) -> object:
        """
        Convert DTO to infrastructure IndexDocument.

        Args:
            dto: Domain-level document DTO

        Returns:
            Infrastructure IndexDocument (opaque to domain)
        """
        ...


# ============================================================
# Export all
# ============================================================

__all__ = [
    # Slicer
    "SliceDirection",
    "CodeFragment",
    "SliceResult",
    "SlicerPort",
    # CallGraph
    "CallerInfo",
    "CalleeInfo",
    "CallGraphQueryPort",
    # Index
    "IndexDocumentDTO",
    "IndexAdapterPort",
]
