"""
CASCADE 컴포넌트 Port 정의 (DEPRECATED)

⚠️  MIGRATION NOTICE:
This module is DEPRECATED. Please use:
    from codegraph_agent.ports.cascade import (
        PatchStatus,
        DiffAnchor,
        PatchResult,
        IFuzzyPatcher,
        ...
    )

레거시 호환성을 위해 codegraph-agent에서 re-export합니다.
"""

import warnings

warnings.warn(
    "apps.orchestrator.orchestrator.shared.ports.cascade is deprecated. Use codegraph_agent.ports.cascade instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from codegraph-agent (SSOT)
from codegraph_agent.ports.cascade import (  # noqa: E402, F401
    DiffAnchor,
    GraphNode,
    ICascadeOrchestrator,
    IFuzzyPatcher,
    IGraphPruner,
    IProcessManager,
    IReproductionEngine,
    PatchResult,
    PatchStatus,
    ProcessInfo,
    ProcessStatus,
    PrunedContext,
    ReproductionResult,
    ReproductionScript,
    ReproductionStatus,
)

__all__ = [
    # Enums
    "PatchStatus",
    "ReproductionStatus",
    "ProcessStatus",
    # Domain Models
    "DiffAnchor",
    "PatchResult",
    "ReproductionScript",
    "ReproductionResult",
    "ProcessInfo",
    "GraphNode",
    "PrunedContext",
    # Ports
    "IFuzzyPatcher",
    "IReproductionEngine",
    "IProcessManager",
    "IGraphPruner",
    "ICascadeOrchestrator",
]
