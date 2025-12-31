"""
Core Specs (RFC-027 Section 5)

LLM Input Contract - Fixed JSON Schema.
LLM은 이 Spec만 생성 가능합니다.

Architecture:
- Domain Layer (Pure model)
- Immutable (frozen=True)
- Type-safe (Pydantic)
- JSON Schema generation support

RFC-027 Section 5: Core Specs (LLM Input Contract)
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# ============================================================
# Scope (Common for all Specs)
# ============================================================


class Scope(BaseModel):
    """
    Scope (RFC-027 Section 5.1)

    Code snapshot scope for analysis/retrieval/edit.

    Fields:
    - repo_id: Repository identifier (e.g., "repo:123")
    - snapshot_id: Code snapshot ID (e.g., "snap:456")
    - parent_snapshot_id: Parent snapshot for incremental analysis (optional)

    Validation:
    - repo_id: non-empty, pattern "repo:xxx"
    - snapshot_id: non-empty, pattern "snap:xxx"
    - parent_snapshot_id: optional, pattern "snap:xxx"

    Incremental Mode:
    - parent_snapshot_id=None → Full analysis
    - parent_snapshot_id="snap:455" → Incremental (delta from 455 to 456)

    Example:
        # Full analysis
        Scope(
            repo_id="repo:123",
            snapshot_id="snap:456"
        )

        # Incremental analysis
        Scope(
            repo_id="repo:123",
            snapshot_id="snap:456",
            parent_snapshot_id="snap:455"
        )
    """

    repo_id: str = Field(..., min_length=1, pattern=r"^repo:[a-zA-Z0-9_-]+$", description="Repository ID")
    snapshot_id: str = Field(..., min_length=1, pattern=r"^snap:[a-zA-Z0-9_-]+$", description="Snapshot ID")
    parent_snapshot_id: str | None = Field(
        None, pattern=r"^snap:[a-zA-Z0-9_-]+$", description="Parent snapshot for incremental"
    )

    @field_validator("parent_snapshot_id")
    @classmethod
    def validate_parent_different_from_snapshot(cls, v: str | None, info) -> str | None:
        """Validate parent_snapshot_id != snapshot_id"""
        if v is None:
            return v

        snapshot_id = info.data.get("snapshot_id")
        if v == snapshot_id:
            raise ValueError(f"parent_snapshot_id must be different from snapshot_id: {v}")

        return v

    model_config = {"frozen": True}

    def is_incremental(self) -> bool:
        """Check if incremental mode"""
        return self.parent_snapshot_id is not None


# ============================================================
# RetrieveSpec (RFC-027 Section 5.1)
# ============================================================


class RetrievalMode(str, Enum):
    """
    Retrieval mode (RFC-027 Section 5.1)

    - GRAPH_GUIDED: Graph traversal (calls, imports, inheritance)
    - VECTOR: Vector similarity search
    - HYBRID: Combination (graph + vector)
    """

    GRAPH_GUIDED = "graph_guided"
    VECTOR = "vector"
    HYBRID = "hybrid"


class ExpansionPolicy(BaseModel):
    """
    Expansion policy for graph-guided retrieval (RFC-027 Section 5.1)

    Controls how to expand from seed symbols.

    Fields:
    - follow_calls: Follow function calls
    - follow_imports: Follow import statements
    - follow_inheritance: Follow class inheritance
    - max_hops: Maximum expansion hops (1-10)

    Validation:
    - max_hops: 1-10 (reasonable range)

    Example:
        ExpansionPolicy(
            follow_calls=True,
            follow_imports=True,
            follow_inheritance=False,
            max_hops=2
        )
    """

    follow_calls: bool = Field(default=True, description="Follow function calls")
    follow_imports: bool = Field(default=True, description="Follow import statements")
    follow_inheritance: bool = Field(default=True, description="Follow class inheritance")
    max_hops: int = Field(default=2, ge=1, le=10, description="Maximum expansion hops (1-10)")

    model_config = {"frozen": True}

    def is_expansive(self) -> bool:
        """Check if at least one expansion is enabled"""
        return self.follow_calls or self.follow_imports or self.follow_inheritance


class RetrieveSpec(BaseModel):
    """
    RetrieveSpec (RFC-027 Section 5.1)

    Graph-guided, incremental retrieval specification.
    LLM generates this to retrieve relevant code.

    Fields:
    - intent: Fixed "retrieve"
    - mode: Retrieval mode (graph_guided/vector/hybrid)
    - scope: Code snapshot scope
    - seed_symbols: Starting symbols (FQN list)
    - expansion_policy: How to expand from seeds
    - include_code: Include code snippets in result
    - k: Maximum results to return (1-1000)

    Validation:
    - intent: must be "retrieve"
    - seed_symbols: non-empty for graph_guided
    - k: 1-1000
    - expansion_policy: at least one expansion enabled

    Example:
        RetrieveSpec(
            intent="retrieve",
            mode=RetrievalMode.GRAPH_GUIDED,
            scope=Scope(repo_id="repo:123", snapshot_id="snap:456"),
            seed_symbols=["AuthService", "UserRepository"],
            expansion_policy=ExpansionPolicy(follow_calls=True, max_hops=2),
            include_code=True,
            k=50
        )
    """

    intent: Literal["retrieve"] = Field(default="retrieve", description="Fixed intent")
    mode: RetrievalMode = Field(default=RetrievalMode.GRAPH_GUIDED, description="Retrieval mode")
    scope: Scope = Field(..., description="Code snapshot scope")
    seed_symbols: list[str] = Field(default_factory=list, description="Starting symbols (FQN list)")
    expansion_policy: ExpansionPolicy = Field(default_factory=ExpansionPolicy, description="Expansion policy")
    include_code: bool = Field(default=True, description="Include code snippets")
    k: int = Field(default=50, ge=1, le=1000, description="Maximum results (1-1000)")

    @field_validator("seed_symbols")
    @classmethod
    def validate_seed_symbols(cls, v: list[str], info) -> list[str]:
        """Validate seed_symbols based on mode"""
        mode = info.data.get("mode")

        # graph_guided requires seeds
        if mode == RetrievalMode.GRAPH_GUIDED and not v:
            raise ValueError("seed_symbols required for graph_guided mode")

        # Validate symbol format (non-empty strings)
        for symbol in v:
            if not symbol or not symbol.strip():
                raise ValueError(f"Invalid symbol (empty): {v}")

        return v

    @field_validator("expansion_policy")
    @classmethod
    def validate_expansion_policy(cls, v: ExpansionPolicy, info) -> ExpansionPolicy:
        """Validate expansion_policy for graph_guided mode"""
        mode = info.data.get("mode")

        # graph_guided requires at least one expansion
        if mode == RetrievalMode.GRAPH_GUIDED and not v.is_expansive():
            raise ValueError("At least one expansion (follow_calls/imports/inheritance) required for graph_guided")

        return v

    model_config = {"frozen": True}


# ============================================================
# AnalyzeSpec (RFC-027 Section 5.2)
# ============================================================


class AnalysisLimits(BaseModel):
    """
    Analysis limits (RFC-027 Section 5.2)

    Controls analysis scope/timeout.

    Fields:
    - max_paths: Maximum paths to analyze (1-10000)
    - timeout_ms: Analysis timeout milliseconds (100-300000)
    - max_depth: Maximum analysis depth (1-100)

    Validation:
    - All fields: positive
    - Reasonable ranges to prevent DoS

    Example:
        AnalysisLimits(
            max_paths=200,
            timeout_ms=30000,  # 30 seconds
            max_depth=20
        )
    """

    max_paths: int = Field(default=200, ge=1, le=10000, description="Maximum paths (1-10000)")
    timeout_ms: int = Field(default=30000, ge=100, le=300000, description="Timeout milliseconds (100-300000)")
    max_depth: int = Field(default=20, ge=1, le=100, description="Maximum depth (1-100)")

    model_config = {"frozen": True}


class AnalyzeSpec(BaseModel):
    """
    AnalyzeSpec (RFC-027 Section 5.2)

    Template-based analysis specification.
    LLM generates this to run static analysis.

    Fields:
    - intent: Fixed "analyze"
    - template_id: Analysis template (e.g., "sql_injection", "null_deref")
    - scope: Code snapshot scope
    - params: Template-specific parameters (free-form)
    - limits: Analysis limits (timeout, max_paths, etc.)

    Validation:
    - intent: must be "analyze"
    - template_id: non-empty
    - params: JSON-compatible dict

    Template Examples:
    - "sql_injection": Taint analysis (SOURCE → SINK)
    - "null_deref": Null pointer dereference
    - "constant_propagation": SCCP
    - "dead_code": Unreachable code

    Example:
        AnalyzeSpec(
            intent="analyze",
            template_id="sql_injection",
            scope=Scope(repo_id="repo:123", snapshot_id="snap:456"),
            params={"severity_min": "medium"},
            limits=AnalysisLimits(max_paths=200, timeout_ms=30000)
        )
    """

    intent: Literal["analyze"] = Field(default="analyze", description="Fixed intent")
    template_id: str = Field(..., min_length=1, description="Analysis template ID")
    scope: Scope = Field(..., description="Code snapshot scope")
    params: dict[str, Any] = Field(default_factory=dict, description="Template-specific parameters")
    limits: AnalysisLimits = Field(default_factory=AnalysisLimits, description="Analysis limits")

    @field_validator("params")
    @classmethod
    def validate_params(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate params are JSON-compatible"""
        # Ensure JSON serializable
        import json

        try:
            json.dumps(v)
        except (TypeError, ValueError) as e:
            raise ValueError(f"params must be JSON-serializable: {e}")

        return v

    model_config = {"frozen": True}


