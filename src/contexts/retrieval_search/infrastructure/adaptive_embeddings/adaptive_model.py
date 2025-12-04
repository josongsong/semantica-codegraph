"""
Adaptive Embedding Model

Embedding model that uses repo-specific LoRA adaptations.
"""

import numpy as np

from src.contexts.retrieval_search.infrastructure.adaptive_embeddings.models import RepoAdaptation


class AdaptiveEmbeddingModel:
    """
    Embedding model with repo-adaptive LoRA.

    Uses base embeddings + repo-specific LoRA weights for improved search.
    """

    def __init__(self, base_embedding_model):
        """
        Initialize adaptive model.

        Args:
            base_embedding_model: Base embedding model
        """
        self.base_model = base_embedding_model
        self.adaptations: dict[str, RepoAdaptation] = {}

    def load_adaptation(self, adaptation: RepoAdaptation):
        """
        Load LoRA adaptation for a repository.

        Args:
            adaptation: RepoAdaptation with LoRA weights
        """
        self.adaptations[adaptation.repo_id] = adaptation

    def unload_adaptation(self, repo_id: str):
        """Unload adaptation for a repository."""
        if repo_id in self.adaptations:
            del self.adaptations[repo_id]

    def embed(self, text: str, repo_id: str | None = None) -> np.ndarray:
        """
        Get embedding for text, with optional repo adaptation.

        Args:
            text: Text to embed
            repo_id: Optional repository ID for adaptation

        Returns:
            Embedding vector
        """
        # Get base embedding
        base_emb = self._get_base_embedding(text)

        # Apply LoRA if adaptation exists
        if repo_id and repo_id in self.adaptations:
            adaptation = self.adaptations[repo_id]
            return self._apply_lora(base_emb, adaptation.lora_weights)

        return base_emb

    def embed_batch(self, texts: list[str], repo_id: str | None = None) -> list[np.ndarray]:
        """
        Get embeddings for batch of texts.

        Args:
            texts: List of texts to embed
            repo_id: Optional repository ID for adaptation

        Returns:
            List of embedding vectors
        """
        return [self.embed(text, repo_id) for text in texts]

    def is_adapted(self, repo_id: str) -> bool:
        """Check if adaptation is loaded for a repository."""
        return repo_id in self.adaptations

    def get_adaptation_info(self, repo_id: str) -> dict[str, any] | None:
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

    def _get_base_embedding(self, text: str) -> np.ndarray:
        """
        Get base embedding from underlying model.

        Args:
            text: Text to embed

        Returns:
            Base embedding
        """
        # In real implementation, call actual embedding model
        # Using placeholder here
        return np.random.randn(768)

    def _apply_lora(self, base_emb: np.ndarray, lora_weights: dict[str, any]) -> np.ndarray:
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
                except ValueError:
                    # Shape mismatch, skip this module
                    continue

        return adapted_emb


class AdaptiveSearchWrapper:
    """
    Wrapper that integrates adaptive embeddings into search.

    Automatically uses repo-specific adaptations when available.
    """

    def __init__(
        self,
        base_search_service,
        adaptive_model: AdaptiveEmbeddingModel,
    ):
        """
        Initialize wrapper.

        Args:
            base_search_service: Base search service
            adaptive_model: Adaptive embedding model
        """
        self.base_search = base_search_service
        self.adaptive_model = adaptive_model

    async def search(
        self,
        repo_id: str,
        query: str,
        top_k: int = 20,
        use_adaptation: bool = True,
    ) -> list[dict]:
        """
        Search with optional repo adaptation.

        Args:
            repo_id: Repository identifier
            query: Search query
            top_k: Number of results
            use_adaptation: Whether to use adaptation if available

        Returns:
            Search results
        """
        # Get query embedding (with adaptation if enabled and available)
        if use_adaptation and self.adaptive_model.is_adapted(repo_id):
            query_embedding = self.adaptive_model.embed(query, repo_id)
        else:
            query_embedding = self.adaptive_model.embed(query, repo_id=None)

        # Perform search with adapted embedding
        results = await self.base_search.search(
            repo_id=repo_id,
            query_embedding=query_embedding,
            top_k=top_k,
        )

        # Add adaptation metadata
        for result in results:
            result["used_adaptation"] = use_adaptation and self.adaptive_model.is_adapted(repo_id)

        return results

    def get_adaptation_status(self, repo_id: str) -> dict[str, any]:
        """Get adaptation status for UI/debugging."""
        is_adapted = self.adaptive_model.is_adapted(repo_id)

        if is_adapted:
            info = self.adaptive_model.get_adaptation_info(repo_id)
            return {
                "adapted": True,
                "info": info,
            }

        return {
            "adapted": False,
            "info": None,
        }
