"""Validation Models"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    """코드 검증 결과"""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_error(self, error: str):
        """에러 추가"""
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: str):
        """경고 추가"""
        self.warnings.append(warning)

    def to_dict(self):
        """딕셔너리로 변환"""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }

    def __str__(self):
        """문자열 표현"""
        status = "✅ Valid" if self.is_valid else "❌ Invalid"
        return f"{status} ({len(self.errors)} errors, {len(self.warnings)} warnings)"
