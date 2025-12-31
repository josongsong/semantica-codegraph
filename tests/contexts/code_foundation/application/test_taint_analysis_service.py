"""
Test Taint Analysis Service

CRITICAL: Tests application orchestration.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from codegraph_engine.code_foundation.application.taint_analysis_service import TaintAnalysisService
from codegraph_engine.code_foundation.domain.taint.atoms import AtomSpec, MatchRule
from codegraph_engine.code_foundation.domain.taint.policy import Policy, PolicyCondition, PolicyFlow, PolicyGrammar


class TestTaintAnalysisService:
    """Test Taint Analysis Service"""

    @pytest.fixture
    def mock_atom_repo(self):
        """Mock atom repository"""
        repo = Mock()
        repo.load_atoms.return_value = [
            AtomSpec(
                id="input.http.flask",
                kind="source",
                tags=["untrusted"],
                match_rules=[MatchRule(base_type="flask.Request")],
            ),
            AtomSpec(
                id="sink.sql.sqlite3",
                kind="sink",
                tags=["injection"],
                match_rules=[MatchRule(base_type="sqlite3.Cursor", call="execute")],
            ),
        ]
        return repo

    @pytest.fixture
    def mock_policy_repo(self):
        """Mock policy repository"""
        repo = Mock()
        repo.load_policies.return_value = [
            Policy(
                id="sql-injection",
                name="SQL Injection",
                severity="critical",
                grammar=PolicyGrammar(
                    WHEN=PolicyCondition(tag="untrusted"),
                    FLOWS=[PolicyFlow(id="sink.sql.sqlite3")],
                ),
            )
        ]
        return repo

    @pytest.fixture
    def mock_matcher(self):
        """Mock matcher with proper return values"""
        from codegraph_engine.code_foundation.domain.taint.models import DetectedAtoms

        matcher = Mock()
        matcher.match_call.return_value = []
        matcher.match_all.return_value = DetectedAtoms(sources=[], sinks=[], sanitizers=[])
        return matcher

    @pytest.fixture
    def mock_validator(self):
        """Mock validator"""
        validator = Mock()
        validator.validate.return_value = True
        return validator

    @pytest.fixture
    def mock_control_parser(self):
        """Mock control parser"""
        parser = Mock()
        # Just return a mock object instead of actual ControlConfig
        mock_config = Mock()
        mock_config.rules_enabled = ["sql-injection"]
        mock_config.rules_disabled = []
        parser.parse.return_value = mock_config
        return parser

    @pytest.fixture
    def mock_policy_compiler(self):
        """Mock policy compiler"""
        compiler = Mock()
        # Return a simple mock
        mock_compiled = Mock()
        mock_compiled.flow_query = Mock()
        mock_compiled.constraints = {}
        compiler.compile.return_value = mock_compiled
        return compiler

    @pytest.fixture
    def service(
        self,
        mock_atom_repo,
        mock_policy_repo,
        mock_matcher,
        mock_validator,
        mock_control_parser,
        mock_policy_compiler,
    ):
        """Create service"""
        return TaintAnalysisService(
            atom_repo=mock_atom_repo,
            policy_repo=mock_policy_repo,
            matcher=mock_matcher,
            validator=mock_validator,
            control_parser=mock_control_parser,
            policy_compiler=mock_policy_compiler,
        )

    def test_analyze_basic(self, service):
        """Base case: Basic analysis"""
        ir_doc = Mock()

        results = service.analyze(ir_doc)

        assert "vulnerabilities" in results
        assert "detected_atoms" in results
        assert "policies_executed" in results
        assert "stats" in results

    def test_analyze_with_control(self, service, tmp_path):
        """Base case: Analysis with control config"""
        # Create semantica.toml
        toml_path = tmp_path / "semantica.toml"
        toml_path.write_text("""
[rules]
enabled = ["sql-injection"]
disabled = []
        """)

        ir_doc = Mock()
        results = service.analyze(ir_doc, control_config_path=toml_path)

        assert len(results["policies_executed"]) > 0

    def test_stats(self, service):
        """Base case: Service statistics"""
        ir_doc = Mock()
        service.analyze(ir_doc)

        stats = service.get_stats()

        assert stats["analyses_run"] == 1
        assert stats["policies_executed"] > 0
