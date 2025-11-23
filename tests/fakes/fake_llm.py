"""
Fake LLM Provider for Unit Testing
"""

from typing import List, Dict
import numpy as np


class FakeLLMProvider:
    """
    LLMProviderPort Fake 구현.

    실제 API 호출 없이 동작.
    """

    def __init__(self, embedding_dim: int = 1536):
        self.embedding_dim = embedding_dim

    def embed(self, text: str) -> List[float]:
        """
        Deterministic embedding 생성.

        텍스트 해시 기반으로 일관된 벡터 생성.
        """
        # 간단한 해시 기반 벡터
        np.random.seed(hash(text) % (2**32))
        vector = np.random.randn(self.embedding_dim)
        # Normalize
        vector = vector / np.linalg.norm(vector)
        return vector.tolist()

    def complete(self, prompt: str, max_tokens: int = 100) -> str:
        """
        Mock completion.

        테스트용으로 단순 응답 반환.
        """
        return f"Mock response to: {prompt[:50]}"

    def chat(self, messages: List[Dict]) -> str:
        """Mock chat completion."""
        last_message = messages[-1]["content"] if messages else ""
        return f"Mock chat response to: {last_message[:50]}"
