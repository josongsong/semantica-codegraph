"""
Graph Builder Adapter

SOTA graph building for GraphBuilderPort.
"""

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.models import IRDocument
from codegraph_engine.code_foundation.domain.ports import GraphBuilderPort
from codegraph_engine.code_foundation.infrastructure.graph.builder import GraphBuilder as InfraGraphBuilder
from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument

logger = get_logger(__name__)


class SOTAGraphBuilderAdapter:
    """
    GraphBuilderPort adapter using SOTA GraphBuilder.

    Delegates to InfraGraphBuilder for actual graph construction.
    """

    def __init__(self):
        """Initialize adapter."""
        self._builder = InfraGraphBuilder()

    def build(self, ir_doc: IRDocument) -> GraphDocument:
        """
        Build graph from IR.

        Args:
            ir_doc: IR document

        Returns:
            GraphDocument

        Raises:
            ValueError: Graph building failed
        """
        try:
            # Build graph (without semantic IR for now)
            graph_doc = self._builder.build_full(
                ir_doc=ir_doc,
                semantic_snapshot=None,  # TODO: Add semantic IR support
            )

            return graph_doc

        except Exception as e:
            logger.error("Graph building failed", error=str(e))
            raise ValueError(f"Graph building failed: {e}") from e


def create_graph_builder_adapter() -> GraphBuilderPort:
    """Create production-grade GraphBuilderPort adapter."""
    return SOTAGraphBuilderAdapter()
