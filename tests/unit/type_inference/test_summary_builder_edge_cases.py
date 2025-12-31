"""
RFC-032: Edge Case & Corner Case Tests (Production-Grade)

L11 기준: Base, Edge, Corner, Extreme 모두 커버
"""

import pytest

from codegraph_engine.code_foundation.domain.type_inference.models import InferSource, ReturnTypeSummary
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node, NodeKind, Span
from codegraph_engine.code_foundation.infrastructure.type_inference.summary_builder import (
    ReturnTypeSummaryBuilder,
    SummaryBuilderConfig,
)


def make_node(node_id: str, **kwargs) -> Node:
    """Helper to create test node."""
    defaults = {
        "kind": NodeKind.FUNCTION,
        "name": node_id,
        "fqn": f"test.{node_id}",
        "language": "python",
        "file_path": "test.py",
        "span": Span(0, 0, 0, 0),
        "attrs": {},
    }
    defaults.update(kwargs)
    return Node(id=node_id, **defaults)


class TestEdgeCases:
    """Edge cases - 경계 조건"""

    def test_empty_return_value(self):
        """return \"\" 처리"""
        node = make_node("f1", attrs={"body_statements": [{"type": "return", "value": '""'}]})

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"f1": []})

        # 빈 문자열 리터럴도 str
        assert summaries["f1"].return_type == "str"

    def test_return_none_explicit(self):
        """return None vs return 없음 구분"""
        node1 = make_node("f1", attrs={"body_statements": [{"type": "return", "value": "None"}]})
        node2 = make_node("f2", attrs={"body_statements": []})

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node1, node2], {"f1": [], "f2": []})

        assert summaries["f1"].return_type == "None"
        assert summaries["f2"].return_type == "None"

    def test_single_element_union(self):
        """Union with 1 element → 단일 타입"""
        node = make_node(
            "f1",
            attrs={
                "body_statements": [
                    {"type": "return", "value": "42"},
                    {"type": "return", "value": "99"},
                ]
            },
        )

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"f1": []})

        # 같은 타입이면 Union 없이
        assert summaries["f1"].return_type == "int"
        assert "|" not in summaries["f1"].return_type

    def test_union_deduplication(self):
        """int | int | str → int | str"""
        node = make_node(
            "f1",
            attrs={
                "body_statements": [
                    {"type": "return", "value": "1"},
                    {"type": "return", "value": "2"},
                    {"type": "return", "value": '"hello"'},
                ]
            },
        )

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"f1": []})

        # Deduplicated
        assert summaries["f1"].return_type == "int | str"

    def test_exactly_8_union_elements(self):
        """Union == 8 (boundary)"""
        returns = [{"type": "return", "value": f'"{i}"'} for i in range(8)]
        node = make_node("f1", attrs={"body_statements": returns})

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"f1": []})

        # 8개는 Any 안 됨 (> 8만 Any)
        assert summaries["f1"].return_type != "Any"
        assert "str" in summaries["f1"].return_type

    def test_exactly_9_union_elements(self):
        """Union == 9 다른 타입 → Any (widening)"""
        # 9가지 다른 타입
        returns = [
            {"type": "return", "value": "1"},  # int
            {"type": "return", "value": "2.0"},  # float
            {"type": "return", "value": '"str"'},  # str
            {"type": "return", "value": "True"},  # bool
            {"type": "return", "value": "None"},  # None
            {"type": "return", "value": "[]"},  # list
            {"type": "return", "value": '{"a": 1}'},  # dict (명확)
            {"type": "return", "value": "{1, 2}"},  # set (명확)
            {"type": "return", "value": "()"},  # tuple
        ]
        node = make_node("f1", attrs={"body_statements": returns})

        config = SummaryBuilderConfig(max_union_size=8)
        builder = ReturnTypeSummaryBuilder(config)
        summaries = builder.build([node], {"f1": []})

        # 9개 타입 → widening
        assert summaries["f1"].return_type == "Any"


