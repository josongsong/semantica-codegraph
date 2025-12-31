"""
TDD: Bidirectional Type Inference

Red Phase: 실패하는 테스트 작성

Test Coverage:
- Top-down inference (expected type → expression)
- Bottom-up inference (expression → inferred type)
- Meet (combine both directions)
- Generic constraint tracking
"""

import pytest

from codegraph_engine.code_foundation.domain.type_inference.models import (
    ExpressionTypeRequest,
    InferContext,
)
from codegraph_engine.code_foundation.infrastructure.type_inference.bidirectional import (
    BidirectionalInference,
)


class TestBidirectionalBasic:
    """기본 Bidirectional 추론"""

    def test_top_down_from_annotation(self):
        """Top-down: Annotation으로부터 기대 타입"""
        # const x: string[] = expr
        # expected_type = string[] → expr should be string[]

        bi_infer = BidirectionalInference()

        # Top-down with expected type
        result = bi_infer.infer_top_down("string[]")

        assert result.inferred_type == "string[]"
        assert result.source.value == "annotation"

    def test_bottom_up_from_literal(self):
        """Bottom-up: Literal로부터 타입 추론"""
        # const x = [1, 2, 3]
        # literal [1, 2, 3] → number[]

        bi_infer = BidirectionalInference()

        # Bottom-up from literal
        result = bi_infer.infer_bottom_up([1, 2, 3])

        assert result.inferred_type == "number[]"
        assert result.source.value == "literal"

    def test_meet_both_directions(self):
        """Meet: Top-down과 Bottom-up 결합"""
        # const x: number[] = [1, 2, 3]
        # top-down: number[]
        # bottom-up: number[]
        # → meet: number[]

        bi_infer = BidirectionalInference()

        top_down = "number[]"
        bottom_up = "number[]"

        result = bi_infer.meet(top_down, bottom_up)

        assert result == "number[]"

    def test_meet_conflict(self):
        """Meet: 타입 충돌"""
        # const x: string[] = [1, 2, 3]
        # top-down: string[]
        # bottom-up: number[]
        # → error or widen to any[]

        bi_infer = BidirectionalInference()

        result = bi_infer.meet("string[]", "number[]")

        # Should return error or widened type
        assert result in ["error", "any[]", "unknown"]


class TestGenericConstraint:
    """Generic 제약 추적"""

    def test_collect_generic_constraint(self):
        """Generic constraint 수집"""
        # function identity<T extends string>(x: T): T
        # → T extends string

        from codegraph_engine.code_foundation.infrastructure.type_inference.generic_constraint import (
            GenericConstraintTracker,
        )
        from codegraph_engine.code_foundation.infrastructure.ir.models import Node, NodeKind

        tracker = GenericConstraintTracker()

        from codegraph_engine.code_foundation.infrastructure.ir.models import Span

        func_node = Node(
            id="func:1",
            kind=NodeKind.FUNCTION,
            fqn="identity",
            file_path="test.ts",
            span=Span(1, 0, 1, 10),
            language="typescript",
            attrs={"type_parameters": [{"name": "T", "constraint": "string"}]},
        )

        constraints = tracker.collect(func_node)

        assert len(constraints) == 1
        assert constraints[0].type_var == "T"
        assert constraints[0].constraint == "string"

    def test_unify_generic_with_concrete(self):
        """Generic을 concrete type과 unify"""
        # identity<T>(42) → T = number

        from codegraph_engine.code_foundation.infrastructure.type_inference.generic_constraint import (
            GenericConstraintTracker,
        )

        tracker = GenericConstraintTracker()

        # T가 number로 결정됨
        tracker.unify("T", "number")

        result = tracker.get_bound_type("T")

        assert result == "number"

    def test_constraint_propagation(self):
        """Constraint 전파"""
        # function process<T extends number>(x: T): T { return x; }
        # const result = process(42)
        # → T = 42 (literal) → number (widen)

        from codegraph_engine.code_foundation.infrastructure.type_inference.generic_constraint import (
            ConstraintPropagation,
        )

        propagator = ConstraintPropagation()

        # T extends number 제약
        propagator.add_constraint("T", "extends", "number")

        # T = 42 (literal)
        propagator.unify("T", "42")

        # Propagate: 42 → number (widen to constraint)
        result = propagator.resolve("T")

        assert result == "number"


class TestGenericSubstitution:
    """Generic 치환"""

    def test_substitute_simple(self):
        """단순 치환"""
        # T → number
        # List<T> → List<number>

        from codegraph_engine.code_foundation.infrastructure.type_inference.generic_constraint import (
            TypeSubstitution,
        )

        sub = TypeSubstitution()
        sub.bind("T", "number")

        result = sub.apply("List<T>")

        assert result == "List<number>"

    def test_substitute_multiple(self):
        """여러 타입 변수 치환"""
        # T → string, U → number
        # Map<T, U> → Map<string, number>

        from codegraph_engine.code_foundation.infrastructure.type_inference.generic_constraint import (
            TypeSubstitution,
        )

        sub = TypeSubstitution()
        sub.bind("T", "string")
        sub.bind("U", "number")

        result = sub.apply("Map<T, U>")

        assert result == "Map<string, number>"

    def test_substitute_nested(self):
        """중첩 Generic 치환"""
        # T → List<string>
        # Result<T> → Result<List<string>>

        from codegraph_engine.code_foundation.infrastructure.type_inference.generic_constraint import (
            TypeSubstitution,
        )

        sub = TypeSubstitution()
        sub.bind("T", "List<string>")

        result = sub.apply("Result<T>")

        assert result == "Result<List<string>>"


class TestKotlinGeneric:
    """Kotlin Generic 추론"""

    def test_kotlin_generic_constraint(self):
        """Kotlin: T : Number"""
        # fun <T : Number> process(x: T): T

        from codegraph_engine.code_foundation.infrastructure.type_inference.generic_constraint import (
            GenericConstraintTracker,
        )
        from codegraph_engine.code_foundation.infrastructure.ir.models import Node, NodeKind

        tracker = GenericConstraintTracker()

        from codegraph_engine.code_foundation.infrastructure.ir.models import Span

        func_node = Node(
            id="func:1",
            kind=NodeKind.FUNCTION,
            fqn="process",
            file_path="test.kt",
            span=Span(1, 0, 1, 10),
            language="kotlin",
            attrs={"type_parameters": [{"name": "T", "constraint": "Number"}]},
        )

        constraints = tracker.collect(func_node)

        assert len(constraints) == 1
        assert constraints[0].type_var == "T"
        assert constraints[0].constraint == "Number"

    def test_kotlin_nullable_generic(self):
        """Kotlin: T?"""
        # fun <T> firstOrNull(list: List<T>): T?

        from codegraph_engine.code_foundation.infrastructure.type_inference.generic_constraint import (
            TypeSubstitution,
        )

        sub = TypeSubstitution()
        sub.bind("T", "Int")

        result = sub.apply("T?")

        assert result == "Int?"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
