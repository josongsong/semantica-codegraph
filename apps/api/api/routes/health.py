"""
Health Check Endpoints (SOTA)

- /health: 기본 liveness (k8s probe용)
- /health/ready: readiness (의존성 체크)
- /health/live: liveness (프로세스 생존)
"""

import time

from fastapi import APIRouter

router = APIRouter()

# 서버 시작 시간 (uptime 계산용)
_start_time = time.time()


@router.get("/")
async def health_check():
    """
    기본 헬스 체크 (Kubernetes liveness probe).

    빠른 응답 (의존성 체크 없음).
    """
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check():
    """
    Readiness 체크 (Kubernetes readiness probe).

    모든 의존성 연결 상태 확인:
    - PostgreSQL
    - Redis (optional)
    - Qdrant (optional)
    """
    from codegraph_shared.infra.health import get_health_status

    result = await get_health_status()

    # HTTP status code: 200 if ready, 503 if not
    # (FastAPI의 status_code는 라우터에서 동적 변경 어려움, 본문에 상태 포함)
    return {
        "status": result["status"],
        "ready": result["status"] in ("healthy", "degraded"),
        "components": result["components"],
    }


@router.get("/live")
async def liveness_check():
    """
    Liveness 체크 (프로세스 생존 확인).

    uptime, 메모리 사용량 등 기본 정보.
    """
    import os

    result = {
        "status": "alive",
        "uptime_seconds": round(time.time() - _start_time, 2),
        "pid": os.getpid(),
    }

    # psutil은 optional (없으면 메모리 정보 생략)
    try:
        import psutil

        process = psutil.Process(os.getpid())
        result["memory_mb"] = round(process.memory_info().rss / 1024 / 1024, 2)
        result["cpu_percent"] = process.cpu_percent()
    except ImportError:
        result["memory_mb"] = None
        result["note"] = "psutil not installed"

    return result
