"""
Health Check for Multi-Index Services

인덱스 서비스 상태 점검:

- 개별 인덱스 건강 상태
- 연결 상태 (Qdrant, PostgreSQL)
- Circuit Breaker 상태
- 전체 시스템 상태
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class HealthStatus(Enum):
    """서비스 건강 상태"""

    HEALTHY = "healthy"  # 정상
    DEGRADED = "degraded"  # 일부 기능 저하
    UNHEALTHY = "unhealthy"  # 비정상
    UNKNOWN = "unknown"  # 확인 불가


@dataclass
class ComponentHealth:
    """개별 컴포넌트 건강 상태"""

    name: str
    status: HealthStatus
    latency_ms: float | None = None
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SystemHealth:
    """전체 시스템 건강 상태"""

    status: HealthStatus
    components: list[ComponentHealth]
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: str | None = None

    @property
    def is_healthy(self) -> bool:
        """시스템이 정상인지"""
        return self.status == HealthStatus.HEALTHY

    @property
    def healthy_count(self) -> int:
        """정상 컴포넌트 수"""
        return sum(1 for c in self.components if c.status == HealthStatus.HEALTHY)

    @property
    def unhealthy_count(self) -> int:
        """비정상 컴포넌트 수"""
        return sum(1 for c in self.components if c.status == HealthStatus.UNHEALTHY)

    def to_dict(self) -> dict[str, Any]:
        """JSON 직렬화용 딕셔너리"""
        return {
            "status": self.status.value,
            "checked_at": self.checked_at.isoformat(),
            "version": self.version,
            "summary": {
                "total": len(self.components),
                "healthy": self.healthy_count,
                "unhealthy": self.unhealthy_count,
            },
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "latency_ms": c.latency_ms,
                    "message": c.message,
                    "details": c.details,
                }
                for c in self.components
            ],
        }


class HealthChecker:
    """
    Multi-Index 서비스 건강 점검기.

    Usage:
        checker = HealthChecker(
            qdrant_client=qdrant,
            postgres_store=postgres,
            index_registry=registry,
            circuit_breaker_registry=cb_registry,
        )

        # 전체 점검
        health = await checker.check_all()

        # 간단한 liveness probe
        is_live = await checker.is_alive()

        # readiness probe
        is_ready = await checker.is_ready()
    """

    def __init__(
        self,
        qdrant_client: Any | None = None,
        postgres_store: Any | None = None,
        index_registry: Any | None = None,
        circuit_breaker_registry: Any | None = None,
        version: str | None = None,
        timeout_seconds: float = 5.0,
    ):
        """
        Args:
            qdrant_client: Qdrant 클라이언트
            postgres_store: PostgreSQL 스토어
            index_registry: 인덱스 레지스트리
            circuit_breaker_registry: Circuit Breaker 레지스트리
            version: 애플리케이션 버전
            timeout_seconds: 헬스체크 타임아웃
        """
        self._qdrant = qdrant_client
        self._postgres = postgres_store
        self._index_registry = index_registry
        self._cb_registry = circuit_breaker_registry
        self._version = version
        self._timeout = timeout_seconds

    async def check_all(self) -> SystemHealth:
        """
        모든 컴포넌트 건강 점검.

        Returns:
            SystemHealth 리포트
        """
        components: list[ComponentHealth] = []

        # 병렬 점검
        checks = []

        if self._qdrant:
            checks.append(self._check_qdrant())
        if self._postgres:
            checks.append(self._check_postgres())
        if self._index_registry:
            checks.append(self._check_indexes())
        if self._cb_registry:
            checks.append(self._check_circuit_breakers())

        if checks:
            results = await asyncio.gather(*checks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    components.append(
                        ComponentHealth(
                            name="unknown",
                            status=HealthStatus.UNHEALTHY,
                            message=str(result),
                        )
                    )
                elif isinstance(result, list):
                    components.extend(result)
                else:
                    components.append(result)

        # 전체 상태 결정
        system_status = self._determine_system_status(components)

        return SystemHealth(
            status=system_status,
            components=components,
            version=self._version,
        )

    async def is_alive(self) -> bool:
        """
        Liveness probe.

        프로세스가 살아있는지만 확인 (빠른 응답).
        """
        return True  # 이 함수가 호출되면 프로세스는 살아있음

    async def is_ready(self) -> bool:
        """
        Readiness probe.

        트래픽을 받을 준비가 되었는지 확인.
        """
        try:
            health = await asyncio.wait_for(
                self.check_all(),
                timeout=self._timeout,
            )
            return health.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)
        except asyncio.TimeoutError:
            logger.warning("health_check_timeout")
            return False
        except Exception as e:
            logger.error("health_check_failed", error=str(e))
            return False

    async def _check_qdrant(self) -> ComponentHealth:
        """Qdrant 연결 점검"""
        import time

        start = time.monotonic()

        try:
            # 간단한 API 호출로 연결 확인
            if hasattr(self._qdrant, "get_collections"):
                collections = await asyncio.wait_for(
                    self._qdrant.get_collections(),
                    timeout=self._timeout,
                )
                latency = (time.monotonic() - start) * 1000

                return ComponentHealth(
                    name="qdrant",
                    status=HealthStatus.HEALTHY,
                    latency_ms=latency,
                    message="Connected",
                    details={"collections_count": len(collections.collections)},
                )
            else:
                return ComponentHealth(
                    name="qdrant",
                    status=HealthStatus.UNKNOWN,
                    message="Client does not support get_collections",
                )

        except asyncio.TimeoutError:
            return ComponentHealth(
                name="qdrant",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.monotonic() - start) * 1000,
                message="Connection timeout",
            )
        except Exception as e:
            return ComponentHealth(
                name="qdrant",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.monotonic() - start) * 1000,
                message=f"Connection failed: {e}",
            )

    async def _check_postgres(self) -> ComponentHealth:
        """PostgreSQL 연결 점검"""
        import time

        start = time.monotonic()

        try:
            # Pool 확인 및 간단한 쿼리
            if hasattr(self._postgres, "pool") and self._postgres.pool:
                async with self._postgres.pool.acquire() as conn:
                    await asyncio.wait_for(
                        conn.fetchval("SELECT 1"),
                        timeout=self._timeout,
                    )
                    latency = (time.monotonic() - start) * 1000

                    # Pool 상태
                    pool = self._postgres.pool
                    pool_info = {
                        "size": pool.get_size() if hasattr(pool, "get_size") else None,
                        "free_size": pool.get_idle_size() if hasattr(pool, "get_idle_size") else None,
                    }

                    return ComponentHealth(
                        name="postgres",
                        status=HealthStatus.HEALTHY,
                        latency_ms=latency,
                        message="Connected",
                        details={"pool": pool_info},
                    )
            else:
                return ComponentHealth(
                    name="postgres",
                    status=HealthStatus.UNHEALTHY,
                    message="Pool not initialized",
                )

        except asyncio.TimeoutError:
            return ComponentHealth(
                name="postgres",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.monotonic() - start) * 1000,
                message="Connection timeout",
            )
        except Exception as e:
            return ComponentHealth(
                name="postgres",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.monotonic() - start) * 1000,
                message=f"Connection failed: {e}",
            )

    async def _check_indexes(self) -> list[ComponentHealth]:
        """인덱스 레지스트리 점검"""
        components: list[ComponentHealth] = []

        entries = self._index_registry.get_all()

        for entry in entries:
            status = HealthStatus.HEALTHY
            message = "Registered"
            details: dict[str, Any] = {
                "weight": entry.weight,
                "phase": entry.phase,
                "enabled": entry.enabled,
            }

            if not entry.enabled:
                status = HealthStatus.DEGRADED
                message = "Disabled"

            components.append(
                ComponentHealth(
                    name=f"index:{entry.name}",
                    status=status,
                    message=message,
                    details=details,
                )
            )

        return components

    async def _check_circuit_breakers(self) -> list[ComponentHealth]:
        """Circuit Breaker 상태 점검"""
        from codegraph_engine.multi_index.infrastructure.resilience.circuit_breaker import (
            CircuitState,
        )

        components: list[ComponentHealth] = []

        stats = await self._cb_registry.get_all_stats()

        for service_name, service_stats in stats.items():
            state = service_stats.get("state", "unknown")

            if state == CircuitState.CLOSED.value:
                status = HealthStatus.HEALTHY
            elif state == CircuitState.HALF_OPEN.value:
                status = HealthStatus.DEGRADED
            elif state == CircuitState.OPEN.value:
                status = HealthStatus.UNHEALTHY
            else:
                status = HealthStatus.UNKNOWN

            components.append(
                ComponentHealth(
                    name=f"circuit_breaker:{service_name}",
                    status=status,
                    message=f"State: {state}",
                    details=service_stats,
                )
            )

        return components

    def _determine_system_status(self, components: list[ComponentHealth]) -> HealthStatus:
        """컴포넌트 상태로 전체 시스템 상태 결정"""
        if not components:
            return HealthStatus.UNKNOWN

        statuses = [c.status for c in components]

        # 모두 정상
        if all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY

        # 하나라도 비정상
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            # 핵심 서비스 체크 (qdrant, postgres)
            critical_unhealthy = any(
                c.status == HealthStatus.UNHEALTHY for c in components if c.name in ("qdrant", "postgres")
            )
            if critical_unhealthy:
                return HealthStatus.UNHEALTHY

            return HealthStatus.DEGRADED

        # 일부 저하
        if any(s == HealthStatus.DEGRADED for s in statuses):
            return HealthStatus.DEGRADED

        return HealthStatus.UNKNOWN


# FastAPI/Starlette 통합을 위한 팩토리
def create_health_routes(checker: HealthChecker) -> dict[str, Any]:
    """
    FastAPI/Starlette 라우트 생성.

    Usage:
        from fastapi import FastAPI
        app = FastAPI()

        checker = HealthChecker(...)
        routes = create_health_routes(checker)

        @app.get("/health")
        async def health():
            return await routes["health"]()

        @app.get("/health/live")
        async def liveness():
            return await routes["live"]()

        @app.get("/health/ready")
        async def readiness():
            return await routes["ready"]()
    """

    async def health_endpoint() -> dict[str, Any]:
        health = await checker.check_all()
        return health.to_dict()

    async def liveness_endpoint() -> dict[str, Any]:
        is_alive = await checker.is_alive()
        return {"status": "alive" if is_alive else "dead"}

    async def readiness_endpoint() -> dict[str, Any]:
        is_ready = await checker.is_ready()
        return {"status": "ready" if is_ready else "not_ready"}

    return {
        "health": health_endpoint,
        "live": liveness_endpoint,
        "ready": readiness_endpoint,
    }
