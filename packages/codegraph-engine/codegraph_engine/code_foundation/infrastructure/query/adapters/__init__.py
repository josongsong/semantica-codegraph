"""
Query Engine Adapters

Concrete implementations of Domain Ports.

Adapters:
- FileSystemCodeTraceAdapter: Reads actual source files for code traces
"""

from .code_trace_adapter import FileSystemCodeTraceAdapter

__all__ = ["FileSystemCodeTraceAdapter"]
