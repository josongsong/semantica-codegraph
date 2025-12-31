"""
Safety Policies

Domain policy configurations for security & compliance.
SOLID: Open/Closed - policies are open for extension, closed for modification.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .models import LicenseType

# ============================================================================
# Secret Scrubber Policy
# ============================================================================


class ScrubberConfig(BaseModel):
    """
    Configuration for secret scrubber.

    Controls detection algorithms and redaction behavior.
    """

    enable_pattern_detection: bool = True
    enable_entropy_detection: bool = True
    enable_pii_detection: bool = True
    entropy_threshold: float = 4.5
    min_secret_length: int = 8
    redaction_char: str = "*"
    whitelist: list[str] = Field(default_factory=list)
    blacklist: list[str] = Field(default_factory=list)
    custom_patterns: dict[str, str] = Field(default_factory=dict)

    @field_validator("entropy_threshold")
    @classmethod
    def validate_entropy_threshold(cls, v: float) -> float:
        if v < 0 or v > 8:
            raise ValueError("entropy_threshold must be between 0 and 8")
        return v

    @field_validator("min_secret_length")
    @classmethod
    def validate_min_secret_length(cls, v: int) -> int:
        if v < 1:
            raise ValueError("min_secret_length must be positive")
        return v


# ============================================================================
# License Compliance Policy
# ============================================================================


class LicensePolicy(BaseModel):
    """
    License compliance policy.

    Defines which licenses are allowed, require review, or are blocked.
    Default policy: Permissive licenses allowed, Copyleft blocked.
    """

    # Allowed licenses (auto-pass)
    allowed: list[LicenseType] = Field(
        default_factory=lambda: [
            LicenseType.MIT,
            LicenseType.APACHE_2,
            LicenseType.BSD_2,
            LicenseType.BSD_3,
            LicenseType.ISC,
        ]
    )

    # Licenses requiring manual review
    review_required: list[LicenseType] = Field(
        default_factory=lambda: [
            LicenseType.LGPL_2,
            LicenseType.LGPL_3,
            LicenseType.MPL_2,
        ]
    )

    # Blocked licenses (viral copyleft)
    blocked: list[LicenseType] = Field(
        default_factory=lambda: [
            LicenseType.GPL_2,
            LicenseType.GPL_3,
            LicenseType.AGPL_3,  # Network copyleft - extremely viral
        ]
    )

    # Block unknown licenses
    block_unknown: bool = False

    # Require all dependencies to have detected license
    require_license: bool = True


class LicenseCompatibility(BaseModel):
    """
    License compatibility matrix.

    Defines which licenses can be combined in the same project.
    Based on FSF compatibility guidelines.
    """

    # Compatibility rules: source_license -> [compatible_target_licenses]
    compatibility: dict[LicenseType, list[LicenseType]] = Field(
        default_factory=lambda: {
            # Permissive licenses: compatible with everything
            LicenseType.MIT: list(LicenseType),
            LicenseType.APACHE_2: list(LicenseType),
            LicenseType.BSD_2: list(LicenseType),
            LicenseType.BSD_3: list(LicenseType),
            LicenseType.ISC: list(LicenseType),
            # GPL: only compatible with GPL/AGPL (viral)
            LicenseType.GPL_2: [LicenseType.GPL_2, LicenseType.GPL_3],
            LicenseType.GPL_3: [LicenseType.GPL_3, LicenseType.AGPL_3],
            # LGPL: compatible with GPL/AGPL
            LicenseType.LGPL_2: [
                LicenseType.LGPL_2,
                LicenseType.LGPL_3,
                LicenseType.GPL_2,
                LicenseType.GPL_3,
            ],
            LicenseType.LGPL_3: [
                LicenseType.LGPL_3,
                LicenseType.GPL_3,
                LicenseType.AGPL_3,
            ],
            # AGPL: only with AGPL (most viral)
            LicenseType.AGPL_3: [LicenseType.AGPL_3],
        }
    )


# ============================================================================
# Action Gate Policy
# ============================================================================


class GateConfig(BaseModel):
    """
    Configuration for dangerous action gate.

    Controls auto-approval rules and timeout settings.
    """

    # Auto-approval rules
    auto_approve_low_risk: bool = True
    auto_approve_medium_risk: bool = False

    # Timeout settings
    default_timeout_seconds: int = 300  # 5 minutes
    critical_timeout_seconds: int = 600  # 10 minutes for critical actions

    # Whitelist patterns (regex)
    file_write_whitelist: list[str] = Field(default_factory=list)
    command_whitelist: list[str] = Field(default_factory=list)
    domain_whitelist: list[str] = Field(default_factory=list)

    @field_validator("default_timeout_seconds", "critical_timeout_seconds")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v < 0:
            raise ValueError("timeout must be non-negative")
        if v > 86400:  # 1 day
            raise ValueError("timeout must be less than 1 day")
        return v

    # Blacklist patterns (glob for files, substring for commands)
    file_delete_blacklist: list[str] = Field(
        default_factory=lambda: [
            "*.db",
            "*.sql",
            ".git/*",
            ".env",
        ]
    )
    command_blacklist: list[str] = Field(
        default_factory=lambda: [
            "rm -rf /",
            "dd if=",
            "mkfs",
            "format",
        ]
    )

    # Enable audit trail
    enable_audit: bool = True


# ============================================================================
# Safety Orchestrator Policy
# ============================================================================


class SafetyConfig(BaseModel):
    """
    Combined safety configuration for orchestrator.

    Aggregates all sub-policies and controls pipeline behavior.
    """

    scrubber_config: ScrubberConfig = Field(default_factory=ScrubberConfig)
    license_policy: LicensePolicy = Field(default_factory=LicensePolicy)
    gate_config: GateConfig = Field(default_factory=GateConfig)

    # Pipeline settings
    enable_secret_scanning: bool = True
    enable_license_checking: bool = True
    enable_action_gating: bool = True

    # Strict mode: reject on ANY violation (not just blocked ones)
    strict_mode: bool = False
