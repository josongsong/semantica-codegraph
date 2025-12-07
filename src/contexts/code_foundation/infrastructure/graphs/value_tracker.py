"""
Argument Value Tracker for Context-Sensitive Analysis

Tracks argument values flowing through function calls to enable
precise context-sensitive call graph construction.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ValueKind(Enum):
    """Kind of value being tracked"""

    LITERAL = "literal"  # Literal value (True, 42, "hello")
    VARIABLE = "variable"  # Variable reference
    CONSTANT = "constant"  # Named constant
    UNKNOWN = "unknown"  # Unknown/dynamic value
    MULTIPLE = "multiple"  # Multiple possible values


@dataclass(frozen=True)
class TrackedValue:
    """
    Represents a tracked value

    Can be:
    - Literal: kind=LITERAL, value=42
    - Variable: kind=VARIABLE, value="flag"
    - Constant: kind=CONSTANT, value="MAX_SIZE"
    - Unknown: kind=UNKNOWN, value=None
    - Multiple: kind=MULTIPLE, value=tuple([True, False])
    """

    kind: ValueKind
    value: Any = None
    type_hint: str | None = None  # Type annotation if known

    def __hash__(self):
        """Make hashable for use in sets"""
        # Convert value to hashable type
        hashable_value = self.value
        if isinstance(self.value, list | set):
            hashable_value = tuple(sorted(str(v) for v in self.value))
        elif isinstance(self.value, dict):
            hashable_value = tuple(sorted(self.value.items()))
        return hash((self.kind, hashable_value, self.type_hint))

    def is_concrete(self) -> bool:
        """Check if value is concrete (not unknown)"""
        return self.kind in (ValueKind.LITERAL, ValueKind.CONSTANT)

    def is_truthy(self) -> bool | None:
        """Determine if value is truthy (if possible)"""
        if self.kind == ValueKind.LITERAL:
            return bool(self.value)
        elif self.kind == ValueKind.CONSTANT:
            # Check for common constant patterns
            if isinstance(self.value, str):
                if self.value in ("True", "true", "TRUE"):
                    return True
                if self.value in ("False", "false", "FALSE", "None", "null"):
                    return False
        return None

    def __repr__(self) -> str:
        if self.kind == ValueKind.LITERAL:
            return f"Literal({self.value})"
        elif self.kind == ValueKind.VARIABLE:
            return f"Var({self.value})"
        elif self.kind == ValueKind.CONSTANT:
            return f"Const({self.value})"
        elif self.kind == ValueKind.MULTIPLE:
            return f"Multiple({self.value})"
        else:
            return "Unknown"


@dataclass
class ArgumentValueTracker:
    """
    Tracks argument values flowing through function calls

    Responsibilities:
    1. Extract argument values at call sites
    2. Track value flow through variables
    3. Resolve constants and literals
    4. Handle multiple possible values

    Example:
        FLAG = True

        def process(use_cache: bool):
            if use_cache:
                return fast()
            return slow()

        process(FLAG)  # Tracks: use_cache=True → fast()
        process(False)  # Tracks: use_cache=False → slow()
    """

    # symbol_id → TrackedValue
    _value_cache: dict[str, TrackedValue] = field(default_factory=dict)

    # (call_site, param_name) → Set[TrackedValue]
    _call_site_values: dict[tuple[str, str], set[TrackedValue]] = field(default_factory=dict)

    def track_argument(
        self,
        call_site: str,
        param_name: str,
        value_node: dict[str, Any],
    ) -> TrackedValue:
        """
        Track argument value at call site

        Args:
            call_site: Location of call (e.g., "file.py:10:5")
            param_name: Parameter name
            value_node: AST node representing the argument value

        Returns:
            TrackedValue representing the argument
        """
        # Extract value from node
        tracked = self._extract_value(value_node)

        # Cache for this call site
        key = (call_site, param_name)
        if key not in self._call_site_values:
            self._call_site_values[key] = set()
        self._call_site_values[key].add(tracked)

        logger.debug(
            "tracked_argument",
            call_site=call_site,
            param=param_name,
            value=str(tracked),
        )

        return tracked

    def get_argument_values(
        self,
        call_site: str,
        param_name: str,
    ) -> set[TrackedValue]:
        """Get all possible values for an argument at call site"""
        return self._call_site_values.get((call_site, param_name), set())

    def get_concrete_values(
        self,
        call_site: str,
        param_name: str,
    ) -> dict[str, Any]:
        """
        Get concrete argument values for call site

        Returns dict of param_name → value for concrete values only
        """
        values = self.get_argument_values(call_site, param_name)
        concrete = {}

        for tracked in values:
            if tracked.is_concrete():
                concrete[param_name] = tracked.value

        return concrete

    def _extract_value(self, node: dict[str, Any]) -> TrackedValue:
        """
        Extract value from AST node

        Handles:
        - Literals: True, 42, "hello"
        - Names: FLAG, MAX_SIZE
        - Attributes: obj.attr
        - More complex expressions marked as UNKNOWN
        """
        node_type = node.get("type", "")

        # Literal values
        if node_type in ("true", "false", "boolean_literal"):
            value = node.get("value", "true").lower() == "true"
            return TrackedValue(ValueKind.LITERAL, value, type_hint="bool")

        if node_type in ("number", "integer_literal", "float_literal"):
            value = node.get("value", 0)
            try:
                # Try to parse as number
                if "." in str(value):
                    value = float(value)
                else:
                    value = int(value)
                return TrackedValue(ValueKind.LITERAL, value, type_hint="number")
            except (ValueError, TypeError):
                pass

        if node_type in ("string", "string_literal"):
            value = node.get("value", "")
            return TrackedValue(ValueKind.LITERAL, value, type_hint="str")

        # Variable/name references
        if node_type in ("identifier", "name"):
            name = node.get("name", "")

            # Check if it's a known constant
            if name.isupper():  # Convention: UPPER_CASE = constant
                return TrackedValue(ValueKind.CONSTANT, name)

            # Check cache
            if name in self._value_cache:
                return self._value_cache[name]

            # Otherwise, track as variable
            return TrackedValue(ValueKind.VARIABLE, name)

        # Attribute access: obj.attr
        if node_type in ("attribute", "member_expression"):
            # Simplified: treat as unknown for now
            # More sophisticated: track through object types
            return TrackedValue(ValueKind.UNKNOWN)

        # Default: unknown
        return TrackedValue(ValueKind.UNKNOWN)

    def resolve_constant(self, name: str, value: Any):
        """Register a constant value"""
        self._value_cache[name] = TrackedValue(ValueKind.CONSTANT, value)
        logger.debug("resolved_constant", name=name, value=value)

    def resolve_variable(self, name: str, value: TrackedValue):
        """Register a variable value"""
        self._value_cache[name] = value

    def get_statistics(self) -> dict[str, Any]:
        """Get tracking statistics"""
        total_values = sum(len(values) for values in self._call_site_values.values())
        concrete_count = sum(1 for values in self._call_site_values.values() for v in values if v.is_concrete())

        return {
            "total_call_sites": len(self._call_site_values),
            "total_tracked_values": total_values,
            "concrete_values": concrete_count,
            "concrete_ratio": concrete_count / total_values if total_values else 0,
            "cached_values": len(self._value_cache),
        }

    def __repr__(self) -> str:
        stats = self.get_statistics()
        return (
            f"ArgumentValueTracker("
            f"{stats['total_call_sites']} call sites, "
            f"{stats['concrete_values']}/{stats['total_tracked_values']} concrete)"
        )
