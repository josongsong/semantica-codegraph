"""
Tests for Python Graph Builder

Tests AST → Graph transformation, edge extraction, and graph construction.
"""

import pytest

from src.core.ports.parser_port import CodeNode
from src.graph_construction.domain import EdgeType, NodeKind
from src.infra.graph_construction import PythonGraphBuilder, PythonNameResolver


class TestPythonGraphBuilderBasic:
    """Test basic graph construction"""

    @pytest.fixture
    def builder(self):
        resolver = PythonNameResolver(repo_root="/repo/src")
        return PythonGraphBuilder(name_resolver=resolver)

    def test_file_node_creation(self, builder):
        """Test: 파일 노드 생성"""
        code_nodes = [
            CodeNode(
                node_id="file_1",
                node_type="file",
                name="module",
                file_path="/repo/src/pkg/module.py",
                start_line=1,
                end_line=100,
                raw_code="",
            )
        ]

        result = builder.build_from_ast(
            code_nodes=code_nodes,
            file_path="/repo/src/pkg/module.py",
            repo_id="test_repo",
            namespace="main",
        )

        assert len(result.nodes) == 1
        file_node = result.nodes[0]
        assert file_node.kind == NodeKind.FILE
        assert file_node.id == "py://pkg.module"
        assert file_node.repo_id == "test_repo"
        assert file_node.namespace == "main"

    def test_class_node_creation(self, builder):
        """Test: 클래스 노드 생성"""
        code_nodes = [
            CodeNode(
                node_id="file_1",
                node_type="file",
                name="module",
                file_path="/repo/src/pkg/module.py",
                start_line=1,
                end_line=100,
                raw_code="",
            ),
            CodeNode(
                node_id="class_1",
                node_type="class",
                name="MyClass",
                file_path="/repo/src/pkg/module.py",
                start_line=10,
                end_line=50,
                raw_code="class MyClass:\n    pass",
                parent_id="file_1",
            ),
        ]

        result = builder.build_from_ast(
            code_nodes=code_nodes,
            file_path="/repo/src/pkg/module.py",
            repo_id="test_repo",
            namespace="main",
        )

        assert len(result.nodes) == 2
        class_node = next(n for n in result.nodes if n.kind == NodeKind.CLASS)
        assert class_node.id == "py://pkg.module.MyClass"
        assert class_node.attrs["name"] == "MyClass"
        assert class_node.attrs["start_line"] == 10

    def test_function_node_creation(self, builder):
        """Test: 함수 노드 생성"""
        code_nodes = [
            CodeNode(
                node_id="file_1",
                node_type="file",
                name="utils",
                file_path="/repo/src/utils.py",
                start_line=1,
                end_line=50,
                raw_code="",
            ),
            CodeNode(
                node_id="func_1",
                node_type="function",
                name="helper",
                file_path="/repo/src/utils.py",
                start_line=5,
                end_line=15,
                raw_code="def helper():\n    pass",
                parent_id="file_1",
            ),
        ]

        result = builder.build_from_ast(
            code_nodes=code_nodes,
            file_path="/repo/src/utils.py",
            repo_id="test_repo",
            namespace="main",
        )

        func_node = next(n for n in result.nodes if n.kind == NodeKind.FUNCTION)
        assert func_node.id == "py://utils.helper"


