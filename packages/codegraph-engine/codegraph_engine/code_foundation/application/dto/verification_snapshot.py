"""
Verification Snapshot DTO

RFC-052: MCP Service Layer Architecture
All MCP responses must include verification metadata.

Non-Negotiable Contract:
- snapshot_id: Which snapshot the result is based on
- engine_version: QueryEngine version
- index_snapshot_id: UnifiedGraphIndex snapshot
- ruleset_hash: Taint/security ruleset hash
- queryplan_hash: QueryPlan hash
- workspace_fingerprint: Project fingerprint

Purpose:
- Deterministic execution guarantee
- Replay capability
- Debugging support
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class VerificationSnapshot:
    """
    Verification metadata for deterministic execution.

    Every MCP response must include this.
    """

    # Core identifiers
    snapshot_id: str  # IR/Semantic snapshot ID
    engine_version: str  # QueryEngine version (e.g., "1.0.0")
    index_snapshot_id: str  # UnifiedGraphIndex snapshot ID

    # Hashes for reproducibility
    ruleset_hash: str  # Taint/security ruleset hash
    queryplan_hash: str  # QueryPlan hash
    workspace_fingerprint: str  # Project fingerprint (git hash, file hashes, etc.)

    # Timestamps
    executed_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, str]:
        """Serialize to dict"""
        return {
            "snapshot_id": self.snapshot_id,
            "engine_version": self.engine_version,
            "index_snapshot_id": self.index_snapshot_id,
            "ruleset_hash": self.ruleset_hash,
            "queryplan_hash": self.queryplan_hash,
            "workspace_fingerprint": self.workspace_fingerprint,
            "executed_at": self.executed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> VerificationSnapshot:
        """Deserialize from dict"""
        return cls(
            snapshot_id=data["snapshot_id"],
            engine_version=data["engine_version"],
            index_snapshot_id=data["index_snapshot_id"],
            ruleset_hash=data["ruleset_hash"],
            queryplan_hash=data["queryplan_hash"],
            workspace_fingerprint=data["workspace_fingerprint"],
            executed_at=datetime.fromisoformat(data["executed_at"]),
        )

    @classmethod
    def create(
        cls,
        snapshot_id: str,
        queryplan_hash: str,
        engine_version: str = "1.0.0",
        ruleset_hash: str = "default",
        workspace_fingerprint: str = "unknown",
    ) -> VerificationSnapshot:
        """
        Factory method with defaults.

        Args:
            snapshot_id: IR/Semantic snapshot ID
            queryplan_hash: QueryPlan hash
            engine_version: QueryEngine version
            ruleset_hash: Taint/security ruleset hash
            workspace_fingerprint: Project fingerprint
        """
        return cls(
            snapshot_id=snapshot_id,
            engine_version=engine_version,
            index_snapshot_id=snapshot_id,  # Default: same as snapshot_id
            ruleset_hash=ruleset_hash,
            queryplan_hash=queryplan_hash,
            workspace_fingerprint=workspace_fingerprint,
        )
