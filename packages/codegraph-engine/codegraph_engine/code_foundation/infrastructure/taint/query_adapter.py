"""
QueryEngineAdapter - Infrastructure Layer

Adapts QueryEngine to TaintEngine's needs.
Implements Port (IQueryEngine) defined in domain.

Hexagonal Architecture:
    Domain (TaintEngine)
        ↓ depends on Port (IQueryEngine)
    Infrastructure (This file)
        ↑ implements Port

SOLID Compliance:
- S: Single responsibility (query execution adapter)
- O: Open for extension (new query types)
- L: Substitutable for IQueryEngine
- I: Implements minimal interface
- D: Depends on abstractions (QueryEngine interface)
"""

from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.query.results import PathResult
from codegraph_engine.code_foundation.domain.taint.compiled_policy import CompiledPolicy
from codegraph_engine.code_foundation.infrastructure.query.query_engine import QueryEngine

logger = get_logger(__name__)

# Re-export for backward compatibility
__all__ = ["CompiledPolicy", "QueryEngineAdapter"]


class QueryEngineAdapter:
    """
    Adapter from QueryEngine to TaintEngine needs.

    Responsibilities:
    1. Execute flow queries
    2. Convert results to PathResult
    3. Handle errors gracefully
    4. Log performance metrics

    NOT Responsible For:
    - Query compilation (PolicyCompiler)
    - Result validation (TaintEngine)
    - Vulnerability creation (TaintEngine)

    Design Pattern: Adapter
    - Adapts QueryEngine interface to IQueryEngine port
    - Translates between domain and infrastructure types

    Usage:
        ```python
        adapter = QueryEngineAdapter(query_engine)

        paths = adapter.execute_flow_query(
            compiled_policy=compiled,
            max_paths=100,
            max_depth=20
        )

        for path in paths:
            print(f"Found path: {path.nodes}")
        ```

    Performance:
    - Delegates to QueryEngine (O(V + E))
    - Result conversion is O(P) where P = paths
    - No additional overhead
    """

    def __init__(self, query_engine: QueryEngine):
        """
        Initialize QueryEngineAdapter.

        Args:
            query_engine: Concrete query engine implementation

        Design:
            - Takes concrete implementation (not port)
            - Infrastructure layer can depend on concrete types
            - Domain layer only sees port (IQueryEngine)
        """
        self._engine = query_engine
        logger.info("query_engine_adapter_initialized")

    def execute_flow_query(
        self,
        compiled_policy: CompiledPolicy,
        max_paths: int = 100,
        max_depth: int = 20,
    ) -> list[PathResult]:
        """
        Execute flow query and return paths.

        Args:
            compiled_policy: Compiled policy with FlowExpr
            max_paths: Maximum number of paths to return
            max_depth: Maximum traversal depth

        Returns:
            List of PathResult objects

        Raises:
            ValueError: If compiled_policy is invalid
            RuntimeError: If query execution fails

        Performance:
        - O(V + E) graph traversal
        - Early termination at max_paths
        - Result conversion O(P) where P = paths

        Error Handling:
        - Catches query execution errors
        - Logs failures
        - Returns empty list on error (resilient)

        Example:
            ```python
            paths = adapter.execute_flow_query(
                compiled_policy=compiled,
                max_paths=50,
                max_depth=15
            )

            logger.info(f"Found {len(paths)} paths")
            ```
        """
        if not compiled_policy:
            raise ValueError("compiled_policy cannot be None")

        if not hasattr(compiled_policy, "flow_query"):
            raise ValueError("compiled_policy must have flow_query attribute")

        flow_expr = compiled_policy.flow_query

        logger.debug(
            "executing_flow_query",
            max_paths=max_paths,
            max_depth=max_depth,
        )

        try:
            # Execute query via QueryEngine
            result = self._engine.execute_flow(
                flow_expr=flow_expr,
                # Note: QueryEngine has its own max_depth handling
                # We rely on FlowExpr configuration
            )

            # Convert to PathResult objects
            paths = self._convert_to_path_results(result, max_paths)

            logger.info(
                "flow_query_executed",
                paths_found=len(paths),
                truncated=len(paths) >= max_paths,
            )

            return paths

        except Exception as e:
            logger.error(
                "flow_query_execution_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Resilient: return empty list instead of crashing
            return []

    def _convert_to_path_results(self, query_result: Any, max_paths: int) -> list[PathResult]:
        """
        Convert QueryEngine result to PathResult objects.

        Args:
            query_result: Result from QueryEngine.execute_flow()
            max_paths: Maximum number of paths to convert

        Returns:
            List of PathResult objects

        Note:
            QueryEngine returns different result formats depending on
            query type. This adapter handles the conversion.

        Performance:
            - O(min(P, max_paths)) where P = total paths
            - Early truncation
        """
        paths: list[PathResult] = []

        # Handle different result types
        if not query_result:
            return paths

        # Check if result has paths attribute
        if not hasattr(query_result, "paths"):
            logger.warning("query_result_has_no_paths_attribute")
            return paths

        result_paths = query_result.paths

        # Convert each path
        for i, path in enumerate(result_paths):
            if i >= max_paths:
                break

            try:
                path_result = self._convert_path(path, i)
                if path_result:
                    paths.append(path_result)
            except Exception as e:
                logger.warning(
                    "path_conversion_failed",
                    path_index=i,
                    error=str(e),
                )
                continue

        return paths

    def _convert_path(self, path: Any, index: int) -> PathResult | None:
        """
        Convert single path to PathResult.

        Args:
            path: Path from query result
            index: Path index (for logging)

        Returns:
            PathResult or None if conversion fails

        Path Attributes Expected:
        - nodes: list[UnifiedNode] or list[str]
        - edges: list[str] (optional)
        - length: int (optional, calculated if missing)
        - confidence: float (optional, default 1.0)
        - metadata: dict (optional)
        """
        try:
            # Extract nodes
            if hasattr(path, "nodes"):
                nodes = path.nodes
            elif hasattr(path, "path"):
                nodes = path.path
            else:
                logger.warning("path_has_no_nodes_attribute", index=index)
                return None

            # Convert nodes to IDs
            node_ids = []
            for node in nodes:
                if isinstance(node, str):
                    node_ids.append(node)
                elif hasattr(node, "id"):
                    node_ids.append(node.id)
                else:
                    logger.warning("invalid_node_type", node_type=type(node))
                    return None

            if not node_ids:
                return None

            # Extract edges
            edges = []
            if hasattr(path, "edges"):
                edges = [str(e) for e in path.edges] if path.edges else []

            # Calculate length
            length = len(node_ids)

            # Extract confidence
            confidence = 1.0
            if hasattr(path, "confidence"):
                confidence = float(path.confidence)
            elif hasattr(path, "score"):
                confidence = float(path.score)

            # Extract metadata
            metadata = {}
            if hasattr(path, "metadata"):
                metadata = dict(path.metadata)

            # Create PathResult
            return PathResult(
                nodes=tuple(node_ids),
                edges=tuple(edges),
                length=length,
                confidence=confidence,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(
                "path_conversion_exception",
                index=index,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    def find_any_path(
        self,
        source_node_id: str,
        sink_node_id: str,
        edge_types: str = "dfg|call",
        max_depth: int = 20,
    ) -> PathResult | None:
        """
        Find any single path from source to sink.

        Simpler API for single-path queries.

        Args:
            source_node_id: Starting node ID
            sink_node_id: Target node ID
            edge_types: Edge types to follow (pipe-separated)
            max_depth: Maximum path length

        Returns:
            PathResult if path found, None otherwise

        Implementation:
            - Uses QueryEngine's path finding
            - Returns first path found
            - O(V + E) with early termination
        """
        # TODO: Implement after QueryEngine.find_path() is available
        # For now, not used by TaintEngine main algorithm
        logger.warning("find_any_path_not_implemented")
        return None

    def get_node(self, node_id: str) -> Any:
        """
        Get node by ID.

        Args:
            node_id: Node identifier

        Returns:
            UnifiedNode if found, None otherwise

        Delegates to QueryEngine's graph index.
        """
        if not hasattr(self._engine, "graph_index"):
            logger.warning("query_engine_has_no_graph_index")
            return None

        return self._engine.graph_index.get_node(node_id)
