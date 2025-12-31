"""
Atomic Edit Domain

순수 비즈니스 로직 - 외부 의존성 없음
"""

from .models import (
    AtomicEditRequest,
    AtomicEditResult,
    ConflictInfo,
    ConflictType,
    FileEdit,
    IsolationLevel,
    RollbackInfo,
    TransactionState,
)

__all__ = [
    # Enums
    "IsolationLevel",
    "TransactionState",
    "ConflictType",
    # Models
    "FileEdit",
    "ConflictInfo",
    "RollbackInfo",
    # Requests
    "AtomicEditRequest",
    # Results
    "AtomicEditResult",
]
