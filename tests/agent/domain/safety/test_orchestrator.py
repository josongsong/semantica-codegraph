"""
Integration Tests for SafetyOrchestrator

Tests domain service with real adapters.
"""

import pytest

from apps.orchestrator.orchestrator.adapters.safety import (
    DangerousActionGateAdapter,
    LicenseComplianceCheckerAdapter,
    SecretScrubberAdapter,
)
from apps.orchestrator.orchestrator.domain.safety import (
    ActionType,
    GateConfig,
    LicensePolicy,
    SafetyConfig,
    SafetyOrchestrator,
    ScrubberConfig,
    ValidationContext,
)


class TestSafetyOrchestrator:
    """Test SafetyOrchestrator with real adapters"""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with real adapters"""
        config = SafetyConfig(
            enable_secret_scanning=True,
            enable_license_checking=True,
            enable_action_gating=True,
        )

        return SafetyOrchestrator(
            config=config,
            secret_scanner=SecretScrubberAdapter(ScrubberConfig()),
            license_checker=LicenseComplianceCheckerAdapter(LicensePolicy()),
            action_gate=DangerousActionGateAdapter(GateConfig()),
        )

    def test_validate_content_clean(self, orchestrator):
        result = orchestrator.validate_content("This is clean content")

        assert result.passed is True
        assert len(result.violations) == 0

    def test_validate_content_with_secret(self, orchestrator):
        result = orchestrator.validate_content(
            "AWS Key: AKIAIOSFODNN7EXAMPLE",
            auto_scrub=False,
        )

        assert result.passed is False
        assert len(result.violations) > 0

    def test_validate_content_auto_scrub(self, orchestrator):
        result = orchestrator.validate_content(
            "AWS Key: AKIAIOSFODNN7EXAMPLE",
            auto_scrub=True,
        )

        # Auto-scrub should pass
        assert result.passed is True
        assert result.scrubbed_content is not None
        assert "AKIAIOSFODNN7EXAMPLE" not in result.scrubbed_content

    def test_validate_licenses_allowed(self, orchestrator):
        dependencies = {
            "package1": "MIT License",
            "package2": "Apache License Version 2.0",
        }

        result = orchestrator.validate_licenses(dependencies)

        assert result.passed is True

    def test_validate_licenses_blocked(self, orchestrator):
        dependencies = {
            "package1": "GNU GENERAL PUBLIC LICENSE Version 3",
        }

        result = orchestrator.validate_licenses(dependencies)

        assert result.passed is False
        assert len(result.violations) > 0

    def test_validate_action_low_risk(self, orchestrator):
        result = orchestrator.validate_action(
            action_type=ActionType.FILE_WRITE,
            target="test.txt",
            description="Write test file",
        )

        # Low risk should auto-approve
        assert result.passed is True

    def test_validate_action_critical_risk(self, orchestrator):
        result = orchestrator.validate_action(
            action_type=ActionType.SHELL_COMMAND,
            target="rm -rf /",
            description="Delete root",
        )

        # Critical risk should be rejected
        assert result.passed is False

    def test_validate_pipeline_all_stages(self, orchestrator):
        ctx = ValidationContext(
            content="Clean content",
            dependencies={"package": "MIT License"},
            action_type=ActionType.FILE_WRITE,
            file_path="test.txt",  # .txt is LOW risk -> AUTO_APPROVED
            metadata={"description": "Test action"},
        )

        results = orchestrator.validate_pipeline(ctx)

        # Should have 3 stages
        assert len(results) == 3
        assert all(r.passed for r in results)

    def test_is_safe(self, orchestrator):
        ctx = ValidationContext(content="Clean content")
        results = orchestrator.validate_pipeline(ctx)

        assert orchestrator.is_safe(results) is True

    def test_metrics(self, orchestrator):
        orchestrator.validate_content("test")
        metrics = orchestrator.get_metrics()

        assert metrics["total_validations"] > 0
