"""
Semantic IR Configuration (Hexagonal Architecture - Backward Compatibility)

Phase 1 최적화: 로깅 오버헤드 제거
Phase 2 최적화: Hexagonal Architecture (Domain/Infrastructure 분리)

Architecture:
    Old (Phase 1): config.py → Direct env var access (위반)
    New (Phase 2): Domain → Port → Adapter → env var (준수)

Backward Compatibility:
    기존 코드와의 호환성을 위해 module-level 상수 유지.
    새 코드는 adapters.py의 ConfigProvider 사용 권장.
"""

import logging
import os

# ============================================================
# Backward Compatibility: Module-level Constants
# ============================================================
# DEPRECATED: 기존 코드와의 호환성을 위해 유지.
# 새 코드는 adapters.ConfigProvider 사용 권장.

_ENABLE_SEMANTIC_IR_DEBUG = os.getenv("SEMANTIC_IR_DEBUG", "false").lower() == "true"

ENABLE_SEMANTIC_IR_PARALLEL = os.getenv("SEMANTIC_IR_PARALLEL", "false").lower() == "true"

SEMANTIC_IR_MAX_WORKERS = int(os.getenv("SEMANTIC_IR_MAX_WORKERS", str(max(1, os.cpu_count() or 1))))

# ============================================================
# SOTA Configuration Constants (No Magic Numbers!)
# ============================================================

# Incremental update threshold: Full rebuild if >50% functions changed
INCREMENTAL_UPDATE_THRESHOLD = float(os.getenv("SEMANTIC_IR_INCREMENTAL_THRESHOLD", "0.5"))

# Body hash length: SHA256 truncated to 16 chars for efficiency
BODY_HASH_LENGTH = int(os.getenv("SEMANTIC_IR_HASH_LENGTH", "16"))

# Hash format prefix
BODY_HASH_PREFIX = "body_sha256"

_DEBUG_ENABLED = _ENABLE_SEMANTIC_IR_DEBUG and logging.getLogger().isEnabledFor(logging.DEBUG)


def should_log_debug() -> bool:
    """
    DEPRECATED: Use adapters.ConfigProvider instead.

    Kept for backward compatibility with Phase 1 code.
    """
    return _DEBUG_ENABLED


# ============================================================
# Phase 2: Hexagonal Architecture Imports
# ============================================================
# 새 코드는 이것 사용 권장

# Lazy imports to avoid circular dependencies
_HAS_HEXAGONAL = None
_ADAPTERS_CACHE = {}


def _ensure_hexagonal_imports():
    """
    Lazy import to avoid circular dependencies.

    config.py → adapters.py → ports.py ✅ (OK)
    builder.py → config.py → adapters.py ✅ (Lazy, OK)
    """
    global _HAS_HEXAGONAL, _ADAPTERS_CACHE

    if _HAS_HEXAGONAL is not None:
        return _HAS_HEXAGONAL

    try:
        from codegraph_engine.code_foundation.domain.semantic_ir.ports import (
            BatchLogger,
            ConfigProvider,
            LogBatch,
        )
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.adapters import (
            EnvConfigProvider,
            StructlogBatchLogger,
            create_default_batch_logger,
            create_default_config,
        )

        _ADAPTERS_CACHE["EnvConfigProvider"] = EnvConfigProvider
        _ADAPTERS_CACHE["StructlogBatchLogger"] = StructlogBatchLogger
        _ADAPTERS_CACHE["create_default_config"] = create_default_config
        _ADAPTERS_CACHE["create_default_batch_logger"] = create_default_batch_logger
        _ADAPTERS_CACHE["ConfigProvider"] = ConfigProvider
        _ADAPTERS_CACHE["BatchLogger"] = BatchLogger
        _ADAPTERS_CACHE["LogBatch"] = LogBatch

        _HAS_HEXAGONAL = True
        return True

    except ImportError:
        _HAS_HEXAGONAL = False
        return False


# Public API with lazy loading
def __getattr__(name):
    """Lazy attribute access for Hexagonal imports"""
    if name in [
        "ConfigProvider",
        "BatchLogger",
        "LogBatch",
        "create_default_config",
        "create_default_batch_logger",
        "EnvConfigProvider",
        "StructlogBatchLogger",
    ]:
        _ensure_hexagonal_imports()
        if name in _ADAPTERS_CACHE:
            return _ADAPTERS_CACHE[name]
        raise AttributeError(f"Hexagonal import failed: {name}")
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    # Phase 1 (Backward Compatibility)
    "_DEBUG_ENABLED",
    "should_log_debug",
    "ENABLE_SEMANTIC_IR_PARALLEL",
    "SEMANTIC_IR_MAX_WORKERS",
    # SOTA Constants
    "INCREMENTAL_UPDATE_THRESHOLD",
    "BODY_HASH_LENGTH",
    "BODY_HASH_PREFIX",
]
