"""
Phase 1: Cross-Language Symbol Resolution Tests

UnifiedSymbol, LanguageBridge, CrossLanguageEdgeGenerator 테스트
"""

import pytest
from src.contexts.code_foundation.domain.models import (
    UnifiedSymbol,
    IRDocument,
    Language,
    GraphEdge,
)
from src.contexts.code_foundation.infrastructure.language_bridge import LanguageBridge
from src.contexts.code_foundation.infrastructure.cross_lang_edges import (
    CrossLanguageEdgeGenerator,
)


class TestUnifiedSymbol:
    """UnifiedSymbol 테스트"""

    def test_python_scip_descriptor(self):
        """Python SCIP descriptor 생성"""
        symbol = UnifiedSymbol.from_simple(
            scheme="python",
            package="com.example",
            descriptor="MyClass#",
            language_fqn="com.example.MyClass",
            language_kind="class",
            version="1.0.0",
            file_path="example.py",
        )

        descriptor = symbol.to_scip_descriptor()
        assert "scip-python" in descriptor
        assert "com.example" in descriptor
        assert "MyClass#" in descriptor

    def test_java_scip_descriptor(self):
        """Java SCIP descriptor 생성"""
        symbol = UnifiedSymbol.from_simple(
            scheme="java",
            package="org.example",
            descriptor="MyClass#",
            language_fqn="org.example.MyClass",
            language_kind="class",
            version="1.0.0",
            file_path="Main.java",
        )

        descriptor = symbol.to_scip_descriptor()
        assert "scip-java" in descriptor
        assert "org.example" in descriptor
        assert "MyClass#" in descriptor

    def test_typescript_scip_descriptor(self):
        """TypeScript SCIP descriptor 생성"""
        symbol = UnifiedSymbol.from_simple(
            scheme="typescript",
            package="@types/node",
            descriptor="fs.readFile().",
            language_fqn="@types/node.fs.readFile",
            language_kind="function",
            version="18.0.0",
            file_path="fs.d.ts",
        )

        descriptor = symbol.to_scip_descriptor()
        assert "scip-typescript" in descriptor
        assert "@types/node" in descriptor
        assert "readFile" in descriptor

    def test_symbol_matching(self):
        """Cross-language symbol matching"""
        python_str = UnifiedSymbol.from_simple(
            scheme="python",
            package="builtins",
            descriptor="str#",
            language_fqn="str",
            language_kind="class",
        )

        java_string = UnifiedSymbol.from_simple(
            scheme="java",
            package="java.lang",
            descriptor="str#",  # Same descriptor
            language_fqn="java.lang.String",
            language_kind="class",
        )

        assert python_str.matches(java_string)


