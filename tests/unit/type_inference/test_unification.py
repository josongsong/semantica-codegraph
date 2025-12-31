"""
RFC-034 Phase 2: Robinson's Unification Algorithm Tests

Tests for:
1. TypeExpr parsing
2. Substitution operations
3. Robinson's Unification Algorithm
4. Occurs check
5. Constraint solving
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.type_inference.generic.unification import (
    RobinsonUnifier,
    Substitution,
    TypeExpr,
    UnificationError,
)


class TestTypeExprParsing:
    """Test TypeExpr.parse method."""

    def test_simple_type(self):
        """Parse simple type: int"""
        t = TypeExpr.parse("int")
        assert t.name == "int"
        assert t.args == []
        assert str(t) == "int"

    def test_type_variable(self):
        """Parse type variable: T"""
        t = TypeExpr.parse("T")
        assert t.name == "T"
        assert t.is_type_var()

    def test_generic_single_arg(self):
        """Parse generic with single arg: List[T]"""
        t = TypeExpr.parse("List[T]")
        assert t.name == "List"
        assert len(t.args) == 1
        assert t.args[0].name == "T"
        assert str(t) == "List[T]"

    def test_generic_multiple_args(self):
        """Parse generic with multiple args: Dict[K, V]"""
        t = TypeExpr.parse("Dict[K, V]")
        assert t.name == "Dict"
        assert len(t.args) == 2
        assert t.args[0].name == "K"
        assert t.args[1].name == "V"
        assert str(t) == "Dict[K, V]"

    def test_nested_generic(self):
        """Parse nested generic: Dict[str, List[int]]"""
        t = TypeExpr.parse("Dict[str, List[int]]")
        assert t.name == "Dict"
        assert len(t.args) == 2
        assert t.args[0].name == "str"
        assert t.args[1].name == "List"
        assert t.args[1].args[0].name == "int"
        assert str(t) == "Dict[str, List[int]]"


class TestTypeVarDetection:
    """Test TypeExpr.is_type_var method."""

    def test_single_uppercase_letter(self):
        """Single uppercase letter is TypeVar"""
        assert TypeExpr.parse("T").is_type_var()
        assert TypeExpr.parse("K").is_type_var()
        assert TypeExpr.parse("V").is_type_var()

    def test_t_with_digit(self):
        """T with digit is TypeVar"""
        assert TypeExpr.parse("T1").is_type_var()
        assert TypeExpr.parse("T2").is_type_var()

    def test_not_type_var(self):
        """Other names are not TypeVars"""
        assert not TypeExpr.parse("int").is_type_var()
        assert not TypeExpr.parse("str").is_type_var()
        assert not TypeExpr.parse("List").is_type_var()


class TestSubstitution:
    """Test Substitution class."""

    def test_simple_binding(self):
        """Bind T → int"""
        sub = Substitution()
        sub.bind("T", TypeExpr.parse("int"))
        assert sub.lookup("T") == TypeExpr.parse("int")

    def test_apply_simple(self):
        """Apply substitution: T → int"""
        sub = Substitution()
        sub.bind("T", TypeExpr.parse("int"))

        t = TypeExpr.parse("T")
        result = sub.apply(t)
        assert str(result) == "int"

    def test_apply_generic(self):
        """Apply substitution: List[T] → List[int]"""
        sub = Substitution()
        sub.bind("T", TypeExpr.parse("int"))

        t = TypeExpr.parse("List[T]")
        result = sub.apply(t)
        assert str(result) == "List[int]"

    def test_apply_nested(self):
        """Apply substitution: Dict[K, List[V]] → Dict[str, List[int]]"""
        sub = Substitution()
        sub.bind("K", TypeExpr.parse("str"))
        sub.bind("V", TypeExpr.parse("int"))

        t = TypeExpr.parse("Dict[K, List[V]]")
        result = sub.apply(t)
        assert str(result) == "Dict[str, List[int]]"

    def test_conflicting_binding(self):
        """Conflicting binding raises error"""
        sub = Substitution()
        sub.bind("T", TypeExpr.parse("int"))

        with pytest.raises(UnificationError):
            sub.bind("T", TypeExpr.parse("str"))


class TestRobinsonUnifier:
    """Test Robinson's Unification Algorithm."""

    def test_simple_unification(self):
        """Unify T with int"""
        unifier = RobinsonUnifier()
        t1 = TypeExpr.parse("T")
        t2 = TypeExpr.parse("int")

        sub = unifier.unify(t1, t2)
        assert str(sub.apply(t1)) == "int"

    def test_generic_unification(self):
        """Unify List[T] with List[int]"""
        unifier = RobinsonUnifier()
        t1 = TypeExpr.parse("List[T]")
        t2 = TypeExpr.parse("List[int]")

        sub = unifier.unify(t1, t2)
        assert str(sub.apply(TypeExpr.parse("T"))) == "int"
        assert str(sub.apply(t1)) == "List[int]"

    def test_multiple_type_vars(self):
        """Unify Dict[K, V] with Dict[str, int]"""
        unifier = RobinsonUnifier()
        t1 = TypeExpr.parse("Dict[K, V]")
        t2 = TypeExpr.parse("Dict[str, int]")

        sub = unifier.unify(t1, t2)
        assert str(sub.apply(TypeExpr.parse("K"))) == "str"
        assert str(sub.apply(TypeExpr.parse("V"))) == "int"

    def test_nested_unification(self):
        """Unify Dict[K, List[V]] with Dict[str, List[int]]"""
        unifier = RobinsonUnifier()
        t1 = TypeExpr.parse("Dict[K, List[V]]")
        t2 = TypeExpr.parse("Dict[str, List[int]]")

        sub = unifier.unify(t1, t2)
        assert str(sub.apply(TypeExpr.parse("K"))) == "str"
        assert str(sub.apply(TypeExpr.parse("V"))) == "int"
        assert str(sub.apply(t1)) == "Dict[str, List[int]]"

    def test_occurs_check(self):
        """Occurs check prevents infinite types: T = List[T]"""
        unifier = RobinsonUnifier()
        t1 = TypeExpr.parse("T")
        t2 = TypeExpr.parse("List[T]")

        with pytest.raises(UnificationError, match="Infinite type"):
            unifier.unify(t1, t2)

    def test_incompatible_types(self):
        """Incompatible types fail unification"""
        unifier = RobinsonUnifier()
        t1 = TypeExpr.parse("int")
        t2 = TypeExpr.parse("str")

        with pytest.raises(UnificationError, match="Cannot unify"):
            unifier.unify(t1, t2)

    def test_incompatible_generics(self):
        """Incompatible generics fail: List[int] vs Dict[str, int]"""
        unifier = RobinsonUnifier()
        t1 = TypeExpr.parse("List[int]")
        t2 = TypeExpr.parse("Dict[str, int]")

        with pytest.raises(UnificationError, match="Cannot unify"):
            unifier.unify(t1, t2)


