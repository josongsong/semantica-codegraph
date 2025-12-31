"""Retrieve Spec Validator"""

from typing import Any

from .base_validator import BaseSpecValidator


class RetrieveSpecValidator(BaseSpecValidator):
    """RetrieveSpec validator"""

    def _validate_specific(self, spec: dict[str, Any]) -> tuple[list[dict], list[dict]]:
        """RetrieveSpec specific validation"""
        errors = []
        warnings = []

        # k 값 확인
        k = spec.get("k", 50)
        if k > 1000:
            warnings.append({"field": "k", "message": f"Large k={k} may be slow (>1000)"})

        return errors, warnings
