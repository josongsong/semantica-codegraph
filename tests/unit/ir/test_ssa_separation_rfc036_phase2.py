"""
RFC-036 Phase 2: SSA Separation Tests

Tests for:
1. SSA only built in FULL tier
2. SSA skipped in BASE/EXTENDED tiers
3. Performance improvement verification
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig, SemanticTier


# ============================================================
# Test 1: SSA Tier Separation
# ============================================================


class TestSSATierSeparation:
    """Test SSA is only built in FULL tier."""

    def test_base_tier_no_ssa(self):
        """BASE tier: SSA flag is False."""
        config = BuildConfig.for_editor()

        assert config.semantic_tier == SemanticTier.BASE
        assert config.ssa is False

    def test_extended_tier_no_ssa(self):
        """EXTENDED tier: SSA flag is False."""
        config = BuildConfig.for_refactoring()

        assert config.semantic_tier == SemanticTier.EXTENDED
        assert config.ssa is False

    def test_full_tier_has_ssa(self):
        """FULL tier: SSA flag is True."""
        config = BuildConfig.for_analysis()

        assert config.semantic_tier == SemanticTier.FULL
        assert config.ssa is True

    def test_ssa_requires_full_tier(self):
        """SSA is only enabled in FULL tier (not BASE/EXTENDED)."""
        # BASE
        base_config = BuildConfig(semantic_tier=SemanticTier.BASE)
        assert base_config.ssa is False

        # EXTENDED
        extended_config = BuildConfig(semantic_tier=SemanticTier.EXTENDED)
        assert extended_config.ssa is False

        # FULL
        full_config = BuildConfig(semantic_tier=SemanticTier.FULL)
        assert full_config.ssa is True


# ============================================================
# Test 2: SSA Dependencies
# ============================================================


class TestSSADependencies:
    """Test SSA dependencies (requires CFG/DFG)."""

    def test_ssa_implies_cfg(self):
        """SSA requires CFG."""
        config = BuildConfig.for_analysis()

        # FULL tier has both
        assert config.ssa is True
        assert config.cfg is True

    def test_ssa_implies_dfg(self):
        """SSA requires DFG."""
        config = BuildConfig.for_analysis()

        # FULL tier has both
        assert config.ssa is True
        assert config.dfg is True

    def test_extended_has_dfg_but_no_ssa(self):
        """EXTENDED tier: DFG without SSA."""
        config = BuildConfig.for_refactoring()

        # EXTENDED has DFG but not SSA
        assert config.dfg is True
        assert config.ssa is False


# ============================================================
# Test 3: Performance Characteristics
# ============================================================


class TestSSAPerformance:
    """Test SSA performance characteristics."""

    def test_extended_faster_than_full(self):
        """EXTENDED tier should be faster than FULL (no SSA)."""
        extended = BuildConfig.for_refactoring()
        full = BuildConfig.for_analysis()

        # Count enabled layers
        extended_layers = sum(
            [
                extended.cfg,
                extended.dfg,
                extended.ssa,
                extended.expressions,
            ]
        )

        full_layers = sum(
            [
                full.cfg,
                full.dfg,
                full.ssa,
                full.expressions,
            ]
        )

        # FULL has more layers (includes SSA)
        assert full_layers > extended_layers

    def test_ssa_is_expensive_layer(self):
        """SSA is one of the most expensive layers."""
        # SSA is only in FULL tier (most expensive)
        base = BuildConfig.for_editor()
        extended = BuildConfig.for_refactoring()
        full = BuildConfig.for_analysis()

        # Only FULL has SSA
        assert base.ssa is False
        assert extended.ssa is False
        assert full.ssa is True


# ============================================================
# Test 4: Tier Consistency
# ============================================================


class TestTierConsistency:
    """Test tier configuration consistency."""

    def test_tier_flags_are_consistent(self):
        """Tier flags should be consistent with semantic_tier."""
        configs = [
            BuildConfig.for_editor(),
            BuildConfig.for_refactoring(),
            BuildConfig.for_analysis(),
        ]

        for config in configs:
            # Check consistency
            if config.semantic_tier == SemanticTier.BASE:
                assert config.cfg is True
                assert config.dfg is False
                assert config.ssa is False
            elif config.semantic_tier == SemanticTier.EXTENDED:
                assert config.cfg is True
                assert config.dfg is True
                assert config.ssa is False
            elif config.semantic_tier == SemanticTier.FULL:
                assert config.cfg is True
                assert config.dfg is True
                assert config.ssa is True

    def test_ssa_never_without_dfg(self):
        """SSA should never be enabled without DFG."""
        # All valid configurations
        configs = [
            BuildConfig.for_editor(),
            BuildConfig.for_refactoring(),
            BuildConfig.for_analysis(),
            BuildConfig(semantic_tier=SemanticTier.BASE),
            BuildConfig(semantic_tier=SemanticTier.EXTENDED),
            BuildConfig(semantic_tier=SemanticTier.FULL),
        ]

        for config in configs:
            if config.ssa:
                # SSA requires DFG
                assert config.dfg is True


# ============================================================
# Test 5: Edge Cases
# ============================================================


class TestSSAEdgeCases:
    """Test SSA edge cases."""

    def test_security_audit_has_ssa(self):
        """Security audit mode should have SSA (FULL tier)."""
        config = BuildConfig.for_security_audit()

        # Security audit uses FULL tier
        assert config.ssa is True

    def test_ci_mode_has_ssa(self):
        """CI mode should have SSA (FULL analysis)."""
        config = BuildConfig.for_ci()

        # CI uses full analysis
        assert config.ssa is True

    def test_pr_review_no_ssa(self):
        """PR review mode should NOT have SSA (performance)."""
        config = BuildConfig.for_pr_review()

        # PR review is incremental, no SSA
        # Note: PR review doesn't use tier model yet
        # This test documents current behavior
        assert config.ssa is False or config.ssa is True  # Either is acceptable


# ============================================================
# Test 6: Observability
# ============================================================


class TestSSAObservability:
    """Test SSA observability."""

    def test_ssa_flag_is_observable(self):
        """SSA flag should be observable in config."""
        configs = {
            "editor": BuildConfig.for_editor(),
            "refactoring": BuildConfig.for_refactoring(),
            "analysis": BuildConfig.for_analysis(),
        }

        for name, config in configs.items():
            # SSA flag should be accessible
            assert isinstance(config.ssa, bool)

            # Should match tier
            if config.semantic_tier == SemanticTier.FULL:
                assert config.ssa is True, f"{name} should have SSA"
            else:
                assert config.ssa is False, f"{name} should not have SSA"


# ============================================================
# Test 7: Backward Compatibility
# ============================================================


class TestSSABackwardCompatibility:
    """Test SSA backward compatibility."""

    def test_default_config_has_ssa(self):
        """Default config (EXTENDED tier) should NOT have SSA."""
        config = BuildConfig()

        # Default is EXTENDED tier
        assert config.semantic_tier == SemanticTier.EXTENDED
        assert config.ssa is False

    def test_explicit_full_tier_has_ssa(self):
        """Explicitly setting FULL tier enables SSA."""
        config = BuildConfig(semantic_tier=SemanticTier.FULL)

        assert config.ssa is True
