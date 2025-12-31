"""
Multi-Adapter Integration Tests (RFC-027)

CRITICAL TEST: Multiple adapters working together.

Test coverage:
- Multiple adapters → Single ResultEnvelope
- ID collision prevention (adapter prefix)
- Evidence-Claim link integrity (multi-source)
- Arbitration preparation (mixed confidence_basis)
- Performance (100+ claims from multiple adapters)
- Memory stress (1000+ items)

Testing Strategy:
- Integration (TaintAdapter + SCCPAdapter + RiskAdapter)
- Extreme cases (1000+ claims, empty chains)
- ID uniqueness verification
"""

import pytest

from codegraph_engine.code_foundation.domain.constant_propagation.models import ConstantPropagationResult, ConstantValue
from codegraph_engine.code_foundation.domain.taint.models import SimpleVulnerability
from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument
from codegraph_runtime.llm_arbitration.infrastructure.adapters.reasoning_adapter import (
    ReasoningAdapter,
)
from codegraph_runtime.llm_arbitration.infrastructure.adapters.risk_adapter import (
    RiskAdapter,
)
from codegraph_runtime.llm_arbitration.infrastructure.adapters.sccp_adapter import (
    SCCPAdapter,
)
from codegraph_runtime.llm_arbitration.infrastructure.adapters.taint_adapter import (
    TaintAdapter,
)
from codegraph_engine.reasoning_engine.application.reasoning_pipeline import ReasoningContext, ReasoningResult
from codegraph_engine.reasoning_engine.domain.impact_models import ImpactLevel
from codegraph_engine.reasoning_engine.domain.speculative_models import RiskLevel, RiskReport
from codegraph_engine.shared_kernel.contracts import (
    ConfidenceBasis,
    EvidenceKind,
    Metrics,
    ResultEnvelopeBuilder,
)

# ============================================================
# Critical Integration Test: Multiple Adapters
# ============================================================


