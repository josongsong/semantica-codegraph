"""
IR Node Adapter

Infrastructure IRNode → Domain IRNodePort adapter.
"""

from typing import Any

from codegraph_engine.code_foundation.domain.ports.ir_port import IRNodePort, Span
from codegraph_engine.code_foundation.infrastructure.ir.models import Node as InfraIRNode


class IRNodeAdapter:
    """
    Adapter for IRNode (infrastructure) → IRNodePort (domain).

    Provides domain-friendly interface to infrastructure IR nodes.

    SOLID Compliance:
    - Single Responsibility: IR node adaptation only
    - Open/Closed: Extensible for new node types
    - Liskov Substitution: Implements IRNodePort contract
    - Interface Segregation: Minimal interface
    - Dependency Inversion: Depends on Port abstraction

    Production-Grade:
    - ✅ No Fake/Stub
    - ✅ Type-safe
    - ✅ Defensive null checks
    """

    def __init__(self, node: InfraIRNode):
        """
        Initialize adapter with infrastructure node.

        Args:
            node: Infrastructure IR node

        Raises:
            TypeError: If node is None or invalid type
        """
        if node is None:
            raise TypeError("Node cannot be None")
        if not isinstance(node, InfraIRNode):
            raise TypeError(f"Expected InfraIRNode, got {type(node)}")

        self._node = node

    @property
    def id(self) -> str:
        """Node ID."""
        return self._node.id

    @property
    def kind(self) -> str:
        """Node kind (e.g., 'function', 'class')."""
        return self._node.kind

    @property
    def name(self) -> str:
        """Node name."""
        return getattr(self._node, "name", "")

    @property
    def file_path(self) -> str | None:
        """File path."""
        return getattr(self._node, "file_path", None)

    @property
    def span(self) -> Span | None:
        """Source location span."""
        if not hasattr(self._node, "span") or self._node.span is None:
            return None

        node_span = self._node.span
        return Span(
            start_line=node_span.start_line,
            end_line=node_span.end_line,
            start_col=getattr(node_span, "start_col", None),
            end_col=getattr(node_span, "end_col", None),
        )

    @property
    def attrs(self) -> dict[str, Any]:
        """Node attributes."""
        return getattr(self._node, "attributes", {})

    def get_attr(self, key: str, default: Any = None) -> Any:
        """
        Get attribute by key.

        Args:
            key: Attribute key
            default: Default value if not found

        Returns:
            Attribute value or default
        """
        return self.attrs.get(key, default)


def create_ir_node_adapter(node: InfraIRNode) -> IRNodeAdapter:
    """
    Create IRNodePort adapter.

    Args:
        node: Infrastructure IR node

    Returns:
        Domain-friendly IR node adapter
    """
    return IRNodeAdapter(node)
