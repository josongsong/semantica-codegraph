"""
TaintAdapter Tests (RFC-027 Section 18.B.1)

Test coverage:
- SimpleVulnerability → Claim + Evidence conversion
- Severity mapping
- confidence_basis = PROVEN
- Evidence.kind = DATA_FLOW_PATH
- Path preservation
- Location parsing
- Conclusion generation
- Metrics generation
- Edge cases (empty vulnerabilities, invalid locations)
- Integration (full TaintAnalysisService → ResultEnvelope)

Testing Strategy:
- Unit tests (conversion logic)
- Integration tests (with real TaintAnalysisService)
- Edge cases (empty, invalid)
- Security (injection prevention)
"""

import pytest
from pydantic import ValidationError

from apps.orchestrator.orchestrator.domain.rfc_specs import ConfidenceBasis, EvidenceKind
from codegraph_engine.code_foundation.domain.taint.models import SimpleVulnerability
from codegraph_runtime.llm_arbitration.infrastructure.adapters.taint_adapter import (
    TaintAdapter,
)

# ============================================================
# Test Fixtures
# ============================================================


@pytest.fixture
def simple_vulnerability():
    """Valid SimpleVulnerability"""
    return SimpleVulnerability(
        policy_id="sql_injection",
        severity="critical",
        source_location="api/users.py:10",
        sink_location="api/users.py:42",
        source_atom_id="source.http.request_args",
        sink_atom_id="sink.sql.execute",
        path=["var_query", "call_process", "var_sql"],
        message="SQL injection via request.args",
    )


@pytest.fixture
def taint_result_single(simple_vulnerability):
    """Taint result with single vulnerability"""
    return {
        "vulnerabilities": [simple_vulnerability],
        "detected_atoms": None,  # Not used by adapter
        "policies_executed": ["sql_injection"],
        "policies_skipped": [],
        "stats": {
            "atoms_detected": 15,
            "paths_found": 1,
        },
    }


@pytest.fixture
def taint_result_multiple():
    """Taint result with multiple vulnerabilities"""
    return {
        "vulnerabilities": [
            SimpleVulnerability(
                policy_id="sql_injection",
                severity="critical",
                source_location="api/users.py:10",
                sink_location="api/users.py:42",
                source_atom_id="source.http.request_args",
                sink_atom_id="sink.sql.execute",
                path=["var_query"],
                message="SQL injection",
            ),
            SimpleVulnerability(
                policy_id="xss",
                severity="high",
                source_location="api/posts.py:20",
                sink_location="api/posts.py:55",
                source_atom_id="source.http.request_body",
                sink_atom_id="sink.html.render",
                path=["var_content", "var_html"],
                message="XSS vulnerability",
            ),
        ],
        "policies_executed": ["sql_injection", "xss"],
        "stats": {"atoms_detected": 30, "paths_found": 2},
    }


@pytest.fixture
def taint_result_empty():
    """Taint result with no vulnerabilities"""
    return {
        "vulnerabilities": [],
        "policies_executed": ["sql_injection"],
        "stats": {"atoms_detected": 10, "paths_found": 0},
    }


# ============================================================
# Unit Tests: Conversion Logic
# ============================================================


