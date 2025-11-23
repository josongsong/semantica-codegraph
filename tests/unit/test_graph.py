
from core.graph.builder import GraphBuilder
from core.parsers.base import CodeNode


def test_graph_builder():
    """그래프 빌더 테스트"""
    builder = GraphBuilder()

    node1 = CodeNode(
        type="function_definition",
        name="func1",
        start_line=1,
        end_line=5,
        content="def func1(): pass",
    )

    node2 = CodeNode(
        type="function_definition",
        name="func2",
        start_line=7,
        end_line=10,
        content="def func2(): pass",
    )

    graph = builder.build_from_nodes([node1, node2], "test.py")
    assert graph.number_of_nodes() == 2


def test_add_call_edges():
    """호출 관계 추가 테스트"""
    builder = GraphBuilder()
    builder.add_call_edges("func1", "func2")

    assert builder.graph.number_of_edges() == 1
    assert builder.graph.has_edge("func1", "func2")
