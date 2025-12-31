"""
Test Schema Validator (Infrastructure)

Comprehensive tests for YAMLSchemaValidator.
"""

from pathlib import Path

import pytest
import yaml

from cwe.infrastructure.schema_validator import YAMLSchemaValidator


class TestYAMLSchemaValidator:
    """Test schema validation with all cases"""

    # ========== BASE CASES ==========

    def test_validate_catalog_valid(self, tmp_path):
        """Base case: Valid CWE catalog"""
        # Setup
        catalog_file = tmp_path / "cwe-89.yaml"
        catalog_data = {
            "metadata": {
                "cwe_id": "CWE-89",
                "name": "SQL Injection",
                "severity": "critical",
            },
            "sources": [{"id": "input.http.flask"}],
            "sinks": [{"id": "sink.sql.execute"}],
            "sanitizers": [],
            "policy": {"grammar": {}},
            "validation": {"min_precision": 0.90},
            "test_suite": {"juliet": {}},
        }
        with open(catalog_file, "w", encoding="utf-8") as f:
            yaml.dump(catalog_data, f)

        # Execute
        validator = YAMLSchemaValidator()
        is_valid, errors = validator.validate_catalog(catalog_file)

        # Verify
        assert is_valid
        assert len(errors) == 0

    def test_validate_atom_consistency_valid(self, tmp_path):
        """Base case: Atom IDs are consistent"""
        catalog_file = tmp_path / "cwe-89.yaml"
        catalog_data = {
            "metadata": {"cwe_id": "CWE-89", "name": "SQL Injection", "severity": "critical"},
            "sources": [{"id": "input.http.flask"}],
            "sinks": [{"id": "sink.sql.execute"}],
            "sanitizers": [{"id": "barrier.sql.parameterized"}],
            "policy": {},
            "validation": {},
            "test_suite": {},
        }
        with open(catalog_file, "w", encoding="utf-8") as f:
            yaml.dump(catalog_data, f)

        available_atoms = {
            "input.http.flask",
            "sink.sql.execute",
            "barrier.sql.parameterized",
            "other.atom",  # Extra atoms OK
        }

        validator = YAMLSchemaValidator()
        is_consistent, errors = validator.validate_atom_consistency(catalog_file, available_atoms)

        assert is_consistent
        assert len(errors) == 0

    # ========== EDGE CASES ==========

    def test_validate_catalog_file_not_found(self, tmp_path):
        """Edge case: Catalog file doesn't exist"""
        validator = YAMLSchemaValidator()
        is_valid, errors = validator.validate_catalog(tmp_path / "nonexistent.yaml")

        assert not is_valid
        assert len(errors) > 0
        assert any("not found" in err.lower() for err in errors)

    def test_validate_catalog_invalid_yaml(self, tmp_path):
        """Edge case: Invalid YAML syntax"""
        catalog_file = tmp_path / "invalid.yaml"
        catalog_file.write_text("invalid: yaml: syntax:")

        validator = YAMLSchemaValidator()
        is_valid, errors = validator.validate_catalog(catalog_file)

        assert not is_valid
        assert len(errors) > 0
        assert any("yaml" in err.lower() for err in errors)

    def test_validate_catalog_not_dict(self, tmp_path):
        """Edge case: YAML root is not dict"""
        catalog_file = tmp_path / "list.yaml"
        with open(catalog_file, "w", encoding="utf-8") as f:
            yaml.dump(["item1", "item2"], f)

        validator = YAMLSchemaValidator()
        is_valid, errors = validator.validate_catalog(catalog_file)

        assert not is_valid
        assert any("must be dict" in err.lower() for err in errors)

    def test_validate_catalog_missing_section(self, tmp_path):
        """Edge case: Missing required section"""
        catalog_file = tmp_path / "incomplete.yaml"
        catalog_data = {
            "metadata": {"cwe_id": "CWE-89", "name": "Test", "severity": "high"},
            # Missing: sources, sinks, policy, validation, test_suite
        }
        with open(catalog_file, "w", encoding="utf-8") as f:
            yaml.dump(catalog_data, f)

        validator = YAMLSchemaValidator()
        is_valid, errors = validator.validate_catalog(catalog_file)

        assert not is_valid
        assert len(errors) >= 5  # At least 5 missing sections
        assert any("sources" in err for err in errors)
        assert any("sinks" in err for err in errors)
        assert any("policy" in err for err in errors)

    def test_validate_catalog_missing_metadata_field(self, tmp_path):
        """Edge case: Missing required metadata field"""
        catalog_file = tmp_path / "no_severity.yaml"
        catalog_data = {
            "metadata": {
                "cwe_id": "CWE-89",
                "name": "SQL Injection",
                # Missing: severity
            },
            "sources": [],
            "sinks": [],
            "policy": {},
            "validation": {},
            "test_suite": {},
        }
        with open(catalog_file, "w", encoding="utf-8") as f:
            yaml.dump(catalog_data, f)

        validator = YAMLSchemaValidator()
        is_valid, errors = validator.validate_catalog(catalog_file)

        assert not is_valid
        assert any("severity" in err.lower() for err in errors)

    def test_validate_atom_consistency_missing_atom(self, tmp_path):
        """Edge case: Catalog references non-existent atom"""
        catalog_file = tmp_path / "cwe-89.yaml"
        catalog_data = {
            "metadata": {"cwe_id": "CWE-89", "name": "Test", "severity": "high"},
            "sources": [{"id": "input.nonexistent"}],  # ❌ Doesn't exist
            "sinks": [{"id": "sink.sql.execute"}],
            "policy": {},
            "validation": {},
            "test_suite": {},
        }
        with open(catalog_file, "w", encoding="utf-8") as f:
            yaml.dump(catalog_data, f)

        available_atoms = {"sink.sql.execute"}  # input.nonexistent missing

        validator = YAMLSchemaValidator()
        is_consistent, errors = validator.validate_atom_consistency(catalog_file, available_atoms)

        assert not is_consistent
        assert len(errors) == 1
        assert "input.nonexistent" in errors[0]

    # ========== CORNER CASES ==========

    def test_validate_catalog_sources_not_list(self, tmp_path):
        """Corner case: sources is dict instead of list"""
        catalog_file = tmp_path / "bad_sources.yaml"
        catalog_data = {
            "metadata": {"cwe_id": "CWE-89", "name": "Test", "severity": "high"},
            "sources": {"id": "wrong_type"},  # ❌ Should be list
            "sinks": [],
            "policy": {},
            "validation": {},
            "test_suite": {},
        }
        with open(catalog_file, "w", encoding="utf-8") as f:
            yaml.dump(catalog_data, f)

        validator = YAMLSchemaValidator()
        is_valid, errors = validator.validate_catalog(catalog_file)

        assert not is_valid
        assert any("sources" in err and "list" in err for err in errors)

    def test_validate_catalog_source_missing_id(self, tmp_path):
        """Corner case: Source item missing 'id' field"""
        catalog_file = tmp_path / "no_id.yaml"
        catalog_data = {
            "metadata": {"cwe_id": "CWE-89", "name": "Test", "severity": "high"},
            "sources": [{"description": "No ID field"}],  # ❌ Missing id
            "sinks": [],
            "policy": {},
            "validation": {},
            "test_suite": {},
        }
        with open(catalog_file, "w", encoding="utf-8") as f:
            yaml.dump(catalog_data, f)

        validator = YAMLSchemaValidator()
        is_valid, errors = validator.validate_catalog(catalog_file)

        assert not is_valid
        assert any("missing 'id'" in err for err in errors)

    def test_validate_catalog_empty_file(self, tmp_path):
        """Corner case: Empty YAML file"""
        catalog_file = tmp_path / "empty.yaml"
        catalog_file.write_text("")

        validator = YAMLSchemaValidator()
        is_valid, errors = validator.validate_catalog(catalog_file)

        # Empty YAML parses as None
        assert not is_valid
        assert len(errors) > 0

    # ========== EXTREME CASES ==========

    def test_validate_catalog_very_large_file(self, tmp_path):
        """Extreme case: Very large catalog (1000+ sources)"""
        catalog_file = tmp_path / "large.yaml"
        catalog_data = {
            "metadata": {"cwe_id": "CWE-999", "name": "Test", "severity": "high"},
            "sources": [{"id": f"source.{i}"} for i in range(1000)],
            "sinks": [{"id": f"sink.{i}"} for i in range(1000)],
            "policy": {},
            "validation": {},
            "test_suite": {},
        }
        with open(catalog_file, "w", encoding="utf-8") as f:
            yaml.dump(catalog_data, f)

        validator = YAMLSchemaValidator()
        is_valid, errors = validator.validate_catalog(catalog_file)

        # Should handle large files
        assert is_valid
        assert len(errors) == 0

    def test_validate_atom_consistency_many_missing(self, tmp_path):
        """Extreme case: Many missing atoms"""
        catalog_file = tmp_path / "many_missing.yaml"
        catalog_data = {
            "metadata": {"cwe_id": "CWE-89", "name": "Test", "severity": "high"},
            "sources": [{"id": f"missing.source.{i}"} for i in range(50)],
            "sinks": [{"id": f"missing.sink.{i}"} for i in range(50)],
            "policy": {},
            "validation": {},
            "test_suite": {},
        }
        with open(catalog_file, "w", encoding="utf-8") as f:
            yaml.dump(catalog_data, f)

        available_atoms = set()  # All missing

        validator = YAMLSchemaValidator()
        is_consistent, errors = validator.validate_atom_consistency(catalog_file, available_atoms)

        assert not is_consistent
        assert len(errors) == 100  # 50 sources + 50 sinks

    def test_validate_catalog_unicode_content(self, tmp_path):
        """Extreme case: Catalog with Unicode characters"""
        catalog_file = tmp_path / "unicode.yaml"
        catalog_data = {
            "metadata": {"cwe_id": "CWE-89", "name": "SQL 인젝션", "severity": "critical"},
            "description": "SQL 인젝션 취약점",
            "sources": [{"id": "input.http.flask", "description": "Flask 요청"}],
            "sinks": [{"id": "sink.sql.execute"}],
            "policy": {},
            "validation": {},
            "test_suite": {},
        }
        with open(catalog_file, "w", encoding="utf-8") as f:
            yaml.dump(catalog_data, f, allow_unicode=True)

        validator = YAMLSchemaValidator()
        is_valid, errors = validator.validate_catalog(catalog_file)

        # Should handle Unicode
        assert is_valid
        assert len(errors) == 0