class TestPythonGraphBuilderEdges:
    """Test edge extraction"""

    @pytest.fixture
    def builder(self):
        resolver = PythonNameResolver(repo_root="/repo/src")
        return PythonGraphBuilder(name_resolver=resolver)

    def test_defines_edge_creation(self, builder):
        """Test: file --defines--> symbol 엣지"""
        code_nodes = [
            CodeNode(
                node_id="file_1",
                node_type="file",
                name="module",
                file_path="/repo/src/pkg/module.py",
                start_line=1,
                end_line=50,
                raw_code="",
            ),
            CodeNode(
                node_id="func_1",
                node_type="function",
                name="process",
                file_path="/repo/src/pkg/module.py",
                start_line=5,
                end_line=15,
                raw_code="",
                parent_id="file_1",
            ),
        ]

        result = builder.build_from_ast(
            code_nodes=code_nodes,
            file_path="/repo/src/pkg/module.py",
            repo_id="test_repo",
            namespace="main",
        )

        defines_edges = [e for e in result.edges if e.edge_type == EdgeType.DEFINES]
        assert len(defines_edges) == 1
        assert defines_edges[0].src_id == "py://pkg.module"
        assert defines_edges[0].dst_id == "py://pkg.module.process"

    def test_contains_edge_creation(self, builder):
        """Test: parent --contains--> child 엣지"""
        code_nodes = [
            CodeNode(
                node_id="file_1",
                node_type="file",
                name="module",
                file_path="/repo/src/pkg/module.py",
                start_line=1,
                end_line=100,
                raw_code="",
            ),
            CodeNode(
                node_id="class_1",
                node_type="class",
                name="Service",
                file_path="/repo/src/pkg/module.py",
                start_line=10,
                end_line=80,
                raw_code="",
                parent_id="file_1",
            ),
            CodeNode(
                node_id="method_1",
                node_type="method",
                name="run",
                file_path="/repo/src/pkg/module.py",
                start_line=20,
                end_line=30,
                raw_code="",
                parent_id="class_1",
                attrs={"parent_name": "Service"},
            ),
        ]

        result = builder.build_from_ast(
            code_nodes=code_nodes,
            file_path="/repo/src/pkg/module.py",
            repo_id="test_repo",
            namespace="main",
        )

        contains_edges = [e for e in result.edges if e.edge_type == EdgeType.CONTAINS]
        assert len(contains_edges) == 2

        # file --contains--> class
        file_contains = next(e for e in contains_edges if e.src_id == "py://pkg.module")
        assert file_contains.dst_id == "py://pkg.module.Service"

        # class --contains--> method
        class_contains = next(e for e in contains_edges if e.src_id == "py://pkg.module.Service")
        assert class_contains.dst_id == "py://pkg.module.Service.run"

    def test_call_edge_extraction(self, builder):
        """Test: 함수 호출 엣지 추출"""
        code_nodes = [
            CodeNode(
                node_id="file_1",
                node_type="file",
                name="module",
                file_path="/repo/src/module.py",
                start_line=1,
                end_line=50,
                raw_code="",
            ),
            CodeNode(
                node_id="func_1",
                node_type="function",
                name="caller",
                file_path="/repo/src/module.py",
                start_line=5,
                end_line=10,
                raw_code="",
                parent_id="file_1",
                attrs={"calls": ["helper"]},
            ),
            CodeNode(
                node_id="func_2",
                node_type="function",
                name="helper",
                file_path="/repo/src/module.py",
                start_line=12,
                end_line=15,
                raw_code="",
                parent_id="file_1",
            ),
        ]

        result = builder.build_from_ast(
            code_nodes=code_nodes,
            file_path="/repo/src/module.py",
            repo_id="test_repo",
            namespace="main",
        )

        call_edges = [e for e in result.edges if e.edge_type == EdgeType.CALLS]
        assert len(call_edges) == 1
        assert call_edges[0].src_id == "py://module.caller"
        assert call_edges[0].dst_id == "py://module.helper"

    def test_import_edge_extraction(self, builder):
        """Test: Import 엣지 추출"""
        code_nodes = [
            CodeNode(
                node_id="file_1",
                node_type="file",
                name="module",
                file_path="/repo/src/pkg/module.py",
                start_line=1,
                end_line=50,
                raw_code="",
                attrs={
                    "imports": [
                        {"name": "os.path", "kind": "module"},
                        {"name": ".utils", "kind": "module"},
                    ]
                },
            ),
        ]

        result = builder.build_from_ast(
            code_nodes=code_nodes,
            file_path="/repo/src/pkg/module.py",
            repo_id="test_repo",
            namespace="main",
        )

        import_edges = [e for e in result.edges if e.edge_type == EdgeType.IMPORTS]
        assert len(import_edges) == 2

        # Absolute import
        abs_import = next(e for e in import_edges if "os.path" in e.attrs["import_name"])
        assert abs_import.dst_id == "py://os.path"

        # Relative import
        rel_import = next(e for e in import_edges if ".utils" in e.attrs["import_name"])
        assert rel_import.dst_id == "py://pkg.utils"


