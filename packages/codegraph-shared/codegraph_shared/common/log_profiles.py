"""
SOTA급 로그 프로필 시스템

환경별 자동 설정:
- DEV: 상세 로깅 (샘플링)
- PROD: 요약만 (배치)
- BENCH: 로깅 최소화 (성능 측정용)
- DEBUG: 전체 로깅 (문제 분석용)
"""

import os
from dataclasses import dataclass
from enum import Enum


class LogProfile(str, Enum):
    """로그 프로필"""

    DEV = "dev"  # 개발: 샘플링 + 배치
    PROD = "prod"  # 운영: 배치만, INFO 레벨
    BENCH = "bench"  # 벤치마크: 로깅 최소화
    DEBUG = "debug"  # 디버깅: 전체 로깅
    TEST = "test"  # 테스트: ERROR만


@dataclass
class LogConfig:
    """로그 설정"""

    # 레벨
    level: str  # DEBUG, INFO, WARNING, ERROR

    # Hot path 설정
    enable_hot_path_logs: bool  # hot path 로깅 활성화
    hot_path_sample_rate: float  # 샘플링 비율 (0.0-1.0)

    # 배치 로깅
    enable_batch_logging: bool  # 배치 로깅 활성화
    batch_sample_size: int  # 배치 샘플 크기

    # 비동기 로깅
    enable_async_logging: bool  # 비동기 로깅 활성화

    # 포맷
    json_format: bool  # JSON 포맷 (분석용)

    # 성능
    disable_string_formatting: bool  # f-string 비활성화


# ============================================================
# 프로필별 설정
# ============================================================

PROFILE_CONFIGS = {
    LogProfile.DEV: LogConfig(
        level="INFO",
        enable_hot_path_logs=True,
        hot_path_sample_rate=0.01,  # 1% 샘플링
        enable_batch_logging=True,
        batch_sample_size=3,
        enable_async_logging=False,  # 개발 중에는 동기
        json_format=False,
        disable_string_formatting=False,
    ),
    LogProfile.PROD: LogConfig(
        level="INFO",
        enable_hot_path_logs=False,  # hot path 로깅 off
        hot_path_sample_rate=0.0,
        enable_batch_logging=True,  # 배치만
        batch_sample_size=0,  # 샘플 없음 (count만)
        enable_async_logging=True,  # 비동기
        json_format=True,  # JSON (분석용)
        disable_string_formatting=True,  # 성능 최적화
    ),
    LogProfile.BENCH: LogConfig(
        level="WARNING",  # 경고만
        enable_hot_path_logs=False,
        hot_path_sample_rate=0.0,
        enable_batch_logging=False,  # 배치도 off
        batch_sample_size=0,
        enable_async_logging=False,
        json_format=False,
        disable_string_formatting=True,
    ),
    LogProfile.DEBUG: LogConfig(
        level="DEBUG",
        enable_hot_path_logs=True,
        hot_path_sample_rate=0.1,  # 10% 샘플링
        enable_batch_logging=True,
        batch_sample_size=10,  # 많은 샘플
        enable_async_logging=False,  # 동기 (디버깅 용이)
        json_format=False,
        disable_string_formatting=False,
    ),
    LogProfile.TEST: LogConfig(
        level="ERROR",  # 에러만
        enable_hot_path_logs=False,
        hot_path_sample_rate=0.0,
        enable_batch_logging=False,
        batch_sample_size=0,
        enable_async_logging=False,
        json_format=False,
        disable_string_formatting=True,
    ),
}


def get_current_profile() -> LogProfile:
    """
    현재 환경의 로그 프로필 결정.

    우선순위:
    1. 환경변수 LOG_PROFILE
    2. 환경변수 ENV (dev/prod)
    3. 기본값 (DEV)
    """
    # 명시적 프로필
    profile_str = os.getenv("LOG_PROFILE", "").lower()
    if profile_str:
        try:
            return LogProfile(profile_str)
        except ValueError:
            pass

    # 환경 기반 추론
    env = os.getenv("ENV", "dev").lower()
    if env == "production" or env == "prod":
        return LogProfile.PROD
    elif env == "test":
        return LogProfile.TEST
    elif env == "bench" or env == "benchmark":
        return LogProfile.BENCH

    # 기본값
    return LogProfile.DEV


def get_log_config(profile: LogProfile | None = None) -> LogConfig:
    """
    로그 설정 가져오기.

    Args:
        profile: 프로필 (None이면 자동 감지)

    Returns:
        LogConfig
    """
    if profile is None:
        profile = get_current_profile()

    return PROFILE_CONFIGS[profile]


# ============================================================
# 전역 설정
# ============================================================

_CURRENT_CONFIG: LogConfig | None = None


def init_logging(profile: LogProfile | None = None):
    """
    로깅 시스템 초기화.

    Args:
        profile: 프로필 (None이면 자동 감지)
    """
    global _CURRENT_CONFIG

    if profile is None:
        profile = get_current_profile()

    _CURRENT_CONFIG = get_log_config(profile)

    # logging_config 적용
    from codegraph_shared.common.logging_config import configure_logging

    configure_logging(
        level=_CURRENT_CONFIG.level,
        json_format=_CURRENT_CONFIG.json_format,
    )

    # 프로필 정보 출력 (간단히)
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized: profile={profile.value}, level={_CURRENT_CONFIG.level}")


def get_current_config() -> LogConfig:
    """현재 로그 설정"""
    global _CURRENT_CONFIG
    if _CURRENT_CONFIG is None:
        init_logging()
    return _CURRENT_CONFIG


def get_logger_for_profile():
    """프로필 기반 로거"""
    from codegraph_shared.common.logging_config import get_logger

    return get_logger(__name__)


# ============================================================
# 편의 함수
# ============================================================


def should_log_hot_path() -> bool:
    """Hot path 로깅 활성화 여부"""
    config = get_current_config()
    return config.enable_hot_path_logs


def get_hot_path_sample_rate() -> float:
    """Hot path 샘플링 비율"""
    config = get_current_config()
    return config.hot_path_sample_rate


def should_use_batch_logging() -> bool:
    """배치 로깅 사용 여부"""
    config = get_current_config()
    return config.enable_batch_logging


def get_batch_sample_size() -> int:
    """배치 샘플 크기"""
    config = get_current_config()
    return config.batch_sample_size
