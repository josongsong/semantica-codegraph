"""
Observability Module (Phase 3 SOTA)

Full observability and explainability for retrieval results.
"""

from typing import TYPE_CHECKING

from src.contexts.retrieval_search.infrastructure.observability.models import (
    Explanation,
    RetrievalTrace,
    SourceBreakdown,
)

if TYPE_CHECKING:
    from src.contexts.retrieval_search.infrastructure.observability.explainer import RetrievalExplainer
    from src.contexts.retrieval_search.infrastructure.observability.tracing import (
        RetrievalTracer,
        TraceCollector,
        TracingRetrieverWrapper,
    )


def __getattr__(name: str):
    """Lazy import for heavy classes."""
    if name == "RetrievalExplainer":
        from src.contexts.retrieval_search.infrastructure.observability.explainer import RetrievalExplainer

        return RetrievalExplainer
    if name == "RetrievalTracer":
        from src.contexts.retrieval_search.infrastructure.observability.tracing import RetrievalTracer

        return RetrievalTracer
    if name == "TraceCollector":
        from src.contexts.retrieval_search.infrastructure.observability.tracing import TraceCollector

        return TraceCollector
    if name == "TracingRetrieverWrapper":
        from src.contexts.retrieval_search.infrastructure.observability.tracing import TracingRetrieverWrapper

        return TracingRetrieverWrapper
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Models (lightweight)
    "SourceBreakdown",
    "Explanation",
    "RetrievalTrace",
    # Explainer (heavy - lazy import via TYPE_CHECKING)
    "RetrievalExplainer",
    # Tracing (heavy - lazy import via TYPE_CHECKING)
    "RetrievalTracer",
    "TracingRetrieverWrapper",
    "TraceCollector",
]
