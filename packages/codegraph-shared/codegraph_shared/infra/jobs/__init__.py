"""
범용 Job Queue 인프라.

SemanticaTask Engine 통합 준비.

Status: INTEGRATION_PENDING
- SemanticaTask Engine 프로젝트: /platform-codes/semantica-task-engine/
- Python SDK: semantica-task-engine (pip install)
- 현재: SDK import 가능, 실제 daemon 연결 미구현

Production 사용 시:
- src/contexts/analysis_indexing/infrastructure/job_orchestrator.py 사용 (production-ready)
- Redis + PostgreSQL 기반 distributed locking

향후 통합 시:
- SemanticaAdapter를 IndexingOrchestrator와 연결
- worker_endpoint를 FastAPI에 마운트
"""

from .handler import JobHandler, JobResult
from .models import Job, JobPriority, JobState

# SemanticaTask SDK 선택적 import
try:
    from .semantica_adapter import SemanticaAdapter
    from .worker_endpoint import router as worker_router
    from .worker_endpoint import set_adapter

    __all__ = [
        "JobHandler",
        "JobResult",
        "Job",
        "JobState",
        "JobPriority",
        "SemanticaAdapter",
        "worker_router",
        "set_adapter",
    ]
except ImportError:
    # semantica SDK가 설치되지 않은 경우
    __all__ = [
        "JobHandler",
        "JobResult",
        "Job",
        "JobState",
        "JobPriority",
    ]