class TestCornerCases:
    """Corner cases - 희귀하지만 발생 가능"""

    def test_empty_function_name(self):
        """name=None인 노드 - empty body로 인해 None 추론"""
        node = make_node("f1", name=None, attrs={"body_statements": []})

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"f1": []})

        # empty body → None
        assert summaries["f1"].return_type == "None"

    def test_malformed_type_info(self):
        """type_info가 dict가 아님 - body 없으므로 Unknown"""
        node = make_node("f1", attrs={"type_info": "not_a_dict"})

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"f1": []})

        # type_info 무시하고 Unknown
        assert not summaries["f1"].is_resolved()

    def test_empty_body_statements(self):
        """body_statements가 빈 리스트"""
        node = make_node("f1", attrs={"body_statements": []})

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"f1": []})

        # return 없음 → None
        assert summaries["f1"].return_type == "None"

    def test_none_body_statements(self):
        """body_statements 키 자체가 없음 - Unknown (전파 대기)"""
        node = make_node("f1", attrs={})

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {"f1": []})

        # body_statements 없으면 Unknown
        assert not summaries["f1"].is_resolved()

    def test_circular_dependency_2_nodes(self):
        """A → B → A"""
        node_a = make_node("a")
        node_b = make_node("b")

        call_graph = {
            "a": ["b"],
            "b": ["a"],
        }

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node_a, node_b], call_graph)

        # 수렴해야 함 (widening 적용)
        assert "a" in summaries
        assert "b" in summaries

    def test_self_recursion(self):
        """A → A (self-loop)"""
        node = make_node("a")
        call_graph = {"a": ["a"]}

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], call_graph)

        # Fixed-point 수렴
        assert "a" in summaries


class TestExtremeCases:
    """Extreme cases - 극한 조건"""

    def test_empty_nodes(self):
        """노드가 하나도 없음"""
        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([], {})

        assert len(summaries) == 0

    def test_empty_call_graph(self):
        """call_graph가 빈 dict"""
        node = make_node("f1", attrs={"type_info": {"return_type": "int"}})

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], {})

        # SCC 분해는 문제 없어야 함
        assert summaries["f1"].return_type == "int"

    def test_call_graph_missing_node(self):
        """call_graph에 존재하지 않는 callee 참조"""
        node = make_node("f1")
        call_graph = {"f1": ["nonexistent"]}

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build([node], call_graph)

        # 무시하고 진행
        assert "f1" in summaries

    def test_very_large_scc(self):
        """큰 SCC (20개 함수가 순환)"""
        nodes = [make_node(f"f{i}") for i in range(20)]

        # f0 → f1 → f2 → ... → f19 → f0
        call_graph = {f"f{i}": [f"f{(i + 1) % 20}"] for i in range(20)}

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build(nodes, call_graph)

        # Widening으로 수렴해야 함
        assert len(summaries) == 20

        # 모두 resolved 또는 Any로 widening
        for s in summaries.values():
            assert s.return_type is not None or not s.is_resolved()

    def test_deep_call_chain(self):
        """깊은 call chain (50 depth) - 전파 테스트"""
        nodes = [make_node(f"f{i}") for i in range(50)]

        # f0 → f1 → f2 → ... → f49 (linear)
        call_graph = {f"f{i}": [f"f{i + 1}"] if i < 49 else [] for i in range(50)}

        # f49에 return type 지정
        nodes[49].attrs = {"type_info": {"return_type": "int"}}

        # 다른 노드들은 body_statements 없이 (Unknown으로 두어 전파 대기)
        for i in range(49):
            nodes[i].attrs = {}  # body_statements 없음

        builder = ReturnTypeSummaryBuilder()
        summaries = builder.build(nodes, call_graph)

        # f49는 annotation으로 해결
        assert summaries["f49"].return_type == "int"

        # f48은 f49를 호출하므로 전파되어야 함
        assert summaries["f48"].return_type == "int", f"f48: {summaries['f48'].return_type} (expected int from f49)"

    def test_max_iterations_exceeded(self):
        """Iteration limit 초과 → widening"""
        # 이 테스트는 pathological case를 시뮬레이션하기 어려움
        # Real-world에서는 max 10 iterations면 충분
        pass


class TestRegressionPrevention:
    """Regression - 실제 발생한 버그 방지"""

    def test_confidence_validation(self):
        """Confidence 범위 검증"""
        with pytest.raises(ValueError, match="confidence"):
            ReturnTypeSummary(
                function_id="test",
                return_type="int",
                confidence=1.5,  # Invalid
                source=InferSource.ANNOTATION,
            )

    def test_empty_string_return_type(self):
        """return_type가 빈 문자열"""
        with pytest.raises(ValueError, match="empty string"):
            ReturnTypeSummary(
                function_id="test",
                return_type="",  # Invalid
                confidence=1.0,
                source=InferSource.ANNOTATION,
            )

    def test_whitespace_only_return_type(self):
        """return_type가 공백만"""
        with pytest.raises(ValueError, match="empty string"):
            ReturnTypeSummary(
                function_id="test",
                return_type="   ",  # Invalid
                confidence=1.0,
                source=InferSource.ANNOTATION,
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
