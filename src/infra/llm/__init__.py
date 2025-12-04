"""LLM provider adapters."""

from src.infra.llm.litellm_adapter import (
    LiteLLMAdapter,
    create_anthropic_adapter,
    create_litellm_adapter,
    create_ollama_adapter,
    create_openai_adapter,
)
from src.infra.llm.local_llm import (
    LocalEmbeddingProvider,
    LocalIntentClassifier,
    LocalLLMAdapter,
    LocalReranker,
    # Backward compatibility aliases
    OllamaAdapter,
    OllamaEmbeddingProvider,
    OllamaIntentClassifier,
    OllamaReranker,
)
from src.infra.llm.openai import OpenAIAdapter

__all__ = [
    # LiteLLM (recommended)
    "LiteLLMAdapter",
    "create_litellm_adapter",
    "create_openai_adapter",
    "create_anthropic_adapter",
    "create_ollama_adapter",
    # Local LLM adapters (provider-agnostic)
    "LocalLLMAdapter",
    "LocalEmbeddingProvider",
    "LocalReranker",
    "LocalIntentClassifier",
    # Legacy adapters
    "OpenAIAdapter",
    # Backward compatibility aliases
    "OllamaAdapter",
    "OllamaEmbeddingProvider",
    "OllamaReranker",
    "OllamaIntentClassifier",
]
