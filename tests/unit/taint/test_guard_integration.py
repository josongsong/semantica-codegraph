"""
RFC-030: Guard Condition Integration Tests

Tests for Dominator-based guard validation in taint analysis.

Coverage:
- GuardDetector detection
- ConstraintValidator guard integration
- Dominator-based guard validation
- TaintEngine guard-aware path sanitization
"""

import pytest

from codegraph_engine.code_foundation.domain.taint.guard import (
    ArgInfo,
    ArgShape,
    DominatorPort,
    GuardCondition,
)
from codegraph_engine.code_foundation.infrastructure.taint.validation.constraint_validator import (
    ConstraintValidator,
)
from codegraph_engine.code_foundation.infrastructure.taint.validation.guard_detector import (
    GuardDetector,
)

# =============================================================================
# Test Fixtures
# =============================================================================


class MockDominatorTree:
    """Mock DominatorTree for testing."""

    def __init__(self, dominance_map: dict[str, set[str]] | None = None):
        """
        Args:
            dominance_map: Map of block_id -> set of blocks it dominates
        """
        self._dominance_map = dominance_map or {}

    def dominates(self, dominator: str, dominated: str) -> bool:
        """Check if dominator block dominates dominated block."""
        if dominator == dominated:
            return True
        dominated_set = self._dominance_map.get(dominator, set())
        return dominated in dominated_set


# =============================================================================
# GuardCondition Tests
# =============================================================================


class TestGuardCondition:
    """Test GuardCondition domain model."""

    def test_guard_condition_creation(self):
        """Test basic GuardCondition creation."""
        guard = GuardCondition(
            guard_block_id="block_1",
            guarded_var="user_input",
            exit_on_fail=True,
        )

        assert guard.guard_block_id == "block_1"
        assert guard.guarded_var == "user_input"
        assert guard.exit_on_fail is True

    def test_is_valid_guard_with_domination(self):
        """Test guard validation with dominator tree."""
        # Setup: block_1 dominates block_3
        dom_tree = MockDominatorTree(
            {
                "block_1": {"block_2", "block_3"},
            }
        )

        guard = GuardCondition(
            guard_block_id="block_1",
            guarded_var="x",
            exit_on_fail=True,
        )

        # Guard at block_1 should protect sink at block_3
        assert guard.is_valid_guard("block_3", dom_tree) is True

    def test_is_valid_guard_without_domination(self):
        """Test guard validation when guard doesn't dominate sink."""
        # Setup: block_1 doesn't dominate block_5
        dom_tree = MockDominatorTree(
            {
                "block_1": {"block_2", "block_3"},
            }
        )

        guard = GuardCondition(
            guard_block_id="block_1",
            guarded_var="x",
            exit_on_fail=True,
        )

        # Guard at block_1 should NOT protect sink at block_5
        assert guard.is_valid_guard("block_5", dom_tree) is False

    def test_is_valid_guard_no_exit_on_fail(self):
        """Test guard validation when exit_on_fail is False."""
        dom_tree = MockDominatorTree(
            {
                "block_1": {"block_2", "block_3"},
            }
        )

        guard = GuardCondition(
            guard_block_id="block_1",
            guarded_var="x",
            exit_on_fail=False,  # Not a valid guard pattern
        )

        # Guard without exit_on_fail should not protect
        assert guard.is_valid_guard("block_3", dom_tree) is False


# =============================================================================
# ConstraintValidator Guard Integration Tests
# =============================================================================


class TestConstraintValidatorGuard:
    """Test ConstraintValidator guard integration."""

    def test_set_dominator_tree(self):
        """Test setting dominator tree."""
        validator = ConstraintValidator()
        dom_tree = MockDominatorTree()

        # Should not raise
        validator.set_dominator_tree(dom_tree)
        assert validator._dominator_tree is dom_tree

    def test_is_guard_protected_no_dominator(self):
        """Test is_guard_protected without dominator tree."""
        validator = ConstraintValidator()

        # Without dominator tree, should return False
        assert validator.is_guard_protected("block_1", "x") is False

    def test_is_guard_protected_with_guards(self):
        """Test is_guard_protected with detected guards."""
        validator = ConstraintValidator()

        # Setup dominator tree
        dom_tree = MockDominatorTree(
            {
                "block_1": {"block_2", "block_3"},
            }
        )
        validator.set_dominator_tree(dom_tree)

        # Manually add detected guard
        validator._detected_guards = [
            GuardCondition(
                guard_block_id="block_1",
                guarded_var="user_input",
                exit_on_fail=True,
            ),
        ]

        # Variable should be protected at dominated block
        assert validator.is_guard_protected("block_3", "user_input") is True

        # Variable should NOT be protected at non-dominated block
        assert validator.is_guard_protected("block_5", "user_input") is False

        # Different variable should NOT be protected
        assert validator.is_guard_protected("block_3", "other_var") is False


