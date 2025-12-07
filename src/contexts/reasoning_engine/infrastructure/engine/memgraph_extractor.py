"""
Memgraph VFG Extractor

Extracts ValueFlowGraph data from Memgraph for Rust engine processing.

RFC-007 v1.2: Memgraph → Rust sync for 10-50x taint analysis speedup
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.infra.graph.memgraph import MemgraphGraphStore

logger = logging.getLogger(__name__)


class MemgraphVFGExtractor:
    """
    Extract VFG (Value Flow Graph) data from Memgraph.

    Memgraph stores the full graph, but we extract only VFG nodes/edges
    for high-speed taint analysis in Rust engine.

    Usage:
        extractor = MemgraphVFGExtractor(memgraph_store)
        vfg_data = extractor.extract_vfg(repo_id, snapshot_id)
        rust_engine.load(vfg_data)
    """

    def __init__(self, memgraph_store: "MemgraphGraphStore"):
        """
        Initialize extractor.

        Args:
            memgraph_store: MemgraphGraphStore instance
        """
        self.store = memgraph_store
        self._driver = self._get_driver()

    def _get_driver(self) -> Any:
        """Get underlying neo4j driver."""
        # MemgraphGraphStore wraps FoundationMemgraphStore
        foundation_store = self.store._store if hasattr(self.store, "_store") else self.store
        return foundation_store._driver

    def extract_vfg(
        self, repo_id: str | None = None, snapshot_id: str | None = None, limit: int | None = None
    ) -> dict[str, Any]:
        """
        Extract VFG nodes and edges from Memgraph.

        Queries:
        1. ValueFlowNode nodes
        2. FLOWS_TO edges

        Args:
            repo_id: Optional repo filter
            snapshot_id: Optional snapshot filter
            limit: Optional result limit (for testing)

        Returns:
            {
                "nodes": [{"id": ..., "value_type": ..., ...}, ...],
                "edges": [{"src_id": ..., "dst_id": ..., "kind": ...}, ...]
            }
        """
        try:
            with self._driver.session() as session:
                # 1. Extract ValueFlowNode nodes
                where_clauses = []
                params = {}

                if repo_id:
                    where_clauses.append("n.repo_id = $repo_id")
                    params["repo_id"] = repo_id

                if snapshot_id:
                    where_clauses.append("n.snapshot_id = $snapshot_id")
                    params["snapshot_id"] = snapshot_id

                where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
                limit_clause = f"LIMIT {limit}" if limit else ""

                node_query = f"""
                    MATCH (n:ValueFlowNode)
                    {where_clause}
                    RETURN 
                        n.node_id AS id,
                        n.symbol_name AS symbol_name,
                        n.file_path AS file_path,
                        n.line AS line,
                        n.language AS language,
                        n.value_type AS value_type,
                        n.schema AS schema,
                        n.function_context AS function_context,
                        n.service_context AS service_context,
                        n.taint_labels AS taint_labels,
                        n.is_source AS is_source,
                        n.is_sink AS is_sink,
                        n.metadata AS metadata,
                        n.repo_id AS repo_id,
                        n.snapshot_id AS snapshot_id
                    {limit_clause}
                """

                node_result = session.run(node_query, **params)
                nodes = [dict(record) for record in node_result]

                logger.info(f"Extracted {len(nodes)} VFG nodes from Memgraph")

                # 2. Extract FLOWS_TO edges
                # Build WHERE clause for both src and dst
                if where_clauses:
                    # Apply filters to both src and dst nodes
                    src_clauses = [clause.replace("n.", "src.") for clause in where_clauses]
                    dst_clauses = [clause.replace("n.", "dst.") for clause in where_clauses]
                    edge_where_clause = f"WHERE {' AND '.join(src_clauses + dst_clauses)}"
                else:
                    edge_where_clause = ""

                edge_query = f"""
                    MATCH (src:ValueFlowNode)-[e:FLOWS_TO]->(dst:ValueFlowNode)
                    {edge_where_clause}
                    RETURN 
                        src.node_id AS src_id,
                        dst.node_id AS dst_id,
                        e.kind AS kind,
                        e.confidence AS confidence,
                        e.boundary_spec AS boundary_spec,
                        e.field_mapping AS field_mapping,
                        e.metadata AS metadata
                    {limit_clause}
                """

                edge_result = session.run(edge_query, **params)
                edges = [dict(record) for record in edge_result]

                logger.info(f"Extracted {len(edges)} VFG edges from Memgraph")

                return {
                    "nodes": nodes,
                    "edges": edges,
                    "stats": {
                        "num_nodes": len(nodes),
                        "num_edges": len(edges),
                        "repo_id": repo_id,
                        "snapshot_id": snapshot_id,
                    },
                }

        except Exception as e:
            logger.error(f"VFG extraction failed: {e}")
            return {"nodes": [], "edges": [], "stats": {"error": str(e)}}

    def extract_sources_and_sinks(
        self, repo_id: str | None = None, snapshot_id: str | None = None
    ) -> dict[str, list[str]]:
        """
        Extract taint sources and sinks from Memgraph.

        Sources: User input, network data, file reads
        Sinks: SQL queries, file writes, network sends

        Args:
            repo_id: Optional repo filter
            snapshot_id: Optional snapshot filter

        Returns:
            {
                "sources": ["node_id1", "node_id2", ...],
                "sinks": ["node_id3", "node_id4", ...]
            }
        """
        try:
            with self._driver.session() as session:
                where_clauses = []
                params = {}

                if repo_id:
                    where_clauses.append("n.repo_id = $repo_id")
                    params["repo_id"] = repo_id

                if snapshot_id:
                    where_clauses.append("n.snapshot_id = $snapshot_id")
                    params["snapshot_id"] = snapshot_id

                where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

                # Find sources (is_source = true)
                source_query = f"""
                    MATCH (n:ValueFlowNode)
                    {where_clause}
                    {"AND" if where_clause else "WHERE"} n.is_source = true
                    RETURN n.node_id AS node_id
                """

                source_result = session.run(source_query, **params)
                sources = [record["node_id"] for record in source_result]

                # Find sinks (is_sink = true)
                sink_query = f"""
                    MATCH (n:ValueFlowNode)
                    {where_clause}
                    {"AND" if where_clause else "WHERE"} n.is_sink = true
                    RETURN n.node_id AS node_id
                """

                sink_result = session.run(sink_query, **params)
                sinks = [record["node_id"] for record in sink_result]

                logger.info(f"Extracted {len(sources)} sources, {len(sinks)} sinks")

                return {"sources": sources, "sinks": sinks}

        except Exception as e:
            logger.error(f"Source/sink extraction failed: {e}")
            return {"sources": [], "sinks": []}

    def get_affected_nodes(self, file_paths: list[str], repo_id: str, snapshot_id: str) -> list[str]:
        """
        Get VFG nodes affected by file changes.

        Used for incremental cache invalidation.

        Args:
            file_paths: List of changed file paths
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            List of affected node IDs
        """
        try:
            with self._driver.session() as session:
                query = """
                    MATCH (n:ValueFlowNode)
                    WHERE n.repo_id = $repo_id
                      AND n.snapshot_id = $snapshot_id
                      AND any(path IN $file_paths WHERE n.file_path CONTAINS path)
                    RETURN n.node_id AS node_id
                """

                result = session.run(query, repo_id=repo_id, snapshot_id=snapshot_id, file_paths=file_paths)

                node_ids = [record["node_id"] for record in result]

                logger.info(f"Found {len(node_ids)} affected nodes for {len(file_paths)} files")

                return node_ids

        except Exception as e:
            logger.error(f"Affected nodes query failed: {e}")
            return []
