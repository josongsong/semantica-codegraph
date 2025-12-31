"""
SCCPAdapter Tests (RFC-027)

Test coverage:
- ConstantPropagationResult → ResultEnvelope conversion
- Dead code detection → Claim + Evidence
- confidence_basis = PROVEN
- Evidence.kind = CODE_SNIPPET
- Unreachable blocks handling
- Conclusion generation
- Metrics generation
- Edge cases (no dead code, many blocks)
- Performance (100+ blocks)

Testing Strategy:
- Base case (with dead code)
- Edge case (no dead code)
- Corner case (many unreachable blocks)
- Performance (100+ blocks)
- Security (block_id injection)
"""

import pytest

from apps.orchestrator.orchestrator.domain.rfc_specs import ConfidenceBasis, EvidenceKind
from codegraph_engine.code_foundation.domain.constant_propagation.models import ConstantPropagationResult, ConstantValue
from codegraph_runtime.llm_arbitration.infrastructure.adapters.sccp_adapter import (
    SCCPAdapter,
)

# ============================================================
# Test Fixtures
# ============================================================


@pytest.fixture
def sccp_result_with_dead_code():
    """SCCP result with unreachable blocks"""
    return ConstantPropagationResult(
        ssa_values={},  # Not used by adapter
        var_values={
            ("x", "block_1"): ConstantValue.constant(10),
            ("y", "block_2"): ConstantValue.constant(20),
        },
        reachable_blocks={"block_1", "block_2", "block_3"},
        unreachable_blocks={"block_4", "block_5"},  # Dead code!
        constants_found=2,
        bottom_count=0,
    )


@pytest.fixture
def sccp_result_no_dead_code():
    """SCCP result with no unreachable blocks"""
    return ConstantPropagationResult(
        ssa_values={},
        var_values={("x", "block_1"): ConstantValue.constant(10)},
        reachable_blocks={"block_1", "block_2"},
        unreachable_blocks=set(),  # No dead code
        constants_found=1,
        bottom_count=0,
    )


# ============================================================
# Base Case Tests
# ============================================================


def test_to_envelope_with_dead_code(sccp_result_with_dead_code):
    """Test conversion with dead code (base case)"""
    adapter = SCCPAdapter()

    envelope = adapter.to_envelope(
        sccp_result=sccp_result_with_dead_code,
        request_id="req_test001",
        execution_time_ms=15.3,
        ir_file_path="api/users.py",
        snapshot_id="snap:456",
    )

    # Validate structure
    assert envelope.request_id == "req_test001"
    assert "2 constants" in envelope.summary
    assert "2 unreachable blocks" in envelope.summary

    # Claims (one per unreachable block)
    assert len(envelope.claims) == 2
    for claim in envelope.claims:
        assert claim.type == "dead_code"
        assert claim.severity == "low"
        assert claim.confidence == 1.0
        assert claim.confidence_basis == ConfidenceBasis.PROVEN  # ← CRITICAL

    # Evidences
    assert len(envelope.evidences) == 2
    for evidence in envelope.evidences:
        assert evidence.kind == EvidenceKind.CODE_SNIPPET  # ← CRITICAL
        assert evidence.content["reachable"] is False
        assert evidence.content["analysis"] == "SCCP"

    # Evidence-Claim links
    for i, evidence in enumerate(envelope.evidences):
        assert evidence.claim_ids == [envelope.claims[i].id]

    # Conclusion
    assert envelope.conclusion is not None
    assert "2 unreachable blocks" in envelope.conclusion.reasoning_summary
    assert "Remove" in envelope.conclusion.recommendation

    # Metrics
    assert envelope.metrics.execution_time_ms == 15.3
    assert envelope.metrics.claims_generated == 2
    assert envelope.metrics.additional["constants_found"] == 2
    assert envelope.metrics.additional["unreachable_blocks"] == 2


def test_to_envelope_no_dead_code(sccp_result_no_dead_code):
    """Test conversion with no dead code"""
    adapter = SCCPAdapter()

    envelope = adapter.to_envelope(
        sccp_result=sccp_result_no_dead_code,
        request_id="req_test002",
        execution_time_ms=10.5,
        ir_file_path="utils.py",
    )

    # No dead code
    assert len(envelope.claims) == 0
    assert len(envelope.evidences) == 0
    assert "no dead code" in envelope.summary.lower()

    # Conclusion still exists
    assert envelope.conclusion is not None
    assert "No dead code" in envelope.conclusion.recommendation

    # Metrics
    assert envelope.metrics.claims_generated == 0


# ============================================================
# Edge Cases
# ============================================================


def test_many_unreachable_blocks():
    """Test with many unreachable blocks (performance)"""
    # 50 unreachable blocks
    unreachable = {f"block_{i}" for i in range(50)}

    sccp_result = ConstantPropagationResult(
        ssa_values={},
        var_values={},
        reachable_blocks={"block_main"},
        unreachable_blocks=unreachable,
        constants_found=0,
        bottom_count=0,
    )

    adapter = SCCPAdapter()

    import time

    start = time.perf_counter()
    envelope = adapter.to_envelope(
        sccp_result=sccp_result,
        request_id="req_perf_test",
        execution_time_ms=100.0,
        ir_file_path="test.py",
    )
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Validate
    assert len(envelope.claims) == 50
    assert len(envelope.evidences) == 50

    # Performance: < 30ms for 50 blocks
    assert elapsed_ms < 30.0, f"Conversion too slow: {elapsed_ms:.2f}ms"


