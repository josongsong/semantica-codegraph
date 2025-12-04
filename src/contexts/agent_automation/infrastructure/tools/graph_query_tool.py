"""
Graph Query Tool

그래프 기반 코드 관계 탐색 도구.

기능:
- 함수 호출 관계 추적 (callers/callees)
- 의존성 분석 (dependencies/dependents)
- 실행 흐름 추적 (flow_trace)
"""

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.schemas import GraphQueryInput, GraphQueryOutput, GraphRelation
from src.contexts.agent_automation.infrastructure.tools.base import BaseTool
from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument, GraphEdgeKind

logger = get_logger(__name__)


class GraphQueryTool(BaseTool[GraphQueryInput, GraphQueryOutput]):
    """
    그래프 쿼리 도구.

    GraphDocument를 사용하여 코드 관계를 탐색합니다.
    """

    name = "graph_query"
    description = "Query code graph for relationships (callers, callees, dependencies, flow traces)"
    input_schema = GraphQueryInput
    output_schema = GraphQueryOutput

    def __init__(self, graph: GraphDocument | None = None):
        """
        Initialize graph query tool.

        Args:
            graph: GraphDocument instance (can be injected later)
        """
        super().__init__()
        self.graph = graph

    def set_graph(self, graph: GraphDocument) -> None:
        """Set graph document for querying."""
        self.graph = graph

    async def _execute(self, input_data: GraphQueryInput) -> GraphQueryOutput:
        """
        Execute graph query.

        Args:
            input_data: Query parameters

        Returns:
            Query results with relationships
        """
        if not self.graph:
            return GraphQueryOutput(
                success=False,
                query_type=input_data.query_type,
                error="Graph not initialized",
            )

        try:
            # Get node to verify it exists
            node = self.graph.get_node(input_data.symbol_id)
            if not node:
                return GraphQueryOutput(
                    success=False,
                    query_type=input_data.query_type,
                    error=f"Symbol not found: {input_data.symbol_id}",
                )

            # Execute query based on type
            sym_id = input_data.symbol_id
            depth = input_data.max_depth
            transitive = input_data.include_transitive
            if input_data.query_type == "callers":
                relations = self._find_callers(sym_id, depth, transitive)
            elif input_data.query_type == "callees":
                relations = self._find_callees(sym_id, depth, transitive)
            elif input_data.query_type == "dependencies":
                relations = self._find_dependencies(input_data.symbol_id, input_data.max_depth)
            elif input_data.query_type == "dependents":
                relations = self._find_dependents(input_data.symbol_id, input_data.max_depth)
            elif input_data.query_type == "flow_trace":
                relations = self._trace_flow(input_data.symbol_id, input_data.max_depth)
            else:
                return GraphQueryOutput(
                    success=False,
                    query_type=input_data.query_type,
                    error=f"Unknown query type: {input_data.query_type}",
                )

            return GraphQueryOutput(
                success=True,
                query_type=input_data.query_type,
                relations=relations,
                total_found=len(relations),
            )

        except Exception as e:
            logger.error(f"Graph query failed: {e}", exc_info=True)
            return GraphQueryOutput(
                success=False,
                query_type=input_data.query_type,
                error=str(e),
            )

    def _find_callers(self, symbol_id: str, max_depth: int, include_transitive: bool) -> list[GraphRelation]:
        """Find functions that call this symbol."""
        if not self.graph:
            return []

        relations: list[GraphRelation] = []
        visited: set[str] = set()

        def traverse(node_id: str, depth: int) -> None:
            if depth > max_depth or node_id in visited:
                return

            visited.add(node_id)

            # Get direct callers
            caller_ids = self.graph.indexes.get_callers(node_id)

            for caller_id in caller_ids:
                caller_node = self.graph.get_node(caller_id)
                target_node = self.graph.get_node(node_id)

                if caller_node and target_node:
                    relations.append(
                        GraphRelation(
                            source_id=caller_id,
                            target_id=node_id,
                            relation_type="CALLS",
                            source_name=caller_node.name,
                            target_name=target_node.name,
                            path=caller_node.path,
                        )
                    )

                    # Transitive traversal
                    if include_transitive and depth < max_depth:
                        traverse(caller_id, depth + 1)

        traverse(symbol_id, 1)
        return relations

    def _find_callees(self, symbol_id: str, max_depth: int, include_transitive: bool) -> list[GraphRelation]:
        """Find functions called by this symbol."""
        if not self.graph:
            return []

        relations: list[GraphRelation] = []
        visited: set[str] = set()

        def traverse(node_id: str, depth: int) -> None:
            if depth > max_depth or node_id in visited:
                return

            visited.add(node_id)

            # Get outgoing CALLS edges
            edges = self.graph.get_edges_from(node_id)
            call_edges = [e for e in edges if e.kind == GraphEdgeKind.CALLS]

            for edge in call_edges:
                callee_id = edge.target_id
                caller_node = self.graph.get_node(node_id)
                callee_node = self.graph.get_node(callee_id)

                if caller_node and callee_node:
                    relations.append(
                        GraphRelation(
                            source_id=node_id,
                            target_id=callee_id,
                            relation_type="CALLS",
                            source_name=caller_node.name,
                            target_name=callee_node.name,
                            path=caller_node.path,
                        )
                    )

                    # Transitive traversal
                    if include_transitive and depth < max_depth:
                        traverse(callee_id, depth + 1)

        traverse(symbol_id, 1)
        return relations

    def _find_dependencies(self, symbol_id: str, max_depth: int) -> list[GraphRelation]:
        """Find modules/symbols this depends on."""
        if not self.graph:
            return []

        relations: list[GraphRelation] = []
        visited: set[str] = {symbol_id}

        def traverse(node_id: str, depth: int) -> None:
            if depth > max_depth:
                return

            # Get outgoing IMPORTS edges
            edges = self.graph.get_edges_from(node_id)
            import_edges = [e for e in edges if e.kind == GraphEdgeKind.IMPORTS]

            for edge in import_edges:
                target_id = edge.target_id
                if target_id in visited:
                    continue

                visited.add(target_id)
                source_node = self.graph.get_node(node_id)
                target_node = self.graph.get_node(target_id)

                if source_node and target_node:
                    relations.append(
                        GraphRelation(
                            source_id=node_id,
                            target_id=target_id,
                            relation_type="IMPORTS",
                            source_name=source_node.name,
                            target_name=target_node.name,
                            path=source_node.path,
                        )
                    )

                    traverse(target_id, depth + 1)

        traverse(symbol_id, 1)
        return relations

    def _find_dependents(self, symbol_id: str, max_depth: int) -> list[GraphRelation]:
        """Find modules/symbols that depend on this."""
        if not self.graph:
            return []

        relations: list[GraphRelation] = []
        visited: set[str] = {symbol_id}

        def traverse(node_id: str, depth: int) -> None:
            if depth > max_depth:
                return

            # Get incoming IMPORTS edges
            importers = self.graph.indexes.get_importers(node_id)

            for importer_id in importers:
                if importer_id in visited:
                    continue

                visited.add(importer_id)
                source_node = self.graph.get_node(importer_id)
                target_node = self.graph.get_node(node_id)

                if source_node and target_node:
                    relations.append(
                        GraphRelation(
                            source_id=importer_id,
                            target_id=node_id,
                            relation_type="IMPORTS",
                            source_name=source_node.name,
                            target_name=target_node.name,
                            path=source_node.path,
                        )
                    )

                    traverse(importer_id, depth + 1)

        traverse(symbol_id, 1)
        return relations

    def _trace_flow(self, symbol_id: str, max_depth: int) -> list[GraphRelation]:
        """Trace execution flow (calls + data flow)."""
        if not self.graph:
            return []

        relations: list[GraphRelation] = []
        visited: set[str] = {symbol_id}

        def traverse(node_id: str, depth: int) -> None:
            if depth > max_depth:
                return

            # Get outgoing edges (CALLS, READS, WRITES)
            edges = self.graph.get_edges_from(node_id)
            flow_edges = [
                e
                for e in edges
                if e.kind
                in [
                    GraphEdgeKind.CALLS,
                    GraphEdgeKind.READS,
                    GraphEdgeKind.WRITES,
                ]
            ]

            for edge in flow_edges:
                target_id = edge.target_id
                if target_id in visited:
                    continue

                visited.add(target_id)
                source_node = self.graph.get_node(node_id)
                target_node = self.graph.get_node(target_id)

                if source_node and target_node:
                    relations.append(
                        GraphRelation(
                            source_id=node_id,
                            target_id=target_id,
                            relation_type=edge.kind.value,
                            source_name=source_node.name,
                            target_name=target_node.name,
                            path=source_node.path,
                        )
                    )

                    traverse(target_id, depth + 1)

        traverse(symbol_id, 1)
        return relations
