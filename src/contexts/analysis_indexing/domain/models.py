"""
Analysis Indexing Domain Models

인덱싱 도메인의 핵심 모델
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class IndexingMode(str, Enum):
    """인덱싱 모드"""

    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"
    BOOTSTRAP = "bootstrap"
    REPAIR = "repair"


class IndexingStatus(str, Enum):
    """인덱싱 상태"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class IndexingMetadata:
    """인덱싱 메타데이터"""

    repo_id: str
    snapshot_id: str
    mode: IndexingMode
    status: IndexingStatus
    files_processed: int
    files_failed: int
    graph_nodes_created: int
    graph_edges_created: int
    chunks_created: int
    started_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None


@dataclass
class IndexingResult:
    """인덱싱 결과"""

    repo_id: str
    snapshot_id: str
    status: IndexingStatus
    files_processed: int
    files_failed: int
    graph_nodes_created: int
    graph_edges_created: int
    chunks_created: int
    total_duration_seconds: float
    errors: list[str] = field(default_factory=list)


@dataclass
class FileHash:
    """파일 해시"""

    repo_id: str
    file_path: str
    content_hash: str
    indexed_at: datetime
