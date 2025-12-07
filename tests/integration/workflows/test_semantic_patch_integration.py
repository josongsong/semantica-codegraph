"""
Integration Tests: Semantic Patch Engine

Test scenarios:
1. Regex pattern matching
2. Structural pattern matching (Comby-style)
3. AST pattern matching
4. Patch application
5. Idempotency verification
"""

import tempfile
from pathlib import Path

import pytest

from src.contexts.reasoning_engine.infrastructure.patch import (
    ASTMatcher,
    MatchResult,
    PatchTemplate,
    PatternSyntax,
    RegexMatcher,
    SemanticPatchEngine,
    StructuralMatcher,
    TransformKind,
)


class TestRegexMatcher:
    """Regex pattern matching tests"""

    def test_simple_match(self):
        """Test simple regex match"""
        matcher = RegexMatcher()

        pattern = r"def\s+(\w+)\("
        source = """
def hello():
    pass

def world():
    pass
"""

        matches = matcher.match(pattern, source, "test.py")

        assert len(matches) == 2
        assert matches[0].file_path == "test.py"

    def test_named_groups(self):
        """Test named capture groups"""
        matcher = RegexMatcher()

        pattern = r"def\s+(?P<func_name>\w+)\("
        source = "def hello():\n    pass"

        matches = matcher.match(pattern, source, "test.py")

        assert len(matches) == 1
        assert "func_name" in matches[0].captures
        assert matches[0].captures["func_name"].value == "hello"


class TestStructuralMatcher:
    """Structural pattern matching tests"""

    def test_capture_variable(self):
        """Test :[var] capture"""
        matcher = StructuralMatcher()

        pattern = "def :[func_name](:[params]):"
        source = "def hello(x, y):\n    pass"

        matches = matcher.match(pattern, source, "test.py")

        assert len(matches) > 0
        assert "func_name" in matches[0].captures
        assert "params" in matches[0].captures

    def test_expression_capture(self):
        """Test :[var:e] expression capture"""
        matcher = StructuralMatcher()

        pattern = "result = :[expr:e]"
        source = "result = x + y * 2"

        matches = matcher.match(pattern, source, "test.py")

        assert len(matches) > 0
        assert "expr" in matches[0].captures
        assert "x + y * 2" in matches[0].captures["expr"].value


class TestASTMatcher:
    """AST pattern matching tests"""

    def test_python_function_match(self):
        """Test Python function AST match"""
        matcher = ASTMatcher("python")

        pattern = "FunctionDef:name=oldFunc"
        source = """
def oldFunc():
    return 42

def newFunc():
    return 100
"""

        matches = matcher.match(pattern, source, "test.py")

        assert len(matches) == 1
        assert "name" in matches[0].captures
        assert matches[0].captures["name"].value == "oldFunc"


class TestPatchTemplates:
    """Patch template tests"""

    def test_create_template(self):
        """Test template creation"""
        template = PatchTemplate(
            name="rename_api",
            description="Rename old API to new API",
            pattern="oldAPI(:[args])",
            replacement="newAPI(:[args])",
            syntax=PatternSyntax.STRUCTURAL,
        )

        assert template.name == "rename_api"
        assert template.pattern == "oldAPI(:[args])"

    def test_template_with_constraints(self):
        """Test template with language constraint"""
        template = PatchTemplate(
            name="python_only",
            description="Python-specific patch",
            pattern="print :[msg]",  # Python 2 style
            replacement="print(:[msg])",  # Python 3 style
            syntax=PatternSyntax.STRUCTURAL,
            language="python",
        )

        assert template.language == "python"


class TestSemanticPatchEngine:
    """Semantic patch engine tests"""

    def test_engine_init(self):
        """Test engine initialization"""
        engine = SemanticPatchEngine()

        assert engine is not None
        assert PatternSyntax.REGEX in engine.matchers
        assert PatternSyntax.STRUCTURAL in engine.matchers

    def test_dry_run_patch(self):
        """Test patch dry run"""
        engine = SemanticPatchEngine()

        # Create test file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("oldAPI(42)\noldAPI(100)\n")
            test_file = f.name

        try:
            # Create template
            template = PatchTemplate(
                name="rename_api",
                pattern="oldAPI(:[args])",
                replacement="newAPI(:[args])",
                syntax=PatternSyntax.STRUCTURAL,
            )

            # Apply (dry run)
            results = engine.apply_patch(
                template=template,
                files=[test_file],
                dry_run=True,
            )

            assert results["total_matches"] == 2
            assert len(results["files_affected"]) == 1
            assert len(results["errors"]) == 0

            # File should not be modified
            content = Path(test_file).read_text()
            assert "oldAPI" in content
            assert "newAPI" not in content

        finally:
            Path(test_file).unlink()

    def test_actual_patch_application(self):
        """Test actual patch application"""
        engine = SemanticPatchEngine()

        # Create test file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def test():\n    oldAPI(42)\n    return True\n")
            test_file = f.name

        try:
            # Create template
            template = PatchTemplate(
                name="rename_api",
                pattern=r"oldAPI\((\d+)\)",
                replacement=r"newAPI(\1)",
                syntax=PatternSyntax.REGEX,
            )

            # Apply (actual)
            results = engine.apply_patch(
                template=template,
                files=[test_file],
                dry_run=False,
                verify=True,
            )

            assert results["total_matches"] == 1

            # File should be modified
            content = Path(test_file).read_text()
            assert "oldAPI" not in content
            assert "newAPI(42)" in content

        finally:
            Path(test_file).unlink()


