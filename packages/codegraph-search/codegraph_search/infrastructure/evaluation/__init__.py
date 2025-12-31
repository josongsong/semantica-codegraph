"""
Retriever Evaluation Module

Golden Set construction, feedback collection, and evaluation metrics.

Phase 1 P0-2: Golden Set Construction (Layer 18)
"""

from codegraph_search.infrastructure.evaluation.evaluator import RetrieverEvaluator
from codegraph_search.infrastructure.evaluation.feedback_service import FeedbackService
from codegraph_search.infrastructure.evaluation.golden_set_service import GoldenSetService
from codegraph_search.infrastructure.evaluation.metrics import (
    compute_all_metrics,
    mean_average_precision,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from codegraph_search.infrastructure.evaluation.models import (
    EvaluationResult,
    FeedbackAction,
    FeedbackLog,
    GoldenSetQuery,
    QueryDifficulty,
    QueryIntent,
)

__all__ = [
    # Models
    "GoldenSetQuery",
    "FeedbackLog",
    "EvaluationResult",
    "QueryIntent",
    "QueryDifficulty",
    "FeedbackAction",
    # Services
    "GoldenSetService",
    "FeedbackService",
    "RetrieverEvaluator",
    # Metrics
    "mean_reciprocal_rank",
    "mean_average_precision",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
    "compute_all_metrics",
]
