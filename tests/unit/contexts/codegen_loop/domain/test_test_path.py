"""
TestPath Domain Model Tests

SOTA L11급:
- Base cases
- Edge cases
- Corner cases
- Immutability
"""

import pytest

from codegraph_engine.code_foundation.domain.query.results import PathResult, UnifiedEdge, UnifiedNode
from codegraph_runtime.codegen_loop.domain.test_path import PATH_PRIORITY, PathType, TestPath


class TestTestPathBase:
    """Base cases - 정상 동작"""

    def test_create_security_path(self):
        """Security path 생성"""
        path_result = PathResult(nodes=[], edges=[])
        test_path = TestPath(
            path_result=path_result,
            path_type=PathType.SECURITY,
            target_function="foo.bar.process",
            context={"source": "request", "sink": "execute"},
        )

        assert test_path.priority == 100
        assert test_path.path_type == PathType.SECURITY
        assert test_path.target_function == "foo.bar.process"
        assert test_path.node_count == 0

    def test_create_exception_path(self):
        """Exception path 생성"""
        node1 = UnifiedNode(id="node1", kind="function", name="foo", file_path="test.py", span=None, attrs={})
        path_result = PathResult(nodes=[node1], edges=[])

        test_path = TestPath(
            path_result=path_result,
            path_type=PathType.EXCEPTION,
            target_function="handle_error",
            context={"type": "exception_handling"},
        )

        assert test_path.priority == 50
        assert test_path.node_count == 1

    def test_priority_ordering(self):
        """우선순위 정렬"""
        paths = [
            TestPath(PathResult([], []), PathType.UNCOVERED, "f1", {}),
            TestPath(PathResult([], []), PathType.SECURITY, "f2", {}),
            TestPath(PathResult([], []), PathType.EXCEPTION, "f3", {}),
            TestPath(PathResult([], []), PathType.NEW_CODE, "f4", {}),
        ]

        sorted_paths = sorted(paths)

        # Descending order (높은 우선순위가 먼저)
        assert sorted_paths[0].path_type == PathType.SECURITY
        assert sorted_paths[1].path_type == PathType.EXCEPTION
        assert sorted_paths[2].path_type == PathType.NEW_CODE
        assert sorted_paths[3].path_type == PathType.UNCOVERED


class TestTestPathEdge:
    """Edge cases - 경계 조건"""

    def test_empty_path_result(self):
        """빈 PathResult"""
        path_result = PathResult(nodes=[], edges=[])
        test_path = TestPath(path_result, PathType.NEW_CODE, "func", {})

        assert test_path.node_count == 0
        assert test_path.priority == 30

    def test_large_path(self):
        """큰 경로 (100 nodes)"""
        nodes = [
            UnifiedNode(id=f"n{i}", kind="var", name=f"v{i}", file_path="f.py", span=None, attrs={}) for i in range(100)
        ]
        path_result = PathResult(nodes=nodes, edges=[])

        test_path = TestPath(path_result, PathType.SECURITY, "func", {})
        assert test_path.node_count == 100

    def test_empty_context(self):
        """빈 context"""
        test_path = TestPath(PathResult([], []), PathType.EXCEPTION, "func", {})
        assert test_path.context == {}


class TestTestPathCorner:
    """Corner cases - 특수 케이스"""

    def test_immutability(self):
        """불변성 검증"""
        test_path = TestPath(PathResult([], []), PathType.SECURITY, "func", {"key": "value"})

        with pytest.raises(AttributeError):
            test_path.priority = 200  # type: ignore

        with pytest.raises(AttributeError):
            test_path.path_type = PathType.EXCEPTION  # type: ignore

    def test_priority_constants(self):
        """우선순위 상수 검증"""
        assert PATH_PRIORITY[PathType.SECURITY] == 100
        assert PATH_PRIORITY[PathType.EXCEPTION] == 50
        assert PATH_PRIORITY[PathType.NEW_CODE] == 30
        assert PATH_PRIORITY[PathType.UNCOVERED] == 20

    def test_comparison_with_non_testpath(self):
        """다른 타입과 비교"""
        test_path = TestPath(PathResult([], []), PathType.SECURITY, "func", {})

        result = test_path.__lt__("not a testpath")
        assert result is NotImplemented

    def test_very_long_fqn(self):
        """매우 긴 FQN (1000+ chars)"""
        long_fqn = "module." * 200 + "function"  # ~1400 chars
        test_path = TestPath(PathResult([], []), PathType.SECURITY, long_fqn, {})
        assert test_path.target_function == long_fqn
        assert len(test_path.target_function) > 1000

    def test_special_chars_in_function_name(self):
        """특수문자 포함 function name"""
        special_name = "func_<lambda>_$特殊_문자"
        test_path = TestPath(PathResult([], []), PathType.EXCEPTION, special_name, {})
        assert test_path.target_function == special_name

    def test_path_result_10000_nodes(self):
        """매우 큰 PathResult (10000 nodes)"""
        nodes = [
            UnifiedNode(id=f"n{i}", kind="var", name=f"v{i}", file_path="f.py", span=None, attrs={})
            for i in range(1000)  # 10000 → 1000
        ]
        path_result = PathResult(nodes=nodes, edges=[])
        test_path = TestPath(path_result, PathType.SECURITY, "func", {})
        assert test_path.node_count == 10000

    def test_same_priority_sorting_stable(self):
        """동일 priority 정렬 안정성"""
        paths = [TestPath(PathResult([], []), PathType.SECURITY, f"f{i}", {}) for i in range(10)]
        sorted_paths = sorted(paths)
        # All should be security (priority 100)
        assert all(p.priority == 100 for p in sorted_paths)

    def test_empty_target_function(self):
        """빈 target_function"""
        test_path = TestPath(PathResult([], []), PathType.NEW_CODE, "", {})
        assert test_path.target_function == ""

    def test_context_with_100_keys(self):
        """매우 큰 context (100 keys)"""
        large_context = {f"key{i}": f"value{i}" for i in range(100)}
        test_path = TestPath(PathResult([], []), PathType.EXCEPTION, "func", large_context)
        assert len(test_path.context) == 100

    def test_path_with_edges(self):
        """Edges 포함 PathResult"""
        nodes = [
            UnifiedNode(id="n1", kind="func", name="f1", file_path="f.py", span=None, attrs={}),
            UnifiedNode(id="n2", kind="func", name="f2", file_path="f.py", span=None, attrs={}),
        ]
        # UnifiedEdge uses from_node/to_node, not source/target
        edges = [UnifiedEdge(from_node="n1", to_node="n2", edge_type="calls", attrs={})]
        path_result = PathResult(nodes=nodes, edges=edges)
        test_path = TestPath(path_result, PathType.SECURITY, "func", {})
        assert test_path.node_count == 2
