"""
Taint Analysis Domain Models

Entities and Value Objects for taint analysis.

CRITICAL: No fake data. All models are validated.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .atoms import MatchRule


class DetectedAtom(BaseModel):
    """
    Lightweight detected atom for simple taint flow analysis.

    Simpler than DetectedEntity - used for service-level orchestration.

    Attributes:
        atom_id: ID of the matched atom spec
        location: Source location string (e.g., "file.py:10:4")
        confidence: Match confidence (0.0-1.0)
        tags: Tags from matched atom
        match_rule: Matched rule (for name extraction) 🔥 NEW
        entity_id: Entity ID (optional) 🔥 NEW
        entity_type: Entity type (optional) 🔥 NEW
        severity: Severity (optional) 🔥 NEW
    """

    atom_id: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    match_rule: Any | None = Field(default=None)  # 🔥 NEW
    entity_id: str = Field(default="")
    entity_type: str = Field(default="")
    severity: str = Field(default="medium")

    model_config = ConfigDict(frozen=True)


class DetectedEntity(BaseModel):
    """Base class for detected entities (detailed version)."""

    atom_id: str = Field(..., min_length=1)
    entity_id: str = Field(..., min_length=1)
    entity_type: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    severity: str = Field(..., min_length=1)
    location: dict[str, Any] = Field(default_factory=dict)
    match_rule: MatchRule

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate location has required fields."""
        # Location must have at least file_path and line
        if v and ("file_path" not in v or "line" not in v):
            raise ValueError("Location must have 'file_path' and 'line' fields")
        return v

    model_config = ConfigDict(frozen=True)


class DetectedSource(DetectedEntity):
    """
    Detected source entity.

    Represents a taint source found in code.

    Example:
        ```python
        source = DetectedSource(
            atom_id="input.http.flask",
            entity_id="var_123",
            entity_type="variable",
            tags=["untrusted", "web"],
            severity="high",
            location={
                "file_path": "app.py",
                "line": 15,
                "column": 4,
            },
            match_rule=MatchRule(...)
        )
        ```
    """

    pass


class DetectedSink(DetectedEntity):
    """
    Detected sink entity.

    Represents a taint sink found in code.

    Additional field:
        matched_arg_indices: Which argument indices matched

    Example:
        ```python
        sink = DetectedSink(
            atom_id="sink.sql.sqlite3",
            entity_id="expr_456",
            entity_type="call",
            tags=["injection", "db"],
            severity="critical",
            location={
                "file_path": "app.py",
                "line": 20,
                "column": 4,
            },
            matched_arg_indices=[0],
            match_rule=MatchRule(...)
        )
        ```
    """

    matched_arg_indices: list[int] = Field(default_factory=list)

    @field_validator("matched_arg_indices")
    @classmethod
    def validate_arg_indices(cls, v: list[int]) -> list[int]:
        """Validate arg indices."""
        if any(idx < 0 for idx in v):
            raise ValueError("Argument indices must be non-negative")
        return v


class DetectedSanitizer(DetectedEntity):
    """
    Detected sanitizer entity.

    Represents a sanitizer found in code.

    Additional field:
        scope: "return" or "guard"

    Example:
        ```python
        sanitizer = DetectedSanitizer(
            atom_id="barrier.sql",
            entity_id="expr_789",
            entity_type="call",
            tags=["safety", "db"],
            severity="medium",
            location={
                "file_path": "app.py",
                "line": 18,
                "column": 4,
            },
            scope="return",
            match_rule=MatchRule(...)
        )
        ```
    """

    scope: str = Field(..., pattern=r"^(return|guard)$")


class SimpleVulnerability(BaseModel):
    """
    Lightweight vulnerability for service-level orchestration.

    Simpler than full Vulnerability model - used by TaintAnalysisService.

    Attributes:
        policy_id: ID of the policy that detected this
        severity: Severity level (low, medium, high, critical)
        source_location: Source location string
        sink_location: Sink location string
        source_atom_id: Source atom ID
        sink_atom_id: Sink atom ID
        path: Path from source to sink
        message: Human-readable message
    """

    policy_id: str = Field(..., min_length=1)
    severity: str = Field(..., pattern=r"^(low|medium|high|critical)$")
    source_location: str = Field(..., min_length=1)
    sink_location: str = Field(..., min_length=1)
    source_atom_id: str = Field(..., min_length=1)
    sink_atom_id: str = Field(..., min_length=1)
    path: list[str] = Field(default_factory=list)
    message: str = Field(default="")

    model_config = ConfigDict(frozen=True)


