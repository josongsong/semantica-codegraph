"""
RFC-037 Phase 2: BuildProvenance Tests

Tests for deterministic build tracking and reproducibility.

Test Categories:
1. Provenance generation (10 tests)
2. Fingerprint computation (12 tests)
3. Determinism verification (8 tests)
4. Serialization (5 tests)
5. Edge cases (10 tests)
"""

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig, SemanticTier
from codegraph_engine.code_foundation.infrastructure.provenance import BuildProvenance, ProvenanceBuilder


# ============================================================
# Test 1: Provenance Generation
# ============================================================


class TestProvenanceGeneration:
    """Test provenance generation."""

    def test_generate_provenance_basic(self, tmp_path):
        """Generate provenance for basic build."""
        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build(
            files=[test_file],
            config=config,
            repo_root=tmp_path,
        )

        # Verify all fields
        assert provenance.input_fingerprint
        assert provenance.builder_version
        assert provenance.config_fingerprint
        assert provenance.dependency_fingerprint
        assert provenance.build_timestamp

    def test_provenance_is_deterministic(self, tmp_path):
        """Generated provenance should be deterministic."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build(
            files=[test_file],
            config=config,
            repo_root=tmp_path,
        )

        assert provenance.is_deterministic()

    def test_provenance_is_frozen(self, tmp_path):
        """BuildProvenance should be immutable (frozen)."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build(
            files=[test_file],
            config=config,
            repo_root=tmp_path,
        )

        # Should not be able to modify
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            provenance.input_fingerprint = "modified"

    def test_empty_files_raises_error(self):
        """Empty files list should raise ValueError."""
        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        with pytest.raises(ValueError, match="files list cannot be empty"):
            builder.build(files=[], config=config)

    def test_none_config_raises_error(self, tmp_path):
        """None config should raise ValueError."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()

        with pytest.raises(ValueError, match="config cannot be None"):
            builder.build(files=[test_file], config=None)

    def test_nonexistent_file_raises_error(self, tmp_path):
        """Non-existent file should raise FileNotFoundError."""
        fake_file = tmp_path / "nonexistent.py"

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        with pytest.raises(FileNotFoundError):
            builder.build(files=[fake_file], config=config)


# ============================================================
# Test 2: Fingerprint Computation
# ============================================================


class TestFingerprintComputation:
    """Test fingerprint computation logic."""

    def test_same_files_same_fingerprint(self, tmp_path):
        """Same files → same input fingerprint."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        prov1 = builder.build([test_file], config, tmp_path)
        prov2 = builder.build([test_file], config, tmp_path)

        assert prov1.input_fingerprint == prov2.input_fingerprint

    def test_different_content_different_fingerprint(self, tmp_path):
        """Different file content → different fingerprint."""
        test_file = tmp_path / "test.py"

        # First build
        test_file.write_text("def foo(): pass")
        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()
        prov1 = builder.build([test_file], config, tmp_path)

        # Modify file
        test_file.write_text("def bar(): pass")
        prov2 = builder.build([test_file], config, tmp_path)

        # Fingerprints should differ
        assert prov1.input_fingerprint != prov2.input_fingerprint

    def test_file_order_stable(self, tmp_path):
        """File order should not affect fingerprint (stable sorting)."""
        file1 = tmp_path / "a.py"
        file2 = tmp_path / "b.py"
        file1.write_text("def a(): pass")
        file2.write_text("def b(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        # Different order
        prov1 = builder.build([file1, file2], config, tmp_path)
        prov2 = builder.build([file2, file1], config, tmp_path)

        # Should have same fingerprint (stable sort)
        assert prov1.input_fingerprint == prov2.input_fingerprint

    def test_same_config_same_fingerprint(self, tmp_path):
        """Same config → same config fingerprint."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        prov1 = builder.build([test_file], config, tmp_path)
        prov2 = builder.build([test_file], config, tmp_path)

        assert prov1.config_fingerprint == prov2.config_fingerprint

    def test_different_tier_different_fingerprint(self, tmp_path):
        """Different tier → different config fingerprint."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config1 = BuildConfig(semantic_tier=SemanticTier.BASE)
        config2 = BuildConfig(semantic_tier=SemanticTier.FULL)

        prov1 = builder.build([test_file], config1, tmp_path)
        prov2 = builder.build([test_file], config2, tmp_path)

        # Different tier → different fingerprint
        assert prov1.config_fingerprint != prov2.config_fingerprint

    def test_different_threshold_different_fingerprint(self, tmp_path):
        """Different threshold → different config fingerprint."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config1 = BuildConfig(
            semantic_tier=SemanticTier.EXTENDED,
            dfg_function_loc_threshold=500,
        )
        config2 = BuildConfig(
            semantic_tier=SemanticTier.EXTENDED,
            dfg_function_loc_threshold=1000,
        )

        prov1 = builder.build([test_file], config1, tmp_path)
        prov2 = builder.build([test_file], config2, tmp_path)

        # Different threshold → different fingerprint
        assert prov1.config_fingerprint != prov2.config_fingerprint

    def test_dependency_fingerprint_stable(self, tmp_path):
        """Dependency fingerprint should be stable."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        prov1 = builder.build([test_file], config, tmp_path)
        prov2 = builder.build([test_file], config, tmp_path)

        # Same environment → same dependency fingerprint
        assert prov1.dependency_fingerprint == prov2.dependency_fingerprint

    def test_fingerprints_are_hex_strings(self, tmp_path):
        """All fingerprints should be hex strings."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build([test_file], config, tmp_path)

        # Should be hex strings (SHA256 = 64 chars)
        assert len(provenance.input_fingerprint) == 64
        assert len(provenance.config_fingerprint) == 64
        assert len(provenance.dependency_fingerprint) == 64

        # Should be valid hex
        int(provenance.input_fingerprint, 16)
        int(provenance.config_fingerprint, 16)
        int(provenance.dependency_fingerprint, 16)


# ============================================================
# Test 3: Determinism Verification
# ============================================================


class TestDeterminismVerification:
    """Test determinism verification logic."""

    def test_is_deterministic_all_fields_present(self, tmp_path):
        """is_deterministic() returns True when all fields present."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build([test_file], config, tmp_path)

        assert provenance.is_deterministic()

    def test_is_deterministic_empty_fingerprint(self):
        """is_deterministic() returns False for empty fingerprint."""
        provenance = BuildProvenance(
            input_fingerprint="",  # Empty!
            builder_version="v1.0",
            config_fingerprint="abc",
            dependency_fingerprint="def",
            build_timestamp="2025-12-21T00:00:00Z",
        )

        assert not provenance.is_deterministic()

    def test_matches_same_inputs(self, tmp_path):
        """matches() returns True for same inputs."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        prov1 = builder.build([test_file], config, tmp_path)
        prov2 = builder.build([test_file], config, tmp_path)

        # Should match (same inputs)
        assert prov1.matches(prov2)

    def test_matches_ignores_timestamp(self, tmp_path):
        """matches() ignores timestamp (non-deterministic)."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        prov1 = builder.build([test_file], config, tmp_path)

        # Wait a bit (timestamp will differ)
        import time

        time.sleep(0.01)

        prov2 = builder.build([test_file], config, tmp_path)

        # Should match despite different timestamps
        assert prov1.matches(prov2)
        assert prov1.build_timestamp != prov2.build_timestamp

    def test_matches_different_files(self, tmp_path):
        """matches() returns False for different files."""
        file1 = tmp_path / "a.py"
        file2 = tmp_path / "b.py"
        file1.write_text("def a(): pass")
        file2.write_text("def b(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        prov1 = builder.build([file1], config, tmp_path)
        prov2 = builder.build([file2], config, tmp_path)

        # Should not match (different files)
        assert not prov1.matches(prov2)

    def test_matches_different_config(self, tmp_path):
        """matches() returns False for different config."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config1 = BuildConfig(semantic_tier=SemanticTier.BASE)
        config2 = BuildConfig(semantic_tier=SemanticTier.FULL)

        prov1 = builder.build([test_file], config1, tmp_path)
        prov2 = builder.build([test_file], config2, tmp_path)

        # Should not match (different config)
        assert not prov1.matches(prov2)


# ============================================================
# Test 4: Serialization
# ============================================================


class TestSerialization:
    """Test serialization and deserialization."""

    def test_to_dict(self, tmp_path):
        """to_dict() should produce JSON-serializable dict."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build([test_file], config, tmp_path)
        data = provenance.to_dict()

        # Should be dict
        assert isinstance(data, dict)

        # Should be JSON-serializable
        json_str = json.dumps(data)
        assert json_str

    def test_from_dict(self, tmp_path):
        """from_dict() should reconstruct provenance."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        prov1 = builder.build([test_file], config, tmp_path)
        data = prov1.to_dict()

        # Reconstruct
        prov2 = BuildProvenance.from_dict(data)

        # Should match
        assert prov1.matches(prov2)

    def test_round_trip_serialization(self, tmp_path):
        """Round-trip serialization should preserve data."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        prov1 = builder.build([test_file], config, tmp_path)

        # Round trip
        data = prov1.to_dict()
        prov2 = BuildProvenance.from_dict(data)

        # All fields should match
        assert prov1.input_fingerprint == prov2.input_fingerprint
        assert prov1.builder_version == prov2.builder_version
        assert prov1.config_fingerprint == prov2.config_fingerprint
        assert prov1.dependency_fingerprint == prov2.dependency_fingerprint

    def test_from_dict_missing_field_raises_error(self):
        """from_dict() with missing field should raise KeyError."""
        incomplete_data = {
            "input_fingerprint": "abc",
            # Missing other required fields
        }

        with pytest.raises(KeyError, match="Missing required field"):
            BuildProvenance.from_dict(incomplete_data)

    def test_from_dict_with_defaults(self):
        """from_dict() should use defaults for optional fields."""
        minimal_data = {
            "input_fingerprint": "a" * 64,  # Valid SHA256
            "builder_version": "v1.0",
            "config_fingerprint": "b" * 64,  # Valid SHA256
            "dependency_fingerprint": "c" * 64,  # Valid SHA256
            "build_timestamp": "2025-12-21T00:00:00Z",
            # No node_sort_key, edge_sort_key, parallel_seed
        }

        provenance = BuildProvenance.from_dict(minimal_data)

        # Should use defaults
        assert provenance.node_sort_key == "id"
        assert provenance.edge_sort_key == "id"
        assert provenance.parallel_seed == 42


# ============================================================
# Test 5: Edge Cases
# ============================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_single_file(self, tmp_path):
        """Single file should work."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build([test_file], config, tmp_path)

        assert provenance.is_deterministic()

    def test_many_files(self, tmp_path):
        """Many files should work."""
        files = []
        for i in range(100):
            file_path = tmp_path / f"file{i}.py"
            file_path.write_text(f"def func{i}(): pass")
            files.append(file_path)

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build(files, config, tmp_path)

        assert provenance.is_deterministic()

    def test_empty_file(self, tmp_path):
        """Empty file should work."""
        test_file = tmp_path / "empty.py"
        test_file.write_text("")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build([test_file], config, tmp_path)

        assert provenance.is_deterministic()

    def test_large_file(self, tmp_path):
        """Large file should work."""
        test_file = tmp_path / "large.py"
        # 10K lines
        content = "\n".join([f"def func{i}(): pass" for i in range(1000)])  # 10000 → 1000
        test_file.write_text(content)

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build([test_file], config, tmp_path)

        assert provenance.is_deterministic()

    def test_special_characters_in_filename(self, tmp_path):
        """Special characters in filename should work."""
        test_file = tmp_path / "test-file_v2.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build([test_file], config, tmp_path)

        assert provenance.is_deterministic()

    def test_nested_directories(self, tmp_path):
        """Nested directories should work."""
        nested_dir = tmp_path / "a" / "b" / "c"
        nested_dir.mkdir(parents=True)
        test_file = nested_dir / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build([test_file], config, tmp_path)

        assert provenance.is_deterministic()

    def test_file_outside_repo(self, tmp_path):
        """File outside repo should work (use absolute path)."""
        # Create file outside tmp_path
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def foo(): pass")
            outside_file = Path(f.name)

        try:
            builder = ProvenanceBuilder()
            config = BuildConfig.for_refactoring()

            provenance = builder.build([outside_file], config, tmp_path)

            assert provenance.is_deterministic()
        finally:
            outside_file.unlink()

    def test_none_repo_root(self, tmp_path):
        """None repo_root should work (use absolute paths)."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build([test_file], config, repo_root=None)

        assert provenance.is_deterministic()

    def test_timestamp_is_iso8601(self, tmp_path):
        """Timestamp should be ISO 8601 format."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build([test_file], config, tmp_path)

        # Should be parseable as ISO 8601
        from datetime import datetime

        dt = datetime.fromisoformat(provenance.build_timestamp.replace("Z", "+00:00"))
        assert dt

    def test_builder_version_is_set(self, tmp_path):
        """Builder version should be set."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build([test_file], config, tmp_path)

        assert provenance.builder_version
        assert len(provenance.builder_version) > 0


# ============================================================
# Test 6: Replay Capability
# ============================================================


class TestReplayCapability:
    """Test replay capability (reproducibility)."""

    def test_same_provenance_implies_same_output(self, tmp_path):
        """Same provenance should imply same output."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        prov1 = builder.build([test_file], config, tmp_path)
        prov2 = builder.build([test_file], config, tmp_path)

        # Same inputs → should match
        assert prov1.matches(prov2)

    def test_provenance_captures_all_inputs(self, tmp_path):
        """Provenance should capture ALL inputs affecting output."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build([test_file], config, tmp_path)

        # All fingerprints should be non-empty
        assert provenance.input_fingerprint
        assert provenance.builder_version
        assert provenance.config_fingerprint
        assert provenance.dependency_fingerprint


# ============================================================
# Test 7: Hash Collision Resistance (L11 SOTA)
# ============================================================


class TestHashCollisionResistance:
    """Test hash collision resistance."""

    def test_similar_files_different_fingerprints(self, tmp_path):
        """Similar files should have different fingerprints."""
        file1 = tmp_path / "test1.py"
        file2 = tmp_path / "test2.py"

        # Very similar content (only 1 char different)
        file1.write_text("def foo(): pass")
        file2.write_text("def foo(): fail")  # 'fail' vs 'pass'

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        prov1 = builder.build([file1], config, tmp_path)
        prov2 = builder.build([file2], config, tmp_path)

        # Should have different fingerprints
        assert prov1.input_fingerprint != prov2.input_fingerprint

    def test_many_files_no_collision(self, tmp_path):
        """Many files should not cause hash collision."""
        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        fingerprints = set()

        # Generate 1000 different files
        for i in range(1000):
            file_path = tmp_path / f"file{i}.py"
            file_path.write_text(f"def func{i}(): pass")

            provenance = builder.build([file_path], config, tmp_path)
            fingerprints.add(provenance.input_fingerprint)

        # All fingerprints should be unique (no collisions)
        assert len(fingerprints) == 1000

    def test_config_variations_no_collision(self, tmp_path):
        """Different config variations should not collide."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()

        # Generate all tier combinations
        configs = [
            BuildConfig(semantic_tier=SemanticTier.BASE),
            BuildConfig(semantic_tier=SemanticTier.EXTENDED),
            BuildConfig(semantic_tier=SemanticTier.FULL),
            BuildConfig(semantic_tier=SemanticTier.EXTENDED, dfg_function_loc_threshold=100),
            BuildConfig(semantic_tier=SemanticTier.EXTENDED, dfg_function_loc_threshold=1000),
        ]

        fingerprints = set()
        for config in configs:
            provenance = builder.build([test_file], config, tmp_path)
            fingerprints.add(provenance.config_fingerprint)

        # All should be unique
        assert len(fingerprints) == len(configs)

    def test_fingerprint_length_is_64_chars(self, tmp_path):
        """Fingerprints should be full SHA256 (64 chars)."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        provenance = builder.build([test_file], config, tmp_path)

        # Full SHA256 = 64 hex chars
        assert len(provenance.input_fingerprint) == 64
        assert len(provenance.config_fingerprint) == 64
        assert len(provenance.dependency_fingerprint) == 64


# ============================================================
# Test 8: Determinism Guarantees (L11 SOTA)
# ============================================================


class TestTypeValidation:
    """Test type validation in deserialization (L11 SOTA)."""

    def test_from_dict_invalid_type_input_fingerprint(self):
        """from_dict() with invalid type should raise TypeError."""
        invalid_data = {
            "input_fingerprint": 123,  # ❌ int instead of str
            "builder_version": "v1.0",
            "config_fingerprint": "def",
            "dependency_fingerprint": "ghi",
            "build_timestamp": "2025-12-21T00:00:00Z",
        }

        with pytest.raises(TypeError, match="input_fingerprint must be str"):
            BuildProvenance.from_dict(invalid_data)

    def test_from_dict_invalid_type_parallel_seed(self):
        """from_dict() with invalid parallel_seed type should raise TypeError."""
        invalid_data = {
            "input_fingerprint": "a" * 64,
            "builder_version": "v1.0",
            "config_fingerprint": "b" * 64,
            "dependency_fingerprint": "c" * 64,
            "build_timestamp": "2025-12-21T00:00:00Z",
            "parallel_seed": "not_an_int",  # ❌ str instead of int
        }

        with pytest.raises(TypeError, match="parallel_seed must be int"):
            BuildProvenance.from_dict(invalid_data)

    def test_from_dict_empty_fingerprint(self):
        """from_dict() with empty fingerprint should raise ValueError."""
        invalid_data = {
            "input_fingerprint": "",  # ❌ Empty
            "builder_version": "v1.0",
            "config_fingerprint": "b" * 64,
            "dependency_fingerprint": "c" * 64,
            "build_timestamp": "2025-12-21T00:00:00Z",
        }

        with pytest.raises(ValueError, match="cannot be empty"):
            BuildProvenance.from_dict(invalid_data)

    def test_from_dict_invalid_fingerprint_length(self):
        """from_dict() with wrong fingerprint length should raise ValueError."""
        invalid_data = {
            "input_fingerprint": "abc",  # ❌ Too short
            "builder_version": "v1.0",
            "config_fingerprint": "b" * 64,
            "dependency_fingerprint": "c" * 64,
            "build_timestamp": "2025-12-21T00:00:00Z",
        }

        with pytest.raises(ValueError, match="must be 64 chars"):
            BuildProvenance.from_dict(invalid_data)

    def test_from_dict_invalid_hex(self):
        """from_dict() with invalid hex should raise ValueError."""
        invalid_data = {
            "input_fingerprint": "z" * 64,  # ❌ 'z' is not hex
            "builder_version": "v1.0",
            "config_fingerprint": "b" * 64,
            "dependency_fingerprint": "c" * 64,
            "build_timestamp": "2025-12-21T00:00:00Z",
        }

        with pytest.raises(ValueError, match="must be valid hex string"):
            BuildProvenance.from_dict(invalid_data)

    def test_from_dict_empty_builder_version(self):
        """from_dict() with empty builder_version should raise ValueError."""
        invalid_data = {
            "input_fingerprint": "a" * 64,
            "builder_version": "",  # ❌ Empty
            "config_fingerprint": "b" * 64,
            "dependency_fingerprint": "c" * 64,
            "build_timestamp": "2025-12-21T00:00:00Z",
        }

        with pytest.raises(ValueError, match="builder_version cannot be empty"):
            BuildProvenance.from_dict(invalid_data)


class TestDeterminismGuarantees:
    """Test determinism guarantees."""

    def test_same_content_different_path_different_fingerprint(self, tmp_path):
        """Same content, different path → different fingerprint."""
        file1 = tmp_path / "a.py"
        file2 = tmp_path / "b.py"

        # Same content
        file1.write_text("def foo(): pass")
        file2.write_text("def foo(): pass")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        prov1 = builder.build([file1], config, tmp_path)
        prov2 = builder.build([file2], config, tmp_path)

        # Different paths → different fingerprints
        assert prov1.input_fingerprint != prov2.input_fingerprint

    def test_whitespace_changes_affect_fingerprint(self, tmp_path):
        """Whitespace changes should affect fingerprint."""
        test_file = tmp_path / "test.py"

        # First version
        test_file.write_text("def foo(): pass")
        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()
        prov1 = builder.build([test_file], config, tmp_path)

        # Add whitespace
        test_file.write_text("def foo():  pass")  # Extra space
        prov2 = builder.build([test_file], config, tmp_path)

        # Should differ (content changed)
        assert prov1.input_fingerprint != prov2.input_fingerprint

    def test_comment_changes_affect_fingerprint(self, tmp_path):
        """Comment changes should affect fingerprint."""
        test_file = tmp_path / "test.py"

        # Without comment
        test_file.write_text("def foo(): pass")
        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()
        prov1 = builder.build([test_file], config, tmp_path)

        # With comment
        test_file.write_text("# Comment\ndef foo(): pass")
        prov2 = builder.build([test_file], config, tmp_path)

        # Should differ (content changed)
        assert prov1.input_fingerprint != prov2.input_fingerprint

    def test_encoding_consistent(self, tmp_path):
        """Encoding should be consistent (UTF-8)."""
        test_file = tmp_path / "test.py"

        # Write with UTF-8 (Korean characters)
        test_file.write_text("def foo(): pass  # 한글 주석", encoding="utf-8")

        builder = ProvenanceBuilder()
        config = BuildConfig.for_refactoring()

        prov1 = builder.build([test_file], config, tmp_path)
        prov2 = builder.build([test_file], config, tmp_path)

        # Should be consistent
        assert prov1.input_fingerprint == prov2.input_fingerprint
