"""
Analysis Indexing Domain Models

인덱싱 도메인의 핵심 모델
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class IndexingMode(str, Enum):
    """인덱싱 모드"""

    FULL = "full"
    INCREMENTAL = "incremental"
    OVERLAY = "overlay"


class IndexingStatus(str, Enum):
    """인덱싱 상태"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class FileToIndex:
    """인덱싱할 파일 정보"""

    file_path: str
    language: str | None = None
    is_modified: bool = False
    old_content: str | None = None  # 증분 인덱싱용


@dataclass
class IndexingJob:
    """인덱싱 작업"""

    repo_id: str
    mode: IndexingMode
    files: list[FileToIndex]
    snapshot_id: str | None = None
    base_path: Path | None = None


@dataclass
class FileIndexingResult:
    """파일 인덱싱 결과"""

    file_path: str
    success: bool
    error: str | None = None

    # 생성된 아티팩트 ID
    ir_nodes_count: int = 0
    graph_nodes_count: int = 0
    chunks_count: int = 0


@dataclass
class IndexingResult:
    """전체 인덱싱 결과"""

    repo_id: str
    snapshot_id: str
    mode: IndexingMode
    status: IndexingStatus

    # 통계
    total_files: int = 0
    success_files: int = 0
    failed_files: int = 0

    # 상세 결과
    file_results: list[FileIndexingResult] = field(default_factory=list)

    # 에러
    errors: list[str] = field(default_factory=list)

    # 메타데이터
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        """성공 여부"""
        return self.status == IndexingStatus.COMPLETED and self.failed_files == 0
