"""
Unit Tests for Safety Domain Models

Tests pure domain logic without infrastructure dependencies.
"""

import pytest

from apps.orchestrator.orchestrator.domain.safety.models import (
    ActionRequest,
    ActionType,
    ApprovalStatus,
    DetectionResult,
    LicenseCategory,
    LicenseInfo,
    LicenseType,
    LicenseViolation,
    PolicyAction,
    RiskLevel,
    SecretType,
    ValidationContext,
    ValidationResult,
    ValidationStage,
)


class TestEnums:
    """Test domain enums"""

    def test_secret_type_values(self):
        assert SecretType.API_KEY.value == "api_key"
        assert SecretType.AWS_KEY.value == "aws_key"
        assert SecretType.GITHUB_TOKEN.value == "github_token"

    def test_license_type_values(self):
        assert LicenseType.MIT.value == "MIT"
        assert LicenseType.GPL_3.value == "GPL-3.0"
        assert LicenseType.AGPL_3.value == "AGPL-3.0"

    def test_action_type_values(self):
        assert ActionType.FILE_DELETE.value == "file_delete"
        assert ActionType.SHELL_COMMAND.value == "shell_command"

    def test_risk_level_values(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.CRITICAL.value == "critical"


class TestDetectionResult:
    """Test DetectionResult value object"""

    def test_detection_result_creation(self):
        result = DetectionResult(
            type=SecretType.API_KEY,
            value="sk_test_12345",
            start=0,
            end=13,
            confidence=0.9,
            pattern_name="API Key Pattern",
        )

        assert result.type == SecretType.API_KEY
        assert result.value == "sk_test_12345"
        assert result.confidence == 0.9
        assert result.pattern_name == "API Key Pattern"

    def test_detection_result_immutable(self):
        """Value objects should be immutable"""
        result = DetectionResult(
            type=SecretType.API_KEY,
            value="sk_test_12345",
            start=0,
            end=13,
            confidence=0.9,
        )

        # Pydantic frozen model
        with pytest.raises(Exception):  # ValidationError or similar
            result.confidence = 0.5

    def test_confidence_validation(self):
        """Confidence must be between 0 and 1"""
        with pytest.raises(Exception):  # Pydantic validation error
            DetectionResult(
                type=SecretType.API_KEY,
                value="test",
                start=0,
                end=4,
                confidence=1.5,  # Invalid
            )


class TestLicenseInfo:
    """Test LicenseInfo value object"""

    def test_license_info_creation(self):
        info = LicenseInfo(
            type=LicenseType.MIT,
            category=LicenseCategory.PERMISSIVE,
            text="MIT License...",
            source="package.json",
            confidence=1.0,
        )

        assert info.type == LicenseType.MIT
        assert info.category == LicenseCategory.PERMISSIVE
        assert info.confidence == 1.0

    def test_license_info_defaults(self):
        info = LicenseInfo(
            type=LicenseType.GPL_3,
            category=LicenseCategory.STRONG_COPYLEFT,
        )

        assert info.text is None
        assert info.source is None
        assert info.confidence == 1.0


class TestLicenseViolation:
    """Test LicenseViolation value object"""

    def test_violation_creation(self):
        license_info = LicenseInfo(
            type=LicenseType.GPL_3,
            category=LicenseCategory.STRONG_COPYLEFT,
        )

        violation = LicenseViolation(
            license=license_info,
            action=PolicyAction.BLOCK,
            reason="GPL-3.0 is blocked by policy",
            package="some-package",
        )

        assert violation.action == PolicyAction.BLOCK
        assert violation.package == "some-package"
        assert "GPL" in violation.reason


class TestActionRequest:
    """Test ActionRequest entity"""

    def test_action_request_creation(self):
        request = ActionRequest(
            id="test-123",
            action_type=ActionType.FILE_DELETE,
            description="Delete test file",
            risk_level=RiskLevel.HIGH,
            context={"target": "test.py"},
        )

        assert request.id == "test-123"
        assert request.action_type == ActionType.FILE_DELETE
        assert request.risk_level == RiskLevel.HIGH
        assert request.context["target"] == "test.py"

    def test_action_request_defaults(self):
        request = ActionRequest(
            id="test-123",
            action_type=ActionType.FILE_WRITE,
            description="Write file",
            risk_level=RiskLevel.LOW,
        )

        assert request.context == {}
        assert request.timeout_seconds == 300
        assert request.timestamp is not None


class TestValidationContext:
    """Test ValidationContext"""

    def test_validation_context_all_fields(self):
        ctx = ValidationContext(
            content="test content",
            file_path="test.py",
            action_type=ActionType.FILE_WRITE,
            dependencies={"package": "MIT License"},
            metadata={"user": "test"},
        )

        assert ctx.content == "test content"
        assert ctx.file_path == "test.py"
        assert ctx.action_type == ActionType.FILE_WRITE
        assert "package" in ctx.dependencies
        assert ctx.metadata["user"] == "test"

    def test_validation_context_defaults(self):
        ctx = ValidationContext()

        assert ctx.content is None
        assert ctx.file_path is None
        assert ctx.action_type is None
        assert ctx.dependencies is None
        assert ctx.metadata is None


class TestValidationResult:
    """Test ValidationResult"""

    def test_validation_result_passed(self):
        result = ValidationResult(
            passed=True,
            stage=ValidationStage.SECRET_SCAN,
            message="Clean",
        )

        assert result.passed is True
        assert result.stage == ValidationStage.SECRET_SCAN
        assert result.message == "Clean"
        assert result.violations == []
        assert result.scrubbed_content is None

    def test_validation_result_failed(self):
        result = ValidationResult(
            passed=False,
            stage=ValidationStage.LICENSE_CHECK,
            violations=[{"license": "GPL-3.0", "action": "block"}],
            message="License violation",
        )

        assert result.passed is False
        assert len(result.violations) == 1
        assert "GPL" in result.violations[0]["license"]
