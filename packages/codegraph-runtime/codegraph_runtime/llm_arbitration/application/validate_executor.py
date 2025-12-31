"""Validate Executor - Spec 유효성 검증"""

from typing import Any

from codegraph_engine.shared_kernel.contracts import AnalyzeSpec, EditSpec, RetrieveSpec


class ValidateExecutor:
    """
    RFC Spec 유효성 검증 (Strategy Pattern).

    Refactored from if-elif chain (181 lines) to Strategy (50 lines).

    SOLID:
    - S: Validation routing만
    - O: 새 validator 추가 시 registry만 확장
    - L: Validator 교체 가능
    - I: 최소 인터페이스
    - D: Validator abstraction에 의존
    """

    def __init__(self):
        """Initialize with validator registry (Strategy)"""
        from .validators import (
            AnalyzeSpecValidator,
            EditSpecValidator,
            RetrieveSpecValidator,
        )

        self._validators = {
            "retrieve": RetrieveSpecValidator(),
            "analyze": AnalyzeSpecValidator(),
            "edit": EditSpecValidator(),
        }

    def validate_spec(self, spec: dict[str, Any]) -> dict[str, Any]:
        """
        Spec 유효성 검증 (Strategy dispatch).

        Args:
            spec: RetrieveSpec | AnalyzeSpec | EditSpec

        Returns:
            Validation result
        """
        intent = spec.get("intent")

        if not intent:
            return {
                "valid": False,
                "errors": [{"field": "intent", "message": "'intent' field is required"}],
                "warnings": [],
                "error_code": "MISSING_INTENT",
                "hint_schema": {
                    "required_fields": ["intent"],
                    "valid_intents": ["retrieve", "analyze", "edit"],
                },
                "suggested_fixes": [{"field": "intent", "suggestion": "Add 'intent' field"}],
            }

        # Strategy pattern: Get validator
        validator = self._validators.get(intent)

        if not validator:
            return {
                "valid": False,
                "errors": [{"field": "intent", "message": f"Invalid intent: {intent}"}],
                "warnings": [],
                "error_code": "INVALID_INTENT",
                "hint_schema": {
                    "valid_intents": list(self._validators.keys()),
                },
                "suggested_fixes": [],
            }

        # Delegate validation
        return validator.validate(spec)
