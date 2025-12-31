"""
Semantic IR Adapters (Hexagonal Architecture)

Infrastructure 계층: Port 인터페이스의 실제 구현.

Architecture:
    Domain (Core) → Port (Interface) ← Adapter (Infrastructure)
"""

import logging
import os

from codegraph_engine.code_foundation.domain.semantic_ir.ports import (
    BatchLogger,
    ConfigProvider,
    LogBatch,
)

# ============================================================
# Configuration Adapter
# ============================================================


class EnvConfigProvider(ConfigProvider):
    """
    환경변수 기반 Configuration Adapter

    Infrastructure 계층에서 환경변수를 읽어 Domain에 제공.

    Examples:
        >>> config = EnvConfigProvider()
        >>> config.is_debug_enabled()
        False  # if SEMANTIC_IR_DEBUG=false
    """

    def __init__(self):
        # 초기화 시 환경변수 읽기 (한 번만)
        self._debug_enabled = os.getenv("SEMANTIC_IR_DEBUG", "false").lower() == "true"
        self._parallel_enabled = os.getenv("SEMANTIC_IR_PARALLEL", "false").lower() == "true"
        self._max_workers = int(os.getenv("SEMANTIC_IR_MAX_WORKERS", str(max(1, os.cpu_count() or 1))))

    def is_debug_enabled(self) -> bool:
        """DEBUG 로그 활성화 여부"""
        return self._debug_enabled

    def is_parallel_enabled(self) -> bool:
        """병렬 처리 활성화 여부"""
        return self._parallel_enabled

    def get_max_workers(self) -> int:
        """병렬 처리 워커 수"""
        return self._max_workers


# ============================================================
# Logging Adapter
# ============================================================


class StructlogBatchLogger(BatchLogger):
    """
    Structlog 기반 배치 로거 Adapter

    Phase 2 최적화: 개별 로그를 배치로 모아서 출력.

    Performance:
        Before: 22,513 individual logs
        After:  ~50 batch logs (450x reduction)

    Examples:
        >>> logger = StructlogBatchLogger(config)
        >>> batch = logger.create_batch("bfg_blocks")
        >>> batch.add("block_created", block_id="block:1")
        >>> batch.add("block_created", block_id="block:2")
        >>> logger.flush_batch(batch)  # Single log output
    """

    def __init__(
        self,
        config: ConfigProvider,
        logger: logging.Logger | None = None,
    ):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self._debug_enabled = config.is_debug_enabled() and self.logger.isEnabledFor(logging.DEBUG)

    def create_batch(self, category: str) -> LogBatch:
        """배치 생성"""
        return LogBatch(category)

    def flush_batch(self, batch: LogBatch) -> None:
        """
        배치 출력

        배치 내 모든 로그를 요약하여 단일 로그로 출력.
        """
        if not self._debug_enabled or batch.is_empty():
            return

        summary = batch.get_summary()

        # 단일 로그로 출력 (배치 요약)
        # Note: standard logging library, not structlog
        self.logger.debug(f"[Batch] {summary['category']}: {summary['count']} entries")

    def is_debug_enabled(self) -> bool:
        """DEBUG 활성화 여부"""
        return self._debug_enabled


# ============================================================
# Factory
# ============================================================


def create_default_config() -> ConfigProvider:
    """
    기본 Configuration 생성

    Production에서 사용하는 기본 설정.
    테스트에서는 mock을 주입 가능.
    """
    return EnvConfigProvider()


def create_default_batch_logger(
    config: ConfigProvider | None = None,
) -> BatchLogger:
    """
    기본 Batch Logger 생성

    Production에서 사용하는 기본 로거.
    """
    if config is None:
        config = create_default_config()

    return StructlogBatchLogger(config)


__all__ = [
    "EnvConfigProvider",
    "StructlogBatchLogger",
    "create_default_config",
    "create_default_batch_logger",
]
