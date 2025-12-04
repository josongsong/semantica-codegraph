"""
Parser Registry Tests

Tests for Tree-sitter parser registry.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.foundation.parsing.parser_registry import ParserRegistry, get_registry


class TestParserRegistryBasics:
    """Test basic ParserRegistry functionality."""

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_registry_creation(self, mock_get_language):
        """Test ParserRegistry can be instantiated."""
        mock_get_language.return_value = MagicMock()

        registry = ParserRegistry()

        assert registry is not None
        assert isinstance(registry._parsers, dict)
        assert isinstance(registry._languages, dict)

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_languages_loaded_on_init(self, mock_get_language):
        """Test languages are loaded during initialization."""
        mock_get_language.return_value = MagicMock()

        registry = ParserRegistry()

        # Should have called get_language for each supported language
        assert mock_get_language.call_count > 0

        # Should have languages registered
        assert len(registry._languages) > 0


class TestLanguageDetection:
    """Test language detection from file extensions."""

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_detect_python(self, mock_get_language):
        """Test Python file detection."""
        mock_get_language.return_value = MagicMock()
        registry = ParserRegistry()

        assert registry.detect_language("test.py") == "python"
        assert registry.detect_language("test.pyi") == "python"
        assert registry.detect_language(Path("test.py")) == "python"

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_detect_typescript(self, mock_get_language):
        """Test TypeScript file detection."""
        mock_get_language.return_value = MagicMock()
        registry = ParserRegistry()

        assert registry.detect_language("test.ts") == "typescript"
        assert registry.detect_language("test.tsx") == "tsx"

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_detect_javascript(self, mock_get_language):
        """Test JavaScript file detection."""
        mock_get_language.return_value = MagicMock()
        registry = ParserRegistry()

        assert registry.detect_language("test.js") == "javascript"
        assert registry.detect_language("test.jsx") == "javascript"
        assert registry.detect_language("test.mjs") == "javascript"
        assert registry.detect_language("test.cjs") == "javascript"

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_detect_other_languages(self, mock_get_language):
        """Test other language detection."""
        mock_get_language.return_value = MagicMock()
        registry = ParserRegistry()

        assert registry.detect_language("test.go") == "go"
        assert registry.detect_language("test.java") == "java"
        assert registry.detect_language("test.rs") == "rust"
        assert registry.detect_language("test.c") == "c"
        assert registry.detect_language("test.cpp") == "cpp"

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_detect_unsupported_extension(self, mock_get_language):
        """Test unsupported file extension returns None."""
        mock_get_language.return_value = MagicMock()
        registry = ParserRegistry()

        assert registry.detect_language("test.txt") is None
        assert registry.detect_language("test.md") is None
        assert registry.detect_language("test.unknown") is None

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_detect_case_insensitive(self, mock_get_language):
        """Test file extension detection is case-insensitive."""
        mock_get_language.return_value = MagicMock()
        registry = ParserRegistry()

        assert registry.detect_language("test.PY") == "python"
        assert registry.detect_language("test.TS") == "typescript"


class TestParserRetrieval:
    """Test parser retrieval and caching."""

    @patch("src.foundation.parsing.parser_registry.Parser")
    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_get_parser_creates_parser(self, mock_get_language, mock_parser_class):
        """Test get_parser creates and returns parser."""
        mock_lang = MagicMock()
        mock_get_language.return_value = mock_lang
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser

        registry = ParserRegistry()
        parser = registry.get_parser("python")

        # Should create parser with language
        mock_parser_class.assert_called_with(mock_lang)
        assert parser is mock_parser

    @patch("src.foundation.parsing.parser_registry.Parser")
    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_get_parser_caching(self, mock_get_language, mock_parser_class):
        """Test get_parser caches parsers."""
        mock_get_language.return_value = MagicMock()
        mock_parser_class.return_value = MagicMock()

        registry = ParserRegistry()

        # Get parser twice
        parser1 = registry.get_parser("python")
        parser2 = registry.get_parser("python")

        # Should return same instance (cached)
        assert parser1 is parser2

        # Should only create parser once
        assert mock_parser_class.call_count == 1

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_get_parser_unsupported_language(self, mock_get_language):
        """Test get_parser returns None for unsupported language."""
        mock_get_language.return_value = MagicMock()
        registry = ParserRegistry()

        parser = registry.get_parser("unsupported_lang")

        assert parser is None

    @patch("src.foundation.parsing.parser_registry.Parser")
    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_get_parser_case_insensitive(self, mock_get_language, mock_parser_class):
        """Test get_parser is case-insensitive."""
        mock_get_language.return_value = MagicMock()
        mock_parser_class.return_value = MagicMock()

        registry = ParserRegistry()

        parser1 = registry.get_parser("Python")
        parser2 = registry.get_parser("PYTHON")
        parser3 = registry.get_parser("python")

        # All should return same parser (case-insensitive)
        assert parser1 is parser2 is parser3


class TestLanguageSupport:
    """Test language support checking."""

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_supports_language(self, mock_get_language):
        """Test supports_language returns True for supported languages."""
        mock_get_language.return_value = MagicMock()
        registry = ParserRegistry()

        assert registry.supports_language("python") is True
        assert registry.supports_language("typescript") is True
        assert registry.supports_language("javascript") is True

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_supports_language_with_aliases(self, mock_get_language):
        """Test supports_language works with aliases."""
        mock_get_language.return_value = MagicMock()
        registry = ParserRegistry()

        # Aliases should be supported
        assert registry.supports_language("py") is True
        assert registry.supports_language("ts") is True
        assert registry.supports_language("js") is True

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_does_not_support_unknown_language(self, mock_get_language):
        """Test supports_language returns False for unknown languages."""
        mock_get_language.return_value = MagicMock()
        registry = ParserRegistry()

        assert registry.supports_language("unknown") is False
        assert registry.supports_language("fortran") is False

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_supported_languages_list(self, mock_get_language):
        """Test supported_languages returns list of languages."""
        mock_get_language.return_value = MagicMock()
        registry = ParserRegistry()

        langs = registry.supported_languages

        # Should be a list
        assert isinstance(langs, list)

        # Should contain some expected languages
        assert "python" in langs
        assert "typescript" in langs
        assert "javascript" in langs

        # Should NOT contain aliases
        assert "py" not in langs
        assert "ts" not in langs
        assert "js" not in langs

        # Should be sorted
        assert langs == sorted(langs)


class TestGlobalRegistry:
    """Test global registry singleton."""

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_get_registry_singleton(self, mock_get_language):
        """Test get_registry returns singleton instance."""
        mock_get_language.return_value = MagicMock()

        # Clear global registry
        import src.foundation.parsing.parser_registry as pr_module

        pr_module._registry = None

        # Get registry twice
        registry1 = get_registry()
        registry2 = get_registry()

        # Should return same instance
        assert registry1 is registry2

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_get_registry_creates_on_first_call(self, mock_get_language):
        """Test get_registry creates registry on first call."""
        mock_get_language.return_value = MagicMock()

        # Clear global registry
        import src.foundation.parsing.parser_registry as pr_module

        pr_module._registry = None

        # Should be None initially
        assert pr_module._registry is None

        # Get registry
        registry = get_registry()

        # Should create instance
        assert registry is not None
        assert pr_module._registry is registry


class TestLanguageRegistration:
    """Test language registration internals."""

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_language_with_aliases(self, mock_get_language):
        """Test language registration with aliases."""
        mock_lang = MagicMock()
        mock_get_language.return_value = mock_lang

        registry = ParserRegistry()

        # Python should be registered with "py" alias
        python_lang = registry._languages.get("python")
        py_lang = registry._languages.get("py")

        # Both should point to same language object
        assert python_lang is py_lang

    @patch("src.foundation.parsing.parser_registry.get_language")
    def test_language_registration_failure(self, mock_get_language):
        """Test language registration handles failures gracefully."""

        # Make get_language fail for one language
        def side_effect(name):
            if name == "python":
                raise Exception("Failed to load")
            return MagicMock()

        mock_get_language.side_effect = side_effect

        # Should not raise, just log warning
        registry = ParserRegistry()

        # Failed language should not be in registry
        assert "python" not in registry._languages

        # Other languages should still work
        assert "typescript" in registry._languages or "javascript" in registry._languages
