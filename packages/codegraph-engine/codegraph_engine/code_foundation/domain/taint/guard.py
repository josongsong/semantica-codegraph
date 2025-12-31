"""
RFC-030: Guard Condition Domain Models

Domain models for guard-aware taint analysis.
These models are pure domain logic, independent of infrastructure.

Hexagonal Architecture:
- Domain Layer (this): Business logic, no external dependencies
- Infrastructure Layer: DominatorTree implementation
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    pass


# ============================================================
# RFC-030 Phase 1: Argument Shape (Domain Model)
# ============================================================


class ArgShape(Enum):
    """
    RFC-030: Structured argument shape types.

    Domain Model - represents semantic classification of arguments.
    Used for subprocess command injection detection.

    Examples:
        - LIST_LITERAL: subprocess.run(["cmd", arg])  → safer
        - STRING: subprocess.run(cmd_str)  → risky with shell=True
    """

    LIST_LITERAL = "list_literal"  # [a, b, c]
    TUPLE_LITERAL = "tuple_literal"  # (a, b, c)
    DICT_LITERAL = "dict_literal"  # {a: 1, b: 2}
    STRING = "string"  # "hello"
    NAME = "name"  # variable reference
    CALL = "call"  # function()
    ATTRIBUTE = "attribute"  # obj.attr
    SUBSCRIPT = "subscript"  # arr[0]
    BINARY_OP = "binary_op"  # a + b
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ArgInfo:
    """
    RFC-030: Structured argument information.

    Immutable domain value object.

    Attributes:
        shape: Argument shape classification
        const_value: Constant value if known (from SCCP)
        is_tainted: Whether argument is tainted
    """

    shape: ArgShape
    const_value: Any = None
    is_tainted: bool = False

    @property
    def is_const(self) -> bool:
        """Check if argument has a known constant value."""
        return self.const_value is not None

    @property
    def is_collection(self) -> bool:
        """Check if argument is a collection literal (safer for subprocess)."""
        return self.shape in (ArgShape.LIST_LITERAL, ArgShape.TUPLE_LITERAL)


# ============================================================
# RFC-030 Phase 2: Guard Condition (Domain Model)
# ============================================================


@runtime_checkable
class DominatorPort(Protocol):
    """
    Port for dominator analysis.

    Hexagonal Architecture: Domain defines this port,
    Infrastructure (DominatorTree) implements it.
    """

    def dominates(self, dominator: str, dominated: str) -> bool:
        """
        Check if 'dominator' block dominates 'dominated' block.

        Args:
            dominator: Potential dominator block ID
            dominated: Block ID to check

        Returns:
            True if dominator dominates dominated
        """
        ...


@dataclass(frozen=True)
class GuardCondition:
    """
    RFC-030: Guard condition with Dominator-based validation.

    Domain Model - represents a control flow guard that protects a variable.

    A valid guard:
    1. Checks a condition (validation)
    2. Exits on failure (abort, raise, return)
    3. Guard block dominates sink block (all paths pass through guard)

    Examples:
        ```python
        if x not in ALLOWED:
            abort()  # exit-on-fail
        use(x)  # x is guarded here
        ```

    Attributes:
        guard_block_id: CFG block containing the guard check
        guarded_var: Variable being protected
        exit_on_fail: True if guard exits on failure
        ssa_version: SSA version for precise value tracking
    """

    guard_block_id: str
    guarded_var: str
    exit_on_fail: bool = False
    ssa_version: int | None = None

    def is_valid_guard(self, sink_block_id: str, dominator: DominatorPort) -> bool:
        """
        Validate guard using Dominator analysis.

        RFC-030: A guard is valid if:
        1. Guard has exit-on-fail semantics
        2. Guard block dominates sink block

        Args:
            sink_block_id: Block containing the sink
            dominator: Dominator port (infrastructure provides implementation)

        Returns:
            True if guard protects the sink

        Note:
            Uses DominatorPort (not DominatorTree directly) for
            Hexagonal Architecture compliance.
        """
        if not self.exit_on_fail:
            return False

        # Guard block must dominate sink block
        return dominator.dominates(self.guard_block_id, sink_block_id)


# ============================================================
# RFC-030 Phase 3: Analysis Modes (Domain Model)
# ============================================================


class AnalysisMode(Enum):
    """
    RFC-030: Analysis precision modes.

    Domain Model - represents trade-off between precision and recall.

    - AUDIT: High recall, may have FPs (for security audits)
    - PRECISION: High precision, may miss some vulns (for CI/CD)
    """

    AUDIT = "audit"
    PRECISION = "precision"

    @property
    def prioritizes_recall(self) -> bool:
        """Check if mode prioritizes finding all vulnerabilities."""
        return self == AnalysisMode.AUDIT

    @property
    def prioritizes_precision(self) -> bool:
        """Check if mode prioritizes avoiding false positives."""
        return self == AnalysisMode.PRECISION
