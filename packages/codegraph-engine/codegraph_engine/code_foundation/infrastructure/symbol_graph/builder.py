"""
Symbol Graph Builder

Converts GraphDocument → SymbolGraph (lightweight).
Strips away heavy attrs and search metadata.
"""

from typing import TYPE_CHECKING

from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument, GraphEdgeKind, GraphNodeKind
from codegraph_engine.code_foundation.infrastructure.symbol_graph.models import (
    Relation,
    RelationIndex,
    RelationKind,
    Symbol,
    SymbolGraph,
    SymbolKind,
)

if TYPE_CHECKING:
    pass


class SymbolGraphBuilder:
    """
    Builds lightweight SymbolGraph from GraphDocument.

    Conversion strategy:
    1. GraphNode → Symbol (remove attrs, keep essential fields)
    2. GraphEdge → Relation (remove attrs, keep kind + span)
    3. Build RelationIndex (reverse indexes)

    Result: ~200 bytes/symbol (vs 500 bytes in GraphDocument)
    """

    def build_from_graph(self, graph_doc: GraphDocument) -> SymbolGraph:
        """
        Build SymbolGraph from GraphDocument.

        Args:
            graph_doc: Heavy GraphDocument with all metadata

        Returns:
            Lightweight SymbolGraph
        """
        symbol_graph = SymbolGraph(
            repo_id=graph_doc.repo_id,
            snapshot_id=graph_doc.snapshot_id,
        )

        # Convert nodes to symbols
        for node in graph_doc.graph_nodes.values():
            symbol = self._convert_node_to_symbol(node)
            symbol_graph.symbols[symbol.id] = symbol

        # Convert edges to relations
        for edge in graph_doc.graph_edges:
            relation = self._convert_edge_to_relation(edge)
            symbol_graph.relations.append(relation)

        # Build indexes
        self._build_indexes(symbol_graph)

        return symbol_graph

    def _convert_node_to_symbol(self, node) -> Symbol:
        """
        Convert GraphNode → Symbol.

        Strips attrs dict, keeps only essential fields.
        """
        # Map GraphNodeKind → SymbolKind
        symbol_kind = self._map_node_kind_to_symbol_kind(node.kind)

        # Extract essential relationship IDs from attrs
        parent_id = None
        signature_id = None
        type_id = None

        if hasattr(node, "attrs") and node.attrs:
            # Parent relationship (CONTAINS edge target)
            # Note: parent_id can also be computed from graph edges
            parent_id = node.attrs.get("parent_id")

            # Signature relationship (for functions)
            signature_id = node.attrs.get("signature_id")

            # Type relationship (for variables)
            type_id = node.attrs.get("declared_type_id")

        return Symbol(
            id=node.id,
            kind=symbol_kind,
            fqn=node.fqn,
            name=node.name,
            repo_id=node.repo_id,
            snapshot_id=node.snapshot_id,
            span=node.span,
            parent_id=parent_id,
            signature_id=signature_id,
            type_id=type_id,
        )

    def _convert_edge_to_relation(self, edge) -> Relation:
        """
        Convert GraphEdge → Relation.

        Strips attrs dict, keeps only essential fields.
        """
        # Map GraphEdgeKind → RelationKind
        relation_kind = self._map_edge_kind_to_relation_kind(edge.kind)

        # Extract span from attrs if available
        span = None
        if hasattr(edge, "attrs") and edge.attrs:
            span = edge.attrs.get("span")

        return Relation(
            id=edge.id,
            kind=relation_kind,
            source_id=edge.source_id,
            target_id=edge.target_id,
            span=span,
        )

    def _map_node_kind_to_symbol_kind(self, node_kind: GraphNodeKind) -> SymbolKind:
        """Map GraphNodeKind → SymbolKind"""
        mapping = {
            GraphNodeKind.FILE: SymbolKind.FILE,
            GraphNodeKind.MODULE: SymbolKind.MODULE,
            GraphNodeKind.CLASS: SymbolKind.CLASS,
            GraphNodeKind.FUNCTION: SymbolKind.FUNCTION,
            GraphNodeKind.METHOD: SymbolKind.METHOD,
            GraphNodeKind.VARIABLE: SymbolKind.VARIABLE,
            GraphNodeKind.FIELD: SymbolKind.FIELD,
            GraphNodeKind.TYPE: SymbolKind.TYPE,
            GraphNodeKind.SIGNATURE: SymbolKind.SIGNATURE,
            GraphNodeKind.CFG_BLOCK: SymbolKind.CFG_BLOCK,
            GraphNodeKind.EXTERNAL_MODULE: SymbolKind.EXTERNAL_MODULE,
            GraphNodeKind.EXTERNAL_FUNCTION: SymbolKind.EXTERNAL_FUNCTION,
            GraphNodeKind.EXTERNAL_TYPE: SymbolKind.EXTERNAL_TYPE,
        }

        return mapping.get(node_kind, SymbolKind.VARIABLE)  # Default fallback

    def _map_edge_kind_to_relation_kind(self, edge_kind: GraphEdgeKind) -> RelationKind:
        """Map GraphEdgeKind → RelationKind"""
        mapping = {
            GraphEdgeKind.CONTAINS: RelationKind.CONTAINS,
            GraphEdgeKind.IMPORTS: RelationKind.IMPORTS,
            GraphEdgeKind.INHERITS: RelationKind.INHERITS,
            GraphEdgeKind.IMPLEMENTS: RelationKind.IMPLEMENTS,
            GraphEdgeKind.CALLS: RelationKind.CALLS,
            GraphEdgeKind.REFERENCES_TYPE: RelationKind.REFERENCES_TYPE,
            GraphEdgeKind.REFERENCES_SYMBOL: RelationKind.REFERENCES_SYMBOL,
            GraphEdgeKind.READS: RelationKind.READS,
            GraphEdgeKind.WRITES: RelationKind.WRITES,
            GraphEdgeKind.CFG_NEXT: RelationKind.CFG_NEXT,
            GraphEdgeKind.CFG_BRANCH: RelationKind.CFG_BRANCH,
            GraphEdgeKind.CFG_LOOP: RelationKind.CFG_LOOP,
            GraphEdgeKind.CFG_HANDLER: RelationKind.CFG_HANDLER,
        }

        return mapping.get(edge_kind, RelationKind.REFERENCES_SYMBOL)  # Default fallback

    def _build_indexes(self, graph: SymbolGraph) -> None:
        """
        Build RelationIndex from relations.

        Creates reverse indexes for efficient graph traversal.
        """
        from collections import defaultdict

        # Initialize indexes
        called_by: dict[str, list[str]] = defaultdict(list)
        imported_by: dict[str, list[str]] = defaultdict(list)
        parent_to_children: dict[str, list[str]] = defaultdict(list)
        type_users: dict[str, list[str]] = defaultdict(list)
        reads_by: dict[str, list[str]] = defaultdict(list)
        writes_by: dict[str, list[str]] = defaultdict(list)
        outgoing: dict[str, list[str]] = defaultdict(list)
        incoming: dict[str, list[str]] = defaultdict(list)

        # Build indexes from relations
        for relation in graph.relations:
            # Adjacency indexes
            outgoing[relation.source_id].append(relation.id)
            incoming[relation.target_id].append(relation.id)

            # Reverse indexes by kind
            if relation.kind == RelationKind.CALLS:
                called_by[relation.target_id].append(relation.source_id)
            elif relation.kind == RelationKind.IMPORTS:
                imported_by[relation.target_id].append(relation.source_id)
            elif relation.kind == RelationKind.CONTAINS:
                parent_to_children[relation.source_id].append(relation.target_id)
            elif relation.kind == RelationKind.REFERENCES_TYPE:
                type_users[relation.target_id].append(relation.source_id)
            elif relation.kind == RelationKind.READS:
                reads_by[relation.target_id].append(relation.source_id)
            elif relation.kind == RelationKind.WRITES:
                writes_by[relation.target_id].append(relation.source_id)

        # Update graph indexes
        graph.indexes = RelationIndex(
            called_by=called_by,
            imported_by=imported_by,
            parent_to_children=parent_to_children,
            type_users=type_users,
            reads_by=reads_by,
            writes_by=writes_by,
            outgoing=outgoing,
            incoming=incoming,
        )