# ============================================================
# EditSpec (RFC-027 Section 5.3)
# ============================================================


class EditOperationType(str, Enum):
    """
    Edit operation types (RFC-027 Section 5.3)

    Safe, automated refactoring operations.

    - RENAME_SYMBOL: Rename function/class/variable
    - ADD_PARAMETER: Add function parameter
    - REMOVE_PARAMETER: Remove function parameter
    - CHANGE_RETURN_TYPE: Change function return type
    - EXTRACT_FUNCTION: Extract code into function
    - INLINE_FUNCTION: Inline function body

    Note: Dangerous operations (DELETE_FUNCTION, MODIFY_BODY) are NOT included.
    """

    RENAME_SYMBOL = "rename_symbol"
    ADD_PARAMETER = "add_parameter"
    REMOVE_PARAMETER = "remove_parameter"
    CHANGE_RETURN_TYPE = "change_return_type"
    EXTRACT_FUNCTION = "extract_function"
    INLINE_FUNCTION = "inline_function"


class EditOperation(BaseModel):
    """
    Edit operation (RFC-027 Section 5.3)

    Single atomic edit operation.

    Fields:
    - type: Operation type (rename/add_param/etc.)
    - target: Symbol FQN (e.g., "module.ClassName.method_name")
    - params: Operation-specific parameters

    Validation:
    - target: non-empty, reasonable FQN format
    - params: JSON-compatible

    Example:
        # Rename
        EditOperation(
            type=EditOperationType.RENAME_SYMBOL,
            target="auth.AuthService.login",
            params={"new_name": "authenticate"}
        )

        # Add parameter
        EditOperation(
            type=EditOperationType.ADD_PARAMETER,
            target="auth.AuthService.login",
            params={"name": "timeout", "type": "int", "default": "30"}
        )
    """

    type: EditOperationType = Field(..., description="Operation type")
    target: str = Field(..., min_length=1, description="Symbol FQN")
    params: dict[str, Any] = Field(default_factory=dict, description="Operation-specific parameters")

    @field_validator("target")
    @classmethod
    def validate_target_fqn(cls, v: str) -> str:
        """Validate target is reasonable FQN format"""
        # Basic validation: no whitespace, contains dot
        if " " in v or "\t" in v or "\n" in v:
            raise ValueError(f"target FQN cannot contain whitespace: {v}")

        # FQN should have at least one component
        if not v or v == ".":
            raise ValueError(f"target FQN is empty or invalid: {v}")

        return v

    @field_validator("params")
    @classmethod
    def validate_params(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate params are JSON-compatible"""
        import json

        try:
            json.dumps(v)
        except (TypeError, ValueError) as e:
            raise ValueError(f"params must be JSON-serializable: {e}")

        return v

    model_config = {"frozen": True}


class EditConstraints(BaseModel):
    """
    Edit constraints (RFC-027 Section 5.3)

    Safety constraints for edit operations.

    Fields:
    - max_files: Maximum files to modify (1-1000)
    - forbidden_paths: Paths that cannot be modified (security)
    - require_tests: Require tests to pass before applying

    Validation:
    - max_files: 1-1000
    - forbidden_paths: path traversal prevention

    Example:
        EditConstraints(
            max_files=10,
            forbidden_paths=["/core/payment/*", "/security/*"],
            require_tests=True
        )
    """

    max_files: int = Field(default=10, ge=1, le=1000, description="Maximum files to modify (1-1000)")
    forbidden_paths: list[str] = Field(default_factory=list, description="Forbidden paths (glob patterns)")
    require_tests: bool = Field(default=False, description="Require tests to pass")

    @field_validator("forbidden_paths")
    @classmethod
    def validate_forbidden_paths(cls, v: list[str]) -> list[str]:
        """Validate forbidden_paths (security)"""
        for path in v:
            # Path traversal prevention
            if ".." in path:
                raise ValueError(f"Path traversal detected in forbidden_paths: {path}")

            # No empty paths
            if not path or not path.strip():
                raise ValueError(f"Empty path in forbidden_paths: {v}")

        return v

    model_config = {"frozen": True}


class EditSpec(BaseModel):
    """
    EditSpec (RFC-027 Section 5.3)

    Atomic, speculative edit specification.
    LLM generates this to perform safe refactoring.

    Fields:
    - intent: Fixed "edit"
    - transaction_id: Transaction identifier (for rollback)
    - atomic: All operations succeed or all fail
    - dry_run: Simulate without applying (default: True)
    - operations: List of edit operations
    - constraints: Safety constraints

    Validation:
    - intent: must be "edit"
    - transaction_id: non-empty
    - operations: non-empty (at least one operation)
    - constraints: forbidden_paths checked

    Safety:
    - dry_run=True by default (simulate first)
    - atomic=True ensures consistency
    - constraints prevent dangerous edits

    Example:
        EditSpec(
            intent="edit",
            transaction_id="txn_001",
            atomic=True,
            dry_run=True,
            operations=[
                EditOperation(
                    type=EditOperationType.RENAME_SYMBOL,
                    target="auth.AuthService.login",
                    params={"new_name": "authenticate"}
                )
            ],
            constraints=EditConstraints(
                max_files=10,
                forbidden_paths=["/core/payment/*"]
            )
        )
    """

    intent: Literal["edit"] = Field(default="edit", description="Fixed intent")
    transaction_id: str = Field(..., min_length=1, description="Transaction ID")
    scope: Scope = Field(..., description="Code scope for IR loading")
    atomic: bool = Field(default=True, description="Atomic (all or nothing)")
    dry_run: bool = Field(default=True, description="Simulate without applying")
    operations: list[EditOperation] = Field(..., min_length=1, description="Edit operations")
    constraints: EditConstraints = Field(default_factory=EditConstraints, description="Safety constraints")

    @field_validator("operations")
    @classmethod
    def validate_operations(cls, v: list[EditOperation]) -> list[EditOperation]:
        """Validate operations are non-empty and unique targets"""
        if not v:
            raise ValueError("operations cannot be empty (at least one required)")

        # Check for duplicate targets (same symbol edited twice)
        targets = [op.target for op in v]
        if len(targets) != len(set(targets)):
            # Find duplicates
            seen = set()
            dupes = [x for x in targets if x in seen or seen.add(x)]
            raise ValueError(f"Duplicate targets in operations: {dupes}")

        return v

    model_config = {"frozen": True}


# ============================================================
# Spec Union (for API)
# ============================================================


SpecUnion = RetrieveSpec | AnalyzeSpec | EditSpec
"""Union type for all specs (for API input)"""


# ============================================================
# Spec Validation Helpers
# ============================================================


def validate_spec_intent(spec: SpecUnion) -> None:
    """
    Validate spec intent matches type

    Args:
        spec: Spec to validate

    Raises:
        ValueError: If intent doesn't match type

    Usage:
        spec = parse_spec(json_data)
        validate_spec_intent(spec)  # Ensures consistency
    """
    if isinstance(spec, RetrieveSpec) and spec.intent != "retrieve":
        raise ValueError(f"RetrieveSpec must have intent='retrieve', got '{spec.intent}'")

    if isinstance(spec, AnalyzeSpec) and spec.intent != "analyze":
        raise ValueError(f"AnalyzeSpec must have intent='analyze', got '{spec.intent}'")

    if isinstance(spec, EditSpec) and spec.intent != "edit":
        raise ValueError(f"EditSpec must have intent='edit', got '{spec.intent}'")


def parse_spec(data: dict[str, Any]) -> SpecUnion:
    """
    Parse JSON to Spec

    Args:
        data: JSON dict

    Returns:
        Parsed spec (RetrieveSpec/AnalyzeSpec/EditSpec)

    Raises:
        ValueError: If intent unknown or validation fails

    Usage:
        json_data = {"intent": "retrieve", ...}
        spec = parse_spec(json_data)

        if isinstance(spec, RetrieveSpec):
            # Handle retrieve
            ...
    """
    intent = data.get("intent")

    if intent == "retrieve":
        return RetrieveSpec(**data)
    elif intent == "analyze":
        return AnalyzeSpec(**data)
    elif intent == "edit":
        return EditSpec(**data)
    else:
        raise ValueError(f"Unknown intent: {intent} (expected: retrieve/analyze/edit)")


def to_json_schema(spec_type: type[BaseModel]) -> dict[str, Any]:
    """
    Generate JSON Schema for spec

    Args:
        spec_type: Spec class (RetrieveSpec/AnalyzeSpec/EditSpec)

    Returns:
        JSON Schema dict

    Usage:
        schema = to_json_schema(RetrieveSpec)
        # LLM can use this schema to generate valid specs
    """
    return spec_type.model_json_schema()
