"""
Port Input Validators

CRITICAL: 입력 검증을 중앙화하여 모든 Port 구현체가 동일한 검증 로직 사용.

Philosophy:
- Fail Fast: 잘못된 입력은 즉시 거부
- Clear Errors: 구체적인 에러 메시지
- No Guessing: 경계값은 명확히 명시

SOTA-Level: No magic numbers, all limits documented.
"""

from typing import Any


class PortInputValidator:
    """
    Port 입력 검증기.

    모든 Port의 입력 검증을 중앙 관리.
    """

    # Hard limits (Safety)
    MAX_PATHS_HARD_LIMIT = 10000
    MAX_DEPTH_HARD_LIMIT = 100
    MIN_TIMEOUT_SECONDS = 0.1
    MAX_TIMEOUT_SECONDS = 300.0

    # Recommended limits (Performance)
    MAX_PATHS_RECOMMENDED = 1000
    MAX_DEPTH_RECOMMENDED = 50
    TIMEOUT_RECOMMENDED = 60.0

    @classmethod
    def validate_max_paths(cls, max_paths: int, *, strict: bool = False) -> None:
        """
        Validate max_paths parameter.

        Args:
            max_paths: Number of paths to find
            strict: If True, enforce recommended limits

        Raises:
            ValueError: If max_paths is invalid
        """
        if not isinstance(max_paths, int):
            raise ValueError(f"max_paths must be int, got {type(max_paths).__name__}")

        if max_paths <= 0:
            raise ValueError(f"max_paths must be > 0, got {max_paths}")

        if max_paths > cls.MAX_PATHS_HARD_LIMIT:
            raise ValueError(f"max_paths exceeds hard limit: {max_paths} > {cls.MAX_PATHS_HARD_LIMIT}")

        if strict and max_paths > cls.MAX_PATHS_RECOMMENDED:
            raise ValueError(
                f"max_paths exceeds recommended limit: {max_paths} > {cls.MAX_PATHS_RECOMMENDED} "
                f"(use strict=False to allow up to {cls.MAX_PATHS_HARD_LIMIT})"
            )

    @classmethod
    def validate_max_depth(cls, max_depth: int, *, strict: bool = False) -> None:
        """
        Validate max_depth parameter.

        Args:
            max_depth: Max traversal depth
            strict: If True, enforce recommended limits

        Raises:
            ValueError: If max_depth is invalid
        """
        if not isinstance(max_depth, int):
            raise ValueError(f"max_depth must be int, got {type(max_depth).__name__}")

        if max_depth <= 0:
            raise ValueError(f"max_depth must be > 0, got {max_depth}")

        if max_depth > cls.MAX_DEPTH_HARD_LIMIT:
            raise ValueError(f"max_depth exceeds hard limit: {max_depth} > {cls.MAX_DEPTH_HARD_LIMIT}")

        if strict and max_depth > cls.MAX_DEPTH_RECOMMENDED:
            raise ValueError(
                f"max_depth exceeds recommended limit: {max_depth} > {cls.MAX_DEPTH_RECOMMENDED} "
                f"(use strict=False to allow up to {cls.MAX_DEPTH_HARD_LIMIT})"
            )

    @classmethod
    def validate_timeout(cls, timeout_seconds: float) -> None:
        """
        Validate timeout_seconds parameter.

        Args:
            timeout_seconds: Timeout in seconds

        Raises:
            ValueError: If timeout is invalid
        """
        if not isinstance(timeout_seconds, (int, float)):
            raise ValueError(f"timeout_seconds must be numeric, got {type(timeout_seconds).__name__}")

        if timeout_seconds < cls.MIN_TIMEOUT_SECONDS:
            raise ValueError(f"timeout_seconds too small: {timeout_seconds} < {cls.MIN_TIMEOUT_SECONDS}")

        if timeout_seconds > cls.MAX_TIMEOUT_SECONDS:
            raise ValueError(f"timeout_seconds too large: {timeout_seconds} > {cls.MAX_TIMEOUT_SECONDS}")

    @classmethod
    def validate_compiled_policy(cls, compiled_policy: Any) -> None:
        """
        Validate compiled_policy parameter.

        Args:
            compiled_policy: CompiledPolicy object

        Raises:
            ValueError: If compiled_policy is invalid
        """
        if compiled_policy is None:
            raise ValueError("compiled_policy cannot be None")

        if not hasattr(compiled_policy, "flow_query"):
            raise ValueError("compiled_policy must have 'flow_query' attribute (CompiledPolicy expected)")

    @classmethod
    def validate_ir_document(cls, ir_doc: Any) -> None:
        """
        Validate IR document parameter.

        Args:
            ir_doc: IR document object

        Raises:
            ValueError: If ir_doc is invalid
        """
        if ir_doc is None:
            raise ValueError("ir_doc cannot be None")

        if not hasattr(ir_doc, "get_all_expressions"):
            raise ValueError("ir_doc must have 'get_all_expressions' method (IRDocument expected)")

    @classmethod
    def validate_path(cls, path: Any) -> None:
        """
        Validate path parameter.

        Args:
            path: PathResult object

        Raises:
            ValueError: If path is invalid
        """
        if path is None:
            raise ValueError("path cannot be None")

    @classmethod
    def validate_constraints(cls, constraints: dict[str, Any]) -> None:
        """
        Validate constraints parameter.

        Args:
            constraints: Constraint specifications

        Raises:
            KeyError: If unknown constraint key found
            TypeError: If constraint value has wrong type
        """
        KNOWN_CONSTRAINTS = {
            "max_length",
            "min_confidence",
            "require_sanitizer",
            "max_paths",
            "max_depth",
        }

        for key in constraints:
            if key not in KNOWN_CONSTRAINTS:
                raise KeyError(f"Unknown constraint: '{key}'. Valid constraints: {sorted(KNOWN_CONSTRAINTS)}")

        # Type validation
        if "max_length" in constraints:
            if not isinstance(constraints["max_length"], int):
                raise TypeError(f"constraint 'max_length' must be int, got {type(constraints['max_length']).__name__}")

        if "min_confidence" in constraints:
            if not isinstance(constraints["min_confidence"], (int, float)):
                raise TypeError(
                    f"constraint 'min_confidence' must be numeric, got {type(constraints['min_confidence']).__name__}"
                )

        if "require_sanitizer" in constraints:
            if not isinstance(constraints["require_sanitizer"], bool):
                raise TypeError(
                    f"constraint 'require_sanitizer' must be bool, "
                    f"got {type(constraints['require_sanitizer']).__name__}"
                )


