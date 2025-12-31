"""Tests for SARIF formatter."""

import json
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.domain.taint import SimpleVulnerability
from codegraph_engine.code_foundation.infrastructure.taint.formatters import SarifFormatter
from codegraph_engine.code_foundation.infrastructure.taint.formatters.sarif_formatter import (
    SarifConfig,
)


@pytest.fixture
def sample_vulnerabilities() -> list[SimpleVulnerability]:
    """Sample vulnerabilities for testing."""
    return [
        SimpleVulnerability(
            policy_id="sql-injection",
            severity="high",
            source_location="app.py:10",
            sink_location="app.py:25",
            source_atom_id="input.http.flask",
            sink_atom_id="sink.sql.sqlite3",
            path=["app.py:10", "app.py:15", "app.py:25"],
        ),
        SimpleVulnerability(
            policy_id="xss",
            severity="high",
            source_location="views.py:5",
            sink_location="views.py:20",
            source_atom_id="input.http.flask",
            sink_atom_id="sink.html.flask",
            path=["views.py:5", "views.py:20"],
        ),
    ]


class TestSarifFormatter:
    """Tests for SarifFormatter."""

    def test_format_empty_list(self):
        """Test formatting empty vulnerability list."""
        formatter = SarifFormatter()
        result = formatter.format([])

        assert result["$schema"] == "https://json.schemastore.org/sarif-2.1.0.json"
        assert result["version"] == "2.1.0"
        assert len(result["runs"]) == 1
        assert result["runs"][0]["results"] == []

    def test_format_with_vulnerabilities(self, sample_vulnerabilities):
        """Test formatting vulnerabilities."""
        formatter = SarifFormatter()
        result = formatter.format(sample_vulnerabilities)

        run = result["runs"][0]

        # Check tool info
        assert run["tool"]["driver"]["name"] == "Semantica"

        # Check rules
        rules = run["tool"]["driver"]["rules"]
        assert len(rules) == 2
        rule_ids = [r["id"] for r in rules]
        assert "sql-injection" in rule_ids
        assert "xss" in rule_ids

        # Check results
        results = run["results"]
        assert len(results) == 2

        # Check first result
        sql_result = next(r for r in results if r["ruleId"] == "sql-injection")
        assert "SQL Injection" in sql_result["message"]["text"]
        assert sql_result["level"] == "error"
        assert "fingerprints" in sql_result

    def test_code_flows_included(self, sample_vulnerabilities):
        """Test that code flows are included."""
        formatter = SarifFormatter()
        result = formatter.format(sample_vulnerabilities)

        sql_result = result["runs"][0]["results"][0]

        assert "codeFlows" in sql_result
        flow = sql_result["codeFlows"][0]

        assert "threadFlows" in flow
        locations = flow["threadFlows"][0]["locations"]

        # Should have source, intermediate, and sink
        assert len(locations) >= 2
        assert locations[0]["kinds"] == ["source"]
        assert locations[-1]["kinds"] == ["sink"]

    def test_code_flows_disabled(self, sample_vulnerabilities):
        """Test disabling code flows."""
        config = SarifConfig(include_code_flows=False)
        formatter = SarifFormatter(config=config)
        result = formatter.format(sample_vulnerabilities)

        assert "codeFlows" not in result["runs"][0]["results"][0]

    def test_to_json(self, sample_vulnerabilities):
        """Test JSON string output."""
        formatter = SarifFormatter()
        json_str = formatter.to_json(sample_vulnerabilities)

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["version"] == "2.1.0"

    def test_write_to_file(self, sample_vulnerabilities, tmp_path):
        """Test writing to file."""
        formatter = SarifFormatter()
        output_path = tmp_path / "results.sarif"

        formatter.write_to_file(sample_vulnerabilities, output_path)

        assert output_path.exists()
        content = json.loads(output_path.read_text())
        assert content["version"] == "2.1.0"

    def test_relative_paths(self, sample_vulnerabilities):
        """Test that paths are made relative."""
        formatter = SarifFormatter()
        base_path = Path("/home/user/project")
        result = formatter.format(sample_vulnerabilities, base_path)

        location = result["runs"][0]["results"][0]["locations"][0]
        physical = location["physicalLocation"]

        assert physical["artifactLocation"]["uriBaseId"] == "%SRCROOT%"

    def test_cwe_mapping(self, sample_vulnerabilities):
        """Test CWE ID extraction."""
        formatter = SarifFormatter()
        result = formatter.format(sample_vulnerabilities)

        rules = result["runs"][0]["tool"]["driver"]["rules"]
        sql_rule = next(r for r in rules if r["id"] == "sql-injection")

        assert "CWE-89" in sql_rule["properties"]["tags"]
        assert "cwe.mitre.org" in sql_rule["helpUri"]

    def test_security_severity(self, sample_vulnerabilities):
        """Test security severity for GitHub."""
        formatter = SarifFormatter()
        result = formatter.format(sample_vulnerabilities)

        rules = result["runs"][0]["tool"]["driver"]["rules"]
        for rule in rules:
            # Should have numeric severity
            severity = rule["properties"]["security-severity"]
            assert float(severity) > 0

    def test_fingerprint_stable(self, sample_vulnerabilities):
        """Test that fingerprints are stable."""
        formatter = SarifFormatter()

        result1 = formatter.format(sample_vulnerabilities)
        result2 = formatter.format(sample_vulnerabilities)

        fp1 = result1["runs"][0]["results"][0]["fingerprints"]["semantica/v1"]
        fp2 = result2["runs"][0]["results"][0]["fingerprints"]["semantica/v1"]

        assert fp1 == fp2

    def test_custom_config(self):
        """Test custom configuration."""
        config = SarifConfig(
            tool_name="MyScanner",
            tool_version="2.0.0",
            pretty_print=False,
        )
        formatter = SarifFormatter(config=config)
        result = formatter.format([])

        assert result["runs"][0]["tool"]["driver"]["name"] == "MyScanner"
        assert result["runs"][0]["tool"]["driver"]["version"] == "2.0.0"
