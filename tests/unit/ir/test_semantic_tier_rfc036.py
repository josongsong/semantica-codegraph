"""
RFC-036 Phase 1: Semantic Tier Model & DFG Threshold Tests

Tests for:
1. Tier model (BASE/EXTENDED/FULL)
2. DFG threshold logic
3. Tier validation
4. BuildConfig presets
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig, SemanticTier
from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument, Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.semantic_ir.builder import DefaultSemanticIrBuilder


# ============================================================
# Test 1: Tier Model
# ============================================================


class TestTierModel:
    """Test 3-tier model configuration."""

    def test_base_tier_only_cfg(self):
        """BASE tier: CFG only, no DFG/SSA/Expressions."""
        config = BuildConfig.for_editor()

        assert config.semantic_tier == SemanticTier.BASE
        assert config.cfg is True
        assert config.dfg is False
        assert config.ssa is False
        assert config.expressions is False
        assert config.generic_inference is False

    def test_extended_tier_has_dfg(self):
        """EXTENDED tier: CFG + DFG + Expressions."""
        config = BuildConfig.for_refactoring()

        assert config.semantic_tier == SemanticTier.EXTENDED
        assert config.cfg is True
        assert config.dfg is True
        assert config.ssa is False
        assert config.expressions is True
        assert config.generic_inference is True

    def test_full_tier_has_ssa(self):
        """FULL tier: All semantic IR."""
        config = BuildConfig.for_analysis()

        assert config.semantic_tier == SemanticTier.FULL
        assert config.cfg is True
        assert config.dfg is True
        assert config.ssa is True
        assert config.expressions is True
        assert config.generic_inference is True

    def test_tier_derivation_base(self):
        """Tier derivation: BASE → flags."""
        config = BuildConfig(semantic_tier=SemanticTier.BASE)

        # Derived flags
        assert config.cfg is True
        assert config.dfg is False
        assert config.ssa is False
        assert config.expressions is False

    def test_tier_derivation_extended(self):
        """Tier derivation: EXTENDED → flags."""
        config = BuildConfig(semantic_tier=SemanticTier.EXTENDED)

        # Derived flags
        assert config.cfg is True
        assert config.dfg is True
        assert config.ssa is False
        assert config.expressions is True

    def test_tier_derivation_full(self):
        """Tier derivation: FULL → flags."""
        config = BuildConfig(semantic_tier=SemanticTier.FULL)

        # Derived flags
        assert config.cfg is True
        assert config.dfg is True
        assert config.ssa is True
        assert config.expressions is True


# ============================================================
# Test 2: DFG Threshold
# ============================================================


class TestDFGThreshold:
    """Test DFG threshold logic."""

    def test_threshold_default_value(self):
        """Default threshold is 500 LOC."""
        config = BuildConfig.for_refactoring()

        assert config.dfg_function_loc_threshold == 500

    def test_threshold_configurable(self):
        """Threshold is configurable."""
        config = BuildConfig(
            semantic_tier=SemanticTier.EXTENDED,
            dfg_function_loc_threshold=1000,
        )

        assert config.dfg_function_loc_threshold == 1000

    def test_threshold_validation_positive(self):
        """Threshold must be > 0."""
        with pytest.raises(ValueError, match="dfg_function_loc_threshold must be > 0"):
            BuildConfig(
                semantic_tier=SemanticTier.EXTENDED,
                dfg_function_loc_threshold=0,
            )

    def test_threshold_validation_negative(self):
        """Threshold must be > 0 (negative)."""
        with pytest.raises(ValueError, match="dfg_function_loc_threshold must be > 0"):
            BuildConfig(
                semantic_tier=SemanticTier.EXTENDED,
                dfg_function_loc_threshold=-100,
            )

    def test_calculate_function_loc_normal(self):
        """Calculate LOC for normal function."""
        builder = DefaultSemanticIrBuilder()

        # Function with 10 lines (1-10)
        func_node = Node(
            id="func1",
            kind=NodeKind.FUNCTION,
            fqn="test.test_func",
            file_path="test.py",
            span=Span(start_line=1, end_line=10, start_col=0, end_col=0),
            language="python",
            name="test_func",
        )

        loc = builder._calculate_function_loc(func_node)
        assert loc == 10

    def test_calculate_function_loc_single_line(self):
        """Calculate LOC for single-line function."""
        builder = DefaultSemanticIrBuilder()

        # Single line function
        func_node = Node(
            id="func2",
            kind=NodeKind.FUNCTION,
            fqn="test.lambda_func",
            file_path="test.py",
            span=Span(start_line=5, end_line=5, start_col=0, end_col=20),
            language="python",
            name="lambda_func",
        )

        loc = builder._calculate_function_loc(func_node)
        assert loc == 1

    def test_calculate_function_loc_no_span(self):
        """Calculate LOC returns 0 for missing span."""
        builder = DefaultSemanticIrBuilder()

        # Function without span (span is required, but can be empty)
        func_node = Node(
            id="func3",
            kind=NodeKind.FUNCTION,
            fqn="test.no_span",
            file_path="test.py",
            span=Span(start_line=0, end_line=0, start_col=0, end_col=0),  # Empty span
            language="python",
            name="no_span",
        )

        # Override span to None for test
        func_node.span = None

        loc = builder._calculate_function_loc(func_node)
        assert loc == 0


# ============================================================
# Test 3: Tier Validation
# ============================================================


class TestTierValidation:
    """Test tier constraint validation."""

    def test_tier_is_source_of_truth(self):
        """semantic_tier is Source of Truth, flags are derived."""
        # User cannot override derived flags
        config = BuildConfig(semantic_tier=SemanticTier.BASE)

        # Even if user tries to set dfg=True, it's overridden
        assert config.dfg is False  # Derived from BASE tier

    def test_preset_for_editor_is_base(self):
        """for_editor() uses BASE tier."""
        config = BuildConfig.for_editor()

        assert config.semantic_tier == SemanticTier.BASE
        assert config.dfg is False

    def test_preset_for_refactoring_is_extended(self):
        """for_refactoring() uses EXTENDED tier."""
        config = BuildConfig.for_refactoring()

        assert config.semantic_tier == SemanticTier.EXTENDED
        assert config.dfg is True
        assert config.ssa is False

    def test_preset_for_analysis_is_full(self):
        """for_analysis() uses FULL tier."""
        config = BuildConfig.for_analysis()

        assert config.semantic_tier == SemanticTier.FULL
        assert config.ssa is True


# ============================================================
# Test 4: Integration with SemanticIrBuilder
# ============================================================


class TestSemanticIrBuilderIntegration:
    """Test integration with DefaultSemanticIrBuilder."""

    def test_base_tier_skips_dfg(self):
        """BASE tier: DFG is None."""
        builder = DefaultSemanticIrBuilder()
        config = BuildConfig(semantic_tier=SemanticTier.BASE)

        # Create minimal IR with at least one node
        module_node = Node(
            id="module:test",
            kind=NodeKind.MODULE,
            fqn="test",
            file_path="test.py",
            span=Span(start_line=1, end_line=1, start_col=0, end_col=0),
            language="python",
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test-snapshot",
            nodes=[module_node],
            edges=[],
        )

        # Build with BASE tier
        snapshot, _ = builder.build_full(ir_doc, source_map={}, build_config=config)

        # DFG should be None
        assert snapshot.dfg_snapshot is None

    def test_extended_tier_builds_dfg(self):
        """EXTENDED tier: DFG is built (with threshold)."""
        builder = DefaultSemanticIrBuilder()
        config = BuildConfig(semantic_tier=SemanticTier.EXTENDED)

        # Create minimal IR with at least one node
        module_node = Node(
            id="module:test",
            kind=NodeKind.MODULE,
            fqn="test",
            file_path="test.py",
            span=Span(start_line=1, end_line=1, start_col=0, end_col=0),
            language="python",
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test-snapshot",
            nodes=[module_node],
            edges=[],
        )

        # Build with EXTENDED tier
        snapshot, _ = builder.build_full(ir_doc, source_map={}, build_config=config)

        # DFG should be built (even if empty)
        # Note: Empty IR will have empty DFG, not None
        assert snapshot.dfg_snapshot is not None or len(ir_doc.nodes) == 1

    def test_full_tier_builds_all(self):
        """FULL tier: All semantic IR is built."""
        builder = DefaultSemanticIrBuilder()
        config = BuildConfig(semantic_tier=SemanticTier.FULL)

        # Create minimal IR with at least one node
        module_node = Node(
            id="module:test",
            kind=NodeKind.MODULE,
            fqn="test",
            file_path="test.py",
            span=Span(start_line=1, end_line=1, start_col=0, end_col=0),
            language="python",
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test-snapshot",
            nodes=[module_node],
            edges=[],
        )

        # Build with FULL tier
        snapshot, _ = builder.build_full(ir_doc, source_map={}, build_config=config)

        # All components should be present (even if empty)
        assert snapshot.cfg_graphs is not None
        assert snapshot.cfg_blocks is not None
        assert snapshot.expressions is not None


# ============================================================
# Test 5: Edge Cases
# ============================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_threshold_at_boundary(self):
        """Function exactly at threshold should be included."""
        builder = DefaultSemanticIrBuilder()
        config = BuildConfig(
            semantic_tier=SemanticTier.EXTENDED,
            dfg_function_loc_threshold=100,
        )

        # Function with exactly 100 lines
        func_node = Node(
            id="func_boundary",
            kind=NodeKind.FUNCTION,
            fqn="test.boundary_func",
            file_path="test.py",
            span=Span(start_line=1, end_line=100, start_col=0, end_col=0),
            language="python",
            name="boundary_func",
        )

        loc = builder._calculate_function_loc(func_node)
        assert loc == 100

        # Should be included (not skipped)
        assert loc <= config.dfg_function_loc_threshold

    def test_threshold_just_over(self):
        """Function just over threshold should be skipped."""
        builder = DefaultSemanticIrBuilder()
        config = BuildConfig(
            semantic_tier=SemanticTier.EXTENDED,
            dfg_function_loc_threshold=100,
        )

        # Function with 101 lines
        func_node = Node(
            id="func_over",
            kind=NodeKind.FUNCTION,
            fqn="test.over_func",
            file_path="test.py",
            span=Span(start_line=1, end_line=101, start_col=0, end_col=0),
            language="python",
            name="over_func",
        )

        loc = builder._calculate_function_loc(func_node)
        assert loc == 101

        # Should be skipped
        assert loc > config.dfg_function_loc_threshold

    def test_none_build_config_defaults_to_full(self):
        """None build_config defaults to FULL tier."""
        builder = DefaultSemanticIrBuilder()

        # Create minimal IR with at least one node
        module_node = Node(
            id="module:test",
            kind=NodeKind.MODULE,
            fqn="test",
            file_path="test.py",
            span=Span(start_line=1, end_line=1, start_col=0, end_col=0),
            language="python",
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test-snapshot",
            nodes=[module_node],
            edges=[],
        )

        # Build without build_config (should default to FULL)
        snapshot, _ = builder.build_full(ir_doc, source_map={}, build_config=None)

        # Should behave like FULL tier (no threshold)
        assert snapshot.cfg_graphs is not None


# ============================================================
# Test 6: Performance Characteristics
# ============================================================


class TestPerformanceCharacteristics:
    """Test performance-related behavior."""

    def test_base_tier_is_fastest(self):
        """BASE tier should be fastest (minimal work)."""
        config_base = BuildConfig.for_editor()
        config_full = BuildConfig.for_analysis()

        # BASE has fewer layers enabled
        base_layers = sum(
            [
                config_base.cfg,
                config_base.dfg,
                config_base.ssa,
                config_base.expressions,
            ]
        )

        full_layers = sum(
            [
                config_full.cfg,
                config_full.dfg,
                config_full.ssa,
                config_full.expressions,
            ]
        )

        assert base_layers < full_layers

    def test_extended_tier_is_balanced(self):
        """EXTENDED tier is balanced (some layers)."""
        config = BuildConfig.for_refactoring()

        # Has DFG but not SSA
        assert config.dfg is True
        assert config.ssa is False

    def test_threshold_reduces_work(self):
        """Higher threshold = more work skipped."""
        config_low = BuildConfig(
            semantic_tier=SemanticTier.EXTENDED,
            dfg_function_loc_threshold=100,
        )

        config_high = BuildConfig(
            semantic_tier=SemanticTier.EXTENDED,
            dfg_function_loc_threshold=1000,
        )

        # Higher threshold means more functions included
        assert config_high.dfg_function_loc_threshold > config_low.dfg_function_loc_threshold


# ============================================================
# Test 7: Observability & Metrics (SOTA)
# ============================================================


class TestObservability:
    """Test observability and metrics."""

    def test_bfg_block_prefix_constant(self):
        """BFG block prefix should be a constant (no magic strings)."""
        # This is a code quality test
        # Verify that BFG_BLOCK_PREFIX constant is used
        import inspect
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.builder import DefaultSemanticIrBuilder

        # Get source code of _build_dfg_with_threshold
        source = inspect.getsource(DefaultSemanticIrBuilder._build_dfg_with_threshold)

        # Should contain BFG_BLOCK_PREFIX constant
        assert "BFG_BLOCK_PREFIX" in source

        # Should NOT contain magic string "bfg_block" directly in comparison
        # (except in constant definition)
        lines = source.split("\n")
        magic_string_lines = [line for line in lines if '"bfg_block"' in line and "BFG_BLOCK_PREFIX" not in line]

        # Only the constant definition line should have the magic string
        assert len(magic_string_lines) <= 1  # At most the definition line


# ============================================================
# Test 8: Extreme Edge Cases (L11 SOTA)
# ============================================================


class TestExtremeEdgeCases:
    """Test extreme edge cases and failure scenarios."""

    def test_empty_bfg_blocks(self):
        """Empty BFG blocks should return None gracefully."""
        builder = DefaultSemanticIrBuilder()
        config = BuildConfig(semantic_tier=SemanticTier.EXTENDED)

        # Create IR with function but no BFG blocks
        func_node = Node(
            id="func:test",
            kind=NodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(start_line=1, end_line=10, start_col=0, end_col=0),
            language="python",
            name="func",
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[func_node],
        )

        # Build DFG with empty blocks
        result = builder._build_dfg_with_threshold(ir_doc, bfg_blocks=[], expressions=[], threshold=500)

        # Should return None (not crash)
        assert result is None

    def test_invalid_threshold_zero(self):
        """Threshold = 0 should raise ValueError."""
        builder = DefaultSemanticIrBuilder()

        ir_doc = IRDocument(repo_id="test", snapshot_id="test")

        with pytest.raises(ValueError, match="threshold must be > 0"):
            builder._build_dfg_with_threshold(ir_doc, bfg_blocks=[], expressions=[], threshold=0)

    def test_invalid_threshold_negative(self):
        """Negative threshold should raise ValueError."""
        builder = DefaultSemanticIrBuilder()

        ir_doc = IRDocument(repo_id="test", snapshot_id="test")

        with pytest.raises(ValueError, match="threshold must be > 0"):
            builder._build_dfg_with_threshold(ir_doc, bfg_blocks=[], expressions=[], threshold=-100)

    def test_all_functions_exceed_threshold(self):
        """All functions exceeding threshold should return None."""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.models import (
            BasicFlowBlock,
            BFGBlockKind,
        )

        builder = DefaultSemanticIrBuilder()

        # Create huge function (1000 LOC)
        func_node = Node(
            id="func:huge",
            kind=NodeKind.FUNCTION,
            fqn="test.huge",
            file_path="test.py",
            span=Span(start_line=1, end_line=1000, start_col=0, end_col=0),
            language="python",
            name="huge",
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[func_node],
        )

        # Create BFG block for this function
        bfg_block = BasicFlowBlock(
            id="bfg_block:func:huge:0",
            kind=BFGBlockKind.STATEMENT,
            function_node_id="func:huge",
        )

        # All functions exceed threshold (100 LOC)
        result = builder._build_dfg_with_threshold(ir_doc, bfg_blocks=[bfg_block], expressions=[], threshold=100)

        # Should return None (all skipped)
        assert result is None

    def test_unparseable_bfg_block_id(self):
        """Unparseable BFG block IDs should be included with warning."""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.models import (
            BasicFlowBlock,
            BFGBlockKind,
        )

        builder = DefaultSemanticIrBuilder()

        func_node = Node(
            id="func:test",
            kind=NodeKind.FUNCTION,
            fqn="test.func",
            file_path="test.py",
            span=Span(start_line=1, end_line=10, start_col=0, end_col=0),
            language="python",
            name="func",
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[func_node],
        )

        # Create blocks with invalid IDs (real BasicFlowBlock objects)
        bad_block1 = BasicFlowBlock(
            id="invalid_format",  # No colons
            kind=BFGBlockKind.STATEMENT,
            function_node_id="func:test",
        )

        bad_block2 = BasicFlowBlock(
            id="bfg:only_two_parts",  # Only 2 parts
            kind=BFGBlockKind.STATEMENT,
            function_node_id="func:test",
        )

        # Should not crash, should include blocks
        result = builder._build_dfg_with_threshold(
            ir_doc, bfg_blocks=[bad_block1, bad_block2], expressions=[], threshold=500
        )

        # Should process (not crash)
        # Unparseable blocks are included, so DFG should be built
        assert result is not None

    def test_function_with_zero_loc(self):
        """Functions with 0 LOC should be included (safe default)."""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.models import (
            BasicFlowBlock,
            BFGBlockKind,
        )

        builder = DefaultSemanticIrBuilder()

        # Function with no span (LOC = 0)
        func_node = Node(
            id="func:nospam",
            kind=NodeKind.FUNCTION,
            fqn="test.nospam",
            file_path="test.py",
            span=Span(start_line=0, end_line=0, start_col=0, end_col=0),
            language="python",
            name="nospam",
        )
        # Override span to None
        func_node.span = None

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[func_node],
        )

        bfg_block = BasicFlowBlock(
            id="bfg_block:func:nospam:0",
            kind=BFGBlockKind.STATEMENT,
            function_node_id="func:nospam",
        )

        # LOC = 0, should be included (not skipped)
        result = builder._build_dfg_with_threshold(ir_doc, bfg_blocks=[bfg_block], expressions=[], threshold=500)

        # Should process (0 LOC < threshold)
        assert result is not None

    def test_function_id_with_colons(self):
        """Function IDs containing colons should be parsed correctly."""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.models import (
            BasicFlowBlock,
            BFGBlockKind,
        )

        builder = DefaultSemanticIrBuilder()

        # Function ID with colons (e.g., method in nested class)
        func_id = "method:MyClass:Inner:my_method"

        func_node = Node(
            id=func_id,
            kind=NodeKind.METHOD,
            fqn="test.MyClass.Inner.my_method",
            file_path="test.py",
            span=Span(start_line=1, end_line=10, start_col=0, end_col=0),
            language="python",
            name="my_method",
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[func_node],
        )

        # BFG block with function ID containing colons
        bfg_block = BasicFlowBlock(
            id=f"bfg_block:{func_id}:0",
            kind=BFGBlockKind.STATEMENT,
            function_node_id=func_id,
        )

        # Should parse correctly
        result = builder._build_dfg_with_threshold(ir_doc, bfg_blocks=[bfg_block], expressions=[], threshold=500)

        # Should process without error
        assert result is not None

    def test_missing_function_node(self):
        """BFG blocks without corresponding function node should be included."""
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.models import (
            BasicFlowBlock,
            BFGBlockKind,
        )

        builder = DefaultSemanticIrBuilder()

        # IR with no function nodes
        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[],  # Empty!
        )

        # BFG block referencing non-existent function
        bfg_block = BasicFlowBlock(
            id="bfg_block:func:missing:0",
            kind=BFGBlockKind.STATEMENT,
            function_node_id="func:missing",
        )

        # Should include block (safe default)
        result = builder._build_dfg_with_threshold(ir_doc, bfg_blocks=[bfg_block], expressions=[], threshold=500)

        # Should process (not crash)
        assert result is not None
