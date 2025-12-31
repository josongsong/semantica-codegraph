"""
Analysis Indexing Bounded Context

헥사고날 아키텍처 기반 인덱싱 시스템

레이어 구조:
- ports/: 포트 인터페이스 (Protocol 기반)
- domain/: 도메인 모델 (하위 호환성 레이어)
- infrastructure/: 실제 구현체 (어댑터, 오케스트레이터)
- di.py: Bounded Context 레벨 DI 컨테이너 (테스트/개발용)

실제 프로덕션 사용:
    from src.container import container
    orchestrator = container.indexing_orchestrator
"""

from .di import AnalysisIndexingContainer, analysis_indexing_container

# 하위 호환성을 위한 Legacy 모델
from .domain.models import FileIndexingResult, FileToIndex, IndexingJob

# 모델 - infrastructure/models가 단일 소스
from .infrastructure.models import (
    IndexingConfig,
    IndexingResult,
    IndexingStage,
    IndexingStatus,
)
from .infrastructure.models.job import IndexJob, JobStatus, TriggerType
from .infrastructure.models.mode import IndexingMode

__all__ = [
    # Models (infrastructure/models - 권장)
    "IndexingMode",
    "IndexingStatus",
    "IndexingStage",
    "IndexingConfig",
    "IndexingResult",
    "IndexJob",
    "JobStatus",
    "TriggerType",
    # Legacy Models (domain/models - 하위 호환)
    "FileToIndex",
    "IndexingJob",
    "FileIndexingResult",
    # DI Container
    "AnalysisIndexingContainer",
    "analysis_indexing_container",
]
