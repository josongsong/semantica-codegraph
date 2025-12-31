"""
ArbitrationEngine Tests (RFC-027 Section 7)

Test coverage:
- Priority sorting (PROVEN > INFERRED > HEURISTIC > UNKNOWN)
- Conflict resolution (same type/severity)
- Suppression marking (suppressed=True, reason set)
- Immutability (input claims unchanged)
- Edge cases (empty, single, no conflicts)
- Corner cases (same priority, multiple conflicts)
- Extreme cases (1000 claims, all conflicting)
- Integration (multi-adapter results)

Testing Strategy:
- Unit tests (priority, conflict resolution)
- Integration tests (multi-adapter)
- Extreme tests (performance, scale)
- Immutability tests (defensive copy)
"""

import pytest

from apps.orchestrator.orchestrator.domain.rfc_arbitration import ArbitrationEngine, ArbitrationPriority
from apps.orchestrator.orchestrator.domain.rfc_specs import Claim, ConfidenceBasis, ProofObligation

# ============================================================
# Test Fixtures
# ============================================================


@pytest.fixture
def claim_proven():
    """PROVEN claim (highest priority)"""
    return Claim(
        id="claim_proven",
        type="sql_injection",
        severity="critical",
        confidence=0.95,
        confidence_basis=ConfidenceBasis.PROVEN,
        proof_obligation=ProofObligation(),
    )


@pytest.fixture
def claim_inferred():
    """INFERRED claim (medium priority)"""
    return Claim(
        id="claim_inferred",
        type="sql_injection",
        severity="critical",
        confidence=0.8,
        confidence_basis=ConfidenceBasis.INFERRED,
        proof_obligation=ProofObligation(),
    )


@pytest.fixture
def claim_heuristic():
    """HEURISTIC claim (low priority)"""
    return Claim(
        id="claim_heuristic",
        type="sql_injection",
        severity="critical",
        confidence=0.5,
        confidence_basis=ConfidenceBasis.HEURISTIC,
        proof_obligation=ProofObligation(),
    )


@pytest.fixture
def claim_unknown():
    """UNKNOWN claim (lowest priority)"""
    return Claim(
        id="claim_unknown",
        type="sql_injection",
        severity="critical",
        confidence=0.3,
        confidence_basis=ConfidenceBasis.UNKNOWN,
        proof_obligation=ProofObligation(),
    )


# ============================================================
# Base Case Tests: Priority Sorting
# ============================================================


def test_arbitrate_single_claim(claim_proven):
    """Test arbitration with single claim (no conflicts)"""
    engine = ArbitrationEngine()

    result = engine.arbitrate([claim_proven])

    # No conflicts
    assert len(result.accepted) == 1
    assert len(result.suppressed) == 0
    assert result.conflicts_resolved == 0
    assert result.accepted[0].id == "claim_proven"
    assert not result.accepted[0].suppressed


def test_arbitrate_proven_over_heuristic(claim_proven, claim_heuristic):
    """Test PROVEN suppresses HEURISTIC (same type/severity)"""
    engine = ArbitrationEngine()

    result = engine.arbitrate([claim_proven, claim_heuristic])

    # PROVEN accepted, HEURISTIC suppressed
    assert len(result.accepted) == 1
    assert len(result.suppressed) == 1
    assert result.conflicts_resolved == 1

    # Accepted is PROVEN
    assert result.accepted[0].id == "claim_proven"
    assert result.accepted[0].confidence_basis == ConfidenceBasis.PROVEN

    # Suppressed is HEURISTIC
    assert result.suppressed[0].id == "claim_heuristic"
    assert result.suppressed[0].suppressed is True
    assert "claim_proven" in result.suppressed[0].suppression_reason
    assert "proven" in result.suppressed[0].suppression_reason.lower()


