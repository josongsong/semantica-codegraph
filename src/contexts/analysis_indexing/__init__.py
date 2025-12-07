"""
Analysis Indexing Bounded Context

헥사고날 아키텍처 기반 인덱싱 시스템

레이어 구조:
- domain/: 도메인 모델과 포트 인터페이스
- usecase/: 비즈니스 로직 (포트에만 의존)
- infrastructure/: 실제 구현체 (어댑터)
- di.py: 의존성 주입 컨테이너
"""

from .di import AnalysisIndexingContainer, analysis_indexing_container
from .domain.models import (
    FileIndexingResult,
    FileToIndex,
    IndexingJob,
    IndexingMode,
    IndexingResult,
    IndexingStatus,
)

__all__ = [
    "IndexingMode",
    "IndexingStatus",
    "FileToIndex",
    "IndexingJob",
    "IndexingResult",
    "FileIndexingResult",
    "AnalysisIndexingContainer",
    "analysis_indexing_container",
]
