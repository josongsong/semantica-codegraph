"""
Session Memory Domain Models (SOTA Refactored)

Clean domain models following DDD principles:
- Value Objects: Immutable, identity by value
- Entities: Mutable, identity by ID
- Aggregates: Consistency boundaries

3-tier memory architecture:
- Working Memory: Current session state
- Episodic Memory: Task execution history
- Semantic Memory: Learned patterns and knowledge
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Generic, Literal, TypeVar

# ============================================================
# Enums (Value Objects)
# ============================================================


class MemoryType(str, Enum):
    """Types of memory for routing."""

    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROFILE = "profile"
    PREFERENCE = "preference"
    FACT = "fact"
    NONE = "none"


class TaskType(str, Enum):
    """Types of tasks the agent can perform."""

    SEARCH = "search"
    IMPLEMENT = "implement"
    DEBUG = "debug"
    TEST = "test"
    REFACTOR = "refactor"
    DOCUMENTATION = "documentation"
    DESIGN = "design"
    FEATURE = "feature"
    REVIEW = "review"
    MIGRATION = "migration"
    UNKNOWN = "unknown"


class TaskStatus(str, Enum):
    """Status of task execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class ImportanceLevel(str, Enum):
    """Importance level for memory retention."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    TRIVIAL = "trivial"


class PatternCategory(str, Enum):
    """Categories for code transformation patterns."""

    NULL_SAFETY = "null_safety"
    ERROR_HANDLING = "error_handling"
    STYLE = "style"
    PERFORMANCE = "performance"
    SECURITY = "security"
    READABILITY = "readability"
    REFACTORING = "refactoring"
    OTHER = "other"


# ============================================================
# Value Objects (Immutable)
# ============================================================


@dataclass(frozen=True)
class EmbeddingVector:
    """Immutable embedding vector with dimension validation."""

    values: tuple[float, ...]

    @property
    def dimension(self) -> int:
        return len(self.values)

    def to_list(self) -> list[float]:
        return list(self.values)

    @classmethod
    def from_list(cls, values: list[float]) -> EmbeddingVector:
        return cls(values=tuple(values))

    @classmethod
    def empty(cls, dimension: int = 0) -> EmbeddingVector:
        return cls(values=tuple([0.0] * dimension))


@dataclass(frozen=True)
class MemoryScore:
    """
    Composite score for memory retrieval (SOTA 3-axis).

    score = w_sim * similarity + w_rec * recency + w_imp * importance
    """

    similarity: float = 0.0
    recency: float = 0.0
    importance: float = 0.0
    w_similarity: float = 0.5
    w_recency: float = 0.3
    w_importance: float = 0.2

    @property
    def composite_score(self) -> float:
        """Compute weighted composite score."""
        return self.w_similarity * self.similarity + self.w_recency * self.recency + self.w_importance * self.importance


@dataclass(frozen=True)
class ErrorSignature:
    """Immutable error signature for pattern matching."""

    error_type: str
    message_pattern: str | None = None
    stack_pattern: str | None = None


@dataclass(frozen=True)
class FileChange:
    """Immutable file change record."""

    path: str
    lines_added: int = 0
    lines_removed: int = 0
    description: str = ""


# ============================================================
# Entity Base
# ============================================================

T = TypeVar("T")


@dataclass
class Entity:
    """Base entity with identity."""

    id: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


# ============================================================
# Working Memory Entities
# ============================================================


@dataclass
class StepRecord(Entity):
    """Record of a single execution step."""

    step_number: int = 0
    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_result: Any = None
    success: bool = True
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class Hypothesis(Entity):
    """A hypothesis about the problem/solution."""

    description: str = ""
    confidence: float = 0.5
    evidence: list[str] = field(default_factory=list)
    status: Literal["active", "confirmed", "rejected"] = "active"


@dataclass
class Decision(Entity):
    """A decision made during execution."""

    description: str = ""
    rationale: str = ""
    alternatives: list[str] = field(default_factory=list)
    accepted: bool = True
    context_snapshot: dict[str, Any] = field(default_factory=dict)


# ============================================================
# Episodic Memory Entities
# ============================================================


@dataclass
class Episode(Entity):
    """
    A complete episode of task execution.
    Aggregate root for episodic memory.
    """

    project_id: str = "default"
    session_id: str = ""

    # Task information
    task_type: TaskType = TaskType.UNKNOWN
    task_description: str = ""
    task_description_embedding: list[float] = field(default_factory=list)
    task_complexity: float = 0.5

    # Context
    files_involved: list[str] = field(default_factory=list)
    symbols_involved: list[str] = field(default_factory=list)
    error_types: list[str] = field(default_factory=list)
    stack_trace_signature: str | None = None

    # Execution
    plan_summary: str = ""
    steps_count: int = 0
    key_decisions: list[Decision] = field(default_factory=list)

    # Outcome
    outcome_status: TaskStatus = TaskStatus.UNKNOWN
    patches: list[FileChange] = field(default_factory=list)
    tests_passed: bool = False
    user_feedback: Literal["positive", "negative", "neutral"] | None = None

    # Extracted knowledge
    problem_pattern: str = ""
    solution_pattern: str = ""
    gotchas: list[str] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)

    # Metadata
    duration_ms: float = 0.0
    tokens_used: int = 0
    retrieval_count: int = 0
    usefulness_score: float = 0.5


# ============================================================
# Semantic Memory Entities (Patterns)
# ============================================================


@dataclass
class Solution(Entity):
    """A solution to a pattern."""

    description: str = ""
    approach: str = ""
    code_template: str | None = None
    success_rate: float = 0.5
    application_count: int = 0
    applicability_conditions: list[str] = field(default_factory=list)


@dataclass
class BugPattern(Entity):
    """A learned pattern for bug detection and resolution."""

    name: str = ""

    # Signature
    error_types: list[str] = field(default_factory=list)
    error_message_patterns: list[str] = field(default_factory=list)
    stack_trace_patterns: list[str] = field(default_factory=list)
    code_patterns: list[str] = field(default_factory=list)

    # Context (for filtering)
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    common_causes: list[str] = field(default_factory=list)

    # Sample data (for embedding)
    sample_error_message: str = ""
    sample_stacktrace: str | None = None
    sample_code_snippet: str | None = None

    # Embeddings
    message_embedding: list[float] | None = None
    stack_embedding: list[float] | None = None
    code_embedding: list[float] | None = None

    # Solutions
    solutions: list[Solution] = field(default_factory=list)

    # Statistics
    occurrence_count: int = 0
    resolution_count: int = 0
    avg_resolution_time_ms: float = 0.0
    last_seen: datetime = field(default_factory=datetime.now)


@dataclass
class CodePattern(Entity):
    """A learned code pattern (refactoring, optimization, etc.)."""

    name: str = ""
    category: str = PatternCategory.OTHER.value
    description: str = ""

    # Pattern detection
    before_pattern: str | None = None
    after_pattern: str | None = None
    detection_rules: list[str] = field(default_factory=list)

    # Applicability
    applicable_languages: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    contraindications: list[str] = field(default_factory=list)

    # Impact metrics
    readability_impact: float = 0.0
    performance_impact: float = 0.0
    maintainability_impact: float = 0.0

    # Statistics
    application_count: int = 0
    success_rate: float = 0.5


@dataclass
class CodeRule(Entity):
    """
    A learned code transformation rule.

    Represents patterns like: "dict['key'] -> dict.get('key', default)"
    """

    name: str = ""
    description: str = ""
    category: PatternCategory = PatternCategory.OTHER

    # Pattern definition
    before_pattern: str = ""
    after_pattern: str = ""
    pattern_type: Literal["regex", "ast", "literal"] = "literal"

    # Language applicability
    languages: list[str] = field(default_factory=lambda: ["python"])

    # Learning metrics
    confidence: float = 0.5
    observation_count: int = 1
    success_count: int = 0
    failure_count: int = 0

    # Thresholds
    min_confidence_threshold: float = 0.3
    promotion_threshold: float = 0.8

    # Examples
    examples: list[dict[str, str]] = field(default_factory=list)
    source_episodes: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5

    @property
    def is_trusted(self) -> bool:
        return self.confidence >= self.promotion_threshold and self.observation_count >= 5

    @property
    def should_remove(self) -> bool:
        return self.confidence < self.min_confidence_threshold and self.observation_count >= 5

    def reinforce(self, success: bool, weight: float = 0.1) -> None:
        """Reinforce or weaken the rule based on outcome."""
        self.observation_count += 1
        if success:
            self.success_count += 1
            self.confidence = min(1.0, self.confidence + weight * (1.0 - self.confidence))
        else:
            self.failure_count += 1
            self.confidence = max(0.0, self.confidence - weight * self.confidence)
        self.updated_at = datetime.now()


# ============================================================
# Project & User Knowledge
# ============================================================


@dataclass
class ProjectKnowledge(Entity):
    """Learned knowledge about a specific project."""

    project_id: str = ""

    # Structure
    architecture_type: str = "monolith"
    main_directories: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)

    # Conventions
    naming_conventions: dict[str, str] = field(default_factory=dict)
    file_organization: str = ""
    testing_patterns: list[str] = field(default_factory=list)

    # Tech stack
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    testing_frameworks: list[str] = field(default_factory=list)

    # Hotspots
    frequently_modified: list[str] = field(default_factory=list)
    high_complexity: list[str] = field(default_factory=list)
    bug_prone: list[str] = field(default_factory=list)

    # Team knowledge
    common_issues: list[str] = field(default_factory=list)
    preferred_solutions: dict[str, str] = field(default_factory=dict)
    avoid_patterns: list[str] = field(default_factory=list)

    # Statistics
    total_sessions: int = 0
    total_tasks: int = 0
    success_rate: float = 0.5
    common_task_types: dict[str, int] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class UserPreferences(Entity):
    """Learned user preferences."""

    user_id: str = ""

    # Coding style
    verbosity: Literal["minimal", "moderate", "detailed"] = "moderate"
    comment_style: Literal["none", "minimal", "extensive"] = "minimal"
    variable_naming: Literal["short", "descriptive"] = "descriptive"

    # Interaction style
    explanation_depth: Literal["brief", "moderate", "thorough"] = "moderate"
    confirmation_frequency: Literal["always", "important", "rarely"] = "important"
    proactivity: Literal["reactive", "moderate", "proactive"] = "moderate"

    # Tool preferences
    preferred_test_approach: Literal["tdd", "after", "minimal"] = "after"
    patch_style: Literal["minimal", "comprehensive"] = "minimal"
    refactoring_aggressiveness: Literal["conservative", "moderate", "aggressive"] = "moderate"

    # Learned patterns
    frequently_accepted: list[str] = field(default_factory=list)
    frequently_rejected: list[str] = field(default_factory=list)

    # Behavioral scores
    likes: dict[str, float] = field(default_factory=dict)
    dislikes: dict[str, float] = field(default_factory=dict)

    # Metadata
    confidence: float = 0.5
    sample_count: int = 0


# ============================================================
# Query & Result Models
# ============================================================


@dataclass
class SimilarityQuery:
    """Query for finding similar episodes."""

    description: str | None = None
    task_type: TaskType | None = None
    files: list[str] | None = None
    error_type: str | None = None
    outcome: TaskStatus | None = None
    limit: int = 5
    min_similarity: float = 0.7


@dataclass
class ErrorObservation:
    """Input for pattern matching - observed error during execution."""

    error_type: str
    error_message: str = ""
    language: str = "python"
    framework: str | None = None
    stacktrace: str | None = None
    code_context: str | None = None

    # Lazy-computed embeddings
    message_embedding: list[float] | None = None
    stack_embedding: list[float] | None = None
    code_embedding: list[float] | None = None


@dataclass
class PatternMatch(Generic[T]):
    """Generic pattern match result."""

    pattern: T
    score: float
    matched_aspects: list[str] = field(default_factory=list)
    recommended_solution: Solution | None = None


@dataclass
class Guidance:
    """Guidance generated from memory."""

    suggested_approach: str = ""
    things_to_try: list[str] = field(default_factory=list)
    things_to_avoid: list[str] = field(default_factory=list)
    expected_challenges: list[str] = field(default_factory=list)
    estimated_complexity: Literal["low", "medium", "high"] = "medium"
    confidence: float = 0.5


# ============================================================
# Session Model
# ============================================================


@dataclass
class Session(Entity):
    """Session entity for tracking agent sessions."""

    repo_id: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None


@dataclass
class Memory(Entity):
    """Generic memory unit."""

    session_id: str = ""
    type: MemoryType = MemoryType.WORKING
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