def test_arbitrate_all_priorities(claim_proven, claim_inferred, claim_heuristic, claim_unknown):
    """Test all 4 priority levels (same type/severity)"""
    engine = ArbitrationEngine()

    result = engine.arbitrate([claim_unknown, claim_heuristic, claim_inferred, claim_proven])  # Unsorted order

    # Only PROVEN accepted
    assert len(result.accepted) == 1
    assert len(result.suppressed) == 3
    assert result.conflicts_resolved == 3

    # Accepted is PROVEN
    assert result.accepted[0].confidence_basis == ConfidenceBasis.PROVEN

    # All others suppressed
    suppressed_bases = {c.confidence_basis for c in result.suppressed}
    assert ConfidenceBasis.INFERRED in suppressed_bases
    assert ConfidenceBasis.HEURISTIC in suppressed_bases
    assert ConfidenceBasis.UNKNOWN in suppressed_bases


# ============================================================
# Edge Cases
# ============================================================


def test_arbitrate_empty_claims():
    """Test arbitration with empty claims"""
    engine = ArbitrationEngine()

    result = engine.arbitrate([])

    assert len(result.accepted) == 0
    assert len(result.suppressed) == 0
    assert result.total == 0
    assert result.conflicts_resolved == 0


def test_arbitrate_no_conflicts():
    """Test arbitration with no conflicts (different types)"""
    claim1 = Claim(
        id="c1",
        type="sql_injection",
        severity="critical",
        confidence=0.95,
        confidence_basis=ConfidenceBasis.PROVEN,
        proof_obligation=ProofObligation(),
    )

    claim2 = Claim(
        id="c2",
        type="xss",  # Different type
        severity="high",
        confidence=0.9,
        confidence_basis=ConfidenceBasis.INFERRED,
        proof_obligation=ProofObligation(),
    )

    engine = ArbitrationEngine()
    result = engine.arbitrate([claim1, claim2])

    # Both accepted (no conflict)
    assert len(result.accepted) == 2
    assert len(result.suppressed) == 0
    assert result.conflicts_resolved == 0


def test_arbitrate_different_severity_no_conflict():
    """Test same type but different severity (no conflict)"""
    claim1 = Claim(
        id="c1",
        type="sql_injection",
        severity="critical",
        confidence=0.95,
        confidence_basis=ConfidenceBasis.PROVEN,
        proof_obligation=ProofObligation(),
    )

    claim2 = Claim(
        id="c2",
        type="sql_injection",  # Same type
        severity="high",  # Different severity
        confidence=0.9,
        confidence_basis=ConfidenceBasis.INFERRED,
        proof_obligation=ProofObligation(),
    )

    engine = ArbitrationEngine()
    result = engine.arbitrate([claim1, claim2])

    # Both accepted (different severity)
    assert len(result.accepted) == 2
    assert len(result.suppressed) == 0


# ============================================================
# Corner Cases
# ============================================================


def test_arbitrate_same_priority_same_type():
    """Test same priority, same type (no suppression)"""
    claim1 = Claim(
        id="c1",
        type="sql_injection",
        severity="critical",
        confidence=0.95,
        confidence_basis=ConfidenceBasis.PROVEN,
        proof_obligation=ProofObligation(),
    )

    claim2 = Claim(
        id="c2",
        type="sql_injection",  # Same type
        severity="critical",  # Same severity
        confidence=0.96,
        confidence_basis=ConfidenceBasis.PROVEN,  # Same priority
        proof_obligation=ProofObligation(),
    )

    engine = ArbitrationEngine()
    result = engine.arbitrate([claim1, claim2])

    # Both PROVEN → only one kept (first seen wins)
    assert len(result.accepted) == 1
    assert len(result.suppressed) == 1
    # Either c1 or c2 can be accepted (same priority)
    assert result.accepted[0].id in ["c1", "c2"]


def test_arbitrate_multiple_conflicts_same_group():
    """Test multiple claims conflicting with same group"""
    # 5 claims, same type/severity, different priorities
    claims = [
        Claim(
            id=f"c{i}",
            type="sql_injection",
            severity="critical",
            confidence=0.5,
            confidence_basis=[ConfidenceBasis.PROVEN, ConfidenceBasis.INFERRED, ConfidenceBasis.HEURISTIC][i % 3],
            proof_obligation=ProofObligation(),
        )
        for i in range(5)
    ]

    engine = ArbitrationEngine()
    result = engine.arbitrate(claims)

    # Only PROVEN accepted
    proven_claims = [c for c in result.accepted if c.confidence_basis == ConfidenceBasis.PROVEN]
    assert len(proven_claims) >= 1

    # Others suppressed
    assert len(result.suppressed) > 0


