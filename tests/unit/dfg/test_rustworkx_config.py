"""
RFC-021 Config Tests

Validates rustworkx configuration controls.
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.config import CodeFoundationConfig, RustworkxConfig
from codegraph_engine.code_foundation.infrastructure.dfg.ssa.dominator import (
    HAS_RUSTWORKX,
    compute_dominators,
    configure_rustworkx,
    is_rustworkx_enabled,
)


class TestRustworkxConfig:
    """rustworkx configuration tests"""

    def test_default_enabled(self):
        """Default: rustworkx enabled if available"""
        # Reset to default
        configure_rustworkx(HAS_RUSTWORKX)

        if HAS_RUSTWORKX:
            assert is_rustworkx_enabled() is True
        else:
            assert is_rustworkx_enabled() is False

    def test_manual_disable(self):
        """Can manually disable rustworkx"""
        configure_rustworkx(False)
        assert is_rustworkx_enabled() is False

        # Reset
        configure_rustworkx(HAS_RUSTWORKX)

    def test_manual_enable_without_rustworkx(self):
        """Cannot enable rustworkx if not installed"""
        if not HAS_RUSTWORKX:
            with pytest.raises(ValueError, match="Cannot enable rustworkx"):
                configure_rustworkx(True)

    def test_config_affects_behavior(self):
        """Config actually affects which implementation is used"""
        blocks = ["B0", "B1", "B2"]
        predecessors = {"B0": [], "B1": ["B0"], "B2": ["B1"]}

        # Test with Python forced
        configure_rustworkx(False)
        result1 = compute_dominators("B0", blocks, predecessors)

        # Test with rustworkx enabled (if available)
        configure_rustworkx(HAS_RUSTWORKX)
        result2 = compute_dominators("B0", blocks, predecessors)

        # Results should be identical
        assert result1.idom == result2.idom

    def test_config_model(self):
        """RustworkxConfig model validation"""
        # Default
        config = RustworkxConfig()
        assert config.enable_dominator is True
        assert config.enable_scc is True
        assert config.force_python is False
        assert config.min_blocks_for_rustworkx == 0

        # Custom
        config = RustworkxConfig(enable_dominator=False, force_python=True, min_blocks_for_rustworkx=1000)
        assert config.enable_dominator is False
        assert config.force_python is True
        assert config.min_blocks_for_rustworkx == 1000

    def test_integrated_config(self):
        """RustworkxConfig integrated into CodeFoundationConfig"""
        config = CodeFoundationConfig()
        assert hasattr(config, "rustworkx")
        assert isinstance(config.rustworkx, RustworkxConfig)

        # Defaults
        assert config.rustworkx.enable_dominator is True
        assert config.rustworkx.enable_scc is True

    def test_env_var_config(self, monkeypatch):
        """Environment variables should configure rustworkx"""
        # Set env vars
        monkeypatch.setenv("CF_RUSTWORKX__FORCE_PYTHON", "true")
        monkeypatch.setenv("CF_RUSTWORKX__MIN_BLOCKS_FOR_RUSTWORKX", "500")

        # Clear cache
        from codegraph_engine.code_foundation.infrastructure.config import get_config

        get_config.cache_clear()

        # Load config
        config = get_config()
        assert config.rustworkx.force_python is True
        assert config.rustworkx.min_blocks_for_rustworkx == 500

        # Cleanup
        get_config.cache_clear()


class TestConfigurableThresholds:
    """Test min_blocks_for_rustworkx threshold"""

    @pytest.mark.skipif(not HAS_RUSTWORKX, reason="rustworkx not installed")
    def test_threshold_below_min(self):
        """Below threshold: should work (might use Python or rustworkx)"""
        # Small graph (below any reasonable threshold)
        blocks = [f"B{i}" for i in range(10)]
        predecessors = {f"B{i}": [f"B{i - 1}"] for i in range(1, 10)}
        predecessors["B0"] = []

        result = compute_dominators("B0", blocks, predecessors)
        assert result.entry_id == "B0"
        assert len(result.idom) == 9

    @pytest.mark.skipif(not HAS_RUSTWORKX, reason="rustworkx not installed")
    def test_threshold_above_min(self):
        """Above threshold: should work (prefer rustworkx)"""
        # Large graph
        blocks = [f"B{i}" for i in range(500)]
        predecessors = {f"B{i}": [f"B{i - 1}"] for i in range(1, 500)}
        predecessors["B0"] = []

        result = compute_dominators("B0", blocks, predecessors)
        assert result.entry_id == "B0"
        assert len(result.idom) == 499
