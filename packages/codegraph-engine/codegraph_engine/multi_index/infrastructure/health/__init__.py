"""
Health Check for Multi-Index Services

서비스 상태 점검 모듈:

- HealthChecker: 전체 헬스체크
- ComponentHealth: 개별 컴포넌트 상태
- SystemHealth: 시스템 전체 상태

Usage:
    from codegraph_engine.multi_index.infrastructure.health import (
        HealthChecker,
        HealthStatus,
        create_health_routes,
    )

    checker = HealthChecker(
        qdrant_client=qdrant,
        postgres_store=postgres,
    )

    # K8s probes
    is_alive = await checker.is_alive()    # /health/live
    is_ready = await checker.is_ready()    # /health/ready

    # 상세 정보
    health = await checker.check_all()     # /health
"""

from codegraph_engine.multi_index.infrastructure.health.health_check import (
    ComponentHealth,
    HealthChecker,
    HealthStatus,
    SystemHealth,
    create_health_routes,
)

__all__ = [
    "ComponentHealth",
    "HealthChecker",
    "HealthStatus",
    "SystemHealth",
    "create_health_routes",
]
