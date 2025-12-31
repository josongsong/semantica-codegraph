"""
Smart Filtering

Advanced filtering strategies for retrieval results.

Features:
- Error-prone code detection (proxy metrics)
- Coverage-based filtering
- Recency scoring
- Complexity filtering
"""

from .error_prone import ErrorProneScorer
from .models import ErrorProneMetrics, FilterConfig

__all__ = [
    "ErrorProneScorer",
    "ErrorProneMetrics",
    "FilterConfig",
]
