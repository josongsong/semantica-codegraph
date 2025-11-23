import logging
import sys
from typing import Optional

from infra.config.settings import settings


def setup_logging(log_level: Optional[str] = None):
    """로깅 설정"""
    level = log_level or settings.log_level
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def get_logger(name: str) -> logging.Logger:
    """로거 생성"""
    return logging.getLogger(name)

