"""
Code Embedding via Proxy (LiteLLM, Ollama)

transformers 직접 로딩 대신 API proxy 사용.
- Ollama: codebert, unixcoder 등 로컬 모델 서빙
- LiteLLM: 통합 API
"""

import hashlib
from typing import TYPE_CHECKING

import numpy as np

from codegraph_shared.infra.llm.embedding_cache import get_embedding_cache
from codegraph_shared.infra.observability import get_logger

if TYPE_CHECKING:
    from codegraph_shared.infra.llm.litellm_adapter import LiteLLMAdapter

logger = get_logger(__name__)


class CodeEmbeddingViaProxy:
    """
    Proxy를 통한 코드 임베딩.

    Ollama나 LiteLLM로 CodeBERT/UniXcoder 서빙.
    """

    def __init__(
        self,
        llm_adapter: "LiteLLMAdapter",
        model_name: str = "nomic-embed-text",  # Ollama code embedding model
        use_cache: bool = True,
    ):
        """
        Args:
            llm_adapter: LiteLLM adapter
            model_name: Embedding model 이름
                - nomic-embed-text (768-dim, code 특화)
                - mxbai-embed-large (1024-dim)
                - all-minilm (384-dim)
            use_cache: 캐시 사용 여부
        """
        self.llm_adapter = llm_adapter
        self.model_name = model_name
        self.use_cache = use_cache
        self.cache = get_embedding_cache() if use_cache else None

        # Model dimension mapping
        self.dimension_map = {
            "nomic-embed-text": 768,
            "mxbai-embed-large": 1024,
            "all-minilm": 384,
            "codebert": 768,  # Custom Ollama model
            "unixcoder": 768,  # Custom Ollama model
        }

    @property
    def dimension(self) -> int:
        """임베딩 차원."""
        return self.dimension_map.get(self.model_name, 768)

    async def encode(self, text: str) -> np.ndarray:
        """
        텍스트 임베딩.

        Args:
            text: 코드 또는 자연어

        Returns:
            임베딩 벡터
        """
        # Cache check
        if self.use_cache and self.cache:
            cache_key = self._make_cache_key(text)
            cached = await self.cache.get(cache_key)
            if cached is not None:
                return np.array(cached, dtype=np.float32)

        try:
            # LiteLLM을 통해 임베딩 생성
            embedding = await self.llm_adapter.embed(text, model=self.model_name)

            # Cache
            if self.use_cache and self.cache:
                await self.cache.set(cache_key, embedding)

            return np.array(embedding, dtype=np.float32)

        except Exception as e:
            logger.error(f"Proxy embedding failed: {e}")
            # Fallback: zero vector
            return np.zeros(self.dimension, dtype=np.float32)

    async def encode_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
    ) -> list[np.ndarray]:
        """
        배치 임베딩.

        Args:
            texts: 텍스트 리스트
            batch_size: 배치 크기

        Returns:
            임베딩 리스트
        """
        results = []

        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            try:
                # LiteLLM batch embedding
                embeddings = await self.llm_adapter.embed_batch(batch, model=self.model_name)

                for emb in embeddings:
                    results.append(np.array(emb, dtype=np.float32))

            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                # Fallback: zero vectors
                for _ in batch:
                    results.append(np.zeros(self.dimension, dtype=np.float32))

        return results

    def _make_cache_key(self, text: str) -> str:
        """캐시 키 생성."""
        hash_obj = hashlib.sha256(text.encode())
        return f"{self.model_name}:{hash_obj.hexdigest()[:16]}"


class CodeEmbeddingProvider:
    """
    Code Embedding Provider (Proxy 기반).

    EmbeddingProvider 인터페이스 구현.
    """

    def __init__(
        self,
        llm_adapter: "LiteLLMAdapter",
        model_name: str = "nomic-embed-text",
        use_cache: bool = True,
    ):
        """
        Args:
            llm_adapter: LiteLLM adapter
            model_name: Embedding model
            use_cache: 캐시 사용 여부
        """
        self.model = CodeEmbeddingViaProxy(
            llm_adapter=llm_adapter,
            model_name=model_name,
            use_cache=use_cache,
        )

    async def embed(self, text: str) -> list[float]:
        """단일 임베딩."""
        embedding = await self.model.encode(text)
        return embedding.tolist()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """배치 임베딩."""
        if not texts:
            return []

        embeddings = await self.model.encode_batch(texts)
        return [emb.tolist() for emb in embeddings]

    @property
    def dimension(self) -> int:
        """임베딩 차원."""
        return self.model.dimension


