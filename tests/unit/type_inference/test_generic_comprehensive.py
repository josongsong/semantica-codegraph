"""
RFC-034: Comprehensive Test Suite (SOTA-Level)

Coverage:
- Base cases: 기본 동작
- Edge cases: 경계 조건
- Corner cases: 예외적 상황
- Extreme cases: 극한 조건
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.type_inference.generic_constraint import (
    ConstraintPropagation,
    GenericConstraintTracker,
    TypeConstraint,
)
from codegraph_engine.code_foundation.infrastructure.type_inference.generic.unification import (
    RobinsonUnifier,
    Substitution,
    TypeExpr,
    UnificationError,
)


# ============================================================
# BASE CASES: 기본 동작 검증
# ============================================================


class TestBaseCases:
    """Base cases: 정상 동작 검증."""

    def test_simple_type_constraint(self):
        """Base: T = int"""
        constraint = TypeConstraint(type_var="T", constraint=None, bound_type="int")
        assert constraint.type_var == "T"
        assert constraint.bound_type == "int"

    def test_simple_unification(self):
        """Base: Unify T with int"""
        unifier = RobinsonUnifier()
        sub = unifier.unify(TypeExpr.parse("T"), TypeExpr.parse("int"))
        assert str(sub.apply(TypeExpr.parse("T"))) == "int"

    def test_generic_unification(self):
        """Base: Unify List[T] with List[int]"""
        unifier = RobinsonUnifier()
        sub = unifier.unify(TypeExpr.parse("List[T]"), TypeExpr.parse("List[int]"))
        assert str(sub.apply(TypeExpr.parse("List[T]"))) == "List[int]"

    def test_constraint_tracker_basic(self):
        """Base: Track and solve constraint"""
        tracker = GenericConstraintTracker()
        tracker._constraints["test::T"] = TypeConstraint(type_var="T", constraint=None, bound_type="int")
        sub = tracker.solve_all_constraints()
        assert tracker.get_resolved_type("T") == "int"


# ============================================================
# EDGE CASES: 경계 조건
# ============================================================


class TestEdgeCases:
    """Edge cases: 경계 조건."""

    def test_empty_type_var_rejected(self):
        """Edge: Empty TypeVar should fail"""
        with pytest.raises(ValueError, match="cannot be empty"):
            TypeConstraint(type_var="", constraint=None)

    def test_invalid_type_var_format(self):
        """Edge: Invalid TypeVar format"""
        with pytest.raises(ValueError, match="Invalid TypeVar"):
            TypeConstraint(type_var="abc", constraint=None)  # Lowercase

        with pytest.raises(ValueError, match="Invalid TypeVar"):
            TypeConstraint(type_var="T123", constraint=None)  # Too long

    def test_empty_bound_type(self):
        """Edge: Empty bound type rejected"""
        with pytest.raises(ValueError, match="empty or whitespace"):
            TypeConstraint(type_var="T", constraint=None, bound_type="   ")

    def test_single_arg_generic(self):
        """Edge: Single argument generic"""
        t = TypeExpr.parse("List[int]")
        assert t.name == "List"
        assert len(t.args) == 1
        assert t.args[0].name == "int"

    def test_multiple_arg_generic(self):
        """Edge: Multiple arguments"""
        t = TypeExpr.parse("Dict[str, int]")
        assert t.name == "Dict"
        assert len(t.args) == 2

    def test_deeply_nested_generics(self):
        """Edge: Deep nesting"""
        t = TypeExpr.parse("Dict[str, List[Dict[int, str]]]")
        assert t.args[1].args[0].name == "Dict"
        assert str(t) == "Dict[str, List[Dict[int, str]]]"

    def test_whitespace_in_type_string(self):
        """Edge: Whitespace handling"""
        t = TypeExpr.parse("  List [ T ]  ")
        assert t.name == "List"
        assert t.args[0].name == "T"

    def test_occurs_check_direct(self):
        """Edge: Direct occurs check"""
        unifier = RobinsonUnifier()
        with pytest.raises(UnificationError, match="Infinite type"):
            unifier.unify(TypeExpr.parse("T"), TypeExpr.parse("List[T]"))

    def test_occurs_check_nested(self):
        """Edge: Nested occurs check"""
        unifier = RobinsonUnifier()
        with pytest.raises(UnificationError, match="Infinite type"):
            unifier.unify(TypeExpr.parse("T"), TypeExpr.parse("Dict[str, T]"))


# ============================================================
# CORNER CASES: 예외적 상황
# ============================================================


class TestCornerCases:
    """Corner cases: 예외적 상황."""

    def test_conflicting_constraints(self):
        """Corner: T = int AND T = str (conflict)"""
        tracker = GenericConstraintTracker()
        tracker._constraints["test::T::1"] = TypeConstraint(type_var="T", constraint=None, bound_type="int")
        tracker._constraints["test::T::2"] = TypeConstraint(type_var="T", constraint=None, bound_type="str")

        # Should not crash - partial solution
        sub = tracker.solve_all_constraints()

        # Should have stats
        assert hasattr(tracker, "_last_solver_stats")
        stats = tracker._last_solver_stats
        assert stats.total_constraints == 2
        # At least one should fail
        assert len(stats.failed_constraints) >= 1

    def test_self_referential_constraint(self):
        """Corner: T = T (identity)"""
        unifier = RobinsonUnifier()
        sub = unifier.unify(TypeExpr.parse("T"), TypeExpr.parse("T"))
        # Should succeed (no-op)
        assert sub is not None

    def test_incompatible_type_constructors(self):
        """Corner: List[int] vs Dict[str, int]"""
        unifier = RobinsonUnifier()
        with pytest.raises(UnificationError, match="Cannot unify"):
            unifier.unify(TypeExpr.parse("List[int]"), TypeExpr.parse("Dict[str, int]"))

    def test_mismatched_arg_count(self):
        """Corner: List[T] vs Dict[K, V] (different arg count)"""
        unifier = RobinsonUnifier()
        with pytest.raises(UnificationError):
            unifier.unify(TypeExpr.parse("List[T]"), TypeExpr.parse("Dict[K, V]"))

    def test_partially_unified_types(self):
        """Corner: Unify Dict[T, int] with Dict[str, V]"""
        unifier = RobinsonUnifier()
        sub = unifier.unify(TypeExpr.parse("Dict[T, int]"), TypeExpr.parse("Dict[str, V]"))

        # Both T and V should be bound
        assert str(sub.apply(TypeExpr.parse("T"))) == "str"
        assert str(sub.apply(TypeExpr.parse("V"))) == "int"

    def test_multiple_independent_constraints(self):
        """Corner: Multiple independent TypeVars"""
        tracker = GenericConstraintTracker()
        tracker._constraints["func1::T"] = TypeConstraint(type_var="T", constraint=None, bound_type="int")
        tracker._constraints["func2::K"] = TypeConstraint(type_var="K", constraint=None, bound_type="str")
        tracker._constraints["func3::V"] = TypeConstraint(type_var="V", constraint=None, bound_type="bool")

        sub = tracker.solve_all_constraints()

        assert tracker.get_resolved_type("T") == "int"
        assert tracker.get_resolved_type("K") == "str"
        assert tracker.get_resolved_type("V") == "bool"


# ============================================================
# EXTREME CASES: 극한 조건
# ============================================================


class TestExtremeCases:
    """Extreme cases: 극한 조건."""

    def test_very_deeply_nested_generics(self):
        """Extreme: 10-level nesting"""
        type_str = "A[B[C[D[E[F[G[H[I[J[int]]]]]]]]]]"
        t = TypeExpr.parse(type_str)
        assert t.name == "A"
        assert str(t) == type_str

    def test_large_number_of_type_vars(self):
        """Extreme: 100 TypeVars"""
        tracker = GenericConstraintTracker()

        # Create 100 constraints
        for i in range(100):
            tracker._constraints[f"func{i}::T{i % 10}"] = TypeConstraint(
                type_var=f"T{i % 10}", constraint=None, bound_type="int"
            )

        # Should not crash
        sub = tracker.solve_all_constraints()

        stats = tracker._last_solver_stats
        assert stats.total_constraints == 100
        # Most should succeed (some conflicts expected due to T0-T9 reuse)
        assert stats.solved_constraints >= 10

    def test_complex_constraint_chain(self):
        """Extreme: Chain of constraints"""
        unifier = RobinsonUnifier()

        # T = U, U = V, V = int
        unifier.unify(TypeExpr.parse("T"), TypeExpr.parse("U"))
        unifier.unify(TypeExpr.parse("U"), TypeExpr.parse("V"))
        unifier.unify(TypeExpr.parse("V"), TypeExpr.parse("int"))

        # All should resolve to int
        sub = unifier.substitution
        assert str(sub.apply(TypeExpr.parse("T"))) == "int"
        assert str(sub.apply(TypeExpr.parse("U"))) == "int"
        assert str(sub.apply(TypeExpr.parse("V"))) == "int"

    def test_multiple_unification_attempts(self):
        """Extreme: Reuse unifier for multiple problems"""
        unifier = RobinsonUnifier()

        # Problem 1
        sub1 = unifier.unify(TypeExpr.parse("T"), TypeExpr.parse("int"))
        assert str(sub1.apply(TypeExpr.parse("T"))) == "int"

        # Problem 2 (same unifier)
        sub2 = unifier.unify(TypeExpr.parse("K"), TypeExpr.parse("str"))
        assert str(sub2.apply(TypeExpr.parse("K"))) == "str"

        # Both should still work
        assert str(sub2.apply(TypeExpr.parse("T"))) == "int"

    def test_all_special_type_vars(self):
        """Extreme: All common TypeVar names"""
        type_vars = ["T", "K", "V", "R", "S", "U", "T1", "T2"]

        for tv in type_vars:
            constraint = TypeConstraint(type_var=tv, constraint=None, bound_type="int")
            assert constraint.type_var == tv

    def test_empty_constraints_dict(self):
        """Extreme: No constraints"""
        tracker = GenericConstraintTracker()
        tracker.solve_all_constraints()

        # Should not crash
        stats = tracker._last_solver_stats
        assert stats.total_constraints == 0
        assert stats.solved_constraints == 0

    def test_all_constraints_fail(self):
        """Extreme: All constraints have errors"""
        tracker = GenericConstraintTracker()

        # Create invalid constraints (will cause parsing errors)
        for i in range(10):
            # Invalid type strings with mismatched brackets
            tracker._constraints[f"test::T{i}"] = TypeConstraint(
                type_var=f"T{i}", constraint=None, bound_type=f"List[[{i}"
            )

        # Should not crash
        sub = tracker.solve_all_constraints()

        stats = tracker._last_solver_stats
        assert stats.total_constraints == 10
        # All should fail gracefully
        assert len(stats.failed_constraints) == 10


# ============================================================
# INTEGRATION TESTS
# ============================================================


class TestIntegration:
    """Integration: End-to-end scenarios."""

    def test_full_pipeline_identity_function(self):
        """Integration: identity<T>(x: T) -> T with identity(42)"""
        tracker = GenericConstraintTracker()

        # Collect generic from function signature
        tracker._constraints["func::identity::T"] = TypeConstraint(
            type_var="T",
            constraint=None,
            bound_type="int",  # From call site
        )

        # Solve
        sub = tracker.solve_all_constraints()

        # Resolve return type
        return_type = tracker.get_resolved_type("T")
        assert return_type == "int"

    def test_full_pipeline_map_function(self):
        """Integration: map<T, R>(fn: T -> R, items: List[T]) -> List[R]"""
        tracker = GenericConstraintTracker()

        # Call: map(str, [1, 2, 3])
        tracker._constraints["func::map::T"] = TypeConstraint(type_var="T", constraint=None, bound_type="int")
        tracker._constraints["func::map::R"] = TypeConstraint(type_var="R", constraint=None, bound_type="str")

        # Solve
        sub = tracker.solve_all_constraints()

        # Resolve return type: List[R]
        result = tracker.get_resolved_type("List[R]")
        assert result == "List[str]"

    def test_full_pipeline_with_conflicts(self):
        """Integration: Handle conflicts gracefully"""
        tracker = GenericConstraintTracker()

        # Multiple conflicting constraints
        tracker._constraints["func1::T"] = TypeConstraint(type_var="T", constraint=None, bound_type="int")
        tracker._constraints["func2::T"] = TypeConstraint(type_var="T", constraint=None, bound_type="str")

        # Should not crash
        sub = tracker.solve_all_constraints()

        # Should report failures
        stats = tracker._last_solver_stats
        assert len(stats.failed_constraints) >= 1
        assert stats.success_rate < 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
