"""
Kind Mapper

Domain과 Foundation의 Kind/Type enum 매핑
중복 제거: kind_map을 한 곳에서 관리
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...ir.models.core import EdgeKind, NodeKind


class DomainToFoundationKindMapper:
    """Domain type string → Foundation enum 매핑"""

    @staticmethod
    def to_node_kind(domain_type: str) -> "NodeKind":
        """
        Domain symbol type → Foundation NodeKind

        Args:
            domain_type: "function", "class", "method", "variable" 등

        Returns:
            NodeKind enum
        """
        from ...ir.models.core import NodeKind

        _NODE_KIND_MAP = {
            "function": NodeKind.FUNCTION,
            "method": NodeKind.METHOD,
            "class": NodeKind.CLASS,
            "variable": NodeKind.VARIABLE,
        }

        return _NODE_KIND_MAP.get(domain_type.lower(), NodeKind.VARIABLE)

    @staticmethod
    def to_edge_kind(domain_ref_type: str) -> "EdgeKind":
        """
        Domain reference type → Foundation EdgeKind

        Args:
            domain_ref_type: "call", "import", "reference" 등

        Returns:
            EdgeKind enum
        """
        from ...ir.models.core import EdgeKind

        _EDGE_KIND_MAP = {
            "call": EdgeKind.CALLS,
            "import": EdgeKind.IMPORTS,
            "reference": EdgeKind.REFERENCES,
        }

        return _EDGE_KIND_MAP.get(domain_ref_type.lower(), EdgeKind.REFERENCES)


class FoundationToDomainKindMapper:
    """Foundation enum → Domain type string 매핑"""

    @staticmethod
    def from_node_kind(node_kind: "NodeKind") -> str:
        """
        Foundation NodeKind → Domain symbol type string

        Args:
            node_kind: NodeKind enum

        Returns:
            "function", "class", "method" 등
        """
        if hasattr(node_kind, "value"):
            return node_kind.value.lower()
        return str(node_kind).lower()

    @staticmethod
    def from_edge_kind(edge_kind: "EdgeKind") -> str:
        """
        Foundation EdgeKind → Domain edge type string

        Args:
            edge_kind: EdgeKind enum

        Returns:
            "calls", "imports" 등
        """
        if hasattr(edge_kind, "value"):
            return edge_kind.value.lower()
        return str(edge_kind).lower()
