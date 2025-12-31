"""
Policy Domain Models

Policies define security rules using WHEN/FLOWS/BLOCK grammar.
Immutable value objects with strict Pydantic validation.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PolicyCondition(BaseModel):
    """
    Policy condition (WHEN clause).

    Specifies which atoms to consider as sources.

    Formats:
    - tag: untrusted → Match atoms with 'untrusted' tag
    - id: input.http.* → Match atoms by ID pattern
    - kind: source → Match atoms by kind

    Example:
        ```yaml
        WHEN:
          tag: untrusted
        ```
    """

    tag: str | None = Field(None, min_length=1, description="Tag to match")
    id: str | None = Field(None, min_length=1, description="Atom ID to match")
    kind: Literal["source", "sink", "propagator", "sanitizer"] | None = Field(
        None,
        description="Atom kind to match",
    )

    @model_validator(mode="after")
    def validate_one_condition(self) -> "PolicyCondition":
        """Must have exactly one condition"""
        conditions = [self.tag, self.id, self.kind]
        non_none = [c for c in conditions if c is not None]

        if len(non_none) != 1:
            raise ValueError("PolicyCondition must have exactly one of: tag, id, kind")

        return self

    def matches(self, atom: Any) -> bool:
        """
        Check if atom matches condition.

        Args:
            atom: AtomSpec to check

        Returns:
            True if matches
        """
        if self.tag:
            return atom.has_tag(self.tag)

        if self.id:
            # Simple prefix match for now
            # TODO: Support wildcards in Phase 2.5
            return atom.id.startswith(self.id.rstrip("*"))

        if self.kind:
            return atom.kind == self.kind

        return False

    class Config:
        """Pydantic config"""

        frozen = True
        extra = "forbid"


class PolicyFlow(BaseModel):
    """
    Policy flow (FLOWS clause).

    Specifies which atoms to consider as sinks.

    Example:
        ```yaml
        FLOWS:
          - id: sink.sql.sqlite3
          - id: sink.sql.psycopg2
        ```
    """

    id: str | None = Field(None, min_length=1, description="Atom ID")
    tag: str | None = Field(None, min_length=1, description="Tag to match")

    @model_validator(mode="after")
    def validate_one_field(self) -> "PolicyFlow":
        """Must have exactly one field"""
        if self.id is None and self.tag is None:
            raise ValueError("PolicyFlow must have either 'id' or 'tag'")

        if self.id is not None and self.tag is not None:
            raise ValueError("PolicyFlow must have only one of: id, tag")

        return self

    def matches(self, atom: Any) -> bool:
        """Check if atom matches flow"""
        if self.id:
            return atom.id.startswith(self.id.rstrip("*"))

        if self.tag:
            return atom.has_tag(self.tag)

        return False

    class Config:
        """Pydantic config"""

        frozen = True
        extra = "forbid"


class PolicyBlockCondition(BaseModel):
    """
    Block condition inside UNLESS.

    Specifies which sanitizers block taint flow.

    Example:
        ```yaml
        kind: sanitizer
        tag: sql
        ```
    """

    kind: Literal["sanitizer"] | None = Field(None, description="Must be sanitizer")
    tag: str | None = Field(None, min_length=1, description="Tag to match")
    id: str | None = Field(None, min_length=1, description="Atom ID")

    @model_validator(mode="after")
    def validate_block_condition(self) -> "PolicyBlockCondition":
        """Validate block has at least one field"""
        if self.kind is None and self.tag is None and self.id is None:
            raise ValueError("PolicyBlockCondition must have at least one of: kind, tag, id")

        return self

    def matches(self, atom: Any) -> bool:
        """Check if atom matches block"""
        if self.kind and atom.kind != self.kind:
            return False

        if self.tag and not atom.has_tag(self.tag):
            return False

        if self.id and not atom.id.startswith(self.id.rstrip("*")):
            return False

        return True

    class Config:
        """Pydantic config"""

        frozen = True
        extra = "forbid"


class PolicyBlock(BaseModel):
    """
    Policy block (BLOCK clause).

    Specifies sanitizers that block taint flow.

    Example:
        ```yaml
        BLOCK:
          UNLESS:
            kind: sanitizer
            tag: sql
        ```
    """

    UNLESS: PolicyBlockCondition = Field(..., description="Sanitizer condition")

    def matches(self, atom: Any) -> bool:
        """Check if atom matches block"""
        return self.UNLESS.matches(atom)

    class Config:
        """Pydantic config"""

        frozen = True
        extra = "forbid"


class PolicyGrammar(BaseModel):
    """
    Policy grammar (WHEN/FLOWS/BLOCK).

    Defines the taint analysis rule using declarative grammar.

    Validation Rules:
    - WHEN: required, single condition
    - FLOWS: required, 1+ flows
    - BLOCK: optional

    Example:
        ```yaml
        grammar:
          WHEN:
            tag: untrusted
          FLOWS:
            - id: sink.sql.sqlite3
            - id: sink.sql.psycopg2
          BLOCK:
            UNLESS:
              kind: sanitizer
              tag: sql
        ```
    """

    WHEN: PolicyCondition = Field(..., description="Source condition")
    FLOWS: list[PolicyFlow] = Field(
        ...,
        min_length=1,
        description="Sink flows (1+)",
    )
    BLOCK: PolicyBlock | None = Field(
        None,
        description="Sanitizer block (optional)",
    )

    @field_validator("FLOWS")
    @classmethod
    def validate_flows(cls, v: list[PolicyFlow]) -> list[PolicyFlow]:
        """Validate flows"""
        if not v:
            raise ValueError("FLOWS must have at least one flow")
        return v

    class Config:
        """Pydantic config"""

        frozen = True
        extra = "forbid"


class Policy(BaseModel):
    """
    Security Policy (Immutable).

    Represents a security rule for taint analysis.

    Validation Rules:
    - id: unique, lowercase, dot-separated
    - name: non-empty
    - severity: low|medium|high|critical
    - grammar: valid WHEN/FLOWS/BLOCK
    - cwe: optional, CWE-XXX format (e.g., CWE-89)
    - owasp: optional
    - tags: optional, list of category tags

    Example:
        ```yaml
        - id: "sql-injection"
          name: "SQL Injection"
          severity: critical
          tags: ["injection", "database", "sql"]
          cwe: "CWE-89"
          owasp: "A03:2021-Injection"
          grammar:
            WHEN:
              tag: untrusted
            FLOWS:
              - id: sink.sql.sqlite3
            BLOCK:
              UNLESS:
                kind: sanitizer
                tag: sql
        ```
    """

    id: str = Field(
        ...,
        min_length=1,
        description="Unique policy ID",
        pattern=r"^[a-z][a-z0-9\-]*$",
    )

    name: str = Field(..., min_length=1, description="Human-readable name")

    severity: Literal["low", "medium", "high", "critical"] = Field(
        ...,
        description="Severity level",
    )

    grammar: PolicyGrammar = Field(..., description="Policy grammar")

    tags: list[str] = Field(
        default_factory=list,
        description="Policy category tags (e.g., ['injection', 'database'])",
    )

    cwe: str | None = Field(
        None,
        description="CWE identifier",
        pattern=r"^CWE-\d+$",
    )

    owasp: str | None = Field(None, description="OWASP category")

    description: str = Field("", description="Policy description")

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Validate tags are non-empty and unique."""
        # Empty tags list is okay (optional)
        if not v:
            return v

        # Check for empty tags
        if any(not tag.strip() for tag in v):
            raise ValueError("Tags cannot be empty strings")

        # Check for duplicates
        if len(v) != len(set(v)):
            raise ValueError("Duplicate tags not allowed")

        return v

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validate ID format"""
        if not v:
            raise ValueError("Policy ID cannot be empty")

        # Check format
        if not v[0].isalpha():
            raise ValueError("Policy ID must start with letter")

        if not all(c.isalnum() or c in "-_" for c in v):
            raise ValueError("Policy ID can only contain alphanumeric, dash, underscore")

        return v

    def get_source_atoms(self, all_atoms: list[Any]) -> list[Any]:
        """
        Get source atoms matching WHEN condition.

        Args:
            all_atoms: All available atoms

        Returns:
            Matching source atoms
        """
        return [atom for atom in all_atoms if self.grammar.WHEN.matches(atom)]

    def get_sink_atoms(self, all_atoms: list[Any]) -> list[Any]:
        """
        Get sink atoms matching FLOWS.

        Args:
            all_atoms: All available atoms

        Returns:
            Matching sink atoms
        """
        matches = []
        for atom in all_atoms:
            if any(flow.matches(atom) for flow in self.grammar.FLOWS):
                matches.append(atom)
        return matches

    def get_sanitizer_atoms(self, all_atoms: list[Any]) -> list[Any]:
        """
        Get sanitizer atoms matching BLOCK.

        Args:
            all_atoms: All available atoms

        Returns:
            Matching sanitizer atoms, or empty if no BLOCK
        """
        if self.grammar.BLOCK is None:
            return []

        return [atom for atom in all_atoms if self.grammar.BLOCK.matches(atom)]

    class Config:
        """Pydantic config"""

        frozen = True
        extra = "forbid"
