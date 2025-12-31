"""
Guard Detector

RFC-030: Detects guard conditions in IR documents.

Hexagonal Architecture:
- Infrastructure Layer (this): IR parsing, pattern matching
- Domain Layer: GuardCondition model

SRP: Separated from ConstraintValidator for single responsibility.
"""

from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.taint.guard import GuardCondition
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import ExprKind

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument

logger = get_logger(__name__)


class GuardDetector:
    """
    RFC-030: Detect guard conditions in IR documents.

    Detects patterns like:
    - if x not in ALLOWED: abort()
    - if not validate(x): raise ValueError()
    - if check_auth(): return None

    SRP: Only responsible for guard detection.
    ConstraintValidator uses this for guard-aware validation.

    Example:
        ```python
        detector = GuardDetector()
        guards = detector.detect(ir_doc)

        for guard in guards:
            if guard.is_valid_guard(sink_block, dominator):
                print(f"{guard.guarded_var} is protected")
        ```
    """

    # Exit functions that indicate guard failure
    EXIT_FUNCTIONS = frozenset({"abort", "sys.exit", "exit", "raise", "return"})

    # Validation patterns in function names
    VALIDATION_PATTERNS = frozenset(
        {
            "validate",
            "check",
            "verify",
            "is_valid",
            "is_allowed",
            "is_authenticated",
            "has_permission",
        }
    )

    # 🔥 RFC-030: Regex guard patterns (FP reduction)
    REGEX_GUARD_PATTERNS = frozenset(
        {
            "re.match",
            "re.fullmatch",
            "re.search",
            "re.findall",
            "match",
            "fullmatch",
        }
    )

    # 🔥 RFC-030: Type check guard patterns (FP reduction)
    TYPE_GUARD_PATTERNS = frozenset(
        {
            "isinstance",
            "isdigit",
            "isnumeric",
            "isalpha",
            "isalnum",
            "isdecimal",
            "type",
        }
    )

    def detect(self, ir_doc: "IRDocument") -> list[GuardCondition]:
        """
        Detect guard conditions in IR document.

        Supports two patterns:
        1. Negative guard: "if x not in ALLOWED: exit()"
        2. Positive guard: "if x in ALLOWED: sink(x)" (sink only inside if)

        Args:
            ir_doc: IR document to analyze

        Returns:
            List of detected guard conditions
        """
        guards: list[GuardCondition] = []

        if not hasattr(ir_doc, "expressions") or not ir_doc.expressions:
            return guards

        # Index expressions by function for efficient lookup
        exprs_by_function: dict[str, list] = {}
        for expr in ir_doc.expressions:
            func_fqn = getattr(expr, "function_fqn", "") or ""
            exprs_by_function.setdefault(func_fqn, []).append(expr)

        # Pattern 1: Negative guards (exit-on-fail)
        guards.extend(self._detect_negative_guards(ir_doc, exprs_by_function))

        # Pattern 2: Positive guards (allowlist check before sink)
        guards.extend(self._detect_positive_guards(ir_doc))

        logger.debug("guards_detected", count=len(guards))
        return guards

    def _detect_negative_guards(self, ir_doc: "IRDocument", exprs_by_function: dict) -> list[GuardCondition]:
        """Detect negative guard pattern: if check fails, exit."""
        guards: list[GuardCondition] = []

        for expr in ir_doc.expressions:
            if not hasattr(expr, "attrs"):
                continue

            callee = expr.attrs.get("callee_name", "")

            # Check for exit calls
            if not self._is_exit_call(callee):
                continue

            # Find validation calls in same function
            func_fqn = getattr(expr, "function_fqn", "") or ""
            func_exprs = exprs_by_function.get(func_fqn, [])

            for check_expr in func_exprs:
                if check_expr.kind != ExprKind.CALL:
                    continue

                check_callee = check_expr.attrs.get("callee_name", "")

                if not self._is_guard_call(check_callee):
                    continue

                # Extract guarded variables from call args
                call_args = check_expr.attrs.get("call_args", [])
                for arg in call_args:
                    if isinstance(arg, str):
                        guards.append(
                            GuardCondition(
                                guard_block_id=check_expr.block_id or "",
                                guarded_var=arg,
                                exit_on_fail=True,
                            )
                        )

        return guards

    def _detect_positive_guards(self, ir_doc: "IRDocument") -> list[GuardCondition]:
        """
        Detect positive guard pattern: if x in ALLOWED: sink(x).

        Pattern: comparison_operator with "in" and list/set literal.
        Uses NAME_LOAD on same line to find guarded variable.
        """
        guards: list[GuardCondition] = []

        # Index NAME_LOAD expressions by line for efficient lookup
        name_loads_by_line: dict[int, list] = {}
        for expr in ir_doc.expressions:
            if expr.kind == ExprKind.NAME_LOAD and expr.span:
                line = expr.span.start_line
                name_loads_by_line.setdefault(line, []).append(expr)

        for expr in ir_doc.expressions:
            if not hasattr(expr, "attrs"):
                continue

            # Look for COMPARE expressions with "in" or "not in" operator
            if expr.kind == ExprKind.COMPARE:
                ops = expr.attrs.get("operators", [])
                has_in = "in" in ops or "In" in ops
                has_not_in = "not in" in ops or "NotIn" in ops or "notin" in ops

                if has_in or has_not_in:
                    # Find NAME_LOAD on same line - these are the guarded variables
                    if expr.span:
                        name_loads = name_loads_by_line.get(expr.span.start_line, [])
                        for name_expr in name_loads:
                            var_name = name_expr.attrs.get("var_name")
                            if var_name:
                                # For "not in", it's a negative guard (exit_on_fail=True)
                                # For "in", it's a positive guard (exit_on_fail=False)
                                guards.append(
                                    GuardCondition(
                                        guard_block_id=expr.block_id or "",
                                        guarded_var=var_name,
                                        exit_on_fail=has_not_in,
                                    )
                                )
                                # Don't break - process ALL NAME_LOADs for multi-variable guards

        return guards

    def _is_exit_call(self, callee: str) -> bool:
        """Check if callee is an exit function."""
        return any(ef in callee for ef in self.EXIT_FUNCTIONS)

    def _is_validation_call(self, callee: str) -> bool:
        """Check if callee is a validation function."""
        callee_lower = callee.lower()
        return any(p in callee_lower for p in self.VALIDATION_PATTERNS)

    def _is_regex_guard(self, callee: str) -> bool:
        """🔥 RFC-030: Check if callee is a regex guard pattern."""
        return any(p in callee for p in self.REGEX_GUARD_PATTERNS)

    def _is_type_guard(self, callee: str) -> bool:
        """🔥 RFC-030: Check if callee is a type check guard pattern."""
        return any(p in callee for p in self.TYPE_GUARD_PATTERNS)

    def _is_guard_call(self, callee: str) -> bool:
        """Check if callee is any type of guard (validation, regex, type)."""
        return self._is_validation_call(callee) or self._is_regex_guard(callee) or self._is_type_guard(callee)