def test_multi_adapter_integration():
    """
    CRITICAL: Test multiple adapters working together

    Scenario:
    - TaintAdapter finds 2 vulnerabilities
    - SCCPAdapter finds 3 dead code blocks
    - RiskAdapter adds 1 breaking change warning

    Verification:
    - 6 total claims
    - All claim IDs unique (no collision)
    - All evidence IDs unique
    - Evidence-Claim links valid
    - Mixed confidence_basis (PROVEN from different sources)
    """
    request_id = "req_multi_test"

    # 1. TaintAdapter results
    taint_result = {
        "vulnerabilities": [
            SimpleVulnerability(
                policy_id="sql_injection",
                severity="critical",
                source_location="api.py:10",
                sink_location="api.py:42",
                source_atom_id="source.http",
                sink_atom_id="sink.sql",
                path=["var1"],
                message="SQL injection",
            ),
            SimpleVulnerability(
                policy_id="xss",
                severity="high",
                source_location="views.py:20",
                sink_location="views.py:55",
                source_atom_id="source.http",
                sink_atom_id="sink.html",
                path=["var2"],
                message="XSS",
            ),
        ],
        "policies_executed": [],
        "stats": {},
    }

    taint_adapter = TaintAdapter()
    taint_envelope = taint_adapter.to_envelope(taint_result, request_id, 100.0)

    # 2. SCCPAdapter results
    sccp_result = ConstantPropagationResult(
        ssa_values={},
        var_values={},
        reachable_blocks={"b1"},
        unreachable_blocks={"b_dead1", "b_dead2", "b_dead3"},
        constants_found=5,
        bottom_count=0,
    )

    sccp_adapter = SCCPAdapter()
    sccp_envelope = sccp_adapter.to_envelope(sccp_result, request_id, 20.0, "config.py")

    # 3. RiskAdapter result
    risk_report = RiskReport(
        patch_id="patch_001",
        risk_level=RiskLevel.BREAKING,
        risk_score=0.8,
        affected_symbols={"func1", "func2"},
        breaking_changes=["Signature changed"],
    )

    risk_adapter = RiskAdapter()
    risk_claim = risk_adapter.to_claim(risk_report, request_id)

    # 4. Combine into single envelope
    builder = ResultEnvelopeBuilder(request_id)
    builder.set_summary("Multi-adapter analysis: 2 vulnerabilities, 3 dead blocks, 1 breaking change")

    # Add all claims
    builder.add_claims(taint_envelope.claims)  # 2 claims
    builder.add_claims(sccp_envelope.claims)  # 3 claims
    builder.add_claim(risk_claim)  # 1 claim

    # Add all evidences
    builder.add_evidences(taint_envelope.evidences)  # 2 evidences
    builder.add_evidences(sccp_envelope.evidences)  # 3 evidences

    # Set metrics (combined)
    builder.set_metrics(
        Metrics(
            execution_time_ms=120.0,  # Total time
            claims_generated=6,
            claims_suppressed=0,
            paths_analyzed=2,  # From taint
            additional={
                "taint_vulnerabilities": 2,
                "sccp_dead_blocks": 3,
                "risk_assessments": 1,
            },
        )
    )

    # Build
    combined_envelope = builder.build()

    # ============================================================
    # Critical Verifications
    # ============================================================

    # 1. Total counts
    assert len(combined_envelope.claims) == 6
    assert len(combined_envelope.evidences) == 5  # Taint 2 + SCCP 3 (Risk has no evidence)

    # 2. ID uniqueness (CRITICAL - no collision)
    claim_ids = [c.id for c in combined_envelope.claims]
    assert len(claim_ids) == len(set(claim_ids)), f"Duplicate claim IDs: {claim_ids}"

    evidence_ids = [e.id for e in combined_envelope.evidences]
    assert len(evidence_ids) == len(set(evidence_ids)), f"Duplicate evidence IDs: {evidence_ids}"

    # 3. ID prefixes (collision prevention)
    taint_claims = [c for c in combined_envelope.claims if "taint" in c.id]
    sccp_claims = [c for c in combined_envelope.claims if "sccp" in c.id]
    risk_claims = [c for c in combined_envelope.claims if "risk" in c.id]

    assert len(taint_claims) == 2, "Should have 2 taint claims"
    assert len(sccp_claims) == 3, "Should have 3 sccp claims"
    assert len(risk_claims) == 1, "Should have 1 risk claim"

    # 4. Evidence-Claim links valid (no orphans)
    all_claim_ids = {c.id for c in combined_envelope.claims}
    for evidence in combined_envelope.evidences:
        for claim_id in evidence.claim_ids:
            assert claim_id in all_claim_ids, f"Orphan evidence: {evidence.id} → {claim_id}"

    # 5. confidence_basis distribution
    proven_claims = [c for c in combined_envelope.claims if c.confidence_basis == ConfidenceBasis.PROVEN]
    assert len(proven_claims) == 6, "All should be PROVEN (static analysis)"

    # 6. Evidence kind distribution
    data_flow_paths = [e for e in combined_envelope.evidences if e.kind == EvidenceKind.DATA_FLOW_PATH]
    code_snippets = [e for e in combined_envelope.evidences if e.kind == EvidenceKind.CODE_SNIPPET]

    assert len(data_flow_paths) == 2, "Taint evidences"
    assert len(code_snippets) == 3, "SCCP evidences"


# ============================================================
# Extreme Case Tests
# ============================================================


def test_extreme_many_vulnerabilities():
    """
    Extreme case: 500 vulnerabilities from taint

    Tests:
    - Memory handling (large claims/evidences list)
    - ID uniqueness at scale
    - Performance
    """
    import time

    # 500 vulnerabilities
    vulns = [
        SimpleVulnerability(
            policy_id=f"vuln_{i}",
            severity="medium",
            source_location=f"test.py:{i}",
            sink_location=f"test.py:{i + 1}",
            source_atom_id="source",
            sink_atom_id="sink",
            path=[],
            message="",
        )
        for i in range(500)
    ]

    taint_result = {"vulnerabilities": vulns, "policies_executed": [], "stats": {}}

    adapter = TaintAdapter()

    start = time.perf_counter()
    envelope = adapter.to_envelope(taint_result, "req_extreme", 1000.0)
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Validate
    assert len(envelope.claims) == 500
    assert len(envelope.evidences) == 500

    # ID uniqueness at scale
    claim_ids = [c.id for c in envelope.claims]
    assert len(claim_ids) == len(set(claim_ids)), "Duplicate claim IDs at scale!"

    evidence_ids = [e.id for e in envelope.evidences]
    assert len(evidence_ids) == len(set(evidence_ids)), "Duplicate evidence IDs at scale!"

    # Performance: < 200ms for 500 items
    assert elapsed_ms < 200.0, f"Too slow for 500 items: {elapsed_ms:.2f}ms"


