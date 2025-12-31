"""
Query Results Unit Tests

SOTA L11급:
- Base case: PathResult, PathSet, UnifiedNode, UnifiedEdge
- Edge case: 빈 컬렉션, None 처리
- Corner case: 큰 path, 특수 문자
"""

import pytest

from codegraph_engine.code_foundation.domain.query.results import (
    PathResult,
    PathSet,
    TruncationReason,
    UnifiedEdge,
    UnifiedNode,
    VerificationResult,
)
from codegraph_engine.code_foundation.domain.query.types import EdgeType, NodeKind


class TestUnifiedNode:
    """UnifiedNode 테스트"""

    def test_base_case_creation(self):
        """기본 생성"""
        node = UnifiedNode(
            id="node_1",
            kind=NodeKind.VAR,
            name="x",
            file_path="test.py",
            span=(1, 0, 1, 10),
        )

        assert node.id == "node_1"
        assert node.kind == NodeKind.VAR
        assert node.name == "x"
        assert node.file_path == "test.py"
        assert node.span == (1, 0, 1, 10)

    def test_base_case_repr(self):
        """__repr__ 확인"""
        node = UnifiedNode(
            id="node_1",
            kind=NodeKind.FUNC,
            name="process",
            file_path="test.py",
            span=(10, 0, 20, 0),
        )

        repr_str = repr(node)
        assert "func" in repr_str.lower()
        assert "process" in repr_str

    def test_edge_case_none_span(self):
        """span이 None인 경우"""
        node = UnifiedNode(
            id="node_1",
            kind=NodeKind.VAR,
            name="x",
            file_path="test.py",
            span=None,
        )

        repr_str = repr(node)
        assert "test.py" in repr_str

    def test_edge_case_none_name(self):
        """name이 None인 경우"""
        node = UnifiedNode(
            id="node_1",
            kind=NodeKind.EXPR,
            name=None,
            file_path="test.py",
            span=(1, 0, 1, 10),
        )

        repr_str = repr(node)
        assert "node_1" in repr_str

    def test_corner_case_string_kind(self):
        """kind가 string인 경우 (backward compatibility)"""
        node = UnifiedNode(
            id="node_1",
            kind="custom_kind",
            name="x",
            file_path="test.py",
            span=(1, 0, 1, 10),
        )

        assert node.kind == "custom_kind"


class TestUnifiedEdge:
    """UnifiedEdge 테스트"""

    def test_base_case_creation(self):
        """기본 생성"""
        edge = UnifiedEdge(
            from_node="node_1",
            to_node="node_2",
            edge_type=EdgeType.DFG,
        )

        assert edge.from_node == "node_1"
        assert edge.to_node == "node_2"
        assert edge.edge_type == EdgeType.DFG

    def test_base_case_repr(self):
        """__repr__ 확인"""
        edge = UnifiedEdge(
            from_node="node_1",
            to_node="node_2",
            edge_type=EdgeType.CALL,
        )

        repr_str = repr(edge)
        assert "node_1" in repr_str
        assert "node_2" in repr_str

    def test_edge_case_with_attrs(self):
        """attrs 포함"""
        edge = UnifiedEdge(
            from_node="node_1",
            to_node="node_2",
            edge_type=EdgeType.DFG,
            attrs={"label": "def-use"},
        )

        assert edge.attrs["label"] == "def-use"


