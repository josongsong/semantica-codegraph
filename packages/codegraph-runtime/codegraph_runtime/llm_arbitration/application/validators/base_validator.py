"""Base Spec Validator (Template Method Pattern)"""

from abc import ABC, abstractmethod
from typing import Any


class BaseSpecValidator(ABC):
    """
    Base Spec Validator (Template Method Pattern).

    SOLID:
    - S: Validation만
    - O: 새 validator 추가 시 상속만
    - L: Liskov 치환
    - I: 최소 인터페이스
    - D: Abstraction
    """

    def validate(self, spec: dict[str, Any]) -> dict[str, Any]:
        """
        Template method (공통 로직).

        Args:
            spec: Spec dict

        Returns:
            {"valid": bool, "errors": [], "warnings": []}
        """
        errors = []
        warnings = []

        # 1. Scope validation (common)
        scope_errors = self._validate_scope(spec.get("scope", {}))
        errors.extend(scope_errors)

        # 2. Spec-specific validation (subclass)
        spec_errors, spec_warnings = self._validate_specific(spec)
        errors.extend(spec_errors)
        warnings.extend(spec_warnings)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def _validate_scope(self, scope: dict) -> list[dict]:
        """Common scope validation"""
        errors = []

        if not scope.get("repo_id"):
            errors.append({"field": "scope.repo_id", "message": "repo_id is required"})

        if not scope.get("snapshot_id"):
            errors.append({"field": "scope.snapshot_id", "message": "snapshot_id is required"})

        return errors

    @abstractmethod
    def _validate_specific(self, spec: dict[str, Any]) -> tuple[list[dict], list[dict]]:
        """
        Spec-specific validation (subclass implements).

        Returns:
            (errors, warnings)
        """
        ...
