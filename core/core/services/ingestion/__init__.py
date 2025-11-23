"""
Ingestion Pipeline

This package handles parsing and chunking of source code.
Converts raw files into structured domain models.
"""

from .chunker import CodeChunker
from .parser import CodeParser

__all__ = [
    "CodeParser",
    "CodeChunker",
]
