"""
Shared Contracts - Pure Data Structures

Canonical source of truth for RFC-027/028 + RFC-SEM-022 models.

Architecture:
- Shared Kernel (DDD)
- Pure data structures (no business logic)
- Immutable (frozen=True)
- Type-safe (Pydantic)

Models:
- Claim: 분석 결과 주장
- Evidence: Machine-readable 증거
- ResultEnvelope: Canonical output format
- Specs: RetrieveSpec, AnalyzeSpec, EditSpec
- VerificationSnapshot: 결정적 실행 스냅샷 (RFC-SEM-022)
- Workspace: Immutable revision snapshot (RFC-SEM-022)
- SemanticaError: Global error schema (RFC-SEM-022)
"""

# Core models
from .claim import Claim, ConfidenceBasis, ProofObligation, create_heuristic_claim, create_proven_claim
from .envelope import Conclusion, Escalation, Metrics, ResultEnvelope, ResultEnvelopeBuilder

# RFC-SEM-022: Global Error Schema
from .errors import (
    ERR_INTERNAL,
    ERR_INVALID_ARGUMENT,
    ERR_NOT_FOUND,
    SemanticaError,
    create_error,
    internal_error,
    invalid_argument_error,
    not_found_error,
)
from .evidence import (
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

# Analysis Modes (RFC-021)
from .modes import AnalysisMode

# Pagination
from .pagination import (
    PagedResponse,
    PaginationParams,
    ResultSummary,
    decode_cursor,
    encode_cursor,
)

# Specs
from .specs import (
    AnalysisLimits,
    AnalyzeSpec,
    EditConstraints,
    EditOperation,
    EditOperationType,
    EditSpec,
    ExpansionPolicy,
    RetrievalMode,
    RetrieveSpec,
    Scope,
    SpecUnion,
    parse_spec,
    to_json_schema,
    validate_spec_intent,
)

# RFC-SEM-022: Verification & Workspace
from .verification import (
    AgentMetadata,
    Execution,
    Finding,
    PatchSet,
    VerificationSnapshot,
    Workspace,
    create_verification_snapshot,
    create_workspace,
)

__all__ = [
    # Pagination
    "PagedResponse",
    "PaginationParams",
    "ResultSummary",
    "encode_cursor",
    "decode_cursor",
    # Confidence & Evidence
    "ConfidenceBasis",
    "EvidenceKind",
    # Claim
    "Claim",
    "ProofObligation",
    "create_proven_claim",
    "create_heuristic_claim",
    # Evidence
    "Evidence",
    "Location",
    "Provenance",
    "CostEvidenceBuilder",
    "ConcurrencyEvidenceBuilder",
    "DifferentialEvidenceBuilder",
    "validate_evidence_claim_links",
    "group_evidences_by_kind",
    # Envelope
    "ResultEnvelope",
    "ResultEnvelopeBuilder",
    "Conclusion",
    "Escalation",
    "Metrics",
    # Specs
    "Scope",
    "RetrievalMode",
    "ExpansionPolicy",
    "RetrieveSpec",
    "AnalysisLimits",
    "AnalyzeSpec",
    "EditOperationType",
    "EditOperation",
    "EditConstraints",
    "EditSpec",
    "SpecUnion",
    "parse_spec",
    "to_json_schema",
    "validate_spec_intent",
    # RFC-SEM-022: Verification
    "VerificationSnapshot",
    "AgentMetadata",
    "Execution",
    "Workspace",
    "PatchSet",
    "Finding",
    "create_verification_snapshot",
    "create_workspace",
    # RFC-SEM-022: Errors
    "SemanticaError",
    "create_error",
    "not_found_error",
    "invalid_argument_error",
    "internal_error",
    "ERR_NOT_FOUND",
    "ERR_INVALID_ARGUMENT",
    "ERR_INTERNAL",
    # Analysis Modes
    "AnalysisMode",
]
