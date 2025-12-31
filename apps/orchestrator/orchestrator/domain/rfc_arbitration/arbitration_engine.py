"""
ArbitrationEngine (RFC-027 Section 7)

Priority-based claim arbitration.

Architecture:
- Domain Layer (Pure logic)
- Stateless (no side effects)
- Immutable (returns new claims, doesn't modify input)

RFC-027 Section 7.1: Priority Rules
- PROVEN > INFERRED > HEURISTIC > UNKNOWN

RFC-027 Section 7.2: Conflict Resolution
- Higher priority suppresses lower priority (same type)
"""

from dataclasses import dataclass
from enum import IntEnum

from codegraph_shared.common.observability import get_logger
from codegraph_engine.shared_kernel.contracts import Claim, ConfidenceBasis

logger = get_logger(__name__)


# ============================================================
# Priority Rules (RFC-027 Section 7.1)
# ============================================================


class ArbitrationPriority(IntEnum):
    """
    Arbitration priority (RFC-027 Section 7.1)

    Lower number = higher priority

    Priority Rules:
    1. STATIC_PROOF (1) — Deterministic static proof (SCCP, Taint)
    2. PATH_EXISTENCE (2) — Path existence proof (DFG traversal)
    3. HEURISTIC (3) — Pattern-based, ML-based
    4. VECTOR_SIMILARITY (4) — Vector similarity hypothesis
    """

    STATIC_PROOF = 1
    PATH_EXISTENCE = 2
    HEURISTIC = 3
    VECTOR_SIMILARITY = 4


CONFIDENCE_BASIS_TO_PRIORITY = {
    ConfidenceBasis.PROVEN: ArbitrationPriority.STATIC_PROOF,
    ConfidenceBasis.INFERRED: ArbitrationPriority.PATH_EXISTENCE,
    ConfidenceBasis.HEURISTIC: ArbitrationPriority.HEURISTIC,
    ConfidenceBasis.UNKNOWN: ArbitrationPriority.VECTOR_SIMILARITY,
}
"""Confidence basis → Priority mapping"""


# ============================================================
# Arbitration Result
# ============================================================


@dataclass(frozen=True)
class ArbitrationResult:
    """
    Arbitration result

    Fields:
    - accepted: Claims that were accepted (not suppressed)
    - suppressed: Claims that were suppressed by higher priority
    - total: Total claims processed
    - conflicts_resolved: Number of conflicts resolved

    Immutable: frozen=True
    """

    accepted: list[Claim]
    suppressed: list[Claim]
    total: int
    conflicts_resolved: int

    def get_all_claims(self) -> list[Claim]:
        """Get all claims (accepted + suppressed)"""
        return self.accepted + self.suppressed


# ============================================================
# ArbitrationEngine
# ============================================================


class ArbitrationEngine:
    """
    ArbitrationEngine (RFC-027 Section 7)

    Priority-based claim arbitration.

    Algorithm:
    1. Sort claims by priority (PROVEN > INFERRED > HEURISTIC > UNKNOWN)
    2. Group by (type, severity)
    3. Keep highest priority, suppress lower priority
    4. Return all claims (accepted + suppressed with reason)

    Design:
    - Stateless (no instance state)
    - Pure function (deterministic)
    - Immutable (returns new claims)

    Usage:
        engine = ArbitrationEngine()

        # Claims from multiple adapters
        claims = [
            Claim(type="sql_injection", confidence_basis=PROVEN, ...),
            Claim(type="sql_injection", confidence_basis=HEURISTIC, ...),  # Same type, lower priority
        ]

        # Arbitrate
        result = engine.arbitrate(claims)

        # Result
        assert len(result.accepted) == 1  # PROVEN kept
        assert len(result.suppressed) == 1  # HEURISTIC suppressed

    Thread-Safety:
        Thread-safe (stateless)
    """

    def __init__(self):
        """Initialize engine (stateless)"""
        pass

    def arbitrate(self, claims: list[Claim]) -> ArbitrationResult:
        """
        Arbitrate claims based on priority rules

        Args:
            claims: List of claims (from multiple adapters)

        Returns:
            ArbitrationResult with accepted and suppressed claims

        Algorithm:
        1. Sort by priority (PROVEN first)
        2. Group by (type, severity)
        3. Keep highest priority per group
        4. Suppress lower priorities

        Immutability:
        - Input claims are NOT modified
        - Returns new Claim objects (with suppression info)

        Example:
            >>> claims = [
            ...     Claim(id="c1", type="sql_injection", confidence_basis=PROVEN, ...),
            ...     Claim(id="c2", type="sql_injection", confidence_basis=HEURISTIC, ...)
            ... ]
            >>> result = engine.arbitrate(claims)
            >>> len(result.accepted)
            1  # PROVEN kept
            >>> result.suppressed[0].suppression_reason
            "Superseded by c1 (PROVEN)"
        """
        if not claims:
            return ArbitrationResult(
                accepted=[],
                suppressed=[],
                total=0,
                conflicts_resolved=0,
            )

        logger.info("arbitration_started", claims=len(claims))

        # 1. Sort by priority
        sorted_claims = sorted(claims, key=self._get_priority)

        # 2. Group by (type, severity) and resolve conflicts
        accepted = []
        suppressed = []
        seen: dict[tuple[str, str], Claim] = {}  # (type, severity) → best claim
        conflicts_resolved = 0

        for claim in sorted_claims:
            key = (claim.type, claim.severity)

            if key in seen:
                # Conflict detected
                existing = seen[key]
                existing_priority = self._get_priority(existing)
                current_priority = self._get_priority(claim)

                if current_priority > existing_priority:
                    # Current has lower priority → suppress
                    suppressed_claim = claim.model_copy(
                        update={
                            "suppressed": True,
                            "suppression_reason": f"Superseded by {existing.id} ({existing.confidence_basis.value})",
                        }
                    )
                    suppressed.append(suppressed_claim)
                    conflicts_resolved += 1

                    logger.debug(
                        "claim_suppressed",
                        claim_id=claim.id,
                        superseded_by=existing.id,
                        priority_diff=current_priority - existing_priority,
                    )
                else:
                    # Existing has lower priority → replace
                    # (should not happen since we sorted, but defensive)
                    suppressed_existing = existing.model_copy(
                        update={
                            "suppressed": True,
                            "suppression_reason": f"Superseded by {claim.id} ({claim.confidence_basis.value})",
                        }
                    )

                    # Remove from accepted, add to suppressed
                    if existing in accepted:
                        accepted.remove(existing)
                    suppressed.append(suppressed_existing)

                    # Add current
                    accepted.append(claim)
                    seen[key] = claim
                    conflicts_resolved += 1
            else:
                # No conflict
                accepted.append(claim)
                seen[key] = claim

        logger.info(
            "arbitration_complete",
            total=len(claims),
            accepted=len(accepted),
            suppressed=len(suppressed),
            conflicts_resolved=conflicts_resolved,
        )

        return ArbitrationResult(
            accepted=accepted,
            suppressed=suppressed,
            total=len(claims),
            conflicts_resolved=conflicts_resolved,
        )

    def _get_priority(self, claim: Claim) -> int:
        """
        Get priority for claim

        Args:
            claim: Claim

        Returns:
            Priority (lower = higher priority)
        """
        return CONFIDENCE_BASIS_TO_PRIORITY.get(claim.confidence_basis, ArbitrationPriority.VECTOR_SIMILARITY)
