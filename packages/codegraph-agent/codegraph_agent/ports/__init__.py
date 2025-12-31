"""
Agent Ports (Hexagonal Architecture)

모든 외부 의존성은 Port를 통해 주입됩니다.
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
from codegraph_agent.ports.command import CommandResult, ICommandExecutor
from codegraph_agent.ports.git import BranchInfo, CommitInfo, IGitAdapter, PRInfo
from codegraph_agent.ports.infrastructure import (
    CommandStatus,
    FileSystemEntry,
    IFileSystem,
    IInfraCommandExecutor,
    IProcessMonitor,
    InfraCommandResult,
    SystemProcess,
)
from codegraph_agent.ports.reasoning import (
    IComplexityAnalyzer,
    IGraphAnalyzer,
    ILATSExecutor,
    IRiskAssessor,
    ISandboxExecutor,
    IToTExecutor,
)
from codegraph_agent.ports.static_gate import (
    AnalysisIssue,
    AnalysisLevel,
    IStaticAnalysisGate,
    IssueSeverity,
    StaticAnalysisResult,
)

__all__ = [
    # CASCADE Ports
    "PatchStatus",
    "ReproductionStatus",
    "ProcessStatus",
    "DiffAnchor",
    "PatchResult",
    "ReproductionScript",
    "ReproductionResult",
    "ProcessInfo",
    "GraphNode",
    "PrunedContext",
    "IFuzzyPatcher",
    "IReproductionEngine",
    "IProcessManager",
    "IGraphPruner",
    "ICascadeOrchestrator",
    # Command Port
    "ICommandExecutor",
    "CommandResult",
    # Git Port
    "IGitAdapter",
    "CommitInfo",
    "BranchInfo",
    "PRInfo",
    # Infrastructure Ports
    "IInfraCommandExecutor",
    "IProcessMonitor",
    "IFileSystem",
    "InfraCommandResult",
    "CommandStatus",
    "SystemProcess",
    "FileSystemEntry",
    # Static Gate Port
    "IStaticAnalysisGate",
    "StaticAnalysisResult",
    "AnalysisIssue",
    "AnalysisLevel",
    "IssueSeverity",
    # Reasoning Ports
    "IComplexityAnalyzer",
    "IRiskAssessor",
    "IGraphAnalyzer",
    "IToTExecutor",
    "ILATSExecutor",
    "ISandboxExecutor",
]
