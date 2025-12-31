"""
Variable Data Flow Tracker

Tracks data flow through variables using READS/WRITES edges.
Bridges the gap between function-level call graphs and variable-level taint analysis.

Algorithm:
1. Start from source function (e.g., input())
2. Find variables it writes to (WRITES edges)
3. Find who reads those variables (READS edges)
4. Continue until reaching sink function (e.g., cursor.execute())
"""

import logging
from collections import deque

from codegraph_engine.code_foundation.infrastructure.ir.models.core import Edge, EdgeKind
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument

logger = logging.getLogger(__name__)


class VariableDataFlowTracker:
    """
    Track data flow through variables using IR edges.

    SOTA Features:
    - BFS-based path finding
    - Cycle detection
    - Multiple path discovery
    - Performance optimized with caching
    """

    def __init__(self):
        """Initialize tracker"""
        self._edge_cache: dict[str, list[Edge]] = {}
        self._path_cache: dict[tuple[str, str], list[list[str]]] = {}

    def find_data_flow_paths(
        self,
        ir_document: IRDocument,
        source_id: str,
        sink_id: str,
        max_depth: int = 20,
        max_paths: int = 10,
    ) -> list[list[str]]:
        """
        Find data flow paths from source to sink through variables.

        Args:
            ir_document: IR document
            source_id: Source node ID (e.g., function that produces tainted data)
            sink_id: Sink node ID (e.g., function that uses tainted data)
            max_depth: Maximum path length (prevent infinite loops)
            max_paths: Maximum number of paths to find

        Returns:
            List of paths, where each path is a list of node IDs:
            [source_id, var1_id, var2_id, ..., sink_id]

        Example:
            input() → user_id → query → cursor.execute()
            Returns: [
                ["func:input", "var:user_id", "var:query", "func:cursor.execute"]
            ]
        """
        # Check cache
        cache_key = (source_id, sink_id)
        if cache_key in self._path_cache:
            logger.debug(f"Cache hit for {source_id} → {sink_id}")
            return self._path_cache[cache_key]

        # Build edge indexes
        writes_by_source, reads_by_target = self._build_edge_indexes(ir_document)

        logger.debug(f"Starting path search: {source_id} → {sink_id}")
        logger.debug(f"Writers: {len(writes_by_source)}, Readers: {len(reads_by_target)}")

        # BFS to find paths
        paths: list[list[str]] = []
        queue: deque = deque([(source_id, [source_id], 0)])  # (current_id, path, depth)
        visited: set[tuple[str, ...]] = set()  # Set of path tuples to detect cycles

        iterations = 0
        while queue and len(paths) < max_paths:
            current_id, path, depth = queue.popleft()
            iterations += 1

            if logger.isEnabledFor(logging.DEBUG) and iterations <= 10:  # Debug first 10 iterations
                node_name = self._node_name(current_id, ir_document)
                logger.debug(f"[BFS {iterations}] Current: {node_name}, Depth: {depth}, Path len: {len(path)}")

            # Max depth check
            if depth > max_depth:
                logger.debug("Max depth reached!")
                continue

            # Cycle detection (same node sequence)
            path_tuple = tuple(path)
            if path_tuple in visited:
                continue
            visited.add(path_tuple)

            # Found sink?
            if current_id == sink_id:
                paths.append(path)
                logger.debug(
                    f"Found path ({len(path)} nodes): {' → '.join([self._node_name(id, ir_document) for id in path])}"
                )
                continue

            # Strategy 1: If current is a function, find:
            # 1a. Variables it writes directly
            # 1b. Parent function that calls it (and find what parent writes)
            if current_id.startswith("function:") or "." in current_id:  # function call
                # 1a. Direct writes
                write_targets = writes_by_source.get(current_id, [])
                for target_id in write_targets:
                    if target_id not in path:  # Avoid immediate cycles
                        queue.append((target_id, path + [target_id], depth + 1))

                # 1b. ⭐ NEW: Find parent function (who CALLS this function)
                # In IR: parent_func --CALLS--> current_func
                # Then: parent_func --WRITES--> variables
                for edge in ir_document.edges:
                    if edge.kind == EdgeKind.CALLS and edge.target_id == current_id:
                        # Found parent function
                        parent_id = edge.source_id
                        parent_writes = writes_by_source.get(parent_id, [])
                        for var_id in parent_writes:
                            if var_id not in path:
                                # Add parent's written variables to search
                                queue.append((var_id, path + [var_id], depth + 1))

            # Strategy 2: If current is a variable, find who reads it
            if current_id.startswith("variable:"):
                read_sources = reads_by_target.get(current_id, [])
                for reader_id in read_sources:
                    if reader_id not in path:
                        queue.append((reader_id, path + [reader_id], depth + 1))

                    # ⭐ NEW: If reader calls other functions, those functions use the variable
                    # Example: get_user reads query, get_user calls cursor.execute
                    # → cursor.execute uses query (argument flow)
                    for edge in ir_document.edges:
                        if edge.kind == EdgeKind.CALLS and edge.source_id == reader_id:
                            callee_id = edge.target_id
                            if callee_id not in path:
                                # Function call that uses the variable
                                queue.append((callee_id, path + [reader_id, callee_id], depth + 2))

                    # Also check if reader writes to other variables
                    reader_writes = writes_by_source.get(reader_id, [])
                    for write_target in reader_writes:
                        if write_target not in path:
                            queue.append((write_target, path + [reader_id, write_target], depth + 2))

        # Cache results
        self._path_cache[cache_key] = paths

        if paths:
            logger.info(f"Found {len(paths)} data flow paths from {source_id} → {sink_id}")
        else:
            logger.debug(f"No data flow paths found from {source_id} → {sink_id}")

        return paths

    def _build_edge_indexes(
        self,
        ir_document: IRDocument,
    ) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """
        Build indexes for fast edge lookup.

        Returns:
            (writes_by_source, reads_by_target)
            - writes_by_source[func_id] = [var1_id, var2_id, ...]
            - reads_by_target[var_id] = [func1_id, func2_id, ...]
        """
        writes_by_source: dict[str, list[str]] = {}
        reads_by_target: dict[str, list[str]] = {}

        for edge in ir_document.edges:
            if edge.kind == EdgeKind.WRITES:
                # source_id (function/expr) writes to target_id (variable)
                writes_by_source.setdefault(edge.source_id, []).append(edge.target_id)

            elif edge.kind == EdgeKind.READS:
                # source_id (function/expr) reads from target_id (variable)
                reads_by_target.setdefault(edge.target_id, []).append(edge.source_id)

        logger.debug(f"Built edge indexes: {len(writes_by_source)} writers, {len(reads_by_target)} read targets")

        return writes_by_source, reads_by_target

    def _node_name(self, node_id: str, ir_document: IRDocument) -> str:
        """Get human-readable node name for debugging"""
        node = ir_document.get_node(node_id)
        if node and hasattr(node, "name") and node.name:
            return node.name
        return node_id.split(":")[-1] if ":" in node_id else node_id

    def clear_cache(self):
        """Clear all caches (useful for testing)"""
        self._edge_cache.clear()
        self._path_cache.clear()
        logger.debug("Cleared data flow tracker caches")

    def get_stats(self) -> dict[str, int]:
        """Get cache statistics"""
        return {
            "cached_paths": len(self._path_cache),
            "cache_hits": 0,  # Would need counter to track
        }
