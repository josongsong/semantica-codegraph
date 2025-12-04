"""
Call Graph Proximity Reranker

Boosts results that are close in the call graph to reference functions.
"""

from collections import deque

from src.contexts.retrieval_search.infrastructure.code_reranking.models import CallGraphProximity, CodeRerankedChunk


class CallGraphReranker:
    """
    Reranks results based on call graph proximity.

    Functions that are close in the call graph (direct callers/callees, or
    connected through a short path) are boosted.
    """

    def __init__(
        self,
        max_distance: int = 3,
        boost_factor: float = 0.20,
        distance_decay: float = 0.5,
    ):
        """
        Initialize call graph reranker.

        Args:
            max_distance: Maximum distance to consider in call graph
            boost_factor: Base boost for direct connections
            distance_decay: Decay factor per hop (0-1)
        """
        self.max_distance = max_distance
        self.boost_factor = boost_factor
        self.distance_decay = distance_decay

    def rerank(
        self,
        candidates: list[dict],
        reference_functions: list[str] | None = None,
        call_graph_adapter=None,
    ) -> list[CodeRerankedChunk]:
        """
        Rerank candidates based on call graph proximity.

        Args:
            candidates: List of candidate chunks with scores
            reference_functions: Functions to calculate distance from
            call_graph_adapter: Adapter to query call graph (optional)

        Returns:
            Reranked list with proximity scores
        """
        if not reference_functions or not call_graph_adapter:
            # No reference or call graph, return as-is
            return [
                CodeRerankedChunk(
                    chunk_id=c.get("chunk_id", "unknown"),
                    original_score=c.get("score", 0.0),
                    final_score=c.get("score", 0.0),
                )
                for c in candidates
            ]

        results = []

        for candidate in candidates:
            chunk_id = candidate.get("chunk_id", "unknown")
            original_score = candidate.get("score", 0.0)
            candidate_functions = candidate.get("functions", [])

            # Calculate proximity to reference functions
            proximity = self._calculate_proximity(
                reference_functions,
                candidate_functions,
                call_graph_adapter,
            )

            # Apply boost based on proximity
            if proximity and proximity.score > 0:
                boost = proximity.score * self.boost_factor
                final_score = min(1.0, original_score + boost)
            else:
                final_score = original_score

            results.append(
                CodeRerankedChunk(
                    chunk_id=chunk_id,
                    original_score=original_score,
                    proximity_score=proximity.score if proximity else 0.0,
                    final_score=final_score,
                    cg_proximity=proximity,
                    metadata=candidate.get("metadata", {}),
                )
            )

        # Sort by final score
        results.sort(key=lambda x: x.final_score, reverse=True)
        return results

    def _calculate_proximity(
        self,
        reference_functions: list[str],
        candidate_functions: list[str],
        call_graph_adapter,
    ) -> CallGraphProximity | None:
        """
        Calculate proximity between reference and candidate functions.

        Uses BFS to find shortest path in call graph.
        """
        if not reference_functions or not candidate_functions:
            return None

        best_proximity = None
        min_distance = float("inf")

        # Try all pairs of reference and candidate functions
        for ref_func in reference_functions:
            for cand_func in candidate_functions:
                # Direct match
                if ref_func == cand_func:
                    return CallGraphProximity(
                        distance=0,
                        path=[ref_func],
                        relationship="same_function",
                        score=1.0,
                    )

                # Check for direct call relationship
                proximity = self._check_direct_relationship(ref_func, cand_func, call_graph_adapter)

                if proximity:
                    if proximity.distance < min_distance:
                        min_distance = proximity.distance
                        best_proximity = proximity
                    continue

                # Find shortest path via BFS
                proximity = self._find_shortest_path(
                    ref_func,
                    cand_func,
                    call_graph_adapter,
                    max_distance=self.max_distance,
                )

                if proximity and proximity.distance < min_distance:
                    min_distance = proximity.distance
                    best_proximity = proximity

        return best_proximity

    def _check_direct_relationship(
        self, ref_func: str, cand_func: str, call_graph_adapter
    ) -> CallGraphProximity | None:
        """Check for direct caller/callee relationship."""
        # Check if ref calls cand
        if call_graph_adapter.calls(ref_func, cand_func):
            return CallGraphProximity(
                distance=1,
                path=[ref_func, cand_func],
                relationship="callee",
                score=1.0,
            )

        # Check if cand calls ref
        if call_graph_adapter.calls(cand_func, ref_func):
            return CallGraphProximity(
                distance=1,
                path=[cand_func, ref_func],
                relationship="caller",
                score=1.0,
            )

        return None

    def _find_shortest_path(
        self,
        source: str,
        target: str,
        call_graph_adapter,
        max_distance: int,
    ) -> CallGraphProximity | None:
        """
        Find shortest path in call graph using BFS.

        Args:
            source: Source function
            target: Target function
            call_graph_adapter: Call graph adapter
            max_distance: Max distance to search

        Returns:
            Proximity object or None if no path found
        """
        # BFS queue: (current_node, path, distance)
        queue = deque([(source, [source], 0)])
        visited = {source}

        while queue:
            current, path, distance = queue.popleft()

            if distance >= max_distance:
                continue

            # Get neighbors (both callees and callers)
            neighbors = []
            try:
                neighbors.extend(call_graph_adapter.get_callees(current))
                neighbors.extend(call_graph_adapter.get_callers(current))
            except Exception:
                # Adapter may not support these methods
                pass

            for neighbor in neighbors:
                if neighbor == target:
                    # Found target
                    final_path = path + [neighbor]
                    final_distance = distance + 1

                    # Calculate score with distance decay
                    score = self.distance_decay ** (final_distance - 1)

                    return CallGraphProximity(
                        distance=final_distance,
                        path=final_path,
                        relationship="indirect",
                        score=score,
                    )

                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor], distance + 1))

        return None
