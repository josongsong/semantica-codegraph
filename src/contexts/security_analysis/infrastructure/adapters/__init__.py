"""
Adapters for security analysis

기존 시스템을 새로운 인터페이스와 연결하는 어댑터들
"""

from src.contexts.security_analysis.infrastructure.adapters.taint_analyzer_adapter import (
    TaintAnalyzerAdapter,
)

__all__ = [
    "TaintAnalyzerAdapter",
]