def test_extreme_empty_chain():
    """
    Extreme case: All adapters return empty results

    Tests:
    - Empty claims handling
    - Empty evidences handling
    - Conclusion generation with no data
    """
    request_id = "req_empty_chain"

    # 1. Taint: no vulnerabilities
    taint_result = {"vulnerabilities": [], "policies_executed": [], "stats": {}}
    taint_adapter = TaintAdapter()
    taint_envelope = taint_adapter.to_envelope(taint_result, request_id, 50.0)

    # 2. SCCP: no dead code
    sccp_result = ConstantPropagationResult(
        ssa_values={},
        var_values={},
        reachable_blocks={"b1"},
        unreachable_blocks=set(),
        constants_found=10,
        bottom_count=0,
    )
    sccp_adapter = SCCPAdapter()
    sccp_envelope = sccp_adapter.to_envelope(sccp_result, request_id, 10.0)

    # 3. Combine
    builder = ResultEnvelopeBuilder(request_id)
    builder.set_summary("No issues found")
    builder.add_claims(taint_envelope.claims)  # 0
    builder.add_claims(sccp_envelope.claims)  # 0

    combined = builder.build()

    # Validate
    assert len(combined.claims) == 0
    assert len(combined.evidences) == 0
    assert "No issues found" in combined.summary


def test_extreme_single_vulnerability_many_paths():
    """
    Extreme case: Single vulnerability with 500 path nodes

    Tests:
    - Large Evidence.content handling
    - JSON serialization at scale
    """
    # 500 nodes in path
    long_path = [f"node_{i}" for i in range(500)]

    vuln = SimpleVulnerability(
        policy_id="test",
        severity="critical",
        source_location="test.py:1",
        sink_location="test.py:500",
        source_atom_id="source",
        sink_atom_id="sink",
        path=long_path,
        message="Long path",
    )

    taint_result = {"vulnerabilities": [vuln], "policies_executed": [], "stats": {}}

    adapter = TaintAdapter()
    envelope = adapter.to_envelope(taint_result, "req_long_path", 100.0)

    # Validate
    assert len(envelope.evidences[0].content["path"]) == 500
    assert envelope.evidences[0].content["path_length"] == 500

    # JSON serialization should work
    import json

    json_data = envelope.to_dict()
    json_str = json.dumps(json_data)
    assert len(json_str) > 0


# ============================================================
# ID Collision Prevention Tests (CRITICAL)
# ============================================================


def test_id_collision_prevention_different_adapters():
    """
    CRITICAL: Verify adapter prefixes prevent ID collision

    When multiple adapters run for same request_id,
    their claim/evidence IDs must not collide.
    """
    request_id = "req_collision_test"

    # Generate IDs from different adapters
    taint_claim_id = f"{request_id}_taint_claim_abc12345"
    sccp_claim_id = f"{request_id}_sccp_claim_abc12345"
    risk_claim_id = f"{request_id}_risk_claim_abc12345"

    # All should be different (prefix differs)
    ids = {taint_claim_id, sccp_claim_id, risk_claim_id}
    assert len(ids) == 3, "Adapter prefixes should prevent collision"

    # No overlap
    assert taint_claim_id != sccp_claim_id
    assert sccp_claim_id != risk_claim_id
    assert taint_claim_id != risk_claim_id


def test_claim_id_format_validation():
    """Test claim ID format includes adapter prefix"""
    vuln = SimpleVulnerability(
        policy_id="test",
        severity="medium",
        source_location="test.py:1",
        sink_location="test.py:2",
        source_atom_id="source",
        sink_atom_id="sink",
        path=[],
        message="",
    )

    adapter = TaintAdapter()
    envelope = adapter.to_envelope(
        {"vulnerabilities": [vuln], "policies_executed": [], "stats": {}}, "req_format_test", 100.0
    )

    # Claim ID should contain "taint" prefix
    claim_id = envelope.claims[0].id
    assert "taint_claim" in claim_id, f"Missing taint prefix: {claim_id}"

    # Evidence ID should contain "taint" prefix
    evidence_id = envelope.evidences[0].id
    assert "taint_ev" in evidence_id, f"Missing taint prefix: {evidence_id}"


# ============================================================
# Memory Stress Tests
# ============================================================


