"""
Benchmark suite for Codegraph performance profiling.

Includes:
- Indexing performance profiling
- Retriever performance benchmarking
"""

from .profiler import IndexingProfiler
from .report_generator import ReportGenerator

__all__ = [
    "IndexingProfiler",
    "ReportGenerator",
]