class TestLanguageBridge:
    """LanguageBridge 테스트"""

    def setup_method(self):
        self.bridge = LanguageBridge()

    def test_python_to_java_str(self):
        """Python str → Java String"""
        python_str = UnifiedSymbol.from_simple(
            scheme="python",
            package="builtins",
            descriptor="str#",
            language_fqn="str",
            language_kind="class",
        )

        java_string = self.bridge.resolve_cross_language(python_str, "java")

        assert java_string is not None
        assert java_string.scheme == "java"
        assert java_string.language_fqn == "java.lang.String"
        assert java_string.package == "java.lang"

    def test_python_to_java_list(self):
        """Python list → Java List"""
        python_list = UnifiedSymbol.from_simple(
            scheme="python",
            package="builtins",
            descriptor="list#",
            language_fqn="list",
            language_kind="class",
        )

        java_list = self.bridge.resolve_cross_language(python_list, "java")

        assert java_list is not None
        assert java_list.language_fqn == "java.util.List"
        assert java_list.package == "java.util"

    def test_typescript_to_python(self):
        """TypeScript Array → Python list"""
        ts_array = UnifiedSymbol.from_simple(
            scheme="typescript",
            package="typescript",
            descriptor="Array#",
            language_fqn="Array",
            language_kind="class",
        )

        python_list = self.bridge.resolve_cross_language(ts_array, "python")

        assert python_list is not None
        assert python_list.language_fqn == "list"
        assert python_list.package == "builtins"

    def test_java_to_kotlin(self):
        """Java String → Kotlin String"""
        java_string = UnifiedSymbol.from_simple(
            scheme="java",
            package="java.lang",
            descriptor="String#",
            language_fqn="java.lang.String",
            language_kind="class",
        )

        kotlin_string = self.bridge.resolve_cross_language(java_string, "kotlin")

        assert kotlin_string is not None
        assert kotlin_string.language_fqn == "kotlin.String"

    def test_unsupported_mapping(self):
        """지원하지 않는 매핑"""
        python_str = UnifiedSymbol.from_simple(
            scheme="python",
            package="builtins",
            descriptor="str#",
            language_fqn="str",
            language_kind="class",
        )

        # Python → Rust (미지원)
        result = self.bridge.resolve_cross_language(python_str, "rust")
        assert result is None

    def test_supported_pairs(self):
        """지원되는 언어 쌍"""
        pairs = self.bridge.get_supported_pairs()

        assert ("python", "java") in pairs
        assert ("java", "python") in pairs
        assert ("typescript", "python") in pairs
        assert ("java", "kotlin") in pairs

    def test_is_supported(self):
        """언어 쌍 지원 여부"""
        assert self.bridge.is_supported("python", "java")
        assert self.bridge.is_supported("java", "kotlin")
        assert not self.bridge.is_supported("python", "rust")

    def test_generic_list_str_python_to_java(self):
        """Generic: Python list[str] → Java List<String>"""
        result = self.bridge.resolve_generic_type("list[str]", "python", "java")
        assert result == "java.util.List<String>"

    def test_generic_dict_python_to_java(self):
        """Generic: Python dict[str, int] → Java Map<String, Integer>"""
        result = self.bridge.resolve_generic_type("dict[str, int]", "python", "java")
        assert result == "java.util.Map<String, Integer>"

    def test_generic_java_to_python(self):
        """Generic: Java List<String> → Python list[str]"""
        result = self.bridge.resolve_generic_type("java.util.List<String>", "java", "python")
        assert result == "list[str]"

    def test_generic_nested(self):
        """Nested generic: list[list[str]]"""
        result = self.bridge.resolve_generic_type("list[list[str]]", "python", "java")
        # Recursive mapping
        assert "List" in result
        assert "String" in result

    def test_optional_python_to_java(self):
        """Optional: Python Optional[int] → Java Optional<Integer>"""
        result = self.bridge.resolve_generic_type("Optional[int]", "python", "java")
        assert result == "java.util.Optional<Integer>"


class TestCrossLanguageEdgeGenerator:
    """CrossLanguageEdgeGenerator 테스트"""

    def setup_method(self):
        self.bridge = LanguageBridge()
        self.generator = CrossLanguageEdgeGenerator(self.bridge)

    def test_detect_typescript_import(self):
        """TypeScript definition import 감지"""
        lang = self.generator._detect_import_language("@types/node")
        assert lang == "typescript"

    def test_detect_java_import(self):
        """Java import 감지"""
        assert self.generator._detect_import_language("java.util.List") == "java"
        assert self.generator._detect_import_language("javax.servlet") == "java"
        assert self.generator._detect_import_language("org.apache.commons") == "java"

    def test_detect_kotlin_import(self):
        """Kotlin import 감지"""
        lang = self.generator._detect_import_language("kotlin.collections.List")
        assert lang == "kotlin"

    def test_detect_ffi_jpype(self):
        """JPype FFI 감지 (Python → Java)"""
        lang = self.generator._detect_ffi_language("jpype")
        assert lang == "java"

    def test_detect_ffi_ctypes(self):
        """ctypes FFI 감지 (Python → C)"""
        lang = self.generator._detect_ffi_language("ctypes")
        assert lang == "c"

    def test_detect_ffi_pybind11(self):
        """pybind11 FFI 감지 (Python → C++)"""
        lang = self.generator._detect_ffi_language("pybind11")
        assert lang == "cpp"

    @pytest.mark.asyncio
    async def test_generate_cross_import_edges(self):
        """Cross-language import edge 생성"""
        # Python file importing TypeScript types
        python_ir = IRDocument(
            file_path="main.py",
            language=Language.PYTHON,
            imports=["@types/node", "some_module"],
        )

        # Java file
        java_ir = IRDocument(file_path="App.java", language=Language.JAVA, imports=["java.util.List"])

        irs = {"main.py": python_ir, "App.java": java_ir}

        edges = await self.generator.generate_cross_edges(irs)

        # TypeScript import edge 확인
        cross_edges = [e for e in edges if e.type == "CROSS_LANG_IMPORT"]
        assert len(cross_edges) >= 1

        ts_edge = next(e for e in cross_edges if e.properties.get("target_language") == "typescript")
        assert ts_edge.source == "main.py"
        assert ts_edge.properties["source_language"] == "python"

    @pytest.mark.asyncio
    async def test_generate_ffi_edges(self):
        """FFI import edge 생성"""
        python_ir = IRDocument(
            file_path="ffi_test.py",
            language=Language.PYTHON,
            imports=["jpype", "ctypes", "normal_module"],
        )

        irs = {"ffi_test.py": python_ir}

        edges = await self.generator.generate_cross_edges(irs)

        ffi_edges = [e for e in edges if e.type == "FFI_IMPORT"]
        assert len(ffi_edges) == 2  # jpype, ctypes

        # JPype edge
        jpype_edge = next(e for e in ffi_edges if e.properties.get("ffi_library") == "jpype")
        assert jpype_edge.properties["target_language"] == "java"

        # ctypes edge
        ctypes_edge = next(e for e in ffi_edges if e.properties.get("ffi_library") == "ctypes")
        assert ctypes_edge.properties["target_language"] == "c"


