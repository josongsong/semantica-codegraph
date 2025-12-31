"""
Agent Ports (Interfaces)

Port = Application의 경계를 정의하는 Interface
Hexagonal Architecture의 핵심
"""

from .git_repository import IGitRepository, PartialCommitResult
from .infrastructure import ICommandExecutor, IFileSystem
from .reasoning import (
    IComplexityAnalyzer,
    IGraphAnalyzer,
    IRiskAssessor,
    ISandboxExecutor,
    IToTExecutor,
)

__all__ = [
    "IGitRepository",
    "PartialCommitResult",
    "ICommandExecutor",
    "IFileSystem",
    "IComplexityAnalyzer",
    "IRiskAssessor",
    "IGraphAnalyzer",
    "IToTExecutor",
    "ISandboxExecutor",
]
