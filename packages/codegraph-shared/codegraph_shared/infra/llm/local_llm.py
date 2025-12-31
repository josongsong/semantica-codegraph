"""
Local LLM Adapter (OpenAI-compatible API Gateway)

Provider-agnostic adapter for local LLM providers (Ollama, vLLM, LocalAI, etc.).
Provides embeddings, chat completions, and reranking using OpenAI-compatible API endpoints.

Gateway server (port 8000) provides OpenAI-compatible endpoints (/v1/embeddings, /v1/chat/completions).

Configured models (MacBook Max optimized):
- Embedding: bge-m3:latest (Korean/multilingual, 8k context)
- Reranking: bge-reranker-large (cross-encoder for precision)
- Result LLM: qwen2.5-coder-32b (code + Korean intelligence, 70B-level reasoning)
- Intent LLM: qwen2.5-coder-7b (fast JSON classification, strategic choice for speed + format compliance)
"""

import json
import time
from typing import Any, TypedDict, Unpack
from urllib.parse import urlparse

import httpx

from codegraph_shared.common.observability import get_logger
from codegraph_shared.config import settings
from codegraph_shared.infra.llm.metrics import (
    record_llm_cost,
    record_llm_latency,
    record_llm_request,
    record_llm_tokens,
)

logger = get_logger(__name__)


# ============================================================
# Type-Safe LLM Parameters (P2 SOTA)
# ============================================================


class LLMKwargs(TypedDict, total=False):
    """
    Type-safe LLM parameters for generate() and chat().

    SOTA Feature (P2):
    - Provides IDE autocomplete for LLM parameters
    - Enables static type checking (mypy/pyright)
    - Documents available parameters

    All fields are optional (total=False).
    """

    # Prompt Caching (P2-4)
    caching: bool  # Enable Prompt Caching (OpenAI/Anthropic KV Cache)

    # Determinism
    seed: int  # Random seed for reproducibility

    # Sampling Control
    top_p: float  # Nucleus sampling (0.0-1.0)
    top_k: int  # Top-K sampling
    frequency_penalty: float  # Penalize frequent tokens (-2.0 to 2.0)
    presence_penalty: float  # Penalize present tokens (-2.0 to 2.0)

    # Response Control
    stop: list[str] | str  # Stop sequences
    logprobs: bool  # Return log probabilities
    n: int  # Number of completions to generate

    # Advanced
    user: str  # End-user ID (for abuse detection)
    response_format: dict[str, Any]  # Structured output format (JSON mode)


