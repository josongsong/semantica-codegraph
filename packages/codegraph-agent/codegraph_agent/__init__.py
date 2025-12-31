"""
Codegraph Agent - Autonomous Coding Agent (RFC-060)

Two operating modes:
- Autonomous Mode: TDD cycle, long-running tasks (SWE-Bench style)
- Assistant Mode: Fast, Cursor-like code editing

Architecture:
- Hexagonal Architecture (Ports and Adapters)
- SOLID Principles
- Event-driven coupling with codegraph-engine/incremental
"""

from codegraph_agent.ports.cascade import (
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
    # Ports (Interfaces)
    "IFuzzyPatcher",
    "IReproductionEngine",
    "IProcessManager",
    "IGraphPruner",
    "ICascadeOrchestrator",
]
