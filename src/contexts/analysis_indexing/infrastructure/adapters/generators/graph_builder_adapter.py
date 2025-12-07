"""
Graph Builder Adapter

그래프 빌드 어댑터
"""


class GraphBuilderAdapter:
    """그래프 빌더 어댑터"""

    def __init__(self, graph_builder):
        """
        초기화

        Args:
            graph_builder: GraphBuilder
        """
        self.graph_builder = graph_builder

    def build_graph(self, ir, semantic_ir=None):
        """
        그래프 빌드

        Args:
            ir: IRDocument
            semantic_ir: SemanticIRSnapshot (선택)

        Returns:
            GraphDocument
        """
        return self.graph_builder.build_full(
            ir_doc=ir,
            semantic_snapshot=semantic_ir,
        )
