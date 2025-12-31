"""
Infrastructure Health Check (SOTA)

Checks:
- PostgreSQL (required)
- Redis (optional)
- Qdrant (optional)

Usage:
    from codegraph_shared.infra.health import get_health_status

    result = await get_health_status()
    # {"status": "healthy", "components": {...}}
"""

import time

from codegraph_shared.infra.config.settings import Settings


async def get_health_status() -> dict:
    """
    Get complete infrastructure health status.

    Returns:
        {
            "status": "healthy" | "degraded" | "down",
            "components": {
                "postgres": {...},
                "redis": {...},
                "qdrant": {...},
            }
        }
    """
    settings = Settings()
    components = {}
    critical_down = False
    any_degraded = False

    # PostgreSQL (Critical)
    pg_result = await _check_postgres(settings)
    components["postgres"] = pg_result
    if pg_result["status"] == "down":
        critical_down = True
    elif pg_result["status"] == "degraded":
        any_degraded = True

    # Redis (Optional)
    redis_result = await _check_redis(settings)
    components["redis"] = redis_result
    if redis_result["status"] == "degraded":
        any_degraded = True
    # Redis down은 degraded (optional)

    # Qdrant (Optional)
    qdrant_result = await _check_qdrant(settings)
    components["qdrant"] = qdrant_result
    if qdrant_result["status"] == "degraded":
        any_degraded = True

    # Overall status
    if critical_down:
        overall_status = "down"
    elif any_degraded:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    return {
        "status": overall_status,
        "components": components,
    }


async def _check_postgres(settings: Settings) -> dict:
    """PostgreSQL health check."""
    start = time.perf_counter()
    try:
        from codegraph_shared.infra.storage.postgres_enhanced import EnhancedPostgresStore

        store = EnhancedPostgresStore(settings.database_url)
        is_healthy, details = await store.health_check()
        await store.close()

        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "healthy" if is_healthy else details.get("status", "down"),
            "latency_ms": round(latency_ms, 2),
            **details,
        }
    except Exception as e:
        return {"status": "down", "error": str(e)}


async def _check_redis(settings: Settings) -> dict:
    """Redis health check (optional)."""
    start = time.perf_counter()
    try:
        import redis.asyncio as redis

        redis_url = getattr(settings, "redis_url", None)
        if not redis_url:
            return {"status": "skipped", "reason": "not_configured"}

        client = redis.from_url(redis_url)
        pong = await client.ping()
        await client.close()

        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "healthy" if pong else "degraded",
            "latency_ms": round(latency_ms, 2),
        }
    except ImportError:
        return {"status": "skipped", "reason": "redis_not_installed"}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


async def _check_qdrant(settings: Settings) -> dict:
    """Qdrant health check (optional)."""
    start = time.perf_counter()
    try:
        from qdrant_client import AsyncQdrantClient

        qdrant_url = getattr(settings, "qdrant_url", None)
        if not qdrant_url:
            return {"status": "skipped", "reason": "not_configured"}

        client = AsyncQdrantClient(url=qdrant_url)
        info = await client.get_collections()
        await client.close()

        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "healthy",
            "latency_ms": round(latency_ms, 2),
            "collections": len(info.collections),
        }
    except ImportError:
        return {"status": "skipped", "reason": "qdrant_not_installed"}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}
