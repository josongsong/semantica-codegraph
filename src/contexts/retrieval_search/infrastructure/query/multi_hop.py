"""
Multi-hop Retrieval

Executes sequential retrieval steps with context accumulation.
"""

from typing import TYPE_CHECKING

from src.contexts.retrieval_search.infrastructure.query.models import DecomposedQuery, MultiHopResult, StepResult

if TYPE_CHECKING:
    from src.contexts.retrieval_search.infrastructure.service import RetrieverService
from src.common.observability import get_logger

logger = get_logger(__name__)


class MultiHopRetriever:
    """
    Multi-hop retrieval orchestrator.

    Executes decomposed query steps sequentially, using results from
    previous steps to inform subsequent searches.
    """

    def __init__(self, retriever_service: "RetrieverService"):
        """
        Initialize multi-hop retriever.

        Args:
            retriever_service: Base retriever service for each step
        """
        self.retriever_service = retriever_service

    async def retrieve_multi_hop(
        self,
        repo_id: str,
        snapshot_id: str,
        decomposed: DecomposedQuery,
        token_budget_per_step: int = 2000,
    ) -> MultiHopResult:
        """
        Execute multi-hop retrieval.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            decomposed: Decomposed query
            token_budget_per_step: Token budget for each step

        Returns:
            MultiHopResult with all step results
        """
        logger.info(f"Starting multi-hop retrieval: {len(decomposed.steps)} steps (type={decomposed.query_type.value})")

        # Get execution order (topologically sorted)
        execution_order = decomposed.get_execution_order()

        # Execute steps sequentially
        step_results = []
        context_accumulator = {}  # step_id → {chunks, symbols, summary}

        for step in execution_order:
            logger.info(f"Executing {step.step_id}: {step.description}")

            # Build context from dependencies
            prior_context = self._build_prior_context(step, context_accumulator)

            # Enhance query with prior context
            enhanced_query = self._enhance_query_with_context(step.query, prior_context)

            # Execute retrieval for this step
            result = await self.retriever_service.retrieve(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                query=enhanced_query,
                token_budget=token_budget_per_step,
            )

            # Extract key information from results
            # Handle both UnifiedRetrievalResult and RetrievalResult
            chunks = self._extract_chunks(result)

            step_result = StepResult(
                step_id=step.step_id,
                chunks=chunks,
                summary=self._summarize_step_results(result, chunks),
                key_symbols=self._extract_key_symbols(result, chunks),
                metadata={
                    "query": enhanced_query,
                    "intent": getattr(result, "intent_kind", None) or getattr(result, "intent", "unknown"),
                    "num_chunks": len(chunks),
                },
            )

            step_results.append(step_result)

            # Update context accumulator
            context_accumulator[step.step_id] = {
                "chunks": step_result.chunks,
                "symbols": step_result.key_symbols,
                "summary": step_result.summary,
            }

            logger.info(
                f"{step.step_id} complete: {len(step_result.chunks)} chunks, {len(step_result.key_symbols)} key symbols"
            )

        # Build final result
        final_result = self._build_final_result(decomposed, step_results)

        logger.info(f"Multi-hop retrieval complete: {len(final_result.final_chunks)} final chunks")

        return final_result

    def _build_prior_context(self, step, context_accumulator: dict) -> dict:
        """
        Build context from previous steps.

        Args:
            step: Current step
            context_accumulator: Results from previous steps

        Returns:
            Dict with prior context
        """
        prior_context = {
            "symbols": [],
            "files": [],
            "summaries": [],
        }

        for dep_id in step.dependencies:
            if dep_id in context_accumulator:
                dep_context = context_accumulator[dep_id]

                prior_context["symbols"].extend(dep_context.get("symbols", []))
                prior_context["summaries"].append(dep_context.get("summary", ""))

                # Extract file paths
                for chunk in dep_context.get("chunks", []):
                    file_path = chunk.get("file_path")
                    if file_path and file_path not in prior_context["files"]:
                        prior_context["files"].append(file_path)

        return prior_context

    def _enhance_query_with_context(self, query: str, prior_context: dict) -> str:
        """
        Enhance query with context from previous steps.

        Args:
            query: Original step query
            prior_context: Context from previous steps

        Returns:
            Enhanced query string
        """
        if not prior_context["symbols"] and not prior_context["files"]:
            return query

        # Add context hints
        context_parts = []

        if prior_context["symbols"]:
            symbols_str = " ".join(prior_context["symbols"][:5])  # Top 5
            context_parts.append(f"related to: {symbols_str}")

        if prior_context["files"]:
            files_str = " ".join(prior_context["files"][:3])  # Top 3
            context_parts.append(f"in files: {files_str}")

        if context_parts:
            enhanced = f"{query} ({', '.join(context_parts)})"
            logger.debug(f"Enhanced query: {enhanced}")
            return enhanced

        return query

    def _extract_chunks(self, result) -> list[dict]:
        """
        Extract chunks from result (handles both UnifiedRetrievalResult and RetrievalResult).

        Args:
            result: Retrieval result

        Returns:
            List of chunk dictionaries
        """
        chunks = []

        # Check if result has 'chunks' attribute (UnifiedRetrievalResult)
        if hasattr(result, "chunks") and isinstance(result.chunks, list):
            # Already in dict format
            for chunk in result.chunks:
                if isinstance(chunk, dict):
                    chunks.append(chunk)
                else:
                    # Convert object to dict
                    chunks.append(
                        {
                            "chunk_id": getattr(chunk, "chunk_id", ""),
                            "content": getattr(chunk, "content", ""),
                            "file_path": getattr(chunk, "file_path", ""),
                            "score": getattr(chunk, "priority_score", 0.0) or getattr(chunk, "score", 0.0),
                        }
                    )
        # Check if result has 'context.chunks' (RetrievalResult)
        elif hasattr(result, "context") and hasattr(result.context, "chunks"):
            for chunk in result.context.chunks:
                chunks.append(
                    {
                        "chunk_id": getattr(chunk, "chunk_id", ""),
                        "content": getattr(chunk, "content", ""),
                        "file_path": getattr(chunk, "file_path", ""),
                        "score": getattr(chunk, "priority_score", 0.0),
                    }
                )

        return chunks

    def _summarize_step_results(self, result, chunks: list[dict]) -> str:
        """Summarize results from a step."""
        if not chunks:
            return "No results found"

        # Simple summary based on top chunks
        top_files = list({chunk.get("file_path") for chunk in chunks[:5] if chunk.get("file_path")})

        summary = f"Found {len(chunks)} relevant chunks"
        if top_files:
            summary += f" in {len(top_files)} files: {', '.join(top_files[:3])}"

        return summary

    def _extract_key_symbols(self, result, chunks: list[dict]) -> list[str]:
        """Extract key symbols from step results."""
        symbols = set()

        for chunk in chunks[:10]:  # Top 10
            # Try to extract symbol names from metadata
            metadata = chunk.get("metadata", {})
            if isinstance(metadata, dict) and "symbol_id" in metadata:
                symbol_id = metadata["symbol_id"]
                if symbol_id:
                    # Extract name from symbol_id (simplified)
                    parts = symbol_id.split(":")
                    if parts:
                        symbols.add(parts[-1])

        return list(symbols)[:10]  # Limit to 10

    def _build_final_result(self, decomposed: DecomposedQuery, step_results: list[StepResult]) -> MultiHopResult:
        """
        Build final multi-hop result.

        Args:
            decomposed: Original decomposed query
            step_results: Results from all steps

        Returns:
            MultiHopResult with consolidated chunks
        """
        # Collect all chunks from all steps
        all_chunks = []
        seen_chunk_ids = set()

        for step_result in step_results:
            for chunk in step_result.chunks:
                chunk_id = chunk.get("chunk_id")
                if chunk_id and chunk_id not in seen_chunk_ids:
                    seen_chunk_ids.add(chunk_id)
                    all_chunks.append(chunk)

        # Sort by score (descending)
        all_chunks.sort(key=lambda c: c.get("score", 0), reverse=True)

        # Limit total chunks
        final_chunks = all_chunks[:50]

        # Build reasoning chain
        reasoning_chain = self._build_reasoning_chain(decomposed, step_results)

        return MultiHopResult(
            decomposed_query=decomposed,
            step_results=step_results,
            final_chunks=final_chunks,
            reasoning_chain=reasoning_chain,
            metadata={
                "num_steps": len(step_results),
                "total_chunks": len(all_chunks),
                "final_chunks": len(final_chunks),
            },
        )

    def _build_reasoning_chain(self, decomposed: DecomposedQuery, step_results: list[StepResult]) -> str:
        """Build reasoning chain showing how steps connect."""
        lines = [f"Query: {decomposed.original_query}", f"Strategy: {decomposed.reasoning}", ""]

        for i, (step, result) in enumerate(zip(decomposed.steps, step_results, strict=False), start=1):
            lines.append(f"Step {i}: {step.description}")
            lines.append(f"  → {result.summary}")
            if result.key_symbols:
                lines.append(f"  → Key symbols: {', '.join(result.key_symbols[:5])}")
            lines.append("")

        lines.append(f"Final: {len(step_results[-1].chunks)} chunks from multi-hop search")

        return "\n".join(lines)
