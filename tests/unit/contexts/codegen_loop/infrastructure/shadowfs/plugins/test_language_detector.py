"""
Tests for LanguageDetector

Test Coverage:
    - Base cases: common languages
    - Corner cases: unknown extensions, no extensions, case insensitive
    - Edge cases: edge extensions, path formats

Author: CodeGraph Team
Date: 2025-12-12
"""

import pytest

from codegraph_runtime.codegen_loop.infrastructure.shadowfs.plugins.language_detector import LanguageDetector


class TestBaseCases:
    """Base case tests: common language detection"""

    def test_detect_python(self):
        """Base: .py → python"""
        detector = LanguageDetector()
        assert detector.detect("main.py") == "python"

    def test_detect_typescript(self):
        """Base: .ts → typescript"""
        detector = LanguageDetector()
        assert detector.detect("app.ts") == "typescript"

    def test_detect_javascript(self):
        """Base: .js → javascript"""
        detector = LanguageDetector()
        assert detector.detect("index.js") == "javascript"

    def test_detect_java(self):
        """Base: .java → java"""
        detector = LanguageDetector()
        assert detector.detect("Main.java") == "java"

    def test_detect_kotlin(self):
        """Base: .kt → kotlin"""
        detector = LanguageDetector()
        assert detector.detect("App.kt") == "kotlin"

    def test_detect_rust(self):
        """Base: .rs → rust"""
        detector = LanguageDetector()
        assert detector.detect("main.rs") == "rust"

    def test_detect_go(self):
        """Base: .go → go"""
        detector = LanguageDetector()
        assert detector.detect("main.go") == "go"

    def test_detect_cpp(self):
        """Base: .cpp → cpp"""
        detector = LanguageDetector()
        assert detector.detect("main.cpp") == "cpp"


class TestCornerCases:
    """Corner case tests: edge scenarios"""

    def test_unknown_extension_fallback(self):
        """Corner: unknown extension → python fallback"""
        detector = LanguageDetector()
        assert detector.detect("file.xyz") == "python"

    def test_no_extension_fallback(self):
        """Corner: no extension → python fallback"""
        detector = LanguageDetector()
        assert detector.detect("Makefile") == "python"

    def test_case_insensitive_uppercase(self):
        """Corner: uppercase extension → case insensitive match"""
        detector = LanguageDetector()
        assert detector.detect("Main.PY") == "python"
        assert detector.detect("App.TS") == "typescript"
        assert detector.detect("Index.JS") == "javascript"

    def test_case_insensitive_mixed(self):
        """Corner: mixed case extension → case insensitive match"""
        detector = LanguageDetector()
        assert detector.detect("file.Py") == "python"
        assert detector.detect("file.Ts") == "typescript"

    def test_empty_string_fallback(self):
        """Corner: empty string → python fallback"""
        detector = LanguageDetector()
        assert detector.detect("") == "python"

    def test_dot_only_fallback(self):
        """Corner: dot only → python fallback"""
        detector = LanguageDetector()
        assert detector.detect(".") == "python"

    def test_multiple_dots_last_wins(self):
        """Corner: multiple dots → last extension used"""
        detector = LanguageDetector()
        assert detector.detect("file.old.py") == "python"
        assert detector.detect("backup.txt.ts") == "typescript"


