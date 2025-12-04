"""Approval Policy - Risk-based approval classification."""

from dataclasses import dataclass
from enum import Enum

from src.infra.observability import get_logger

logger = get_logger(__name__)


class RiskLevel(str, Enum):
    """Risk level for code changes."""

    LOW = "low"  # Auto-approve
    MEDIUM = "medium"  # Auto-approve with notification
    HIGH = "high"  # Require approval
    CRITICAL = "critical"  # Require approval + extra validation


@dataclass
class ApprovalRequired:
    """Approval requirement for a change."""

    required: bool
    risk_level: RiskLevel
    reasons: list[str]
    auto_approve: bool


class ApprovalPolicy:
    """Determines if human approval is needed for code changes.

    Risk factors:
    - File path (critical files like migrations, config)
    - Change size (large diffs)
    - Destructive operations (deletions, db changes)
    - Test coverage (changes without tests)
    """

    def __init__(
        self,
        critical_paths: list[str] | None = None,
        auto_approve_threshold_lines: int = 50,
        require_tests: bool = True,
    ):
        """Initialize approval policy.

        Args:
            critical_paths: Paths requiring approval (glob patterns)
            auto_approve_threshold_lines: Max lines for auto-approval
            require_tests: Require test changes for auto-approval
        """
        self.critical_paths = critical_paths or [
            "migrations/**",
            "infra/**",
            "docker-compose.yml",
            ".env*",
            "pyproject.toml",
        ]
        self.auto_approve_threshold = auto_approve_threshold_lines
        self.require_tests = require_tests

    def evaluate(
        self,
        file_path: str,
        diff_lines: int,
        is_deletion: bool = False,
        has_tests: bool = False,
        metadata: dict | None = None,
    ) -> ApprovalRequired:
        """Evaluate if approval is required.

        Args:
            file_path: File being changed
            diff_lines: Number of changed lines
            is_deletion: If file is being deleted
            has_tests: If test changes are included
            metadata: Additional metadata

        Returns:
            ApprovalRequired
        """
        reasons = []
        risk_level = RiskLevel.LOW

        # Check critical paths
        if self._is_critical_path(file_path):
            reasons.append(f"Critical file: {file_path}")
            risk_level = RiskLevel.HIGH

        # Check change size
        if diff_lines > self.auto_approve_threshold:
            reasons.append(f"Large change: {diff_lines} lines")
            risk_level = max(risk_level, RiskLevel.MEDIUM, key=lambda x: list(RiskLevel).index(x))

        # Check deletion
        if is_deletion:
            reasons.append("File deletion")
            risk_level = max(risk_level, RiskLevel.HIGH, key=lambda x: list(RiskLevel).index(x))

        # Check test coverage
        if self.require_tests and not has_tests and diff_lines > 10:
            reasons.append("No test changes included")
            risk_level = max(risk_level, RiskLevel.MEDIUM, key=lambda x: list(RiskLevel).index(x))

        # Database migrations are critical
        if "migration" in file_path.lower() or file_path.endswith(".sql"):
            reasons.append("Database migration")
            risk_level = RiskLevel.CRITICAL

        # Determine if approval required
        required = risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        auto_approve = not required

        logger.info(
            "approval_policy_evaluated",
            file_path=file_path,
            risk_level=risk_level.value,
            required=required,
            reasons=reasons,
        )

        return ApprovalRequired(
            required=required,
            risk_level=risk_level,
            reasons=reasons,
            auto_approve=auto_approve,
        )

    def _is_critical_path(self, file_path: str) -> bool:
        """Check if file path matches critical patterns.

        Args:
            file_path: File path to check

        Returns:
            True if critical
        """
        from fnmatch import fnmatch

        for pattern in self.critical_paths:
            if fnmatch(file_path, pattern):
                return True

        return False
