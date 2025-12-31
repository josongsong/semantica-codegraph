"""
DEPRECATED: Use src.contexts.shared_kernel.contracts instead

RFC-027/028 Specs & Models

This package is deprecated. The canonical source of truth is now:
  src.contexts.shared_kernel.contracts

This module re-exports from the new location for backward compatibility.
New code should import from codegraph_engine.shared_kernel.contracts directly.

Migration: All imports from this module work unchanged, but please update
to use src.contexts.shared_kernel.contracts for new code.
"""

# Re-export from canonical location
from codegraph_engine.shared_kernel.contracts import (  # noqa: F401
    AnalysisLimits,
    AnalyzeSpec,
    Claim,
    Conclusion,
    ConfidenceBasis,
    EditConstraints,
    EditOperation,
    EditOperationType,
    EditSpec,
    Escalation,
    Evidence,
    EvidenceKind,
    ExpansionPolicy,
    Location,
    Metrics,
    ProofObligation,
    Provenance,
    ResultEnvelope,
    ResultEnvelopeBuilder,
    RetrievalMode,
    RetrieveSpec,
    Scope,
    SpecUnion,
    parse_spec,
    validate_spec_intent,
)

__all__ = [
    # Evidence
    "Evidence",
    "EvidenceKind",
    "Location",
    "Provenance",
    # Claim
    "Claim",
    "ConfidenceBasis",
    "ProofObligation",
    # Envelope
    "ResultEnvelope",
    "ResultEnvelopeBuilder",
    "Conclusion",
    "Escalation",
    "Metrics",
    # Specs
    "Scope",
    "RetrieveSpec",
    "RetrievalMode",
    "ExpansionPolicy",
    "AnalyzeSpec",
    "AnalysisLimits",
    "EditSpec",
    "EditOperation",
    "EditOperationType",
    "EditConstraints",
    "SpecUnion",
    "parse_spec",
    "validate_spec_intent",
]
