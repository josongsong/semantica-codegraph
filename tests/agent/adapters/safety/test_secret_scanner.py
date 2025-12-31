"""
Unit Tests for SecretScrubber Adapter

Tests adapter implementation of SecretScannerPort.
"""

import pytest

from apps.orchestrator.orchestrator.adapters.safety import SecretScrubberAdapter
from apps.orchestrator.orchestrator.domain.safety import ScrubberConfig, SecretType


class TestSecretScrubber:
    """Test SecretScrubber adapter"""

    @pytest.fixture
    def scrubber(self):
        return SecretScrubberAdapter(ScrubberConfig())

    def test_detect_aws_key(self, scrubber):
        text = "AWS Key: AKIAIOSFODNN7EXAMPLE"
        detections = scrubber.detect(text)

        assert len(detections) > 0
        assert any(d.type == SecretType.AWS_KEY for d in detections)

    def test_detect_github_token(self, scrubber):
        text = "Token: ghp_1234567890abcdefghijklmnopqrst"
        detections = scrubber.detect(text)

        assert len(detections) > 0
        assert any(d.type == SecretType.GITHUB_TOKEN for d in detections)

    def test_detect_jwt(self, scrubber):
        # JWT must match pattern: eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}
        text = "JWT: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        detections = scrubber.detect(text)

        assert len(detections) > 0
        assert any(d.type == SecretType.JWT for d in detections)

    def test_scrub_secrets(self, scrubber):
        text = "My API key is AKIAIOSFODNN7EXAMPLE"
        scrubbed, detections = scrubber.scrub(text)

        assert len(detections) > 0
        assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed
        assert "[REDACTED_" in scrubbed

    def test_whitelist(self, scrubber):
        scrubber.add_to_whitelist("AKIAIOSFODNN7EXAMPLE")
        text = "AWS Key: AKIAIOSFODNN7EXAMPLE"
        detections = scrubber.detect(text)

        # Whitelisted value should not be detected
        assert len([d for d in detections if d.value == "AKIAIOSFODNN7EXAMPLE"]) == 0

    def test_validate_clean_text(self, scrubber):
        text = "This is a clean text without secrets"
        is_clean, violations = scrubber.validate_clean(text)

        assert is_clean is True
        assert len(violations) == 0

    def test_validate_dirty_text(self, scrubber):
        text = "Secret: AKIAIOSFODNN7EXAMPLE"
        is_clean, violations = scrubber.validate_clean(text)

        assert is_clean is False
        assert len(violations) > 0
