"""
LiteLLM Adapter

Unified LLM interface using LiteLLM for multi-provider support.
Includes automatic observability (tracing, cost tracking, logging).

Supported Providers:
- OpenAI (gpt-4o, gpt-4o-mini, gpt-3.5-turbo)
- Anthropic (claude-3-opus, claude-3-sonnet, claude-3-haiku)
- Azure OpenAI
- Ollama (local models)
- And many more via LiteLLM

Usage:
    from codegraph_shared.infra.llm import LiteLLMAdapter

    # Basic usage
    llm = LiteLLMAdapter(model="gpt-4o-mini")
    response = await llm.complete("Explain Python generators")

    # With chat messages
    response = await llm.chat([
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ])

    # Embeddings
    embedding = await llm.embed("Hello world")
"""

import time
from typing import Any

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

# Try to import LiteLLM
try:
    import litellm
    from litellm import acompletion, aembedding

    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    litellm = None
    acompletion = None
    aembedding = None

# Try to import observability
try:
    from codegraph_shared.infra.llm.metrics import (
        record_llm_error,
        record_llm_latency,
        record_llm_request,
        record_llm_tokens,
    )
    from codegraph_shared.infra.observability import (
        SpanKind,
        get_logger,
        record_llm_cost,
        start_span,
    )

    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    SpanKind = None
    start_span = None
    record_llm_cost = None
    get_logger = None
    record_llm_request = None
    record_llm_tokens = None
    record_llm_latency = None
    record_llm_error = None


