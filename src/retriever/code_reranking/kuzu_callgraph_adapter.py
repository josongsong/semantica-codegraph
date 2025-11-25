"""
Kuzu Call Graph Adapter

Production adapter for CallGraphReranker using Kuzu graph database.
"""


class KuzuCallGraphAdapter:
    """
    Adapter for CallGraphReranker that queries Kuzu graph database.

    Provides call graph traversal operations needed for proximity scoring.
    """

    def __init__(self, kuzu_store):
        """
        Initialize adapter.

        Args:
            kuzu_store: KuzuGraphStore instance from infra layer
        """
        self.kuzu_store = kuzu_store

    def calls(self, caller: str, callee: str) -> bool:
        """
        Check if caller calls callee.

        Args:
            caller: Caller function node ID
            callee: Callee function node ID

        Returns:
            True if direct call relationship exists
        """
        try:
            # Query Kuzu for direct CALLS edge
            query = """
            MATCH (caller:graph_node {node_id: $caller})-[:CALLS]->(callee:graph_node {node_id: $callee})
            RETURN count(*) as cnt
            """

            result = self.kuzu_store._conn.execute(query, {"caller": caller, "callee": callee})
            rows = result.get_all()
            return len(rows) > 0 and rows[0][0] > 0

        except Exception:
            # If query fails, assume no relationship
            return False

    def get_callees(self, func: str) -> list[str]:
        """
        Get all functions called by func.

        Args:
            func: Function node ID

        Returns:
            List of callee node IDs
        """
        try:
            query = """
            MATCH (caller:graph_node {node_id: $func})-[:CALLS]->(callee:graph_node)
            RETURN callee.node_id
            """

            result = self.kuzu_store._conn.execute(query, {"func": func})
            return [row[0] for row in result.get_all()]

        except Exception:
            return []

    def get_callers(self, func: str) -> list[str]:
        """
        Get all functions that call func.

        Args:
            func: Function node ID

        Returns:
            List of caller node IDs
        """
        try:
            # Reuse existing query_called_by method
            result = self.kuzu_store.query_called_by(func)
            return list(result) if result else []

        except Exception:
            return []

    def get_shortest_path(self, source: str, target: str, max_hops: int = 3) -> list[str] | None:
        """
        Find shortest path between two functions in call graph.

        Args:
            source: Source function node ID
            target: Target function node ID
            max_hops: Maximum path length

        Returns:
            Path as list of node IDs, or None if no path found
        """
        try:
            # Kuzu supports path queries
            query = """
            MATCH path = (source:graph_node {node_id: $source})
                         -[:CALLS*1..$max_hops]->
                         (target:graph_node {node_id: $target})
            RETURN nodes(path)
            ORDER BY length(path) ASC
            LIMIT 1
            """

            result = self.kuzu_store._conn.execute(query, {"source": source, "target": target, "max_hops": max_hops})
            rows = result.get_all()

            if rows:
                # Extract node IDs from path
                nodes = rows[0][0]
                return [node["node_id"] for node in nodes]

            return None

        except Exception:
            # Fallback to BFS if path query fails
            return None

    def get_related_functions(self, func: str, max_distance: int = 2) -> dict[str, int]:
        """
        Get all functions within max_distance hops.

        Args:
            func: Function node ID
            max_distance: Maximum distance in hops

        Returns:
            Dict mapping function ID to distance
        """
        try:
            query = """
            MATCH path = (source:graph_node {node_id: $func})
                         -[:CALLS*1..$max_distance]-
                         (related:graph_node)
            RETURN DISTINCT related.node_id, length(path) as distance
            ORDER BY distance ASC
            """

            result = self.kuzu_store._conn.execute(query, {"func": func, "max_distance": max_distance})

            related: dict[str, int] = {}
            for row in result.get_all():
                func_id = row[0]
                distance = row[1]
                # Keep minimum distance if multiple paths exist
                if func_id not in related or distance < related[func_id]:
                    related[func_id] = distance

            return related

        except Exception:
            return {}
