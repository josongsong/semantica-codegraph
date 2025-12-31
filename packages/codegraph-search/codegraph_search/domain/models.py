"""
Retrieval Search Domain Models

검색 도메인의 핵심 모델
"""

from dataclasses import dataclass, field
from enum import Enum


class IntentType(str, Enum):
    """검색 인텐트 타입"""

    SEMANTIC = "semantic"
    LEXICAL = "lexical"
    SYMBOL = "symbol"
    HYBRID = "hybrid"


class IndexType(str, Enum):
    """인덱스 타입"""

    LEXICAL = "lexical"
    VECTOR = "vector"
    SYMBOL = "symbol"
    FUZZY = "fuzzy"
    DOMAIN = "domain"


@dataclass
class SearchQuery:
    """검색 쿼리"""

    query: str
    repo_id: str
    limit: int = 10
    offset: int = 0


@dataclass
class SearchHit:
    """검색 결과 항목"""

    id: str
    score: float
    content: str
    metadata: dict[str, str | int | float] = field(default_factory=dict)
    rank: int = 0


@dataclass
class SearchResult:
    """검색 결과"""

    query: str
    hits: list[SearchHit]
    total: int
    took_ms: float


@dataclass
class Intent:
    """검색 인텐트"""

    type: IntentType
    confidence: float
    weights: dict[IndexType, float] = field(default_factory=dict)
