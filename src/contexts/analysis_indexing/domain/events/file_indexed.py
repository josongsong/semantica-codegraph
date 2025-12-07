"""
File Indexed Event

파일 인덱싱 완료 이벤트
"""

from dataclasses import dataclass

from .base import DomainEvent


@dataclass(frozen=True)
class FileIndexed(DomainEvent):
    """파일 인덱싱 완료 이벤트"""

    file_path: str = ""
    ir_nodes_count: int = 0
    graph_nodes_count: int = 0
    chunks_count: int = 0
    language: str = ""


@dataclass(frozen=True)
class FileIndexingFailed(DomainEvent):
    """파일 인덱싱 실패 이벤트"""

    file_path: str = ""
    error: str = ""
    language: str = ""
