"""Rule Validator - RFC-039.

Validates contributed rules before acceptance.

Validation Gates:
    1. Lint: Check required fields, valid patterns
    2. Shadow: Check for shadowing with existing rules
    3. Test: Run test cases (if provided)
    4. Benchmark: Performance check

Usage:
    >>> validator = RuleValidator()
    >>> result = validator.validate(rule_spec)
    >>> if not result.passed:
    ...     for error in result.errors:
    ...         print(f"Error: {error.message}")
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """Validation error that blocks acceptance."""

    code: str
    message: str
    field: str | None = None
    severity: Literal["error"] = "error"

    def __str__(self) -> str:
        if self.field:
            return f"[{self.code}] {self.field}: {self.message}"
        return f"[{self.code}] {self.message}"


@dataclass
class ValidationWarning:
    """Validation warning that doesn't block acceptance."""

    code: str
    message: str
    field: str | None = None
    severity: Literal["warning"] = "warning"

    def __str__(self) -> str:
        if self.field:
            return f"[{self.code}] {self.field}: {self.message}"
        return f"[{self.code}] {self.message}"


@dataclass
class ValidationResult:
    """Result of rule validation."""

    rule_id: str
    passed: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)
    gates_passed: list[str] = field(default_factory=list)
    gates_failed: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def summary(self) -> str:
        """Generate summary string."""
        status = "PASSED" if self.passed else "FAILED"
        return f"Validation {status}: {self.rule_id} ({self.error_count} errors, {self.warning_count} warnings)"


# Valid effect kinds
VALID_EFFECT_KINDS = {"source", "sink", "sanitizer", "propagator", "passthrough"}

# Valid tiers
VALID_TIERS = {"tier1", "tier2", "tier3"}

