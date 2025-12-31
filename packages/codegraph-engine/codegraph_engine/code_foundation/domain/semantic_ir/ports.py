"""
Domain Ports for Semantic IR Builder (Hexagonal Architecture)

This module defines the interfaces (ports) that the domain layer uses
to interact with infrastructure concerns, maintaining clean separation.

Architecture:
    Domain (Core) → Port (Interface) ← Adapter (Infrastructure)

    Domain은 Port(interface)만 의존
    Infrastructure는 Adapter로 Port 구현
"""

from abc import ABC, abstractmethod
from typing import Protocol

from codegraph_engine.code_foundation.domain.ports.ir_port import Span


class BodyHashPort(Protocol):
    """
    Port for computing function body hashes.

    Hexagonal Architecture: Domain → Port ← Adapter (Infrastructure)

    This allows the domain logic (SemanticIrBuilder) to be independent
    of infrastructure details (SourceFile, AstTree).
    """

    def compute_hash(self, file_path: str, span: Span) -> tuple[str, str | None]:
        """
        Compute hash of function body content.

        Args:
            file_path: Path to source file
            span: Function span (start/end line/col)

        Returns:
            (hash_value, error_message)
            - hash_value: "body_sha256:XXXXXXXX" if success, None if error
            - error_message: Error description if failed, None if success

        Note:
            This is a synchronous interface. For async, use AsyncBodyHashPort.
        """
        ...

    def clear_cache(self) -> None:
        """
        Clear any internal caching.

        Called at the start of each build to prevent cache pollution.
        """
        ...


class BodyHashMetricsPort(Protocol):
    """
    Port for recording body hash computation metrics.

    Allows domain to emit metrics without coupling to specific monitoring system.
    """

    def record_computation(self, file_path: str, duration_ms: float, cache_hit: bool) -> None:
        """Record a hash computation event"""
        ...

    def record_cache_size(self, size: int) -> None:
        """Record current cache size"""
        ...

    def record_error(self, error_type: str, file_path: str) -> None:
        """Record an error event"""
        ...


# ============================================================
# Configuration Port
# ============================================================


class ConfigProvider(Protocol):
    """
    Configuration 제공 인터페이스 (Port)

    Domain 계층은 이 인터페이스만 의존.
    실제 구현(Adapter)은 Infrastructure에서 제공.

    Examples:
        # Infrastructure (Adapter)
        class EnvConfigProvider(ConfigProvider):
            def is_debug_enabled(self) -> bool:
                return os.getenv("SEMANTIC_IR_DEBUG") == "true"

        # Domain (Core)
        class SemanticIrBuilder:
            def __init__(self, config: ConfigProvider):
                self._debug = config.is_debug_enabled()
    """

    def is_debug_enabled(self) -> bool:
        """
        DEBUG 로그 활성화 여부

        Returns:
            True if debug logging is enabled
        """
        ...

    def is_parallel_enabled(self) -> bool:
        """
        병렬 처리 활성화 여부

        Returns:
            True if parallel processing is enabled
        """
        ...

    def get_max_workers(self) -> int:
        """
        병렬 처리 워커 수

        Returns:
            Maximum number of worker processes
        """
        ...


# ============================================================
# Logging Port
# ============================================================


class LogBatch:
    """
    배치 로깅을 위한 데이터 구조

    여러 로그 메시지를 모아서 한 번에 출력.
    """

    def __init__(self, category: str):
        self.category = category
        self.entries: list[dict] = []

    def add(self, message: str, **kwargs):
        """로그 엔트리 추가"""
        self.entries.append({"message": message, **kwargs})

    def is_empty(self) -> bool:
        """비어있는지 확인"""
        return len(self.entries) == 0

    def count(self) -> int:
        """엔트리 수"""
        return len(self.entries)

    def get_summary(self) -> dict:
        """요약 통계"""
        return {
            "category": self.category,
            "count": len(self.entries),
            "sample": self.entries[:3] if self.entries else [],
        }


class BatchLogger(ABC):
    """
    배치 로깅 인터페이스 (Port)

    Phase 2 최적화: 개별 로그 대신 배치로 로그 출력.

    Performance:
        Before: 22,513 logger.debug() calls
        After:  ~50 batch logs (450x reduction)
    """

    @abstractmethod
    def create_batch(self, category: str) -> LogBatch:
        """배치 생성"""
        ...

    @abstractmethod
    def flush_batch(self, batch: LogBatch) -> None:
        """배치 출력"""
        ...

    @abstractmethod
    def is_debug_enabled(self) -> bool:
        """DEBUG 활성화 여부"""
        ...
