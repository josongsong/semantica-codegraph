"""
Session Memory Repositories (SOTA Refactored)

Generic repository implementations eliminating code duplication.
"""

from .base import BoundedInMemoryRepository, InMemoryRepository
from .pattern_repository import (
    BugPatternRepository,
    CodePatternRepository,
    CodeRuleRepository,
)
from .scoring import VectorSimilarity

__all__ = [
    "InMemoryRepository",
    "BoundedInMemoryRepository",
    "BugPatternRepository",
    "CodePatternRepository",
    "CodeRuleRepository",
    "VectorSimilarity",
]
