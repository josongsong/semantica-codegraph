"""
LLM Provider Port

Abstract interface for LLM and embedding operations.
Implementations: OpenAI, Anthropic, local models, etc.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from enum import Enum


class EmbeddingModel(str, Enum):
    """Supported embedding models."""
    OPENAI_SMALL = "text-embedding-3-small"
    OPENAI_LARGE = "text-embedding-3-large"
    OPENAI_ADA = "text-embedding-ada-002"


class LLMProviderPort(ABC):
    """
    Port for LLM and embedding operations.

    Responsibilities:
    - Generate embeddings
    - Generate text completions
    - Summarize code
    """

    @abstractmethod
    async def embed_texts(
        self,
        texts: List[str],
        model: EmbeddingModel = EmbeddingModel.OPENAI_SMALL,
    ) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings
            model: Embedding model to use

        Returns:
            List of embedding vectors
        """
        pass

    @abstractmethod
    async def embed_single(
        self,
        text: str,
        model: EmbeddingModel = EmbeddingModel.OPENAI_SMALL,
    ) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text string
            model: Embedding model to use

        Returns:
            Embedding vector
        """
        pass

    @abstractmethod
    async def generate_summary(
        self,
        code: str,
        language: str,
        max_tokens: int = 150,
    ) -> str:
        """
        Generate a natural language summary of code.

        Args:
            code: Source code
            language: Programming language
            max_tokens: Maximum tokens in summary

        Returns:
            Summary text
        """
        pass

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> str:
        """
        Generate text completion.

        Args:
            prompt: User prompt
            system_prompt: System prompt (optional)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature

        Returns:
            Generated text
        """
        pass

    @abstractmethod
    async def batch_summarize(
        self,
        code_snippets: List[Dict[str, Any]],
        language: str,
    ) -> List[str]:
        """
        Batch summarize multiple code snippets.

        Args:
            code_snippets: List of code snippets with metadata
            language: Programming language

        Returns:
            List of summaries
        """
        pass

    @abstractmethod
    def get_embedding_dimension(self, model: EmbeddingModel) -> int:
        """Get the dimension of embeddings for a model."""
        pass
