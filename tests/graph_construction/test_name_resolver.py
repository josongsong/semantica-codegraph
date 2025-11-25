"""
Tests for Python Name Resolver

Tests FQN generation, import resolution, and synthetic ID creation.
"""

import pytest

from src.core.ports.parser_port import CodeNode
from src.graph_construction.ports import NameResolutionError
from src.infra.graph_construction import PythonNameResolver


class TestPythonNameResolverFQN:
    """Test FQN generation for different node types"""

    @pytest.fixture
    def resolver(self):
        return PythonNameResolver(repo_root="/repo/src")

    def test_file_node_fqn(self, resolver):
        """Test: File 노드는 py://module 형식"""
        node = CodeNode(
            node_id="file_1",
            node_type="file",
            name="utils",
            file_path="/repo/src/pkg/utils.py",
            start_line=1,
            end_line=100,
            raw_code="",
        )

        fqn = resolver.resolve_fqn(node, "/repo/src/pkg/utils.py")
        assert fqn == "py://pkg.utils"

    def test_class_node_fqn(self, resolver):
        """Test: Class 노드는 py://module.ClassName"""
        node = CodeNode(
            node_id="class_1",
            node_type="class",
            name="MyClass",
            file_path="/repo/src/pkg/module.py",
            start_line=10,
            end_line=50,
            raw_code="",
        )

        fqn = resolver.resolve_fqn(node, "/repo/src/pkg/module.py")
        assert fqn == "py://pkg.module.MyClass"

    def test_function_node_fqn(self, resolver):
        """Test: Function 노드는 py://module.function_name"""
        node = CodeNode(
            node_id="func_1",
            node_type="function",
            name="calculate",
            file_path="/repo/src/math/ops.py",
            start_line=5,
            end_line=15,
            raw_code="",
        )

        fqn = resolver.resolve_fqn(node, "/repo/src/math/ops.py")
        assert fqn == "py://math.ops.calculate"

    def test_method_node_fqn(self, resolver):
        """Test: Method 노드는 py://module.ClassName.method_name"""
        node = CodeNode(
            node_id="method_1",
            node_type="method",
            name="process",
            file_path="/repo/src/pkg/service.py",
            start_line=20,
            end_line=30,
            raw_code="",
            attrs={"parent_name": "DataService"},
        )

        fqn = resolver.resolve_fqn(node, "/repo/src/pkg/service.py")
        assert fqn == "py://pkg.service.DataService.process"

    def test_nested_class_method_fqn(self, resolver):
        """Test: Nested class의 method FQN"""
        node = CodeNode(
            node_id="method_2",
            node_type="method",
            name="inner_method",
            file_path="/repo/src/pkg/models.py",
            start_line=40,
            end_line=45,
            raw_code="",
            attrs={"parent_fqn": "py://pkg.models.OuterClass"},
        )

        fqn = resolver.resolve_fqn(node, "/repo/src/pkg/models.py")
        assert fqn == "py://pkg.models.OuterClass.inner_method"

    def test_init_file_module_path(self, resolver):
        """Test: __init__.py는 패키지 이름으로 변환"""
        node = CodeNode(
            node_id="file_2",
            node_type="file",
            name="__init__",
            file_path="/repo/src/pkg/__init__.py",
            start_line=1,
            end_line=50,
            raw_code="",
        )

        fqn = resolver.resolve_fqn(node, "/repo/src/pkg/__init__.py")
        assert fqn == "py://pkg"


class TestPythonNameResolverImports:
    """Test import resolution"""

    @pytest.fixture
    def resolver(self):
        return PythonNameResolver(repo_root="/repo/src")

    def test_absolute_import_resolution(self, resolver):
        """Test: Absolute import는 그대로 FQN 변환"""
        fqn = resolver.resolve_import_target(
            import_name="os.path",
            file_path="/repo/src/pkg/module.py",
            import_kind="module",
        )
        assert fqn == "py://os.path"

    def test_relative_import_same_level(self, resolver):
        """Test: 같은 레벨 상대 import (.utils)"""
        fqn = resolver.resolve_import_target(
            import_name=".utils",
            file_path="/repo/src/pkg/module.py",
            import_kind="module",
        )
        # pkg.module에서 .utils -> pkg.utils
        assert fqn == "py://pkg.utils"

    def test_relative_import_parent_level(self, resolver):
        """Test: 상위 레벨 상대 import (..config)"""
        fqn = resolver.resolve_import_target(
            import_name="..config",
            file_path="/repo/src/pkg/subpkg/module.py",
            import_kind="module",
        )
        # pkg.subpkg.module에서 ..config -> pkg.config
        assert fqn == "py://pkg.config"

    def test_relative_import_too_many_levels(self, resolver):
        """Test: 잘못된 상대 import (너무 많은 상위 참조)"""
        fqn = resolver.resolve_import_target(
            import_name="....utils",
            file_path="/repo/src/pkg/module.py",
            import_kind="module",
        )
        # pkg.module에서 4단계 상위는 불가능
        assert fqn is None


