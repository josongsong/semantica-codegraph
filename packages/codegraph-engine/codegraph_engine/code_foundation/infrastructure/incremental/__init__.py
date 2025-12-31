"""
Incremental Update System (RFC-045)

파일 변경 감지 및 증분 IR 업데이트

컴포넌트:
- ChangeTracker: 파일 변경 추적 및 의존성 그래프
- IncrementalIRBuilder: Delta 기반 IR 빌드
- IncrementalOrchestrator: ShadowFS 이벤트 기반 조율

사용:
    from codegraph_engine.code_foundation.infrastructure.incremental import (
        ChangeTracker,
        IncrementalIRBuilder,
        IncrementalOrchestrator,
    )
"""

from codegraph_engine.code_foundation.infrastructure.incremental.change_tracker import (
    ChangeTracker,
    FileState,
)
from codegraph_engine.code_foundation.infrastructure.incremental.incremental_builder import (
    IncrementalIRBuilder,
    IncrementalResult,
)
from codegraph_engine.code_foundation.infrastructure.incremental.orchestrator import (
    IncrementalOrchestrator,
)

__all__ = [
    # Change Tracker
    "ChangeTracker",
    "FileState",
    # Builder
    "IncrementalIRBuilder",
    "IncrementalResult",
    # Orchestrator
    "IncrementalOrchestrator",
]