class QueryEngineValidator:
    """
    QueryEngine 전용 검증기.

    execute_flow_query의 모든 파라미터를 한 번에 검증.
    """

    @staticmethod
    def validate_all(
        compiled_policy: Any,
        max_paths: int,
        max_depth: int,
        timeout_seconds: float,
        *,
        strict: bool = False,
    ) -> None:
        """
        Validate all execute_flow_query parameters.

        Args:
            compiled_policy: CompiledPolicy object
            max_paths: Number of paths
            max_depth: Traversal depth
            timeout_seconds: Timeout in seconds
            strict: Enforce recommended limits

        Raises:
            ValueError: If any parameter is invalid
        """
        PortInputValidator.validate_compiled_policy(compiled_policy)
        PortInputValidator.validate_max_paths(max_paths, strict=strict)
        PortInputValidator.validate_max_depth(max_depth, strict=strict)
        PortInputValidator.validate_timeout(timeout_seconds)


class AtomMatcherValidator:
    """
    AtomMatcher 전용 검증기.
    """

    @staticmethod
    def validate_all(ir_doc: Any, atoms: list) -> None:
        """
        Validate all match_all parameters.

        Args:
            ir_doc: IR document
            atoms: Atom specifications (can be empty)

        Raises:
            ValueError: If any parameter is invalid
        """
        PortInputValidator.validate_ir_document(ir_doc)

        if not isinstance(atoms, list):
            raise ValueError(f"atoms must be list, got {type(atoms).__name__}")


class ConstraintValidatorValidator:
    """
    ConstraintValidator 전용 검증기.
    """

    @staticmethod
    def validate_all(path: Any, constraints: dict) -> None:
        """
        Validate all validate_path parameters.

        Args:
            path: PathResult object
            constraints: Constraint specifications

        Raises:
            ValueError: If any parameter is invalid
            KeyError: If unknown constraint found
        """
        PortInputValidator.validate_path(path)

        if not isinstance(constraints, dict):
            raise ValueError(f"constraints must be dict, got {type(constraints).__name__}")

        if constraints:  # Only validate non-empty constraints
            PortInputValidator.validate_constraints(constraints)
