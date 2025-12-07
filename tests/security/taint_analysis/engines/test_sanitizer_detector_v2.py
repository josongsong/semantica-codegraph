"""
Unit tests for ImprovedSanitizerDetector

Tests:
1. Known library detection
2. User config detection
3. Heuristic detection
4. Confidence scoring
"""

import pytest
from dataclasses import dataclass
from pathlib import Path
from src.contexts.code_foundation.infrastructure.analyzers.sanitizer_detector_v2 import (
    SanitizerSignature,
    ImprovedSanitizerDetector,
    create_sanitizer_detector,
)


@dataclass
class MockFunction:
    """Mock function definition for testing"""

    name: str
    qualified_name: str = ""
    body: str = ""

    def __post_init__(self):
        if not self.qualified_name:
            self.qualified_name = self.name


class TestSanitizerSignature:
    """Test SanitizerSignature dataclass"""

    def test_basic_creation(self):
        """Test creating a signature"""
        sig = SanitizerSignature(
            pattern="html.escape",
            sanitizer_type="escape",
            confidence=1.0,
            source="known_library",
            description="HTML escaping",
        )

        assert sig.pattern == "html.escape"
        assert sig.sanitizer_type == "escape"
        assert sig.confidence == 1.0
        assert sig.source == "known_library"


class TestKnownLibraryDetection:
    """Test Tier 1: Known library detection"""

    def test_detect_html_escape(self):
        """Test detecting html.escape"""
        detector = ImprovedSanitizerDetector()
        func = MockFunction("escape", qualified_name="html.escape")

        sig = detector.detect(func)

        assert sig is not None
        assert sig.pattern == "html.escape"
        assert sig.sanitizer_type == "escape"
        assert sig.confidence == 1.0
        assert sig.source == "known_library"

    def test_detect_sqlalchemy_text(self):
        """Test detecting sqlalchemy.text"""
        detector = ImprovedSanitizerDetector()
        func = MockFunction("text", qualified_name="sqlalchemy.text")

        sig = detector.detect(func)

        assert sig is not None
        assert sig.pattern == "sqlalchemy.text"
        assert sig.sanitizer_type == "parameterize"
        assert sig.confidence == 1.0

    def test_detect_markupsafe_escape(self):
        """Test detecting markupsafe.escape"""
        detector = ImprovedSanitizerDetector()
        func = MockFunction("escape", qualified_name="markupsafe.escape")

        sig = detector.detect(func)

        assert sig is not None
        assert sig.sanitizer_type == "escape"
        assert sig.confidence == 1.0

    def test_detect_django_escape(self):
        """Test detecting Django utils"""
        detector = ImprovedSanitizerDetector()
        func = MockFunction("escape", qualified_name="django.utils.html.escape")

        sig = detector.detect(func)

        assert sig is not None
        assert sig.sanitizer_type == "escape"
        assert sig.confidence == 1.0

    def test_no_detection_for_unknown(self):
        """Test that unknown functions return None"""
        detector = ImprovedSanitizerDetector()
        func = MockFunction("random_func", qualified_name="my_module.random_func")

        sig = detector.detect(func)

        # Should fall through to heuristic, which won't match
        assert sig is None


class TestHeuristicDetection:
    """Test Tier 3: Heuristic detection"""

    def test_detect_escape_in_name(self):
        """Test detecting 'escape' in function name"""
        detector = ImprovedSanitizerDetector()
        func = MockFunction("custom_escape_html")

        sig = detector.detect(func)

        assert sig is not None
        assert sig.sanitizer_type == "escape"
        assert sig.source == "heuristic"
        assert sig.confidence <= 0.7  # Capped
        assert sig.confidence > 0.5  # But high enough

    def test_detect_sanitize_in_name(self):
        """Test detecting 'sanitize' in name"""
        detector = ImprovedSanitizerDetector()
        func = MockFunction("sanitize_input")

        sig = detector.detect(func)

        assert sig is not None
        assert sig.sanitizer_type == "escape"
        assert sig.source == "heuristic"

    def test_detect_validate_in_name(self):
        """Test detecting 'validate' in name"""
        detector = ImprovedSanitizerDetector()
        func = MockFunction("validate_email")

        sig = detector.detect(func)

        assert sig is not None
        assert sig.sanitizer_type == "validate"
        assert sig.source == "heuristic"

    def test_detect_encode_in_name(self):
        """Test detecting 'encode' in name"""
        detector = ImprovedSanitizerDetector()
        func = MockFunction("url_encode")

        sig = detector.detect(func)

        assert sig is not None
        assert sig.sanitizer_type == "encode"
        assert sig.source == "heuristic"

    def test_confidence_capped_at_07(self):
        """Test that heuristic confidence is capped at 0.7"""
        detector = ImprovedSanitizerDetector()
        func = MockFunction("super_escape_sanitize_clean")  # Multiple keywords

        sig = detector.detect(func)

        assert sig is not None
        assert sig.confidence <= 0.7  # Always capped


