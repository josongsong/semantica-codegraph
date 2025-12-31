"""
Code Editing Domain

코드 편집 관련 순수 비즈니스 로직
- FIM (Fill-in-the-Middle)
- Refactoring
- Atomic Edit
- Utils (Hash, Validation)
"""

# Atomic Edit exports
from .atomic_edit import (
    AtomicEditRequest,
    AtomicEditResult,
    ConflictInfo,
    ConflictType,
    FileEdit,
    IsolationLevel,
    RollbackInfo,
    TransactionState,
)

# FIM exports
from .fim import Completion, FIMEngine, FIMRequest, FIMResult

# Refactoring exports
from .refactoring import (
    ExtractMethodRequest,
    FileChange,
    RefactoringResult,
    RefactoringType,
    RenameRequest,
    SymbolInfo,
    SymbolKind,
    SymbolLocation,
)

# Utils exports
from .utils import (
    Validator,
    compute_content_hash,
    validate_file_path,
    validate_non_empty,
    validate_positive,
    validate_range,
)

__all__ = [
    # FIM
    "FIMRequest",
    "FIMResult",
    "Completion",
    "FIMEngine",
    # Refactoring
    "RefactoringType",
    "SymbolKind",
    "SymbolLocation",
    "SymbolInfo",
    "FileChange",
    "RenameRequest",
    "ExtractMethodRequest",
    "RefactoringResult",
    # Atomic Edit
    "IsolationLevel",
    "TransactionState",
    "ConflictType",
    "FileEdit",
    "ConflictInfo",
    "RollbackInfo",
    "AtomicEditRequest",
    "AtomicEditResult",
    # Utils
    "compute_content_hash",
    "Validator",
    "validate_file_path",
    "validate_non_empty",
    "validate_positive",
    "validate_range",
]
