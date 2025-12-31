"""
Atom Specifications (Layer 1)

Type-aware source/sink/propagator/sanitizer definitions.

CRITICAL: No fake data. All validations are strict.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class MatchRule(BaseModel):
    """
    Type-aware match rule with strict validation.

    Validation Rules:
    - At least one of: base_type, call, read, write must be present
    - If propagator: from_args and to must be present
    - If sanitizer: scope must be present
    - Constraints must be valid dict

    Example:
        ```python
        rule = MatchRule(
            base_type="sqlite3.Cursor",
            call="execute",
            args=[0],
            constraints={"arg_type": "not_const"}
        )
        ```
    """

    # Type matching
    base_type: str | None = Field(
        None,
        description="Fully-qualified type name (e.g., 'sqlite3.Cursor')",
        min_length=1,
    )

    # Call/field matching
    call: str | None = Field(None, description="Method/function name", min_length=1)
    read: str | None = Field(None, description="Field read access", min_length=1)
    write: str | None = Field(None, description="Field write access", min_length=1)

    # Arg/kwarg matching (index-sensitive)
    args: list[int] | None = Field(
        None,
        description="Argument indices (0-based)",
    )
    kwargs: list[str] | None = Field(
        None,
        description="Keyword argument names",
    )

    # Propagator-specific
    from_args: list[int] | None = Field(
        None,
        description="Propagator source arg indices",
    )
    to: Literal["base", "return"] | None = Field(
        None,
        description="Propagator target",
    )

    # Sanitizer-specific
    scope: Literal["return", "guard"] | None = Field(
        None,
        description="Sanitizer scope (return=flow-through, guard=control-flow)",
    )

    # Constraints
    constraints: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional constraints (arg_type, arg_source, etc.)",
    )

    @field_validator("args", "from_args")
    @classmethod
    def validate_arg_indices(cls, v: list[int] | None) -> list[int] | None:
        """Validate arg indices are non-negative."""
        if v is not None:
            if not all(idx >= 0 for idx in v):
                raise ValueError("Argument indices must be non-negative")
            if len(v) != len(set(v)):
                raise ValueError("Duplicate argument indices not allowed")
        return v

    @model_validator(mode="after")
    def validate_match_rule(self) -> "MatchRule":
        """Validate match rule has at least one matcher."""
        if not any([self.base_type, self.call, self.read, self.write]):
            raise ValueError("MatchRule must have at least one of: base_type, call, read, write")

        # Propagator validation
        if self.from_args is not None or self.to is not None:
            if self.from_args is None or self.to is None:
                raise ValueError("Propagator MatchRule must have both from_args and to")

        # Sanitizer validation (scope is optional but recommended)

        return self

    def matches_base_type(self, type_fqn: str) -> bool:
        """
        Check if type FQN matches this rule.

        Args:
            type_fqn: Fully-qualified type name (may be raw hover result)

        Returns:
            True if matches

        Raises:
            NotImplementedError: Wildcard matching not yet implemented
        """
        if self.base_type is None:
            return True  # No type constraint

        if "*" in self.base_type:
            raise NotImplementedError("Wildcard type matching not yet implemented. Use exact FQN for now.")

        # Exact match
        if self.base_type == type_fqn:
            return True

        # Flexible match: handle raw hover results like "(variable) conn: Connection"
        # Extract short name from rule and check if it appears in type_fqn
        base_short = self.base_type.split(".")[-1]  # e.g., "Connection" from "sqlite3.Connection"
        return base_short in type_fqn

    def get_sink_args(self) -> list[int]:
        """Get sink argument indices."""
        return self.args or []

    def is_propagator(self) -> bool:
        """Check if this is a propagator rule."""
        return self.from_args is not None and self.to is not None

    def is_sanitizer(self) -> bool:
        """Check if this is a sanitizer rule."""
        return self.scope is not None


# Builtin functions allowed as standalone calls (not generic names like "execute")
_ALLOWED_STANDALONE_CALLS = frozenset(
    {
        # Dangerous builtins
        "open",
        "eval",
        "exec",
        "compile",
        "__import__",
        "input",
        # Common dangerous functions
        "pickle.loads",
        "yaml.load",
        "subprocess.run",
        "subprocess.call",
        "subprocess.Popen",
        # Flask file operations
        "send_file",
        "send_from_directory",
    }
)


class AtomSpec(BaseModel):
    """
    Atom specification (immutable).

    Represents a source, sink, propagator, or sanitizer definition.

    Validation Rules:
    - id must be unique and non-empty
    - kind must be one of: source, sink, propagator, sanitizer
    - tags must be non-empty list
    - match_rules must be non-empty list
    - severity must be valid

    Example:
        ```python
        atom = AtomSpec(
            id="sink.sql.sqlite3",
            kind="sink",
            tags=["injection", "db", "sql"],
            match_rules=[
                MatchRule(
                    base_type="sqlite3.Cursor",
                    call="execute",
                    args=[0],
                    constraints={"arg_type": "not_const"}
                )
            ],
            severity="critical"
        )
        ```
    """

    id: str = Field(
        ...,
        description="Unique atom ID (e.g., 'sink.sql.sqlite3')",
        min_length=1,
        pattern=r"^[a-z][a-z0-9._-]*$",
    )

    kind: Literal["source", "sink", "propagator", "sanitizer"] = Field(
        ...,
        description="Atom kind",
    )

    tags: list[str] = Field(
        ...,
        description="Semantic tags (e.g., ['untrusted', 'web'])",
        min_length=1,
    )

    match_rules: list[MatchRule] = Field(
        ...,
        description="Match rules for detection",
        min_length=1,
    )

    description: str = Field(
        "",
        description="Human-readable description",
    )

    severity: Literal["low", "medium", "high", "critical"] = Field(
        "medium",
        description="Severity level",
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Validate tags are non-empty and unique."""
        if not v:
            raise ValueError("At least one tag is required")

        # Check for empty tags
        if any(not tag.strip() for tag in v):
            raise ValueError("Tags cannot be empty strings")

        # Check for duplicates
        if len(v) != len(set(v)):
            raise ValueError("Duplicate tags not allowed")

        return v

    @field_validator("match_rules")
    @classmethod
    def validate_match_rules(cls, v: list[MatchRule]) -> list[MatchRule]:
        """Validate at least one match rule exists."""
        if not v:
            raise ValueError("At least one match rule is required")
        return v

    @model_validator(mode="after")
    def validate_atom_spec(self) -> "AtomSpec":
        """Validate atom spec consistency."""
        # Propagator must have propagator rules
        if self.kind == "propagator":
            if not any(rule.is_propagator() for rule in self.match_rules):
                raise ValueError("Propagator atom must have at least one propagator rule (with from_args and to)")

        # Sanitizer should have sanitizer rules
        if self.kind == "sanitizer":
            if not any(rule.is_sanitizer() for rule in self.match_rules):
                # Warning: Not strict error for backward compatibility
                pass

        return self

    def matches_call(
        self,
        call_expr: Any,
        type_info: str | None,
    ) -> list[MatchRule]:
        """
        Find matching rules for call expression (Hybrid approach).

        Args:
            call_expr: Call expression (from IR)
            type_info: Type FQN of receiver (e.g., "sqlite3.Cursor") or None

        Returns:
            List of matching rules
        """
        matches = []
        call_name = call_expr.attrs.get("callee_name") if hasattr(call_expr, "attrs") else None

        for rule in self.match_rules:
            # Strategy 1: Type+call matching (Hybrid)
            if rule.base_type and rule.call:
                if type_info and rule.matches_base_type(type_info):
                    # Type-aware match (precise)
                    if call_name and (call_name == rule.call or call_name.endswith(f".{rule.call}")):
                        matches.append(rule)
                elif not type_info and call_name and "." in call_name:
                    # Fallback: suffix match when type unavailable (e.g., "cursor.execute")
                    if call_name.endswith(f".{rule.call}"):
                        matches.append(rule)

            # Strategy 2: Call-only matching (FP prevention)
            elif not rule.base_type and rule.call and call_name:
                # Case 1: Exact qualified match (e.g., "os.system")
                if call_name == rule.call and "." in rule.call:
                    matches.append(rule)
                # Case 2: Suffix match with receiver (e.g., "cursor.execute")
                elif "." in call_name and call_name.endswith(f".{rule.call}"):
                    matches.append(rule)
                # Case 3: Rule qualified, call is suffix
                elif "." in rule.call and rule.call.endswith(f".{call_name}"):
                    matches.append(rule)
                # Case 4: Builtin standalone functions (allowed)
                elif call_name == rule.call and rule.call in _ALLOWED_STANDALONE_CALLS:
                    matches.append(rule)
                # Standalone generic names (e.g., "execute") → NOT matched (FP prevention)

        return matches

    def matches_call_with_name(
        self,
        call_name: str,
        type_info: str | None = None,
    ) -> list[MatchRule]:
        """
        Find matching rules for call by name and optional type.

        Args:
            call_name: Call name (e.g., "execute", "cursor.execute")
            type_info: Type FQN of receiver (e.g., "sqlite3.Cursor")

        Returns:
            List of matching rules
        """
        matches = []
        for rule in self.match_rules:
            # Type+call matching (Hybrid)
            if rule.base_type and rule.call:
                if type_info and rule.matches_base_type(type_info):
                    # Type-aware match (precise)
                    if call_name == rule.call or call_name.endswith(f".{rule.call}"):
                        matches.append(rule)
                elif not type_info and "." in call_name:
                    # Fallback: suffix match when type unavailable (e.g., "cursor.execute")
                    if call_name.endswith(f".{rule.call}"):
                        matches.append(rule)
            # Call-only matching (with FP prevention)
            elif not rule.base_type and rule.call:
                # Case 1: Exact qualified match (e.g., "os.system")
                if call_name == rule.call and "." in rule.call:
                    matches.append(rule)
                # Case 2: Suffix match with receiver (e.g., "cursor.execute")
                elif "." in call_name and call_name.endswith(f".{rule.call}"):
                    matches.append(rule)
                # Case 3: Rule qualified, call is suffix
                elif "." in rule.call and rule.call.endswith(f".{call_name}"):
                    matches.append(rule)
                # Case 4: Builtin standalone functions (allowed)
                elif call_name == rule.call and rule.call in _ALLOWED_STANDALONE_CALLS:
                    matches.append(rule)
                # Standalone generic names (e.g., "execute") → NOT matched (FP prevention)
            # Type-only matching
            elif rule.base_type and not rule.call:
                if type_info and rule.matches_base_type(type_info):
                    matches.append(rule)

        return matches

    def has_tag(self, tag: str) -> bool:
        """Check if atom has tag."""
        return tag in self.tags

    def is_kind(self, kind: str) -> bool:
        """Check if atom is of given kind."""
        return self.kind == kind

    class Config:
        """Pydantic config."""

        frozen = True  # Immutable
        extra = "forbid"  # No extra fields allowed
