"""
Query Ports - RFC-021 Phase 2 (P0 Fix)

Protocol definitions for QueryEngine dependencies.

Note: TYPE_CHECKING에서도 infrastructure import 금지 (Hexagonal Architecture)
"""

from typing import Any, Protocol


class CallGraphPort(Protocol):
    """
    Call Graph Protocol

    Minimal interface for call graph providers.
    """

    def get_callees(self, func_name: str) -> list[str]:
        """Get functions called by func_name"""
        ...

    def get_functions(self) -> list[str]:
        """Get all functions in graph"""
        ...


class ProjectContextPort(Protocol):
    """
    Project Context Protocol (RFC-021 Phase 2 P0 Fix)

    Defines required interface for DeepAnalyzer.

    Hexagonal Architecture:
        Domain Port는 infrastructure import 금지
        → ir_documents는 list[Any]로 선언

    Attributes:
        call_graph: Call graph (required)
        ir_documents: IR documents (optional, type: Any for DIP)
        node_map: Node ID → Node mapping (optional for location info)
        repo_path: Repository path (optional)
    """

    call_graph: CallGraphPort
    """Call graph (required)"""

    ir_documents: list[Any] | None
    """IR documents for alias analysis (optional, type: Any for DIP)"""

    node_map: dict[str, Any] | None
    """Node ID → Node mapping for location info (optional)"""

    repo_path: str | None
    """Repository path (optional)"""
