"""
Kuzu Graph Store

Saves and queries GraphDocument in Kuzu database.
"""

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .schema import KuzuSchema

if TYPE_CHECKING:
    import kuzu

    from ...graph.models import GraphDocument, GraphEdge, GraphNode


def _serialize_to_json(obj: Any) -> str:
    """
    Serialize object to JSON, handling dataclasses and Pydantic models.

    Args:
        obj: Object to serialize

    Returns:
        JSON string
    """

    def default(o):
        # Handle dataclasses
        if is_dataclass(o):
            return asdict(o)
        # Handle Pydantic models
        if hasattr(o, "model_dump"):
            return o.model_dump()
        # Handle objects with __dict__
        if hasattr(o, "__dict__"):
            return o.__dict__
        # Fallback: convert to string
        return str(o)

    return json.dumps(obj, default=default)


class KuzuGraphStore:
    """
    Kuzu-based storage for GraphDocument.

    Usage:
        store = KuzuGraphStore("/path/to/db")
        store.save_graph(graph_doc)
        nodes = store.query_called_by("function_id")
    """

    def __init__(self, db_path: str | Path, include_framework_rels: bool = False):
        """
        Initialize Kuzu graph store.

        Args:
            db_path: Path to Kuzu database directory
            include_framework_rels: Whether to create framework-specific REL tables
        """
        try:
            import kuzu
        except ImportError as e:
            raise ImportError("kuzu is required for KuzuGraphStore. " "Install it with: pip install kuzu") from e

        self.db_path = Path(db_path)
        # Create parent directory only (Kuzu creates the DB directory itself)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db = kuzu.Database(str(self.db_path))
        self._conn = kuzu.Connection(self._db)
        KuzuSchema.initialize(self._db, include_framework_rels=include_framework_rels)

    def save_graph(self, graph_doc: "GraphDocument") -> None:
        """
        Save GraphDocument to Kuzu.

        Args:
            graph_doc: Graph document to save
        """
        conn = self._conn

        # 1. Save nodes
        self._save_nodes(conn, graph_doc)

        # 2. Save edges
        self._save_edges(conn, graph_doc)

    def _save_nodes(self, conn: "kuzu.Connection", graph_doc: "GraphDocument"):
        """Save all graph nodes to graph_node table."""
        for node in graph_doc.graph_nodes.values():
            self._insert_node(conn, node)

    def _insert_node(self, conn: "kuzu.Connection", node: "GraphNode"):
        """Insert a single graph node."""
        # Serialize attrs to JSON
        attrs_json = _serialize_to_json(node.attrs) if node.attrs else "{}"

        # Extract span
        span_start = node.span.start_line if node.span else None
        span_end = node.span.end_line if node.span else None

        query = """
        MERGE (n:graph_node {node_id: $node_id})
        ON CREATE SET
            n.repo_id = $repo_id,
            n.lang = $lang,
            n.kind = $kind,
            n.fqn = $fqn,
            n.name = $name,
            n.path = $path,
            n.snapshot_id = $snapshot_id,
            n.span_start_line = $span_start_line,
            n.span_end_line = $span_end_line,
            n.attrs = $attrs
        ON MATCH SET
            n.repo_id = $repo_id,
            n.lang = $lang,
            n.kind = $kind,
            n.fqn = $fqn,
            n.name = $name,
            n.path = $path,
            n.snapshot_id = $snapshot_id,
            n.span_start_line = $span_start_line,
            n.span_end_line = $span_end_line,
            n.attrs = $attrs
        """

        params = {
            "node_id": node.id,
            "repo_id": node.repo_id,
            "lang": node.attrs.get("language", ""),
            "kind": node.kind.value,
            "fqn": node.fqn,
            "name": node.name,
            "path": node.path or "",
            "snapshot_id": node.snapshot_id,
            "span_start_line": span_start,
            "span_end_line": span_end,
            "attrs": attrs_json,
        }

        conn.execute(query, params)

    def _save_edges(self, conn: "kuzu.Connection", graph_doc: "GraphDocument"):
        """Save all graph edges to appropriate REL tables."""
        for edge in graph_doc.graph_edges:
            self._insert_edge(conn, edge)

    def _insert_edge(self, conn: "kuzu.Connection", edge: "GraphEdge"):
        """Insert a single graph edge into appropriate REL table."""
        # Map edge kind to REL table name
        rel_table = self._get_rel_table_name(edge.kind.value)

        # Serialize attrs
        attrs_json = _serialize_to_json(edge.attrs) if edge.attrs else "{}"

        # Create relationship
        query = f"""
        MATCH (source:graph_node {{node_id: $source_id}})
        MATCH (target:graph_node {{node_id: $target_id}})
        MERGE (source)-[r:{rel_table}]->(target)
        ON CREATE SET r.attrs = $attrs
        ON MATCH SET r.attrs = $attrs
        """

        params = {
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "attrs": attrs_json,
        }

        try:
            conn.execute(query, params)
        except Exception as e:
            # Skip if REL table doesn't exist (optional framework relations)
            if "does not exist" in str(e).lower():
                pass
            else:
                raise

    def _get_rel_table_name(self, edge_kind: str) -> str:
        """
        Map GraphEdgeKind value to Kuzu REL table name.

        Args:
            edge_kind: Edge kind value (e.g., "CONTAINS", "CALLS")

        Returns:
            REL table name
        """
        # Most edge kinds map directly to REL table names
        return edge_kind.upper()

    # ============================================================
    # Query API
    # ============================================================

    def query_called_by(self, function_id: str) -> list[str]:
        """
        Find all functions that call this function.

        Args:
            function_id: Target function node ID

        Returns:
            List of caller node IDs
        """
        conn = self._conn
        query = """
        MATCH (caller:graph_node)-[:CALLS]->(callee:graph_node {node_id: $function_id})
        RETURN caller.node_id
        """

        result = conn.execute(query, {"function_id": function_id})
        return [row[0] for row in result.get_all()]

    def query_imported_by(self, module_id: str) -> list[str]:
        """
        Find all modules that import this module.

        Args:
            module_id: Target module node ID

        Returns:
            List of importer node IDs
        """
        conn = self._conn
        query = """
        MATCH (importer:graph_node)-[:IMPORTS]->(module:graph_node {node_id: $module_id})
        RETURN importer.node_id
        """

        result = conn.execute(query, {"module_id": module_id})
        return [row[0] for row in result.get_all()]

    def query_contains_children(self, parent_id: str) -> list[str]:
        """
        Find all direct children of a node.

        Args:
            parent_id: Parent node ID

        Returns:
            List of child node IDs
        """
        conn = self._conn
        query = """
        MATCH (parent:graph_node {node_id: $parent_id})-[:CONTAINS]->(child:graph_node)
        RETURN child.node_id
        """

        result = conn.execute(query, {"parent_id": parent_id})
        return [row[0] for row in result.get_all()]

    def query_reads_variable(self, variable_id: str) -> list[str]:
        """
        Find all CFG blocks that read this variable.

        Args:
            variable_id: Variable node ID

        Returns:
            List of CFG block node IDs
        """
        conn = self._conn
        query = """
        MATCH (block:graph_node)-[:READS]->(var:graph_node {node_id: $variable_id})
        RETURN block.node_id
        """

        result = conn.execute(query, {"variable_id": variable_id})
        return [row[0] for row in result.get_all()]

    def query_writes_variable(self, variable_id: str) -> list[str]:
        """
        Find all CFG blocks that write this variable.

        Args:
            variable_id: Variable node ID

        Returns:
            List of CFG block node IDs
        """
        conn = self._conn
        query = """
        MATCH (block:graph_node)-[:WRITES]->(var:graph_node {node_id: $variable_id})
        RETURN block.node_id
        """

        result = conn.execute(query, {"variable_id": variable_id})
        return [row[0] for row in result.get_all()]

    def query_cfg_successors(self, block_id: str) -> list[str]:
        """
        Find all CFG successor blocks.

        Args:
            block_id: CFG block node ID

        Returns:
            List of successor block node IDs
        """
        conn = self._conn
        query = """
        MATCH (block:graph_node {node_id: $block_id})-[r]->(succ:graph_node)
        WHERE type(r) IN ['CFG_NEXT', 'CFG_BRANCH', 'CFG_LOOP', 'CFG_HANDLER']
        RETURN succ.node_id
        """

        result = conn.execute(query, {"block_id": block_id})
        return [row[0] for row in result.get_all()]

    def query_node_by_id(self, node_id: str) -> dict | None:
        """
        Get node by ID.

        Args:
            node_id: Node ID

        Returns:
            Node data as dict, or None if not found
        """
        conn = self._conn
        query = """
        MATCH (n:graph_node {node_id: $node_id})
        RETURN
            n.node_id, n.repo_id, n.lang, n.kind, n.fqn, n.name,
            n.path, n.snapshot_id, n.span_start_line, n.span_end_line, n.attrs
        """

        result = conn.execute(query, {"node_id": node_id})
        rows = result.get_all()

        if not rows:
            return None

        row = rows[0]
        return {
            "node_id": row[0],
            "repo_id": row[1],
            "lang": row[2],
            "kind": row[3],
            "fqn": row[4],
            "name": row[5],
            "path": row[6],
            "snapshot_id": row[7],
            "span_start_line": row[8],
            "span_end_line": row[9],
            "attrs": json.loads(row[10]) if row[10] else {},
        }

    # ============================================================
    # Delete API
    # ============================================================

    def delete_nodes(self, node_ids: list[str]) -> int:
        """
        Delete nodes by IDs.

        This will also delete all relationships connected to these nodes.

        Args:
            node_ids: List of node IDs to delete

        Returns:
            Number of nodes deleted
        """
        if not node_ids:
            return 0

        conn = self._conn
        deleted_count = 0

        for node_id in node_ids:
            query = """
            MATCH (n:graph_node {node_id: $node_id})
            DETACH DELETE n
            """
            try:
                conn.execute(query, {"node_id": node_id})
                deleted_count += 1
            except Exception:
                # Node might not exist, skip
                pass

        return deleted_count

    def delete_repo(self, repo_id: str) -> dict[str, int]:
        """
        Delete all nodes and edges for a repository.

        Args:
            repo_id: Repository ID

        Returns:
            Dict with counts: {"nodes": int, "edges": int}
        """
        conn = self._conn

        # Count before deletion
        count_query = """
        MATCH (n:graph_node {repo_id: $repo_id})
        RETURN count(*)
        """
        result = conn.execute(count_query, {"repo_id": repo_id})
        node_count = result.get_all()[0][0]

        # Delete all nodes (edges will be deleted automatically)
        delete_query = """
        MATCH (n:graph_node {repo_id: $repo_id})
        DETACH DELETE n
        """
        conn.execute(delete_query, {"repo_id": repo_id})

        return {"nodes": node_count, "edges": 0}  # Kuzu auto-deletes edges

    def delete_snapshot(self, repo_id: str, snapshot_id: str) -> dict[str, int]:
        """
        Delete all nodes and edges for a specific snapshot.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            Dict with counts: {"nodes": int, "edges": int}
        """
        conn = self._conn

        # Count before deletion
        count_query = """
        MATCH (n:graph_node {repo_id: $repo_id, snapshot_id: $snapshot_id})
        RETURN count(*)
        """
        result = conn.execute(count_query, {"repo_id": repo_id, "snapshot_id": snapshot_id})
        node_count = result.get_all()[0][0]

        # Delete all nodes for this snapshot
        delete_query = """
        MATCH (n:graph_node {repo_id: $repo_id, snapshot_id: $snapshot_id})
        DETACH DELETE n
        """
        conn.execute(delete_query, {"repo_id": repo_id, "snapshot_id": snapshot_id})

        return {"nodes": node_count, "edges": 0}  # Kuzu auto-deletes edges

    def delete_nodes_by_filter(self, repo_id: str, snapshot_id: str | None = None, kind: str | None = None) -> int:
        """
        Delete nodes by filter criteria.

        Args:
            repo_id: Repository ID (required)
            snapshot_id: Optional snapshot ID filter
            kind: Optional node kind filter (e.g., "Function", "Class")

        Returns:
            Number of nodes deleted
        """
        conn = self._conn

        # Build filter conditions
        conditions = ["repo_id: $repo_id"]
        params: dict[str, str] = {"repo_id": repo_id}

        if snapshot_id:
            conditions.append("snapshot_id: $snapshot_id")
            params["snapshot_id"] = snapshot_id

        if kind:
            conditions.append("kind: $kind")
            params["kind"] = kind

        filter_str = ", ".join(conditions)

        # Count before deletion
        count_query = f"""
        MATCH (n:graph_node {{{filter_str}}})
        RETURN count(*)
        """
        result = conn.execute(count_query, params)
        node_count = result.get_all()[0][0]

        # Delete matching nodes
        delete_query = f"""
        MATCH (n:graph_node {{{filter_str}}})
        DETACH DELETE n
        """
        conn.execute(delete_query, params)

        return node_count

    def close(self):
        """Close database connection."""
        # Kuzu automatically closes connections when DB object is destroyed
        pass