class LiteLLMAdapter:
    """
    LiteLLM-based adapter for unified LLM access.

    Features:
    - Multi-provider support (OpenAI, Anthropic, Azure, Ollama, etc.)
    - Automatic observability (tracing, cost tracking)
    - Consistent interface across providers
    - Fallback support
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        embedding_model: str = "text-embedding-3-small",
        temperature: float = 0.0,
        max_tokens: int | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        timeout: float = 60.0,
        fallback_models: list[str] | None = None,
    ):
        """
        Initialize LiteLLM adapter.

        Args:
            model: Default model for completions (e.g., "gpt-4o-mini", "claude-3-sonnet")
            embedding_model: Model for embeddings (e.g., "text-embedding-3-small")
            temperature: Default temperature for completions
            max_tokens: Default max tokens for completions
            api_key: Optional API key (uses env vars if not provided)
            api_base: Optional API base URL
            timeout: Request timeout in seconds
            fallback_models: List of fallback models if primary fails
        """
        if not LITELLM_AVAILABLE:
            raise ImportError("LiteLLM not installed. Install with: pip install litellm")

        self.model = model
        self.embedding_model = embedding_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.api_base = api_base
        self.timeout = timeout
        self.fallback_models = fallback_models or []

        # Configure LiteLLM
        if api_key:
            litellm.api_key = api_key
        if api_base:
            litellm.api_base = api_base

        # Disable LiteLLM's own logging if we have observability
        if OBSERVABILITY_AVAILABLE:
            litellm.set_verbose = False

        logger.info(
            f"LiteLLMAdapter initialized: model={model}, "
            f"embedding_model={embedding_model}, "
            f"fallback_models={fallback_models}"
        )

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """
        Generate completion from a prompt string.

        This is the simplified interface matching the Protocol expected
        by memory system components.

        Args:
            prompt: User prompt text
            model: Optional model override
            temperature: Optional temperature override
            max_tokens: Optional max_tokens override
            system_prompt: Optional system prompt

        Returns:
            Generated text response
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        return await self.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Generate chat completion from messages.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Optional model override
            temperature: Optional temperature override
            max_tokens: Optional max_tokens override

        Returns:
            Generated text response
        """
        model = model or self.model
        temperature = temperature if temperature is not None else self.temperature
        max_tokens = max_tokens or self.max_tokens

        # Try primary model, then fallbacks
        models_to_try = [model] + self.fallback_models
        last_error = None

        for try_model in models_to_try:
            try:
                return await self._do_completion(
                    messages=messages,
                    model=try_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as e:
                last_error = e
                logger.warning(f"Model {try_model} failed: {e}, trying fallback...")
                continue

        # All models failed
        raise last_error or RuntimeError("All models failed")

    async def _do_completion(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        """Execute completion with observability."""
        start_time = time.time()

        # With observability
        if OBSERVABILITY_AVAILABLE and start_span:
            with start_span("llm_completion", kind=SpanKind.CLIENT) as span:
                span.set_attribute("llm.model", model)
                span.set_attribute("llm.temperature", temperature)
                span.set_attribute("llm.messages_count", len(messages))
                span.set_attribute("service.name", "litellm")

                try:
                    response = await acompletion(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=self.timeout,
                    )

                    # Extract response
                    content = response.choices[0].message.content or ""

                    # Track usage
                    if hasattr(response, "usage") and response.usage:
                        prompt_tokens = response.usage.prompt_tokens
                        completion_tokens = response.usage.completion_tokens

                        span.set_attribute("llm.prompt_tokens", prompt_tokens)
                        span.set_attribute("llm.completion_tokens", completion_tokens)
                        span.set_attribute("llm.total_tokens", prompt_tokens + completion_tokens)

                        # Record cost
                        if record_llm_cost:
                            cost = record_llm_cost(
                                model=model,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                operation="chat_completion",
                            )
                            span.set_attribute("llm.cost_usd", cost)

                        # Record OTEL metrics
                        if record_llm_tokens:
                            record_llm_tokens(
                                model=model,
                                input_tokens=prompt_tokens,
                                output_tokens=completion_tokens,
                                provider="litellm",
                                operation="completion",
                            )

                    latency_ms = (time.time() - start_time) * 1000
                    span.set_attribute("llm.latency_ms", latency_ms)

                    # Record metrics
                    if record_llm_request:
                        record_llm_request(
                            model=model,
                            provider="litellm",
                            operation="completion",
                            status="success",
                        )
                    if record_llm_latency:
                        record_llm_latency(
                            model=model,
                            latency_ms=latency_ms,
                            provider="litellm",
                            operation="completion",
                            status="success",
                        )

                    logger.debug(f"LLM completion: model={model}, latency={latency_ms:.0f}ms")

                    return content

                except Exception as e:
                    span.set_attribute("error", True)
                    span.set_attribute("error.message", str(e))

                    # Record error metrics
                    if record_llm_request:
                        record_llm_request(
                            model=model,
                            provider="litellm",
                            operation="completion",
                            status="error",
                        )
                    if record_llm_error:
                        record_llm_error(
                            model=model,
                            error_type=type(e).__name__,
                            provider="litellm",
                            operation="completion",
                        )

                    raise

        else:
            # Without observability
            response = await acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=self.timeout,
            )

            return response.choices[0].message.content or ""

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        """
        Generate embedding for text.

        Args:
            text: Text to embed
            model: Optional model override

        Returns:
            Embedding as list of floats
        """
        model = model or self.embedding_model

        response = await aembedding(
            model=model,
            input=[text],
            timeout=self.timeout,
        )

        return response.data[0]["embedding"]

    async def embed_batch(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            model: Optional model override

        Returns:
            List of embeddings
        """
        if not texts:
            return []

        model = model or self.embedding_model

        response = await aembedding(
            model=model,
            input=texts,
            timeout=self.timeout,
        )

        return [item["embedding"] for item in response.data]


# Convenience factory functions


def create_litellm_adapter(
    model: str = "gpt-4o-mini",
    **kwargs,
) -> LiteLLMAdapter:
    """
    Create a LiteLLM adapter.

    Args:
        model: Model name
        **kwargs: Additional arguments passed to LiteLLMAdapter

    Returns:
        LiteLLMAdapter instance
    """
    return LiteLLMAdapter(model=model, **kwargs)


def create_openai_adapter(model: str = "gpt-4o-mini", **kwargs) -> LiteLLMAdapter:
    """Create adapter configured for OpenAI."""
    return LiteLLMAdapter(
        model=model,
        embedding_model="text-embedding-3-small",
        **kwargs,
    )


def create_anthropic_adapter(model: str = "claude-3-sonnet-20240229", **kwargs) -> LiteLLMAdapter:
    """Create adapter configured for Anthropic."""
    return LiteLLMAdapter(
        model=model,
        embedding_model="text-embedding-3-small",  # Use OpenAI for embeddings
        **kwargs,
    )


def create_ollama_adapter(
    model: str = "llama3.2",
    api_base: str = "http://localhost:11434",
    **kwargs,
) -> LiteLLMAdapter:
    """Create adapter configured for local Ollama."""
    return LiteLLMAdapter(
        model=f"ollama/{model}",
        embedding_model=f"ollama/{model}",
        api_base=api_base,
        **kwargs,
    )
