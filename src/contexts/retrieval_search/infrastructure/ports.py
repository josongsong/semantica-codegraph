"""
Retriever Layer Ports

리트리버 레이어 컴포넌트들의 인터페이스 정의.
"""

from typing import Any, Protocol


class RerankerPort(Protocol):
    """경량 리랭커 인터페이스"""

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        후보 청크들을 재정렬.

        Args:
            query: 사용자 쿼리
            candidates: 후보 청크 리스트
            top_k: 반환할 상위 K개

        Returns:
            재정렬된 청크 리스트
        """
        ...


class InterleaverPort(Protocol):
    """멀티 전략 인터리빙 인터페이스"""

    def interleave(
        self,
        strategy_results: list[Any],  # list[StrategyResult]
        top_k: int = 50,
    ) -> list[dict[str, Any]]:
        """
        여러 검색 전략의 결과를 인터리빙.

        Args:
            strategy_results: 전략별 검색 결과 리스트
            top_k: 반환할 상위 K개

        Returns:
            인터리빙된 검색 결과
        """
        ...


class TopKSelectorPort(Protocol):
    """적응형 Top-K 선택 인터페이스"""

    def select_initial_k(
        self,
        query: str,
        intent: str | None = None,
    ) -> int:
        """
        쿼리와 의도에 따라 적응형 Top-K 선택.

        Args:
            query: 사용자 쿼리
            intent: 쿼리 의도 (선택적)

        Returns:
            선택된 Top-K 값
        """
        ...


class DependencyOrdererPort(Protocol):
    """의존성 기반 정렬 인터페이스"""

    def order_chunks(
        self,
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        청크들을 의존성 순서로 정렬.

        Args:
            chunks: 정렬할 청크 리스트

        Returns:
            의존성 순서로 정렬된 청크 리스트
        """
        ...


class QueryExpanderPort(Protocol):
    """쿼리 확장 인터페이스"""

    def expand(
        self,
        query: str,
        max_expansions: int = 10,
        similarity_threshold: float = 0.6,
        frequency_min: int = 2,
    ) -> dict[str, Any]:
        """
        쿼리를 확장하여 여러 변형 생성.

        Args:
            query: 원본 쿼리
            max_expansions: 최대 확장 용어 수
            similarity_threshold: 의미 유사도 임계값
            frequency_min: 최소 빈도수

        Returns:
            확장 결과 (용어와 점수)
        """
        ...


class CrossEncoderRerankerPort(Protocol):
    """Cross-encoder 최종 리랭커 인터페이스"""

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Cross-encoder를 사용한 최종 리랭킹.

        Args:
            query: 사용자 쿼리
            candidates: 후보 청크 리스트
            top_k: 반환할 상위 K개

        Returns:
            재정렬된 청크 리스트
        """
        ...