class TestConstraintSolving:
    """Test constraint solving with GenericConstraintTracker."""

    def test_solve_simple_constraint(self):
        """Solve: T = int"""
        from codegraph_engine.code_foundation.infrastructure.type_inference.generic_constraint import (
            GenericConstraintTracker,
            TypeConstraint,
        )

        tracker = GenericConstraintTracker()
        tracker._constraints["func::identity::T"] = TypeConstraint(type_var="T", constraint=None, bound_type="int")

        tracker.solve_all_constraints()
        resolved = tracker.get_resolved_type("T")
        assert resolved == "int"

    def test_solve_generic_type(self):
        """Solve: T = int, resolve List[T] → List[int]"""
        from codegraph_engine.code_foundation.infrastructure.type_inference.generic_constraint import (
            GenericConstraintTracker,
            TypeConstraint,
        )

        tracker = GenericConstraintTracker()
        tracker._constraints["func::map::T"] = TypeConstraint(type_var="T", constraint=None, bound_type="int")

        tracker.solve_all_constraints()
        resolved = tracker.get_resolved_type("List[T]")
        assert resolved == "List[int]"

    def test_solve_multiple_constraints(self):
        """Solve: K = str, V = int, resolve Dict[K, V]"""
        from codegraph_engine.code_foundation.infrastructure.type_inference.generic_constraint import (
            GenericConstraintTracker,
            TypeConstraint,
        )

        tracker = GenericConstraintTracker()
        tracker._constraints["func::pair::K"] = TypeConstraint(type_var="K", constraint=None, bound_type="str")
        tracker._constraints["func::pair::V"] = TypeConstraint(type_var="V", constraint=None, bound_type="int")

        tracker.solve_all_constraints()
        resolved = tracker.get_resolved_type("Dict[K, V]")
        assert resolved == "Dict[str, int]"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
