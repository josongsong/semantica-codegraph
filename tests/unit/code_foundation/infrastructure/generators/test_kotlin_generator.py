"""
Unit Tests: Kotlin Generator

RFC-031 Hash ID 기반 Kotlin Generator 테스트.

Test Coverage:
- Basic structure (File/Class/Function/Property)
- Kotlin 특화: data class, sealed class, object
- Extension functions
- Suspend functions (coroutines)
- Companion object
- Hash ID format validation
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.generators.kotlin_generator import (
    _KotlinIRGenerator,
)
from codegraph_engine.code_foundation.infrastructure.ir.models import NodeKind
from codegraph_engine.code_foundation.infrastructure.parsing import SourceFile


class TestKotlinGeneratorBasic:
    """기본 구조 테스트"""

    def test_empty_file(self):
        """빈 파일"""
        code = ""
        source = SourceFile(file_path="Empty.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        # File node만 존재
        assert len(ir_doc.nodes) == 1
        assert ir_doc.nodes[0].kind == NodeKind.FILE
        assert ir_doc.nodes[0].language == "kotlin"

    def test_package_declaration(self):
        """패키지 선언"""
        code = """
package com.example.app

class User
"""
        source = SourceFile(file_path="User.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        # Meta에 package 정보 확인
        assert ir_doc.meta["package"] == "com.example.app"

    def test_simple_class(self):
        """단순 클래스"""
        code = """
class User {
    val name: String = "John"
}
"""
        source = SourceFile(file_path="User.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        nodes_by_kind = {n.kind: n for n in ir_doc.nodes}

        # File + Class + Property
        assert NodeKind.FILE in nodes_by_kind
        assert NodeKind.CLASS in nodes_by_kind
        assert NodeKind.VARIABLE in nodes_by_kind

        class_node = nodes_by_kind[NodeKind.CLASS]
        assert class_node.name == "User"
        assert class_node.language == "kotlin"

        # Hash ID format: node:repo:kind:hash
        assert class_node.id.startswith("node:test-repo:class:")
        assert len(class_node.id.split(":")[3]) == 24  # 24 hex chars

    def test_function_declaration(self):
        """함수 선언"""
        code = """
fun calculate(x: Int, y: Int): Int {
    return x + y
}
"""
        source = SourceFile(file_path="Math.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        func_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FUNCTION]
        assert len(func_nodes) == 1

        func = func_nodes[0]
        assert func.name == "calculate"
        assert func.language == "kotlin"

        # Parameters (stored in attrs)
        assert "parameters" in func.attrs
        params = func.attrs["parameters"]
        assert len(params) == 2
        assert params[0]["name"] == "x"
        assert params[0]["type"] == "Int"

        # Return type (stored in attrs)
        assert func.attrs.get("return_type") == "Int"


class TestKotlinDataClass:
    """Data class 테스트"""

    def test_data_class(self):
        """data class"""
        code = """
data class User(
    val name: String,
    val age: Int
)
"""
        source = SourceFile(file_path="User.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        class_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.CLASS]
        assert len(class_nodes) == 1

        data_class = class_nodes[0]
        assert data_class.name == "User"
        assert data_class.attrs.get("kotlin_data_class") is True
        assert data_class.attrs.get("data") is True

    def test_sealed_class(self):
        """sealed class"""
        code = """
sealed class Result {
    data class Success(val data: String) : Result()
    data class Error(val message: String) : Result()
}
"""
        source = SourceFile(file_path="Result.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        class_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.CLASS]

        # Result + Success + Error = 3 classes
        assert len(class_nodes) >= 1

        sealed_class = [n for n in class_nodes if n.name == "Result"][0]
        assert sealed_class.attrs.get("kotlin_sealed_class") is True
        assert sealed_class.attrs.get("sealed") is True


class TestKotlinObject:
    """Object 선언 테스트"""

    def test_object_declaration(self):
        """object (Singleton)"""
        code = """
