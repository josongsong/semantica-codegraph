"""
Embedding Priority Rules

Chunk kind 기반 우선순위 정의.
높은 우선순위 chunk를 먼저 embedding하여 대형 레포에서도 즉각적인 검색 제공.
"""

import logging

from codegraph_engine.code_foundation.infrastructure.chunk.models import Chunk

logger = logging.getLogger(__name__)

# 우선순위 규칙 (높을수록 우선)
CHUNK_PRIORITY = {
    "function": 10,  # 가장 중요 (실행 로직)
    "usage": 9,  # 사용 예시
    "class": 8,  # 클래스 정의
    "test": 7,  # 테스트 코드
    "method": 6,  # 메서드
    "header": 5,  # 파일 헤더
    "docstring": 4,  # 문서화
    "skeleton": 3,  # 시그니처
    "module": 2,  # 모듈
    "file": 1,  # 파일
    "document": 1,  # 문서
}

# 우선순위 임계값 (export for reuse)
HIGH_PRIORITY_THRESHOLD = 8  # function, usage, class
MEDIUM_PRIORITY_THRESHOLD = 5  # test, method, header
LOW_PRIORITY_THRESHOLD = 0  # 나머지

__all__ = [
    "CHUNK_PRIORITY",
    "HIGH_PRIORITY_THRESHOLD",
    "MEDIUM_PRIORITY_THRESHOLD",
    "LOW_PRIORITY_THRESHOLD",
    "get_chunk_priority",
    "is_high_priority",
    "is_medium_priority",
    "is_low_priority",
    "partition_by_priority",
]


def get_chunk_priority(chunk: Chunk) -> int:
    """
    Chunk의 우선순위 계산.

    Args:
        chunk: Chunk 객체

    Returns:
        우선순위 (0-10, 높을수록 우선)
    """
    base_priority = CHUNK_PRIORITY.get(chunk.kind, 0)

    # 보너스 우선순위
    bonus = 0

    # PageRank 높으면 +1
    try:
        pagerank = getattr(chunk, "pagerank", None)
        if pagerank and isinstance(pagerank, int | float) and pagerank > 0.5:
            bonus += 1
    except Exception as e:
        logger.debug(f"pagerank_check_failed: {e}")

    # 테스트가 아니면서 중요도 높으면 +1
    try:
        is_test = getattr(chunk, "is_test", False)
        importance = getattr(chunk, "importance", None)
        if not is_test and importance and isinstance(importance, int | float) and importance > 0.7:
            bonus += 1
    except Exception as e:
        logger.debug(f"importance_check_failed: {e}")

    return base_priority + bonus


def is_high_priority(chunk: Chunk) -> bool:
    """우선순위 높은 chunk인지 확인 (즉시 embedding 대상)."""
    return get_chunk_priority(chunk) >= HIGH_PRIORITY_THRESHOLD


def is_medium_priority(chunk: Chunk) -> bool:
    """중간 우선순위 chunk인지 확인."""
    priority = get_chunk_priority(chunk)
    return MEDIUM_PRIORITY_THRESHOLD <= priority < HIGH_PRIORITY_THRESHOLD


def is_low_priority(chunk: Chunk) -> bool:
    """낮은 우선순위 chunk인지 확인 (나중에 처리)."""
    return get_chunk_priority(chunk) < MEDIUM_PRIORITY_THRESHOLD


def partition_by_priority(chunks: list[Chunk]) -> tuple[list[Chunk], list[Chunk], list[Chunk]]:
    """
    Chunk를 우선순위별로 분리.

    Args:
        chunks: Chunk 리스트

    Returns:
        (high_priority, medium_priority, low_priority)
    """
    high = []
    medium = []
    low = []

    for chunk in chunks:
        if is_high_priority(chunk):
            high.append(chunk)
        elif is_medium_priority(chunk):
            medium.append(chunk)
        else:
            low.append(chunk)

    return high, medium, low