class TestIdempotency:
    """Idempotency tests"""

    def test_idempotent_patch(self):
        """Test that patch is idempotent"""
        engine = SemanticPatchEngine()

        # Create test file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("oldAPI(42)\n")
            test_file = f.name

        try:
            template = PatchTemplate(
                name="rename",
                pattern="oldAPI(:[args])",
                replacement="newAPI(:[args])",
                syntax=PatternSyntax.STRUCTURAL,
                idempotent=True,
            )

            # Apply first time
            results1 = engine.apply_patch(
                template=template,
                files=[test_file],
                dry_run=False,
            )

            assert results1["total_matches"] == 1

            # Apply second time (should have no matches)
            results2 = engine.apply_patch(
                template=template,
                files=[test_file],
                dry_run=False,
            )

            assert results2["total_matches"] == 0

        finally:
            Path(test_file).unlink()


class TestSafetyVerification:
    """Safety verification tests"""

    def test_syntax_check_python(self):
        """Test Python syntax verification"""
        engine = SemanticPatchEngine()

        # Create test file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def test():\n    x = 1\n    return x\n")
            test_file = f.name

        try:
            # Template that breaks syntax
            template = PatchTemplate(
                name="bad_patch",
                pattern=r"return\s+(\w+)",
                replacement=r"return",  # Missing variable
                syntax=PatternSyntax.REGEX,
                language="python",
            )

            # Should fail verification
            results = engine.apply_patch(
                template=template,
                files=[test_file],
                dry_run=False,
                verify=True,
            )

            # Should have error
            assert len(results["errors"]) > 0

        finally:
            Path(test_file).unlink()


class TestComplexPatterns:
    """Complex pattern tests"""

    def test_multi_line_pattern(self):
        """Test multi-line structural pattern"""
        matcher = StructuralMatcher()

        pattern = "if :[cond]:\n    :[body:s]"
        source = """
if x > 0:
    print("positive")
    y = x * 2
"""

        matches = matcher.match(pattern, source, "test.py")

        # Should match multi-line block
        assert len(matches) > 0

    def test_nested_function_calls(self):
        """Test nested function call pattern"""
        matcher = StructuralMatcher()

        pattern = "func(:[args:e])"
        source = "result = func(a, b, nested(c, d))"

        matches = matcher.match(pattern, source, "test.py")

        assert len(matches) > 0


class TestAutoTemplateGeneration:
    """Auto template generation tests"""

    def test_generate_from_example(self):
        """Test auto-generating template from example"""
        engine = SemanticPatchEngine()

        before = "oldFunc(x)"
        after = "newFunc(x)"

        template = engine.create_template_from_example(before, after)

        assert template is not None
        assert template.name == "auto_generated"


class TestRealWorldScenarios:
    """Real-world patch scenarios"""

    def test_deprecated_api_migration(self):
        """Test deprecated API migration"""
        engine = SemanticPatchEngine()

        # Create test file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
from old_module import deprecated_function

def my_code():
    result = deprecated_function(param1, param2)
    return result
""")
            test_file = f.name

        try:
            template = PatchTemplate(
                name="migrate_deprecated",
                pattern="deprecated_function(:[args])",
                replacement="new_function(:[args])",
                syntax=PatternSyntax.STRUCTURAL,
                description="Migrate from deprecated_function to new_function",
            )

            results = engine.apply_patch(
                template=template,
                files=[test_file],
                dry_run=False,
            )

            assert results["total_matches"] == 1

            content = Path(test_file).read_text()
            assert "new_function" in content
            assert "deprecated_function" not in content

        finally:
            Path(test_file).unlink()

    def test_add_type_hints(self):
        """Test adding type hints"""
        engine = SemanticPatchEngine()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def greet(name):\n    return f'Hello {name}'\n")
            test_file = f.name

        try:
            template = PatchTemplate(
                name="add_type_hints",
                pattern=r"def (\w+)\((\w+)\):",
                replacement=r"def \1(\2: str) -> str:",
                syntax=PatternSyntax.REGEX,
                description="Add type hints to function",
            )

            results = engine.apply_patch(
                template=template,
                files=[test_file],
                dry_run=False,
            )

            assert results["total_matches"] == 1

            content = Path(test_file).read_text()
            assert ": str" in content
            assert "-> str" in content

        finally:
            Path(test_file).unlink()


class TestStatistics:
    """Statistics tests"""

    def test_engine_statistics(self):
        """Test engine statistics"""
        engine = SemanticPatchEngine()

        stats = engine.get_statistics()

        assert "total_patches_applied" in stats
        assert "matchers_available" in stats
