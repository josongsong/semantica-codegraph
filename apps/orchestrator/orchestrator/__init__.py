"""Agent Package"""

from ._version import __version__
from .domain.reasoning import ReflectionVerdict
from .errors import (
    AgentError,
    ConfigurationError,
    ExecutionError,
    FallbackError,
    InitializationError,
    ReflectionError,
    ValidationError,
)
from .errors import (
    TimeoutError as AgentTimeoutError,
)
from .orchestrator import (
    # Backward compatibility (generic naming)
    AgentOrchestrator,
    AgentRequest,
    AgentResponse,
    # Main API (새 이름)
    DeepReasoningOrchestrator,
    DeepReasoningRequest,
    DeepReasoningResponse,
    FastPathOrchestrator,
    FastPathRequest,
    FastPathResponse,
    # Backward compatibility (v7 naming)
    V7AgentOrchestrator,
    V7AgentRequest,
    V7AgentResponse,
    # Backward compatibility (v8 naming)
    V8AgentOrchestrator,
    V8AgentRequest,
    V8AgentResponse,
    V8ExecutionResult,
)

__all__ = [
    # Main Orchestrator API (새 이름)
    "DeepReasoningOrchestrator",
    "DeepReasoningRequest",
    "DeepReasoningResponse",
    "FastPathOrchestrator",
    "FastPathRequest",
    "FastPathResponse",
    # Backward Compatibility (v8)
    "V8AgentOrchestrator",
    "V8AgentRequest",
    "V8AgentResponse",
    "V8ExecutionResult",
    # Backward Compatibility (v7)
    "V7AgentOrchestrator",
    "V7AgentRequest",
    "V7AgentResponse",
    # Backward Compatibility (generic)
    "AgentOrchestrator",
    "AgentRequest",
    "AgentResponse",
    "ReflectionVerdict",
    # Errors
    "AgentError",
    "ValidationError",
    "InitializationError",
    "ExecutionError",
    "ReflectionError",
    "FallbackError",
    "ConfigurationError",
    "AgentTimeoutError",
    # Metadata
    "__version__",
]
