"""
Custom exceptions for Program Slice Engine
"""


class SlicingError(Exception):
    """Base exception for slicing errors"""

    pass


class NodeNotFoundError(SlicingError):
    """Raised when target node is not found in PDG"""

    pass


class InvalidSliceError(SlicingError):
    """Raised when slice result is invalid"""

    pass


class BudgetExceededError(SlicingError):
    """Raised when token budget is exceeded and cannot be pruned"""

    pass


class FileExtractionError(SlicingError):
    """Raised when file extraction fails"""

    pass


class InterproceduralError(SlicingError):
    """Raised when interprocedural analysis fails"""

    pass
