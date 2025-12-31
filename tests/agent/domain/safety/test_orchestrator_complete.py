"""
Complete Test Suite for SafetyOrchestrator

SOTA-Level Coverage:
- Base Cases: 정상 동작
- Edge Cases: 경계값, 빈 입력, None
- Corner Cases: 예외 조합
- Extreme Cases: 대용량, 타임아웃, 메모리

Test Pyramid:
- Unit Tests: 각 메서드 독립 테스트
- Integration Tests: Adapter 연동 테스트
- Contract Tests: Port 인터페이스 검증
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
from apps.orchestrator.orchestrator.ports.safety import ActionGatePort, LicenseCheckerPort, SecretScannerPort

# ============================================================================
# Mock Adapters for Unit Tests
# ============================================================================


class MockSecretScanner:
    """Mock SecretScanner for unit tests"""

    def __init__(self, should_find_secrets=False):
        self.should_find_secrets = should_find_secrets
        self.detect_called = 0
        self.scrub_called = 0

    def detect(self, text: str):
        self.detect_called += 1
        if self.should_find_secrets:
            from apps.orchestrator.orchestrator.domain.safety import DetectionResult, SecretType

            return [
                DetectionResult(
                    type=SecretType.API_KEY,
                    value="mock_secret",
                    start=0,
                    end=11,
                    confidence=0.9,
                )
            ]
        return []

    def scrub(self, text: str, min_confidence: float = 0.7, redaction_func=None):
        self.scrub_called += 1
        scrubbed = text.replace("secret", "[REDACTED]")
        return scrubbed, self.detect(text)

    def validate_clean(self, text: str, min_confidence: float = 0.7):
        detections = self.detect(text)
        return len(detections) == 0, detections

    def add_to_whitelist(self, *values: str):
        pass

    def add_to_blacklist(self, *values: str):
        pass


class MockLicenseChecker:
    """Mock LicenseChecker for unit tests"""

    def __init__(self, should_find_violations=False):
        self.should_find_violations = should_find_violations

    def detect_license(self, text: str, source: str | None = None):
        from apps.orchestrator.orchestrator.domain.safety import LicenseCategory, LicenseInfo, LicenseType

        return LicenseInfo(
            type=LicenseType.GPL_3 if self.should_find_violations else LicenseType.MIT,
            category=LicenseCategory.STRONG_COPYLEFT if self.should_find_violations else LicenseCategory.PERMISSIVE,
        )

    def check_compliance(self, license, package: str | None = None):
        if self.should_find_violations:
            from apps.orchestrator.orchestrator.domain.safety import LicenseViolation, PolicyAction

            return LicenseViolation(
                license=license,
                action=PolicyAction.BLOCK,
                reason="GPL blocked",
                package=package,
            )
        return None

    def check_compatibility(self, source_license: str, target_license: str):
        return not self.should_find_violations

    def scan_dependencies(self, dependencies: dict[str, str]):
        violations = []
        for pkg, text in dependencies.items():
            lic = self.detect_license(text, pkg)
            violation = self.check_compliance(lic, pkg)
            if violation:
                violations.append(violation)
        return violations


class MockActionGate:
    """Mock ActionGate for unit tests"""

    def __init__(self, should_approve=True):
        self.should_approve = should_approve

    def request_approval(self, action_type, target, description, context=None, request_id=None):
        from apps.orchestrator.orchestrator.domain.safety import ApprovalStatus

        if self.should_approve:
            return ApprovalStatus.AUTO_APPROVED, "Auto-approved"
        return ApprovalStatus.REJECTED, "Rejected"

    def approve(self, request_id: str, approver: str, reason: str | None = None):
        return self.should_approve

    def reject(self, request_id: str, approver: str, reason: str | None = None):
        return not self.should_approve

    def get_status(self, request_id: str):
        from apps.orchestrator.orchestrator.domain.safety import ApprovalStatus

        return ApprovalStatus.APPROVED if self.should_approve else ApprovalStatus.REJECTED

    def get_pending_requests(self):
        return []

    def cleanup_timeouts(self):
        return 0


# ============================================================================
# Contract Tests: Port Interface 검증
# ============================================================================


class TestPortContracts:
    """Test that Adapters correctly implement Ports"""

    def test_secret_scrubber_implements_port(self):
        """SecretScrubber must implement SecretScannerPort"""
        scrubber = SecretScrubberAdapter()
        assert isinstance(scrubber, SecretScannerPort), "SecretScrubber must implement SecretScannerPort"

    def test_license_checker_implements_port(self):
        """LicenseComplianceChecker must implement LicenseCheckerPort"""
        checker = LicenseComplianceCheckerAdapter()
        assert isinstance(checker, LicenseCheckerPort), "LicenseComplianceChecker must implement LicenseCheckerPort"

    def test_action_gate_implements_port(self):
        """DangerousActionGate must implement ActionGatePort"""
        gate = DangerousActionGateAdapter()
        assert isinstance(gate, ActionGatePort), "DangerousActionGate must implement ActionGatePort"

    def test_mock_scanners_implement_ports(self):
        """Mock adapters must also implement Ports"""
        mock_scanner = MockSecretScanner()
        mock_checker = MockLicenseChecker()
        mock_gate = MockActionGate()

        # Mocks should implement required methods (duck typing)
        assert hasattr(mock_scanner, "detect")
        assert hasattr(mock_scanner, "scrub")
        assert hasattr(mock_checker, "scan_dependencies")
        assert hasattr(mock_gate, "request_approval")


# ============================================================================
# Unit Tests: SafetyOrchestrator Initialization
# ============================================================================


class TestOrchestratorInitialization:
    """Test SafetyOrchestrator constructor validation"""

    def test_init_with_valid_adapters(self):
        """Should accept valid adapters"""
        orchestrator = SafetyOrchestrator(
            config=SafetyConfig(),
            secret_scanner=SecretScrubberAdapter(),
            license_checker=LicenseComplianceCheckerAdapter(),
            action_gate=DangerousActionGateAdapter(),
        )

        assert orchestrator.secret_scanner is not None
        assert orchestrator.license_checker is not None
        assert orchestrator.action_gate is not None

    def test_init_with_none_adapters(self):
        """Should accept None adapters when disabled"""
        config = SafetyConfig(
            enable_secret_scanning=False,
            enable_license_checking=False,
            enable_action_gating=False,
        )

        orchestrator = SafetyOrchestrator(config=config)

        assert orchestrator.secret_scanner is None
        assert orchestrator.license_checker is None
        assert orchestrator.action_gate is None

    def test_init_rejects_invalid_adapter(self):
        """Should reject adapters that don't implement Port"""

        class InvalidAdapter:
            pass

        with pytest.raises(TypeError, match="must implement SecretScannerPort"):
            SafetyOrchestrator(secret_scanner=InvalidAdapter())  # type: ignore

    def test_init_default_config(self):
        """Should use default config if not provided"""
        orchestrator = SafetyOrchestrator()

        assert orchestrator.config is not None
        assert orchestrator.config.enable_secret_scanning is True
        assert orchestrator.config.enable_license_checking is True
        assert orchestrator.config.enable_action_gating is True


