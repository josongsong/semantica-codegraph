"""
Observability Module (Phase 3 SOTA)

Full observability and explainability for retrieval results.
"""

from .explainer import RetrievalExplainer
from .models import Explanation, RetrievalTrace, SourceBreakdown
from .tracing import RetrievalTracer, TraceCollector, TracingRetrieverWrapper

__all__ = [
    # Models
    "SourceBreakdown",
    "Explanation",
    "RetrievalTrace",
    # Explainer
    "RetrievalExplainer",
    # Tracing
    "RetrievalTracer",
    "TracingRetrieverWrapper",
    "TraceCollector",
]
