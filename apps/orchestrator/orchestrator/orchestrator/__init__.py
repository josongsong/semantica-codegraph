"""Agent Orchestrator - SOTA System

DeepReasoning: System 2 깊은 추론 (Beam/o1/Debate/AlphaCode) + Constitutional AI
FastPath: System 1 빠른 선형 실행 (Linear Workflow)

Main API:
    from apps.orchestrator.orchestrator.orchestrator import DeepReasoningOrchestrator, DeepReasoningRequest, DeepReasoningResponse

    orchestrator = DeepReasoningOrchestrator(...)
    response = await orchestrator.execute(DeepReasoningRequest(task=...))
"""

# Version
from .._version import __version__
from ..domain.reasoning import ReflectionVerdict

# DeepReasoning (System 2 - 깊은 추론)
from .deep_reasoning_orchestrator import (
    DeepReasoningOrchestrator,
    DeepReasoningRequest,
    DeepReasoningResponse,
    # Backward compatibility aliases
    V8AgentOrchestrator,
    V8AgentRequest,
    V8AgentResponse,
    V8ExecutionResult,
)

# FastPath (System 1 - 빠른 선형 실행)
from .fast_path_orchestrator import (
    AgentOrchestrator,
    AgentRequest,
    AgentResponse,
    FastPathOrchestrator,
    FastPathRequest,
    FastPathResponse,
    # Backward compatibility aliases
    V7AgentOrchestrator,
    V7AgentRequest,
    V7AgentResponse,
)

# Models
from .models import (
    AgentResult,
    ExecutionContext,
    ExecutionStatus,
    OrchestratorConfig,
)

__all__ = [
    # Version
    "__version__",
    # DeepReasoning (Main API - System 2)
    "DeepReasoningOrchestrator",
    "DeepReasoningRequest",
    "DeepReasoningResponse",
    "V8ExecutionResult",
    "ReflectionVerdict",
    # FastPath (System 1)
    "FastPathOrchestrator",
    "FastPathRequest",
    "FastPathResponse",
    # Models
    "AgentResult",
    "ExecutionContext",
    "ExecutionStatus",
    "OrchestratorConfig",
    # Backward Compatibility (v8 naming)
    "V8AgentOrchestrator",
    "V8AgentRequest",
    "V8AgentResponse",
    # Backward Compatibility (v7 naming)
    "V7AgentOrchestrator",
    "V7AgentRequest",
    "V7AgentResponse",
    # Backward Compatibility (generic naming)
    "AgentOrchestrator",
    "AgentRequest",
    "AgentResponse",
]