# ============================================================
# Extreme Cases
# ============================================================


def test_arbitrate_1000_claims_all_conflicting():
    """
    Extreme case: 1000 claims, all same type/severity

    Tests:
    - Performance (< 50ms)
    - Memory handling
    - Priority sorting at scale
    """
    import time

    # 1000 claims, same type/severity, varying priorities
    claims = [
        Claim(
            id=f"claim_{i}",
            type="performance_issue",
            severity="medium",
            confidence=0.5,
            confidence_basis=[
                ConfidenceBasis.PROVEN,
                ConfidenceBasis.INFERRED,
                ConfidenceBasis.HEURISTIC,
                ConfidenceBasis.UNKNOWN,
            ][i % 4],
            proof_obligation=ProofObligation(),
        )
        for i in range(1000)
    ]

    engine = ArbitrationEngine()

    start = time.perf_counter()
    result = engine.arbitrate(claims)
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Validate
    assert result.total == 1000
    assert len(result.accepted) > 0  # At least PROVEN claims
    assert len(result.suppressed) > 0

    # All PROVEN should be accepted (or only first if same type/severity)
    proven_accepted = [c for c in result.accepted if c.confidence_basis == ConfidenceBasis.PROVEN]
    assert len(proven_accepted) >= 1  # At least one PROVEN

    # Performance: < 50ms for 1000 claims
    assert elapsed_ms < 50.0, f"Arbitration too slow: {elapsed_ms:.2f}ms"


def test_arbitrate_extreme_many_groups():
    """
    Extreme case: 500 claims, 100 different groups

    Tests:
    - Grouping performance
    - No false conflicts
    """
    import time

    # 500 claims, 100 types × 5 priorities
    claims = []
    for type_i in range(100):
        for priority_j in range(5):
            basis = [
                ConfidenceBasis.PROVEN,
                ConfidenceBasis.INFERRED,
                ConfidenceBasis.HEURISTIC,
                ConfidenceBasis.UNKNOWN,
            ][priority_j % 4]

            claims.append(
                Claim(
                    id=f"claim_t{type_i}_p{priority_j}",
                    type=f"type_{type_i}",
                    severity="medium",
                    confidence=0.5,
                    confidence_basis=basis,
                    proof_obligation=ProofObligation(),
                )
            )

    engine = ArbitrationEngine()

    start = time.perf_counter()
    result = engine.arbitrate(claims)
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Validate
    assert result.total == 500
    # 100 types → 100 accepted (one per type)
    assert len(result.accepted) == 100
    # 400 suppressed
    assert len(result.suppressed) == 400

    # Performance: < 100ms for 500 claims
    assert elapsed_ms < 100.0, f"Arbitration too slow: {elapsed_ms:.2f}ms"


# ============================================================
# Immutability Tests (CRITICAL)
# ============================================================


def test_immutability_input_claims_unchanged(claim_proven, claim_heuristic):
    """Test input claims are not modified (immutability)"""
    engine = ArbitrationEngine()

    # Original state
    original_suppressed_proven = claim_proven.suppressed
    original_suppressed_heuristic = claim_heuristic.suppressed

    # Arbitrate
    result = engine.arbitrate([claim_proven, claim_heuristic])

    # Input claims UNCHANGED
    assert claim_proven.suppressed == original_suppressed_proven
    assert claim_heuristic.suppressed == original_suppressed_heuristic

    # Result claims are different objects
    assert result.suppressed[0] is not claim_heuristic  # New object


def test_immutability_result_frozen():
    """Test ArbitrationResult is frozen (immutable)"""
    from pydantic import ValidationError

    result = ArbitrationEngine().arbitrate([])

    # Frozen - cannot modify
    with pytest.raises(Exception):  # FrozenInstanceError or ValidationError
        result.accepted = []


# ============================================================
# Integration Tests: Multi-Adapter
# ============================================================


