"""
Parser Registry

Manages registration and lookup of language-specific parsers.
"""

from typing import Dict, List, Optional
from pathlib import Path

from ..ports.parser_port import ParserPort, ParserError


class LanguageDetector:
    """
    Detects programming language from file extension or content.

    Simple extension-based detection with fallback to content analysis.
    """

    # Extension to language mapping
    EXTENSION_MAP = {
        ".py": "python",
        ".pyi": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".rs": "rust",
        ".go": "go",
        ".java": "java",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
        ".rb": "ruby",
        ".php": "php",
        ".cs": "csharp",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "zsh",
        ".fish": "fish",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".xml": "xml",
        ".md": "markdown",
        ".rst": "rst",
        ".sql": "sql",
    }

    def detect_language(self, file_path: Path, content: Optional[str] = None) -> str:
        """
        Detect language from file path and optionally content.

        Args:
            file_path: Path to the file
            content: Optional file content for content-based detection

        Returns:
            Detected language (lowercase)

        Raises:
            ValueError: If language cannot be detected
        """
        # Try extension-based detection
        extension = file_path.suffix.lower()
        if extension in self.EXTENSION_MAP:
            return self.EXTENSION_MAP[extension]

        # Fallback to content-based detection (if content provided)
        if content:
            return self._detect_from_content(content)

        raise ValueError(f"Cannot detect language for file: {file_path}")

    def _detect_from_content(self, content: str) -> str:
        """
        Detect language from file content.

        Args:
            content: File content

        Returns:
            Detected language

        Raises:
            ValueError: If language cannot be detected
        """
        # Simple shebang detection
        if content.startswith("#!"):
            first_line = content.split("\n")[0].lower()
            if "python" in first_line:
                return "python"
            if "node" in first_line or "javascript" in first_line:
                return "javascript"
            if "bash" in first_line or "sh" in first_line:
                return "bash"

        raise ValueError("Cannot detect language from content")


class ParserRegistry:
    """
    Registry for managing parser implementations.

    Allows registration and lookup of parsers by language.
    """

    def __init__(self):
        """Initialize empty registry."""
        self._parsers: Dict[str, ParserPort] = {}
        self.language_detector = LanguageDetector()

    def register(self, parser: ParserPort) -> None:
        """
        Register a parser.

        Args:
            parser: Parser implementation

        Raises:
            ValueError: If parser doesn't support any language
        """
        # Auto-detect supported languages by trying common ones
        supported_languages = []
        for lang in ["python", "typescript", "javascript", "rust", "go"]:
            if parser.supports(lang):
                supported_languages.append(lang)

        if not supported_languages:
            raise ValueError(f"Parser {parser.__class__.__name__} doesn't support any language")

        for lang in supported_languages:
            self._parsers[lang] = parser

    def register_for_language(self, language: str, parser: ParserPort) -> None:
        """
        Register a parser for a specific language.

        Args:
            language: Language identifier (lowercase)
            parser: Parser implementation
        """
        if not parser.supports(language):
            raise ValueError(
                f"Parser {parser.__class__.__name__} doesn't support {language}"
            )

        self._parsers[language] = parser

    def get_parser(self, language: str) -> Optional[ParserPort]:
        """
        Get parser for a language.

        Args:
            language: Language identifier (lowercase)

        Returns:
            Parser implementation or None if not found
        """
        return self._parsers.get(language.lower())

    def get_parser_for_file(self, file_path: Path) -> Optional[ParserPort]:
        """
        Get parser for a file based on its extension.

        Args:
            file_path: Path to the file

        Returns:
            Parser implementation or None if language not supported

        Raises:
            ValueError: If language cannot be detected
        """
        language = self.language_detector.detect_language(file_path)
        return self.get_parser(language)

    def supported_languages(self) -> List[str]:
        """
        Get list of supported languages.

        Returns:
            List of language identifiers
        """
        return list(self._parsers.keys())

    def is_supported(self, language: str) -> bool:
        """
        Check if a language is supported.

        Args:
            language: Language identifier

        Returns:
            True if supported, False otherwise
        """
        return language.lower() in self._parsers


# Global registry instance
_global_registry: Optional[ParserRegistry] = None


def get_global_registry() -> ParserRegistry:
    """
    Get the global parser registry instance.

    Returns:
        Global parser registry
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ParserRegistry()
    return _global_registry


def register_parser(parser: ParserPort) -> None:
    """
    Register a parser in the global registry.

    Args:
        parser: Parser implementation
    """
    get_global_registry().register(parser)