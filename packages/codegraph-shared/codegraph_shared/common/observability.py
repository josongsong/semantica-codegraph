"""
통합 Observability 시스템

SOTA급 로깅 + 메트릭 + 트레이싱 통합.
환경별 자동 설정.
"""

import logging
import os
from typing import Any

# 전역 로거 캐시
_LOGGER_CACHE: dict[str, Any] = {}
_INITIALIZED = False


def get_logger(name: str):
    """
    로거 가져오기 (프로필 기반 자동 설정).

    첫 호출 시 자동으로 로깅 시스템 초기화.

    Args:
        name: 로거 이름 (보통 __name__)

    Returns:
        설정된 로거
    """
    global _INITIALIZED

    # 첫 호출 시 초기화
    if not _INITIALIZED:
        _initialize_logging()
        _INITIALIZED = True

    # 캐시 확인
    if name in _LOGGER_CACHE:
        return _LOGGER_CACHE[name]

    # 로거 생성
    try:
        from codegraph_shared.common.logging_config import get_logger as get_structured_logger

        logger = get_structured_logger(name)
    except ImportError:
        # Fallback to stdlib
        logger = logging.getLogger(name)

    _LOGGER_CACHE[name] = logger
    return logger


def _initialize_logging():
    """로깅 시스템 초기화 (자동)"""
    try:
        from codegraph_shared.common.log_profiles import init_logging

        init_logging()  # 프로필 기반 자동 설정
    except ImportError:
        # Fallback
        logging.basicConfig(
            format="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
            level=logging.INFO,
        )


def reset_logging():
    """로깅 시스템 리셋 (테스트용)"""
    global _INITIALIZED, _LOGGER_CACHE
    _INITIALIZED = False
    _LOGGER_CACHE.clear()


# ============================================================
# 메트릭 스텁 (backward compatibility)
# ============================================================


def record_counter(name: str, value: int = 1, **tags):
    """카운터 메트릭 기록 (스텁)"""
    pass


def record_histogram(name: str, value: float, **tags):
    """히스토그램 메트릭 기록 (스텁)"""
    pass


def record_gauge(name: str, value: float, **tags):
    """게이지 메트릭 기록 (스텁)"""
    pass
