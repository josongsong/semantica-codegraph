"""
Parser Registry for Tree-sitter

Manages language-specific parsers and provides a unified interface.
"""

from pathlib import Path

from codegraph_shared.common.observability import get_logger

try:
    from tree_sitter import Parser
    from tree_sitter_language_pack import get_language
except ImportError as e:
    raise ImportError(
        "tree-sitter-language-pack is required. Install with: pip install tree-sitter tree-sitter-language-pack"
    ) from e

logger = get_logger(__name__)


class ParserRegistry:
    """
    Registry for language parsers.

    Supports:
    - Python
    - TypeScript/JavaScript
    - Go
    - Java
    - Rust
    - C/C++
    """

    def __init__(self):
        self._parsers: dict[str, Parser] = {}
        self._languages: dict[str, object] = {}
        # SOTA: Lazy loading - only load languages when needed
        # Before: 11 languages × 160ms = 1.77s
        # After: Load on-demand (Python only = 0.16s for attrs)
        self._language_names = [
            ("python", ["py"]),
            ("typescript", ["ts"]),
            ("tsx", None),
            ("javascript", ["js"]),
            ("go", None),
            ("java", None),
            ("kotlin", ["kt"]),
            ("rust", None),
            ("c", None),
            ("cpp", None),
            ("vue", None),
        ]

    def _register_language(self, name: str, aliases: list[str] | None = None) -> None:
        """
        Register a language and its aliases.

        Args:
            name: Language name (e.g., "python", "typescript")
            aliases: Optional list of aliases (e.g., ["py"] for python)
        """
        try:
            lang = get_language(name)
            self._languages[name] = lang

            if aliases:
                for alias in aliases:
                    self._languages[alias] = lang

            logger.debug(f"Loaded {name} parser" + (f" with aliases {aliases}" if aliases else ""))
        except Exception as e:
            logger.warning(f"Failed to load {name} parser: {e}")

    def get_parser(self, language: str) -> Parser | None:
        """
        Get parser for the specified language (lazy loading).

        SOTA: Load language on first use instead of all at init.
        Reduces init time from 1.77s → 0.16s for single-language projects.

        Args:
            language: Language name (python, typescript, javascript, etc.)

        Returns:
            Parser instance or None if language not supported
        """
        language = language.lower()

        # Return cached parser
        if language in self._parsers:
            return self._parsers[language]

        # Lazy load: Get or load language instance
        lang = self._languages.get(language)
        if not lang:
            # Try to load language now
            lang = self._lazy_load_language(language)
            if not lang:
                return None

        # Create and cache parser
        parser = Parser(lang)
        self._parsers[language] = parser
        return parser

    def _lazy_load_language(self, language: str) -> object | None:
        """
        Lazy load a language on first use.

        Args:
            language: Language name

        Returns:
            Language object or None
        """
        # Check if language is in our supported list
        for lang_name, aliases in self._language_names:
            if language == lang_name or (aliases and language in aliases):
                self._register_language(lang_name, aliases)
                return self._languages.get(language)

        return None

    # ⭐ P3-1: Centralized extension → language mapping
    # All language detection should use this map
    EXTENSION_MAP: dict[str, str] = {
        # Python
        ".py": "python",
        ".pyi": "python",
        ".pyw": "python",
        # TypeScript/JavaScript
        ".ts": "typescript",
        ".tsx": "tsx",
        ".mts": "typescript",
        ".cts": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        # Go
        ".go": "go",
        # Java/Kotlin
        ".java": "java",
        ".kt": "kotlin",
        ".kts": "kotlin",
        # Rust
        ".rs": "rust",
        # C/C++
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".hpp": "cpp",
        ".hxx": "cpp",
        ".hh": "cpp",
        # Ruby
        ".rb": "ruby",
        # Swift
        ".swift": "swift",
        # PHP
        ".php": "php",
        # Scala
        ".scala": "scala",
        ".sc": "scala",
        # C#
        ".cs": "csharp",
    }

    def detect_language(self, file_path: str | Path) -> str | None:
        """
        ⭐ P3-1: Centralized language detection from file extension.

        This is the single source of truth for language detection.
        All other code should use this method (or the module-level function).

        Args:
            file_path: Path to source file

        Returns:
            Language name or None if not supported
        """
        if isinstance(file_path, str):
            file_path = Path(file_path)

        ext = file_path.suffix.lower()
        return self.EXTENSION_MAP.get(ext)

    def supports_language(self, language: str) -> bool:
        """Check if language is supported"""
        return language.lower() in self._languages

    @property
    def supported_languages(self) -> list[str]:
        """Get list of supported languages"""
        # Return unique language names (excluding aliases)
        aliases = {"py", "ts", "js"}  # Short-form aliases
        unique_langs = {lang for lang in self._languages if lang not in aliases}
        return sorted(unique_langs)


# Global registry instance
_registry: ParserRegistry | None = None


def get_registry() -> ParserRegistry:
    """Get global parser registry instance"""
    global _registry
    if _registry is None:
        _registry = ParserRegistry()
    return _registry


# ⭐ P3-1: Convenience functions for centralized language detection
def detect_language(file_path: str | Path) -> str | None:
    """
    ⭐ P3-1: Centralized language detection from file extension.

    This is a convenience function that uses the global ParserRegistry.
    Use this instead of implementing your own extension-based detection.

    Args:
        file_path: Path to source file

    Returns:
        Language name or None if not supported

    Examples:
        >>> detect_language("main.py")
        'python'
        >>> detect_language("App.tsx")
        'tsx'
        >>> detect_language("/path/to/Main.java")
        'java'
    """
    return get_registry().detect_language(file_path)


def get_extension_map() -> dict[str, str]:
    """
    Get the extension → language mapping.

    Returns:
        Dictionary mapping file extensions to language names
    """
    return ParserRegistry.EXTENSION_MAP.copy()