class HybridCodeEmbeddingProviderProxy:
    """
    Hybrid Code Embedding (Proxy 기반).

    - Query: 범용 모델 (OpenAI, GPT 등)
    - Code: 코드 특화 모델 (nomic-embed-text 등)
    """

    def __init__(
        self,
        query_provider,  # OpenAI, LiteLLM 등
        code_llm_adapter: "LiteLLMAdapter",
        code_model: str = "nomic-embed-text",
        use_cache: bool = True,
    ):
        """
        Args:
            query_provider: 자연어 쿼리용 provider
            code_llm_adapter: 코드용 LiteLLM adapter
            code_model: 코드 임베딩 모델
            use_cache: 캐시 사용 여부
        """
        self.query_provider = query_provider
        self.code_provider = CodeEmbeddingProvider(
            llm_adapter=code_llm_adapter,
            model_name=code_model,
            use_cache=use_cache,
        )

        logger.info(
            f"HybridCodeEmbeddingProviderProxy initialized: query={type(query_provider).__name__}, code={code_model}"
        )

    async def embed(self, text: str, is_code: bool = False) -> list[float]:
        """임베딩 생성 (자동 선택)."""
        if is_code:
            return await self.code_provider.embed(text)
        else:
            return await self.query_provider.embed(text)

    async def embed_query(self, query: str) -> list[float]:
        """쿼리 임베딩."""
        return await self.query_provider.embed(query)

    async def embed_code(self, code: str) -> list[float]:
        """코드 임베딩."""
        return await self.code_provider.embed(code)

    async def embed_batch(self, texts: list[str], is_code: bool = False) -> list[list[float]]:
        """배치 임베딩."""
        if is_code:
            return await self.code_provider.embed_batch(texts)
        else:
            return await self.query_provider.embed_batch(texts)

    async def embed_code_batch(self, codes: list[str]) -> list[list[float]]:
        """코드 배치 임베딩."""
        return await self.code_provider.embed_batch(codes)

    @property
    def dimension(self) -> int:
        """임베딩 차원 (code provider 기준)."""
        return self.code_provider.dimension


# Factory functions


def create_code_embedding_provider(
    llm_adapter: "LiteLLMAdapter",
    model_name: str = "nomic-embed-text",
    use_cache: bool = True,
) -> CodeEmbeddingProvider:
    """
    Code embedding provider 생성.

    Args:
        llm_adapter: LiteLLM adapter
        model_name: Embedding model
        use_cache: 캐시 사용 여부

    Returns:
        CodeEmbeddingProvider

    Example:
        >>> from codegraph_shared.infra.llm.litellm_adapter import LiteLLMAdapter
        >>> llm = LiteLLMAdapter()
        >>> provider = create_code_embedding_provider(llm, "nomic-embed-text")
        >>> embedding = await provider.embed("def foo(): pass")
    """
    return CodeEmbeddingProvider(
        llm_adapter=llm_adapter,
        model_name=model_name,
        use_cache=use_cache,
    )


def create_hybrid_code_provider(
    query_provider,
    code_llm_adapter: "LiteLLMAdapter",
    code_model: str = "nomic-embed-text",
    use_cache: bool = True,
) -> HybridCodeEmbeddingProviderProxy:
    """
    Hybrid code embedding provider 생성.

    Args:
        query_provider: 쿼리용 provider
        code_llm_adapter: 코드용 LiteLLM adapter
        code_model: 코드 임베딩 모델
        use_cache: 캐시 사용 여부

    Returns:
        HybridCodeEmbeddingProviderProxy

    Example:
        >>> from codegraph_shared.infra.llm.openai import OpenAIAdapter
        >>> from codegraph_shared.infra.llm.litellm_adapter import LiteLLMAdapter
        >>>
        >>> query_provider = OpenAIAdapter(api_key="...")
        >>> code_llm = LiteLLMAdapter()  # Ollama 백엔드
        >>>
        >>> hybrid = create_hybrid_code_provider(
        ...     query_provider=query_provider,
        ...     code_llm_adapter=code_llm,
        ...     code_model="nomic-embed-text"
        ... )
        >>>
        >>> # 자연어 쿼리 → OpenAI
        >>> query_emb = await hybrid.embed_query("find fibonacci function")
        >>>
        >>> # 코드 → Ollama nomic-embed-text
        >>> code_emb = await hybrid.embed_code("def fib(n): ...")
    """
    return HybridCodeEmbeddingProviderProxy(
        query_provider=query_provider,
        code_llm_adapter=code_llm_adapter,
        code_model=code_model,
        use_cache=use_cache,
    )