# ============================================================================
# Base Cases: 정상 동작
# ============================================================================


class TestBaseCase:
    """Test normal operation"""

    @pytest.fixture
    def orchestrator(self):
        return SafetyOrchestrator(
            config=SafetyConfig(),
            secret_scanner=MockSecretScanner(should_find_secrets=False),
            license_checker=MockLicenseChecker(should_find_violations=False),
            action_gate=MockActionGate(should_approve=True),
        )

    def test_validate_clean_content(self, orchestrator):
        """Should pass validation for clean content"""
        result = orchestrator.validate_content("clean content")

        assert result.passed is True
        assert len(result.violations) == 0
        assert result.message == "Clean"

    def test_validate_compliant_licenses(self, orchestrator):
        """Should pass validation for compliant licenses"""
        dependencies = {"package": "MIT License"}
        result = orchestrator.validate_licenses(dependencies)

        assert result.passed is True

    def test_validate_safe_action(self, orchestrator):
        """Should approve safe actions"""
        result = orchestrator.validate_action(
            action_type=ActionType.FILE_WRITE,
            target="test.txt",
            description="Test",
        )

        assert result.passed is True


# ============================================================================
# Edge Cases: 경계값, 빈 입력
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    @pytest.fixture
    def orchestrator(self):
        return SafetyOrchestrator(
            config=SafetyConfig(),
            secret_scanner=MockSecretScanner(),
            license_checker=MockLicenseChecker(),
            action_gate=MockActionGate(),
        )

    def test_validate_empty_content(self, orchestrator):
        """Should handle empty content"""
        result = orchestrator.validate_content("")

        assert result.passed is True

    def test_validate_empty_dependencies(self, orchestrator):
        """Should handle empty dependencies dict"""
        result = orchestrator.validate_licenses({})

        assert result.passed is True

    def test_validate_none_context(self, orchestrator):
        """Should handle None in ValidationContext"""
        ctx = ValidationContext()  # All fields None

        results = orchestrator.validate_pipeline(ctx)

        # Should return empty list (no stages executed)
        assert isinstance(results, list)

    def test_validate_very_long_content(self, orchestrator):
        """Should handle extremely long content (10MB)"""
        large_content = "A" * (10 * 1024 * 1024)  # 10MB

        result = orchestrator.validate_content(large_content)

        assert result.passed is True

    def test_validate_special_characters(self, orchestrator):
        """Should handle special characters"""
        special_text = "!@#$%^&*()_+-=[]{}|;':\",./<>?\n\t\r"
        result = orchestrator.validate_content(special_text)

        assert result.passed is True