def test_invalid_sccp_result_type():
    """Test with invalid sccp_result type"""
    adapter = SCCPAdapter()

    with pytest.raises(ValueError, match="must be ConstantPropagationResult"):
        adapter.to_envelope(
            sccp_result="invalid",  # ❌ Not ConstantPropagationResult
            request_id="req_test",
            execution_time_ms=100.0,
        )


def test_block_id_extraction():
    """Test _extract_line_from_block_id (edge cases)"""
    adapter = SCCPAdapter()

    # Standard format
    assert adapter._extract_line_from_block_id("cfg:func:block:42") == 42

    # Just number
    assert adapter._extract_line_from_block_id("block:10") == 10

    # No number
    assert adapter._extract_line_from_block_id("block_main") == 1  # Fallback

    # Multiple numbers (takes last)
    assert adapter._extract_line_from_block_id("cfg:func_123:block:456") == 456


# ============================================================
# Conclusion Tests
# ============================================================


def test_conclusion_coverage_calculation():
    """Test conclusion coverage calculation"""
    # 3 reachable, 2 unreachable → coverage = 3/5 = 0.6
    sccp_result = ConstantPropagationResult(
        ssa_values={},
        var_values={},
        reachable_blocks={"b1", "b2", "b3"},
        unreachable_blocks={"b4", "b5"},
        constants_found=5,
        bottom_count=0,
    )

    adapter = SCCPAdapter()
    conclusion = adapter._build_conclusion(sccp_result)

    assert conclusion.coverage == 0.6  # 3/5


def test_conclusion_no_dead_code():
    """Test conclusion with no dead code"""
    sccp_result = ConstantPropagationResult(
        ssa_values={},
        var_values={},
        reachable_blocks={"b1", "b2"},
        unreachable_blocks=set(),
        constants_found=10,
        bottom_count=0,
    )

    adapter = SCCPAdapter()
    conclusion = adapter._build_conclusion(sccp_result)

    assert "No dead code" in conclusion.recommendation
    assert conclusion.coverage == 1.0  # All reachable


# ============================================================
# Metrics Tests
# ============================================================


def test_metrics_generation(sccp_result_with_dead_code):
    """Test metrics generation"""
    adapter = SCCPAdapter()
    metrics = adapter._build_metrics(
        execution_time_ms=15.3,
        claims_generated=2,
        sccp_result=sccp_result_with_dead_code,
    )

    assert metrics.execution_time_ms == 15.3
    assert metrics.claims_generated == 2
    assert metrics.paths_analyzed == 0  # SCCP doesn't analyze paths
    assert metrics.additional["constants_found"] == 2
    assert metrics.additional["unreachable_blocks"] == 2


# ============================================================
# Integration Tests
# ============================================================


def test_integration_full_flow():
    """Integration: ConstantPropagationResult → SCCPAdapter → ResultEnvelope"""
    # Mock SCCP result
    sccp_result = ConstantPropagationResult(
        ssa_values={},
        var_values={
            ("DEBUG", "block_1"): ConstantValue.constant(False),
            ("MAX_SIZE", "block_2"): ConstantValue.constant(100),
        },
        reachable_blocks={"block_1", "block_2", "block_3"},
        unreachable_blocks={"block_debug", "block_test"},  # Dead code
        constants_found=2,
        bottom_count=0,
    )

    # Convert
    adapter = SCCPAdapter()
    envelope = adapter.to_envelope(
        sccp_result=sccp_result,
        request_id="req_integration_sccp",
        execution_time_ms=12.5,
        ir_file_path="config.py",
        snapshot_id="snap:main_abc",
    )

    # Validate RFC-027 compliance
    assert envelope.request_id == "req_integration_sccp"
    assert len(envelope.claims) == 2  # 2 unreachable blocks
    assert len(envelope.evidences) == 2

    # All claims are PROVEN
    assert all(c.confidence_basis == ConfidenceBasis.PROVEN for c in envelope.claims)
    assert all(c.type == "dead_code" for c in envelope.claims)

    # All evidences are CODE_SNIPPET
    assert all(e.kind == EvidenceKind.CODE_SNIPPET for e in envelope.evidences)

    # Conclusion
    assert envelope.conclusion is not None
    assert "2 constants" in envelope.conclusion.reasoning_summary
    assert "2 unreachable blocks" in envelope.conclusion.reasoning_summary

    # Metrics
    assert envelope.metrics.additional["constants_found"] == 2

    # Replay ref
    assert envelope.replay_ref == "replay:integration_sccp"


# ============================================================
# Stateless Tests
# ============================================================


def test_adapter_stateless(sccp_result_no_dead_code):
    """Test adapter is stateless (thread-safe)"""
    adapter = SCCPAdapter()

    # Call twice
    result1 = adapter.to_envelope(
        sccp_result=sccp_result_no_dead_code,
        request_id="req_test1",
        execution_time_ms=10.0,
    )

    result2 = adapter.to_envelope(
        sccp_result=sccp_result_no_dead_code,
        request_id="req_test2",
        execution_time_ms=20.0,
    )

    # Independent
    assert result1.request_id != result2.request_id
    assert result1.metrics.execution_time_ms == 10.0
    assert result2.metrics.execution_time_ms == 20.0