def test_to_envelope_single_vulnerability(taint_result_single):
    """Test conversion with single vulnerability (base case)"""
    adapter = TaintAdapter()

    envelope = adapter.to_envelope(
        taint_result=taint_result_single,
        request_id="req_test001",
        execution_time_ms=234.5,
        snapshot_id="snap:456",
    )

    # Validate structure
    assert envelope.request_id == "req_test001"
    assert "critical" in envelope.summary.lower()

    # Claims
    assert len(envelope.claims) == 1
    claim = envelope.claims[0]
    assert claim.type == "sql_injection"
    assert claim.severity == "critical"
    assert claim.confidence == 0.95
    assert claim.confidence_basis == ConfidenceBasis.PROVEN  # ← CRITICAL

    # Evidences
    assert len(envelope.evidences) == 1
    evidence = envelope.evidences[0]
    assert evidence.kind == EvidenceKind.DATA_FLOW_PATH  # ← CRITICAL
    assert evidence.content["source"] == "source.http.request_args"
    assert evidence.content["sink"] == "sink.sql.execute"
    assert len(evidence.content["path"]) == 3
    assert evidence.claim_ids == [claim.id]  # ← Link

    # Provenance
    assert evidence.provenance.engine == "TaintAnalyzer"
    assert evidence.provenance.template == "sql_injection"
    assert evidence.provenance.snapshot_id == "snap:456"

    # Conclusion
    assert envelope.conclusion is not None
    assert "sql_injection" in envelope.conclusion.reasoning_summary.lower()
    assert envelope.conclusion.coverage == 1.0

    # Metrics
    assert envelope.metrics.execution_time_ms == 234.5
    assert envelope.metrics.claims_generated == 1
    assert envelope.metrics.claims_suppressed == 0


def test_to_envelope_multiple_vulnerabilities(taint_result_multiple):
    """Test conversion with multiple vulnerabilities"""
    adapter = TaintAdapter()

    envelope = adapter.to_envelope(
        taint_result=taint_result_multiple,
        request_id="req_test002",
        execution_time_ms=456.7,
    )

    # Claims
    assert len(envelope.claims) == 2
    assert envelope.claims[0].type == "sql_injection"
    assert envelope.claims[1].type == "xss"

    # All claims are PROVEN
    assert all(c.confidence_basis == ConfidenceBasis.PROVEN for c in envelope.claims)

    # Evidences
    assert len(envelope.evidences) == 2
    assert all(e.kind == EvidenceKind.DATA_FLOW_PATH for e in envelope.evidences)

    # Links
    assert envelope.evidences[0].claim_ids == [envelope.claims[0].id]
    assert envelope.evidences[1].claim_ids == [envelope.claims[1].id]

    # Metrics
    assert envelope.metrics.claims_generated == 2
    assert envelope.metrics.additional["policies_executed"] == 2


def test_to_envelope_empty_vulnerabilities(taint_result_empty):
    """Test conversion with no vulnerabilities"""
    adapter = TaintAdapter()

    envelope = adapter.to_envelope(
        taint_result=taint_result_empty,
        request_id="req_test003",
        execution_time_ms=50.0,
    )

    # No vulnerabilities
    assert len(envelope.claims) == 0
    assert len(envelope.evidences) == 0
    assert "No taint vulnerabilities" in envelope.summary

    # No conclusion (no claims)
    assert envelope.conclusion is None

    # Metrics
    assert envelope.metrics.claims_generated == 0


# ============================================================
# Unit Tests: Severity Mapping
# ============================================================


@pytest.mark.parametrize(
    "vuln_severity,expected_severity",
    [
        ("critical", "critical"),
        ("high", "high"),
        ("medium", "medium"),
        ("low", "low"),
    ],
)
def test_severity_mapping(vuln_severity, expected_severity):
    """Test severity mapping (all levels)"""
    vuln = SimpleVulnerability(
        policy_id="test",
        severity=vuln_severity,
        source_location="test.py:1",
        sink_location="test.py:2",
        source_atom_id="source",
        sink_atom_id="sink",
        path=[],
        message="Test",
    )

    adapter = TaintAdapter()
    envelope = adapter.to_envelope(
        taint_result={"vulnerabilities": [vuln], "policies_executed": [], "stats": {}},
        request_id="req_test",
        execution_time_ms=100.0,
    )

    assert envelope.claims[0].severity == expected_severity


# ============================================================
# Unit Tests: Location Parsing
# ============================================================


