"""
Adapter for integrating V3 retriever with existing pipeline.

Bridges MultiIndexResult → V3 Service → Context Builder.
"""

import logging
from typing import Any

from src.index.common.documents import SearchHit
from src.retriever.context_builder import ContextBuilder, ContextChunk, ContextResult
from src.retriever.multi_index import MultiIndexResult

from .config import RetrieverV3Config
from .models import FusedResultV3, IntentProbability
from .service import RetrieverV3Service

logger = logging.getLogger(__name__)


class V3RetrieverAdapter:
    """
    Adapter for integrating V3 retriever into existing pipeline.

    Usage:
        adapter = V3RetrieverAdapter(config=config)

        # From multi-index orchestrator
        multi_result = await orchestrator.search(...)

        # Use v3 fusion
        fused_results, intent = adapter.fuse_multi_index_result(
            query=query,
            multi_result=multi_result,
        )

        # Build context
        context = adapter.build_context(
            fused_results=fused_results,
            token_budget=4000,
        )
    """

    def __init__(
        self,
        config: RetrieverV3Config | None = None,
        context_builder: ContextBuilder | None = None,
    ):
        """
        Initialize adapter.

        Args:
            config: V3 configuration (uses default if None)
            context_builder: Context builder instance (creates default if None)
        """
        self.config = config or RetrieverV3Config()
        self.v3_service = RetrieverV3Service(config=self.config)
        self.context_builder = context_builder

    def fuse_multi_index_result(
        self,
        query: str,
        multi_result: MultiIndexResult,
        metadata_map: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[list[FusedResultV3], IntentProbability]:
        """
        Fuse multi-index result using V3 engine.

        Args:
            query: Query string
            multi_result: Result from MultiIndexOrchestrator
            metadata_map: Optional metadata for chunks

        Returns:
            Tuple of (fused_results, intent_probability)
        """
        # Convert MultiIndexResult to hits_by_strategy dict
        hits_by_strategy = {
            "vector": multi_result.vector_hits,
            "lexical": multi_result.lexical_hits,
            "symbol": multi_result.symbol_hits,
            "graph": multi_result.graph_hits,
        }

        # Remove empty strategies
        hits_by_strategy = {k: v for k, v in hits_by_strategy.items() if v}

        # Execute V3 fusion
        fused_results, intent_prob = self.v3_service.retrieve(
            query=query,
            hits_by_strategy=hits_by_strategy,
            metadata_map=metadata_map,
            enable_cache=False,  # Disable cache for now
        )

        logger.info(
            f"V3 fusion complete: {len(fused_results)} results, "
            f"intent={intent_prob.dominant_intent()}"
        )

        return fused_results, intent_prob

    def build_context(
        self,
        fused_results: list[FusedResultV3],
        token_budget: int = 4000,
    ) -> ContextResult | None:
        """
        Build context from fused results.

        Args:
            fused_results: Fused results from V3
            token_budget: Token budget for context

        Returns:
            ContextResult or None if context_builder not available
        """
        if not self.context_builder:
            logger.warning("Context builder not available")
            return None

        # Convert FusedResultV3 to ContextChunk-compatible format
        # For now, use simplified conversion
        # TODO: Implement proper FusedResultV3 → ContextChunk conversion

        logger.info(f"Building context with {len(fused_results)} results")

        # Simplified: just use first N results based on token budget
        # In production, should use proper token counting
        context_chunks = []
        estimated_tokens = 0
        tokens_per_chunk = 200  # Rough estimate

        for result in fused_results:
            if estimated_tokens + tokens_per_chunk > token_budget:
                break

            # Create simple context chunk
            chunk = ContextChunk(
                chunk_id=result.chunk_id,
                file_path=result.file_path or "",
                content="",  # Would need to fetch actual content
                start_line=0,
                end_line=0,
                priority_score=result.final_score,
                token_count=tokens_per_chunk,
            )
            context_chunks.append(chunk)
            estimated_tokens += tokens_per_chunk

        # Create context result
        context = ContextResult(
            chunks=context_chunks,
            total_tokens=estimated_tokens,
            chunk_count=len(context_chunks),
            token_budget=token_budget,
        )

        logger.info(
            f"Context built: {context.chunk_count} chunks, {context.total_tokens} tokens"
        )

        return context

    def retrieve_with_context(
        self,
        query: str,
        multi_result: MultiIndexResult,
        token_budget: int = 4000,
        metadata_map: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[list[FusedResultV3], IntentProbability, ContextResult | None]:
        """
        Complete retrieval pipeline with V3 fusion and context building.

        Args:
            query: Query string
            multi_result: Result from MultiIndexOrchestrator
            token_budget: Token budget for context
            metadata_map: Optional metadata for chunks

        Returns:
            Tuple of (fused_results, intent, context)
        """
        # Fusion
        fused_results, intent = self.fuse_multi_index_result(
            query=query,
            multi_result=multi_result,
            metadata_map=metadata_map,
        )

        # Context building
        context = self.build_context(
            fused_results=fused_results,
            token_budget=token_budget,
        )

        return fused_results, intent, context


def convert_search_hit_to_metadata(hit: SearchHit) -> dict[str, Any]:
    """
    Convert SearchHit to metadata dict for V3.

    Args:
        hit: SearchHit from index

    Returns:
        Metadata dict
    """
    return {
        "chunk_id": hit.chunk_id,
        "file_path": hit.file_path,
        "symbol_id": hit.symbol_id,
        "chunk_size": hit.metadata.get("chunk_size", 0) if hit.metadata else 0,
        "symbol_type": hit.metadata.get("symbol_type", "") if hit.metadata else "",
    }


def build_metadata_map(multi_result: MultiIndexResult) -> dict[str, dict[str, Any]]:
    """
    Build metadata map from MultiIndexResult.

    Args:
        multi_result: Result from MultiIndexOrchestrator

    Returns:
        Dict of chunk_id → metadata
    """
    metadata_map = {}

    # Collect from all strategies
    for hits in [
        multi_result.vector_hits,
        multi_result.lexical_hits,
        multi_result.symbol_hits,
        multi_result.graph_hits,
    ]:
        for hit in hits:
            if hit.chunk_id not in metadata_map:
                metadata_map[hit.chunk_id] = convert_search_hit_to_metadata(hit)

    return metadata_map
