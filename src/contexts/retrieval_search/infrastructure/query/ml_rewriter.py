"""
Query Rewriter

자연어 쿼리를 코드 도메인 용어로 재작성.
Phase 3 Day 30-33: 룰 기반 구현
"""

from src.infra.observability import get_logger

logger = get_logger(__name__)


class QueryRewriter:
    """
    룰 기반 쿼리 재작성기.

    Features:
    - Intent 기반 템플릿
    - 코드 도메인 용어 확장
    - 다중 쿼리 변형 생성
    """

    def __init__(self):
        """Initialize query rewriter."""
        # Intent별 템플릿
        self.templates = {
            "definition": [
                "what is {term}",
                "{term} definition",
                "define {term}",
            ],
            "usage": [
                "how to use {term}",
                "{term} usage example",
                "using {term}",
            ],
            "implementation": [
                "{term} implementation",
                "how does {term} work",
                "{term} source code",
            ],
            "reference": [
                "find {term}",
                "where is {term}",
                "{term} location",
            ],
        }

        # 코드 도메인 용어 매핑
        self.domain_terms = {
            "로그인": "login authenticate",
            "인증": "authentication auth",
            "데이터베이스": "database db connection",
            "에러": "error exception",
            "설정": "configuration config settings",
            "테스트": "test unittest pytest",
        }

    async def rewrite(
        self,
        query: str,
        intent: str = "balanced",
    ) -> list[str]:
        """
        쿼리를 재작성하여 여러 변형 생성.

        Args:
            query: Original query
            intent: Query intent (definition, usage, etc.)

        Returns:
            List of rewritten queries (original + variants)
        """
        rewritten = []

        # 1. Original query
        rewritten.append(query)

        # 2. Intent 기반 재작성
        if intent in self.templates:
            for template in self.templates[intent][:2]:  # 최대 2개
                variant = template.format(term=query)
                if variant not in rewritten:
                    rewritten.append(variant)

        # 3. 도메인 용어 확장
        expanded = self._expand_domain_terms(query)
        if expanded and expanded not in rewritten:
            rewritten.append(expanded)

        # 최대 3개로 제한
        return rewritten[:3]

    def _expand_domain_terms(self, query: str) -> str | None:
        """
        한글 → 영어 코드 용어 확장.

        Args:
            query: Original query

        Returns:
            Expanded query or None
        """
        expanded = query
        has_expansion = False

        for korean, english in self.domain_terms.items():
            if korean in query:
                # 한글 용어를 영어로 확장
                expanded = expanded.replace(korean, f"{korean} {english}")
                has_expansion = True

        return expanded if has_expansion else None
