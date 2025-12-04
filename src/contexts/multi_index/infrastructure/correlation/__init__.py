"""
Correlation Index - 심볼 간 상관관계 인덱스

Co-change: Git history에서 함께 변경되는 파일/심볼 쌍
Co-occurrence: 같은 컨텍스트(파일/함수)에서 함께 사용되는 심볼 쌍
"""

from src.contexts.multi_index.infrastructure.correlation.adapter_postgres import (
    CorrelationIndex,
    create_correlation_index,
)
from src.contexts.multi_index.infrastructure.correlation.models import (
    CorrelationEntry,
    CorrelationType,
)

__all__ = [
    "CorrelationIndex",
    "CorrelationEntry",
    "CorrelationType",
    "create_correlation_index",
]
