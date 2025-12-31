"""DEPRECATED: Use src.contexts.shared_kernel.contracts instead"""

from codegraph_engine.shared_kernel.contracts import (  # noqa: F401
    ConcurrencyEvidenceBuilder,
    CostEvidenceBuilder,
    DifferentialEvidenceBuilder,
    Evidence,
    EvidenceKind,
    Location,
    Provenance,
    group_evidences_by_kind,
    validate_evidence_claim_links,
)

__all__ = [
    "Evidence",
    "EvidenceKind",
    "Location",
    "Provenance",
    "CostEvidenceBuilder",
    "ConcurrencyEvidenceBuilder",
    "DifferentialEvidenceBuilder",
    "group_evidences_by_kind",
    "validate_evidence_claim_links",
]
