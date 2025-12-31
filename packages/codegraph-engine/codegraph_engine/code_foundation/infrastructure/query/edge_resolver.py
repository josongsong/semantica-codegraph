"""
EdgeResolver

Resolves EdgeSelector (domain) to IR edges (infrastructure).

Architecture:
- Infrastructure layer (uses UnifiedGraphIndex)
- Handles forward/backward edge direction
- Handles edge type unions

Contract:
- Returns edges matching selector criteria
- Respects backward flag (reverses edge direction)
- Empty list if no edges (never None)
"""

from typing import TYPE_CHECKING

from codegraph_engine.code_foundation.domain.query.results import UnifiedEdge
from codegraph_engine.code_foundation.domain.query.selectors import EdgeSelector
from codegraph_engine.code_foundation.domain.query.types import EdgeType

if TYPE_CHECKING:
    from .graph_index import UnifiedGraphIndex


class EdgeResolver:
    """
    Resolves EdgeSelector to UnifiedEdge

    Edge Types:
    - dfg: Data-flow edges (VariableEntity → VariableEntity)
    - cfg: Control-flow edges (Block → Block)
    - call: Call-graph edges (Function → Function)
    - all: Union of all edge types
    - union: Custom union of edge types
    """

    def __init__(self, graph: "UnifiedGraphIndex"):
        """
        Initialize with graph index

        Args:
            graph: Unified graph index
        """
        self.graph = graph

    def resolve(self, from_node_id: str, edge_selector: EdgeSelector, backward: bool = False) -> list[UnifiedEdge]:
        """
        Resolve edges from node

        Args:
            from_node_id: Source node ID (in forward mode) or target node ID (in backward mode)
            edge_selector: Edge selector (domain)
            backward: If True, use backward edges (incoming)

        Returns:
            List of matching edges

        Note:
        - In backward mode, from_node_id is actually the target
        - Edge direction in result is NOT reversed (caller responsibility)
        """
        # Determine effective backward flag
        effective_backward = backward or edge_selector.is_backward

        # Get base edges
        if effective_backward:
            # Get incoming edges
            edges = self.graph.get_edges_to(from_node_id)
        else:
            # Get outgoing edges
            edges = self.graph.get_edges_from(from_node_id)

        # Filter by edge type
        edge_type = edge_selector.edge_type

        if edge_type == EdgeType.ALL:
            # No filtering
            pass
        elif edge_type == EdgeType.UNION:
            # Union of multiple edge types
            operands = edge_selector.attrs.get("operands", [])
            if operands:
                allowed_types: set[EdgeType] = set()
                for operand in operands:
                    operand_type = operand.edge_type
                    if operand_type == EdgeType.ALL:
                        # If any operand is ALL, return all edges
                        allowed_types = {EdgeType.DFG, EdgeType.CFG, EdgeType.CALL}
                        break
                    allowed_types.add(operand_type)
                edges = [e for e in edges if e.edge_type in allowed_types]
        else:
            # Single edge type
            edges = [e for e in edges if e.edge_type == edge_type]

        return edges
