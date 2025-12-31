"""
Control Configuration Domain Models

Project-level rule management (semantica.toml).
Immutable value objects with strict validation.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class RuleControl(BaseModel):
    """
    Rule control configuration.

    Controls which policies are enabled/disabled
    and severity overrides.

    Example:
        ```toml
        [rules]
        enabled = ["sql-injection", "xss"]
        disabled = ["debug-info"]
        severity_override = { "sql-injection" = "high" }
        ```
    """

    enabled: list[str] = Field(
        default_factory=list,
        description="Enabled policy IDs",
    )

    disabled: list[str] = Field(
        default_factory=list,
        description="Disabled policy IDs",
    )

    severity_override: dict[str, Literal["low", "medium", "high", "critical"]] = Field(
        default_factory=dict,
        description="Policy severity overrides",
    )

    @field_validator("enabled", "disabled")
    @classmethod
    def validate_no_duplicates(cls, v: list[str]) -> list[str]:
        """Validate no duplicates"""
        if len(v) != len(set(v)):
            raise ValueError("Duplicate policy IDs not allowed")
        return v

    @model_validator(mode="after")
    def validate_no_overlap(self) -> "RuleControl":
        """Validate enabled/disabled don't overlap"""
        enabled_set = set(self.enabled)
        disabled_set = set(self.disabled)

        overlap = enabled_set & disabled_set
        if overlap:
            raise ValueError(f"Policy IDs cannot be both enabled and disabled: {overlap}")

        return self

    def is_enabled(self, policy_id: str) -> bool:
        """
        Check if policy is enabled.

        Args:
            policy_id: Policy ID

        Returns:
            True if enabled (default: True if not in disabled)

        Logic:
        - If in enabled list: True
        - If in disabled list: False
        - Otherwise: True (enabled by default)
        """
        if policy_id in self.disabled:
            return False

        # If enabled list is empty, all are enabled by default
        if not self.enabled:
            return True

        # If enabled list is non-empty, only those are enabled
        return policy_id in self.enabled

    def get_effective_severity(
        self,
        policy_id: str,
        default_severity: str,
    ) -> str:
        """
        Get effective severity for policy.

        Args:
            policy_id: Policy ID
            default_severity: Default severity from policy

        Returns:
            Effective severity (override or default)
        """
        return self.severity_override.get(policy_id, default_severity)

    class Config:
        """Pydantic config"""

        frozen = True
        extra = "forbid"


class IgnoreConfig(BaseModel):
    """
    Ignore configuration.

    Controls which files/patterns to ignore.

    Example:
        ```toml
        [ignore]
        patterns = ["tests/**", "*_test.py"]
        files = ["examples/unsafe.py"]
        directories = ["vendor/", "node_modules/"]
        ```
    """

    patterns: list[str] = Field(
        default_factory=list,
        description="Glob patterns to ignore",
    )

    files: list[str] = Field(
        default_factory=list,
        description="Specific files to ignore",
    )

    directories: list[str] = Field(
        default_factory=list,
        description="Directories to ignore",
    )

    def should_ignore(self, file_path: str) -> bool:
        """
        Check if file should be ignored.

        Args:
            file_path: File path to check

        Returns:
            True if should be ignored

        Logic:
        - Exact match in files
        - Pattern match in patterns
        - Directory prefix match

        Note:
            Uses fnmatch for pattern matching.
        """
        import fnmatch
        from pathlib import Path

        # Exact file match
        if file_path in self.files:
            return True

        # Pattern match
        for pattern in self.patterns:
            if fnmatch.fnmatch(file_path, pattern):
                return True

        # Directory match
        path = Path(file_path)
        for dir_pattern in self.directories:
            # Check if file is under this directory
            if str(path).startswith(dir_pattern.rstrip("/")):
                return True

        return False

    class Config:
        """Pydantic config"""

        frozen = True
        extra = "forbid"


class ControlConfig(BaseModel):
    """
    Complete control configuration (semantica.toml).

    Combines rule control and ignore configuration.

    Example:
        ```toml
        [rules]
        enabled = ["sql-injection"]
        disabled = []

        [rules.severity_override]
        "sql-injection" = "high"

        [ignore]
        patterns = ["tests/**"]
        files = []
        directories = ["vendor/"]
        ```
    """

    rules: RuleControl = Field(
        default_factory=RuleControl,
        description="Rule control",
    )

    ignore: IgnoreConfig = Field(
        default_factory=IgnoreConfig,
        description="Ignore configuration",
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )

    class Config:
        """Pydantic config"""

        frozen = True
        extra = "forbid"