class TestPathResult:
    """PathResult 테스트"""

    def _create_node(self, id: str, name: str) -> UnifiedNode:
        return UnifiedNode(
            id=id,
            kind=NodeKind.VAR,
            name=name,
            file_path="test.py",
            span=(1, 0, 1, 10),
        )

    def _create_edge(self, from_id: str, to_id: str) -> UnifiedEdge:
        return UnifiedEdge(
            from_node=from_id,
            to_node=to_id,
            edge_type=EdgeType.DFG,
        )

    def test_base_case_creation(self):
        """기본 생성"""
        nodes = [self._create_node("n1", "x"), self._create_node("n2", "y")]
        edges = [self._create_edge("n1", "n2")]

        path = PathResult(nodes=nodes, edges=edges)

        assert len(path) == 2
        assert len(path.edges) == 1

    def test_base_case_iteration(self):
        """iteration 지원"""
        nodes = [self._create_node(f"n{i}", f"x{i}") for i in range(3)]
        edges = [self._create_edge(f"n{i}", f"n{i + 1}") for i in range(2)]

        path = PathResult(nodes=nodes, edges=edges)

        collected = list(path)
        assert len(collected) == 3

    def test_base_case_indexing(self):
        """indexing 지원"""
        nodes = [self._create_node("n1", "x"), self._create_node("n2", "y")]
        path = PathResult(nodes=nodes, edges=[])

        assert path[0].name == "x"
        assert path[1].name == "y"

    def test_base_case_subpath(self):
        """subpath 추출"""
        nodes = [self._create_node(f"n{i}", f"x{i}") for i in range(5)]
        edges = [self._create_edge(f"n{i}", f"n{i + 1}") for i in range(4)]

        path = PathResult(nodes=nodes, edges=edges)
        sub = path.subpath(1, 3)

        assert len(sub) == 2
        assert sub[0].name == "x1"
        assert sub[1].name == "x2"

    def test_edge_case_empty_path(self):
        """빈 path"""
        path = PathResult(nodes=[], edges=[])

        assert len(path) == 0

    def test_edge_case_single_node(self):
        """단일 노드"""
        path = PathResult(nodes=[self._create_node("n1", "x")], edges=[])

        assert len(path) == 1
        assert len(path.edges) == 0

    def test_corner_case_uncertain_path(self):
        """uncertain path (may-alias)"""
        path = PathResult(
            nodes=[self._create_node("n1", "x")],
            edges=[],
            uncertain=True,
        )

        assert path.uncertain is True


class TestPathSet:
    """PathSet 테스트"""

    def _create_path(self, length: int) -> PathResult:
        nodes = [
            UnifiedNode(
                id=f"n{i}",
                kind=NodeKind.VAR,
                name=f"x{i}",
                file_path="test.py",
                span=(i, 0, i, 10),
            )
            for i in range(length)
        ]
        return PathResult(nodes=nodes, edges=[])

    def test_base_case_creation(self):
        """기본 생성"""
        paths = [self._create_path(3), self._create_path(5)]
        pathset = PathSet(paths=paths, complete=True)

        assert len(pathset) == 2
        assert pathset.complete is True

    def test_base_case_bool(self):
        """bool 변환"""
        assert bool(PathSet(paths=[self._create_path(1)], complete=True)) is True
        assert bool(PathSet(paths=[], complete=True)) is False

    def test_base_case_shortest(self):
        """shortest path"""
        paths = [self._create_path(5), self._create_path(2), self._create_path(3)]
        pathset = PathSet(paths=paths, complete=True)

        shortest = pathset.shortest()
        assert len(shortest) == 2

    def test_base_case_longest(self):
        """longest path"""
        paths = [self._create_path(5), self._create_path(2), self._create_path(3)]
        pathset = PathSet(paths=paths, complete=True)

        longest = pathset.longest()
        assert len(longest) == 5

    def test_base_case_limit(self):
        """limit"""
        paths = [self._create_path(i) for i in range(10)]
        pathset = PathSet(paths=paths, complete=True)

        limited = pathset.limit(3)
        assert len(limited) == 3

    def test_edge_case_empty_pathset(self):
        """빈 PathSet"""
        pathset = PathSet(paths=[], complete=True)

        assert len(pathset) == 0
        assert bool(pathset) is False

    def test_edge_case_shortest_empty_raises(self):
        """빈 PathSet에서 shortest() 호출 시 에러"""
        pathset = PathSet(paths=[], complete=True)

        with pytest.raises(ValueError, match="No paths"):
            pathset.shortest()

    def test_corner_case_truncated(self):
        """truncated PathSet"""
        pathset = PathSet(
            paths=[self._create_path(3)],
            complete=False,
            truncation_reason=TruncationReason.TIMEOUT,
        )

        assert pathset.complete is False
        assert "timeout" in pathset.describe()

    def test_corner_case_describe(self):
        """describe 출력"""
        pathset = PathSet(paths=[self._create_path(1)], complete=True)

        desc = pathset.describe()
        assert "1 paths" in desc
        assert "complete" in desc


class TestVerificationResult:
    """VerificationResult 테스트"""

    def test_base_case_ok(self):
        """성공 결과"""
        result = VerificationResult(ok=True)

        assert result.ok is True
        assert result.violation_path is None
        assert bool(result) is True

    def test_base_case_violation(self):
        """위반 결과"""
        violation = PathResult(nodes=[], edges=[])
        result = VerificationResult(ok=False, violation_path=violation)

        assert result.ok is False
        assert result.violation_path is violation
        assert bool(result) is False

    def test_base_case_repr(self):
        """__repr__"""
        ok_result = VerificationResult(ok=True)
        fail_result = VerificationResult(ok=False)

        assert "ok=True" in repr(ok_result)
        assert "ok=False" in repr(fail_result)
