"""
Adaptive Embeddings Models

Models for LoRA-based repo-adaptive embeddings.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AdaptationExample:
    """
    Single example for adapting embeddings.

    Attributes:
        query: User query
        positive_chunk_id: Chunk that was relevant
        negative_chunk_ids: Chunks that were not relevant
        repo_id: Repository identifier
        timestamp: When this example was collected
        metadata: Additional metadata
    """

    query: str
    positive_chunk_id: str
    negative_chunk_ids: list[str] = field(default_factory=list)
    repo_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)


@dataclass
class LoRAConfig:
    """
    Configuration for LoRA adaptation.

    Attributes:
        rank: LoRA rank (typically 4-16)
        alpha: LoRA alpha scaling factor
        dropout: Dropout rate
        target_modules: Modules to apply LoRA to (e.g., ["q_proj", "v_proj"])
        learning_rate: Learning rate for training
        num_epochs: Number of training epochs
        batch_size: Training batch size
        warmup_steps: Warmup steps for learning rate
    """

    rank: int = 8
    alpha: float = 16.0
    dropout: float = 0.1
    target_modules: list[str] = field(default_factory=lambda: ["q_proj", "v_proj", "k_proj"])
    learning_rate: float = 3e-4
    num_epochs: int = 3
    batch_size: int = 16
    warmup_steps: int = 100


@dataclass
class RepoAdaptation:
    """
    LoRA weights for a specific repository.

    Attributes:
        repo_id: Repository identifier
        lora_weights: LoRA weight matrices
        training_samples: Number of samples used for training
        last_updated: When this adaptation was last updated
        performance_metrics: Metrics tracking improvement
        metadata: Additional metadata
    """

    repo_id: str
    lora_weights: dict[str, any] = field(default_factory=dict)
    training_samples: int = 0
    last_updated: datetime = field(default_factory=datetime.now)
    performance_metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class AdaptationStatus:
    """
    Status of adaptation for a repository.

    Attributes:
        repo_id: Repository identifier
        is_adapted: Whether adaptation has been applied
        samples_collected: Number of samples collected
        samples_required: Minimum samples required for adaptation
        last_adaptation: When last adapted
        adaptation_quality: Quality score (0-1)
    """

    repo_id: str
    is_adapted: bool = False
    samples_collected: int = 0
    samples_required: int = 100
    last_adaptation: datetime | None = None
    adaptation_quality: float = 0.0
