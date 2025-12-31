"""
GraphDocument → DeltaGraph Adapter

실제 Semantica GraphDocument를 DeltaGraph가 사용할 수 있게 변환
"""

import logging
from typing import Any

from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument, GraphEdgeKind

logger = logging.getLogger(__name__)


class GraphDocumentAdapter:
    """
    GraphDocument를 DeltaGraph용 dict로 변환

    GraphDocument (실제 Semantica Graph) → dict (DeltaGraph 입력)
    """

    @staticmethod
    def to_dict(graph_doc: GraphDocument) -> dict[str, Any]:
        """
        GraphDocument → dict 변환

        Args:
            graph_doc: 실제 Semantica GraphDocument

        Returns:
            {'nodes': {id: data}, 'edges': {id: [edges]}}
        """
        nodes = {}
        edges = {}

        # Nodes 변환
        for node_id, node in graph_doc.graph_nodes.items():
            nodes[node_id] = {
                "id": node_id,
                "kind": node.kind.value,
                "fqn": node.fqn,
                "name": node.name,
                "path": node.path,
                "repo_id": node.repo_id,
                "snapshot_id": node.snapshot_id,
                "attrs": node.attrs,
            }

        # Edges 변환 (adjacency list)
        for edge in graph_doc.graph_edges:
            source_id = edge.source_id
            if source_id not in edges:
                edges[source_id] = []

            edges[source_id].append(
                {
                    "id": edge.id,
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "kind": edge.kind.value,
                    "attrs": edge.attrs,
                }
            )

        # 모든 노드에 대해 edges 초기화 (없으면 빈 리스트)
        for node_id in nodes:
            if node_id not in edges:
                edges[node_id] = []

        logger.info(f"GraphDocument converted: {len(nodes)} nodes, {sum(len(e) for e in edges.values())} edges")

        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def get_callers(graph_doc: GraphDocument, symbol_id: str) -> list[str]:
        """
        실제 call graph에서 caller 추출

        Args:
            graph_doc: GraphDocument
            symbol_id: Target symbol ID

        Returns:
            List of caller IDs

        Performance: O(1) - uses pre-built called_by index
        """
        # Use pre-built reverse index (O(1) instead of O(E) scan)
        callers = graph_doc.indexes.called_by.get(symbol_id, [])
        logger.debug(f"Found {len(callers)} callers for {symbol_id}")
        return callers

    @staticmethod
    def get_callees(graph_doc: GraphDocument, symbol_id: str) -> list[str]:
        """
        실제 call graph에서 callee 추출

        Args:
            graph_doc: GraphDocument
            symbol_id: Source symbol ID

        Returns:
            List of callee IDs

        Performance: O(k) where k = outgoing edges from symbol
        """
        # Use outgoing edge index + edge_by_id for efficient lookup
        callees = []
        edge_ids = graph_doc.indexes.outgoing.get(symbol_id, [])
        for edge_id in edge_ids:
            edge = graph_doc.edge_by_id.get(edge_id)
            if edge and edge.kind == GraphEdgeKind.CALLS:
                callees.append(edge.target_id)
        return callees

    @staticmethod
    def get_symbol_file(graph_doc: GraphDocument, symbol_id: str) -> str | None:
        """
        Symbol이 속한 파일 경로

        Args:
            graph_doc: GraphDocument
            symbol_id: Symbol ID

        Returns:
            File path or None
        """
        node = graph_doc.graph_nodes.get(symbol_id)
        if node:
            return node.path
        return None

    @staticmethod
    def get_symbols_by_file(graph_doc: GraphDocument, file_path: str) -> list[str]:
        """
        파일에 속한 모든 symbol ID

        Args:
            graph_doc: GraphDocument
            file_path: File path

        Returns:
            List of symbol IDs

        Performance: O(1) - uses pre-built path index
        """
        # Use pre-built path index (O(1) instead of O(N) scan)
        return list(graph_doc.get_node_ids_by_path(file_path))