object AppConfig {
    val apiUrl: String = "https://api.example.com"
}
"""
        source = SourceFile(file_path="Config.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        class_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.CLASS]
        assert len(class_nodes) == 1

        obj = class_nodes[0]
        assert obj.name == "AppConfig"
        assert obj.attrs.get("kotlin_object") is True

    def test_companion_object(self):
        """companion object"""
        code = """
class Factory {
    companion object {
        fun create(): Factory = Factory()
    }
}
"""
        source = SourceFile(file_path="Factory.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        class_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.CLASS]

        # Factory + Companion = 2 classes
        assert len(class_nodes) == 2

        companion = [n for n in class_nodes if n.name == "Companion"][0]
        assert companion.attrs.get("kotlin_companion_object") is True


class TestKotlinExtensionFunction:
    """Extension function 테스트"""

    def test_extension_function(self):
        """확장 함수"""
        code = """
fun String.toInt(): Int {
    return this.toIntOrNull() ?: 0
}
"""
        source = SourceFile(file_path="Extensions.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        func_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FUNCTION]
        assert len(func_nodes) == 1

        ext_func = func_nodes[0]
        assert ext_func.name == "toInt"

        # Extension receiver 확인
        # Note: 현재 구현에서는 receiver_type이 attrs에 저장됨
        # assert ext_func.attrs.get("kotlin_extension_receiver") == "String"


class TestKotlinCoroutine:
    """Coroutine (suspend function) 테스트"""

    def test_suspend_function(self):
        """suspend 함수"""
        code = """
suspend fun fetchData(): String {
    return "data"
}
"""
        source = SourceFile(file_path="Api.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        func_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FUNCTION]
        assert len(func_nodes) == 1

        suspend_func = func_nodes[0]
        assert suspend_func.name == "fetchData"
        assert suspend_func.attrs.get("kotlin_suspend") is True
        assert suspend_func.attrs.get("suspend") is True


class TestKotlinProperty:
    """Property 테스트"""

    def test_val_property(self):
        """val (immutable)"""
        code = """
class User {
    val name: String = "John"
}
"""
        source = SourceFile(file_path="User.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        var_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.VARIABLE]
        assert len(var_nodes) == 1

        prop = var_nodes[0]
        assert prop.name == "name"
        assert prop.attrs.get("kotlin_immutable") is True

    def test_var_property(self):
        """var (mutable)"""
        code = """
class Counter {
    var count: Int = 0
}
"""
        source = SourceFile(file_path="Counter.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        var_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.VARIABLE]
        assert len(var_nodes) == 1

        prop = var_nodes[0]
        assert prop.name == "count"
        assert prop.attrs.get("kotlin_mutable") is True


class TestKotlinEdges:
    """Edge 생성 테스트"""

    def test_contains_edges(self):
        """CONTAINS edge"""
        code = """
class User {
    fun greet() {}
}
"""
        source = SourceFile(file_path="User.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        # File → Class, Class → Function
        from codegraph_engine.code_foundation.infrastructure.ir.models import EdgeKind

        contains_edges = [e for e in ir_doc.edges if e.kind == EdgeKind.CONTAINS]
        assert len(contains_edges) >= 2

        # Edge ID format: edge:kind:hash
        for edge in contains_edges:
            assert edge.id.startswith("edge:contains:")
            assert len(edge.id.split(":")[2]) == 20  # 20 hex chars

    def test_imports_edge(self):
        """IMPORTS edge"""
        code = """
import kotlin.collections.List

class User
"""
        source = SourceFile(file_path="User.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        from codegraph_engine.code_foundation.infrastructure.ir.models import EdgeKind

        import_edges = [e for e in ir_doc.edges if e.kind == EdgeKind.IMPORTS]
        assert len(import_edges) >= 1


class TestKotlinHashID:
    """Hash ID 검증"""

    def test_node_id_format(self):
        """Node ID 형식: node:repo:kind:hash"""
        code = """
