"""
Model Converter

Domain ↔ Foundation 모델 변환 로직 통합
중복 제거: Symbol, Node, Edge, Span 변환을 한 곳에서 관리
"""

from typing import TYPE_CHECKING

from ....domain.models import GraphEdge, GraphNode, Reference, Symbol
from .kind_mapper import DomainToFoundationKindMapper, FoundationToDomainKindMapper

if TYPE_CHECKING:
    from ...graph.models import GraphNode as FoundationGraphNode
    from ...ir.models.core import Edge, Node


class ModelConverter:
    """Domain ↔ Foundation 모델 변환기"""

    @staticmethod
    def foundation_node_to_domain_symbol(node: "Node") -> Symbol:
        """
        Foundation Node → Domain Symbol

        Args:
            node: Foundation Node

        Returns:
            Domain Symbol
        """
        return Symbol(
            name=node.name or "",
            type=FoundationToDomainKindMapper.from_node_kind(node.kind),
            start_line=node.span.start_line if node.span else 1,
            end_line=node.span.end_line if node.span else 1,
            start_col=node.span.start_col if node.span else 0,
            end_col=node.span.end_col if node.span else 0,
            docstring=node.docstring,
        )

    @staticmethod
    def domain_symbol_to_foundation_node(symbol: Symbol, file_path: str, language: str) -> "Node":
        """
        Domain Symbol → Foundation Node

        Args:
            symbol: Domain Symbol
            file_path: 파일 경로
            language: 언어

        Returns:
            Foundation Node
        """
        from ...ir.models.core import Node, Span

        return Node(
            id=f"{file_path}::{symbol.name}",
            kind=DomainToFoundationKindMapper.to_node_kind(symbol.type),
            fqn=f"{file_path}::{symbol.name}",
            file_path=file_path,
            span=Span(
                start_line=symbol.start_line,
                start_col=symbol.start_col,
                end_line=symbol.end_line,
                end_col=symbol.end_col,
            ),
            language=language,
            name=symbol.name,
            docstring=symbol.docstring,
        )

    @staticmethod
    def foundation_edge_to_domain_reference(edge: "Edge") -> Reference:
        """
        Foundation Edge → Domain Reference

        Args:
            edge: Foundation Edge

        Returns:
            Domain Reference
        """
        return Reference(
            name=edge.source_id,
            target=edge.target_id,
            start_line=edge.span.start_line if edge.span else 0,
            end_line=edge.span.end_line if edge.span else 0,
            ref_type=FoundationToDomainKindMapper.from_edge_kind(edge.kind),
        )

    @staticmethod
    def domain_reference_to_foundation_edge(ref: Reference) -> "Edge":
        """
        Domain Reference → Foundation Edge

        Args:
            ref: Domain Reference

        Returns:
            Foundation Edge
        """
        from ...ir.models.core import Edge

        return Edge(
            id=f"edge:{ref.ref_type}:{ref.name}→{ref.target}",
            kind=DomainToFoundationKindMapper.to_edge_kind(ref.ref_type),
            source_id=ref.name,
            target_id=ref.target,
        )

    @staticmethod
    def foundation_graph_node_to_domain_node(fnode: "FoundationGraphNode", default_file_path: str) -> GraphNode:
        """
        Foundation GraphNode → Domain GraphNode

        Args:
            fnode: Foundation GraphNode
            default_file_path: 기본 파일 경로

        Returns:
            Domain GraphNode
        """
        return GraphNode(
            id=fnode.id,
            type=FoundationToDomainKindMapper.from_node_kind(fnode.kind),
            name=fnode.name or "",
            file_path=fnode.path if hasattr(fnode, "path") else default_file_path,
            start_line=fnode.span.start_line if hasattr(fnode, "span") and fnode.span else 1,
            end_line=fnode.span.end_line if hasattr(fnode, "span") and fnode.span else 1,
            properties={
                "fqn": fnode.fqn if hasattr(fnode, "fqn") else fnode.id,
                "docstring": fnode.docstring if hasattr(fnode, "docstring") else "",
            },
        )

    @staticmethod
    def foundation_graph_edge_to_domain_edge(fedge) -> GraphEdge:
        """
        Foundation GraphEdge → Domain GraphEdge

        Args:
            fedge: Foundation GraphEdge

        Returns:
            Domain GraphEdge
        """
        return GraphEdge(
            source=fedge.source_id,
            target=fedge.target_id,
            type=FoundationToDomainKindMapper.from_edge_kind(fedge.kind),
            properties={},
        )
