"""
Fake LLM Provider for Unit Testing
"""


import numpy as np


class FakeLLMProvider:
    """
    LLMProviderPort Fake 구현.

    실제 API 호출 없이 동작.
    """

    def __init__(self, embedding_dim: int = 1536):
        self.embedding_dim = embedding_dim

    def embed(self, text: str) -> list[float]:
        """
        Deterministic embedding 생성 (단어 매칭 기반 유사도 반영).

        텍스트를 단어로 분리하고, 각 단어에 대해 고정된 벡터를 할당한 뒤,
        평균을 내어 최종 벡터를 생성합니다.
        이 방식은 공통 단어가 많을수록 벡터가 유사해집니다.
        """
        # 텍스트를 소문자로 변환 후 단어 분리
        words = text.lower().split()

        if not words:
            # 빈 텍스트는 zero vector
            return [0.0] * self.embedding_dim

        # 각 단어에 대해 고정된 벡터 생성 (단어 해시 기반)
        word_vectors = []
        for word in words:
            np.random.seed(hash(word) % (2**32))
            word_vec = np.random.randn(self.embedding_dim)
            word_vectors.append(word_vec)

        # 단어 벡터들의 평균
        vector = np.mean(word_vectors, axis=0)

        # Normalize
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm

        result: list[float] = vector.tolist()
        return result

    def complete(self, prompt: str, max_tokens: int = 100) -> str:
        """
        Mock completion.

        테스트용으로 단순 응답 반환.
        """
        return f"Mock response to: {prompt[:50]}"

    def chat(self, messages: list[dict]) -> str:
        """Mock chat completion."""
        last_message = messages[-1]["content"] if messages else ""
        return f"Mock chat response to: {last_message[:50]}"

    async def generate(self, prompt: str, max_tokens: int = 500, temperature: float = 0.3) -> str:
        """
        Async text generation (LLMPort protocol).

        Returns a mock summary for testing.
        """
        # Generate a simple summary based on prompt
        if "function" in prompt.lower():
            return "This function processes data and returns the result."
        elif "class" in prompt.lower():
            return "This class manages state and provides methods for operations."
        elif "file" in prompt.lower():
            return "This file contains utility functions and classes."
        else:
            return "This code element provides functionality for the system."


# Alias for backward compatibility
FakeLLM = FakeLLMProvider
