"""
Test Function/Class Detector

Detects if a function/class is a test based on:
- Function/method name patterns (test_*, *_test, it, describe, etc.)
- File path patterns (test_*.py, *.test.ts, *.spec.js)
- Decorators (@pytest.mark.*, @Test, etc.)
"""

from pathlib import Path


class TestDetector:
    """Detects if a symbol is a test function/class."""

    # Test function name patterns
    TEST_FUNCTION_PREFIXES = {"test_", "test"}
    TEST_FUNCTION_SUFFIXES = {"_test"}
    TEST_FUNCTION_NAMES = {
        # JavaScript/TypeScript
        "it",
        "test",
        "describe",
        "beforeEach",
        "afterEach",
        "beforeAll",
        "afterAll",
        # Python alternatives
        "setUp",
        "tearDown",
        "setUpClass",
        "tearDownClass",
    }

    # Test file patterns
    TEST_FILE_PATTERNS = {
        "python": ["test_*.py", "*_test.py", "tests.py", "conftest.py"],
        "typescript": ["*.test.ts", "*.spec.ts", "*.test.tsx", "*.spec.tsx"],
        "javascript": ["*.test.js", "*.spec.js", "*.test.jsx", "*.spec.jsx"],
        "go": ["*_test.go"],
        "rust": ["*_test.rs"],
        "java": ["*Test.java", "*Tests.java"],
    }

    # Test decorators/annotations
    TEST_DECORATORS = {
        "@pytest.mark",
        "@unittest",
        "@Test",
        "@DisplayName",
        "@ParameterizedTest",
        "@RepeatedTest",
    }

    def is_test_function(
        self, name: str, file_path: str, language: str | None = None, decorators: list[str] | None = None
    ) -> bool:
        """
        Check if a function/method is a test.

        Args:
            name: Function/method name
            file_path: Source file path
            language: Programming language
            decorators: List of decorator/annotation names

        Returns:
            True if detected as test function
        """
        # Check name patterns
        name_lower = name.lower()

        # Exact match
        if name in self.TEST_FUNCTION_NAMES:
            return True

        # Prefix match
        for prefix in self.TEST_FUNCTION_PREFIXES:
            if name_lower.startswith(prefix):
                return True

        # Suffix match
        for suffix in self.TEST_FUNCTION_SUFFIXES:
            if name_lower.endswith(suffix):
                return True

        # Check decorators (Python, Java, etc.)
        if decorators:
            for dec in decorators:
                for test_dec in self.TEST_DECORATORS:
                    if test_dec in dec:
                        return True

        # Check file path
        if self._is_test_file(file_path, language):
            # If in test file and follows test naming convention loosely
            if "test" in name_lower or "spec" in name_lower:
                return True

        return False

    def is_test_class(
        self, name: str, file_path: str, language: str | None = None, decorators: list[str] | None = None
    ) -> bool:
        """
        Check if a class is a test class.

        Args:
            name: Class name
            file_path: Source file path
            language: Programming language
            decorators: List of decorator/annotation names

        Returns:
            True if detected as test class
        """
        name_lower = name.lower()

        # Common test class patterns
        if name.endswith("Test") or name.endswith("Tests") or name.endswith("TestCase"):
            return True

        if name.startswith("Test"):
            return True

        # Check decorators
        if decorators:
            for dec in decorators:
                for test_dec in self.TEST_DECORATORS:
                    if test_dec in dec:
                        return True

        # In test file
        if self._is_test_file(file_path, language):
            if "test" in name_lower or "spec" in name_lower:
                return True

        return False

    def _is_test_file(self, file_path: str, language: str | None = None) -> bool:
        """
        Check if file is a test file based on path patterns.

        Args:
            file_path: File path
            language: Programming language

        Returns:
            True if test file
        """
        path = Path(file_path)
        filename = path.name
        parts = path.parts

        # Check if in test directory
        if "test" in parts or "tests" in parts or "__tests__" in parts:
            return True

        # Language-specific patterns
        if language:
            patterns = self.TEST_FILE_PATTERNS.get(language, [])
            for pattern in patterns:
                if self._match_pattern(filename, pattern):
                    return True

        # Generic patterns
        if filename.startswith("test_") or filename.endswith("_test.py"):
            return True

        if ".test." in filename or ".spec." in filename:
            return True

        return False

    def _match_pattern(self, filename: str, pattern: str) -> bool:
        """Simple glob pattern matching."""
        import fnmatch

        return fnmatch.fnmatch(filename, pattern)
