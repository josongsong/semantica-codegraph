"""
Language Detector Registry Implementation (RFC-101 Cross-Language Support)

Concrete implementation of language detector registry.
Follows Factory Pattern + Dependency Injection.
"""

import re
from typing import Optional

from ...domain.language_detector import (
    IBoundaryDetector,
    ILanguageDetectorRegistry,
    Language,
)


class LanguageDetectorRegistry(ILanguageDetectorRegistry):
    """
    Concrete registry for language-specific boundary detectors.

    Follows:
    - Singleton Pattern (single global registry)
    - Factory Pattern (creates/retrieves detectors)
    - Dependency Injection (register external detectors)
    """

    _instance: Optional["LanguageDetectorRegistry"] = None

    def __new__(cls):
        """Singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._detectors = {}
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize registry (only once)."""
        if not self._initialized:
            self._detectors: dict[Language, IBoundaryDetector] = {}
            self._initialized = True

    def register(self, language: Language, detector: IBoundaryDetector) -> None:
        """
        Register a language-specific detector.

        Args:
            language: Language enum
            detector: Detector implementation
        """
        self._detectors[language] = detector

    def get_detector(self, language: Language) -> Optional[IBoundaryDetector]:
        """
        Get detector for a language.

        Args:
            language: Language enum

        Returns:
            Detector implementation or None
        """
        return self._detectors.get(language)

    def detect_language(self, file_path: str, code: str) -> Language:
        """
        Auto-detect language from file extension and code.

        Strategy:
        1. Check file extension (primary)
        2. Analyze code content (fallback)

        Args:
            file_path: File path (for extension)
            code: Source code (for content analysis)

        Returns:
            Detected Language
        """
        # Extension-based detection
        extension = file_path.split(".")[-1].lower()

        extension_map = {
            "py": Language.PYTHON,
            "ts": Language.TYPESCRIPT,
            "tsx": Language.TYPESCRIPT,
            "js": Language.JAVASCRIPT,
            "jsx": Language.JAVASCRIPT,
            "java": Language.JAVA,
            "kt": Language.KOTLIN,
            "kts": Language.KOTLIN,
            "go": Language.GO,
            "rs": Language.RUST,
            "cs": Language.CSHARP,
        }

        if extension in extension_map:
            return extension_map[extension]

        # Content-based detection (fallback)
        return self._detect_from_content(code)

    def _detect_from_content(self, code: str) -> Language:
        """
        Detect language from code content.

        Uses heuristics:
        - Python: "def ", "import ", "class ", ":"
        - TypeScript: "interface ", "type ", ": string", "export "
        - Java: "public class", "private ", "void "
        - Go: "func ", "package ", "import ("
        """
        # Python indicators
        if re.search(r"\bdef\s+\w+\s*\(", code) or re.search(r"\bimport\s+\w+", code):
            return Language.PYTHON

        # TypeScript indicators
        if re.search(r"\binterface\s+\w+", code) or re.search(r"\btype\s+\w+\s*=", code):
            return Language.TYPESCRIPT

        # Java indicators
        if re.search(r"\bpublic\s+class\s+\w+", code) or re.search(r"\bprivate\s+\w+\s+\w+", code):
            return Language.JAVA

        # Go indicators
        if re.search(r"\bfunc\s+\w+\s*\(", code) or re.search(r"\bpackage\s+\w+", code):
            return Language.GO

        # Default fallback
        return Language.PYTHON

    def get_all_detectors(self) -> dict[Language, IBoundaryDetector]:
        """
        Get all registered detectors.

        Returns:
            Dictionary mapping Language to IBoundaryDetector
        """
        return self._detectors.copy()

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance (for testing)."""
        cls._instance = None