# ============================================================================
# Corner Cases: 예외 조합
# ============================================================================


class TestCornerCases:
    """Test corner cases and unusual combinations"""

    def test_strict_mode_fails_on_any_violation(self):
        """Strict mode should fail on ANY violation"""
        config = SafetyConfig(strict_mode=True)
        orchestrator = SafetyOrchestrator(
            config=config,
            secret_scanner=MockSecretScanner(should_find_secrets=True),
            license_checker=MockLicenseChecker(should_find_violations=True),  # Make this fail
            action_gate=MockActionGate(should_approve=True),
        )

        ctx = ValidationContext(
            content="content with secret",
            dependencies={"pkg": "GPL License"},  # This will fail
        )

        results = orchestrator.validate_pipeline(ctx)

        # In strict mode, should stop at first failure
        # Note: MockSecretScanner auto-scrubs, so first stage passes
        # Second stage (license) should fail and stop
        assert len(results) == 2
        assert not results[1].passed  # License check failed

    def test_disabled_stages_skip_validation(self):
        """Disabled stages should be skipped"""
        config = SafetyConfig(
            enable_secret_scanning=False,
            enable_license_checking=True,
            enable_action_gating=False,
        )

        orchestrator = SafetyOrchestrator(
            config=config,
            license_checker=MockLicenseChecker(),
        )

        ctx = ValidationContext(
            content="test",
            dependencies={"pkg": "MIT"},
            action_type=ActionType.FILE_WRITE,
        )

        results = orchestrator.validate_pipeline(ctx)

        # Only license check should run
        assert len(results) == 1

    def test_metrics_tracking(self):
        """Metrics should track all validations"""
        orchestrator = SafetyOrchestrator(
            secret_scanner=MockSecretScanner(should_find_secrets=True),
            license_checker=MockLicenseChecker(should_find_violations=True),
            action_gate=MockActionGate(should_approve=False),
        )

        orchestrator.validate_content("test")
        orchestrator.validate_licenses({"pkg": "GPL"})
        orchestrator.validate_action(ActionType.FILE_DELETE, "test.py", "Delete")

        metrics = orchestrator.get_metrics()

        assert metrics["total_validations"] == 3
        assert metrics["secrets_detected"] > 0
        assert metrics["license_violations"] > 0
        assert metrics["actions_blocked"] > 0


