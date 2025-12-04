"""
Pipeline Components

Provides reusable pipeline infrastructure including:
- Stage decorators for common boilerplate
- Context management
- Progress tracking
"""

from src.pipeline.decorators import index_execution, stage_execution

__all__ = [
    "stage_execution",
    "index_execution",
]
