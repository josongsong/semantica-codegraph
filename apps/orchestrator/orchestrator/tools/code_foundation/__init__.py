"""
Code Foundation Tools for LLM Agent

SOTA 기반 동적 도구 선택 시스템:
- MasRouter (arXiv 2025): 계층적 라우팅
- ScaleMCP (arXiv 2025): 동적 도구 검색
- AutoTool (arXiv 2024): 패턴 기반 학습
- Anthropic: tool_choice 제어
"""

from .base import (
    CodeFoundationTool,
    ExecutionMode,
    ToolCategory,
    ToolMetadata,
    ToolResult,
)
from .executor import ConstrainedToolExecutor
from .provider import CodeFoundationToolProvider
from .registry import CodeFoundationToolRegistry
from .router import CodeAnalysisIntentRouter, Intent

__all__ = [
    # Base
    "CodeFoundationTool",
    "ToolMetadata",
    "ToolResult",
    "ToolCategory",
    "ExecutionMode",
    # Components
    "CodeFoundationToolRegistry",
    "CodeAnalysisIntentRouter",
    "Intent",
    "CodeFoundationToolProvider",
    "ConstrainedToolExecutor",
]