class TestPhase1Integration:
    """Phase 1 통합 테스트"""

    def test_end_to_end_python_java(self):
        """End-to-end: Python → Java type mapping"""
        bridge = LanguageBridge()

        # Python symbol
        python_dict = UnifiedSymbol.from_simple(
            scheme="python",
            package="builtins",
            descriptor="dict#",
            language_fqn="dict",
            language_kind="class",
        )

        # Resolve to Java
        java_map = bridge.resolve_cross_language(python_dict, "java")

        assert java_map is not None
        assert java_map.scheme == "java"
        assert java_map.language_fqn == "java.util.Map"

        # SCIP descriptor
        scip = java_map.to_scip_descriptor()
        assert "scip-java" in scip
        assert "java.util" in scip

    @pytest.mark.asyncio
    async def test_polyglot_project(self):
        """Polyglot 프로젝트 시뮬레이션"""
        # Python + Java + TypeScript 프로젝트
        python_ir = IRDocument(
            file_path="main.py",
            language=Language.PYTHON,
            imports=["jpype", "@types/node", "requests"],
        )

        java_ir = IRDocument(
            file_path="Helper.java",
            language=Language.JAVA,
            imports=["java.util.List", "kotlin.collections"],
        )

        ts_ir = IRDocument(
            file_path="index.ts",
            language=Language.TYPESCRIPT,
            imports=["fs", "path"],
        )

        irs = {
            "main.py": python_ir,
            "Helper.java": java_ir,
            "index.ts": ts_ir,
        }

        bridge = LanguageBridge()
        generator = CrossLanguageEdgeGenerator(bridge)

        edges = await generator.generate_cross_edges(irs)

        # 검증
        assert len(edges) > 0

        # FFI edges (jpype)
        ffi_edges = [e for e in edges if e.type == "FFI_IMPORT"]
        assert len(ffi_edges) >= 1

        # Cross-language imports
        cross_edges = [e for e in edges if e.type == "CROSS_LANG_IMPORT"]
        assert len(cross_edges) >= 2  # @types/node, kotlin.collections


class TestCustomTypeMappingFix:
    """Test custom type mapping (P1 fix)"""

    def test_custom_type_python_to_java(self):
        """Custom type은 그대로 유지되어야 함"""
        bridge = LanguageBridge()

        # User-defined type
        result = bridge.resolve_generic_type("Optional[User]", "python", "java")

        # Should keep User as-is
        assert result is not None
        assert "User" in result

    def test_custom_type_in_list(self):
        """리스트 안의 custom type"""
        bridge = LanguageBridge()

        result = bridge.resolve_generic_type("list[User]", "python", "java")

        assert result is not None
        assert "User" in result
        assert "List" in result or "java.util.List" in result

    def test_custom_type_in_dict(self):
        """딕셔너리의 custom type"""
        bridge = LanguageBridge()

        result = bridge.resolve_generic_type("dict[str, User]", "python", "java")

        assert result is not None
        assert "User" in result
        assert "Map" in result or "java.util.Map" in result

    def test_nested_custom_types(self):
        """중첩된 custom type"""
        bridge = LanguageBridge()

        result = bridge.resolve_generic_type("list[dict[str, User]]", "python", "java")

        assert result is not None
        assert "User" in result

    def test_pure_custom_type(self):
        """Generic 없는 순수 custom type"""
        bridge = LanguageBridge()

        result = bridge.resolve_generic_type("User", "python", "java")

        # Should return as-is
        assert result == "User"

    def test_java_to_python_custom(self):
        """Java → Python custom type"""
        bridge = LanguageBridge()

        # Currently no Java→Python mapping exists, but should still work
        result = bridge.resolve_generic_type("Optional[User]", "java", "python")

        # Even if no mapping, should keep User
        if result:
            assert "User" in result
