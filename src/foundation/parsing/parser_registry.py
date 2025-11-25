"""
Parser Registry for Tree-sitter

Manages language-specific parsers and provides a unified interface.
"""

import logging
from pathlib import Path

try:
    from tree_sitter import Parser
    from tree_sitter_language_pack import get_language
except ImportError as e:
    raise ImportError(
        "tree-sitter-language-pack is required. " "Install with: pip install tree-sitter tree-sitter-language-pack"
    ) from e

logger = logging.getLogger(__name__)


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
        self._setup_languages()

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

    def _setup_languages(self):
        """Setup Tree-sitter languages"""
        # Register languages with their aliases
        self._register_language("python", ["py"])
        self._register_language("typescript", ["ts"])
        self._register_language("tsx")
        self._register_language("javascript", ["js"])
        self._register_language("go")
        self._register_language("java")
        self._register_language("rust")
        self._register_language("c")
        self._register_language("cpp")

    def get_parser(self, language: str) -> Parser | None:
        """
        Get parser for the specified language.

        Args:
            language: Language name (python, typescript, javascript, etc.)

        Returns:
            Parser instance or None if language not supported
        """
        language = language.lower()

        # Return cached parser
        if language in self._parsers:
            return self._parsers[language]

        # Get language instance
        lang = self._languages.get(language)
        if not lang:
            return None

        # Create and cache parser
        parser = Parser(lang)
        self._parsers[language] = parser
        return parser

    def detect_language(self, file_path: str | Path) -> str | None:
        """
        Detect language from file extension.

        Args:
            file_path: Path to source file

        Returns:
            Language name or None if not supported
        """
        if isinstance(file_path, str):
            file_path = Path(file_path)

        ext = file_path.suffix.lower()

        ext_map = {
            ".py": "python",
            ".pyi": "python",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".js": "javascript",
            ".jsx": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".go": "go",
            ".java": "java",
            ".rs": "rust",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".c": "c",
            ".h": "c",
            ".hpp": "cpp",
        }

        return ext_map.get(ext)

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
