"""
Adaptive Embeddings Module (Phase 3 SOTA)

Repo-adaptive embeddings using LoRA (Low-Rank Adaptation).
"""

from typing import TYPE_CHECKING

from codegraph_ml.adaptive_embeddings.collector import AdaptationCollector
from codegraph_ml.adaptive_embeddings.models import (
    AdaptationExample,
    AdaptationStatus,
    LoRAConfig,
    RepoAdaptation,
)

if TYPE_CHECKING:
    from codegraph_search.infrastructure.adaptive_embeddings.lora_trainer import LoRATrainer
    from codegraph_search.infrastructure.adaptive_embeddings.openai_embedding_adapter import (
        OpenAIEmbeddingAdapter,
        ProductionAdaptiveEmbeddingModel,
    )

    from codegraph_ml.adaptive_embeddings.adaptive_model import (
        AdaptiveEmbeddingModel,
        AdaptiveSearchWrapper,
    )


def __getattr__(name: str):
    """Lazy import for ML model classes."""
    if name == "LoRATrainer":
        from codegraph_ml.adaptive_embeddings.lora_trainer import LoRATrainer

        return LoRATrainer
    if name == "AdaptiveEmbeddingModel":
        from codegraph_ml.adaptive_embeddings.adaptive_model import (
            AdaptiveEmbeddingModel,
        )

        return AdaptiveEmbeddingModel
    if name == "AdaptiveSearchWrapper":
        from codegraph_ml.adaptive_embeddings.adaptive_model import (
            AdaptiveSearchWrapper,
        )

        return AdaptiveSearchWrapper
    if name == "OpenAIEmbeddingAdapter":
        from codegraph_ml.adaptive_embeddings.openai_embedding_adapter import (
            OpenAIEmbeddingAdapter,
        )

        return OpenAIEmbeddingAdapter
    if name == "ProductionAdaptiveEmbeddingModel":
        from codegraph_ml.adaptive_embeddings.openai_embedding_adapter import (
            ProductionAdaptiveEmbeddingModel,
        )

        return ProductionAdaptiveEmbeddingModel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Models (lightweight)
    "AdaptationExample",
    "LoRAConfig",
    "RepoAdaptation",
    "AdaptationStatus",
    # Collector (lightweight)
    "AdaptationCollector",
    # Trainer (ML models - lazy import via TYPE_CHECKING)
    "LoRATrainer",
    # Adaptive Model (ML models - lazy import via TYPE_CHECKING)
    "AdaptiveEmbeddingModel",
    "AdaptiveSearchWrapper",
    # Production Adapters (ML models - lazy import via TYPE_CHECKING)
    "OpenAIEmbeddingAdapter",
    "ProductionAdaptiveEmbeddingModel",
]