# =============================================================================
# ArgInfo Tests
# =============================================================================


class TestArgInfo:
    """Test ArgInfo domain model."""

    def test_arg_info_creation(self):
        """Test ArgInfo creation."""
        info = ArgInfo(
            shape=ArgShape.LIST_LITERAL,
            const_value=["a", "b"],
            is_tainted=False,
        )

        assert info.shape == ArgShape.LIST_LITERAL
        assert info.const_value == ["a", "b"]
        assert info.is_tainted is False

    def test_is_const(self):
        """Test is_const property."""
        with_const = ArgInfo(shape=ArgShape.STRING, const_value="hello")
        without_const = ArgInfo(shape=ArgShape.NAME)

        assert with_const.is_const is True
        assert without_const.is_const is False

    def test_is_collection(self):
        """Test is_collection property."""
        list_arg = ArgInfo(shape=ArgShape.LIST_LITERAL)
        tuple_arg = ArgInfo(shape=ArgShape.TUPLE_LITERAL)
        string_arg = ArgInfo(shape=ArgShape.STRING)

        assert list_arg.is_collection is True
        assert tuple_arg.is_collection is True
        assert string_arg.is_collection is False


# =============================================================================
# GuardDetector Tests
# =============================================================================


class TestGuardDetector:
    """Test GuardDetector."""

    def test_detector_creation(self):
        """Test GuardDetector creation."""
        detector = GuardDetector()

        assert detector is not None
        assert len(detector.EXIT_FUNCTIONS) > 0
        assert len(detector.VALIDATION_PATTERNS) > 0
        assert len(detector.REGEX_GUARD_PATTERNS) > 0

    def test_detect_returns_list(self):
        """Test detect returns a list (even if empty without IR)."""
        detector = GuardDetector()

        # Mock IRDocument
        class MockIRDoc:
            expressions = []

        guards = detector.detect(MockIRDoc())
        assert isinstance(guards, list)


# =============================================================================
# Integration Tests
# =============================================================================


class TestGuardIntegration:
    """Integration tests for guard-aware taint analysis."""

    def test_full_guard_flow(self):
        """Test complete guard detection and validation flow."""
        # 1. Create guard condition
        guard = GuardCondition(
            guard_block_id="if_block",
            guarded_var="user_input",
            exit_on_fail=True,
        )

        # 2. Create dominator tree where if_block dominates sink_block
        dom_tree = MockDominatorTree(
            {
                "entry": {"if_block", "sink_block"},
                "if_block": {"sink_block"},
            }
        )

        # 3. Create validator and configure
        validator = ConstraintValidator()
        validator.set_dominator_tree(dom_tree)
        validator._detected_guards = [guard]

        # 4. Check protection
        assert validator.is_guard_protected("sink_block", "user_input") is True

        # 5. Check non-protected case
        assert validator.is_guard_protected("other_block", "user_input") is False

    def test_multiple_guards_same_variable(self):
        """Test multiple guards protecting same variable."""
        # Multiple guards at different points
        guard1 = GuardCondition(
            guard_block_id="check_1",
            guarded_var="data",
            exit_on_fail=True,
        )
        guard2 = GuardCondition(
            guard_block_id="check_2",
            guarded_var="data",
            exit_on_fail=True,
        )

        # Only check_2 dominates sink
        dom_tree = MockDominatorTree(
            {
                "check_1": {"intermediate"},
                "check_2": {"sink"},
            }
        )

        validator = ConstraintValidator()
        validator.set_dominator_tree(dom_tree)
        validator._detected_guards = [guard1, guard2]

        # data should be protected at sink by guard2
        assert validator.is_guard_protected("sink", "data") is True

        # data should NOT be protected at other (neither guard dominates)
        assert validator.is_guard_protected("other", "data") is False
