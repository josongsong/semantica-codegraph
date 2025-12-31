"""
Language Detection by File Extension

This module provides language detection for code files based on their extensions.
Used by IncrementalUpdatePlugin to determine the correct language for IR parsing.

Architecture:
    Infrastructure Layer - Utility for plugin infrastructure

Performance:
    O(1) dict lookup per detection
    Thread-safe (stateless)

Author: CodeGraph Team
Date: 2025-12-12
"""

from pathlib import Path


class LanguageDetector:
    """
    Detects programming language from file extension.

    Thread-Safe:
        Yes (stateless, immutable mapping)

    Performance:
        O(1) per detection (dict lookup)

    Examples:
        >>> detector = LanguageDetector()
        >>> detector.detect("main.py")
        'python'
        >>> detector.detect("app.ts")
        'typescript'
        >>> detector.detect("unknown.xyz")
        'python'  # fallback
    """

    # Extension → Language mapping
    # Canonical source: tree-sitter language support
    _EXTENSION_MAP: dict[str, str] = {
        # Python
        ".py": "python",
        ".pyi": "python",
        ".pyw": "python",
        # TypeScript
        ".ts": "typescript",
        ".tsx": "typescript",
        ".mts": "typescript",
        ".cts": "typescript",
        # JavaScript
        ".js": "javascript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        # Java
        ".java": "java",
        # Kotlin
        ".kt": "kotlin",
        ".kts": "kotlin",
        # Rust
        ".rs": "rust",
        # Go
        ".go": "go",
        # C
        ".c": "c",
        ".h": "c",
        # C++
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".hpp": "cpp",
        ".hh": "cpp",
        ".hxx": "cpp",
        # C#
        ".cs": "csharp",
        # Ruby
        ".rb": "ruby",
        # PHP
        ".php": "php",
        # Swift
        ".swift": "swift",
        # Scala
        ".scala": "scala",
        ".sc": "scala",
        # Shell
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "bash",
        # Lua
        ".lua": "lua",
        # R
        ".r": "r",
        ".R": "r",
        # Haskell
        ".hs": "haskell",
        # Erlang
        ".erl": "erlang",
        # Elixir
        ".ex": "elixir",
        ".exs": "elixir",
    }

    # Default fallback language
    _DEFAULT_LANGUAGE = "python"

    def detect(self, path: str) -> str:
        """
        Detect programming language from file path.

        Args:
            path: File path (absolute or relative)

        Returns:
            Language name (lowercase string)

        Default:
            Returns "python" if extension not recognized

        Examples:
            >>> detector = LanguageDetector()
            >>> detector.detect("main.py")
            'python'
            >>> detector.detect("/path/to/app.ts")
            'typescript'
            >>> detector.detect("Makefile")
            'python'  # fallback
            >>> detector.detect("file.UNKNOWN")
            'python'  # fallback

        Note:
            Case-insensitive extension matching
        """
        ext = Path(path).suffix.lower()
        return self._EXTENSION_MAP.get(ext, self._DEFAULT_LANGUAGE)

    def supported_languages(self) -> set[str]:
        """
        Returns set of all supported languages.

        Returns:
            Set of language names (lowercase)

        Examples:
            >>> detector = LanguageDetector()
            >>> "python" in detector.supported_languages()
            True
            >>> len(detector.supported_languages()) > 10
            True
        """
        return set(self._EXTENSION_MAP.values())

    def supported_extensions(self) -> set[str]:
        """
        Returns set of all supported file extensions.

        Returns:
            Set of extensions (with leading dot, lowercase)

        Examples:
            >>> detector = LanguageDetector()
            >>> ".py" in detector.supported_extensions()
            True
            >>> ".ts" in detector.supported_extensions()
            True
        """
        return set(self._EXTENSION_MAP.keys())

    def is_supported(self, path: str) -> bool:
        """
        Check if file extension is supported.

        Args:
            path: File path

        Returns:
            True if extension is recognized, False otherwise

        Examples:
            >>> detector = LanguageDetector()
            >>> detector.is_supported("main.py")
            True
            >>> detector.is_supported("unknown.xyz")
            False
        """
        ext = Path(path).suffix.lower()
        return ext in self._EXTENSION_MAP
