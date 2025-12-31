"""
Evidence Models - Proof of Analysis Results

RFC-052: MCP Service Layer Architecture
All high-level analysis results must have evidence.

Design Principles:
- Evidence is immutable once created
- Evidence has stable ID (for referencing)
- Evidence expires based on snapshot lifecycle
- Evidence can be retrieved separately (not inline in responses)

Evidence Types:
- taint_flow: Taint analysis path
- slice: Program slice
- dataflow: Dataflow path
- impact: Impact analysis result
- type_inference: Type constraint proof
- fix_verification: AutoFix verification result
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class EvidenceKind(str, Enum):
    """Types of evidence"""

    TAINT_FLOW = "taint_flow"
    SLICE = "slice"
    DATAFLOW = "dataflow"
    IMPACT = "impact"
    TYPE_INFERENCE = "type_inference"
    FIX_VERIFICATION = "fix_verification"
    CALL_CHAIN = "call_chain"
    DATA_DEPENDENCY = "data_dependency"


@dataclass(frozen=True)
class GraphRefs:
    """
    References to graph elements.

    Used for replay and validation.
    """

    node_ids: tuple[str, ...] = field(default_factory=tuple)
    edge_ids: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_ids": list(self.node_ids),
            "edge_ids": list(self.edge_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphRefs:
        return cls(
            node_ids=tuple(data.get("node_ids", [])),
            edge_ids=tuple(data.get("edge_ids", [])),
        )


@dataclass
class Evidence:
    """
    Evidence of analysis result.

    Immutable proof that can be stored and retrieved.
    """

    evidence_id: str  # Stable ID (e.g., "ev_abc123")
    kind: EvidenceKind
    snapshot_id: str  # Which snapshot this evidence is based on

    # Graph references (for replay)
    graph_refs: GraphRefs

    # Analysis details
    constraint_summary: str | None = None  # Human-readable constraint summary
    rule_id: str | None = None  # Which rule triggered this
    rule_hash: str | None = None  # Rule version hash
    solver_trace_ref: str | None = None  # Reference to detailed solver trace (optional)

    # Metadata
    plan_hash: str | None = None  # QueryPlan hash that generated this
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None  # None = follows snapshot lifecycle

    # Additional data (kind-specific)
    extra_data: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if evidence is expired"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict"""
        return {
            "evidence_id": self.evidence_id,
            "kind": self.kind.value,
            "snapshot_id": self.snapshot_id,
            "graph_refs": self.graph_refs.to_dict(),
            "constraint_summary": self.constraint_summary,
            "rule_id": self.rule_id,
            "rule_hash": self.rule_hash,
            "solver_trace_ref": self.solver_trace_ref,
            "plan_hash": self.plan_hash,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "extra_data": self.extra_data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Evidence:
        """Deserialize from dict"""
        return cls(
            evidence_id=data["evidence_id"],
            kind=EvidenceKind(data["kind"]),
            snapshot_id=data["snapshot_id"],
            graph_refs=GraphRefs.from_dict(data["graph_refs"]),
            constraint_summary=data.get("constraint_summary"),
            rule_id=data.get("rule_id"),
            rule_hash=data.get("rule_hash"),
            solver_trace_ref=data.get("solver_trace_ref"),
            plan_hash=data.get("plan_hash"),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            extra_data=data.get("extra_data", {}),
        )

    @classmethod
    def create(
        cls,
        evidence_id: str,
        kind: EvidenceKind,
        snapshot_id: str,
        graph_refs: GraphRefs,
        plan_hash: str | None = None,
        ttl_days: int = 30,
        **kwargs: Any,
    ) -> Evidence:
        """
        Factory method with default TTL.

        Args:
            evidence_id: Stable ID
            kind: Evidence type
            snapshot_id: Snapshot ID
            graph_refs: Graph references
            plan_hash: QueryPlan hash
            ttl_days: Days until expiration (default: 30)
            **kwargs: Additional fields
        """
        expires_at = datetime.now() + timedelta(days=ttl_days)

        return cls(
            evidence_id=evidence_id,
            kind=kind,
            snapshot_id=snapshot_id,
            graph_refs=graph_refs,
            plan_hash=plan_hash,
            expires_at=expires_at,
            **kwargs,
        )


@dataclass(frozen=True)
class EvidenceRef:
    """
    Lightweight reference to evidence.

    Used in API responses (instead of full evidence).
    """

    evidence_id: str
    kind: EvidenceKind
    created_at: str  # ISO format

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.kind.value,
            "created_at": self.created_at,
        }

    @classmethod
    def from_evidence(cls, evidence: Evidence) -> EvidenceRef:
        """Create ref from full evidence"""
        return cls(
            evidence_id=evidence.evidence_id,
            kind=evidence.kind,
            created_at=evidence.created_at.isoformat(),
        )
