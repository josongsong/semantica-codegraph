"""
Test Taint Domain Models

CRITICAL: Tests validation, relationships, no fake data.
"""

from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from codegraph_engine.code_foundation.domain.taint.atoms import MatchRule
from codegraph_engine.code_foundation.domain.taint.models import (
    DetectedAtoms,
    DetectedSanitizer,
    DetectedSink,
    DetectedSource,
    TaintFlow,
    Vulnerability,
)


class TestDetectedEntity:
    """Test DetectedSource, DetectedSink, DetectedSanitizer."""

    def test_detected_source_base_case(self):
        """Base case: Valid detected source."""
        source = DetectedSource(
            atom_id="input.http.flask",
            entity_id="var_123",
            entity_type="variable",
            tags=["untrusted", "web"],
            severity="high",
            location={
                "file_path": "app.py",
                "line": 15,
                "column": 4,
            },
            match_rule=MatchRule(base_type="flask.Request", read="args"),
        )

        assert source.atom_id == "input.http.flask"
        assert source.entity_id == "var_123"
        assert "untrusted" in source.tags
        assert source.location["file_path"] == "app.py"

    def test_detected_sink_base_case(self):
        """Base case: Valid detected sink."""
        sink = DetectedSink(
            atom_id="sink.sql.sqlite3",
            entity_id="expr_456",
            entity_type="call",
            tags=["injection", "db"],
            severity="critical",
            location={
                "file_path": "app.py",
                "line": 20,
                "column": 4,
            },
            matched_arg_indices=[0],
            match_rule=MatchRule(base_type="sqlite3.Cursor", call="execute"),
        )

        assert sink.matched_arg_indices == [0]
        assert sink.severity == "critical"

    def test_detected_sanitizer_base_case(self):
        """Base case: Valid detected sanitizer."""
        sanitizer = DetectedSanitizer(
            atom_id="barrier.sql",
            entity_id="expr_789",
            entity_type="call",
            tags=["safety", "db"],
            severity="medium",
            location={
                "file_path": "app.py",
                "line": 18,
                "column": 4,
            },
            scope="return",
            match_rule=MatchRule(call="escape_sql", scope="return"),
        )

        assert sanitizer.scope == "return"

    def test_validation_location_missing_file_path(self):
        """Edge case: Location must have file_path and line."""
        with pytest.raises(ValidationError, match="file_path"):
            DetectedSource(
                atom_id="test",
                entity_id="var_1",
                entity_type="variable",
                tags=["test"],
                severity="low",
                location={"line": 10},  # Missing file_path
                match_rule=MatchRule(base_type="test"),
            )

    def test_validation_negative_arg_index(self):
        """Edge case: Negative arg index should fail."""
        with pytest.raises(ValidationError, match="non-negative"):
            DetectedSink(
                atom_id="test",
                entity_id="expr_1",
                entity_type="call",
                tags=["test"],
                severity="low",
                location={"file_path": "test.py", "line": 10},
                matched_arg_indices=[-1],
                match_rule=MatchRule(base_type="test"),
            )

    def test_validation_invalid_sanitizer_scope(self):
        """Edge case: Invalid sanitizer scope should fail."""
        with pytest.raises(ValidationError, match="pattern"):
            DetectedSanitizer(
                atom_id="test",
                entity_id="expr_1",
                entity_type="call",
                tags=["test"],
                severity="low",
                location={"file_path": "test.py", "line": 10},
                scope="invalid",  # Must be "return" or "guard"
                match_rule=MatchRule(call="test"),
            )

    def test_immutability(self):
        """Edge case: Detected entities should be immutable."""
        source = DetectedSource(
            atom_id="test",
            entity_id="var_1",
            entity_type="variable",
            tags=["test"],
            severity="low",
            location={"file_path": "test.py", "line": 10},
            match_rule=MatchRule(base_type="test"),
        )

        with pytest.raises(ValidationError):
            source.atom_id = "changed"  # type: ignore


