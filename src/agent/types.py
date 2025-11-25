"""
Agent Mode System - Core Type Definitions

Defines all types used across the agent mode system:
- AgentMode: 23 specialized operating modes
- ApprovalLevel: Human-in-the-loop approval levels
- Task, Result, ModeContext: Core data structures
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentMode(str, Enum):
    """Agent operating modes organized by capability"""

    # Core modes (Phase 0)
    IDLE = "idle"
    CONTEXT_NAV = "context_navigation"
    IMPLEMENTATION = "implementation"
    DEBUG = "debug"
    TEST = "test"
    DOCUMENTATION = "documentation"

    # Advanced workflow (Phase 1)
    DESIGN = "design"
    QA = "qa"
    REFACTOR = "refactor"
    MULTI_FILE_EDITING = "multi_file_editing"
    GIT_WORKFLOW = "git_workflow"
    AGENT_PLANNING = "agent_planning"
    IMPACT_ANALYSIS = "impact_analysis"

    # Specialization (Phase 2)
    MIGRATION = "migration"
    DEPENDENCY_INTELLIGENCE = "dependency_intelligence"
    SPEC_COMPLIANCE = "spec_compliance"
    VERIFICATION = "verification"
    PERFORMANCE_PROFILING = "performance_profiling"

    # Advanced specialization (Phase 3)
    OPS_INFRA = "ops_infra"
    ENVIRONMENT_REPRODUCTION = "environment_reproduction"
    BENCHMARK = "benchmark"
    DATA_ML_INTEGRATION = "data_ml_integration"
    EXPLORATORY_RESEARCH = "exploratory_research"


class ApprovalLevel(str, Enum):
    """Human-in-the-loop approval levels"""

    LOW = "low"  # Read-only operations, auto-approve
    MEDIUM = "medium"  # Read + design, auto-approve
    HIGH = "high"  # Read + design + modify, auto-approve
    CRITICAL = "critical"  # Dangerous operations, always require approval


@dataclass
class Task:
    """User task to be executed by agent"""

    query: str  # User's natural language query
    intent: str | None = None  # Classified intent (search, implement, debug, etc.)
    files: list[str] = field(default_factory=list)  # Target files (if known)
    context: dict[str, Any] = field(default_factory=dict)  # Additional context


@dataclass
class Result:
    """Result of mode execution"""

    mode: AgentMode  # Mode that produced this result
    data: Any  # Result data (varies by mode)
    trigger: str | None = None  # Trigger for next mode transition
    explanation: str = ""  # Human-readable explanation
    requires_approval: bool = False  # Whether human approval is needed
    metadata: dict[str, Any] = field(default_factory=dict)  # Additional metadata


@dataclass
class ModeContext:
    """
    Shared context maintained across mode transitions.

    This context persists throughout the agent's operation and is passed
    between modes during transitions.
    """

    # Current work context
    current_files: list[str] = field(default_factory=list)
    current_symbols: list[str] = field(default_factory=list)
    current_task: str = ""

    # History
    mode_history: list[AgentMode] = field(default_factory=list)
    action_history: list[dict] = field(default_factory=list)

    # Graph context (Semantica differentiator)
    impact_nodes: list[str] = field(default_factory=list)  # Affected graph nodes
    dependency_chain: list[str] = field(default_factory=list)  # Dependency path

    # User preferences
    approval_level: ApprovalLevel = ApprovalLevel.HIGH
    preferred_patterns: list[str] = field(default_factory=list)

    # Execution state
    pending_changes: list[dict] = field(default_factory=list)
    test_results: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    last_error: dict | None = None  # Last error encountered (for Debug mode)

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary for serialization"""
        return {
            "current_files": self.current_files,
            "current_symbols": self.current_symbols,
            "current_task": self.current_task,
            "mode_history": [mode.value for mode in self.mode_history],
            "action_history": self.action_history,
            "impact_nodes": self.impact_nodes,
            "dependency_chain": self.dependency_chain,
            "approval_level": self.approval_level.value,
            "preferred_patterns": self.preferred_patterns,
            "pending_changes": self.pending_changes,
            "test_results": self.test_results,
            "errors": self.errors,
        }

    def add_file(self, file_path: str) -> None:
        """Add file to current context (avoid duplicates)"""
        if file_path not in self.current_files:
            self.current_files.append(file_path)

    def add_symbol(self, symbol: str) -> None:
        """Add symbol to current context (avoid duplicates)"""
        if symbol not in self.current_symbols:
            self.current_symbols.append(symbol)

    def add_action(self, action: dict) -> None:
        """Record an action in history"""
        self.action_history.append(action)

    def add_pending_change(self, change: dict) -> None:
        """Add a pending code change"""
        self.pending_changes.append(change)

    def clear_pending_changes(self) -> None:
        """Clear all pending changes"""
        self.pending_changes.clear()


# Additional model types for comprehensive agent operations


@dataclass
class Change:
    """Code change representation."""

    file_path: str
    content: str
    change_type: str  # "add", "modify", "delete"
    line_start: int | None = None
    line_end: int | None = None


@dataclass
class Action:
    """Action taken by agent."""

    mode: str
    action_type: str
    timestamp: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Error:
    """Error representation."""

    message: str
    error_type: str
    traceback: str | None = None


@dataclass
class TestResults:
    """Test execution results."""

    all_passed: bool
    total_tests: int
    passed_tests: int
    failed_tests: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CoverageData:
    """Code coverage data."""

    coverage_percentage: float
    covered_lines: int
    total_lines: int
    details: dict[str, Any] = field(default_factory=dict)
