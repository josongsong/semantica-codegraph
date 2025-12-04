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
    CRITIC = "critic"  # Self-critique and evaluation
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
    action_history: list[dict[str, Any]] = field(default_factory=list)

    # Graph context (Semantica differentiator)
    impact_nodes: list[str] = field(default_factory=list)  # Affected graph nodes
    dependency_chain: list[str] = field(default_factory=list)  # Dependency path

    # User preferences
    approval_level: ApprovalLevel = ApprovalLevel.HIGH
    preferred_patterns: list[str] = field(default_factory=list)

    # Execution state
    pending_changes: list[dict[str, Any]] = field(default_factory=list)
    test_results: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    last_error: dict[str, Any] | None = None  # Last error encountered (for Debug mode)

    # Memory context (episodic + semantic memory)
    recalled_memories: dict[str, Any] = field(default_factory=dict)  # From memory system
    guidance: dict[str, Any] = field(default_factory=dict)  # Synthesized guidance
    session_facts: list[str] = field(default_factory=list)  # Facts to remember

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
            "recalled_memories": self.recalled_memories,
            "guidance": self.guidance,
            "session_facts": self.session_facts,
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

    def add_fact(self, fact: str) -> None:
        """Add a fact to remember for this session."""
        if fact not in self.session_facts:
            self.session_facts.append(fact)

    def set_memories(self, memories: dict[str, Any]) -> None:
        """Set recalled memories from memory system."""
        self.recalled_memories = memories
        if guidance := memories.get("guidance"):
            self.guidance = {
                "suggested_approach": getattr(guidance, "suggested_approach", ""),
                "things_to_try": getattr(guidance, "things_to_try", []),
                "things_to_avoid": getattr(guidance, "things_to_avoid", []),
                "expected_challenges": getattr(guidance, "expected_challenges", []),
                "confidence": getattr(guidance, "confidence", 0.0),
            }

    def get_similar_episodes(self) -> list[dict]:
        """Get similar past episodes from recalled memories."""
        return self.recalled_memories.get("episodes", [])

    def get_relevant_patterns(self) -> list[dict]:
        """Get relevant bug/code patterns from recalled memories."""
        return self.recalled_memories.get("patterns", [])

    def get_guidance_summary(self) -> str:
        """Get human-readable guidance summary."""
        if not self.guidance:
            return ""

        parts = []
        if approach := self.guidance.get("suggested_approach"):
            parts.append(f"Suggested approach: {approach}")
        if things_to_try := self.guidance.get("things_to_try"):
            parts.append(f"Try: {', '.join(things_to_try[:3])}")
        if things_to_avoid := self.guidance.get("things_to_avoid"):
            parts.append(f"Avoid: {', '.join(things_to_avoid[:3])}")

        return "\n".join(parts)


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
class CodeTestResults:
    """
    Test execution results.

    Note: Named CodeTestResults to avoid pytest collection warnings.
    """

    all_passed: bool
    total_tests: int
    passed_tests: int
    failed_tests: int
    details: dict[str, Any] = field(default_factory=dict)


# Alias for backward compatibility
TestResults = CodeTestResults


@dataclass
class CoverageData:
    """Code coverage data."""

    coverage_percentage: float
    covered_lines: int
    total_lines: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReflectionOutput:
    """Reflection 평가 결과."""

    needs_improvement: bool  # 개선 필요 여부
    quality_score: float  # 0.0 ~ 1.0
    issues: list[str] = field(default_factory=list)  # 발견된 문제점
    suggestions: list[str] = field(default_factory=list)  # 개선 제안
    strengths: list[str] = field(default_factory=list)  # 잘된 부분
    metadata: dict[str, Any] = field(default_factory=dict)  # 추가 정보


@dataclass
class CriticOutput:
    """Critic Agent 평가 결과."""

    approved: bool  # 승인 여부
    overall_score: float  # 0.0 ~ 1.0 종합 점수
    correctness_score: float  # 정확성
    completeness_score: float  # 완전성
    safety_score: float  # 안전성
    issues: list[str] = field(default_factory=list)  # 발견된 문제
    recommendations: list[str] = field(default_factory=list)  # 개선 권장사항
    must_fix: list[str] = field(default_factory=list)  # 필수 수정사항
    metadata: dict[str, Any] = field(default_factory=dict)
