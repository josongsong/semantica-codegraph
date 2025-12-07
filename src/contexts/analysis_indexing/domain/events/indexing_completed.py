"""
Indexing Completed Event

인덱싱 완료 이벤트
"""

from dataclasses import dataclass

from .base import DomainEvent


@dataclass(frozen=True)
class IndexingCompleted(DomainEvent):
    """인덱싱 완료 이벤트"""

    repo_id: str = ""
    snapshot_id: str = ""
    total_files: int = 0
    success_files: int = 0
    failed_files: int = 0
    mode: str = "full"


@dataclass(frozen=True)
class IndexingFailed(DomainEvent):
    """인덱싱 실패 이벤트"""

    repo_id: str = ""
    snapshot_id: str = ""
    error: str = ""
    mode: str = "full"
