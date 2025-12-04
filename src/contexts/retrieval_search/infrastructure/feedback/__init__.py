"""
Feedback Module (Phase 2 SOTA)

User feedback collection and model improvement through hard negative mining.
"""

from typing import TYPE_CHECKING

from src.contexts.retrieval_search.infrastructure.feedback.hard_negatives import (
    HardNegativeMiner,
    RetrainingTrigger,
    TrainingSample,
)

if TYPE_CHECKING:
    from src.contexts.retrieval_search.infrastructure.feedback.contrastive_training import (
        ContrastiveRetrainingPipeline,
        EmbeddingModel,
    )


def __getattr__(name: str):
    """Lazy import for ML model classes."""
    if name == "ContrastiveRetrainingPipeline":
        from src.contexts.retrieval_search.infrastructure.feedback.contrastive_training import (
            ContrastiveRetrainingPipeline,
        )

        return ContrastiveRetrainingPipeline
    if name == "EmbeddingModel":
        from src.contexts.retrieval_search.infrastructure.feedback.contrastive_training import EmbeddingModel

        return EmbeddingModel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Hard Negative Mining (lightweight)
    "HardNegativeMiner",
    "TrainingSample",
    "RetrainingTrigger",
    # Contrastive Training (ML models - lazy import via TYPE_CHECKING)
    "ContrastiveRetrainingPipeline",
    "EmbeddingModel",
]
