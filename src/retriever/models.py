"""
Retriever Layer Models

Top-level models for retrieval results.
"""

from dataclasses import dataclass, field

from .context_builder.models import ContextResult
from .fusion.engine import FusedHit
from .intent.models import IntentClassificationResult
from .scope.models import ScopeResult


@dataclass
class RetrievalResult:
    """
    Complete retrieval result.

    Attributes:
        query: Original query
        intent_result: Intent classification result
        scope_result: Scope selection result
        fused_hits: Fused search hits (sorted by priority)
        context: Built context for LLM
        metadata: Additional metadata
    """

    query: str
    intent_result: IntentClassificationResult
    scope_result: ScopeResult
    fused_hits: list[FusedHit] = field(default_factory=list)
    context: ContextResult | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def total_hits(self) -> int:
        """Total number of fused hits."""
        return len(self.fused_hits)

    @property
    def context_chunks_count(self) -> int:
        """Number of chunks in context."""
        return self.context.chunk_count if self.context else 0

    @property
    def intent_kind(self) -> str:
        """Intent kind value."""
        return self.intent_result.intent.kind.value
