"""
Language Detector

Auto-detect programming language from file extension.

Single source of truth for language detection (DRY principle).
"""

from pathlib import Path

from .models import Language


class LanguageDetector:
    """
    Language auto-detection from file extensions.

    Single Responsibility: Language detection only.

    Benefits:
    - DRY: Single source of truth
    - Extensible: Easy to add new languages
    - Testable: Isolated logic

    Example:
        ```python
        detector = LanguageDetector()
        lang = detector.detect(Path("file.py"))
        # → Language.PYTHON

        # Custom extension
        LanguageDetector.register(".myext", Language.PYTHON)
        ```
    """

    # Extension → Language mapping (Single source of truth)
    _EXTENSION_MAP: dict[str, Language] = {
        ".py": Language.PYTHON,
        ".js": Language.JAVASCRIPT,
        ".jsx": Language.JAVASCRIPT,
        ".ts": Language.TYPESCRIPT,
        ".tsx": Language.TYPESCRIPT,
        ".go": Language.GO,
        ".rs": Language.RUST,
        ".java": Language.JAVA,
        ".cpp": Language.CPP,
        ".cc": Language.CPP,
        ".cxx": Language.CPP,
        ".c": Language.CPP,
        ".h": Language.CPP,
        ".hpp": Language.CPP,
    }

    @classmethod
    def detect(cls, file_path: Path) -> Language:
        """
        Detect language from file extension.

        Args:
            file_path: File path

        Returns:
            Detected language (or Language.UNKNOWN if not recognized)

        Example:
            >>> LanguageDetector.detect(Path("main.py"))
            Language.PYTHON

            >>> LanguageDetector.detect(Path("script.xyz"))
            Language.UNKNOWN
        """
        ext = file_path.suffix.lower()
        return cls._EXTENSION_MAP.get(ext, Language.UNKNOWN)

    @classmethod
    def register(cls, extension: str, language: Language) -> None:
        """
        Register custom file extension.

        Enables extensibility without modifying this class.

        Args:
            extension: File extension (e.g., ".myext")
            language: Programming language

        Example:
            >>> LanguageDetector.register(".pyx", Language.PYTHON)
            >>> LanguageDetector.detect(Path("module.pyx"))
            Language.PYTHON
        """
        if not extension.startswith("."):
            extension = f".{extension}"

        cls._EXTENSION_MAP[extension.lower()] = language

    @classmethod
    def supported_extensions(cls) -> list[str]:
        """
        Get list of supported extensions.

        Returns:
            List of supported file extensions

        Example:
            >>> LanguageDetector.supported_extensions()
            ['.py', '.js', '.ts', ...]
        """
        return list(cls._EXTENSION_MAP.keys())

    @classmethod
    def supports(cls, extension: str) -> bool:
        """
        Check if extension is supported.

        Args:
            extension: File extension to check

        Returns:
            True if supported, False otherwise

        Example:
            >>> LanguageDetector.supports(".py")
            True
            >>> LanguageDetector.supports(".xyz")
            False
        """
        return extension.lower() in cls._EXTENSION_MAP
