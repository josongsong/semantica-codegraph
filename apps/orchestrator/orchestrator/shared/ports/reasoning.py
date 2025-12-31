"""
Reasoning Ports (DEPRECATED)

⚠️  MIGRATION NOTICE:
This module is DEPRECATED. Please use:
    from codegraph_agent.ports.reasoning import (
        IComplexityAnalyzer,
        IRiskAssessor,
        IToTExecutor,
        ILATSExecutor,
        ...
    )

레거시 호환성을 위해 codegraph-agent에서 re-export합니다.
"""

import warnings

warnings.warn(
    "apps.orchestrator.orchestrator.shared.ports.reasoning is deprecated. Use codegraph_agent.ports.reasoning instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from codegraph-agent (SSOT)
from codegraph_agent.ports.reasoning import (  # noqa: E402, F401
    IComplexityAnalyzer,
    IGraphAnalyzer,
    ILATSExecutor,
    IRiskAssessor,
    ISandboxExecutor,
    IToTExecutor,
)

__all__ = [
    "IComplexityAnalyzer",
    "IRiskAssessor",
    "IGraphAnalyzer",
    "IToTExecutor",
    "ILATSExecutor",
    "ISandboxExecutor",
]
