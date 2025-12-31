"""
RequestAuditLog Model (RFC-027 Section 9.1)

Stores everything needed to replay a request.

Architecture:
- Domain Layer (Pure model)
- Immutable (frozen=True)
- Type-safe (Pydantic)

RFC-027 Section 9.1: Stored Per Request
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class RequestAuditLog(BaseModel):
    """
    RequestAuditLog (RFC-027 Section 9.1)

    Everything needed to replay a request for determinism verification.

    Fields:
    - request_id: Request ID (unique)
    - input_spec: Original spec from LLM
    - resolved_spec: Resolved spec (after defaults applied)
    - engine_versions: Engine versions (for reproducibility)
    - index_digests: Index checksums (for cache validation)
    - llm_decisions: LLM decisions (bias trace)
    - tool_trace: Tool execution trace
    - outputs: Analysis outputs
    - timestamp: When executed
    - duration_ms: Execution time

    Validation:
    - request_id: non-empty, pattern "req_xxx"
    - duration_ms: >= 0
    - timestamp: valid datetime

    Example:
        RequestAuditLog(
            request_id="req_abc123",
            input_spec={"intent": "analyze", ...},
            resolved_spec={"intent": "analyze", ...},
            engine_versions={"sccp": "1.0.0", "taint": "3.0.0"},
            index_digests={"chunk_index": "sha256:abc..."},
            outputs={"claims": 2, "evidences": 2},
            timestamp=datetime.now(),
            duration_ms=234.5
        )
    """

    request_id: str = Field(..., min_length=1, pattern=r"^req_[a-zA-Z0-9_-]+$", description="Request ID")

    # Specs
    input_spec: dict[str, Any] = Field(..., description="Original input spec")
    resolved_spec: dict[str, Any] = Field(..., description="Resolved spec (with defaults)")

    # Engine state
    engine_versions: dict[str, str] = Field(default_factory=dict, description="Engine versions")
    index_digests: dict[str, str] = Field(default_factory=dict, description="Index checksums")

    # Traces
    llm_decisions: list[dict[str, Any]] = Field(default_factory=list, description="LLM decisions (bias trace)")
    tool_trace: list[dict[str, Any]] = Field(default_factory=list, description="Tool execution trace")

    # Output
    outputs: dict[str, Any] = Field(default_factory=dict, description="Analysis outputs")

    # Metadata
    timestamp: datetime = Field(..., description="Execution timestamp")
    duration_ms: float = Field(..., ge=0.0, description="Execution time (milliseconds)")

    @field_validator("engine_versions")
    @classmethod
    def validate_engine_versions(cls, v: dict[str, str]) -> dict[str, str]:
        """Validate engine versions are valid"""
        for engine, version in v.items():
            if not engine or not version:
                raise ValueError(f"Empty engine or version: {engine}={version}")
        return v

    model_config = {"frozen": True}

    def to_replay_entry(self) -> dict[str, Any]:
        """
        Convert to replay entry (for API response)

        Returns:
            Dict with replay-essential fields only

        Example:
            >>> log.to_replay_entry()
            {
                "request_id": "req_abc123",
                "input_spec": {...},
                "engine_versions": {...},
                "timestamp": "2025-12-16T10:30:00"
            }
        """
        return {
            "request_id": self.request_id,
            "input_spec": self.input_spec,
            "resolved_spec": self.resolved_spec,
            "engine_versions": self.engine_versions,
            "index_digests": self.index_digests,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
        }