class TestPriorityOrder:
    """Test that detection follows priority order"""

    def test_known_library_wins_over_heuristic(self):
        """Test known library has higher priority"""
        detector = ImprovedSanitizerDetector()

        # Function matches both known library AND heuristic
        func = MockFunction("escape", qualified_name="html.escape")

        sig = detector.detect(func)

        # Should use known library, not heuristic
        assert sig.source == "known_library"
        assert sig.confidence == 1.0

    def test_heuristic_as_fallback(self):
        """Test heuristic is used when no known library matches"""
        detector = ImprovedSanitizerDetector()

        # Unknown module, but name suggests sanitizer
        func = MockFunction("sanitize", qualified_name="custom.sanitize")

        sig = detector.detect(func)

        # Should fall back to heuristic
        assert sig.source == "heuristic"
        assert sig.confidence <= 0.7


class TestConvenienceFunctions:
    """Test convenience functions"""

    def test_create_sanitizer_detector_no_config(self):
        """Test creating detector without config"""
        detector = create_sanitizer_detector()

        assert isinstance(detector, ImprovedSanitizerDetector)
        assert len(detector.user_sanitizers) == 0

    def test_create_sanitizer_detector_with_nonexistent_config(self):
        """Test with non-existent config path"""
        detector = create_sanitizer_detector("/nonexistent/config.yaml")

        # Should not crash, just have empty user_sanitizers
        assert len(detector.user_sanitizers) == 0


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_function_without_qualified_name(self):
        """Test function with only name (no qualified_name)"""
        detector = ImprovedSanitizerDetector()

        @dataclass
        class MinimalFunc:
            name: str

        func = MinimalFunc(name="escape_html")
        sig = detector.detect(func)

        # Should still work with heuristic
        assert sig is not None
        assert sig.source == "heuristic"

    def test_empty_function_name(self):
        """Test with empty function name"""
        detector = ImprovedSanitizerDetector()
        func = MockFunction("")

        sig = detector.detect(func)

        # Should return None (no match)
        assert sig is None

    def test_case_insensitive_heuristic(self):
        """Test that heuristic matching is case-insensitive"""
        detector = ImprovedSanitizerDetector()

        # Mixed case
        func1 = MockFunction("EscapeHTML")
        sig1 = detector.detect(func1)

        func2 = MockFunction("SANITIZE_input")
        sig2 = detector.detect(func2)

        assert sig1 is not None
        assert sig2 is not None


# Integration tests


class TestIntegration:
    """Integration tests"""

    def test_full_detection_flow(self):
        """Test complete detection flow"""
        detector = ImprovedSanitizerDetector()

        test_cases = [
            # (func, expected_source, expected_type)
            (
                MockFunction("escape", "html.escape"),
                "known_library",
                "escape",
            ),
            (
                MockFunction("text", "sqlalchemy.text"),
                "known_library",
                "parameterize",
            ),
            (
                MockFunction("custom_sanitize"),
                "heuristic",
                "escape",
            ),
            (
                MockFunction("validate_input"),
                "heuristic",
                "validate",
            ),
        ]

        for func, expected_source, expected_type in test_cases:
            sig = detector.detect(func)

            assert sig is not None, f"Failed to detect {func.name}"
            assert sig.source == expected_source
            assert sig.sanitizer_type == expected_type

    def test_statistics(self):
        """Test that detector maintains correct stats"""
        detector = ImprovedSanitizerDetector()

        # Count known sanitizers
        assert len(detector.KNOWN_SANITIZERS) > 20

        # Verify common ones are present
        assert "html.escape" in detector.KNOWN_SANITIZERS
        assert "sqlalchemy.text" in detector.KNOWN_SANITIZERS
        assert "markupsafe.escape" in detector.KNOWN_SANITIZERS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
