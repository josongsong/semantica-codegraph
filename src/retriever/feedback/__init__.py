"""
Feedback Module (Phase 2 SOTA)

User feedback collection and model improvement through hard negative mining.
"""

from .contrastive_training import ContrastiveRetrainingPipeline, EmbeddingModel
from .hard_negatives import HardNegativeMiner, RetrainingTrigger, TrainingSample

__all__ = [
    # Hard Negative Mining
    "HardNegativeMiner",
    "TrainingSample",
    "RetrainingTrigger",
    # Contrastive Training
    "ContrastiveRetrainingPipeline",
    "EmbeddingModel",
]
