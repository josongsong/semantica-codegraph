"""Analyze Spec Validator"""

from typing import Any

from .base_validator import BaseSpecValidator


class AnalyzeSpecValidator(BaseSpecValidator):
    """AnalyzeSpec validator (Single Responsibility)"""

    def _validate_specific(self, spec: dict[str, Any]) -> tuple[list[dict], list[dict]]:
        """AnalyzeSpec specific validation"""
        errors = []
        warnings = []

        # Template ID 필수
        if not spec.get("template_id"):
            errors.append({"field": "template_id", "message": "template_id is required"})

        # Limits 범위
        limits = spec.get("limits", {})
        max_paths = limits.get("max_paths", 200)
        if max_paths > 10000:
            warnings.append(
                {
                    "field": "limits.max_paths",
                    "message": f"Very large max_paths={max_paths} (>10000)",
                }
            )

        timeout_ms = limits.get("timeout_ms", 30000)
        if timeout_ms > 300000:  # 5분
            warnings.append(
                {
                    "field": "limits.timeout_ms",
                    "message": f"Very long timeout={timeout_ms}ms (>5min)",
                }
            )

        return errors, warnings
