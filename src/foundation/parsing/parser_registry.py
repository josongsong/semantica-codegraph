"""
Parser Registry for Tree-sitter

Manages language-specific parsers and provides a unified interface.
"""

from pathlib import Path
from typing import Optional

try:
    import tree_sitter_python as tspython
    import tree_sitter_typescript as tstype
    from tree_sitter import Language, Parser
except ImportError:
    raise ImportError(
        "tree-sitter is required. "
        "Install with: pip install tree-sitter tree-sitter-python tree-sitter-typescript"
    )


class ParserRegistry:
    """
    Registry for language parsers.

    Supports:
    - Python
    - TypeScript/JavaScript (planned)
    - Go, Java, Rust (future)
    """

    def __init__(self):
        self._parsers: dict[str, Parser] = {}
        self._languages: dict[str, Language] = {}
        self._setup_languages()

    def _setup_languages(self):
        """Setup Tree-sitter languages"""
        # Python
        try:
            self._languages["python"] = Language(tspython.language())
            self._languages["py"] = self._languages["python"]  # Alias
        except Exception as e:
            print(f"Warning: Failed to load Python parser: {e}")

        # TypeScript
        try:
            # TypeScript has two variants: typescript and tsx
            ts_lang = Language(tstype.language())
            self._languages["typescript"] = ts_lang
            self._languages["ts"] = ts_lang  # Alias

            tsx_lang = Language(tstype.language_tsx())
            self._languages["tsx"] = tsx_lang
        except Exception as e:
            print(f"Warning: Failed to load TypeScript parser: {e}")

        # JavaScript (using TypeScript parser)
        if "typescript" in self._languages:
            self._languages["javascript"] = self._languages["typescript"]
            self._languages["js"] = self._languages["typescript"]

    def get_parser(self, language: str) -> Optional[Parser]:
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

    def detect_language(self, file_path: str | Path) -> Optional[str]:
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
            # Future extensions
            ".go": "go",
            ".java": "java",
            ".rs": "rust",
            ".cpp": "cpp",
            ".c": "c",
        }

        return ext_map.get(ext)

    def supports_language(self, language: str) -> bool:
        """Check if language is supported"""
        return language.lower() in self._languages

    @property
    def supported_languages(self) -> list[str]:
        """Get list of supported languages"""
        # Return unique language names (excluding aliases)
        unique_langs = set()
        for lang in self._languages:
            if lang not in {"py", "ts", "js"}:  # Exclude aliases
                unique_langs.add(lang)
        return sorted(unique_langs)


# Global registry instance
_registry: Optional[ParserRegistry] = None


def get_registry() -> ParserRegistry:
    """Get global parser registry instance"""
    global _registry
    if _registry is None:
        _registry = ParserRegistry()
    return _registry