class TestPythonNameResolverSyntheticID:
    """Test synthetic ID generation for unresolved symbols"""

    @pytest.fixture
    def resolver(self):
        return PythonNameResolver(repo_root="/repo/src")

    def test_synthetic_id_format(self, resolver):
        """Test: Synthetic ID 형식 검증"""
        synthetic_id = resolver.create_synthetic_id(
            identifier="unknown_func",
            file_path="/repo/src/pkg/module.py",
            repo_id="myrepo",
            namespace="main",
        )

        # Format: unresolved://repo_id/namespace/file_path/identifier_hash
        assert synthetic_id.startswith("unresolved://myrepo/main/")
        assert "unknown_func" in synthetic_id

    def test_synthetic_id_deterministic(self, resolver):
        """Test: 같은 입력은 같은 synthetic ID 생성"""
        id1 = resolver.create_synthetic_id(
            identifier="foo",
            file_path="/repo/src/pkg/module.py",
            repo_id="myrepo",
            namespace="main",
        )
        id2 = resolver.create_synthetic_id(
            identifier="foo",
            file_path="/repo/src/pkg/module.py",
            repo_id="myrepo",
            namespace="main",
        )

        assert id1 == id2

    def test_synthetic_id_collision_resistant(self, resolver):
        """Test: 다른 파일의 같은 이름은 다른 ID"""
        id1 = resolver.create_synthetic_id(
            identifier="helper",
            file_path="/repo/src/pkg/a.py",
            repo_id="myrepo",
            namespace="main",
        )
        id2 = resolver.create_synthetic_id(
            identifier="helper",
            file_path="/repo/src/pkg/b.py",
            repo_id="myrepo",
            namespace="main",
        )

        assert id1 != id2


class TestPythonNameResolverModulePath:
    """Test module path extraction logic"""

    def test_module_path_with_repo_root(self):
        """Test: repo_root 기준 상대 경로 변환"""
        resolver = PythonNameResolver(repo_root="/repo/src")

        module = resolver._extract_module_path("/repo/src/pkg/subpkg/module.py")
        assert module == "pkg.subpkg.module"

    def test_module_path_removes_src_prefix(self):
        """Test: src/ 접두사 자동 제거"""
        resolver = PythonNameResolver(repo_root="/repo")

        module = resolver._extract_module_path("/repo/src/pkg/module.py")
        assert module == "pkg.module"

    def test_module_path_without_repo_root(self):
        """Test: repo_root 미지정 시 파일명 사용"""
        resolver = PythonNameResolver()

        module = resolver._extract_module_path("/some/path/module.py")
        assert module == "module"

    def test_module_path_init_file(self):
        """Test: __init__.py는 패키지명으로"""
        resolver = PythonNameResolver(repo_root="/repo/src")

        module = resolver._extract_module_path("/repo/src/pkg/__init__.py")
        assert module == "pkg"


class TestPythonNameResolverErrors:
    """Test error handling"""

    @pytest.fixture
    def resolver(self):
        return PythonNameResolver(repo_root="/repo/src")

    def test_invalid_node_raises_error(self, resolver):
        """Test: 잘못된 노드 입력 시 NameResolutionError"""
        # parent_name이 없는 method는 해석 불가능하지 않음 (qualifiers 비어있을 뿐)
        # 실제 에러 케이스를 만들기 위해 None 값 전달
        with pytest.raises((NameResolutionError, AttributeError)):
            resolver.resolve_fqn(None, "/repo/src/pkg/module.py")  # type: ignore
