"""
OpenAI Embedding Adapter

Production adapter for AdaptiveEmbeddingModel using OpenAI embeddings.
"""

from typing import Any

import numpy as np


class OpenAIEmbeddingAdapter:
    """
    Adapter for AdaptiveEmbeddingModel that uses OpenAI embeddings.

    Wraps the OpenAIAdapter from infra layer to provide the interface
    expected by AdaptiveEmbeddingModel.
    """

    def __init__(self, openai_adapter):
        """
        Initialize adapter.

        Args:
            openai_adapter: OpenAIAdapter instance from infra layer
        """
        self.openai_adapter = openai_adapter

    async def embed(self, text: str) -> np.ndarray:
        """
        Generate embedding for text.

        Args:
            text: Text to embed

        Returns:
            Embedding as numpy array
        """
        try:
            embedding = await self.openai_adapter.embed(text)
            return np.array(embedding, dtype=np.float32)
        except Exception as e:
            # Return zero vector on error
            print(f"Warning: Embedding failed for text, returning zero vector: {e}")
            return np.zeros(1536, dtype=np.float32)  # Default OpenAI embedding size

    async def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings as numpy arrays
        """
        try:
            embeddings = await self.openai_adapter.embed_batch(texts)
            return [np.array(emb, dtype=np.float32) for emb in embeddings]
        except Exception as e:
            # Return zero vectors on error
            print(f"Warning: Batch embedding failed, returning zero vectors: {e}")
            return [np.zeros(1536, dtype=np.float32) for _ in texts]  # Default OpenAI embedding size

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this model.

        Returns:
            Embedding dimension
        """
        # OpenAI text-embedding-3-small: 1536 dimensions
        # OpenAI text-embedding-3-large: 3072 dimensions
        # For now, return default
        return 1536


class ProductionAdaptiveEmbeddingModel:
    """
    Production-ready adaptive embedding model.

    Combines OpenAI embeddings with repo-specific LoRA adaptations.
    """

    def __init__(self, openai_adapter):
        """
        Initialize production adaptive model.

        Args:
            openai_adapter: OpenAIAdapter from infra layer
        """
        self.embedding_adapter = OpenAIEmbeddingAdapter(openai_adapter)
        self.adaptations: dict[str, Any] = {}  # RepoAdaptation objects

    def load_adaptation(self, adaptation):
        """
        Load LoRA adaptation for a repository.

        Args:
            adaptation: RepoAdaptation object with LoRA weights
        """
        self.adaptations[adaptation.repo_id] = adaptation

    def unload_adaptation(self, repo_id: str):
        """Unload adaptation for a repository."""
        if repo_id in self.adaptations:
            del self.adaptations[repo_id]

    async def embed(self, text: str, repo_id: str | None = None) -> np.ndarray:
        """
        Get embedding for text with optional repo adaptation.

        Args:
            text: Text to embed
            repo_id: Optional repository ID for adaptation

        Returns:
            Embedding vector
        """
        # Get base embedding from OpenAI
        base_emb = await self.embedding_adapter.embed(text)

        # Apply LoRA if adaptation exists
        if repo_id and repo_id in self.adaptations:
            adaptation = self.adaptations[repo_id]
            return self._apply_lora(base_emb, adaptation.lora_weights)

        return base_emb

    async def embed_batch(self, texts: list[str], repo_id: str | None = None) -> list[np.ndarray]:
        """
        Get embeddings for batch of texts.

        Args:
            texts: List of texts to embed
            repo_id: Optional repository ID for adaptation

        Returns:
            List of embedding vectors
        """
        # Get base embeddings
        base_embs = await self.embedding_adapter.embed_batch(texts)

        # Apply LoRA if adaptation exists
        if repo_id and repo_id in self.adaptations:
            adaptation = self.adaptations[repo_id]
            return [self._apply_lora(emb, adaptation.lora_weights) for emb in base_embs]

        return base_embs

    def is_adapted(self, repo_id: str) -> bool:
        """Check if adaptation is loaded for a repository."""
        return repo_id in self.adaptations

    def get_adaptation_info(self, repo_id: str) -> dict[str, Any] | None:
        """
        Get information about adaptation for a repository.

        Args:
            repo_id: Repository identifier

        Returns:
            Info dictionary or None if not adapted
        """
        if repo_id not in self.adaptations:
            return None

        adaptation = self.adaptations[repo_id]
        return {
            "repo_id": adaptation.repo_id,
            "training_samples": adaptation.training_samples,
            "last_updated": adaptation.last_updated.isoformat(),
            "metrics": adaptation.performance_metrics,
        }

    def _apply_lora(self, base_emb: np.ndarray, lora_weights: dict[str, Any]) -> np.ndarray:
        """
        Apply LoRA adaptation to base embedding.

        Args:
            base_emb: Base embedding
            lora_weights: LoRA weight matrices

        Returns:
            Adapted embedding
        """
        adapted_emb = base_emb.copy()

        # Typical scaling for LoRA
        rank = 8  # Default, should match training config
        alpha = 16.0
        scale = alpha / rank

        # Apply each LoRA module
        for module_key in lora_weights:
            if "_A" not in module_key:
                continue

            # Get A and B matrices for this module
            module_name = module_key.replace("_A", "")
            A = lora_weights.get(f"{module_name}_A")
            B = lora_weights.get(f"{module_name}_B")

            if A is not None and B is not None:
                # Compute delta: B @ (A @ x)
                try:
                    intermediate = A @ adapted_emb.reshape(-1, 1)
                    delta = B @ intermediate
                    adapted_emb = adapted_emb + (scale * delta.flatten())
                except (ValueError, Exception):
                    # Shape mismatch or other error, skip this module
                    continue

        return adapted_emb