class TestTaintFlow:
    """Test TaintFlow value object."""

    def test_base_case(self):
        """Base case: Valid taint flow."""
        flow = TaintFlow(
            nodes=["var_user_id", "var_query", "call_execute"],
            edges=["dfg", "dfg"],
            length=3,
            has_sanitizer=False,
            confidence=0.95,
        )

        assert flow.length == 3
        assert len(flow.nodes) == 3
        assert len(flow.edges) == 2
        assert flow.confidence == 0.95

    def test_validation_empty_nodes(self):
        """Edge case: Empty nodes should fail."""
        with pytest.raises(ValidationError, match="at least 1"):
            TaintFlow(
                nodes=[],
                length=0,
                confidence=0.5,
            )

    def test_validation_length_mismatch(self):
        """Edge case: Length must match nodes length."""
        with pytest.raises(ValidationError, match="does not match"):
            TaintFlow(
                nodes=["a", "b", "c"],
                length=5,  # Wrong!
                confidence=0.5,
            )

    def test_validation_edges_count(self):
        """Edge case: Edges count must be nodes - 1."""
        with pytest.raises(ValidationError, match="should be 2"):
            TaintFlow(
                nodes=["a", "b", "c"],
                edges=["dfg"],  # Should be 2 edges!
                length=3,
                confidence=0.5,
            )

    def test_validation_confidence_range(self):
        """Edge case: Confidence must be 0.0-1.0."""
        with pytest.raises(ValidationError):
            TaintFlow(
                nodes=["a"],
                length=1,
                confidence=1.5,  # > 1.0
            )

        with pytest.raises(ValidationError):
            TaintFlow(
                nodes=["a"],
                length=1,
                confidence=-0.1,  # < 0.0
            )

    def test_immutability(self):
        """Edge case: TaintFlow should be immutable."""
        flow = TaintFlow(
            nodes=["a", "b"],
            length=2,
            confidence=0.5,
        )

        with pytest.raises(ValidationError):
            flow.length = 5  # type: ignore


class TestVulnerability:
    """Test Vulnerability entity."""

    def test_base_case(self):
        """Base case: Valid vulnerability."""
        source = DetectedSource(
            atom_id="input.http.flask",
            entity_id="var_1",
            entity_type="variable",
            tags=["untrusted"],
            severity="high",
            location={"file_path": "app.py", "line": 10},
            match_rule=MatchRule(base_type="flask.Request", read="args"),
        )

        sink = DetectedSink(
            atom_id="sink.sql.sqlite3",
            entity_id="expr_1",
            entity_type="call",
            tags=["injection"],
            severity="critical",
            location={"file_path": "app.py", "line": 20},
            matched_arg_indices=[0],
            match_rule=MatchRule(base_type="sqlite3.Cursor", call="execute"),
        )

        flow = TaintFlow(
            nodes=["var_1", "var_2", "expr_1"],
            length=3,
            confidence=0.95,
        )

        vuln = Vulnerability(
            policy_id="sql-injection",
            policy_name="SQL Injection",
            severity="critical",
            source=source,
            sink=sink,
            flow=flow,
            confidence=0.95,
            cwe="CWE-89",
            owasp="A03:2021-Injection",
        )

        assert vuln.policy_id == "sql-injection"
        assert vuln.severity == "critical"
        assert vuln.confidence == 0.95
        assert isinstance(vuln.id, UUID)
        assert isinstance(vuln.created_at, datetime)

    def test_to_dict(self):
        """Base case: Serialize to dict."""
        source = DetectedSource(
            atom_id="test.source",
            entity_id="var_1",
            entity_type="variable",
            tags=["test"],
            severity="low",
            location={"file_path": "test.py", "line": 1},
            match_rule=MatchRule(base_type="test"),
        )

        sink = DetectedSink(
            atom_id="test.sink",
            entity_id="expr_1",
            entity_type="call",
            tags=["test"],
            severity="low",
            location={"file_path": "test.py", "line": 2},
            matched_arg_indices=[0],
            match_rule=MatchRule(base_type="test"),
        )

        flow = TaintFlow(nodes=["a", "b"], length=2, confidence=0.5)

        vuln = Vulnerability(
            policy_id="test-policy",
            policy_name="Test Policy",
            severity="low",
            source=source,
            sink=sink,
            flow=flow,
            confidence=0.5,
        )

        data = vuln.to_dict()

        assert data["policy_id"] == "test-policy"
        assert data["severity"] == "low"
        assert data["source"]["atom_id"] == "test.source"
        assert data["sink"]["atom_id"] == "test.sink"
        assert data["flow"]["length"] == 2

    def test_get_file_path(self):
        """Base case: Get file path."""
        source = DetectedSource(
            atom_id="test",
            entity_id="var_1",
            entity_type="variable",
            tags=["test"],
            severity="low",
            location={"file_path": "app.py", "line": 10},
            match_rule=MatchRule(base_type="test"),
        )

        sink = DetectedSink(
            atom_id="test",
            entity_id="expr_1",
            entity_type="call",
            tags=["test"],
            severity="low",
            location={"file_path": "app.py", "line": 20},
            matched_arg_indices=[],
            match_rule=MatchRule(base_type="test"),
        )

        flow = TaintFlow(nodes=["a"], length=1, confidence=0.5)

        vuln = Vulnerability(
            policy_id="test",
            policy_name="Test",
            severity="low",
            source=source,
            sink=sink,
            flow=flow,
            confidence=0.5,
        )

        assert vuln.get_file_path() == "app.py"
        assert vuln.get_line() == 10

    def test_validation_invalid_severity(self):
        """Edge case: Invalid severity should fail."""
        source = DetectedSource(
            atom_id="test",
            entity_id="var_1",
            entity_type="variable",
            tags=["test"],
            severity="low",
            location={"file_path": "test.py", "line": 1},
            match_rule=MatchRule(base_type="test"),
        )

        sink = DetectedSink(
            atom_id="test",
            entity_id="expr_1",
            entity_type="call",
            tags=["test"],
            severity="low",
            location={"file_path": "test.py", "line": 2},
            matched_arg_indices=[],
            match_rule=MatchRule(base_type="test"),
        )

        flow = TaintFlow(nodes=["a"], length=1, confidence=0.5)

        with pytest.raises(ValidationError, match="pattern"):
            Vulnerability(
                policy_id="test",
                policy_name="Test",
                severity="super_high",  # Invalid!
                source=source,
                sink=sink,
                flow=flow,
                confidence=0.5,
            )

    def test_validation_invalid_cwe_format(self):
        """Edge case: Invalid CWE format should fail."""
        source = DetectedSource(
            atom_id="test",
            entity_id="var_1",
            entity_type="variable",
            tags=["test"],
            severity="low",
            location={"file_path": "test.py", "line": 1},
            match_rule=MatchRule(base_type="test"),
        )

        sink = DetectedSink(
            atom_id="test",
            entity_id="expr_1",
            entity_type="call",
            tags=["test"],
            severity="low",
            location={"file_path": "test.py", "line": 2},
            matched_arg_indices=[],
            match_rule=MatchRule(base_type="test"),
        )

        flow = TaintFlow(nodes=["a"], length=1, confidence=0.5)

        with pytest.raises(ValidationError, match="pattern"):
            Vulnerability(
                policy_id="test",
                policy_name="Test",
                severity="low",
                source=source,
                sink=sink,
                flow=flow,
                confidence=0.5,
                cwe="invalid-format",  # Must be "CWE-\d+"
            )


