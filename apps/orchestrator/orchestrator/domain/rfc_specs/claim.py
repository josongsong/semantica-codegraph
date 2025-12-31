"""DEPRECATED: Use src.contexts.shared_kernel.contracts instead"""

from codegraph_engine.shared_kernel.contracts import (  # noqa: F401
    Claim,
    ConfidenceBasis,
    ProofObligation,
    create_heuristic_claim,
    create_proven_claim,
)

__all__ = [
    "Claim",
    "ConfidenceBasis",
    "ProofObligation",
    "create_heuristic_claim",
    "create_proven_claim",
]
