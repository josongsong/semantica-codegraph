"""TaintRuleSpec - RFC-033 Implementation Spec.

YAML 파싱 결과 모델.
스키마 검증을 엄격하게 수행하여 YAML과 코드 간 불일치 방지.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConstraintSpec(BaseModel):
    """Semantic constraints on arguments/kwargs.

    Strict validation: 알려지지 않은 필드는 거부됨.

    Examples:
        - arg_type: not_const
        - kwarg_shell: true
        - arg_pattern: "^SELECT.*"
    """

    model_config = ConfigDict(extra="forbid")  # 알려지지 않은 필드 거부

    # Argument type constraints
    arg_type: (
        Literal[
            "const",
            "not_const",
            "const_string",
            "string",
            "int",
            "any",
        ]
        | None
    ) = None

    # Argument count constraint
    arg_count: int | None = None

    # Argument value constraints
    arg_value: list[str] | None = None
    arg_pattern: str | None = None  # Regex pattern
    arg_min_length: int | None = None
    arg_max_length: int | None = None

    # Has params (e.g., parameterized query)
    has_params: bool | None = None

    # Kwarg constraints
    kwarg_shell: bool | None = None  # shell=True dangerous
    kwarg_check_hostname: bool | None = None  # check_hostname=False
    kwarg_verify: bool | None = None  # verify=False (SSL)


class MatchClauseSpec(BaseModel):
    """Single matching clause (OR-able).

    RFC-033 Section 2-2.
    Strict validation: 알려지지 않은 필드는 거부됨.

    At least one of: base_type, base_type_pattern, call, call_pattern, read
    """

    model_config = ConfigDict(extra="forbid")  # 알려지지 않은 필드 거부

    # Type matching (exclusive with pattern)
    base_type: str | None = Field(
        None,
        description="Exact type match: 'sqlite3.Cursor'",
    )
    base_type_pattern: str | None = Field(
        None,
        description="Wildcard type match: '*.Cursor', '*mongo*'",
    )

    # Call matching (exclusive with pattern)
    call: str | None = Field(
        None,
        description="Exact call match: 'execute'",
    )
    call_pattern: str | None = Field(
        None,
        description="Wildcard call match: 'execute*'",
    )

    # Property access (HTTP sources)
    read: str | None = Field(
        None,
        description="Property read: 'GET', 'POST', 'args'",
    )

    # Property write (attribute assignment sinks)
    write: str | None = Field(
        None,
        description="Property write: 'innerHTML', 'CommandText'",
    )

    # Taint flow positions
    args: list[int] = Field(
        default_factory=list,
        description="Which args are tainted: [0, 1]",
    )
    kwargs: list[str] = Field(
        default_factory=list,
        description="Which kwargs are tainted: ['password', 'key']",
    )

    # Propagator-specific
    from_args: list[int] = Field(
        default_factory=list,
        description="Taint source args for propagators",
    )
    to: Literal["return", "base", "arg0", "arg1", "arg2"] | None = Field(
        None,
        description="Taint destination for propagators",
    )

    # Sanitizer-specific
    scope: Literal["return", "base", "all", "guard"] | None = Field(
        None,
        description="Sanitizer scope (guard = authorization check)",
    )

    # Semantic constraints
    constraints: ConstraintSpec | None = Field(
        None,
        description="Semantic constraints on args/kwargs",
    )

    # Optional specificity override
    specificity_score: float | None = Field(
        None,
        description="Manual specificity override",
    )

    @model_validator(mode="after")
    def validate_clause(self) -> "MatchClauseSpec":
        """Validate at least one match field.

        RFC-033 Requirement: At least one of base_type, call, read must be present.
        """
        if not any(
            [
                self.base_type,
                self.base_type_pattern,
                self.call,
                self.call_pattern,
                self.read,
                self.write,
            ]
        ):
            raise ValueError(
                "At least one match field required: base_type, base_type_pattern, call, call_pattern, read, or write"
            )

        # Mutual exclusivity checks
        if self.base_type and self.base_type_pattern:
            raise ValueError("Cannot specify both base_type and base_type_pattern")

        if self.call and self.call_pattern:
            raise ValueError("Cannot specify both call and call_pattern")

        return self


class TaintRuleSpec(BaseModel):
    """Rule specification from YAML.

    RFC-033 Section 2-1.
    Strict validation: 모든 메타데이터 필드를 명시적으로 정의.

    One TaintRuleSpec per atom, with multiple match clauses.
    Each match clause will be compiled to a separate TaintRuleExecIR.

    Note: tier is NOT in YAML, but inferred by compiler:
        - tier1: exact matches (base_type + call)
        - tier2: wildcard matches (*.Cursor)
        - tier3: fallback (broad patterns)
    """

    model_config = ConfigDict(extra="forbid")  # 알려지지 않은 필드 거부

    # Core identity (from YAML 'id' field)
    rule_id: str = Field(
        ...,
        description="Unique rule ID (same as atom_id for atoms.yaml)",
    )

    atom_id: str = Field(
        ...,
        description="Atom ID (same as rule_id for atoms.yaml)",
    )

    # Atom kind
    kind: Literal["source", "sink", "sanitizer", "propagator", "passthrough"] = Field(
        ...,
        description="Taint atom kind",
    )

    # Match clauses (OR semantics)
    match: list[MatchClauseSpec] = Field(
        ...,
        min_length=1,
        description="Match clauses (OR combined)",
    )

    # === Security Metadata (CWE/OWASP) ===
    cwe: list[str] = Field(
        default_factory=list,
        description="CWE identifiers: ['CWE-89', 'CWE-78']",
    )

    owasp: str | None = Field(
        None,
        description="OWASP category: 'A03:2021-Injection'",
    )

    # === Applicability ===
    frameworks: list[str] = Field(
        default_factory=list,
        description="Applicable frameworks: ['django', 'flask']",
    )

    # === Severity & Tags ===
    severity: Literal["low", "medium", "high", "critical"] | None = Field(
        None,
        description="Vulnerability severity (for sinks)",
    )

    tags: list[str] = Field(
        default_factory=list,
        description="Tags: untrusted, web, sql, etc.",
    )

    description: str = Field(
        default="",
        description="Human-readable description",
    )

    # === Sanitizer-specific ===
    scope: Literal["return", "base", "all", "guard"] | None = Field(
        None,
        description="Sanitizer scope at rule level (guard = authorization check)",
    )

    # Priority (for tie-breaking)
    atom_priority: Literal["low", "normal", "high"] = Field(
        default="normal",
        description="Priority: low=10, normal=50, high=90",
    )

    # User metadata (extensible) - dict[str, Any] for flexibility
    user_metadata: dict[str, str] = Field(
        default_factory=dict,
        description="User-defined metadata",
    )

    @model_validator(mode="after")
    def validate_spec(self) -> "TaintRuleSpec":
        """Validate TaintRuleSpec.

        RFC-033 Requirements:
        - At least one match clause
        - severity required for sinks
        - CWE recommended for sinks (warning only)
        """
        if not self.match:
            raise ValueError("At least one match clause required")

        if self.kind == "sink" and not self.severity:
            # Default to medium for sinks
            self.severity = "medium"

        return self