class TestEdgeCases:
    """Edge case tests: absolute paths, special formats"""

    def test_absolute_path(self):
        """Edge: absolute path → language detected correctly"""
        detector = LanguageDetector()
        assert detector.detect("/usr/local/bin/main.py") == "python"
        assert detector.detect("/home/user/project/app.ts") == "typescript"

    def test_relative_path(self):
        """Edge: relative path → language detected correctly"""
        detector = LanguageDetector()
        assert detector.detect("./src/main.py") == "python"
        assert detector.detect("../project/app.ts") == "typescript"

    def test_nested_directories(self):
        """Edge: deeply nested path → language detected correctly"""
        detector = LanguageDetector()
        path = "a/b/c/d/e/f/g/h/i/j/main.py"
        assert detector.detect(path) == "python"

    def test_special_characters_in_filename(self):
        """Edge: special characters → language detected correctly"""
        detector = LanguageDetector()
        assert detector.detect("file-name.py") == "python"
        assert detector.detect("file_name.py") == "python"
        assert detector.detect("file.name.py") == "python"

    def test_all_supported_python_extensions(self):
        """Edge: all Python extensions → python"""
        detector = LanguageDetector()
        assert detector.detect("file.py") == "python"
        assert detector.detect("file.pyi") == "python"
        assert detector.detect("file.pyw") == "python"

    def test_all_supported_typescript_extensions(self):
        """Edge: all TypeScript extensions → typescript"""
        detector = LanguageDetector()
        assert detector.detect("file.ts") == "typescript"
        assert detector.detect("file.tsx") == "typescript"
        assert detector.detect("file.mts") == "typescript"
        assert detector.detect("file.cts") == "typescript"

    def test_all_supported_javascript_extensions(self):
        """Edge: all JavaScript extensions → javascript"""
        detector = LanguageDetector()
        assert detector.detect("file.js") == "javascript"
        assert detector.detect("file.jsx") == "javascript"
        assert detector.detect("file.mjs") == "javascript"
        assert detector.detect("file.cjs") == "javascript"


class TestUtilityMethods:
    """Tests for utility methods"""

    def test_supported_languages(self):
        """Utility: supported_languages returns all languages"""
        detector = LanguageDetector()
        languages = detector.supported_languages()

        # Check type
        assert isinstance(languages, set)

        # Check common languages present
        assert "python" in languages
        assert "typescript" in languages
        assert "javascript" in languages
        assert "java" in languages
        assert "kotlin" in languages
        assert "rust" in languages
        assert "go" in languages

    def test_supported_extensions(self):
        """Utility: supported_extensions returns all extensions"""
        detector = LanguageDetector()
        extensions = detector.supported_extensions()

        # Check type
        assert isinstance(extensions, set)

        # Check common extensions present
        assert ".py" in extensions
        assert ".ts" in extensions
        assert ".js" in extensions
        assert ".java" in extensions
        assert ".kt" in extensions
        assert ".rs" in extensions
        assert ".go" in extensions

    def test_is_supported_true(self):
        """Utility: is_supported returns True for supported extensions"""
        detector = LanguageDetector()
        assert detector.is_supported("main.py") is True
        assert detector.is_supported("app.ts") is True
        assert detector.is_supported("index.js") is True

    def test_is_supported_false(self):
        """Utility: is_supported returns False for unsupported extensions"""
        detector = LanguageDetector()
        assert detector.is_supported("file.xyz") is False
        assert detector.is_supported("Makefile") is False
        assert detector.is_supported("file.unknown") is False

    def test_is_supported_case_insensitive(self):
        """Utility: is_supported is case insensitive"""
        detector = LanguageDetector()
        assert detector.is_supported("Main.PY") is True
        assert detector.is_supported("App.TS") is True


class TestThreadSafety:
    """Tests for thread safety"""

    def test_stateless_detector(self):
        """Thread-Safety: detector is stateless"""
        detector = LanguageDetector()

        # Multiple calls with same input
        assert detector.detect("main.py") == "python"
        assert detector.detect("main.py") == "python"
        assert detector.detect("main.py") == "python"

        # Calls with different inputs don't interfere
        assert detector.detect("app.ts") == "typescript"
        assert detector.detect("main.py") == "python"
        assert detector.detect("index.js") == "javascript"

    def test_multiple_instances_independent(self):
        """Thread-Safety: multiple instances are independent"""
        detector1 = LanguageDetector()
        detector2 = LanguageDetector()

        # Both should work independently
        assert detector1.detect("main.py") == "python"
        assert detector2.detect("app.ts") == "typescript"

        # Results should be consistent
        assert detector1.detect("main.py") == detector2.detect("main.py")
