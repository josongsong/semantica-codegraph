"""Query Intent Detection."""

import re
from enum import Enum

from src.infra.observability import get_logger

logger = get_logger(__name__)


class QueryIntent(str, Enum):
    """Query intent 타입."""

    REGEX = "regex"  # 정규식 검색
    SYMBOL = "symbol"  # 심볼 검색 (클래스/함수)
    PATH = "path"  # 파일 경로 검색
    KEYWORD = "keyword"  # 키워드 검색
    NATURAL_LANGUAGE = "natural_language"  # 자연어 검색


class QueryIntentDetector:
    """Query intent 감지기.

    SOTA 규칙:
    - Regex query → Base (Zoekt)만
    - Symbol query → Delta + Graph
    - NL query → Full pipeline
    """

    @staticmethod
    def detect(query: str) -> QueryIntent:
        """Query intent 감지.

        Args:
            query: 검색 쿼리

        Returns:
            QueryIntent
        """
        # 1. 파일 경로 체크 (우선순위 높임)
        if QueryIntentDetector._is_path(query):
            return QueryIntent.PATH

        # 2. Regex 패턴 체크
        if QueryIntentDetector._is_regex(query):
            return QueryIntent.REGEX

        # 3. 심볼 패턴 체크 (CamelCase, snake_case)
        if QueryIntentDetector._is_symbol(query):
            return QueryIntent.SYMBOL

        # 4. 키워드 vs 자연어
        if QueryIntentDetector._is_natural_language(query):
            return QueryIntent.NATURAL_LANGUAGE

        # 5. 기본값: 키워드
        return QueryIntent.KEYWORD

    @staticmethod
    def _is_regex(query: str) -> bool:
        """정규식 패턴 여부.

        Args:
            query: 쿼리

        Returns:
            정규식 여부
        """
        # Regex 특수문자 포함
        regex_chars = r".*+?[]{}()^$|\\"
        return any(c in query for c in regex_chars)

    @staticmethod
    def _is_path(query: str) -> bool:
        """파일 경로 여부.

        Args:
            query: 쿼리

        Returns:
            경로 여부
        """
        # 경로 구분자 포함
        return "/" in query or "\\" in query or query.endswith(".py")

    @staticmethod
    def _is_symbol(query: str) -> bool:
        """심볼 패턴 여부.

        Args:
            query: 쿼리

        Returns:
            심볼 여부
        """
        # CamelCase 또는 snake_case 패턴
        has_camel = bool(re.search(r"[a-z][A-Z]", query))
        has_snake = "_" in query and query.replace("_", "").isalnum()

        return has_camel or has_snake

    @staticmethod
    def _is_natural_language(query: str) -> bool:
        """자연어 여부.

        Args:
            query: 쿼리

        Returns:
            자연어 여부
        """
        # 공백으로 구분된 여러 단어 + 일반 문자
        words = query.split()
        return len(words) > 2 and all(w.isalpha() for w in words)
