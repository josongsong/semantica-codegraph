"""
Auto-instrumentation for OpenTelemetry

자동 계측 설정 및 초기화.
FastAPI, AsyncPG, HTTPX, Redis 등을 자동으로 계측합니다.
"""

from typing import Any

from src.infra.observability import get_logger

logger = get_logger(__name__)

# OTEL instrumentation 의존성 체크
try:
    from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor

    INSTRUMENTATION_AVAILABLE = True
    logger.info("opentelemetry_instrumentation_available")
except ImportError as e:
    INSTRUMENTATION_AVAILABLE = False
    logger.warning("opentelemetry_instrumentation_not_available", error=str(e))


class AutoInstrumentation:
    """
    자동 계측 관리자.

    Features:
    - FastAPI 자동 계측 (HTTP requests/responses)
    - AsyncPG 자동 계측 (DB queries)
    - HTTPX 자동 계측 (HTTP clients)
    - Redis 자동 계측 (cache operations)
    """

    def __init__(self, enable: bool = True):
        """
        Initialize auto-instrumentation.

        Args:
            enable: Enable/disable auto-instrumentation
        """
        self.enable = enable
        self._instrumented = set()

    def instrument_all(self) -> None:
        """
        모든 자동 계측 활성화.

        Instruments:
        - FastAPI (if FastAPI app is available)
        - AsyncPG (automatically instruments all asyncpg connections)
        - HTTPX (automatically instruments all httpx clients)
        - Redis (automatically instruments all redis clients)
        """
        if not self.enable:
            logger.info("auto_instrumentation_disabled")
            return

        if not INSTRUMENTATION_AVAILABLE:
            logger.warning("auto_instrumentation_packages_not_available")
            return

        logger.info("auto_instrumentation_start")

        # AsyncPG (자동 계측 - 모든 asyncpg 연결)
        self._instrument_asyncpg()

        # HTTPX (자동 계측 - 모든 httpx 클라이언트)
        self._instrument_httpx()

        # Redis (자동 계측 - 모든 redis 클라이언트)
        self._instrument_redis()

        logger.info("auto_instrumentation_complete", instrumented=list(self._instrumented))

    def instrument_fastapi(self, app: Any) -> None:
        """
        FastAPI 앱 계측.

        Args:
            app: FastAPI application instance

        Metrics collected:
        - http.server.request.duration
        - http.server.request.size
        - http.server.response.size
        - http.server.active_requests
        """
        if not self.enable or not INSTRUMENTATION_AVAILABLE:
            return

        if "fastapi" in self._instrumented:
            logger.warning("fastapi_already_instrumented")
            return

        try:
            FastAPIInstrumentor.instrument_app(app)
            self._instrumented.add("fastapi")
            logger.info("fastapi_instrumented")
        except Exception as e:
            logger.error("fastapi_instrumentation_failed", error=str(e), exc_info=True)

    def _instrument_asyncpg(self) -> None:
        """
        AsyncPG 자동 계측.

        Metrics collected:
        - db.client.connections.usage
        - db.client.connections.max
        - db.client.operation.duration

        Traces:
        - Database query spans with SQL statement
        """
        if "asyncpg" in self._instrumented:
            return

        try:
            AsyncPGInstrumentor().instrument()
            self._instrumented.add("asyncpg")
            logger.info("asyncpg_instrumented")
        except Exception as e:
            logger.error("asyncpg_instrumentation_failed", error=str(e), exc_info=True)

    def _instrument_httpx(self) -> None:
        """
        HTTPX 자동 계측.

        Metrics collected:
        - http.client.request.duration
        - http.client.request.size
        - http.client.response.size

        Traces:
        - HTTP client request spans
        """
        if "httpx" in self._instrumented:
            return

        try:
            HTTPXClientInstrumentor().instrument()
            self._instrumented.add("httpx")
            logger.info("httpx_instrumented")
        except Exception as e:
            logger.error("httpx_instrumentation_failed", error=str(e), exc_info=True)

    def _instrument_redis(self) -> None:
        """
        Redis 자동 계측.

        Metrics collected:
        - redis.client.operation.duration
        - redis.client.connections.usage

        Traces:
        - Redis command spans
        """
        if "redis" in self._instrumented:
            return

        try:
            RedisInstrumentor().instrument()
            self._instrumented.add("redis")
            logger.info("redis_instrumented")
        except Exception as e:
            logger.error("redis_instrumentation_failed", error=str(e), exc_info=True)

    def uninstrument_all(self) -> None:
        """모든 계측 해제 (테스트용)."""
        if not INSTRUMENTATION_AVAILABLE:
            return

        if "asyncpg" in self._instrumented:
            AsyncPGInstrumentor().uninstrument()
            self._instrumented.remove("asyncpg")

        if "httpx" in self._instrumented:
            HTTPXClientInstrumentor().uninstrument()
            self._instrumented.remove("httpx")

        if "redis" in self._instrumented:
            RedisInstrumentor().uninstrument()
            self._instrumented.remove("redis")

        # FastAPI는 앱별로 uninstrument 필요
        if "fastapi" in self._instrumented:
            self._instrumented.remove("fastapi")

        logger.info("auto_instrumentation_removed")


# Global auto-instrumentation instance
_auto_instrumentation: AutoInstrumentation | None = None


def setup_auto_instrumentation(enable: bool = True) -> AutoInstrumentation:
    """
    Setup auto-instrumentation (global singleton).

    Args:
        enable: Enable/disable auto-instrumentation

    Returns:
        AutoInstrumentation instance
    """
    global _auto_instrumentation

    if _auto_instrumentation is not None:
        logger.warning("auto_instrumentation_already_setup")
        return _auto_instrumentation

    _auto_instrumentation = AutoInstrumentation(enable=enable)
    _auto_instrumentation.instrument_all()
    return _auto_instrumentation


def get_auto_instrumentation() -> AutoInstrumentation | None:
    """Get global auto-instrumentation instance."""
    return _auto_instrumentation


def instrument_fastapi_app(app: Any) -> None:
    """
    FastAPI 앱 계측 (convenience function).

    Args:
        app: FastAPI application instance
    """
    if _auto_instrumentation:
        _auto_instrumentation.instrument_fastapi(app)
    else:
        logger.warning("auto_instrumentation_not_setup")