# ============================================================================
# Extreme Cases: 성능, 메모리, 동시성
# ============================================================================


class TestExtremeCases:
    """Test extreme scenarios"""

    def test_many_violations(self):
        """Should handle hundreds of violations"""
        orchestrator = SafetyOrchestrator(
            license_checker=MockLicenseChecker(should_find_violations=True),
        )

        # 1000 dependencies
        dependencies = {f"package-{i}": "GPL License" for i in range(1000)}

        result = orchestrator.validate_licenses(dependencies)

        assert result.passed is False
        assert len(result.violations) == 1000

    def test_reset_metrics(self):
        """Metrics should reset properly"""
        orchestrator = SafetyOrchestrator(
            secret_scanner=MockSecretScanner(should_find_secrets=True),
        )

        orchestrator.validate_content("test")
        metrics_before = orchestrator.get_metrics()
        assert metrics_before["total_validations"] > 0

        orchestrator.reset_metrics()
        metrics_after = orchestrator.get_metrics()

        assert metrics_after["total_validations"] == 0
        assert metrics_after["secrets_detected"] == 0

    def test_is_safe_with_mixed_results(self):
        """is_safe() should require ALL validations to pass"""
        from apps.orchestrator.orchestrator.domain.safety import ValidationResult, ValidationStage

        results = [
            ValidationResult(passed=True, stage=ValidationStage.SECRET_SCAN),
            ValidationResult(passed=False, stage=ValidationStage.LICENSE_CHECK),
            ValidationResult(passed=True, stage=ValidationStage.ACTION_GATE),
        ]

        orchestrator = SafetyOrchestrator()

        assert orchestrator.is_safe(results) is False

    def test_is_safe_with_all_pass(self):
        """is_safe() should return True if all pass"""
        from apps.orchestrator.orchestrator.domain.safety import ValidationResult, ValidationStage

        results = [
            ValidationResult(passed=True, stage=ValidationStage.SECRET_SCAN),
            ValidationResult(passed=True, stage=ValidationStage.LICENSE_CHECK),
        ]

        orchestrator = SafetyOrchestrator()

        assert orchestrator.is_safe(results) is True


# ============================================================================
# Integration Tests with Real Adapters
# ============================================================================


class TestIntegrationWithRealAdapters:
    """Test with real adapters (not mocks)"""

    @pytest.fixture
    def real_orchestrator(self):
        return SafetyOrchestrator(
            config=SafetyConfig(),
            secret_scanner=SecretScrubberAdapter(ScrubberConfig()),
            license_checker=LicenseComplianceCheckerAdapter(LicensePolicy()),
            action_gate=DangerousActionGateAdapter(GateConfig()),
        )

    def test_real_secret_detection(self, real_orchestrator):
        """Should detect real AWS keys"""
        content = "AWS_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE"

        result = real_orchestrator.validate_content(content, auto_scrub=False)

        assert result.passed is False
        assert len(result.violations) > 0

    def test_real_license_violation(self, real_orchestrator):
        """Should detect GPL license"""
        dependencies = {"bad-package": "GNU GENERAL PUBLIC LICENSE Version 3"}

        result = real_orchestrator.validate_licenses(dependencies)

        assert result.passed is False

    def test_real_dangerous_action(self, real_orchestrator):
        """Should block dangerous commands"""
        result = real_orchestrator.validate_action(
            action_type=ActionType.SHELL_COMMAND,
            target="rm -rf /",
            description="Delete everything",
        )

        assert result.passed is False

    def test_end_to_end_pipeline(self, real_orchestrator):
        """Full pipeline with real adapters"""
        ctx = ValidationContext(
            content="This is clean code",
            dependencies={"package": "MIT License"},
            action_type=ActionType.FILE_WRITE,
            file_path="test.txt",  # .txt is LOW risk -> AUTO_APPROVED
            metadata={"description": "Test write"},
        )

        results = real_orchestrator.validate_pipeline(ctx)

        assert len(results) == 3
        assert real_orchestrator.is_safe(results) is True