class TaintFlow(BaseModel):
    """
    Taint flow path (Value Object).

    Represents a path from source to sink.

    Validation Rules:
    - nodes must be non-empty
    - length must match nodes length
    - confidence must be 0.0-1.0

    Example:
        ```python
        flow = TaintFlow(
            nodes=["var_user_id", "var_query", "call_execute"],
            edges=["dfg", "dfg"],
            length=3,
            has_sanitizer=False,
            confidence=0.95,
            metadata={"distance": 3}
        )
        ```
    """

    nodes: list[str] = Field(..., min_length=1)
    edges: list[str] = Field(default_factory=list)
    length: int = Field(..., ge=1)
    has_sanitizer: bool = Field(False)
    confidence: float = Field(..., ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("length")
    @classmethod
    def validate_length(cls, v: int, info) -> int:
        """Validate length matches nodes."""
        nodes = info.data.get("nodes", [])
        if nodes and v != len(nodes):
            raise ValueError(f"Length {v} does not match nodes length {len(nodes)}")
        return v

    @field_validator("edges")
    @classmethod
    def validate_edges(cls, v: list[str], info) -> list[str]:
        """Validate edges count."""
        nodes = info.data.get("nodes", [])
        if nodes and v and len(v) != len(nodes) - 1:
            raise ValueError(f"Edges count {len(v)} should be {len(nodes) - 1} (nodes - 1)")
        return v

    model_config = ConfigDict(frozen=True)


class Vulnerability(BaseModel):
    """
    Vulnerability entity.

    Represents a detected security vulnerability.

    Validation Rules:
    - id must be valid UUID
    - policy_id must be non-empty
    - source and sink must be present
    - flow must be present
    - confidence must be 0.0-1.0
    - severity must be valid

    Example:
        ```python
        vuln = Vulnerability(
            id=uuid4(),
            policy_id="sql-injection",
            policy_name="SQL Injection",
            severity="critical",
            source=DetectedSource(...),
            sink=DetectedSink(...),
            flow=TaintFlow(...),
            confidence=0.95,
            cwe="CWE-89",
            owasp="A03:2021-Injection",
            created_at=datetime.now()
        )
        ```
    """

    id: UUID = Field(default_factory=uuid4)
    policy_id: str = Field(..., min_length=1)
    policy_name: str = Field(..., min_length=1)
    severity: str = Field(..., pattern=r"^(low|medium|high|critical)$")

    source: DetectedSource
    sink: DetectedSink
    flow: TaintFlow

    confidence: float = Field(..., ge=0.0, le=1.0)

    cwe: str | None = Field(None, pattern=r"^CWE-\d+$")
    owasp: str | None = Field(None)

    created_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to dict.

        Returns:
            Dict representation suitable for JSON

        Note:
            Pydantic models are already serializable via model_dump(),
            but this method provides explicit control over format.
        """
        return {
            "id": str(self.id),
            "policy_id": self.policy_id,
            "policy_name": self.policy_name,
            "severity": self.severity,
            "source": {
                "atom_id": self.source.atom_id,
                "location": self.source.location,
                "tags": self.source.tags,
            },
            "sink": {
                "atom_id": self.sink.atom_id,
                "location": self.sink.location,
                "tags": self.sink.tags,
                "matched_args": self.sink.matched_arg_indices,
            },
            "flow": {
                "length": self.flow.length,
                "has_sanitizer": self.flow.has_sanitizer,
                "confidence": self.flow.confidence,
            },
            "confidence": self.confidence,
            "cwe": self.cwe,
            "owasp": self.owasp,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    def get_file_path(self) -> str:
        """Get file path where vulnerability was found."""
        return self.source.location.get("file_path", "unknown")

    def get_line(self) -> int:
        """Get line number where vulnerability starts."""
        return self.source.location.get("line", 0)

    model_config = ConfigDict(extra="forbid")


class DetectedAtoms(BaseModel):
    """
    Collection of detected atoms (Value Object).

    Aggregates all detected sources, sinks, and sanitizers
    from a single analysis run.

    Supports both lightweight DetectedAtom and detailed DetectedSource/DetectedSink.

    Example:
        ```python
        detected = DetectedAtoms(
            sources=[DetectedAtom(atom_id="source.http", location="app.py:10:0", confidence=0.9)],
            sinks=[DetectedAtom(atom_id="sink.sql", location="app.py:15:4", confidence=0.9)],
            sanitizers=[]
        )
        ```
    """

    sources: list[DetectedSource | DetectedAtom] = Field(default_factory=list)
    sinks: list[DetectedSink | DetectedAtom] = Field(default_factory=list)
    sanitizers: list[DetectedSanitizer | DetectedAtom] = Field(default_factory=list)
    propagators: list[DetectedAtom] = Field(default_factory=list)

    def count_sources(self) -> int:
        """Count detected sources."""
        return len(self.sources)

    def count_sinks(self) -> int:
        """Count detected sinks."""
        return len(self.sinks)

    def count_sanitizers(self) -> int:
        """Count detected sanitizers."""
        return len(self.sanitizers)

    def get_sources_by_tag(self, tag: str) -> list[DetectedSource]:
        """Get sources with specific tag."""
        return [s for s in self.sources if tag in s.tags]

    def get_sinks_by_tag(self, tag: str) -> list[DetectedSink]:
        """Get sinks with specific tag."""
        return [s for s in self.sinks if tag in s.tags]

    # ⭐ O(1) lookup methods for performance optimization
    def get_source_by_entity_id(self, entity_id: str) -> "DetectedSource | None":
        """
        Get source by entity_id with O(1) lookup via cached index.

        Args:
            entity_id: Entity ID to search for

        Returns:
            DetectedSource if found, None otherwise
        """
        # Build index on first call (lazy initialization)
        if not hasattr(self, "_source_index"):
            object.__setattr__(self, "_source_index", {s.entity_id: s for s in self.sources if hasattr(s, "entity_id")})
        return self._source_index.get(entity_id)  # type: ignore

    def get_sink_by_entity_id(self, entity_id: str) -> "DetectedSink | None":
        """
        Get sink by entity_id with O(1) lookup via cached index.

        Args:
            entity_id: Entity ID to search for

        Returns:
            DetectedSink if found, None otherwise
        """
        # Build index on first call (lazy initialization)
        if not hasattr(self, "_sink_index"):
            object.__setattr__(self, "_sink_index", {s.entity_id: s for s in self.sinks if hasattr(s, "entity_id")})
        return self._sink_index.get(entity_id)  # type: ignore

    model_config = ConfigDict(frozen=True)
