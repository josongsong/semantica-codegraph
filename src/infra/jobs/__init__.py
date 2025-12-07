"""
범용 Job Queue 인프라.

SemanticaTask Engine 통합.
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
