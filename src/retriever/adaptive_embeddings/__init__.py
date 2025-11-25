"""
Adaptive Embeddings Module (Phase 3 SOTA)

Repo-adaptive embeddings using LoRA (Low-Rank Adaptation).
"""

from .adaptive_model import AdaptiveEmbeddingModel, AdaptiveSearchWrapper
from .collector import AdaptationCollector
from .lora_trainer import LoRATrainer
from .models import (
    AdaptationExample,
    AdaptationStatus,
    LoRAConfig,
    RepoAdaptation,
)
from .openai_embedding_adapter import (
    OpenAIEmbeddingAdapter,
    ProductionAdaptiveEmbeddingModel,
)

__all__ = [
    # Models
    "AdaptationExample",
    "LoRAConfig",
    "RepoAdaptation",
    "AdaptationStatus",
    # Collector
    "AdaptationCollector",
    # Trainer
    "LoRATrainer",
    # Adaptive Model
    "AdaptiveEmbeddingModel",
    "AdaptiveSearchWrapper",
    # Production Adapters
    "OpenAIEmbeddingAdapter",
    "ProductionAdaptiveEmbeddingModel",
]
