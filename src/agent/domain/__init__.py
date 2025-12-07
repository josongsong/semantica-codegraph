"""
Agent Domain Layer

비즈니스 로직을 포함한 Domain Model.
Pydantic DTO와 명확히 분리.
"""

from src.agent.domain.models import (
    AgentTask,
    AnalysisResult,
    CodeChange,
    CommitResult,
    ConflictResolution,
    ExecutionResult,
    MergeConflict,
    PRResult,
    SandboxHandle,
    Screenshot,
    ValidationResult,
    VisualDiff,
    WorkflowResult,
    WorkflowState,
)

__all__ = [
    "AgentTask",
    "CodeChange",
    "WorkflowState",
    "AnalysisResult",
    "ExecutionResult",
    "SandboxHandle",
    "Screenshot",
    "ValidationResult",
    "CommitResult",
    "PRResult",
    "MergeConflict",
    "ConflictResolution",
    "VisualDiff",
    "WorkflowResult",
]
