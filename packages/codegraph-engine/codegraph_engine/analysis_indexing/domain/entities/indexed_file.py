"""
Indexed File Entity

인덱싱된 파일 엔티티
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..value_objects.file_hash import FileHash
from ..value_objects.file_path import FilePath


@dataclass
class IndexedFile:
    """인덱싱된 파일 엔티티"""

    file_path: FilePath
    file_hash: FileHash
    language: str
    indexed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ir_nodes_count: int = 0
    graph_nodes_count: int = 0
    chunks_count: int = 0
    error: str | None = None

    @property
    def is_success(self) -> bool:
        """인덱싱 성공 여부"""
        return self.error is None

    def mark_failed(self, error: str) -> None:
        """인덱싱 실패 표시"""
        self.error = error
