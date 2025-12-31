"""RFC-027 Confidence & Evidence Type Enums"""

from enum import Enum, IntEnum


class ConfidenceBasis(str, Enum):
    """
    Confidence basis for claims.

    Priority (Arbitration):
        PROVEN > INFERRED > HEURISTIC > UNKNOWN
    """

    PROVEN = "proven"  # Deterministic Static Proof (SCCP+, Taint with sound CFG)
    INFERRED = "inferred"  # Path Existence Proof (DFG traversal, verified paths)
    HEURISTIC = "heuristic"  # Pattern-based detection (regex, AST pattern)
    UNKNOWN = "unknown"  # Vector similarity hypothesis (no verification)


class EvidenceKind(str, Enum):
    """Evidence types for claims."""

    CODE_SNIPPET = "code_snippet"
    DATA_FLOW_PATH = "data_flow_path"
    CALL_PATH = "call_path"
    DIFF = "diff"
    TEST_RESULT = "test_result"

    # RFC-028 additions (Cost/Concurrency/Differential)
    COST_TERM = "cost_term"
    LOOP_BOUND = "loop_bound"
    RACE_WITNESS = "race_witness"
    LOCK_REGION = "lock_region"
    DIFF_DELTA = "diff_delta"


class ArbitrationPriority(IntEnum):
    """Lower number = higher priority"""

    STATIC_PROOF = 1  # Deterministic Static Proof (SCCP+, Taint)
    PATH_EXISTENCE = 2  # Path Existence Proof (DFG traversal)
    HEURISTIC = 3  # Heuristic / Pattern-based
    VECTOR_SIMILARITY = 4  # Vector Similarity Hypothesis


# Mapping: ConfidenceBasis → ArbitrationPriority
CONFIDENCE_BASIS_PRIORITY = {
    ConfidenceBasis.PROVEN: ArbitrationPriority.STATIC_PROOF,
    ConfidenceBasis.INFERRED: ArbitrationPriority.PATH_EXISTENCE,
    ConfidenceBasis.HEURISTIC: ArbitrationPriority.HEURISTIC,
    ConfidenceBasis.UNKNOWN: ArbitrationPriority.VECTOR_SIMILARITY,
}
