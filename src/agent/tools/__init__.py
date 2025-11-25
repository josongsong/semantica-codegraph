"""
Agent Tools

Tool-based interface for LLM agents to interact with code.

Tools:
- code_search: Search code using Semantica's multi-index system
- symbol_search: Find symbols (functions, classes) by name
- open_file: Read file contents
- get_span: Get specific line range from file
- propose_patch: Create code modification proposal
- apply_patch: Apply a proposed patch
- run_tests: Execute tests

Architecture:
- Each tool is a self-contained class inheriting from BaseTool
- Tools use Pydantic schemas for input/output validation
- Tools integrate with Semantica Codegraph for powerful code analysis
"""

from .base import BaseTool, ToolExecutionError
from .code_search import CodeSearchTool
from .file_ops import GetSpanTool, OpenFileTool
from .symbol_search import SymbolSearchTool

__all__ = [
    "BaseTool",
    "ToolExecutionError",
    "CodeSearchTool",
    "SymbolSearchTool",
    "OpenFileTool",
    "GetSpanTool",
]