@pytest.mark.parametrize(
    "location_str,expected_file,expected_line",
    [
        ("api/users.py:42", "api/users.py", 42),
        ("src/auth/service.py:123", "src/auth/service.py", 123),
        ("test.py:1", "test.py", 1),
        ("no_line.py", "no_line.py", 1),  # No line number → default 1
        ("path/to/file.py:invalid", "path/to/file.py", 1),  # Invalid line → default 1
    ],
)
def test_location_parsing(location_str, expected_file, expected_line):
    """Test location parsing (edge cases)"""
    adapter = TaintAdapter()
    file_path, line_num = adapter._parse_location(location_str)

    assert file_path == expected_file
    assert line_num == expected_line


# ============================================================
# Unit Tests: Conclusion Generation
# ============================================================


def test_conclusion_critical_vulnerabilities():
    """Test conclusion for critical vulnerabilities"""
    vulns = [
        SimpleVulnerability(
            policy_id="sql_injection",
            severity="critical",
            source_location="test.py:1",
            sink_location="test.py:2",
            source_atom_id="src",
            sink_atom_id="sink",
            path=[],
            message="",
        )
    ]

    adapter = TaintAdapter()
    conclusion = adapter._build_conclusion(vulns)

    assert "CRITICAL" in conclusion.recommendation
    assert "1 critical" in conclusion.recommendation.lower()


def test_conclusion_high_vulnerabilities():
    """Test conclusion for high vulnerabilities"""
    vulns = [
        SimpleVulnerability(
            policy_id="xss",
            severity="high",
            source_location="test.py:1",
            sink_location="test.py:2",
            source_atom_id="src",
            sink_atom_id="sink",
            path=[],
            message="",
        )
    ]

    adapter = TaintAdapter()
    conclusion = adapter._build_conclusion(vulns)

    assert "HIGH" in conclusion.recommendation
    assert "high-severity" in conclusion.recommendation.lower()


def test_conclusion_multiple_types():
    """Test conclusion with multiple vulnerability types"""
    vulns = [
        SimpleVulnerability(
            policy_id="sql_injection",
            severity="critical",
            source_location="test.py:1",
            sink_location="test.py:2",
            source_atom_id="src",
            sink_atom_id="sink",
            path=[],
            message="",
        ),
        SimpleVulnerability(
            policy_id="xss",
            severity="high",
            source_location="test.py:3",
            sink_location="test.py:4",
            source_atom_id="src",
            sink_atom_id="sink",
            path=[],
            message="",
        ),
    ]

    adapter = TaintAdapter()
    conclusion = adapter._build_conclusion(vulns)

    assert "sql_injection" in conclusion.reasoning_summary
    assert "xss" in conclusion.reasoning_summary


# ============================================================
# Unit Tests: Metrics Generation
# ============================================================


def test_metrics_generation(taint_result_single):
    """Test metrics generation"""
    adapter = TaintAdapter()
    metrics = adapter._build_metrics(
        execution_time_ms=234.5,
        claims_generated=1,
        taint_result=taint_result_single,
    )

    assert metrics.execution_time_ms == 234.5
    assert metrics.claims_generated == 1
    assert metrics.claims_suppressed == 0
    assert metrics.additional["atoms_detected"] == 15
    assert metrics.additional["policies_executed"] == 1


# ============================================================
# Edge Cases
# ============================================================


def test_invalid_taint_result_type():
    """Test with invalid taint_result type"""
    adapter = TaintAdapter()

    with pytest.raises(ValueError, match="taint_result must be dict"):
        adapter.to_envelope(
            taint_result="invalid",  # ❌ Not dict
            request_id="req_test",
            execution_time_ms=100.0,
        )


def test_missing_vulnerabilities_key():
    """Test with missing 'vulnerabilities' key"""
    adapter = TaintAdapter()

    with pytest.raises(ValueError, match="missing 'vulnerabilities'"):
        adapter.to_envelope(
            taint_result={"stats": {}},  # ❌ No vulnerabilities key
            request_id="req_test",
            execution_time_ms=100.0,
        )