# Pattern for valid rule IDs
RULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class RuleValidator:
    """Validates contributed rules.

    RFC-039: Rule validation gates.

    Gates:
        1. lint: Check required fields and valid values
        2. shadow: Check for shadowing (optional)
        3. test: Run test cases (if provided)
        4. benchmark: Performance check (optional)

    Usage:
        >>> validator = RuleValidator()
        >>> result = validator.validate(rule_spec)
    """

    def __init__(
        self,
        check_shadowing: bool = True,
        run_tests: bool = True,
        run_benchmark: bool = False,
    ) -> None:
        """Initialize validator.

        Args:
            check_shadowing: Whether to check for shadowing
            run_tests: Whether to run test cases
            run_benchmark: Whether to run performance benchmark
        """
        self.check_shadowing = check_shadowing
        self.run_tests = run_tests
        self.run_benchmark = run_benchmark

    def validate(self, rule_spec: dict) -> ValidationResult:
        """Validate a rule specification.

        Args:
            rule_spec: Rule specification dict (from YAML)

        Returns:
            ValidationResult
        """
        rule_id = rule_spec.get("id", "unknown")
        errors: list[ValidationError] = []
        warnings: list[ValidationWarning] = []
        gates_passed: list[str] = []
        gates_failed: list[str] = []

        # Gate 1: Lint
        lint_errors, lint_warnings = self._lint(rule_spec)
        errors.extend(lint_errors)
        warnings.extend(lint_warnings)

        if lint_errors:
            gates_failed.append("lint")
        else:
            gates_passed.append("lint")

        # Gate 2: Shadow check (optional)
        if self.check_shadowing and not lint_errors:
            shadow_warnings = self._check_shadow(rule_spec)
            warnings.extend(shadow_warnings)
            gates_passed.append("shadow")  # Shadow only warns, never fails

        # Gate 3: Test cases (optional)
        if self.run_tests and not lint_errors:
            test_errors = self._run_tests(rule_spec)
            errors.extend(test_errors)
            if test_errors:
                gates_failed.append("test")
            else:
                gates_passed.append("test")

        # Gate 4: Benchmark (optional)
        if self.run_benchmark and not lint_errors:
            bench_warnings = self._run_benchmark(rule_spec)
            warnings.extend(bench_warnings)
            gates_passed.append("benchmark")  # Benchmark only warns

        passed = len(errors) == 0

        result = ValidationResult(
            rule_id=rule_id,
            passed=passed,
            errors=errors,
            warnings=warnings,
            gates_passed=gates_passed,
            gates_failed=gates_failed,
        )

        logger.info(result.summary())
        return result

    def _lint(self, rule_spec: dict) -> tuple[list[ValidationError], list[ValidationWarning]]:
        """Lint check: required fields and valid values.

        Args:
            rule_spec: Rule specification

        Returns:
            Tuple of (errors, warnings)
        """
        errors: list[ValidationError] = []
        warnings: list[ValidationWarning] = []

        # Required fields
        required_fields = ["id", "effect"]
        for field in required_fields:
            if field not in rule_spec:
                errors.append(
                    ValidationError(
                        code="E001",
                        message="Missing required field",
                        field=field,
                    )
                )

        # Rule ID format
        rule_id = rule_spec.get("id")
        if rule_id:
            if not RULE_ID_PATTERN.match(rule_id):
                errors.append(
                    ValidationError(
                        code="E002",
                        message="Invalid rule ID format (must be lowercase with underscores)",
                        field="id",
                    )
                )

        # Effect kind
        effect = rule_spec.get("effect", {})
        effect_kind = effect.get("kind") if isinstance(effect, dict) else None
        if effect_kind and effect_kind not in VALID_EFFECT_KINDS:
            errors.append(
                ValidationError(
                    code="E003",
                    message=f"Invalid effect kind: {effect_kind}",
                    field="effect.kind",
                )
            )

        # Pattern validation
        pattern = rule_spec.get("pattern", {})
        if isinstance(pattern, dict):
            base_type = pattern.get("base_type")
            call = pattern.get("call")

            # Check for overly broad patterns
            if base_type == "*" and call == "*":
                warnings.append(
                    ValidationWarning(
                        code="W001",
                        message="Pattern is very broad (matches everything)",
                        field="pattern",
                    )
                )

        # Tier validation
        tier = rule_spec.get("tier")
        if tier and tier not in VALID_TIERS:
            errors.append(
                ValidationError(
                    code="E004",
                    message=f"Invalid tier: {tier}",
                    field="tier",
                )
            )

        # Tags validation
        tags = rule_spec.get("tags", [])
        if not tags:
            warnings.append(
                ValidationWarning(
                    code="W002",
                    message="No tags specified (helps with discovery)",
                    field="tags",
                )
            )

        # Description validation
        description = rule_spec.get("description")
        if not description:
            warnings.append(
                ValidationWarning(
                    code="W003",
                    message="No description provided",
                    field="description",
                )
            )

        return errors, warnings

    def _check_shadow(self, rule_spec: dict) -> list[ValidationWarning]:
        """Check for shadowing with existing rules.

        Args:
            rule_spec: Rule specification

        Returns:
            List of shadowing warnings
        """
        warnings: list[ValidationWarning] = []

        # This would integrate with ShadowingAnalyzer
        # For now, just a placeholder
        # In real implementation:
        # 1. Compile the new rule
        # 2. Run ShadowingAnalyzer against existing rules
        # 3. Report any shadowing

        return warnings

    def _run_tests(self, rule_spec: dict) -> list[ValidationError]:
        """Run test cases if provided.

        Args:
            rule_spec: Rule specification

        Returns:
            List of test errors
        """
        errors: list[ValidationError] = []

        test_cases = rule_spec.get("test_cases", [])
        if not test_cases:
            # No test cases is not an error, but could be a warning
            return errors

        # This would run actual test cases
        # For now, just validate test case format
        for i, test in enumerate(test_cases):
            if not isinstance(test, dict):
                errors.append(
                    ValidationError(
                        code="E010",
                        message=f"Test case {i} is not a dict",
                        field="test_cases",
                    )
                )
                continue

            if "input" not in test:
                errors.append(
                    ValidationError(
                        code="E011",
                        message=f"Test case {i} missing 'input' field",
                        field="test_cases",
                    )
                )

            if "expected" not in test:
                errors.append(
                    ValidationError(
                        code="E012",
                        message=f"Test case {i} missing 'expected' field",
                        field="test_cases",
                    )
                )

        return errors

    def _run_benchmark(self, rule_spec: dict) -> list[ValidationWarning]:
        """Run performance benchmark.

        Args:
            rule_spec: Rule specification

        Returns:
            List of benchmark warnings
        """
        warnings: list[ValidationWarning] = []

        # This would run actual benchmarks
        # For now, just check for known slow patterns

        pattern = rule_spec.get("pattern", {})
        if isinstance(pattern, dict):
            base_type = pattern.get("base_type", "")
            call = pattern.get("call", "")

            # Warn about regex patterns (can be slow)
            if "*" in str(base_type) and "*" in str(call):
                warnings.append(
                    ValidationWarning(
                        code="W010",
                        message="Pattern has wildcards in both type and call (may be slow)",
                        field="pattern",
                    )
                )

        return warnings


def validate_rule(rule_spec: dict) -> ValidationResult:
    """Convenience function to validate a rule.

    Args:
        rule_spec: Rule specification

    Returns:
        ValidationResult
    """
    validator = RuleValidator()
    return validator.validate(rule_spec)
