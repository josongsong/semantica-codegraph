"""
Multi Index Domain Models

다중 인덱스 관리 도메인 모델
"""

from dataclasses import dataclass, field
from enum import Enum


class IndexType(str, Enum):
    """인덱스 타입"""

    LEXICAL = "lexical"
    VECTOR = "vector"
    SYMBOL = "symbol"
    FUZZY = "fuzzy"
    DOMAIN = "domain"


@dataclass
class UpsertRequest:
    """인덱스 업서트 요청"""

    index_type: IndexType
    repo_id: str
    data: list[dict]  # Chunk 또는 Graph 데이터


@dataclass
class UpsertResult:
    """인덱스 업서트 결과"""

    index_type: IndexType
    success: bool
    count: int
    errors: list[str] = field(default_factory=list)


@dataclass
class DeleteRequest:
    """인덱스 삭제 요청"""

    index_type: IndexType
    repo_id: str
    ids: list[str]


@dataclass
class DeleteResult:
    """인덱스 삭제 결과"""

    index_type: IndexType
    deleted_count: int