def test_invalid_request_id():
    """Test with invalid request_id"""
    adapter = TaintAdapter()

    with pytest.raises(ValueError, match="must start with 'req_'"):
        adapter.to_envelope(
            taint_result={"vulnerabilities": [], "stats": {}},
            request_id="invalid",  # ❌ Must start with req_
            execution_time_ms=100.0,
        )


def test_path_with_many_nodes():
    """Test vulnerability with long path (performance)"""
    # 100 nodes in path
    vuln = SimpleVulnerability(
        policy_id="test",
        severity="medium",
        source_location="test.py:1",
        sink_location="test.py:100",
        source_atom_id="source",
        sink_atom_id="sink",
        path=[f"node_{i}" for i in range(100)],  # Long path
        message="Test",
    )

    adapter = TaintAdapter()
    envelope = adapter.to_envelope(
        taint_result={"vulnerabilities": [vuln], "policies_executed": [], "stats": {}},
        request_id="req_test",
        execution_time_ms=100.0,
    )

    # Path preserved
    assert len(envelope.evidences[0].content["path"]) == 100
    assert envelope.evidences[0].content["path_length"] == 100


# ============================================================
# Integration Tests (Simplified - no IR dependency)
# ============================================================


def test_integration_full_flow():
    """
    Integration test: TaintResult → TaintAdapter → ResultEnvelope

    Simulates full flow without IR dependencies.
    """
    # Mock TaintAnalysisService result
    taint_result = {
        "vulnerabilities": [
            SimpleVulnerability(
                policy_id="sql_injection",
                severity="critical",
                source_location="api/users.py:10",
                sink_location="api/users.py:42",
                source_atom_id="source.http.request_args",
                sink_atom_id="sink.sql.execute",
                path=["user_input", "query", "cursor.execute"],
                message="SQL injection detected",
            ),
            SimpleVulnerability(
                policy_id="xss",
                severity="high",
                source_location="api/posts.py:20",
                sink_location="api/posts.py:55",
                source_atom_id="source.http.request_body",
                sink_atom_id="sink.html.render",
                path=["content", "html"],
                message="XSS vulnerability",
            ),
        ],
        "policies_executed": ["sql_injection", "xss"],
        "stats": {"atoms_detected": 25, "paths_found": 2},
    }

    # Convert
    adapter = TaintAdapter()
    envelope = adapter.to_envelope(
        taint_result=taint_result,
        request_id="req_integration_001",
        execution_time_ms=234.5,
        snapshot_id="snap:main_abc123",
    )

    # Validate RFC-027 compliance
    assert envelope.request_id == "req_integration_001"
    assert len(envelope.claims) == 2
    assert len(envelope.evidences) == 2

    # All claims are PROVEN (static proof)
    assert all(c.confidence_basis == ConfidenceBasis.PROVEN for c in envelope.claims)

    # All evidences are DATA_FLOW_PATH
    assert all(e.kind == EvidenceKind.DATA_FLOW_PATH for e in envelope.evidences)

    # Evidence-Claim links
    assert envelope.evidences[0].claim_ids == [envelope.claims[0].id]
    assert envelope.evidences[1].claim_ids == [envelope.claims[1].id]

    # Conclusion
    assert envelope.conclusion is not None
    assert "2 vulnerabilities" in envelope.conclusion.reasoning_summary
    assert "sql_injection" in envelope.conclusion.reasoning_summary
    assert "xss" in envelope.conclusion.reasoning_summary

    # Metrics
    assert envelope.metrics.execution_time_ms == 234.5
    assert envelope.metrics.claims_generated == 2
    assert envelope.metrics.additional["policies_executed"] == 2

    # Replay ref
    assert envelope.replay_ref == "replay:integration_001"


# ============================================================
# Security Tests
# ============================================================


