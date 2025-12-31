"""
Edge Cases & Corner Cases for Bidirectional Inference

Rule 3: Test Code 필수 - Happy/Invalid/Boundary/Edge

Test Coverage:
- Nested generics (List<Map<T, U>>)
- Constraint conflicts (T extends X vs T = Y)
- Nullable generics (T?, T | null)
- Multiple type parameters
- Generic inheritance
- Circular constraints
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.type_inference.bidirectional import (
    BidirectionalInference,
)
from codegraph_engine.code_foundation.infrastructure.type_inference.generic_constraint import (
    ConstraintPropagation,
    GenericConstraintTracker,
    TypeSubstitution,
)


class TestNestedGenerics:
    """중첩 Generic 처리"""

    def test_nested_generic_simple(self):
        """List<T> 치환"""
        sub = TypeSubstitution()
        sub.bind("T", "string")

        result = sub.apply("List<T>")
        assert result == "List<string>"

    def test_nested_generic_double(self):
        """List<Map<T, U>> 치환"""
        sub = TypeSubstitution()
        sub.bind("T", "string")
        sub.bind("U", "number")

        result = sub.apply("List<Map<T, U>>")
        assert result == "List<Map<string, number>>"

    def test_nested_generic_triple(self):
        """Result<List<Map<T, U>>> 치환"""
        sub = TypeSubstitution()
        sub.bind("T", "string")
        sub.bind("U", "number")

        result = sub.apply("Result<List<Map<T, U>>>")
        assert result == "Result<List<Map<string, number>>>"

    def test_nested_with_same_var(self):
        """List<List<T>> 치환"""
        sub = TypeSubstitution()
        sub.bind("T", "number")

        result = sub.apply("List<List<T>>")
        assert result == "List<List<number>>"


class TestConstraintConflicts:
    """Constraint 충돌 처리"""

    def test_constraint_satisfied(self):
        """Constraint 만족"""
        prop = ConstraintPropagation()
        prop.add_constraint("T", "extends", "number")
        prop.unify("T", "42")

        result = prop.resolve("T")
        assert result == "number"  # 42 → number (widen)

    def test_constraint_violation(self):
        """Constraint 위반 (T extends number, but T = string)"""
        prop = ConstraintPropagation()
        prop.add_constraint("T", "extends", "number")
        prop.unify("T", "string")

        result = prop.resolve("T")
        # Should return string (unify takes precedence)
        # Or raise error in strict mode
        assert result in ["string", "error", None]

    def test_no_constraint_literal(self):
        """Constraint 없을 때 literal"""
        prop = ConstraintPropagation()
        prop.unify("T", "42")

        result = prop.resolve("T")
        # No constraint, but literal → keep literal
        assert result == "42"

    def test_empty_constraint(self):
        """Constraint 없음"""
        prop = ConstraintPropagation()

        result = prop.resolve("T")
        assert result is None


class TestNullableGenerics:
    """Nullable Generic 처리"""

    def test_nullable_kotlin_style(self):
        """Kotlin: T?"""
        sub = TypeSubstitution()
        sub.bind("T", "Int")

        result = sub.apply("T?")
        assert result == "Int?"

    def test_nullable_typescript_style(self):
        """TypeScript: T | null"""
        sub = TypeSubstitution()
        sub.bind("T", "string")

        result = sub.apply("T | null")
        assert result == "string | null"

    def test_nullable_list(self):
        """List<T?>"""
        sub = TypeSubstitution()
        sub.bind("T", "number")

        result = sub.apply("List<T?>")
        assert result == "List<number?>"


class TestMultipleTypeParameters:
    """여러 타입 파라미터"""

    def test_two_parameters(self):
        """Map<K, V>"""
        sub = TypeSubstitution()
        sub.bind("K", "string")
        sub.bind("V", "number")

        result = sub.apply("Map<K, V>")
        assert result == "Map<string, number>"

    def test_three_parameters(self):
        """Trio<A, B, C>"""
        sub = TypeSubstitution()
        sub.bind("A", "string")
        sub.bind("B", "number")
        sub.bind("C", "boolean")

        result = sub.apply("Trio<A, B, C>")
        assert result == "Trio<string, number, boolean>"

    def test_mixed_bound_unbound(self):
        """일부만 bound"""
        sub = TypeSubstitution()
        sub.bind("T", "string")
        # U는 unbound

        result = sub.apply("Map<T, U>")
        assert result == "Map<string, U>"  # U는 그대로


class TestGenericInheritance:
    """Generic 상속"""

    def test_generic_constraint_from_parent(self):
        """부모 클래스의 Generic constraint"""
        tracker = GenericConstraintTracker()

        # Parent: class Base<T extends number>
        tracker.collect_from_dict("parent", {"name": "T", "constraint": "number"})

        # Child: class Child extends Base<T>
        # T는 number로 제약되어야 함
        constraint = tracker._constraints.get("parent::T")
        assert constraint is not None
        assert constraint.constraint == "number"


class TestCircularConstraints:
    """순환 Constraint (에러 처리)"""

    def test_circular_simple(self):
        """T = U, U = T"""
        sub = TypeSubstitution()
        sub.bind("T", "U")
        sub.bind("U", "T")

        # Should not infinite loop (simple string replace)
        result = sub.apply("T")
        assert result == "U"  # T → U (first substitution)

        # Applying again would go back to T
        result2 = sub.apply(result)
        assert result2 == "T"  # U → T

    def test_self_reference(self):
        """T = T"""
        sub = TypeSubstitution()
        sub.bind("T", "T")

        result = sub.apply("T")
        assert result == "T"  # No change


class TestBoundaryConditions:
    """경계 조건"""

    def test_empty_generic_params(self):
        """Generic 없음"""
        from codegraph_engine.code_foundation.infrastructure.ir.models import (
            IRDocument,
            Node,
            NodeKind,
            Span,
        )

        bi = BidirectionalInference()

        node = Node(
            id="func:1",
            kind=NodeKind.FUNCTION,
            fqn="test",
            file_path="test.ts",
            span=Span(1, 0, 1, 10),
            language="typescript",
            attrs={},  # No generic_params
        )

        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="test",
            nodes=[node],
            edges=[],
        )

        generics = bi.collect_generics_from_ir(ir_doc)
        assert len(generics) == 0

    def test_malformed_generic_param(self):
        """잘못된 generic 형식"""
        tracker = GenericConstraintTracker()

        # 잘못된 dict (name 없음)
        tracker.collect_from_dict("node:1", {"constraint": "string"})

        # Should not crash, just skip
        assert len(tracker._constraints) == 0

    def test_none_constraint(self):
        """constraint가 None"""
        tracker = GenericConstraintTracker()
        tracker.collect_from_dict("node:1", {"name": "T", "constraint": None})

        constraint = tracker._constraints.get("node:1::T")
        assert constraint is not None
        assert constraint.constraint is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
