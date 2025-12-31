"""
Search Pipeline Context

Immutable context object passed through pipeline steps.
"""

from dataclasses import dataclass, field
from typing import Any

from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit

from ..models import FusedResultV3, IntentProbability


@dataclass
class SearchContext:
    """
    Immutable context for search pipeline.

    Each pipeline step receives context and returns modified context.
    Follows functional programming principles for testability.
    """

    # Input (immutable)
    repo_id: str
    snapshot_id: str
    original_query: str
    limit: int
    symbol_limit: int
    enable_cache: bool

    # Query enhancement (Step 0)
    query_variations: list[str] = field(default_factory=list)
    hyde_used: bool = False
    rag_fusion_used: bool = False

    # Intent classification (Step 1)
    intent_prob: IntentProbability | None = None
    dominant_intent: str | None = None

    # Search execution (Step 2)
    hits_by_strategy: dict[str, list[SearchHit]] = field(default_factory=dict)
    search_mode: str | None = None  # "parallel", "sequential", "routing"
    early_stopped: bool = False

    # Fusion (Step 3)
    fused_results: list[FusedResultV3] = field(default_factory=list)

    # Reranking (Step 4)
    cross_encoder_used: bool = False
    position_bias_mitigated: bool = False

    # Metrics (Step 5)
    metrics: dict[str, Any] = field(default_factory=dict)
    step_timings: dict[str, float] = field(default_factory=dict)

    def with_query_variations(
        self,
        variations: list[str],
        hyde_used: bool = False,
        rag_fusion_used: bool = False,
    ) -> "SearchContext":
        """Create new context with query variations."""
        return SearchContext(
            repo_id=self.repo_id,
            snapshot_id=self.snapshot_id,
            original_query=self.original_query,
            limit=self.limit,
            symbol_limit=self.symbol_limit,
            enable_cache=self.enable_cache,
            query_variations=variations,
            hyde_used=hyde_used,
            rag_fusion_used=rag_fusion_used,
            intent_prob=self.intent_prob,
            dominant_intent=self.dominant_intent,
            hits_by_strategy=self.hits_by_strategy,
            search_mode=self.search_mode,
            early_stopped=self.early_stopped,
            fused_results=self.fused_results,
            cross_encoder_used=self.cross_encoder_used,
            position_bias_mitigated=self.position_bias_mitigated,
            metrics=self.metrics,
            step_timings=self.step_timings,
        )

    def with_intent(
        self,
        intent_prob: IntentProbability,
        dominant_intent: str,
    ) -> "SearchContext":
        """Create new context with intent."""
        return SearchContext(
            repo_id=self.repo_id,
            snapshot_id=self.snapshot_id,
            original_query=self.original_query,
            limit=self.limit,
            symbol_limit=self.symbol_limit,
            enable_cache=self.enable_cache,
            query_variations=self.query_variations,
            hyde_used=self.hyde_used,
            rag_fusion_used=self.rag_fusion_used,
            intent_prob=intent_prob,
            dominant_intent=dominant_intent,
            hits_by_strategy=self.hits_by_strategy,
            search_mode=self.search_mode,
            early_stopped=self.early_stopped,
            fused_results=self.fused_results,
            cross_encoder_used=self.cross_encoder_used,
            position_bias_mitigated=self.position_bias_mitigated,
            metrics=self.metrics,
            step_timings=self.step_timings,
        )

    def with_search_results(
        self,
        hits_by_strategy: dict[str, list[SearchHit]],
        search_mode: str,
        early_stopped: bool = False,
    ) -> "SearchContext":
        """Create new context with search results."""
        return SearchContext(
            repo_id=self.repo_id,
            snapshot_id=self.snapshot_id,
            original_query=self.original_query,
            limit=self.limit,
            symbol_limit=self.symbol_limit,
            enable_cache=self.enable_cache,
            query_variations=self.query_variations,
            hyde_used=self.hyde_used,
            rag_fusion_used=self.rag_fusion_used,
            intent_prob=self.intent_prob,
            dominant_intent=self.dominant_intent,
            hits_by_strategy=hits_by_strategy,
            search_mode=search_mode,
            early_stopped=early_stopped,
            fused_results=self.fused_results,
            cross_encoder_used=self.cross_encoder_used,
            position_bias_mitigated=self.position_bias_mitigated,
            metrics=self.metrics,
            step_timings=self.step_timings,
        )

    def with_fused_results(
        self,
        fused_results: list[FusedResultV3],
    ) -> "SearchContext":
        """Create new context with fused results."""
        return SearchContext(
            repo_id=self.repo_id,
            snapshot_id=self.snapshot_id,
            original_query=self.original_query,
            limit=self.limit,
            symbol_limit=self.symbol_limit,
            enable_cache=self.enable_cache,
            query_variations=self.query_variations,
            hyde_used=self.hyde_used,
            rag_fusion_used=self.rag_fusion_used,
            intent_prob=self.intent_prob,
            dominant_intent=self.dominant_intent,
            hits_by_strategy=self.hits_by_strategy,
            search_mode=self.search_mode,
            early_stopped=self.early_stopped,
            fused_results=fused_results,
            cross_encoder_used=self.cross_encoder_used,
            position_bias_mitigated=self.position_bias_mitigated,
            metrics=self.metrics,
            step_timings=self.step_timings,
        )

    def with_reranking_flags(
        self,
        cross_encoder_used: bool = False,
        position_bias_mitigated: bool = False,
    ) -> "SearchContext":
        """Create new context with reranking flags."""
        return SearchContext(
            repo_id=self.repo_id,
            snapshot_id=self.snapshot_id,
            original_query=self.original_query,
            limit=self.limit,
            symbol_limit=self.symbol_limit,
            enable_cache=self.enable_cache,
            query_variations=self.query_variations,
            hyde_used=self.hyde_used,
            rag_fusion_used=self.rag_fusion_used,
            intent_prob=self.intent_prob,
            dominant_intent=self.dominant_intent,
            hits_by_strategy=self.hits_by_strategy,
            search_mode=self.search_mode,
            early_stopped=self.early_stopped,
            fused_results=self.fused_results,
            cross_encoder_used=cross_encoder_used,
            position_bias_mitigated=position_bias_mitigated,
            metrics=self.metrics,
            step_timings=self.step_timings,
        )

    def with_timing(self, step_name: str, duration_ms: float) -> "SearchContext":
        """Add step timing."""
        new_timings = {**self.step_timings, step_name: duration_ms}
        return SearchContext(
            repo_id=self.repo_id,
            snapshot_id=self.snapshot_id,
            original_query=self.original_query,
            limit=self.limit,
            symbol_limit=self.symbol_limit,
            enable_cache=self.enable_cache,
            query_variations=self.query_variations,
            hyde_used=self.hyde_used,
            rag_fusion_used=self.rag_fusion_used,
            intent_prob=self.intent_prob,
            dominant_intent=self.dominant_intent,
            hits_by_strategy=self.hits_by_strategy,
            search_mode=self.search_mode,
            early_stopped=self.early_stopped,
            fused_results=self.fused_results,
            cross_encoder_used=self.cross_encoder_used,
            position_bias_mitigated=self.position_bias_mitigated,
            metrics=self.metrics,
            step_timings=new_timings,
        )