class TestPythonGraphBuilderIntegration:
    """Integration tests with realistic code structures"""

    @pytest.fixture
    def builder(self):
        resolver = PythonNameResolver(repo_root="/repo/src")
        return PythonGraphBuilder(name_resolver=resolver)

    def test_complete_module_graph(self, builder):
        """Test: 완전한 모듈 그래프 생성"""
        code_nodes = [
            # File
            CodeNode(
                node_id="file_1",
                node_type="file",
                name="service",
                file_path="/repo/src/api/service.py",
                start_line=1,
                end_line=100,
                raw_code="",
                attrs={"imports": [{"name": "..models", "kind": "module"}]},
            ),
            # Class
            CodeNode(
                node_id="class_1",
                node_type="class",
                name="UserService",
                file_path="/repo/src/api/service.py",
                start_line=10,
                end_line=80,
                raw_code="",
                parent_id="file_1",
            ),
            # Method
            CodeNode(
                node_id="method_1",
                node_type="method",
                name="get_user",
                file_path="/repo/src/api/service.py",
                start_line=20,
                end_line=30,
                raw_code="",
                parent_id="class_1",
                attrs={"parent_name": "UserService", "calls": ["validate"]},
            ),
            # Helper function
            CodeNode(
                node_id="func_1",
                node_type="function",
                name="validate",
                file_path="/repo/src/api/service.py",
                start_line=85,
                end_line=95,
                raw_code="",
                parent_id="file_1",
            ),
        ]

        result = builder.build_from_ast(
            code_nodes=code_nodes,
            file_path="/repo/src/api/service.py",
            repo_id="test_repo",
            namespace="main",
        )

        # Validate nodes
        assert len(result.nodes) == 4  # file + class + method + function
        assert result.node_count == 4

        # Validate edges
        assert len(result.edges) > 0

        # Check specific edge types
        defines_edges = [e for e in result.edges if e.edge_type == EdgeType.DEFINES]
        contains_edges = [e for e in result.edges if e.edge_type == EdgeType.CONTAINS]
        calls_edges = [e for e in result.edges if e.edge_type == EdgeType.CALLS]
        import_edges = [e for e in result.edges if e.edge_type == EdgeType.IMPORTS]

        assert len(defines_edges) == 3  # file defines class, method, function
        assert len(contains_edges) >= 2  # file->class, class->method
        assert len(calls_edges) == 1  # method calls function
        assert len(import_edges) == 1  # file imports models

    def test_edge_id_deterministic(self, builder):
        """Test: Edge ID는 결정론적"""
        code_nodes = [
            CodeNode(
                node_id="file_1",
                node_type="file",
                name="module",
                file_path="/repo/src/module.py",
                start_line=1,
                end_line=20,
                raw_code="",
            ),
            CodeNode(
                node_id="func_1",
                node_type="function",
                name="foo",
                file_path="/repo/src/module.py",
                start_line=5,
                end_line=10,
                raw_code="",
                parent_id="file_1",
            ),
        ]

        result1 = builder.build_from_ast(
            code_nodes=code_nodes,
            file_path="/repo/src/module.py",
            repo_id="test_repo",
            namespace="main",
        )

        result2 = builder.build_from_ast(
            code_nodes=code_nodes,
            file_path="/repo/src/module.py",
            repo_id="test_repo",
            namespace="main",
        )

        # 같은 입력은 같은 edge ID 생성
        edge_ids_1 = {e.id for e in result1.edges}
        edge_ids_2 = {e.id for e in result2.edges}
        assert edge_ids_1 == edge_ids_2
