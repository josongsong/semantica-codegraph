"""
Test LanguageDetector

Tests for language auto-detection.
"""

from pathlib import Path

import pytest

from codegraph_engine.code_foundation.domain.language_detector import LanguageDetector
from codegraph_engine.code_foundation.domain.models import Language


class TestLanguageDetector:
    """Base case tests"""

    @pytest.mark.parametrize(
        "filename,expected_language",
        [
            ("script.py", Language.PYTHON),
            ("app.js", Language.JAVASCRIPT),
            ("component.jsx", Language.JAVASCRIPT),
            ("module.ts", Language.TYPESCRIPT),
            ("component.tsx", Language.TYPESCRIPT),
            ("main.go", Language.GO),
            ("lib.rs", Language.RUST),
            ("Main.java", Language.JAVA),
            ("program.cpp", Language.CPP),
            ("program.cc", Language.CPP),
            ("program.cxx", Language.CPP),
            ("program.c", Language.CPP),
            ("header.h", Language.CPP),
            ("header.hpp", Language.CPP),
        ],
    )
    def test_detect_language(self, filename, expected_language):
        """Base case: Detect language from extension"""
        result = LanguageDetector.detect(Path(filename))
        assert result == expected_language

    def test_detect_unknown_language(self):
        """Base case: Unknown extension returns UNKNOWN"""
        result = LanguageDetector.detect(Path("file.xyz"))
        assert result == Language.UNKNOWN

    def test_case_insensitive(self):
        """Base case: Extension detection is case-insensitive"""
        assert LanguageDetector.detect(Path("FILE.PY")) == Language.PYTHON
        assert LanguageDetector.detect(Path("FILE.Py")) == Language.PYTHON
        assert LanguageDetector.detect(Path("file.PY")) == Language.PYTHON

    def test_supported_extensions(self):
        """Base case: Get list of supported extensions"""
        extensions = LanguageDetector.supported_extensions()

        assert isinstance(extensions, list)
        assert len(extensions) > 0
        assert ".py" in extensions
        assert ".js" in extensions
        assert ".ts" in extensions

    def test_supports(self):
        """Base case: Check if extension is supported"""
        assert LanguageDetector.supports(".py") is True
        assert LanguageDetector.supports(".js") is True
        assert LanguageDetector.supports(".xyz") is False


class TestLanguageDetectorEdgeCases:
    """Edge case tests"""

    def test_empty_extension(self):
        """Edge case: File with no extension"""
        result = LanguageDetector.detect(Path("Makefile"))
        assert result == Language.UNKNOWN

    def test_multiple_dots(self):
        """Edge case: File with multiple dots"""
        result = LanguageDetector.detect(Path("test.spec.ts"))
        assert result == Language.TYPESCRIPT

    def test_hidden_file(self):
        """Edge case: Hidden file"""
        result = LanguageDetector.detect(Path(".gitignore"))
        assert result == Language.UNKNOWN

    def test_hidden_python_file(self):
        """Edge case: Hidden Python file"""
        result = LanguageDetector.detect(Path(".test.py"))
        assert result == Language.PYTHON


class TestLanguageDetectorCornerCases:
    """Corner case tests"""

    def test_register_custom_extension(self):
        """Corner case: Register custom extension"""
        # Register .pyx as Python
        LanguageDetector.register(".pyx", Language.PYTHON)

        result = LanguageDetector.detect(Path("module.pyx"))
        assert result == Language.PYTHON

        # Cleanup
        LanguageDetector._EXTENSION_MAP.pop(".pyx", None)

    def test_register_without_dot(self):
        """Corner case: Register extension without leading dot"""
        LanguageDetector.register("myext", Language.PYTHON)

        result = LanguageDetector.detect(Path("file.myext"))
        assert result == Language.PYTHON

        # Cleanup
        LanguageDetector._EXTENSION_MAP.pop(".myext", None)

    def test_register_overwrites(self):
        """Corner case: Register overwrites existing mapping"""
        original = LanguageDetector.detect(Path("test.js"))
        assert original == Language.JAVASCRIPT

        # Overwrite .js → Python
        LanguageDetector.register(".js", Language.PYTHON)
        result = LanguageDetector.detect(Path("test.js"))
        assert result == Language.PYTHON

        # Restore
        LanguageDetector.register(".js", Language.JAVASCRIPT)

    def test_supports_case_insensitive(self):
        """Corner case: supports() is case-insensitive"""
        assert LanguageDetector.supports(".PY") is True
        assert LanguageDetector.supports(".Py") is True
        assert LanguageDetector.supports("PY") is False  # No dot


class TestLanguageDetectorExtensibility:
    """Test extensibility"""

    def test_extensibility(self):
        """Test that new languages can be added"""
        # Add custom language
        LanguageDetector.register(".custom", Language.UNKNOWN)

        assert LanguageDetector.supports(".custom") is True
        assert LanguageDetector.detect(Path("file.custom")) == Language.UNKNOWN

        # Cleanup
        LanguageDetector._EXTENSION_MAP.pop(".custom", None)
