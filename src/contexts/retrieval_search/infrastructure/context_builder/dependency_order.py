"""
Dependency-aware Ordering (SOTA Enhancement)

Orders chunks by dependency relationships so LLMs see definitions before usages.

Strategy:
1. Extract dependency graph from chunks (using symbol/graph relationships)
2. Topological sort to order chunks (definitions → usages)
3. Handle cycles with SCC (Strongly Connected Components)
4. Fallback to heuristic ordering for chunks without dependencies

Expected improvements:
- Context quality: +15% (LLM sees proper dependency order)
- Comprehension: Better understanding of code relationships
- Accuracy: Reduced hallucinations from missing context

Example ordering:
  Before: UserHandler → User → UserService
  After:  User → UserService → UserHandler (definition-first)
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from src.common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class DependencyInfo:
    """Dependency information for a chunk."""

    chunk_id: str
    depends_on: list[str]  # List of chunk IDs this depends on
    depended_by: list[str]  # List of chunk IDs that depend on this
    level: int = 0  # Dependency level (0 = no deps, higher = more downstream)


class DependencyGraphExtractor:
    """
    Extracts dependency relationships between chunks.

    Uses graph edges (CALLS, IMPORTS, INHERITS, REFERENCES_TYPE, etc.)
    to build chunk-to-chunk dependency relationships.
    """

    # Dependency edge types (ordered by importance)
    DEPENDENCY_EDGES = [
        "INHERITS",  # Class inheritance (strongest dependency)
        "IMPLEMENTS",  # Interface implementation
        "REFERENCES_TYPE",  # Type usage
        "INSTANTIATES",  # Object creation
        "IMPORTS",  # Import relationships
        "CALLS",  # Function calls (weakest dependency for ordering)
    ]

    def __init__(self, graph_doc=None, symbol_graph=None):
        """
        Initialize dependency graph extractor.

        Args:
            graph_doc: GraphDocument (optional)
            symbol_graph: SymbolGraph (optional)
        """
        self.graph_doc = graph_doc
        self.symbol_graph = symbol_graph

    def extract_dependencies(self, chunks: list[dict[str, Any]]) -> dict[str, DependencyInfo]:
        """
        Extract dependency relationships between chunks.

        Args:
            chunks: List of chunks with chunk_id and metadata

        Returns:
            Dict mapping chunk_id → DependencyInfo
        """
        # Build chunk ID → symbol IDs mapping
        chunk_to_symbols = self._build_chunk_symbol_mapping(chunks)

        # Extract dependencies between chunks
        dependencies: dict[str, DependencyInfo] = {}

        for chunk in chunks:
            chunk_id = chunk.get("chunk_id", "")
            if not chunk_id:
                continue

            symbol_ids = chunk_to_symbols.get(chunk_id, [])

            # Find chunks that this chunk depends on
            depends_on = self._find_dependencies(chunk_id, symbol_ids, chunk_to_symbols)

            dependencies[chunk_id] = DependencyInfo(chunk_id=chunk_id, depends_on=depends_on, depended_by=[])

        # Build reverse dependency index (depended_by)
        for chunk_id, dep_info in dependencies.items():
            for dep_chunk_id in dep_info.depends_on:
                if dep_chunk_id in dependencies:
                    dependencies[dep_chunk_id].depended_by.append(chunk_id)

        # Calculate dependency levels
        self._calculate_dependency_levels(dependencies)

        return dependencies

    def _build_chunk_symbol_mapping(self, chunks: list[dict[str, Any]]) -> dict[str, list[str]]:
        """
        Build mapping from chunk_id to symbol IDs.

        Args:
            chunks: List of chunks

        Returns:
            Dict mapping chunk_id → list of symbol IDs
        """
        chunk_to_symbols: dict[str, list[str]] = {}

        for chunk in chunks:
            chunk_id = chunk.get("chunk_id", "")
            metadata = chunk.get("metadata", {})

            # Extract symbol ID from chunk metadata
            # Chunks can contain: fqn, symbol_id, node_id, etc.
            symbol_ids = []

            if "symbol_id" in metadata:
                symbol_ids.append(metadata["symbol_id"])
            elif "node_id" in metadata:
                symbol_ids.append(metadata["node_id"])
            elif "fqn" in metadata:
                # Try to find symbol by FQN
                symbol_id = self._find_symbol_by_fqn(metadata["fqn"])
                if symbol_id:
                    symbol_ids.append(symbol_id)

            chunk_to_symbols[chunk_id] = symbol_ids

        return chunk_to_symbols

    def _find_symbol_by_fqn(self, fqn: str) -> str | None:
        """Find symbol ID by FQN."""
        if self.symbol_graph:
            for symbol in self.symbol_graph.symbols.values():
                if symbol.fqn == fqn:
                    return symbol.id

        if self.graph_doc:
            for node in self.graph_doc.graph_nodes.values():
                if node.fqn == fqn:
                    return node.id

        return None

    def _find_dependencies(
        self,
        chunk_id: str,
        symbol_ids: list[str],
        chunk_to_symbols: dict[str, list[str]],
    ) -> list[str]:
        """
        Find chunks that this chunk depends on.

        Args:
            chunk_id: Current chunk ID
            symbol_ids: Symbol IDs associated with this chunk
            chunk_to_symbols: Mapping of chunk_id → symbol IDs

        Returns:
            List of chunk IDs that this chunk depends on
        """
        if not symbol_ids:
            return []

        # Collect all target symbols that this chunk depends on
        target_symbols: set[str] = set()

        for symbol_id in symbol_ids:
            # Get outgoing dependency edges from this symbol
            targets = self._get_dependency_targets(symbol_id)
            target_symbols.update(targets)

        # Map target symbols back to chunks
        depends_on_chunks: set[str] = set()

        for target_symbol_id in target_symbols:
            # Find which chunk contains this target symbol
            for other_chunk_id, other_symbol_ids in chunk_to_symbols.items():
                if other_chunk_id == chunk_id:
                    continue  # Skip self-dependencies

                if target_symbol_id in other_symbol_ids:
                    depends_on_chunks.add(other_chunk_id)
                    break

        return list(depends_on_chunks)

    def _get_dependency_targets(self, symbol_id: str) -> list[str]:
        """
        Get all symbols that this symbol depends on.

        Args:
            symbol_id: Source symbol ID

        Returns:
            List of target symbol IDs
        """
        targets: list[str] = []

        # Try SymbolGraph first
        if self.symbol_graph:
            for relation in self.symbol_graph.relations:
                if relation.source_id == symbol_id:
                    # Check if this is a dependency edge
                    if relation.kind.value.upper() in self.DEPENDENCY_EDGES:
                        targets.append(relation.target_id)

        # Fall back to GraphDocument
        elif self.graph_doc:
            for edge in self.graph_doc.graph_edges:
                if edge.source_id == symbol_id:
                    if edge.kind.value in self.DEPENDENCY_EDGES:
                        targets.append(edge.target_id)

        return targets

    def _calculate_dependency_levels(self, dependencies: dict[str, DependencyInfo]) -> None:
        """
        Calculate dependency levels for all chunks.

        Level 0: No dependencies (leaf nodes)
        Level 1: Depends only on level 0
        Level N: Depends on level N-1

        Modifies DependencyInfo.level in-place.

        Args:
            dependencies: Dict of chunk dependencies
        """
        # Find chunks with no dependencies (level 0)
        to_process = deque([chunk_id for chunk_id, info in dependencies.items() if not info.depends_on])

        # Set level 0
        for chunk_id in to_process:
            dependencies[chunk_id].level = 0

        # BFS to calculate levels
        processed: set[str] = set(to_process)

        while to_process:
            chunk_id = to_process.popleft()

            # Update dependents (chunks that depend on this one)
            for dependent_id in dependencies[chunk_id].depended_by:
                if dependent_id in processed:
                    continue

                # Check if all dependencies of dependent are processed
                dep_info = dependencies[dependent_id]
                all_deps_processed = all(dep_id in processed for dep_id in dep_info.depends_on)

                if all_deps_processed:
                    # Calculate level as max(dependency levels) + 1
                    max_dep_level = max(
                        (dependencies[dep_id].level for dep_id in dep_info.depends_on if dep_id in dependencies),
                        default=0,
                    )
                    dep_info.level = max_dep_level + 1

                    to_process.append(dependent_id)
                    processed.add(dependent_id)


class DependencyAwareOrdering:
    """
    Orders chunks by dependency relationships.

    Uses topological sort with cycle handling (SCC decomposition).
    """

    def __init__(self, graph_doc=None, symbol_graph=None):
        """
        Initialize dependency-aware ordering.

        Args:
            graph_doc: GraphDocument (optional)
            symbol_graph: SymbolGraph (optional)
        """
        self.extractor = DependencyGraphExtractor(graph_doc, symbol_graph)

    def order_chunks(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Order chunks by dependency relationships.

        Chunks are ordered so that:
        1. Definitions come before usages
        2. Base classes before derived classes
        3. Imported modules before importers
        4. Lower dependency level before higher

        Args:
            chunks: List of chunks to order

        Returns:
            Ordered list of chunks (definitions first)
        """
        if not chunks:
            return []

        # Extract dependencies
        dependencies = self.extractor.extract_dependencies(chunks)

        if not dependencies:
            # No dependency info - fallback to original order
            logger.warning("No dependency information available, using original order")
            return chunks

        # Detect cycles (SCCs)
        sccs = self._find_strongly_connected_components(dependencies)

        # Topological sort of SCCs
        scc_order = self._topological_sort_sccs(sccs, dependencies)

        # Build ordered chunk list
        ordered_chunks = []
        chunk_map = {chunk["chunk_id"]: chunk for chunk in chunks}

        for scc in scc_order:
            # Within an SCC, order by dependency level
            scc_chunks = []
            for chunk_id in scc:
                if chunk_id in chunk_map:
                    scc_chunks.append((dependencies[chunk_id].level, chunk_id, chunk_map[chunk_id]))

            # Sort by level (lower level first)
            scc_chunks.sort(key=lambda x: x[0])

            # Add to result
            ordered_chunks.extend([chunk for _, _, chunk in scc_chunks])

        logger.info(
            f"Dependency ordering: {len(chunks)} chunks → {len(ordered_chunks)} ordered ({len(sccs)} dependency groups)"
        )

        return ordered_chunks

    def _find_strongly_connected_components(self, dependencies: dict[str, DependencyInfo]) -> list[list[str]]:
        """
        Find strongly connected components (cycles) using Tarjan's algorithm.

        Args:
            dependencies: Dependency information

        Returns:
            List of SCCs (each SCC is a list of chunk IDs)
        """
        # Tarjan's algorithm
        index_counter = [0]
        stack: list[str] = []
        lowlinks: dict[str, int] = {}
        index: dict[str, int] = {}
        on_stack: dict[str, bool] = {}
        sccs: list[list[str]] = []

        def strongconnect(chunk_id: str) -> None:
            index[chunk_id] = index_counter[0]
            lowlinks[chunk_id] = index_counter[0]
            index_counter[0] += 1
            stack.append(chunk_id)
            on_stack[chunk_id] = True

            # Consider successors
            dep_info = dependencies.get(chunk_id)
            if dep_info:
                for successor in dep_info.depends_on:
                    if successor not in dependencies:
                        continue

                    if successor not in index:
                        # Successor not yet visited
                        strongconnect(successor)
                        lowlinks[chunk_id] = min(lowlinks[chunk_id], lowlinks[successor])
                    elif on_stack.get(successor, False):
                        # Successor is in stack (part of current SCC)
                        lowlinks[chunk_id] = min(lowlinks[chunk_id], index[successor])

            # If chunk_id is a root node, pop the stack and create SCC
            if lowlinks[chunk_id] == index[chunk_id]:
                scc: list[str] = []
                while True:
                    successor = stack.pop()
                    on_stack[successor] = False
                    scc.append(successor)
                    if successor == chunk_id:
                        break
                sccs.append(scc)

        # Process all chunks
        for chunk_id in dependencies:
            if chunk_id not in index:
                strongconnect(chunk_id)

        return sccs

    def _topological_sort_sccs(self, sccs: list[list[str]], dependencies: dict[str, DependencyInfo]) -> list[list[str]]:
        """
        Topologically sort SCCs.

        Args:
            sccs: List of strongly connected components
            dependencies: Dependency information

        Returns:
            Topologically sorted SCCs (dependencies first)
        """
        # Build SCC graph
        chunk_to_scc: dict[str, int] = {}
        for scc_idx, scc in enumerate(sccs):
            for chunk_id in scc:
                chunk_to_scc[chunk_id] = scc_idx

        # Find dependencies between SCCs
        scc_deps: dict[int, set[int]] = defaultdict(set)

        for chunk_id, dep_info in dependencies.items():
            if chunk_id not in chunk_to_scc:
                continue

            scc_idx = chunk_to_scc[chunk_id]

            for dep_chunk_id in dep_info.depends_on:
                if dep_chunk_id not in chunk_to_scc:
                    continue

                dep_scc_idx = chunk_to_scc[dep_chunk_id]

                # Only add edge if different SCC (ignore intra-SCC edges)
                if scc_idx != dep_scc_idx:
                    scc_deps[scc_idx].add(dep_scc_idx)

        # Topological sort of SCCs (Kahn's algorithm)
        # For dependencies-first ordering: if A depends on B, B must come before A
        # So we count incoming edges TO each SCC (from its dependents)
        in_degree = dict.fromkeys(range(len(sccs)), 0)
        for scc_idx, deps in scc_deps.items():
            # scc_idx depends on deps → deps must come first
            # So scc_idx has len(deps) incoming edges
            in_degree[scc_idx] = len(deps)

        # Start with SCCs that have no dependencies (in-degree 0)
        queue = deque([i for i in range(len(sccs)) if in_degree[i] == 0])
        sorted_sccs: list[list[str]] = []

        while queue:
            scc_idx = queue.popleft()
            sorted_sccs.append(sccs[scc_idx])

            # Find SCCs that depend on this one, and reduce their in-degree
            for other_scc_idx, deps in scc_deps.items():
                if scc_idx in deps:
                    # other_scc_idx depends on scc_idx
                    # scc_idx is now processed, so reduce in-degree of other_scc_idx
                    in_degree[other_scc_idx] -= 1
                    if in_degree[other_scc_idx] == 0:
                        queue.append(other_scc_idx)

        # Handle remaining SCCs (shouldn't happen with proper cycle handling)
        for scc_idx, degree in in_degree.items():
            if degree > 0:
                sorted_sccs.append(sccs[scc_idx])

        return sorted_sccs

    def get_ordering_stats(self, original_chunks: list[dict], ordered_chunks: list[dict]) -> dict[str, Any]:
        """
        Get statistics about the reordering.

        Args:
            original_chunks: Original chunk order
            ordered_chunks: Dependency-ordered chunks

        Returns:
            Statistics dict
        """
        dependencies = self.extractor.extract_dependencies(ordered_chunks)

        total_deps = sum(len(info.depends_on) for info in dependencies.values())
        chunks_with_deps = sum(1 for info in dependencies.values() if info.depends_on)

        # Calculate reordering distance (how much did order change)
        original_ids = [c.get("chunk_id", "") for c in original_chunks]
        ordered_ids = [c.get("chunk_id", "") for c in ordered_chunks]

        reordering_distance = sum(1 for i, chunk_id in enumerate(ordered_ids) if original_ids[i] != chunk_id)

        return {
            "total_chunks": len(ordered_chunks),
            "chunks_with_dependencies": chunks_with_deps,
            "total_dependencies": total_deps,
            "avg_dependencies_per_chunk": (total_deps / len(ordered_chunks) if ordered_chunks else 0),
            "reordering_distance": reordering_distance,
            "reordering_percentage": (reordering_distance / len(ordered_chunks) * 100 if ordered_chunks else 0),
        }
