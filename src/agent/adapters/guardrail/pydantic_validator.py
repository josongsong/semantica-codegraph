"""
Pydantic Guardrail Validator

IGuardrailValidator 포트 구현.
Phase 1에서는 Pydantic 기반 validation.
Phase 2+에서 Guardrails AI로 확장 예정.
"""

import re
from dataclasses import dataclass
from typing import Any

from src.ports import IGuardrailValidator


@dataclass
class ValidationResult:
    """검증 결과"""

    valid: bool
    errors: list[str]
    warnings: list[str]
    policy_name: str


class PydanticValidatorAdapter(IGuardrailValidator):
    """
    Pydantic → IGuardrailValidator Adapter.

    Phase 1: Pydantic validation
    Phase 2+: Guardrails AI 통합
    """

    def __init__(self):
        """초기화"""
        self.policies: dict[str, Any] = {}

        # 기본 정책 등록
        self._register_default_policies()

    def _register_default_policies(self):
        """기본 정책 등록"""
        # Policy 1: Secret detection
        self.policies["secret_detection"] = {
            "type": "regex",
            "patterns": [
                r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]+['\"]",
                r"(?i)(aws|azure|gcp)[_-]?(key|secret|token)\s*[:=]\s*['\"][^'\"]+['\"]",
            ],
        }

        # Policy 2: Code quality
        self.policies["code_quality"] = {
            "type": "pydantic",
            "min_lines": 1,
            "max_lines": 1000,
        }

        # Policy 3: Breaking changes
        self.policies["breaking_changes"] = {
            "type": "custom",
            "disallowed_patterns": [
                "rm -rf",
                "DROP TABLE",
                "DELETE FROM",
            ],
        }

    async def validate(self, data: Any, policy_name: str) -> ValidationResult:
        """
        데이터 검증.

        Args:
            data: 검증할 데이터
            policy_name: 정책 이름

        Returns:
            ValidationResult
        """
        if policy_name not in self.policies:
            return ValidationResult(
                valid=False,
                errors=[f"Policy not found: {policy_name}"],
                warnings=[],
                policy_name=policy_name,
            )

        policy = self.policies[policy_name]
        policy_type = policy.get("type")

        if policy_type == "regex":
            return await self._validate_regex(data, policy, policy_name)
        elif policy_type == "pydantic":
            return await self._validate_pydantic(data, policy, policy_name)
        elif policy_type == "custom":
            return await self._validate_custom(data, policy, policy_name)
        else:
            return ValidationResult(
                valid=False,
                errors=[f"Unknown policy type: {policy_type}"],
                warnings=[],
                policy_name=policy_name,
            )

    async def _validate_regex(self, data: Any, policy: dict, policy_name: str) -> ValidationResult:
        """Regex 기반 검증 (secret detection)"""
        errors = []
        warnings = []

        # 데이터를 문자열로 변환
        if isinstance(data, str):
            text = data
        elif isinstance(data, list):
            # CodeChange 리스트인 경우
            text = "\n".join(["\n".join(item.new_lines if hasattr(item, "new_lines") else []) for item in data])
        else:
            text = str(data)

        # Regex 패턴 매칭
        for pattern in policy.get("patterns", []):
            matches = re.findall(pattern, text)
            if matches:
                errors.append(f"Detected sensitive data: {pattern}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            policy_name=policy_name,
        )

    async def _validate_pydantic(self, data: Any, policy: dict, policy_name: str) -> ValidationResult:
        """Pydantic 기반 검증"""
        errors = []
        warnings = []

        # 간단한 검증 (라인 수 등)
        if isinstance(data, list):
            total_lines = sum([len(item.new_lines) if hasattr(item, "new_lines") else 0 for item in data])

            min_lines = policy.get("min_lines", 0)
            max_lines = policy.get("max_lines", 10000)

            if total_lines < min_lines:
                errors.append(f"Too few lines: {total_lines} < {min_lines}")
            elif total_lines > max_lines:
                errors.append(f"Too many lines: {total_lines} > {max_lines}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            policy_name=policy_name,
        )

    async def _validate_custom(self, data: Any, policy: dict, policy_name: str) -> ValidationResult:
        """Custom 검증 (breaking changes)"""
        errors = []
        warnings = []

        # 데이터를 문자열로 변환
        if isinstance(data, str):
            text = data
        elif isinstance(data, list):
            text = "\n".join(["\n".join(item.new_lines if hasattr(item, "new_lines") else []) for item in data])
        else:
            text = str(data)

        # Disallowed patterns 체크
        for pattern in policy.get("disallowed_patterns", []):
            if pattern in text:
                errors.append(f"Disallowed pattern detected: {pattern}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            policy_name=policy_name,
        )
