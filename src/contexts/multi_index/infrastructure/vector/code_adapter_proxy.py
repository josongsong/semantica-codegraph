"""
Code-aware Vector Adapter (Proxy 기반)

Ollama/LiteLLM을 사용한 code embedding.
transformers 직접 로딩보다 빠르고 유연함.
"""

from typing import TYPE_CHECKING

from src.contexts.multi_index.infrastructure.vector.adapter_qdrant import QdrantVectorIndex
from src.infra.llm.code_embedding_proxy import (
    create_code_embedding_provider,
    create_hybrid_code_provider,
)
from src.infra.observability import get_logger

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient

    from src.infra.llm.litellm_adapter import LiteLLMAdapter

logger = get_logger(__name__)


def create_code_vector_adapter(
    client: "AsyncQdrantClient",
    code_llm_adapter: "LiteLLMAdapter",
    code_model: str = "nomic-embed-text",
    collection_name: str = "chunks",
    use_cache: bool = True,
    upsert_concurrency: int = 4,
) -> QdrantVectorIndex:
    """
    Code embedding vector adapter 생성 (Proxy 기반).

    Args:
        client: Qdrant async client
        code_llm_adapter: 코드 임베딩용 LiteLLM adapter (Ollama 백엔드)
        code_model: Ollama 모델 이름
            - "nomic-embed-text" (768-dim, 추천)
            - "mxbai-embed-large" (1024-dim)
            - "all-minilm" (384-dim)
        collection_name: Qdrant collection
        use_cache: 캐시 사용 여부
        upsert_concurrency: 병렬 upsert 수

    Returns:
        QdrantVectorIndex with code embedding

    Example:
        >>> from qdrant_client import AsyncQdrantClient
        >>> from src.infra.llm.litellm_adapter import LiteLLMAdapter
        >>>
        >>> qdrant = AsyncQdrantClient(url="http://localhost:6333")
        >>> llm = LiteLLMAdapter()  # Ollama 백엔드
        >>>
        >>> adapter = create_code_vector_adapter(
        ...     client=qdrant,
        ...     code_llm_adapter=llm,
        ...     code_model="nomic-embed-text"
        ... )
    """
    provider = create_code_embedding_provider(
        llm_adapter=code_llm_adapter,
        model_name=code_model,
        use_cache=use_cache,
    )

    dimension = provider.dimension

    logger.info(f"Creating code vector adapter: model={code_model}, dimension={dimension}, cache={use_cache}")

    return QdrantVectorIndex(
        client=client,
        embedding_provider=provider,
        collection_prefix=collection_name,
        vector_size=dimension,
        upsert_concurrency=upsert_concurrency,
    )


def create_hybrid_vector_adapter(
    client: "AsyncQdrantClient",
    query_provider,  # OpenAI, LiteLLM 등
    code_llm_adapter: "LiteLLMAdapter",
    code_model: str = "nomic-embed-text",
    collection_name: str = "chunks",
    use_cache: bool = True,
    upsert_concurrency: int = 4,
) -> QdrantVectorIndex:
    """
    Hybrid vector adapter 생성 (Query: 범용, Code: Proxy).

    Args:
        client: Qdrant async client
        query_provider: 쿼리용 embedding provider (OpenAI 등)
        code_llm_adapter: 코드용 LiteLLM adapter
        code_model: 코드 임베딩 모델
        collection_name: Qdrant collection
        use_cache: 캐시 사용 여부
        upsert_concurrency: 병렬 upsert 수

    Returns:
        QdrantVectorIndex with hybrid embedding

    Example:
        >>> from src.infra.llm.openai import OpenAIAdapter
        >>> from src.infra.llm.litellm_adapter import LiteLLMAdapter
        >>>
        >>> # Query: OpenAI (자연어 특화)
        >>> query_provider = OpenAIAdapter(api_key="...")
        >>>
        >>> # Code: Ollama (코드 특화, 무료)
        >>> code_llm = LiteLLMAdapter()
        >>>
        >>> adapter = create_hybrid_vector_adapter(
        ...     client=qdrant,
        ...     query_provider=query_provider,
        ...     code_llm_adapter=code_llm,
        ...     code_model="nomic-embed-text"
        ... )
    """
    hybrid_provider = create_hybrid_code_provider(
        query_provider=query_provider,
        code_llm_adapter=code_llm_adapter,
        code_model=code_model,
        use_cache=use_cache,
    )

    dimension = hybrid_provider.dimension

    logger.info(
        f"Creating hybrid vector adapter: "
        f"query={type(query_provider).__name__}, code={code_model}, "
        f"dimension={dimension}"
    )

    return QdrantVectorIndex(
        client=client,
        embedding_provider=hybrid_provider,
        collection_prefix=collection_name,
        vector_size=dimension,
        upsert_concurrency=upsert_concurrency,
    )