class TestDetectedAtoms:
    """Test DetectedAtoms collection."""

    def test_base_case_empty(self):
        """Base case: Empty collection."""
        detected = DetectedAtoms()

        assert detected.count_sources() == 0
        assert detected.count_sinks() == 0
        assert detected.count_sanitizers() == 0

    def test_base_case_with_entities(self):
        """Base case: Collection with entities."""
        source = DetectedSource(
            atom_id="test.source",
            entity_id="var_1",
            entity_type="variable",
            tags=["untrusted", "web"],
            severity="high",
            location={"file_path": "test.py", "line": 1},
            match_rule=MatchRule(base_type="test"),
        )

        sink = DetectedSink(
            atom_id="test.sink",
            entity_id="expr_1",
            entity_type="call",
            tags=["injection", "db"],
            severity="critical",
            location={"file_path": "test.py", "line": 2},
            matched_arg_indices=[0],
            match_rule=MatchRule(base_type="test"),
        )

        detected = DetectedAtoms(
            sources=[source],
            sinks=[sink],
        )

        assert detected.count_sources() == 1
        assert detected.count_sinks() == 1
        assert detected.count_sanitizers() == 0

    def test_get_by_tag(self):
        """Base case: Filter by tag."""
        source1 = DetectedSource(
            atom_id="test1",
            entity_id="var_1",
            entity_type="variable",
            tags=["untrusted", "web"],
            severity="high",
            location={"file_path": "test.py", "line": 1},
            match_rule=MatchRule(base_type="test"),
        )

        source2 = DetectedSource(
            atom_id="test2",
            entity_id="var_2",
            entity_type="variable",
            tags=["untrusted", "file"],
            severity="medium",
            location={"file_path": "test.py", "line": 2},
            match_rule=MatchRule(base_type="test"),
        )

        detected = DetectedAtoms(sources=[source1, source2])

        web_sources = detected.get_sources_by_tag("web")
        assert len(web_sources) == 1
        assert web_sources[0].atom_id == "test1"

        untrusted_sources = detected.get_sources_by_tag("untrusted")
        assert len(untrusted_sources) == 2

    def test_immutability(self):
        """Edge case: DetectedAtoms should be immutable."""
        detected = DetectedAtoms()

        with pytest.raises(ValidationError):
            detected.sources = []  # type: ignore
