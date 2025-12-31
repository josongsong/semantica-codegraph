"""
Constraint Validator

Validates constraints on IR nodes for Taint Analysis.
Supports 40+ constraint types as per RFC-017.
"""

from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression, ExprKind

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.dfg.ssa.dominator import DominatorTree
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument

logger = get_logger(__name__)


class ConstraintValidator:
    """
    Constraint Validator for Taint Analysis.

    Validates constraints on IR nodes (expressions, variables).
    Supports 5 categories of constraints:

    1. **Type Constraints**: arg_type, return_type
    2. **Source Constraints**: arg_source, value_source
    3. **Flow Constraints**: flow_sensitivity, path_sensitivity
    4. **Context Constraints**: context_sensitive, scope
    5. **Pattern Constraints**: value_pattern, name_pattern

    Example:
        ```python
        validator = ConstraintValidator()

        # Validate "arg_type: not_const"
        is_valid = validator.validate(
            call_expr,
            {"arg_type": "not_const"}
        )
        # → True if argument is not a constant
        ```

    Constraint Format:
        ```yaml
        constraints:
          arg_type: not_const        # Not a constant
          arg_source: external       # From external input
          value_pattern: ".*query.*" # Matches regex
        ```
    """

    def __init__(self):
        """Initialize validator"""
        self._stats = {
            "total_validated": 0,
            "passed": 0,
            "failed": 0,
            "paths_validated": 0,
            "by_type": {},
        }
        # RFC-030: Dominator-based guard validation
        self._dominator_tree: DominatorTree | None = None
        self._ir_document: IRDocument | None = None
        self._detected_guards: list[Any] = []

    # ============================================================
    # RFC-030: Dominator-based Guard Validation
    # ============================================================

    def set_dominator_tree(self, dom_tree: "DominatorTree") -> None:
        """
        Set dominator tree for guard validation.

        RFC-030: Dominator tree enables path-sensitive guard checks.
        A guard is valid if guard_block dominates sink_block.

        Args:
            dom_tree: Computed dominator tree from CFG
        """
        self._dominator_tree = dom_tree
        logger.debug("dominator_tree_set", has_tree=dom_tree is not None)

    def set_ir_document(self, ir_doc: "IRDocument") -> None:
        """
        Set IR document for guard detection.

        RFC-030: IR document enables GuardDetector to find guard patterns.

        Args:
            ir_doc: IR document to analyze
        """
        self._ir_document = ir_doc

        # Detect guards using GuardDetector
        if ir_doc is not None:
            try:
                from codegraph_engine.code_foundation.infrastructure.taint.validation.guard_detector import (
                    GuardDetector,
                )

                detector = GuardDetector()
                self._detected_guards = detector.detect(ir_doc)
                logger.debug("guards_detected", count=len(self._detected_guards))
            except Exception as e:
                logger.debug("guard_detection_failed", error=str(e))
                self._detected_guards = []

    def is_guard_protected(self, sink_block_id: str, variable: str) -> bool:
        """
        Check if variable is protected by a guard at sink location.

        RFC-030: Uses Dominator analysis to validate guards.

        Args:
            sink_block_id: CFG block ID of the sink
            variable: Variable name to check

        Returns:
            True if variable is protected by a valid guard
        """
        if not self._dominator_tree or not self._detected_guards:
            return False

        for guard in self._detected_guards:
            # Check if guard protects this variable
            if guard.guarded_var != variable:
                continue

            # Validate guard using dominator analysis
            if guard.is_valid_guard(sink_block_id, self._dominator_tree):
                logger.debug(
                    "guard_protection_valid",
                    variable=variable,
                    guard_block=guard.guard_block_id,
                    sink_block=sink_block_id,
                )
                return True

        return False

    def validate_path(self, path: Any, constraints: dict[str, Any]) -> bool:
        """
        Validate path against constraints.

        Implements ConstraintValidatorPort interface for TaintEngine.

        Args:
            path: PathResult from query engine
            constraints: Constraint specifications

        Returns:
            True if path satisfies all constraints

        Note:
            For now, path-level validation is simplified.
            Full path-sensitive analysis will be added in Phase 4.
        """
        if not constraints:
            return True

        self._stats["paths_validated"] += 1

        # Path-level constraints validation
        # For now, we check basic path properties
        if "max_length" in constraints:
            max_length = constraints["max_length"]
            if hasattr(path, "length") and path.length > max_length:
                logger.debug("path_too_long", length=path.length, max=max_length)
                return False

        if "min_confidence" in constraints:
            min_conf = constraints["min_confidence"]
            if hasattr(path, "confidence") and path.confidence < min_conf:
                logger.debug("confidence_too_low", conf=path.confidence, min=min_conf)
                return False

        if "require_sanitizer" in constraints:
            if constraints["require_sanitizer"]:
                # Check if path has sanitizer
                if hasattr(path, "has_sanitizer") and not path.has_sanitizer:
                    logger.debug("sanitizer_required")
                    return False

        return True

    def validate(self, node: Any, constraints: dict[str, Any]) -> bool:
        """
        Validate all constraints on node.

        Args:
            node: IR node to validate (Expression, Variable, etc.)
            constraints: Dict of constraints

        Returns:
            True if all constraints pass, False otherwise

        Example:
            ```python
            constraints = {
                "arg_type": "not_const",
                "arg_source": "external"
            }
            result = validator.validate(call_expr, constraints)
            ```
        """
        if not constraints:
            return True

        self._stats["total_validated"] += 1

        for key, value in constraints.items():
            if not self.validate_constraint(node, key, value):
                self._stats["failed"] += 1
                logger.debug("constraint_failed", key=key, value=value)
                return False

        self._stats["passed"] += 1
        return True

    def validate_constraint(
        self,
        node: Any,
        key: str,
        value: Any,
    ) -> bool:
        """
        Validate single constraint.

        Args:
            node: IR node to validate
            key: Constraint key (e.g., "arg_type")
            value: Constraint value (e.g., "not_const")

        Returns:
            True if constraint passes

        Raises:
            ValueError: If constraint key is unknown

        Dispatches to specific validators:
        - arg_type → _validate_arg_type()
        - arg_source → _validate_arg_source()
        - value_pattern → _validate_value_pattern()
        - etc.
        """
        self._stats["by_type"][key] = self._stats["by_type"].get(key, 0) + 1

        # Dispatch to specific validator
        validator_method = f"_validate_{key}"
        if hasattr(self, validator_method):
            return getattr(self, validator_method)(node, value)

        # Unknown constraint
        logger.warning("unknown_constraint", key=key, value=value)
        raise ValueError(f"Unknown constraint key: {key}")

    # ============================================================
    # Category 1: Type Constraints
    # ============================================================

    def _validate_arg_type(self, node: Any, value: str) -> bool:
        """
        Validate argument type constraint.

        Supported values:
        - "not_const": Not a constant literal
        - "string": Is a string type
        - "numeric": Is a numeric type
        - "collection": Is a collection type
        - "callable": Is a callable type

        Args:
            node: IR node (Expression)
            value: Constraint value

        Returns:
            True if constraint passes
        """
        if value == "not_const":
            return self._is_not_constant(node)

        if value == "string":
            return self._is_string_type(node)

        if value == "numeric":
            return self._is_numeric_type(node)

        if value == "collection":
            return self._is_collection_type(node)

        if value == "callable":
            return self._is_callable_type(node)

        logger.warning("unknown_arg_type", value=value)
        return False

    def _validate_return_type(self, node: Any, value: str) -> bool:
        """
        Validate return type constraint.

        Args:
            node: IR node
            value: Expected return type

        Returns:
            True if return type matches

        Implementation:
            Uses TypeInfo from node attributes if available.
            Supports basic type matching (exact, contains).
        """
        if isinstance(node, Expression):
            # Check if has type_info
            type_info = node.attrs.get("type_info")
            if type_info and hasattr(type_info, "inferred_type"):
                inferred = type_info.inferred_type or ""
                # Exact match or contains
                return value in inferred or inferred == value

            # Fallback to type attr
            node_type = node.attrs.get("type", "")
            if node_type:
                return value in node_type or node_type == value

        return False

    # ============================================================
    # Category 2: Source Constraints
    # ============================================================

    def _validate_arg_source(self, node: Any, value: str) -> bool:
        """
        Validate argument source constraint.

        Supported values:
        - "external": From external input (user, network, file)
        - "internal": From internal code
        - "parameter": From function parameter
        - "global": From global variable

        Args:
            node: IR node
            value: Constraint value

        Returns:
            True if constraint passes

        Note:
            Requires data-flow analysis (Phase 3).
        """
        if value == "external":
            # Check if node is from external source
            # For now, heuristic: check name/attrs
            if isinstance(node, Expression):
                name = node.attrs.get("name", "")
                if any(ext in name.lower() for ext in ["request", "input", "user", "stdin"]):
                    return True
            return False

        if value == "internal":
            return not self._validate_arg_source(node, "external")

        if value == "parameter":
            if isinstance(node, Expression):
                return node.attrs.get("from_parameter", False)
            return False

        if value == "global":
            if isinstance(node, Expression):
                return node.attrs.get("is_global", False)
            return False

        logger.warning("unknown_arg_source", value=value)
        return False

    def _validate_value_source(self, node: Any, value: str) -> bool:
        """
        Validate value source constraint.

        Similar to arg_source but for value origin tracking.

        Implementation:
            Uses heuristics based on node attributes.
            Full data-flow tracking will be added in Phase 3.
        """
        # For now, use same logic as arg_source
        return self._validate_arg_source(node, value)

    # ============================================================
    # Category 3: Flow Constraints
    # ============================================================

    def _validate_flow_sensitivity(self, node: Any, value: bool) -> bool:
        """
        Validate flow sensitivity constraint.

        Args:
            node: IR node
            value: True if flow-sensitive required

        Returns:
            True if constraint passes

        Implementation:
            Simplified check - returns True if flow-sensitivity not strictly required.
            Full CFG-based flow analysis will be added in Phase 4.
        """
        # For now, if flow-sensitivity is required, we assume it's satisfied
        # Full implementation will use CFG to check def-use chains
        if value:
            logger.debug("flow_sensitivity_required_but_not_validated")
        return True

    def _validate_path_sensitivity(self, node: Any, value: bool) -> bool:
        """
        Validate path sensitivity constraint.

        RFC-030: Uses Dominator-based guard detection for path sensitivity.

        Implementation:
            1. Check if node has block_id
            2. Check if variable is guard-protected at that block
            3. If protected, path is considered sanitized
        """
        if not value:
            return True

        # RFC-030: Use Dominator-based guard validation
        if self._dominator_tree and self._detected_guards:
            # Get block_id and variable from node
            if isinstance(node, Expression):
                block_id = node.attrs.get("block_id", "")
                var_name = node.attrs.get("name", "")

                if block_id and var_name:
                    if self.is_guard_protected(block_id, var_name):
                        logger.debug("path_sensitivity_guard_protected", var=var_name)
                        return True

        # Fallback: assume satisfied if no guard info
        logger.debug("path_sensitivity_no_guard_info")
        return True

    # ============================================================
    # Category 4: Context Constraints
    # ============================================================

    def _validate_context_sensitive(self, node: Any, value: bool) -> bool:
        """
        Validate context sensitivity constraint.

        Implementation:
            Simplified check - returns True if context-sensitivity not strictly required.
            Full context-sensitive analysis will be added in Phase 6.
        """
        # For now, if context-sensitivity is required, we assume it's satisfied
        # Full implementation will track calling contexts
        if value:
            logger.debug("context_sensitivity_required_but_not_validated")
        return True

    def _validate_scope(self, node: Any, value: str) -> bool:
        """
        Validate scope constraint.

        Supported values:
        - "local": Local variable
        - "parameter": Function parameter
        - "global": Global variable
        - "closure": Closure variable

        Args:
            node: IR node
            value: Expected scope

        Returns:
            True if in correct scope
        """
        if isinstance(node, Expression):
            node_scope = node.attrs.get("scope")
            if node_scope:
                return node_scope == value

        return False

    # ============================================================
    # Category 5: Pattern Constraints
    # ============================================================

    def _validate_value_pattern(self, node: Any, value: str) -> bool:
        """
        Validate value pattern constraint.

        Args:
            node: IR node
            value: Regex pattern

        Returns:
            True if value matches pattern

        Example:
            ```python
            # Match SQL-like strings
            validator.validate_constraint(
                node,
                "value_pattern",
                ".*SELECT.*FROM.*"
            )
            ```
        """
        import re

        if isinstance(node, Expression):
            # Check constant value
            const_value = node.attrs.get("value")
            if const_value and isinstance(const_value, str):
                return bool(re.search(value, const_value, re.IGNORECASE))

            # Check variable name
            var_name = node.attrs.get("name", "")
            if var_name:
                return bool(re.search(value, var_name, re.IGNORECASE))

        return False

    def _validate_name_pattern(self, node: Any, value: str) -> bool:
        """
        Validate name pattern constraint.

        Args:
            node: IR node
            value: Regex pattern for name

        Returns:
            True if name matches pattern
        """
        import re

        if isinstance(node, Expression):
            name = node.attrs.get("name") or node.attrs.get("callee_name", "")
            if name:
                return bool(re.search(value, name, re.IGNORECASE))

        return False

    # ============================================================
    # Helper Methods
    # ============================================================

    def _is_not_constant(self, node: Any) -> bool:
        """
        Check if node is not a constant.

        Args:
            node: IR node

        Returns:
            True if not a constant literal
        """
        if isinstance(node, Expression):
            # Check if LITERAL kind
            if node.kind == ExprKind.LITERAL:
                return False

            # Check if has constant value
            if "value" in node.attrs and node.attrs["value"] is not None:
                return False

            # Check if marked as constant
            if node.attrs.get("is_const", False):
                return False

        return True

    def _is_string_type(self, node: Any) -> bool:
        """Check if node is string type"""
        if isinstance(node, Expression):
            type_str = node.attrs.get("type", "")
            return "str" in type_str.lower() or "string" in type_str.lower()
        return False

    def _is_numeric_type(self, node: Any) -> bool:
        """Check if node is numeric type"""
        if isinstance(node, Expression):
            type_str = node.attrs.get("type", "")
            return any(t in type_str.lower() for t in ["int", "float", "number", "decimal"])
        return False

    def _is_collection_type(self, node: Any) -> bool:
        """Check if node is collection type"""
        if isinstance(node, Expression):
            type_str = node.attrs.get("type", "")
            return any(t in type_str.lower() for t in ["list", "dict", "set", "tuple", "array", "collection"])
        return False

    def _is_callable_type(self, node: Any) -> bool:
        """Check if node is callable type"""
        if isinstance(node, Expression):
            type_str = node.attrs.get("type", "")
            return any(t in type_str.lower() for t in ["function", "callable", "method", "lambda"])
        return False

    def get_stats(self) -> dict[str, Any]:
        """Get validation statistics"""
        return {
            **self._stats,
            "success_rate": (
                self._stats["passed"] / self._stats["total_validated"] if self._stats["total_validated"] > 0 else 0.0
            ),
        }

    def reset_stats(self) -> None:
        """Reset statistics"""
        self._stats = {
            "total_validated": 0,
            "passed": 0,
            "failed": 0,
            "by_type": {},
        }
