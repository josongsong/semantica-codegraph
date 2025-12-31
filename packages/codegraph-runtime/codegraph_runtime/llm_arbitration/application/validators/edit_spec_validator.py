"""Edit Spec Validator"""

from typing import Any

from .base_validator import BaseSpecValidator


class EditSpecValidator(BaseSpecValidator):
    """EditSpec validator"""

    def _validate_specific(self, spec: dict[str, Any]) -> tuple[list[dict], list[dict]]:
        """EditSpec specific validation"""
        errors = []
        warnings = []

        # Operations 필수
        operations = spec.get("operations", [])
        if not operations:
            errors.append({"field": "operations", "message": "operations cannot be empty"})

        # Constraints
        constraints = spec.get("constraints", {})
        max_files = constraints.get("max_files", 10)
        if max_files > 100:
            warnings.append(
                {
                    "field": "constraints.max_files",
                    "message": f"Large max_files={max_files} (>100)",
                }
            )

        # dry_run=False 경고
        if not spec.get("dry_run", True):
            warnings.append(
                {
                    "field": "dry_run",
                    "message": "dry_run=False will apply changes (not simulated)",
                }
            )

        return errors, warnings
