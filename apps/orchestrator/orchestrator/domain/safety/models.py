"""
Safety Domain Models

Pure domain models without infrastructure dependencies.
SOLID: Single Responsibility - each model represents one domain concept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ============================================================================
# Enums (Domain Vocabulary)
# ============================================================================


class SecretType(str, Enum):
    """Types of secrets detected"""

    API_KEY = "api_key"
    PASSWORD = "password"
    TOKEN = "token"
    PRIVATE_KEY = "private_key"
    AWS_KEY = "aws_key"
    GITHUB_TOKEN = "github_token"
    SLACK_TOKEN = "slack_token"
    JWT = "jwt"
    DATABASE_URL = "database_url"
    CREDIT_CARD = "credit_card"
    SSN = "ssn"
    EMAIL = "email"
    PHONE = "phone"
    IP_ADDRESS = "ip_address"
    HIGH_ENTROPY = "high_entropy"
    CUSTOM = "custom"


class PIIType(str, Enum):
    """Types of PII (Personally Identifiable Information) detected"""

    NAME = "name"
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    ADDRESS = "address"
    DOB = "date_of_birth"
    IP_ADDRESS = "ip_address"


class LicenseType(str, Enum):
    """Common open source license types (SPDX identifiers)"""

    MIT = "MIT"
    APACHE_2 = "Apache-2.0"
    BSD_2 = "BSD-2-Clause"
    BSD_3 = "BSD-3-Clause"
    GPL_2 = "GPL-2.0"
    GPL_3 = "GPL-3.0"
    LGPL_2 = "LGPL-2.1"
    LGPL_3 = "LGPL-3.0"
    AGPL_3 = "AGPL-3.0"
    MPL_2 = "MPL-2.0"
    EPL_2 = "EPL-2.0"
    ISC = "ISC"
    UNLICENSE = "Unlicense"
    PROPRIETARY = "Proprietary"
    UNKNOWN = "Unknown"


class LicenseCategory(str, Enum):
    """License categories by restrictions level"""

    PERMISSIVE = "permissive"  # MIT, Apache, BSD
    WEAK_COPYLEFT = "weak_copyleft"  # LGPL, MPL
    STRONG_COPYLEFT = "strong_copyleft"  # GPL
    NETWORK_COPYLEFT = "network_copyleft"  # AGPL (viral over network)
    PROPRIETARY = "proprietary"
    UNKNOWN = "unknown"


class PolicyAction(str, Enum):
    """Policy enforcement actions"""

    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"
    REQUIRE_REVIEW = "require_review"


class RiskLevel(str, Enum):
    """Risk levels for dangerous actions"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionType(str, Enum):
    """Types of potentially dangerous actions"""

    FILE_DELETE = "file_delete"
    FILE_WRITE = "file_write"
    FILE_EXECUTE = "file_execute"
    NETWORK_REQUEST = "network_request"
    DATABASE_WRITE = "database_write"
    DATABASE_DELETE = "database_delete"
    SHELL_COMMAND = "shell_command"
    CODE_GENERATION = "code_generation"
    DEPENDENCY_INSTALL = "dependency_install"
    CREDENTIAL_ACCESS = "credential_access"
    SYSTEM_CONFIG = "system_config"


class ApprovalStatus(str, Enum):
    """Approval status for dangerous actions"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    AUTO_APPROVED = "auto_approved"


class ValidationStage(str, Enum):
    """Multi-stage validation pipeline stages"""

    SECRET_SCAN = "secret_scan"
    LICENSE_CHECK = "license_check"
    ACTION_GATE = "action_gate"


# ============================================================================
# Value Objects (Immutable Domain Data)
# ============================================================================


class DetectionResult(BaseModel):
    """
    Result of secret/PII detection.

    Immutable value object representing a detected secret or PII.
    """

    type: SecretType | PIIType
    value: str
    start: int
    end: int
    confidence: float = Field(ge=0.0, le=1.0)
    pattern_name: str | None = None
    entropy: float | None = None

    class Config:
        frozen = True  # Immutable


@dataclass(frozen=True)
class LicenseInfo:
    """
    License information detected from code/dependencies.

    Immutable value object.
    """

    type: LicenseType
    category: LicenseCategory
    text: str | None = None
    source: str | None = None  # File path or package name
    confidence: float = 1.0


class LicenseViolation(BaseModel):
    """
    License policy violation.

    Contains the violation details and required action.
    """

    license: LicenseInfo
    action: PolicyAction
    reason: str
    package: str | None = None

    class Config:
        frozen = True


@dataclass
class ActionRequest:
    """
    Request for executing a potentially dangerous action.

    Mutable entity that tracks approval workflow state.
    """

    id: str
    action_type: ActionType
    description: str
    risk_level: RiskLevel
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    timeout_seconds: int = 300  # 5 minutes default


class ApprovalRecord(BaseModel):
    """
    Record of approval decision.

    Immutable audit log entry.
    """

    request_id: str
    status: ApprovalStatus
    approver: str | None = None
    reason: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    auto_approved_by_rule: str | None = None

    class Config:
        frozen = True


class ValidationResult(BaseModel):
    """
    Result of a validation stage.

    Contains pass/fail status and violations found.
    """

    passed: bool
    stage: ValidationStage
    violations: list[Any] = Field(default_factory=list)
    scrubbed_content: str | None = None
    message: str | None = None


@dataclass
class ValidationContext:
    """
    Context for multi-stage validation pipeline.

    Contains all inputs needed for validation stages.
    """

    content: str | None = None
    file_path: str | None = None
    action_type: ActionType | None = None
    dependencies: dict[str, str] | None = None  # {package: license_text}
    metadata: dict[str, Any] | None = None
