"""
Memory System Data Models

Defines core data structures for the 3-tier memory architecture:
- Working Memory: Current session state
- Episodic Memory: Task execution history
- Semantic Memory: Learned patterns and knowledge
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal

# ============================================================
# Common Types
# ============================================================


class TaskType(str, Enum):
    """Types of tasks the agent can perform."""

    SEARCH = "search"
    IMPLEMENT = "implement"
    IMPLEMENTATION = "implementation"  # Alias for IMPLEMENT
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


# ============================================================
# Working Memory Models
# ============================================================


@dataclass
class StepRecord:
    """Record of a single execution step."""

    id: str
    step_number: int
    tool_name: str
    tool_input: dict[str, Any]
    tool_result: Any
    success: bool
    error: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0


@dataclass
class Hypothesis:
    """A hypothesis about the problem/solution."""

    id: str
    description: str
    confidence: float  # 0.0 to 1.0
    evidence: list[str] = field(default_factory=list)
    status: Literal["active", "confirmed", "rejected"] = "active"
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Decision:
    """A decision made during execution."""

    id: str
    description: str
    rationale: str
    alternatives: list[str] = field(default_factory=list)
    accepted: bool = True
    timestamp: datetime = field(default_factory=datetime.now)
    context_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class FileState:
    """State of a file in working context."""

    path: str
    modified: bool = False
    access_count: int = 0
    last_accessed: datetime = field(default_factory=datetime.now)
    previous_state: "FileState | None" = None


@dataclass
class SymbolInfo:
    """Information about a symbol being referenced."""

    name: str
    kind: str  # function, class, variable, etc.
    file_path: str
    line_number: int


@dataclass
class Discovery:
    """Something discovered during execution."""

    description: str
    importance: Literal["low", "medium", "high"] = "medium"
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ErrorRecord:
    """Record of an error encountered."""

    step_id: str
    error: Exception
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


# ============================================================
# Episodic Memory Models
# ============================================================


@dataclass
class ToolUsageSummary:
    """Summary of tool usage."""

    tool_name: str
    call_count: int
    success_count: int
    avg_duration_ms: float


@dataclass
class Pivot:
    """A strategic change during execution."""

    step_number: int
    description: str
    reason: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class PatchSummary:
    """Summary of a code patch."""

    file_path: str
    lines_added: int
    lines_removed: int
    description: str


@dataclass
class Episode:
    """
    A complete episode of task execution.

    Stored in episodic memory for future reference.
    """

    id: str
    project_id: str
    session_id: str

    # Task information
    task_type: TaskType
    task_description: str
    task_description_embedding: list[float] = field(default_factory=list)
    task_complexity: float = 0.5  # 0.0 to 1.0

    # Context
    files_involved: list[str] = field(default_factory=list)
    symbols_involved: list[str] = field(default_factory=list)
    error_types: list[str] = field(default_factory=list)
    stack_trace_signature: str | None = None

    # Execution
    plan_summary: str = ""
    steps_count: int = 0
    tools_used: list[ToolUsageSummary] = field(default_factory=list)
    key_decisions: list[Decision] = field(default_factory=list)
    pivots: list[Pivot] = field(default_factory=list)

    # Outcome
    outcome_status: TaskStatus = TaskStatus.UNKNOWN
    patches: list[PatchSummary] = field(default_factory=list)
    tests_passed: bool = False
    user_feedback: Literal["positive", "negative", "neutral"] | None = None

    # Extracted knowledge
    problem_pattern: str = ""
    solution_pattern: str = ""
    gotchas: list[str] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0
    tokens_used: int = 0
    retrieval_count: int = 0  # How many times this episode was referenced
    usefulness_score: float = 0.5  # 0.0 to 1.0


# ============================================================
# Semantic Memory Models
# ============================================================


@dataclass
class BugPattern:
    """A learned pattern for bug detection and resolution."""

    id: str
    name: str

    # Signature
    error_types: list[str] = field(default_factory=list)
    error_message_patterns: list[str] = field(default_factory=list)  # regex patterns for boost
    stack_trace_patterns: list[str] = field(default_factory=list)  # regex patterns for boost
    code_patterns: list[str] = field(default_factory=list)

    # Context (hard filter)
    languages: list[str] = field(default_factory=list)  # python, typescript, etc.
    typical_file_types: list[str] = field(default_factory=list)
    typical_frameworks: list[str] = field(default_factory=list)  # fastapi, nestjs, etc.
    common_causes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)  # db, timeout, auth, etc.

    # Sample data (for embedding generation)
    sample_error_message: str = ""
    sample_stacktrace: str | None = None
    sample_code_snippet: str | None = None

    # Semantic embeddings (for similarity matching)
    message_embedding: list[float] | None = None
    stack_embedding: list[float] | None = None
    code_embedding: list[float] | None = None

    # Solutions
    solutions: list["Solution"] = field(default_factory=list)

    # Statistics
    occurrence_count: int = 0
    resolution_count: int = 0
    avg_resolution_time_ms: float = 0.0
    last_seen: datetime = field(default_factory=datetime.now)

    # Related patterns
    related_pattern_ids: list[str] = field(default_factory=list)


@dataclass
class Solution:
    """A solution to a bug pattern."""

    description: str
    approach: str
    code_template: str | None = None
    success_rate: float = 0.5  # 0.0 to 1.0
    applicability_conditions: list[str] = field(default_factory=list)


@dataclass
class CodePattern:
    """A learned code pattern (refactoring, optimization, etc.)."""

    id: str
    name: str
    category: str  # Extended categories: extract_method, rename, simplify, type_hints, etc.

    # Description
    description: str = ""

    # Pattern detection
    ast_pattern: str | None = None
    code_smell: str | None = None
    metrics_threshold: dict[str, float] = field(default_factory=dict)
    detection_rules: list[str] = field(default_factory=list)

    # Transformation (before/after code patterns)
    transformation_description: str = ""
    before_template: str = ""
    after_template: str = ""
    before_pattern: str | None = None  # Simplified before code sample
    after_pattern: str | None = None  # Simplified after code sample
    template_variables: list[str] = field(default_factory=list)

    # Applicability
    applicable_languages: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    contraindications: list[str] = field(default_factory=list)

    # Effects
    readability_impact: float = 0.0  # -1.0 to 1.0
    performance_impact: float = 0.0
    maintainability_impact: float = 0.0
    testability_impact: float = 0.0

    # Statistics
    application_count: int = 0
    success_rate: float = 0.5
    avg_improvement: float = 0.0


@dataclass
class ProjectKnowledge:
    """Learned knowledge about a specific project."""

    project_id: str

    # Structure
    architecture_type: str = "monolith"
    main_directories: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)

    # Conventions
    naming_conventions: dict[str, str] = field(default_factory=dict)
    file_organization: str = ""
    import_style: str = ""
    testing_patterns: list[str] = field(default_factory=list)
    documentation_style: str = ""

    # Tech stack
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    testing_frameworks: list[str] = field(default_factory=list)
    build_tools: list[str] = field(default_factory=list)

    # Hotspots
    frequently_modified: list[str] = field(default_factory=list)
    high_complexity: list[str] = field(default_factory=list)
    bug_prone: list[str] = field(default_factory=list)
    critical_paths: list[str] = field(default_factory=list)

    # Team knowledge
    common_issues: list[str] = field(default_factory=list)
    preferred_solutions: dict[str, str] = field(default_factory=dict)
    avoid_patterns: list[str] = field(default_factory=list)
    review_focus: list[str] = field(default_factory=list)

    # Statistics
    total_sessions: int = 0
    total_tasks: int = 0
    success_rate: float = 0.5
    common_task_types: dict[str, int] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class UserPreferences:
    """Learned user preferences."""

    # Coding style
    verbosity: Literal["minimal", "moderate", "detailed"] = "moderate"
    comment_style: Literal["none", "minimal", "extensive"] = "minimal"
    variable_naming: Literal["short", "descriptive"] = "descriptive"
    function_size: Literal["small", "medium", "large"] = "medium"

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
    custom_shortcuts: dict[str, str] = field(default_factory=dict)


# ============================================================
# Generalization Layer Models (RFC: Semantic Memory Learning)
# ============================================================


@dataclass
class StyleProfile:
    """
    Inferred coding style profile from repo/user code.

    Learned via AST analysis and pattern detection.
    No ML required - pure statistical inference.
    """

    # Naming conventions (detected ratios)
    naming_convention: Literal["snake_case", "camelCase", "PascalCase", "mixed"] = "snake_case"
    naming_snake_ratio: float = 0.0  # 0.0-1.0
    naming_camel_ratio: float = 0.0
    naming_pascal_ratio: float = 0.0

    # Function style
    function_length_mean: float = 15.0  # Average lines per function
    function_length_std: float = 10.0  # Standard deviation
    early_return_ratio: float = 0.0  # Ratio of functions using early return
    max_nesting_depth_mean: float = 2.0  # Average max nesting depth

    # Import style
    import_sorted: bool = False  # Whether imports are alphabetically sorted
    import_grouped: bool = False  # Whether imports are grouped (stdlib, third-party, local)
    import_alias_usage: float = 0.0  # Ratio of aliased imports

    # Type hints
    type_hint_coverage: float = 0.0  # Ratio of functions with type hints
    return_type_coverage: float = 0.0  # Ratio with return type annotations

    # Docstrings
    docstring_coverage: float = 0.0  # Ratio of functions with docstrings
    docstring_style: Literal["google", "numpy", "sphinx", "none"] = "none"

    # General patterns
    prefer_comprehensions: bool = False  # List/dict comprehensions over loops
    prefer_f_strings: bool = False  # f-strings over .format()

    # Metadata
    samples_analyzed: int = 0
    last_updated: datetime = field(default_factory=datetime.now)
    confidence: float = 0.0  # Overall confidence in profile (0.0-1.0)


@dataclass
class InteractionProfile:
    """
    Learned user interaction preferences.

    Inferred from conversation history and response patterns.
    """

    # Response preferences
    preferred_response_length: Literal["brief", "moderate", "detailed"] = "moderate"
    avg_response_tokens: float = 500.0  # Average preferred response length
    response_length_std: float = 200.0

    # Detail level
    detail_preference: Literal["summary", "balanced", "thorough"] = "balanced"
    code_to_explanation_ratio: float = 0.5  # 0=all explanation, 1=all code

    # Format preferences
    preferred_format: Literal["prose", "markdown", "code_heavy", "bullet_points"] = "markdown"
    use_tables: bool = False  # Prefers tabular data
    use_code_blocks: bool = True  # Prefers code in blocks

    # Tone
    tone: Literal["formal", "casual", "technical"] = "technical"
    use_emojis: bool = False

    # Interaction patterns
    asks_clarifying_questions: float = 0.3  # How often user asks for clarification
    requests_examples: float = 0.5  # How often user wants examples
    iterates_on_solutions: float = 0.4  # How often user refines initial solution

    # Confirmation behavior
    needs_confirmation: Literal["always", "risky_only", "rarely"] = "risky_only"

    # Metadata
    interactions_analyzed: int = 0
    last_updated: datetime = field(default_factory=datetime.now)
    confidence: float = 0.0


@dataclass
class CodeRule:
    """
    A learned code transformation rule.

    Represents a pattern like: "dict['key'] -> dict.get('key', default)"
    Learned from patches and reinforced/weakened over time.
    """

    id: str
    name: str  # Human-readable name
    description: str = ""

    # Pattern definition
    category: Literal[
        "null_safety",
        "error_handling",
        "style",
        "performance",
        "security",
        "readability",
        "other",
    ] = "other"

    # Before/After patterns (can be regex or AST pattern)
    before_pattern: str = ""  # e.g., "dict\\['(\\w+)'\\]"
    after_pattern: str = ""  # e.g., "dict.get('\\1')"
    pattern_type: Literal["regex", "ast", "literal"] = "literal"

    # Language applicability
    languages: list[str] = field(default_factory=lambda: ["python"])

    # Learning metrics
    confidence: float = 0.5  # 0.0-1.0, adjusted with each observation
    observation_count: int = 1  # Times this pattern was observed
    success_count: int = 0  # Times applying this rule led to success
    failure_count: int = 0  # Times applying this rule led to failure

    # Thresholds for lifecycle
    min_confidence_threshold: float = 0.3  # Below this, rule is removed
    promotion_threshold: float = 0.8  # Above this, rule is "trusted"

    # Examples
    examples: list[dict[str, str]] = field(default_factory=list)  # [{"before": ..., "after": ...}]

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    last_applied: datetime = field(default_factory=datetime.now)
    source_episodes: list[str] = field(default_factory=list)  # Episode IDs that contributed

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5

    @property
    def is_trusted(self) -> bool:
        """Check if rule has high enough confidence to auto-apply."""
        return self.confidence >= self.promotion_threshold

    @property
    def should_remove(self) -> bool:
        """Check if rule should be removed due to low confidence."""
        return self.confidence < self.min_confidence_threshold and self.observation_count >= 5

    def reinforce(self, success: bool, weight: float = 0.1) -> None:
        """
        Reinforce or weaken the rule based on outcome.

        Args:
            success: Whether the application was successful
            weight: Learning rate (0.0-1.0)
        """
        self.observation_count += 1
        if success:
            self.success_count += 1
            self.confidence = min(1.0, self.confidence + weight * (1.0 - self.confidence))
        else:
            self.failure_count += 1
            self.confidence = max(0.0, self.confidence - weight * self.confidence)
        self.last_applied = datetime.now()


@dataclass
class SemanticKnowledge:
    """
    Aggregated semantic knowledge container.

    Single structure holding all learned generalizations.
    Stored as lightweight JSON for persistence.
    """

    # Profiles
    style: StyleProfile = field(default_factory=StyleProfile)
    interaction: InteractionProfile = field(default_factory=InteractionProfile)

    # Rules (keyed by rule ID)
    code_rules: dict[str, CodeRule] = field(default_factory=dict)

    # Metadata
    version: str = "1.0"
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)

    def add_rule(self, rule: CodeRule) -> None:
        """Add or update a code rule."""
        self.code_rules[rule.id] = rule
        self.last_updated = datetime.now()

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a code rule by ID."""
        if rule_id in self.code_rules:
            del self.code_rules[rule_id]
            self.last_updated = datetime.now()
            return True
        return False

    def cleanup_low_confidence_rules(self) -> int:
        """Remove rules that fall below confidence threshold."""
        to_remove = [rid for rid, rule in self.code_rules.items() if rule.should_remove]
        for rid in to_remove:
            del self.code_rules[rid]
        if to_remove:
            self.last_updated = datetime.now()
        return len(to_remove)

    def get_trusted_rules(self) -> list[CodeRule]:
        """Get all rules with high confidence."""
        return [r for r in self.code_rules.values() if r.is_trusted]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to lightweight dict for storage."""
        from dataclasses import asdict

        return {
            "style": asdict(self.style),
            "interaction": asdict(self.interaction),
            "code_rules": {rid: asdict(rule) for rid, rule in self.code_rules.items()},
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }


# ============================================================
# Memory Query Models
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
    min_similarity: float = 0.7  # Minimum cosine similarity threshold


@dataclass
class ErrorObservation:
    """
    Input for pattern matching - observed error during execution.

    Contains error details and lazy-computed embeddings for semantic matching.
    """

    # Required fields
    error_type: str  # ValueError, TypeError, etc.
    error_message: str

    # Optional context
    language: str = "python"
    framework: str | None = None
    stacktrace: str | None = None
    code_context: str | None = None  # surrounding code snippet

    # Lazy-computed embeddings (filled by matcher)
    message_embedding: list[float] | None = None
    stack_embedding: list[float] | None = None
    code_embedding: list[float] | None = None


@dataclass
class BugPatternMatch:
    """A matched bug pattern with scoring details."""

    pattern: BugPattern
    score: float  # 0.0 to 1.0
    matched_aspects: list[str]
    recommended_solution: Solution | None = None

    # Score breakdown for debugging/tuning
    type_score: float = 0.0
    message_score: float = 0.0
    stack_score: float = 0.0
    code_score: float = 0.0
    regex_boost: float = 0.0


@dataclass
class Guidance:
    """Guidance generated from memory."""

    suggested_approach: str = ""
    things_to_try: list[str] = field(default_factory=list)
    things_to_avoid: list[str] = field(default_factory=list)
    expected_challenges: list[str] = field(default_factory=list)
    estimated_complexity: Literal["low", "medium", "high"] = "medium"
    confidence: float = 0.5  # 0.0 to 1.0


# ============================================================
# SOTA Memory Bucket Models (Profile/Preference/Semantic)
# ============================================================


class MemoryType(str, Enum):
    """Types of memory for routing."""

    PROFILE = "profile"  # Static user/project attributes
    PREFERENCE = "preference"  # User preferences and patterns
    EPISODIC = "episodic"  # Task execution history
    SEMANTIC = "semantic"  # Summarized knowledge/insights
    FACT = "fact"  # Individual facts (Mem0-style)
    NONE = "none"  # Should not be stored


class ImportanceLevel(str, Enum):
    """Importance level for memory retention."""

    CRITICAL = "critical"  # Always keep
    HIGH = "high"  # Keep for long time
    MEDIUM = "medium"  # Standard retention
    LOW = "low"  # Short retention
    TRIVIAL = "trivial"  # May discard


@dataclass
class MemoryEvent:
    """
    Raw event for write pipeline (SOTA pattern).

    All memory inputs go through this unified format before
    being classified and routed to appropriate buckets.
    """

    user_id: str
    project_id: str
    text: str
    source: str  # conversation, tool_result, observation, user_input
    timestamp: datetime = field(default_factory=datetime.now)
    context: dict[str, Any] = field(default_factory=dict)

    # Classification results (filled by write pipeline)
    memory_type: MemoryType = MemoryType.NONE
    importance: float = 0.5  # 0.0 to 1.0
    importance_level: ImportanceLevel = ImportanceLevel.MEDIUM


@dataclass
class UserProfile:
    """
    Profile memory bucket - static user attributes.

    SOTA pattern: Separate from preferences for stable identity.
    """

    user_id: str
    name: str | None = None
    role: str | None = None  # developer, designer, manager, etc.
    expertise_level: Literal["beginner", "intermediate", "expert"] = "intermediate"
    primary_languages: list[str] = field(default_factory=list)
    primary_frameworks: list[str] = field(default_factory=list)
    timezone: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Static facts about user
    facts: dict[str, str] = field(default_factory=dict)


@dataclass
class UserPreferenceV2:
    """
    Preference memory bucket - learned behavioral patterns.

    SOTA pattern: Separate from profile, continuously updated.
    """

    user_id: str

    # Coding style preferences
    verbosity: Literal["minimal", "moderate", "detailed"] = "moderate"
    comment_style: Literal["none", "minimal", "extensive"] = "minimal"
    variable_naming: Literal["short", "descriptive"] = "descriptive"
    function_size: Literal["small", "medium", "large"] = "medium"

    # Interaction preferences
    explanation_depth: Literal["brief", "moderate", "thorough"] = "moderate"
    confirmation_frequency: Literal["always", "important", "rarely"] = "important"
    proactivity: Literal["reactive", "moderate", "proactive"] = "moderate"

    # Tool preferences
    preferred_test_approach: Literal["tdd", "after", "minimal"] = "after"
    patch_style: Literal["minimal", "comprehensive"] = "minimal"
    refactoring_aggressiveness: Literal["conservative", "moderate", "aggressive"] = "moderate"

    # Learned patterns (SOTA: track acceptance/rejection)
    frequently_accepted: list[str] = field(default_factory=list)
    frequently_rejected: list[str] = field(default_factory=list)
    custom_shortcuts: dict[str, str] = field(default_factory=dict)

    # Behavioral scores (learned over time)
    likes: dict[str, float] = field(default_factory=dict)  # feature -> score
    dislikes: dict[str, float] = field(default_factory=dict)

    # Metadata
    confidence: float = 0.5  # How confident we are in preferences
    sample_count: int = 0  # How many interactions used to learn
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class SemanticMemory:
    """
    Semantic memory bucket - summarized knowledge/insights.

    SOTA pattern: Result of reflection over episodic memories.
    Higher-level abstractions from multiple episodes.
    """

    id: str
    project_id: str

    # Content
    title: str
    summary: str
    key_insights: list[str] = field(default_factory=list)

    # Source tracking
    source_episode_ids: list[str] = field(default_factory=list)
    source_count: int = 1

    # Classification
    category: str = "general"  # bug_pattern, code_pattern, project_insight, etc.
    tags: list[str] = field(default_factory=list)

    # Embedding for retrieval
    embedding: list[float] = field(default_factory=list)

    # Scoring (SOTA: 3-axis)
    importance: float = 0.5
    recency_score: float = 1.0  # Decays over time
    retrieval_count: int = 0

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    ttl_days: int | None = None  # Time-to-live, None = forever


@dataclass
class MemoryUnit:
    """
    Universal memory unit with full metadata (SOTA pattern).

    Minimum unit for storage/retrieval with privacy controls.
    """

    id: str
    content: str
    memory_type: MemoryType

    # Source
    source: str
    source_id: str | None = None
    user_id: str | None = None
    project_id: str | None = None

    # Scoring
    importance: float = 0.5
    recency_score: float = 1.0
    relevance_score: float = 0.0  # Computed at query time

    # Tracking
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    use_count: int = 0

    # Privacy/retention
    sensitivity: Literal["public", "private", "secret"] = "private"
    ttl_seconds: int | None = None  # None = no expiry
    deletable: bool = True

    # Embedding
    embedding: list[float] = field(default_factory=list)


@dataclass
class ReflectionResult:
    """
    Result of reflection process (Generative Agents style).

    Reflection takes multiple episodic memories and produces
    higher-level semantic memory.
    """

    semantic_memory: SemanticMemory
    source_episodes: list[str]
    reflection_prompt: str
    llm_response: str
    confidence: float = 0.5
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class MemoryScore:
    """
    Composite score for memory retrieval (SOTA 3-axis).

    score = w_sim * similarity + w_rec * recency + w_imp * importance
    """

    memory_id: str
    similarity: float = 0.0  # Embedding similarity
    recency: float = 0.0  # Time decay
    importance: float = 0.0  # Stored importance

    # Weights (configurable)
    w_similarity: float = 0.5
    w_recency: float = 0.3
    w_importance: float = 0.2

    @property
    def composite_score(self) -> float:
        """Compute weighted composite score."""
        return self.w_similarity * self.similarity + self.w_recency * self.recency + self.w_importance * self.importance


@dataclass
class MemoryQueryResult:
    """Result of memory query with scoring details."""

    memories: list[MemoryUnit]
    scores: list[MemoryScore]
    query_type: MemoryType | None = None
    total_candidates: int = 0
    retrieval_time_ms: float = 0.0
