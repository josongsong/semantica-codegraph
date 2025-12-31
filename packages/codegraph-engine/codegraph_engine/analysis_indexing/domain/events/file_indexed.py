"""File Indexed Events."""

from dataclasses import dataclass

from .base import DomainEvent


@dataclass
class FileIndexed(DomainEvent):
    """파일 인덱싱 완료 이벤트"""

    session_id: str = ""
    file_path: str = ""
    language: str = ""
    ir_nodes_count: int = 0
    graph_nodes_count: int = 0
    chunks_count: int = 0


@dataclass
class FileIndexingFailed(DomainEvent):
    """파일 인덱싱 실패 이벤트"""

    session_id: str = ""
    file_path: str = ""
    error: str = ""