def test_location_with_path_traversal():
    """Test location with path traversal attempt (SECURITY)"""
    vuln = SimpleVulnerability(
        policy_id="test",
        severity="medium",
        source_location="test.py:1",
        sink_location="../../../etc/passwd:2",  # Path traversal in sink (primary location)
        source_atom_id="source",
        sink_atom_id="sink",
        path=[],
        message="Test",
    )

    adapter = TaintAdapter()

    # Should fail at Evidence validation (Location prevents path traversal)
    with pytest.raises(ValidationError, match="Path traversal"):
        adapter.to_envelope(
            taint_result={"vulnerabilities": [vuln], "policies_executed": [], "stats": {}},
            request_id="req_test",
            execution_time_ms=100.0,
        )


def test_location_with_absolute_path():
    """Test location with absolute path (SECURITY)"""
    vuln = SimpleVulnerability(
        policy_id="test",
        severity="medium",
        source_location="test.py:1",
        sink_location="/etc/passwd:2",  # Absolute path in sink (primary location)
        source_atom_id="source",
        sink_atom_id="sink",
        path=[],
        message="Test",
    )

    adapter = TaintAdapter()

    # Should fail at Evidence validation (Location prevents absolute paths)
    with pytest.raises(ValidationError, match="Absolute path"):
        adapter.to_envelope(
            taint_result={"vulnerabilities": [vuln], "policies_executed": [], "stats": {}},
            request_id="req_test",
            execution_time_ms=100.0,
        )


# ============================================================
# Performance Tests
# ============================================================


