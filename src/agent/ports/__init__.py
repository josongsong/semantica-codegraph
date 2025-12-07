"""
Agent Ports (Interfaces)

Port = Application의 경계를 정의하는 Interface
Hexagonal Architecture의 핵심
"""

from .reasoning import (
    IComplexityAnalyzer,
    IGraphAnalyzer,
    IRiskAssessor,
    ISandboxExecutor,
    IToTExecutor,
)

__all__ = [
    "IComplexityAnalyzer",
    "IRiskAssessor",
    "IGraphAnalyzer",
    "IToTExecutor",
    "ISandboxExecutor",
]