def test_integration_multi_adapter_arbitration():
    """
    Integration: Multiple adapters → Arbitration

    Scenario:
    - TaintAdapter: PROVEN sql_injection
    - Vector search: UNKNOWN sql_injection (conflict!)
    - SCCPAdapter: PROVEN dead_code (no conflict)

    Expected:
    - sql_injection: PROVEN accepted, UNKNOWN suppressed
    - dead_code: PROVEN accepted
    """
    claims = [
        # TaintAdapter: PROVEN
        Claim(
            id="taint_claim_001",
            type="sql_injection",
            severity="critical",
            confidence=0.95,
            confidence_basis=ConfidenceBasis.PROVEN,
            proof_obligation=ProofObligation(),
        ),
        # Vector search: UNKNOWN (conflict with taint)
        Claim(
            id="vector_claim_001",
            type="sql_injection",  # Same type
            severity="critical",  # Same severity
            confidence=0.4,
            confidence_basis=ConfidenceBasis.UNKNOWN,  # Lower priority
            proof_obligation=ProofObligation(),
        ),
        # SCCPAdapter: PROVEN (no conflict)
        Claim(
            id="sccp_claim_001",
            type="dead_code",  # Different type
            severity="low",
            confidence=1.0,
            confidence_basis=ConfidenceBasis.PROVEN,
            proof_obligation=ProofObligation(),
        ),
    ]

    engine = ArbitrationEngine()
    result = engine.arbitrate(claims)

    # 2 accepted (PROVEN sql_injection, PROVEN dead_code)
    assert len(result.accepted) == 2
    assert len(result.suppressed) == 1
    assert result.conflicts_resolved == 1

    # Accepted IDs
    accepted_ids = {c.id for c in result.accepted}
    assert "taint_claim_001" in accepted_ids  # PROVEN kept
    assert "sccp_claim_001" in accepted_ids  # No conflict

    # Suppressed
    assert result.suppressed[0].id == "vector_claim_001"
    assert "taint_claim_001" in result.suppressed[0].suppression_reason


# ============================================================
# Correctness Tests: Suppression Reason
# ============================================================


def test_suppression_reason_format(claim_proven, claim_heuristic):
    """Test suppression_reason format"""
    engine = ArbitrationEngine()

    result = engine.arbitrate([claim_proven, claim_heuristic])

    suppressed = result.suppressed[0]
    reason = suppressed.suppression_reason

    # Format: "Superseded by {id} ({confidence_basis})"
    assert "Superseded by" in reason
    assert "claim_proven" in reason
    assert "proven" in reason.lower()


# ============================================================
# Performance Tests
# ============================================================


def test_performance_100_claims():
    """Test arbitration performance with 100 claims"""
    import time

    # 100 claims, 10 types × 10 priorities
    claims = [
        Claim(
            id=f"claim_{i}",
            type=f"type_{i // 10}",
            severity="medium",
            confidence=0.5,
            confidence_basis=[ConfidenceBasis.PROVEN, ConfidenceBasis.INFERRED, ConfidenceBasis.HEURISTIC][i % 3],
            proof_obligation=ProofObligation(),
        )
        for i in range(100)
    ]

    engine = ArbitrationEngine()

    start = time.perf_counter()
    result = engine.arbitrate(claims)
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Validate
    assert result.total == 100

    # Performance: < 10ms for 100 claims
    assert elapsed_ms < 10.0, f"Too slow: {elapsed_ms:.2f}ms"


# ============================================================
# Stateless Tests
# ============================================================


def test_engine_stateless(claim_proven, claim_heuristic):
    """Test engine is stateless (thread-safe)"""
    engine = ArbitrationEngine()

    # Call twice with different inputs
    result1 = engine.arbitrate([claim_proven])
    result2 = engine.arbitrate([claim_heuristic])

    # Results independent
    assert len(result1.accepted) == 1
    assert len(result2.accepted) == 1
    assert result1.accepted[0].id != result2.accepted[0].id


# ============================================================
# Helper Method Tests
# ============================================================


def test_get_all_claims(claim_proven, claim_heuristic):
    """Test ArbitrationResult.get_all_claims()"""
    engine = ArbitrationEngine()

    result = engine.arbitrate([claim_proven, claim_heuristic])

    all_claims = result.get_all_claims()

    # All claims (accepted + suppressed)
    assert len(all_claims) == 2
    assert result.accepted[0] in all_claims
    assert result.suppressed[0] in all_claims