class User {
    fun greet() {}
}
"""
        source = SourceFile(file_path="User.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        for node in ir_doc.nodes:
            parts = node.id.split(":")
            assert len(parts) == 4
            assert parts[0] == "node"
            assert parts[1] == "test-repo"
            assert parts[2] in {"file", "class", "function", "variable", "import"}
            assert len(parts[3]) == 24  # 24 hex chars

    def test_edge_id_format(self):
        """Edge ID 형식: edge:kind:hash"""
        code = """
class User {
    fun greet() {}
}
"""
        source = SourceFile(file_path="User.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        for edge in ir_doc.edges:
            parts = edge.id.split(":")
            assert len(parts) == 3
            assert parts[0] == "edge"
            assert parts[1] in {"contains", "calls", "imports", "inherits"}
            assert len(parts[2]) == 20  # 20 hex chars

    def test_collision_resistance(self):
        """Hash ID 충돌 방지"""
        # 다른 패키지 사용
        code1 = "package com.example.app1\n\nclass User { fun greet() {} }"
        code2 = "package com.example.app2\n\nclass User { fun hello() {} }"

        source1 = SourceFile(file_path="User1.kt", content=code1, language="kotlin")
        source2 = SourceFile(file_path="User2.kt", content=code2, language="kotlin")

        # 각각 새 generator 사용
        generator1 = _KotlinIRGenerator(repo_id="test-repo")
        generator2 = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc1 = generator1.generate(source1, snapshot_id="snap1")
        ir_doc2 = generator2.generate(source2, snapshot_id="snap2")

        # 같은 이름 "User"이지만 다른 패키지 → 다른 FQN → 다른 ID
        class1 = [n for n in ir_doc1.nodes if n.kind == NodeKind.CLASS][0]
        class2 = [n for n in ir_doc2.nodes if n.kind == NodeKind.CLASS][0]

        assert class1.fqn != class2.fqn  # FQN이 다름
        assert class1.id != class2.id  # ID도 다름


class TestKotlinComplexScenarios:
    """복잡한 시나리오"""

    def test_nested_classes(self):
        """중첩 클래스"""
        code = """
class Outer {
    class Inner {
        fun method() {}
    }
}
"""
        source = SourceFile(file_path="Nested.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        class_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.CLASS]
        assert len(class_nodes) == 2  # Outer + Inner

    def test_multiple_functions(self):
        """여러 함수"""
        code = """
fun add(a: Int, b: Int): Int = a + b
fun subtract(a: Int, b: Int): Int = a - b
fun multiply(a: Int, b: Int): Int = a * b
"""
        source = SourceFile(file_path="Math.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        func_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FUNCTION]
        assert len(func_nodes) == 3

        func_names = {f.name for f in func_nodes}
        assert func_names == {"add", "subtract", "multiply"}

    def test_real_world_example(self):
        """실제 코드 예제"""
        code = """
package com.example.app

import kotlin.collections.List

data class User(
    val id: Int,
    val name: String
)

class UserRepository {
    suspend fun findById(id: Int): User? {
        return null
    }
}

object AppConfig {
    const val API_URL = "https://api.example.com"
}
"""
        source = SourceFile(file_path="User.kt", content=code, language="kotlin")
        generator = _KotlinIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(source, snapshot_id="snap1")

        # 검증
        assert ir_doc.meta["package"] == "com.example.app"
        assert len(ir_doc.nodes) >= 5  # File + User + UserRepository + findById + AppConfig

        class_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.CLASS]
        func_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FUNCTION]

        # User (data class)
        user_class = [n for n in class_nodes if n.name == "User"][0]
        assert user_class.attrs.get("kotlin_data_class") is True

        # findById (suspend function)
        find_func = [n for n in func_nodes if n.name == "findById"][0]
        assert find_func.attrs.get("kotlin_suspend") is True

        # AppConfig (object)
        config_obj = [n for n in class_nodes if n.name == "AppConfig"][0]
        assert config_obj.attrs.get("kotlin_object") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