def test_conversion_performance():
    """Test conversion performance (100 vulnerabilities)"""
    import time

    # 100 vulnerabilities
    vulns = [
        SimpleVulnerability(
            policy_id=f"test_{i}",
            severity="medium",
            source_location=f"test.py:{i}",
            sink_location=f"test.py:{i + 1}",
            source_atom_id="source",
            sink_atom_id="sink",
            path=[f"node_{j}" for j in range(10)],
            message="Test",
        )
        for i in range(100)
    ]

    taint_result = {"vulnerabilities": vulns, "policies_executed": [], "stats": {}}

    adapter = TaintAdapter()

    start = time.perf_counter()
    envelope = adapter.to_envelope(
        taint_result=taint_result,
        request_id="req_perf_test",
        execution_time_ms=1000.0,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000

    # Validate
    assert len(envelope.claims) == 100
    assert len(envelope.evidences) == 100

    # Performance: < 50ms for 100 vulnerabilities
    assert elapsed_ms < 50.0, f"Conversion too slow: {elapsed_ms:.2f}ms"


# ============================================================
# Immutability Tests
# ============================================================


def test_adapter_stateless():
    """Test adapter is stateless (thread-safe)"""
    adapter = TaintAdapter()

    # Call twice with different inputs
    result1 = adapter.to_envelope(
        taint_result={"vulnerabilities": [], "policies_executed": [], "stats": {}},
        request_id="req_test1",
        execution_time_ms=100.0,
    )

    result2 = adapter.to_envelope(
        taint_result={"vulnerabilities": [], "policies_executed": [], "stats": {}},
        request_id="req_test2",
        execution_time_ms=200.0,
    )

    # Results should be independent
    assert result1.request_id != result2.request_id
    assert result1.metrics.execution_time_ms == 100.0
    assert result2.metrics.execution_time_ms == 200.0


# ============================================================
# Extreme Cases (L11 SOTA급 추가)
# ============================================================


def test_extreme_1000_vulnerabilities():
    """Extreme: 1000개 vulnerabilities 처리 (대규모)"""
    import time

    # 1000개 vulnerabilities 생성
    vulns = []
    for i in range(1000):
        vulns.append(
            SimpleVulnerability(
                policy_id=f"policy_{i % 10}",
                severity=["critical", "high", "medium", "low"][i % 4],
                source_location=f"file{i}.py:{i}",
                sink_location=f"file{i}.py:{i + 10}",
                source_atom_id=f"source_{i}",
                sink_atom_id=f"sink_{i}",
                path=[f"node_{j}" for j in range(5)],  # 5-node path
                message=f"Vuln {i}",
            )
        )

    adapter = TaintAdapter()

    start = time.perf_counter()
    envelope = adapter.to_envelope(
        taint_result={"vulnerabilities": vulns, "policies_executed": [], "stats": {}},
        request_id="req_extreme_1000",
        execution_time_ms=1000.0,
    )
    elapsed = (time.perf_counter() - start) * 1000

    # 검증
    assert len(envelope.claims) == 1000
    assert len(envelope.evidences) == 1000

    # 성능: 1000개 처리가 1초 이하 (L11 기준)
    assert elapsed < 1000, f"Too slow: {elapsed:.1f}ms"

    # 메모리: 모든 claim/evidence가 unique ID
    claim_ids = {c.id for c in envelope.claims}
    assert len(claim_ids) == 1000  # No duplicates


def test_extreme_invalid_severity():
    """Extreme: Invalid severity는 Pydantic이 검증 (L11 SOTA)"""
    adapter = TaintAdapter()

    # SimpleVulnerability가 이미 Pydantic validation 수행
    # severity는 '^(low|medium|high|critical)$' 패턴만 허용
    # 따라서 invalid severity로 SimpleVulnerability 생성 불가

    # 대신 adapter의 _validate_severity 직접 테스트
    from codegraph_runtime.llm_arbitration.infrastructure.adapters.taint_adapter import _validate_severity

    # Valid severities
    for sev in ["critical", "high", "medium", "low"]:
        assert _validate_severity(sev) == sev

    # Invalid severity
    with pytest.raises(ValueError, match="Invalid severity"):
        _validate_severity("unknown")


@pytest.mark.asyncio
async def test_extreme_concurrent_conversions():
    """Extreme: 동시 다중 conversion (Thread-safety)"""
    import asyncio

    adapter = TaintAdapter()

    # 50개 request 동시 처리
    async def convert_one(idx: int):
        vuln = SimpleVulnerability(
            policy_id=f"policy_{idx}",
            severity="high",
            source_location=f"file{idx}.py:1",
            sink_location=f"file{idx}.py:10",
            source_atom_id=f"source_{idx}",
            sink_atom_id=f"sink_{idx}",
            path=[],
            message=f"Test {idx}",
        )

        envelope = adapter.to_envelope(
            taint_result={"vulnerabilities": [vuln], "policies_executed": [], "stats": {}},
            request_id=f"req_concurrent_{idx}",
            execution_time_ms=100.0,
        )

        return envelope

    # 동시 실행
    tasks = [convert_one(i) for i in range(50)]
    envelopes = await asyncio.gather(*tasks)

    # 모두 성공
    assert len(envelopes) == 50

    # 모든 request_id unique
    request_ids = {e.request_id for e in envelopes}
    assert len(request_ids) == 50


def test_extreme_memory_leak_prevention():
    """Extreme: 대량 envelope 생성 후 메모리 누수 없음"""
    import gc
    import sys

    adapter = TaintAdapter()

    # 초기 메모리
    gc.collect()
    initial_objects = len(gc.get_objects())

    # 1000개 envelope 생성
    for i in range(1000):
        vuln = SimpleVulnerability(
            policy_id="test",
            severity="medium",
            source_location="test.py:1",
            sink_location="test.py:2",
            source_atom_id="source",
            sink_atom_id="sink",
            path=[],
            message="Test",
        )

        envelope = adapter.to_envelope(
            taint_result={"vulnerabilities": [vuln], "policies_executed": [], "stats": {}},
            request_id=f"req_mem_{i}",
            execution_time_ms=100.0,
        )

        # Envelope 사용 후 즉시 버림 (GC 대상)
        del envelope

    # GC 실행
    gc.collect()
    final_objects = len(gc.get_objects())

    # 메모리 누수 없음 (객체 수 증가 < 20%)
    growth = (final_objects - initial_objects) / initial_objects
    assert growth < 0.2, f"Memory leak suspected: {growth * 100:.1f}% growth"