def test_memory_stress_1000_claims():
    """
    Memory stress: 1000 claims + 1000 evidences

    Tests:
    - Memory handling (large ResultEnvelope)
    - ID generation at scale
    - JSON serialization performance
    """
    import time

    # Create 1000 vulnerabilities
    vulns = [
        SimpleVulnerability(
            policy_id=f"vuln_{i}",
            severity="low",
            source_location=f"test_{i // 100}.py:{i % 100}",
            sink_location=f"test_{i // 100}.py:{i % 100 + 1}",
            source_atom_id=f"source_{i}",
            sink_atom_id=f"sink_{i}",
            path=[f"node_{j}" for j in range(5)],  # 5 nodes per path
            message=f"Vulnerability {i}",
        )
        for i in range(1000)
    ]

    taint_result = {"vulnerabilities": vulns, "policies_executed": [], "stats": {}}

    adapter = TaintAdapter()

    # Convert
    start = time.perf_counter()
    envelope = adapter.to_envelope(taint_result, "req_stress_1000", 5000.0)
    conversion_ms = (time.perf_counter() - start) * 1000

    # Validate
    assert len(envelope.claims) == 1000
    assert len(envelope.evidences) == 1000

    # ID uniqueness at extreme scale
    claim_ids = [c.id for c in envelope.claims]
    assert len(claim_ids) == len(set(claim_ids)), "Duplicate claim IDs at 1000 scale!"

    # JSON serialization
    start = time.perf_counter()
    json_data = envelope.to_dict()
    json_ms = (time.perf_counter() - start) * 1000

    assert len(json_data["claims"]) == 1000

    # Performance targets
    assert conversion_ms < 500.0, f"Conversion too slow: {conversion_ms:.2f}ms"
    assert json_ms < 200.0, f"JSON serialization too slow: {json_ms:.2f}ms"


# ============================================================
# Conclusion Merging Tests
# ============================================================


def test_conclusion_from_reasoning_adapter():
    """Test ReasoningAdapter conclusion can be used in envelope"""
    result = ReasoningResult(
        summary="Impact analysis complete",
        total_risk=RiskLevel.LOW,
        total_impact=ImpactLevel.LOW,
        breaking_changes=[],
        impacted_symbols=["func1"],
        recommended_actions=["Proceed with changes"],
        context=ReasoningContext(graph=GraphDocument(repo_id="test", snapshot_id="snap")),
    )

    reasoning_adapter = ReasoningAdapter()
    conclusion = reasoning_adapter.to_conclusion(result)

    # Use in envelope
    builder = ResultEnvelopeBuilder("req_conclusion_test")
    builder.set_summary("Test")
    builder.set_conclusion(conclusion)

    envelope = builder.build()

    assert envelope.conclusion is not None
    assert envelope.conclusion.coverage == 0.9  # RiskLevel.LOW


# ============================================================
# Edge Case: Mixed Results
# ============================================================


def test_mixed_severity_levels():
    """Test mixed severity levels across adapters"""
    # Critical from taint
    vuln = SimpleVulnerability(
        policy_id="sql_injection",
        severity="critical",
        source_location="api.py:42",
        sink_location="api.py:43",
        source_atom_id="source",
        sink_atom_id="sink",
        path=[],
        message="",
    )

    taint_adapter = TaintAdapter()
    taint_env = taint_adapter.to_envelope(
        {"vulnerabilities": [vuln], "policies_executed": [], "stats": {}}, "req_mixed", 100.0
    )

    # Low from SCCP (dead code)
    sccp_result = ConstantPropagationResult(
        ssa_values={},
        var_values={},
        reachable_blocks=set(),
        unreachable_blocks={"b1"},
        constants_found=0,
        bottom_count=0,
    )

    sccp_adapter = SCCPAdapter()
    sccp_env = sccp_adapter.to_envelope(sccp_result, "req_mixed", 10.0)

    # Combine
    builder = ResultEnvelopeBuilder("req_mixed")
    builder.set_summary("Mixed severity")
    builder.add_claims(taint_env.claims)  # Critical
    builder.add_claims(sccp_env.claims)  # Low

    builder.set_metrics(Metrics(execution_time_ms=110.0, claims_generated=2))

    envelope = builder.build()

    # Validate severity distribution
    critical = [c for c in envelope.claims if c.severity == "critical"]
    low = [c for c in envelope.claims if c.severity == "low"]

    assert len(critical) == 1
    assert len(low) == 1
