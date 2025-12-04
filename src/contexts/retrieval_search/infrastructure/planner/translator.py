"""Query Translator - Zoekt ↔ Tantivy 쿼리 변환."""

from src.contexts.retrieval_search.infrastructure.planner.intent import QueryIntent
from src.infra.observability import get_logger

logger = get_logger(__name__)


class QueryTranslator:
    """Query translator.

    Unified query를 Zoekt/Tantivy 형식으로 변환합니다.
    """

    @staticmethod
    def to_zoekt(query: str, intent: QueryIntent, repo_id: str) -> str:
        """Zoekt 쿼리 형식으로 변환.

        Args:
            query: 원본 쿼리
            intent: Query intent
            repo_id: 저장소 ID

        Returns:
            Zoekt 쿼리
        """
        parts = [f"repo:{repo_id}"]

        if intent == QueryIntent.REGEX:
            # Zoekt regex는 그대로
            parts.append(query)
        elif intent == QueryIntent.SYMBOL:
            # sym: prefix
            parts.append(f"sym:{query}")
        elif intent == QueryIntent.PATH:
            # f: prefix
            parts.append(f"f:{query}")
        else:
            # 일반 텍스트
            parts.append(query)

        zoekt_query = " ".join(parts)
        logger.debug(f"Zoekt query: {zoekt_query}")
        return zoekt_query

    @staticmethod
    def to_tantivy(query: str, intent: QueryIntent, repo_id: str) -> str:
        """Tantivy 쿼리 형식으로 변환.

        Args:
            query: 원본 쿼리
            intent: Query intent
            repo_id: 저장소 ID

        Returns:
            Tantivy 쿼리 (Lucene syntax)
        """
        # Tantivy는 Lucene query syntax 사용
        parts = [f"repo_id:{repo_id}"]

        if intent == QueryIntent.REGEX:
            # Tantivy는 regex 제한적 → ngram fallback
            # 간단한 변환만
            parts.append(f"content:{query}")
        elif intent == QueryIntent.SYMBOL or intent == QueryIntent.KEYWORD:
            # content 필드 검색
            parts.append(f"content:{query}")
        elif intent == QueryIntent.PATH:
            # file_path 필드
            parts.append(f"file_path:{query}")
        else:
            # 자연어 검색
            parts.append(f"content:{query}")

        tantivy_query = " AND ".join(parts)
        logger.debug(f"Tantivy query: {tantivy_query}")
        return tantivy_query
