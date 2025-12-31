"""
Enhanced Chunk Ordering

Implements enhanced ordering strategies for context building.
Addresses Supplementary Opinion A from the retrieval execution plan.

Strategies:
- Flow-based ordering (for flow_trace queries)
- Structural ordering (for symbol_nav queries)
- Importance-based ordering (default)
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from codegraph_search.infrastructure.intent import IntentKind

if TYPE_CHECKING:
    from apps.api.shared.ports import GraphPort
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class OrderedChunk:
    """Chunk with ordering metadata."""

    chunk_id: str
    content: str
    file_path: str
    original_rank: int
    final_rank: int
    ordering_score: float
    ordering_reason: str
    metadata: dict[str, Any]


class ChunkOrderingStrategy:
    """
    Enhanced chunk ordering for better LLM context flow.

    Different strategies based on query intent:
    - flow_trace: Order by call graph flow (A → B → C)
    - symbol_nav: Put definition first, then usages
    - concept_search: Order by semantic relevance
    - code_search: Order by match quality + importance
    """

    def __init__(self, graph_port: "GraphPort | None" = None):
        """
        Initialize chunk ordering strategy.

        Args:
            graph_port: Graph port for flow-based ordering
        """
        self.graph_port = graph_port

    def order_chunks(
        self,
        chunks: list[dict[str, Any]],
        intent: IntentKind,
        query: str | None = None,
    ) -> list[OrderedChunk]:
        """
        Order chunks based on intent.

        Args:
            chunks: Input chunks with scores
            intent: Query intent
            query: Original query (optional, for context)

        Returns:
            Ordered chunks
        """
        if intent == IntentKind.FLOW_TRACE:
            return self._order_by_flow(chunks)
        elif intent == IntentKind.SYMBOL_NAV:
            return self._order_by_structure(chunks)
        elif intent == IntentKind.CONCEPT_SEARCH:
            return self._order_by_semantic_relevance(chunks)
        else:
            # Default: order by score
            return self._order_by_score(chunks)

    def _order_by_flow(self, chunks: list[dict[str, Any]]) -> list[OrderedChunk]:
        """
        Order chunks by call graph flow.

        Strategy:
        - Identify entry point (likely caller)
        - Follow call chain: A calls B, B calls C
        - Present in execution order

        Args:
            chunks: Input chunks

        Returns:
            Flow-ordered chunks
        """
        if not self.graph_port:
            logger.warning("Graph port not available, falling back to score ordering")
            return self._order_by_score(chunks)

        # Extract functions from chunks
        chunk_functions = {}
        for chunk in chunks:
            func_name = self._extract_function_name(chunk)
            if func_name:
                chunk_functions[chunk["chunk_id"]] = func_name

        if not chunk_functions:
            return self._order_by_score(chunks)

        # Build call graph
        call_graph = self._build_call_graph(list(chunk_functions.values()))

        # Find execution order (topological sort)
        execution_order = self._topological_sort(call_graph)

        # Map function names back to chunk IDs
        func_to_chunk = {v: k for k, v in chunk_functions.items()}

        # Order chunks by execution order
        ordered = []
        rank = 1
        for func_name in execution_order:
            chunk_id = func_to_chunk.get(func_name)
            if chunk_id:
                chunk = next(c for c in chunks if c["chunk_id"] == chunk_id)
                ordered.append(
                    OrderedChunk(
                        chunk_id=chunk["chunk_id"],
                        content=chunk.get("content", ""),
                        file_path=chunk.get("file_path", ""),
                        original_rank=chunks.index(chunk) + 1,
                        final_rank=rank,
                        ordering_score=float(len(execution_order) - rank + 1),
                        ordering_reason="flow_execution_order",
                        metadata=chunk.get("metadata", {}),
                    )
                )
                rank += 1

        # Add remaining chunks (not in flow)
        remaining_ids = {c["chunk_id"] for c in chunks} - {o.chunk_id for o in ordered}
        for chunk in chunks:
            if chunk["chunk_id"] in remaining_ids:
                ordered.append(
                    OrderedChunk(
                        chunk_id=chunk["chunk_id"],
                        content=chunk.get("content", ""),
                        file_path=chunk.get("file_path", ""),
                        original_rank=chunks.index(chunk) + 1,
                        final_rank=rank,
                        ordering_score=chunk.get("score", 0.0),
                        ordering_reason="not_in_flow",
                        metadata=chunk.get("metadata", {}),
                    )
                )
                rank += 1

        logger.info(f"Flow ordering: {len(ordered)} chunks, {len(ordered) - len(remaining_ids)} in flow")

        return ordered

    def _order_by_structure(self, chunks: list[dict[str, Any]]) -> list[OrderedChunk]:
        """
        Order chunks by structure (for symbol_nav).

        Strategy:
        - Definition chunks first
        - Usage/reference chunks second
        - Related chunks third

        Args:
            chunks: Input chunks

        Returns:
            Structure-ordered chunks
        """
        definitions = []
        usages = []
        others = []

        for chunk in chunks:
            chunk_type = chunk.get("chunk_type", "")
            is_definition = self._is_definition_chunk(chunk)

            if is_definition:
                definitions.append(chunk)
            elif "usage" in chunk_type or "reference" in chunk_type:
                usages.append(chunk)
            else:
                others.append(chunk)

        # Order: definitions → usages → others
        # Within each group, order by score
        definitions.sort(key=lambda c: c.get("score", 0.0), reverse=True)
        usages.sort(key=lambda c: c.get("score", 0.0), reverse=True)
        others.sort(key=lambda c: c.get("score", 0.0), reverse=True)

        ordered = []
        rank = 1

        for group, reason in [
            (definitions, "definition"),
            (usages, "usage"),
            (others, "related"),
        ]:
            for chunk in group:
                ordered.append(
                    OrderedChunk(
                        chunk_id=chunk["chunk_id"],
                        content=chunk.get("content", ""),
                        file_path=chunk.get("file_path", ""),
                        original_rank=chunks.index(chunk) + 1,
                        final_rank=rank,
                        ordering_score=chunk.get("score", 0.0),
                        ordering_reason=reason,
                        metadata=chunk.get("metadata", {}),
                    )
                )
                rank += 1

        logger.info(f"Structural ordering: {len(definitions)} definitions, {len(usages)} usages, {len(others)} others")

        return ordered

    def _order_by_semantic_relevance(self, chunks: list[dict[str, Any]]) -> list[OrderedChunk]:
        """
        Order chunks by semantic relevance (for concept_search).

        Simply orders by score (semantic/vector score is primary).

        Args:
            chunks: Input chunks

        Returns:
            Relevance-ordered chunks
        """
        return self._order_by_score(chunks, reason="semantic_relevance")

    def _order_by_score(self, chunks: list[dict[str, Any]], reason: str = "score") -> list[OrderedChunk]:
        """
        Default ordering by score.

        Args:
            chunks: Input chunks
            reason: Ordering reason

        Returns:
            Score-ordered chunks
        """
        sorted_chunks = sorted(chunks, key=lambda c: c.get("score", 0.0), reverse=True)

        ordered = []
        for rank, chunk in enumerate(sorted_chunks, 1):
            ordered.append(
                OrderedChunk(
                    chunk_id=chunk["chunk_id"],
                    content=chunk.get("content", ""),
                    file_path=chunk.get("file_path", ""),
                    original_rank=chunks.index(chunk) + 1,
                    final_rank=rank,
                    ordering_score=chunk.get("score", 0.0),
                    ordering_reason=reason,
                    metadata=chunk.get("metadata", {}),
                )
            )

        return ordered

    def _extract_function_name(self, chunk: dict[str, Any]) -> str | None:
        """Extract function name from chunk."""
        # Try metadata
        metadata = chunk.get("metadata", {})
        if "function_name" in metadata:
            return metadata["function_name"]

        # Try chunk type
        chunk_type = chunk.get("chunk_type", "")
        if "function:" in chunk_type:
            return chunk_type.split("function:", 1)[1].strip()

        return None

    def _is_definition_chunk(self, chunk: dict[str, Any]) -> bool:
        """Check if chunk is a definition."""
        chunk_type = chunk.get("chunk_type", "")
        return any(kw in chunk_type.lower() for kw in ["definition", "class", "function", "method"])

    def _build_call_graph(self, function_names: list[str]) -> dict[str, list[str]]:
        """
        Build call graph for function names.

        Args:
            function_names: List of function names

        Returns:
            Call graph {caller: [callees]}
        """
        if not self.graph_port:
            return {}

        call_graph = {}
        for func in function_names:
            try:
                callees = self.graph_port.get_callees(func)
                # Filter to only functions in our list
                relevant_callees = [c for c in callees if c in function_names]
                if relevant_callees:
                    call_graph[func] = relevant_callees
            except Exception as e:
                logger.warning(f"Failed to get callees for {func}: {e}")

        return call_graph

    def _topological_sort(self, graph: dict[str, list[str]]) -> list[str]:
        """
        Topological sort of call graph.

        Args:
            graph: Call graph {caller: [callees]}

        Returns:
            Sorted list of function names (execution order)
        """
        # Simple topological sort
        visited = set()
        result = []

        def visit(node: str):
            if node in visited:
                return
            visited.add(node)

            # Visit callees first (depth-first)
            for callee in graph.get(node, []):
                visit(callee)

            result.append(node)

        # Visit all nodes
        for node in graph.keys():
            visit(node)

        # Reverse to get execution order (callers before callees)
        return list(reversed(result))
