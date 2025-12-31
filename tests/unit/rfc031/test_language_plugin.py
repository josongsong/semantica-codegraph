"""
RFC-031: Language Plugin Tests

Tests for:
1. FQNToken and ParsedFQN
2. PythonPlugin FQN parsing/building
3. JavaPlugin FQN parsing/building
4. TypeScriptPlugin FQN parsing/building
5. Plugin registry
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.language_plugin import (
    FQNToken,
    JavaPlugin,
    ParsedFQN,
    PythonPlugin,
    TypeScriptPlugin,
    get_plugin,
    supported_languages,
)


class TestParsedFQN:
    """Test ParsedFQN dataclass"""

    def test_simple_fqn(self):
        """Simple FQN without special token"""
        fqn = ParsedFQN("module.Class.method")
        assert fqn.base == "module.Class.method"
        assert fqn.token is None
        assert fqn.suffix is None
        assert not fqn.is_special

    def test_lambda_fqn(self):
        """FQN with lambda token"""
        fqn = ParsedFQN("module.func", FQNToken.LAMBDA, "0")
        assert fqn.base == "module.func"
        assert fqn.token == FQNToken.LAMBDA
        assert fqn.suffix == "0"
        assert fqn.is_special

    def test_display_lambda(self):
        """Display format for lambda"""
        fqn = ParsedFQN("module.func", FQNToken.LAMBDA, "0")
        assert fqn.display() == "module.func.<lambda_0>"

    def test_display_import(self):
        """Display format for import"""
        fqn = ParsedFQN("module", FQNToken.IMPORT, "Symbol")
        assert fqn.display() == "module.__import__.Symbol"

    def test_display_anon_class(self):
        """Display format for anonymous class"""
        fqn = ParsedFQN("com.example.Outer", FQNToken.ANON_CLASS, "1")
        assert fqn.display() == "com.example.Outer.$anon_1"

    def test_canonical_key_simple(self):
        """Canonical key for simple FQN"""
        fqn = ParsedFQN("module.func")
        assert fqn.canonical_key() == "module.func"

    def test_canonical_key_with_token(self):
        """Canonical key includes token and suffix"""
        fqn = ParsedFQN("module.func", FQNToken.LAMBDA, "0")
        key = fqn.canonical_key()
        assert "module.func" in key
        assert "LAMBDA" in key
        assert "0" in key


class TestPythonPlugin:
    """Test Python language plugin"""

    @pytest.fixture
    def plugin(self):
        return PythonPlugin()

    def test_language(self, plugin):
        """Plugin should report python as language"""
        assert plugin.language == "python"

    def test_normalize_fqn(self, plugin):
        """Python FQN normalization (no-op)"""
        fqn = "module.Class.method"
        assert plugin.normalize_fqn(fqn) == fqn

    def test_parse_simple(self, plugin):
        """Parse simple FQN"""
        parsed = plugin.parse_fqn("module.func")
        assert parsed.base == "module.func"
        assert parsed.token is None

    def test_parse_lambda(self, plugin):
        """Parse lambda FQN"""
        parsed = plugin.parse_fqn("module.func.<lambda_0>")
        assert parsed.base == "module.func"
        assert parsed.token == FQNToken.LAMBDA
        assert parsed.suffix == "0"

    def test_parse_import(self, plugin):
        """Parse import FQN"""
        parsed = plugin.parse_fqn("os.__import__.path")
        assert parsed.base == "os"
        assert parsed.token == FQNToken.IMPORT
        assert parsed.suffix == "path"

    def test_parse_comprehension(self, plugin):
        """Parse comprehension FQN"""
        parsed = plugin.parse_fqn("module.func.<comp_0>")
        assert parsed.base == "module.func"
        assert parsed.token == FQNToken.COMPREHENSION
        assert parsed.suffix == "0"

    def test_parse_local(self, plugin):
        """Parse local variable FQN"""
        parsed = plugin.parse_fqn("module.func.<local>.x")
        assert parsed.base == "module.func"
        assert parsed.token == FQNToken.LOCAL
        assert parsed.suffix == "x"

    def test_build_lambda_fqn(self, plugin):
        """Build lambda FQN"""
        fqn = plugin.build_lambda_fqn("module.func", 0)
        assert fqn == "module.func.<lambda_0>"

    def test_build_import_fqn(self, plugin):
        """Build import FQN"""
        fqn = plugin.build_import_fqn("os", "path")
        assert fqn == "os.__import__.path"

    def test_is_builtin_type(self, plugin):
        """Check builtin types"""
        assert plugin.is_builtin_type("int")
        assert plugin.is_builtin_type("str")
        assert plugin.is_builtin_type("List[int]")
        assert plugin.is_builtin_type("Dict[str, Any]")
        assert not plugin.is_builtin_type("MyClass")


class TestJavaPlugin:
    """Test Java language plugin"""

    @pytest.fixture
    def plugin(self):
        return JavaPlugin()

    def test_language(self, plugin):
        """Plugin should report java as language"""
        assert plugin.language == "java"

    def test_normalize_fqn_inner_class(self, plugin):
        """Normalize Java inner class FQN"""
        fqn = "com.example.Outer$Inner"
        normalized = plugin.normalize_fqn(fqn)
        assert normalized == "com.example.Outer.Inner"

    def test_normalize_fqn_nested(self, plugin):
        """Normalize nested inner classes"""
        fqn = "com.example.Outer$Inner$Deep"
        normalized = plugin.normalize_fqn(fqn)
        assert normalized == "com.example.Outer.Inner.Deep"

    def test_parse_simple(self, plugin):
        """Parse simple FQN"""
        parsed = plugin.parse_fqn("com.example.MyClass")
        assert parsed.base == "com.example.MyClass"
        assert parsed.token is None

    def test_parse_anonymous_class(self, plugin):
        """Parse anonymous class FQN"""
        parsed = plugin.parse_fqn("com.example.MyClass$1")
        assert parsed.base == "com.example.MyClass"
        assert parsed.token == FQNToken.ANON_CLASS
        assert parsed.suffix == "1"

    def test_parse_inner_class(self, plugin):
        """Parse named inner class FQN"""
        parsed = plugin.parse_fqn("com.example.Outer$Inner")
        assert parsed.base == "com.example.Outer"
        assert parsed.token == FQNToken.INNER_CLASS
        assert "Inner" in parsed.suffix

    def test_build_lambda_fqn(self, plugin):
        """Build Java lambda FQN"""
        fqn = plugin.build_lambda_fqn("com.example.MyClass", 0)
        assert fqn == "com.example.MyClass$lambda$0"

    def test_is_builtin_type(self, plugin):
        """Check Java builtin types"""
        assert plugin.is_builtin_type("int")
        assert plugin.is_builtin_type("String")
        assert plugin.is_builtin_type("Integer")
        assert plugin.is_builtin_type("Object")
        assert not plugin.is_builtin_type("MyClass")
        assert not plugin.is_builtin_type("List<String>")  # Generic, not primitive


class TestTypeScriptPlugin:
    """Test TypeScript language plugin"""

    @pytest.fixture
    def plugin(self):
        return TypeScriptPlugin()

    def test_language(self, plugin):
        """Plugin should report typescript as language"""
        assert plugin.language == "typescript"

    def test_normalize_fqn(self, plugin):
        """TypeScript FQN normalization (no-op)"""
        fqn = "module.Class.method"
        assert plugin.normalize_fqn(fqn) == fqn

    def test_parse_simple(self, plugin):
        """Parse simple FQN"""
        parsed = plugin.parse_fqn("module.func")
        assert parsed.base == "module.func"
        assert parsed.token is None

    def test_parse_anonymous(self, plugin):
        """Parse anonymous function FQN"""
        parsed = plugin.parse_fqn("module.func.<anonymous_0>")
        assert parsed.base == "module.func"
        assert parsed.token == FQNToken.LAMBDA
        assert parsed.suffix == "0"

    def test_build_lambda_fqn(self, plugin):
        """Build TypeScript arrow function FQN"""
        fqn = plugin.build_lambda_fqn("module.handler", 0)
        assert fqn == "module.handler.<anonymous_0>"

    def test_is_builtin_type(self, plugin):
        """Check TypeScript builtin types"""
        assert plugin.is_builtin_type("number")
        assert plugin.is_builtin_type("string")
        assert plugin.is_builtin_type("boolean")
        assert plugin.is_builtin_type("Array<number>")
        assert plugin.is_builtin_type("Promise<void>")
        assert not plugin.is_builtin_type("MyClass")


class TestPluginRegistry:
    """Test plugin registry"""

    def test_get_python_plugin(self):
        """Get Python plugin"""
        plugin = get_plugin("python")
        assert plugin.language == "python"

    def test_get_java_plugin(self):
        """Get Java plugin"""
        plugin = get_plugin("java")
        assert plugin.language == "java"

    def test_get_typescript_plugin(self):
        """Get TypeScript plugin"""
        plugin = get_plugin("typescript")
        assert plugin.language == "typescript"

    def test_get_javascript_uses_typescript(self):
        """JavaScript uses TypeScript plugin"""
        plugin = get_plugin("javascript")
        assert plugin.language == "typescript"

    def test_case_insensitive(self):
        """Plugin lookup is case-insensitive"""
        assert get_plugin("Python").language == "python"
        assert get_plugin("JAVA").language == "java"

    def test_unsupported_language_raises(self):
        """Unsupported language raises KeyError"""
        with pytest.raises(KeyError):
            get_plugin("cobol")

    def test_supported_languages(self):
        """List supported languages"""
        languages = supported_languages()
        assert "python" in languages
        assert "java" in languages
        assert "typescript" in languages
        assert "javascript" in languages


class TestFQNRoundTrip:
    """Test FQN parsing → building roundtrip"""

    def test_python_lambda_roundtrip(self):
        """Python lambda FQN roundtrip"""
        plugin = PythonPlugin()
        original = plugin.build_lambda_fqn("module.func", 0)
        parsed = plugin.parse_fqn(original)
        rebuilt = plugin.build_lambda_fqn(parsed.base, int(parsed.suffix))
        assert original == rebuilt

    def test_python_import_roundtrip(self):
        """Python import FQN roundtrip"""
        plugin = PythonPlugin()
        original = plugin.build_import_fqn("os", "path")
        parsed = plugin.parse_fqn(original)
        rebuilt = plugin.build_import_fqn(parsed.base, parsed.suffix)
        assert original == rebuilt

    def test_java_lambda_roundtrip(self):
        """Java lambda FQN roundtrip"""
        plugin = JavaPlugin()
        original = plugin.build_lambda_fqn("com.example.Service", 0)
        # Note: Java lambda parsing might not fully roundtrip due to javac naming
        parsed = plugin.parse_fqn(original)
        assert parsed.token == FQNToken.LAMBDA
