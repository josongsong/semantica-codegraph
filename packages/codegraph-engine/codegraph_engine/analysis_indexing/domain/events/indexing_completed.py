"""Indexing Completed Events."""

from dataclasses import dataclass

from .base import DomainEvent


@dataclass
class IndexingCompleted(DomainEvent):
    """인덱싱 완료 이벤트"""

    session_id: str = ""
    repo_id: str = ""
    snapshot_id: str = ""
    total_files: int = 0
    success_files: int = 0
    failed_files: int = 0


@dataclass
class IndexingFailed(DomainEvent):
    """인덱싱 실패 이벤트"""

    session_id: str = ""
    repo_id: str = ""
    error: str = ""
