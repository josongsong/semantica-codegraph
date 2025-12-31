"""
Health Check Adapter

시스템 컴포넌트 헬스 체크 구현
"""

import asyncio
from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_shared.ports import IHealthChecker

logger = get_logger(__name__)


class HealthCheckAdapter(IHealthChecker):
    """
    Health Check Adapter.

    PostgreSQL, Redis, Qdrant, Memgraph, LLM API 등 헬스 체크.
    """

    def __init__(
        self,
        postgres_client: Any | None = None,
        redis_client: Any | None = None,
        qdrant_client: Any | None = None,
        memgraph_client: Any | None = None,
        llm_provider: Any | None = None,
    ):
        """
        Initialize health checker.

        Args:
            postgres_client: PostgreSQL 클라이언트
            redis_client: Redis 클라이언트
            qdrant_client: Qdrant 클라이언트
            memgraph_client: Memgraph 클라이언트
            llm_provider: LLM Provider
        """
        self._postgres = postgres_client
        self._redis = redis_client
        self._qdrant = qdrant_client
        self._memgraph = memgraph_client
        self._llm = llm_provider

    async def check_health(self) -> dict[str, bool]:
        """
        전체 시스템 헬스 체크.

        Returns:
            {"postgres": True, "redis": True, ...}
        """
        results = {}

        # 병렬 체크
        tasks = []
        components = []

        if self._postgres:
            tasks.append(self._check_postgres())
            components.append("postgres")

        if self._redis:
            tasks.append(self._check_redis())
            components.append("redis")

        if self._qdrant:
            tasks.append(self._check_qdrant())
            components.append("qdrant")

        if self._memgraph:
            tasks.append(self._check_memgraph())
            components.append("memgraph")

        if self._llm:
            tasks.append(self._check_llm())
            components.append("llm_api")

        if tasks:
            health_results = await asyncio.gather(*tasks, return_exceptions=True)

            for component, result in zip(components, health_results, strict=False):
                if isinstance(result, Exception):
                    logger.error(f"Health check failed for {component}: {result}")
                    results[component] = False
                else:
                    results[component] = result
        else:
            logger.warning("No components configured for health check")

        return results

    async def check_component(self, component: str) -> bool:
        """
        특정 컴포넌트 헬스 체크.

        Args:
            component: "postgres" | "redis" | "qdrant" | "memgraph" | "llm_api"

        Returns:
            True if healthy
        """
        try:
            if component == "postgres" and self._postgres:
                return await self._check_postgres()
            elif component == "redis" and self._redis:
                return await self._check_redis()
            elif component == "qdrant" and self._qdrant:
                return await self._check_qdrant()
            elif component == "memgraph" and self._memgraph:
                return await self._check_memgraph()
            elif component == "llm_api" and self._llm:
                return await self._check_llm()
            else:
                logger.warning(f"Component not configured: {component}")
                return False
        except Exception as e:
            logger.error(f"Health check failed for {component}: {e}")
            return False

    async def _check_postgres(self) -> bool:
        """PostgreSQL 헬스 체크"""
        try:
            if hasattr(self._postgres, "health_check"):
                return await self._postgres.health_check()
            elif hasattr(self._postgres, "execute"):
                # Simple query
                await self._postgres.execute("SELECT 1")
                return True
            else:
                logger.warning("PostgreSQL client has no health check method")
                return False
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            return False

    async def _check_redis(self) -> bool:
        """Redis 헬스 체크"""
        try:
            if hasattr(self._redis, "health_check"):
                return await self._redis.health_check()
            elif hasattr(self._redis, "ping"):
                await self._redis.ping()
                return True
            else:
                logger.warning("Redis client has no health check method")
                return False
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False

    async def _check_qdrant(self) -> bool:
        """Qdrant 헬스 체크"""
        try:
            if hasattr(self._qdrant, "health_check"):
                return await self._qdrant.health_check()
            elif hasattr(self._qdrant, "get_collections"):
                # List collections
                await self._qdrant.get_collections()
                return True
            else:
                logger.warning("Qdrant client has no health check method")
                return False
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False

    async def _check_memgraph(self) -> bool:
        """Memgraph 헬스 체크"""
        try:
            if hasattr(self._memgraph, "health_check"):
                return await self._memgraph.health_check()
            elif hasattr(self._memgraph, "execute"):
                # Simple query
                await self._memgraph.execute("RETURN 1")
                return True
            else:
                logger.warning("Memgraph client has no health check method")
                return False
        except Exception as e:
            logger.error(f"Memgraph health check failed: {e}")
            return False

    async def _check_llm(self) -> bool:
        """LLM API 헬스 체크"""
        try:
            if hasattr(self._llm, "health_check"):
                return await self._llm.health_check()
            else:
                # LLM은 실제 호출 없이 True (비용)
                logger.debug("LLM API health check skipped (no dedicated endpoint)")
                return True
        except Exception as e:
            logger.error(f"LLM health check failed: {e}")
            return False
