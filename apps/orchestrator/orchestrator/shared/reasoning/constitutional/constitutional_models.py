"""
Constitutional AI Models

규칙 기반 검증을 위한 데이터 모델.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RuleSeverity(str, Enum):
    """규칙 위반 심각도"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class RuleViolation:
    """규칙 위반"""

    rule_id: str
    rule_name: str
    severity: RuleSeverity

    # Violation details
    description: str
    location: str = ""  # 위반 위치

    # Suggested fix
    suggested_fix: str = ""


@dataclass
class ConstitutionalConfig:
    """Constitutional AI 설정"""

    # Enforcement
    enforce_critical: bool = True  # CRITICAL 위반 시 차단
    enforce_errors: bool = True  # ERROR 위반 시 차단

    # Revision
    auto_revise: bool = True  # 자동 수정 시도
    max_revision_attempts: int = 3


@dataclass
class ConstitutionalResult:
    """Constitutional AI 결과"""

    # Original content
    original_content: str

    # Violations
    violations: list[RuleViolation] = field(default_factory=list)

    # Revised content
    revised_content: str = ""
    revision_attempted: bool = False

    # Status
    is_safe: bool = True
    is_compliant: bool = True

    # Metrics
    total_violations: int = 0
    critical_violations: int = 0
    revision_attempts: int = 0

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)

    def has_blocking_violations(self) -> bool:
        """
        차단 위반이 있는지

        Returns:
            차단 위반 여부
        """
        return any(v.severity in [RuleSeverity.CRITICAL, RuleSeverity.ERROR] for v in self.violations)
