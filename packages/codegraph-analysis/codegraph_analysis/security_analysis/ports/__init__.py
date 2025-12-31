"""
Security Analysis Ports

보안 분석의 포트(인터페이스) 정의
Hexagonal Architecture의 Port 레이어
"""

from .protocols import (
    SecurityAnalyzerPort,
    VulnerabilityStorePort,
)

__all__ = [
    "SecurityAnalyzerPort",
    "VulnerabilityStorePort",
]
