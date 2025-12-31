"""
Refactoring Domain

순수 비즈니스 로직 - 외부 의존성 없음
"""

from .models import (
    ExtractMethodRequest,
    FileChange,
    RefactoringResult,
    RefactoringType,
    RenameRequest,
    SymbolInfo,
    SymbolKind,
    SymbolLocation,
)

__all__ = [
    # Enums
    "RefactoringType",
    "SymbolKind",
    # Models
    "SymbolLocation",
    "SymbolInfo",
    "FileChange",
    # Requests
    "RenameRequest",
    "ExtractMethodRequest",
    # Results
    "RefactoringResult",
]
