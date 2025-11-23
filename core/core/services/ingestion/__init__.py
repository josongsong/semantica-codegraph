"""
Ingestion Pipeline

This package handles parsing and chunking of source code.
Converts raw files into structured domain models.
"""

from .parser import CodeParser
from .chunker import CodeChunker

__all__ = [
    "CodeParser",
    "CodeChunker",
]