class LocalLLMAdapter:
    """
    Local LLM adapter using OpenAI-compatible API gateway.

    Provider-agnostic: works with Ollama, vLLM, LocalAI, or any OpenAI-compatible server.
    Uses API gateway server at http://127.0.0.1:8000 with httpx.
    Gateway provides OpenAI-compatible endpoints (/v1/embeddings, /v1/chat/completions).
    Handles SSE (Server-Sent Events) streaming responses.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        embedding_model: str = "bge-m3:latest",
        result_model: str = "qwen2.5-coder-32b",
        intent_model: str = "qwen2.5-coder-7b",
        reranker_model: str = "bge-reranker-large",
        timeout: float = 120.0,
    ) -> None:
        """
        Initialize local LLM adapter.

        Args:
            base_url: OpenAI-compatible API gateway server URL (default: http://127.0.0.1:8000)
            embedding_model: Model for embeddings (bge-m3:latest)
            result_model: Model for result generation (qwen2.5-coder-32b)
            intent_model: Model for intent analysis (qwen2.5-coder-7b)
            reranker_model: Model for reranking (bge-reranker-large)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.embedding_model = embedding_model
        self.result_model = result_model
        self.intent_model = intent_model
        self.reranker_model = reranker_model
        self.timeout = timeout
        self._warmed_up = False

        # Build native URL from settings (for providers that have separate native API)
        parsed = urlparse(base_url)
        self._native_url = f"{parsed.scheme}://{parsed.hostname}:{settings.local_llm_native_port}"

        # Use httpx for direct API calls (handles SSE better)
        self.client = httpx.AsyncClient(timeout=timeout)

        logger.info(
            f"LocalLLM adapter initialized: {base_url}, "
            f"embedding={embedding_model}, result={result_model}, "
            f"intent={intent_model}, reranker={reranker_model}"
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    async def warmup(self) -> None:
        """
        Warmup the embedding model by sending a dummy request.

        First embedding call can take 2-3 seconds for model loading.
        Subsequent calls are much faster (~100-150ms).
        Call this before starting batch embedding to avoid cold start latency.
        """
        if self._warmed_up:
            return

        logger.info(f"local_llm_warmup_starting: model={self.embedding_model}")
        try:
            # Send a dummy embedding request to load the model
            await self.embed("warmup")
            self._warmed_up = True
            logger.info(f"local_llm_warmup_completed: model={self.embedding_model}")
        except Exception as e:
            logger.warning(f"local_llm_warmup_failed: model={self.embedding_model}, error={e}")

    def _parse_sse_response(self, text: str) -> dict[str, Any]:
        """
        Parse SSE (Server-Sent Events) response.

        Server returns: "data: {...json...}\n\n"
        We need to extract the JSON part.
        """
        lines = text.strip().split("\n")
        for line in lines:
            if line.startswith("data: "):
                json_str = line[6:]  # Remove "data: " prefix
                return json.loads(json_str)
        # Fallback: try parsing as plain JSON
        return json.loads(text)

    def _messages_to_prompt(self, messages: list[dict[str, Any]]) -> str:
        """
        Convert OpenAI-style messages to Ollama prompt format.

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            Combined prompt string
        """
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
        return "\n\n".join(prompt_parts)

    # ========================================================================
    # Embedding Methods (bge-m3) - Using OpenAI-compatible API Gateway
    # ========================================================================

    async def embed(self, text: str) -> list[float]:
        """
        Generate embedding for text using OpenAI-compatible API gateway.

        Args:
            text: Text to embed

        Returns:
            Embedding as list of floats (1024 dimensions for bge-m3)
        """
        start_time = time.time()

        try:
            # Use OpenAI-compatible API: /v1/embeddings via gateway server
            response = await self.client.post(
                f"{self.base_url}/v1/embeddings",
                json={
                    "model": self.embedding_model,
                    "input": text,
                },
            )
            response.raise_for_status()
            data = response.json()

            # Record metrics (Phase 1 Day 5)
            latency_ms = (time.time() - start_time) * 1000
            record_llm_request(
                model=self.embedding_model,
                provider="local",
                operation="embedding",
                status="success",
            )
            record_llm_latency(
                model=self.embedding_model,
                latency_ms=latency_ms,
                provider="local",
                operation="embedding",
                status="success",
            )
            # Estimate tokens (rough: 1 token ≈ 4 chars)
            estimated_tokens = len(text) // 4
            record_llm_tokens(
                model=self.embedding_model,
                input_tokens=estimated_tokens,
                output_tokens=0,
                provider="local",
                operation="embedding",
            )
            # Local models have no cost
            record_llm_cost(
                model=self.embedding_model,
                cost_usd=0.0,
                provider="local",
                operation="embedding",
            )

            return data["data"][0]["embedding"]
        except Exception:
            latency_ms = (time.time() - start_time) * 1000
            record_llm_request(
                model=self.embedding_model,
                provider="local",
                operation="embedding",
                status="error",
            )
            record_llm_latency(
                model=self.embedding_model,
                latency_ms=latency_ms,
                provider="local",
                operation="embedding",
                status="error",
            )
            raise

    async def embed_batch(self, texts: list[str], concurrency: int = 32) -> list[list[float]]:
        """
        Generate embeddings for multiple texts via OpenAI-compatible API gateway.

        Uses asyncio.Semaphore for concurrent processing (default: 32 concurrent requests).

        Args:
            texts: List of texts to embed
            concurrency: Number of concurrent embedding requests (default: 32)

        Returns:
            List of embeddings in same order as input texts
        """
        import asyncio

        if not texts:
            return []

        # Warmup on first batch call to avoid cold start latency
        if not self._warmed_up:
            await self.warmup()

        semaphore = asyncio.Semaphore(concurrency)
        embeddings: list[list[float] | None] = [None] * len(texts)

        async def embed_single(index: int, text: str) -> None:
            async with semaphore:
                response = await self.client.post(
                    f"{self.base_url}/v1/embeddings",
                    json={
                        "model": self.embedding_model,
                        "input": text,
                    },
                )
                response.raise_for_status()
                data = response.json()
                embeddings[index] = data["data"][0]["embedding"]

        # Create tasks for all texts
        tasks = [embed_single(i, text) for i, text in enumerate(texts)]

        # Process with progress logging
        total = len(tasks)
        completed = 0

        async def run_with_progress():
            nonlocal completed
            for coro in asyncio.as_completed(tasks):
                await coro
                completed += 1
                if completed % 20 == 0 or completed == total:
                    logger.debug(f"Embedding progress: {completed}/{total}")

        await run_with_progress()

        # Filter out any None values (shouldn't happen but safety check)
        return [e for e in embeddings if e is not None]

    # ========================================================================
    # Chat Methods (qwen2.5-coder-32b / qwen2.5-coder-7b)
    # ========================================================================

    async def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Unpack[LLMKwargs],  # ✅ SOTA: Type-Safe kwargs (P2)
    ) -> str:
        """
        Generate chat completion using result model (qwen2.5-coder-32b).

        SOTA Feature (P2):
        - Type-safe parameters with IDE autocomplete
        - Static type checking (mypy/pyright)
        - Comprehensive parameter documentation

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Optional model override
            temperature: Sampling temperature (default: 0.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Type-safe LLM parameters (see LLMKwargs)
                - caching: Enable Prompt Caching (P2-4)
                - seed: Random seed (determinism)
                - top_p, top_k, frequency_penalty, presence_penalty: Sampling
                - stop: Stop sequences
                - response_format: JSON mode
                - etc.

        Returns:
            Generated text response

        Example:
            >>> result = await llm.chat(
            ...     messages=[{"role": "user", "content": "Hello"}],
            ...     caching=True,           # ✅ IDE autocomplete!
            ...     seed=42,                # ✅ Type-checked!
            ...     response_format={"type": "json_object"},  # ✅ Documented!
            ... )
        """
        # Use OpenAI-compatible API: /v1/chat/completions
        payload: dict[str, Any] = {
            "model": model or self.result_model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        # ✅ SOTA (P2): Type-safe 파라미터 병합
        # NOTE: OpenAI/Anthropic는 caching=True를 자동으로 처리
        # vLLM/Ollama는 지원하지 않는 파라미터를 무시 (호환성 유지)
        payload.update(kwargs)

        response = await self.client.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
        )
        response.raise_for_status()

        # Handle SSE response format or JSON
        try:
            data = response.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"] or ""
            # Fallback for SSE format
            data = self._parse_sse_response(response.text)
            return data["choices"][0]["message"]["content"] or ""
        except Exception:
            # Try parsing as SSE
            data = self._parse_sse_response(response.text)
            return data["choices"][0]["message"]["content"] or ""

    async def chat_for_intent(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 500,
    ) -> str:
        """
        Generate chat completion for intent analysis using qwen2.5-coder-7b.

        Optimized for fast JSON output.

        Args:
            messages: List of message dicts
            temperature: Sampling temperature (default: 0.0 for deterministic)
            max_tokens: Maximum tokens (default: 500 for intent JSON)

        Returns:
            Generated JSON response
        """
        # Use OpenAI-compatible API: /v1/chat/completions
        payload = {
            "model": self.intent_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        response = await self.client.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
        )
        response.raise_for_status()

        # Handle SSE response format or JSON
        try:
            data = response.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"] or ""
            # Fallback for SSE format
            data = self._parse_sse_response(response.text)
            return data["choices"][0]["message"]["content"] or ""
        except Exception:
            # Try parsing as SSE
            data = self._parse_sse_response(response.text)
            return data["choices"][0]["message"]["content"] or ""

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **kwargs: Unpack[LLMKwargs],  # ✅ SOTA: Type-Safe kwargs (P2)
    ) -> str:
        """
        Generate text from prompt (compatibility method for LLMPort).

        SOTA Feature (P2):
        - Type-safe parameters with IDE autocomplete
        - Static type checking (mypy/pyright)
        - Runtime parameter validation

        Args:
            prompt: Input prompt text
            model: Optional model override
            temperature: Sampling temperature (default: 0.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Type-safe LLM parameters (see LLMKwargs)
                - caching: Enable Prompt Caching (P2-4)
                - seed: Random seed for reproducibility
                - top_p, top_k: Sampling control
                - stop: Stop sequences
                - etc.

        Returns:
            Generated text response

        Example:
            >>> result = await llm.generate(
            ...     prompt="Hello",
            ...     caching=True,  # ✅ IDE autocomplete!
            ...     seed=42,       # ✅ Type-checked!
            ... )
        """
        return await self.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,  # ← Type-safe 전달
        )

    # ========================================================================
    # Reranking Methods (bge-reranker-large via /v1/rerank endpoint)
    # ========================================================================

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> list[tuple[int, float]]:
        """
        Rerank documents using bge-reranker-large.

        Uses the /v1/rerank endpoint if available, otherwise falls back
        to embedding-based similarity.

        Args:
            query: Search query
            documents: List of documents to rerank
            top_k: Number of top results to return (None = all)

        Returns:
            List of (index, score) tuples sorted by score descending
        """
        if not documents:
            return []

        # Try the dedicated rerank endpoint first
        try:
            response = await self.client.post(
                f"{self.base_url}/v1/rerank",
                json={
                    "model": self.reranker_model,
                    "query": query,
                    "documents": documents,
                    "top_n": top_k or len(documents),
                },
            )
            response.raise_for_status()
            data = response.json()

            # Parse rerank response
            results = []
            for item in data.get("results", []):
                idx = item.get("index", 0)
                score = item.get("relevance_score", 0.0)
                results.append((idx, score))

            # Sort by score descending
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k] if top_k else results

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (404, 422, 500):
                # Rerank endpoint not available or failed, fall back to embedding similarity
                logger.debug(f"Rerank endpoint error ({e.response.status_code}), using embedding similarity")
                return await self._rerank_via_embedding(query, documents, top_k)
            raise
        except Exception as e:
            # Any other error, fall back to embedding similarity
            logger.debug(f"Rerank failed ({e}), using embedding similarity")
            return await self._rerank_via_embedding(query, documents, top_k)

    async def _rerank_via_embedding(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> list[tuple[int, float]]:
        """
        Fallback: Rerank using embedding cosine similarity.

        Args:
            query: Search query
            documents: List of documents
            top_k: Number of top results

        Returns:
            List of (index, score) tuples
        """
        # Get query embedding
        query_emb = await self.embed(query)

        # Get document embeddings
        doc_embs = await self.embed_batch(documents)

        # Calculate cosine similarity
        def cosine_sim(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b, strict=False))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(x * x for x in b) ** 0.5
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

        scores = []
        for i, doc_emb in enumerate(doc_embs):
            score = cosine_sim(query_emb, doc_emb)
            scores.append((i, score))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k] if top_k else scores

    async def rerank_with_scores(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        content_key: str = "content",
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Rerank candidate chunks and add reranking scores.

        Args:
            query: Search query
            candidates: List of candidate dicts
            content_key: Key to extract content from candidates
            top_k: Number of results to rerank

        Returns:
            Reranked candidates with 'rerank_score' added
        """
        if not candidates:
            return []

        # Limit candidates for reranking
        candidates_to_rerank = candidates[:top_k]

        # Extract documents
        documents = [c.get(content_key, "") for c in candidates_to_rerank]

        # Get reranking scores
        reranked_indices = await self.rerank(query, documents, top_k=len(documents))

        # Create result with scores
        result = []
        for idx, score in reranked_indices:
            candidate = candidates_to_rerank[idx].copy()
            candidate["rerank_score"] = score
            result.append(candidate)

        logger.info(f"Reranked {len(candidates_to_rerank)} candidates")
        return result

    # ========================================================================
    # Health Check
    # ========================================================================

    async def healthcheck(self) -> dict[str, bool]:
        """
        Check Ollama server health and model availability.

        Returns:
            Dict with model availability status
        """
        status = {
            "server": False,
            "embedding": False,
            "result_llm": False,
            "intent_llm": False,
            "reranker": False,
        }

        try:
            # Test embedding model
            await self.embed("test")
            status["embedding"] = True
            status["server"] = True
        except Exception as e:
            logger.error(f"Embedding model health check failed: {e}")

        try:
            # Test result LLM
            await self.chat([{"role": "user", "content": "hi"}], max_tokens=5)
            status["result_llm"] = True
            status["server"] = True
        except Exception as e:
            logger.error(f"Result LLM health check failed: {e}")

        try:
            # Test intent LLM
            await self.chat_for_intent([{"role": "user", "content": "hi"}], max_tokens=5)
            status["intent_llm"] = True
        except Exception as e:
            logger.error(f"Intent LLM health check failed: {e}")

        try:
            # Test reranker
            await self.rerank("test", ["doc1", "doc2"], top_k=2)
            status["reranker"] = True
        except Exception as e:
            logger.error(f"Reranker health check failed: {e}")

        return status

    async def list_models(self) -> list[str]:
        """
        List available models on the Ollama server.

        Returns:
            List of model IDs
        """
        try:
            response = await self.client.get(f"{self.base_url}/v1/models")
            response.raise_for_status()
            data = response.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []


# ============================================================================
# Specialized Adapters (for compatibility with existing code)
# ============================================================================


class LocalEmbeddingProvider:
    """
    Embedding provider using local LLM (bge-m3).

    Implements the EmbeddingProvider protocol for SearchIndex.
    """

    def __init__(self, adapter: LocalLLMAdapter | None = None) -> None:
        """
        Initialize embedding provider.

        Args:
            adapter: Optional LocalLLMAdapter instance (creates new if None)
        """
        self.adapter = adapter or LocalLLMAdapter()

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        return await self.adapter.embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        return await self.adapter.embed_batch(texts)


class LocalReranker:
    """
    Reranker using local LLM (bge-reranker-large).

    Compatible with CrossEncoderReranker interface.
    """

    def __init__(
        self,
        adapter: LocalLLMAdapter | None = None,
        batch_size: int = 10,
    ) -> None:
        """
        Initialize reranker.

        Args:
            adapter: Optional LocalLLMAdapter instance
            batch_size: Batch size for reranking
        """
        self.adapter = adapter or LocalLLMAdapter()
        self.batch_size = batch_size

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Rerank candidates.

        Args:
            query: Search query
            candidates: Candidate chunks
            top_k: Number of results

        Returns:
            Reranked candidates with scores
        """
        return await self.adapter.rerank_with_scores(
            query=query,
            candidates=candidates,
            content_key="content",
            top_k=top_k,
        )


class LocalIntentClassifier:
    """
    Intent classifier using local LLM (qwen2.5-coder-7b).

    Fast JSON output for query intent classification.
    """

    def __init__(self, adapter: LocalLLMAdapter | None = None) -> None:
        """
        Initialize intent classifier.

        Args:
            adapter: Optional LocalLLMAdapter instance
        """
        self.adapter = adapter or LocalLLMAdapter()

    async def classify(
        self,
        query: str,
        system_prompt: str | None = None,
    ) -> str:
        """
        Classify query intent.

        Args:
            query: User query
            system_prompt: Optional system prompt for classification

        Returns:
            JSON string with intent classification
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": query})

        return await self.adapter.chat_for_intent(messages)


# ============================================================================
# Backward Compatibility Aliases
# ============================================================================

# For backward compatibility with code using old names
OllamaAdapter = LocalLLMAdapter
OllamaEmbeddingProvider = LocalEmbeddingProvider
OllamaReranker = LocalReranker
OllamaIntentClassifier = LocalIntentClassifier
