"""
Analysis Indexing Domain Models

⚠️ DEPRECATED: 이 파일은 하위 호환성을 위해 유지됩니다.
실제 모델은 infrastructure/models를 사용하세요.

Usage:
    # 권장
    from codegraph_engine.analysis_indexing.infrastructure.models import (
        IndexingMode,
        IndexingStatus,
        IndexingResult,
        IndexingConfig,
    )

    # 하위 호환 (Deprecated)
    from codegraph_engine.analysis_indexing.domain.models import IndexingMode
"""

# Re-export from infrastructure/models for backward compatibility
# Legacy models for backward compatibility
# These are simplified versions - use infrastructure/models for full features
from dataclasses import dataclass
from pathlib import Path

from codegraph_engine.analysis_indexing.infrastructure.models import (
    IndexingConfig,
    IndexingResult,
    IndexingStage,
    IndexingStatus,
)
from codegraph_engine.analysis_indexing.infrastructure.models.job import (
    IndexJob,
    JobStatus,
    TriggerType,
)
from codegraph_engine.analysis_indexing.infrastructure.models.mode import IndexingMode


@dataclass
class FileToIndex:
    """인덱싱할 파일 정보 (Legacy)"""

    file_path: str
    language: str | None = None
    is_modified: bool = False
    old_content: str | None = None


@dataclass
class IndexingJob:
    """인덱싱 작업 (Legacy - use infrastructure/models/job.IndexJob instead)"""

    repo_id: str
    mode: IndexingMode
    files: list[FileToIndex]
    snapshot_id: str | None = None
    base_path: Path | None = None


@dataclass
class FileIndexingResult:
    """파일 인덱싱 결과 (Legacy)"""

    file_path: str
    success: bool
    error: str | None = None
    ir_nodes_count: int = 0
    graph_nodes_count: int = 0
    chunks_count: int = 0


__all__ = [
    # From infrastructure/models (권장)
    "IndexingMode",
    "IndexingStatus",
    "IndexingStage",
    "IndexingResult",
    "IndexingConfig",
    "IndexJob",
    "JobStatus",
    "TriggerType",
    # Legacy (Deprecated)
    "FileToIndex",
    "IndexingJob",
    "FileIndexingResult",
]
