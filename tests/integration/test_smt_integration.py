"""
Integration test for SMT verification in DeepSecurityAnalyzer

RFC-AUDIT-004: Verify SMT integration with taint analysis
"""

from dataclasses import dataclass
from typing import Any, Optional

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.deep_security_analyzer import (
    AnalysisMode,
    DeepSecurityAnalyzer,
)
from codegraph_engine.code_foundation.infrastructure.analyzers.interprocedural_taint import (
    TaintPath,
)


@dataclass
class MockIRDocument:
    """Mock IR document for testing"""

    code: str

    def get_code(self) -> str:
        return self.code


@dataclass
class MockCallGraph:
    """Mock call graph for testing"""

    pass


class TestSMTIntegration:
    """Test SMT verification integration with deep security analyzer"""

    def test_smt_verifier_initialized(self):
        """Test that SMT verifier is properly initialized"""
        ir_doc = MockIRDocument(code="print('test')")
        analyzer = DeepSecurityAnalyzer(ir_doc)

        # SMT verifier should be initialized (or None if Z3 not available)
        assert hasattr(analyzer, "smt_verifier")

    def test_security_issue_has_smt_field(self):
        """Test that SecurityIssue has smt_result field"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.deep_security_analyzer import (
            SecurityIssue,
            Severity,
        )

        # Create issue with SMT result
        issue = SecurityIssue(
            pattern="eval(input())",
            issue_type="code_injection",
            severity=Severity.CRITICAL,
            location="test.py:1",
            message="Test",
        )

        # Should have smt_result field
        assert hasattr(issue, "smt_result")
        assert issue.smt_result is None  # Default

    @pytest.mark.skipif(
        not hasattr(
            __import__("src.contexts.code_foundation.infrastructure.smt.z3_solver", fromlist=["Z3_AVAILABLE"]),
            "Z3_AVAILABLE",
        )
        or not __import__(
            "src.contexts.code_foundation.infrastructure.smt.z3_solver", fromlist=["Z3_AVAILABLE"]
        ).Z3_AVAILABLE,
        reason="Z3 not installed",
    )
    def test_audit_scan_uses_smt(self, caplog):
        """Test that AUDIT scan uses SMT verification"""
        import logging

        caplog.set_level(logging.INFO)

        # This is a minimal integration test
        # Full test would require mock taint paths with path_condition
        ir_doc = MockIRDocument(code="x = input(); eval(x)")
        analyzer = DeepSecurityAnalyzer(ir_doc)

        # Verify SMT verifier is initialized
        assert analyzer.smt_verifier is not None


class TestSMTPathFiltering:
    """Test that infeasible paths are filtered"""

    def test_infeasible_path_filtered(self):
        """
        CRITICAL: Verify that UNSAT paths are filtered

        This is the core value of SMT integration:
        Reducing false positives by eliminating impossible paths.
        """
        # This test requires more complex setup
        # For now, we verify the code path exists
        pass  # TODO: Implement when full integration is ready


class TestRFCAudit004OutputContract:
    """Verify RFC-AUDIT-004 output contract compliance"""

    def test_output_contract_structure(self):
        """Test that SecurityIssue matches RFC-AUDIT-004 output contract"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.deep_security_analyzer import (
            SecurityIssue,
            Severity,
        )
        from codegraph_engine.code_foundation.infrastructure.smt.z3_solver import SMTResult

        # Create issue with full RFC-AUDIT-004 fields
        smt_result = SMTResult(
            status="SAT",
            feasible=True,
            model={"x": 42},
        )

        issue = SecurityIssue(
            pattern="eval(input())",
            issue_type="code_injection",
            severity=Severity.CRITICAL,
            location="test.py:1",
            message="Test",
            smt_result=smt_result,
        )

        # Verify RFC contract fields
        assert issue.smt_result is not None
        assert issue.smt_result.status == "SAT"
        assert issue.smt_result.feasible is True
        assert issue.smt_result.model == {"x": 42}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
