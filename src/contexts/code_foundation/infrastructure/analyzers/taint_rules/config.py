"""
Taint Rules Configuration System

프로젝트별로 Rule Set을 조합/토글하는 설정 시스템
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml
import json


@dataclass
class RuleOverride:
    """개별 Rule 설정 override"""

    rule_id: str
    enabled: bool = True
    severity: str | None = None
    reason: str | None = None  # Why was this overridden?


@dataclass
class RuleSetConfig:
    """RuleSet 단위 설정"""

    name: str
    enabled: bool = True
    severity_threshold: str = "LOW"  # Minimum severity to include


@dataclass
class TaintConfig:
    """
    Taint Analysis 전체 설정

    YAML/JSON으로 저장 가능
    """

    # RuleSet 단위 enable/disable
    rule_sets: list[RuleSetConfig] = field(default_factory=list)

    # 개별 Rule override
    rule_overrides: dict[str, RuleOverride] = field(default_factory=dict)

    # Global settings
    enabled: bool = True
    max_path_length: int = 50  # Taint path 최대 길이
    sanitizer_trust_level: float = 0.8  # Sanitizer 신뢰 threshold

    @classmethod
    def from_yaml(cls, path: Path) -> "TaintConfig":
        """Load config from YAML file"""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_json(cls, path: Path) -> "TaintConfig":
        """Load config from JSON file"""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaintConfig":
        """Load config from dictionary"""
        taint_data = data.get("taint", {})

        # Parse RuleSets
        rule_sets = []
        for rs_data in taint_data.get("rule_sets", []):
            rule_sets.append(RuleSetConfig(**rs_data))

        # Parse Rule overrides
        rule_overrides = {}
        for rule_id, override_data in taint_data.get("rule_overrides", {}).items():
            rule_overrides[rule_id] = RuleOverride(rule_id=rule_id, **override_data)

        return cls(
            rule_sets=rule_sets,
            rule_overrides=rule_overrides,
            enabled=taint_data.get("enabled", True),
            max_path_length=taint_data.get("max_path_length", 50),
            sanitizer_trust_level=taint_data.get("sanitizer_trust_level", 0.8),
        )

    def to_yaml(self, path: Path):
        """Save config to YAML file"""
        data = self.to_dict()
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        # Convert RuleOverride objects to dicts
        overrides_dict = {}
        for rule_id, override in self.rule_overrides.items():
            if isinstance(override, RuleOverride):
                overrides_dict[rule_id] = {
                    "enabled": override.enabled,
                    "severity": override.severity,
                    "reason": override.reason,
                }
            elif isinstance(override, dict):
                # Already a dict
                overrides_dict[rule_id] = override
            else:
                raise ValueError(f"Invalid override type: {type(override)}")

        return {
            "taint": {
                "enabled": self.enabled,
                "max_path_length": self.max_path_length,
                "sanitizer_trust_level": self.sanitizer_trust_level,
                "rule_sets": [
                    {
                        "name": rs.name,
                        "enabled": rs.enabled,
                        "severity_threshold": rs.severity_threshold,
                    }
                    for rs in self.rule_sets
                ],
                "rule_overrides": overrides_dict,
            }
        }

    def is_rule_set_enabled(self, name: str) -> bool:
        """Check if a RuleSet is enabled"""
        for rs in self.rule_sets:
            if rs.name == name:
                return rs.enabled
        return True  # Default: enabled

    def is_rule_enabled(self, rule_id: str) -> bool:
        """Check if a specific rule is enabled"""
        if rule_id in self.rule_overrides:
            return self.rule_overrides[rule_id].enabled
        return True  # Default: enabled

    def get_rule_severity_override(self, rule_id: str) -> str | None:
        """Get severity override for a rule"""
        if rule_id in self.rule_overrides:
            return self.rule_overrides[rule_id].severity
        return None


# ============================================================
# Pre-defined Profiles
# ============================================================

STRICT_SECURITY_PROFILE = TaintConfig(
    rule_sets=[
        RuleSetConfig(name="python_core", enabled=True, severity_threshold="LOW"),
        RuleSetConfig(name="flask", enabled=True, severity_threshold="LOW"),
        RuleSetConfig(name="django", enabled=True, severity_threshold="LOW"),
    ],
    sanitizer_trust_level=0.95,  # High trust threshold
)

PERFORMANCE_PROFILE = TaintConfig(
    rule_sets=[
        RuleSetConfig(name="python_core", enabled=True, severity_threshold="HIGH"),
        RuleSetConfig(name="flask", enabled=False),
        RuleSetConfig(name="django", enabled=False),
    ],
    max_path_length=20,  # Shorter paths
    sanitizer_trust_level=0.7,
)

FRONTEND_PROFILE = TaintConfig(
    rule_sets=[
        RuleSetConfig(name="python_core", enabled=False),
        RuleSetConfig(name="react", enabled=True, severity_threshold="MEDIUM"),
        RuleSetConfig(name="nextjs", enabled=True, severity_threshold="MEDIUM"),
    ],
)

BACKEND_PROFILE = TaintConfig(
    rule_sets=[
        RuleSetConfig(name="python_core", enabled=True, severity_threshold="MEDIUM"),
        RuleSetConfig(name="flask", enabled=True, severity_threshold="MEDIUM"),
        RuleSetConfig(name="django", enabled=True, severity_threshold="MEDIUM"),
        RuleSetConfig(name="sqlalchemy", enabled=True, severity_threshold="HIGH"),
    ],
)

PROFILES = {
    "strict": STRICT_SECURITY_PROFILE,
    "performance": PERFORMANCE_PROFILE,
    "frontend": FRONTEND_PROFILE,
    "backend": BACKEND_PROFILE,
}


def load_profile(name: str) -> TaintConfig:
    """Load a pre-defined profile"""
    if name not in PROFILES:
        raise ValueError(f"Unknown profile: {name}. Available: {list(PROFILES.keys())}")
    return PROFILES[name]
