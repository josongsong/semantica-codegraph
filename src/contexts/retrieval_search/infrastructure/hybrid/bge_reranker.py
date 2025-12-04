"""
BGE Reranker

LocalLLM의 bge-reranker-large 활용.
Phase 3 Day 29
"""

from src.infra.observability import get_logger

logger = get_logger(__name__)


class BGEReranker:
    """
    BGE reranker를 사용한 재순위 매기기.

    LocalLLM의 bge-reranker-large 모델 활용.
    """

    def __init__(self, local_llm):
        """
        Initialize BGE reranker.

        Args:
            local_llm: LocalLLMAdapter instance
        """
        self.llm = local_llm

    async def rerank(
        self,
        query: str,
        docs: list[str],
        top_k: int = 20,
    ) -> list[tuple[int, float]]:
        """
        Rerank documents using BGE reranker.

        Args:
            query: Query text
            docs: List of document texts
            top_k: Number of top results

        Returns:
            List of (index, score) tuples sorted by score descending
        """
        if not docs:
            return []

        try:
            # Use LocalLLM's rerank method (bge-reranker-large)
            results = await self.llm.rerank(query, docs, top_k)

            logger.debug(
                "bge_reranker_completed",
                query_len=len(query),
                docs_count=len(docs),
                results_count=len(results),
            )

            return results

        except Exception as e:
            logger.warning(
                "bge_reranker_failed",
                error=str(e),
                docs_count=len(docs),
            )
            # Fallback: return original order with decreasing scores
            return [(i, 1.0 - i * 0.01) for i in range(min(top_k, len(docs)))]
