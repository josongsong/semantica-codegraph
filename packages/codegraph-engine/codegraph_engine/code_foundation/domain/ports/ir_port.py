"""
IR (Intermediate Representation) Port

Port for accessing IR data without depending on infrastructure.
Hexagonal Architecture: Domain defines interface, Infrastructure implements.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Span:
    """Source code location"""

    start_line: int
    end_line: int
    start_col: int | None = None
    end_col: int | None = None


@dataclass(frozen=True)
class IRNode:
    """
    IR Node abstraction (Domain layer)

    Minimal interface needed by Domain logic.
    Infrastructure provides full implementation.
    """

    id: str
    kind: str
    name: str
    file_path: str | None
    span: Span | None
    attrs: dict[str, Any]


class IRNodePort(Protocol):
    """
    Port for IR Node operations

    Dependency Inversion: Domain defines interface
    """

    @property
    def id(self) -> str: ...

    @property
    def kind(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def file_path(self) -> str | None: ...

    @property
    def span(self) -> Span | None: ...

    @property
    def attrs(self) -> dict[str, Any]: ...


class IRDocumentPort(Protocol):
    """
    Port for IR Document operations

    Hexagonal Architecture:
    - Domain Layer: Defines this interface (Port)
    - Infrastructure Layer: Implements this interface (Adapter)
    - Application Layer: Uses through dependency injection

    Example:
        ```python
        class TaintEngine:
            def __init__(self, ir_document: IRDocumentPort):
                self.ir = ir_document

            def analyze(self):
                for node in self.ir.nodes:
                    ...
        ```
    """

    @property
    def nodes(self) -> list[IRNodePort]:
        """
        All nodes in IR document (REQUIRED)

        Returns:
            List of all IR nodes
        """
        ...

    def find_nodes_by_name(self, name: str) -> list[IRNodePort]:
        """
        Find IR nodes by name

        Args:
            name: Node name to search

        Returns:
            List of matching nodes
        """
        ...

    def get_all_nodes(self) -> list[IRNodePort]:
        """
        Get all nodes in IR

        Returns:
            All IR nodes
        """
        ...

    def find_node_by_id(self, node_id: str) -> IRNodePort | None:
        """
        Find node by ID

        Args:
            node_id: Node ID

        Returns:
            Node if found, None otherwise
        """
        ...
