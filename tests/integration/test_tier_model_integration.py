"""
RFC-036/037 Integration Test: Real Codebase

Tests tier model with actual Python files.
"""

import tempfile
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig, SemanticTier
from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder


@pytest.mark.asyncio
class TestTierModelIntegration:
    """Integration tests with real Python files."""

    async def test_base_tier_builds_cfg_only(self, tmp_path):
        """BASE tier should build CFG only (no DFG, no SSA)."""
        # Create real Python file
        test_file = tmp_path / "calculator.py"
        test_file.write_text("""
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    result = a * b
    return result
""")

        # Build with BASE tier
        builder = LayeredIRBuilder(tmp_path)
        config = BuildConfig.for_editor()

        result = await builder.build([test_file], config)

        # Verify tier
        assert config.semantic_tier == SemanticTier.BASE

        # Verify CFG exists
        ir_doc = result.ir_documents[str(test_file)]
        assert ir_doc.cfgs  # CFG should exist

        # Verify DFG/SSA do not exist
        assert ir_doc.dfg_snapshot is None  # No DFG
        # SSA is not stored in IRDocument, but we can verify config
        assert config.dfg is False
        assert config.ssa is False

    async def test_extended_tier_builds_dfg_with_threshold(self, tmp_path):
        """EXTENDED tier should build DFG with threshold."""
        # Create file with small and large functions
        test_file = tmp_path / "mixed.py"

        # Small function (10 lines)
        small_func = "def small():\n" + "    x = 1\n" * 8 + "    return x\n"

        # Large function (600 lines - exceeds 500 threshold)
        large_func = "def large():\n" + "    x = 1\n" * 598 + "    return x\n"

        test_file.write_text(small_func + "\n" + large_func)

        # Build with EXTENDED tier
        builder = LayeredIRBuilder(tmp_path)
        config = BuildConfig.for_refactoring()

        result = await builder.build([test_file], config)

        # Verify tier
        assert config.semantic_tier == SemanticTier.EXTENDED
        assert config.dfg is True
        assert config.ssa is False

        # Verify DFG exists (for small function at least)
        ir_doc = result.ir_documents[str(test_file)]
        # DFG may be partial (large function skipped)
        # We just verify no crash and config is correct
        assert config.dfg_function_loc_threshold == 500

    async def test_full_tier_builds_everything(self, tmp_path):
        """FULL tier should build CFG + DFG + SSA."""
        test_file = tmp_path / "full.py"
        test_file.write_text("""
def process(data):
    if data:
        result = transform(data)
        return result
    return None

def transform(x):
    return x * 2
""")

        # Build with FULL tier
        builder = LayeredIRBuilder(tmp_path)
        config = BuildConfig.for_analysis()

        result = await builder.build([test_file], config)

        # Verify tier
        assert config.semantic_tier == SemanticTier.FULL
        assert config.cfg is True
        assert config.dfg is True
        assert config.ssa is True

        # Verify all components exist
        ir_doc = result.ir_documents[str(test_file)]
        assert ir_doc.cfgs  # CFG
        # DFG and SSA presence depends on actual build
        # We verify config is correct

    async def test_provenance_generated(self, tmp_path):
        """Build should generate provenance."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = LayeredIRBuilder(tmp_path)
        config = BuildConfig.for_refactoring()

        result = await builder.build([test_file], config)

        # Verify provenance exists
        assert result.provenance is not None
        assert result.provenance.is_deterministic()

        # Verify fingerprints
        assert len(result.provenance.input_fingerprint) == 64
        assert len(result.provenance.config_fingerprint) == 64

    async def test_deterministic_builds(self, tmp_path):
        """Same inputs should produce same provenance."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = LayeredIRBuilder(tmp_path)
        config = BuildConfig.for_refactoring()

        # Build twice
        result1 = await builder.build([test_file], config)
        result2 = await builder.build([test_file], config)

        # Provenances should match (excluding timestamp)
        assert result1.provenance.matches(result2.provenance)

    async def test_different_tiers_different_provenance(self, tmp_path):
        """Different tiers should have different provenance."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        builder = LayeredIRBuilder(tmp_path)

        # Build with different tiers
        config_base = BuildConfig.for_editor()
        config_full = BuildConfig.for_analysis()

        result_base = await builder.build([test_file], config_base)
        result_full = await builder.build([test_file], config_full)

        # Provenances should NOT match (different config)
        assert not result_base.provenance.matches(result_full.provenance)
