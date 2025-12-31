"""
Contrastive Retraining Pipeline

Uses hard negatives for contrastive learning to improve retrieval quality.
"""

from typing import Protocol

import numpy as np

from codegraph_shared.common.observability import get_logger
from codegraph_search.infrastructure.feedback.hard_negatives import TrainingSample

logger = get_logger(__name__)


class EmbeddingModel(Protocol):
    """Protocol for embedding models."""

    def encode(self, text: str) -> np.ndarray:
        """Encode text into embedding."""
        ...

    def train_step(self, loss: float) -> None:
        """Execute single training step."""
        ...


class ContrastiveRetrainingPipeline:
    """
    Contrastive learning pipeline using hard negatives.

    Loss function (from 실행안):
    - Pull positive closer to query
    - Push hard negatives farther from query

    Contrastive Loss:
        L = -log(exp(sim(q, p) / τ) / (exp(sim(q, p) / τ) + Σ exp(sim(q, n_i) / τ)))

    where:
    - q: query embedding
    - p: positive chunk embedding
    - n_i: hard negative chunk embeddings
    - τ: temperature parameter
    """

    def __init__(
        self,
        embedding_model: EmbeddingModel | None = None,
        temperature: float = 0.07,
        learning_rate: float = 1e-5,
        batch_size: int = 32,
    ):
        """
        Initialize contrastive retraining pipeline.

        Args:
            embedding_model: Embedding model to train
            temperature: Temperature parameter for contrastive loss
            learning_rate: Learning rate
            batch_size: Batch size for training
        """
        self.embedding_model = embedding_model
        self.temperature = temperature
        self.learning_rate = learning_rate
        self.batch_size = batch_size

    def train(
        self,
        training_samples: list[TrainingSample],
        chunk_store: dict[str, str],  # chunk_id → content
        epochs: int = 3,
    ) -> dict:
        """
        Train embedding model using contrastive learning.

        Args:
            training_samples: List of training samples with hard negatives
            chunk_store: Dict mapping chunk_id to content
            epochs: Number of training epochs

        Returns:
            Training metrics dict
        """
        if not self.embedding_model:
            logger.warning("No embedding model provided - skipping training")
            return {"status": "skipped", "reason": "no_model"}

        logger.info(
            f"Starting contrastive training: "
            f"{len(training_samples)} samples, "
            f"{epochs} epochs, "
            f"temperature={self.temperature}"
        )

        total_loss = 0.0
        num_batches = 0

        for epoch in range(epochs):
            epoch_loss = 0.0

            # Shuffle samples
            import random

            samples = training_samples.copy()
            random.shuffle(samples)

            # Process in batches
            for i in range(0, len(samples), self.batch_size):
                batch = samples[i : i + self.batch_size]

                # Compute contrastive loss for batch
                batch_loss = self._compute_batch_loss(batch, chunk_store)

                # Training step (simplified - actual implementation would use optimizer)
                if batch_loss > 0:
                    self.embedding_model.train_step(batch_loss)

                epoch_loss += batch_loss
                num_batches += 1

            avg_epoch_loss = epoch_loss / max(len(samples), 1)
            total_loss += epoch_loss

            logger.info(f"Epoch {epoch + 1}/{epochs}: avg_loss={avg_epoch_loss:.4f}")

        avg_total_loss = total_loss / max(num_batches, 1)

        logger.info(f"Training complete: avg_loss={avg_total_loss:.4f}")

        return {
            "status": "completed",
            "epochs": epochs,
            "num_samples": len(training_samples),
            "avg_loss": avg_total_loss,
        }

    def _compute_batch_loss(self, batch: list[TrainingSample], chunk_store: dict[str, str]) -> float:
        """
        Compute contrastive loss for a batch.

        Args:
            batch: Batch of training samples
            chunk_store: Chunk content mapping

        Returns:
            Average loss for batch
        """
        if not self.embedding_model:
            return 0.0

        batch_losses = []

        for sample in batch:
            # Get query embedding
            query_emb = self.embedding_model.encode(sample.query)

            # Get positive chunk embedding
            positive_content = chunk_store.get(sample.positive_chunk_id, "")
            if not positive_content:
                logger.warning(f"Positive chunk not found: {sample.positive_chunk_id}")
                continue

            positive_emb = self.embedding_model.encode(positive_content)

            # Get hard negative embeddings
            negative_embs = []
            for neg_id in sample.hard_negatives:
                neg_content = chunk_store.get(neg_id, "")
                if neg_content:
                    neg_emb = self.embedding_model.encode(neg_content)
                    negative_embs.append(neg_emb)

            if not negative_embs:
                logger.warning(f"No hard negatives found for sample: {sample.query[:50]}")
                continue

            # Compute contrastive loss
            loss = self._contrastive_loss(query_emb, positive_emb, negative_embs)
            batch_losses.append(loss)

        if not batch_losses:
            return 0.0

        return float(np.mean(batch_losses))

    def _contrastive_loss(
        self,
        query_emb: np.ndarray,
        positive_emb: np.ndarray,
        negative_embs: list[np.ndarray],
    ) -> float:
        """
        Compute contrastive loss.

        Loss = -log(exp(sim(q, p) / τ) / (exp(sim(q, p) / τ) + Σ exp(sim(q, n_i) / τ)))

        Args:
            query_emb: Query embedding
            positive_emb: Positive chunk embedding
            negative_embs: List of hard negative embeddings

        Returns:
            Contrastive loss value
        """
        # Compute similarities (cosine similarity)
        pos_sim = self._cosine_similarity(query_emb, positive_emb)

        neg_sims = [self._cosine_similarity(query_emb, neg_emb) for neg_emb in negative_embs]

        # Apply temperature scaling
        pos_logit = pos_sim / self.temperature
        neg_logits = [sim / self.temperature for sim in neg_sims]

        # Compute log-sum-exp for numerical stability
        all_logits = [pos_logit] + neg_logits
        max_logit = max(all_logits)

        # Numerator: exp(pos_logit - max_logit)
        numerator = np.exp(pos_logit - max_logit)

        # Denominator: sum of all exp(logit - max_logit)
        denominator = sum(np.exp(logit - max_logit) for logit in all_logits)

        # Loss: -log(numerator / denominator)
        loss = -np.log(numerator / denominator + 1e-8)

        return float(loss)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))
