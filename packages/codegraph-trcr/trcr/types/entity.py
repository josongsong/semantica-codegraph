"""Entity Protocol - Domain Layer.

Entity represents a code entity that can be matched by taint rules:
    - Call nodes (function/method calls)
    - Read nodes (property/attribute reads)
    - Assignment nodes (variable assignments)

This is a Protocol (interface) to decouple TRCR from specific IR implementations.
The actual Entity implementation comes from IRDocument (Program IR).

RFC-033: Entity requirements derived from predicate evaluation.
RFC-038: Guards field for guard-aware execution.
"""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from trcr.types.guards import GuardType


class Entity(Protocol):
    """Entity protocol for taint rule matching.

    RFC-033: Minimal interface required for rule matching.

    An Entity represents a code entity that can be matched:
        - Call: function/method call (e.g., cursor.execute())
        - Read: property read (e.g., request.GET)
        - Assign: variable assignment

    Required fields (from RFC-033 predicate requirements):
        - base_type: Type of the receiver object
        - call: Call name (for call entities)
        - read: Property name (for read entities)
        - args: Positional arguments
        - kwargs: Keyword arguments
        - kind: Entity kind ("call", "read", "assign")

    This is a Protocol, not a concrete class.
    The actual implementation is provided by the caller (e.g., IRDocument).
    """

    # Identity
    @property
    def id(self) -> str:
        """Unique entity ID."""
        ...

    @property
    def kind(self) -> str:
        """Entity kind: 'call', 'read', 'assign'."""
        ...

    # Type information
    @property
    def base_type(self) -> str | None:
        """Base type of receiver object.

        Examples:
            - cursor.execute() → "sqlite3.Cursor"
            - request.GET → "flask.Request"
            - pymongo.collection.find() → "pymongo.collection.Collection"
        """
        ...

    # Call information
    @property
    def call(self) -> str | None:
        """Call name for call entities.

        Examples:
            - cursor.execute() → "execute"
            - conn.cursor() → "cursor"
            - requests.get() → "get"
        """
        ...

    @property
    def qualified_call(self) -> str | None:
        """Fully qualified call name.

        Examples:
            - sqlite3.Cursor.execute
            - requests.get
            - conn.execute
        """
        ...

    # Property read information
    @property
    def read(self) -> str | None:
        """Property name for read entities.

        Examples:
            - request.GET → "GET"
            - request.args → "args"
        """
        ...

    # Arguments
    @property
    def args(self) -> list[Any]:
        """Positional arguments."""
        ...

    @property
    def kwargs(self) -> dict[str, Any]:
        """Keyword arguments."""
        ...

    def get_arg(self, index: int) -> Any | None:
        """Get argument by index.

        Args:
            index: Argument index (0-based)

        Returns:
            Argument value or None if not found
        """
        ...

    def get_kwarg(self, name: str) -> Any | None:
        """Get keyword argument by name.

        Args:
            name: Keyword argument name

        Returns:
            Argument value or None if not found
        """
        ...

    # Value information (for constraints)
    def is_constant(self, arg_index: int) -> bool:
        """Check if argument is a constant.

        Args:
            arg_index: Argument index

        Returns:
            True if constant, False otherwise
        """
        ...

    def is_string_literal(self, arg_index: int) -> bool:
        """Check if argument is a string literal.

        Args:
            arg_index: Argument index

        Returns:
            True if string literal, False otherwise
        """
        ...

    # RFC-038: Guard information (provided by codegraph)
    @property
    def guards(self) -> "list[GuardType]":
        """Guards detected for this entity.

        RFC-038: Guard-aware Execution.

        Guards are detected by CFG analysis in codegraph.
        codegraph populates this field before sending Entity to trcr.

        Returns:
            List of guards (empty if no guards detected)
        """
        ...


class MockEntity:
    """Mock entity for testing.

    Simple concrete implementation of Entity protocol for tests.
    Production code uses IRDocument entities.
    """

    def __init__(
        self,
        entity_id: str,
        kind: str,
        base_type: str | None = None,
        call: str | None = None,
        read: str | None = None,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        is_const: dict[int, bool] | None = None,
        guards: "list[GuardType] | None" = None,
    ) -> None:
        """Initialize mock entity.

        Args:
            entity_id: Entity ID
            kind: Entity kind
            base_type: Base type
            call: Call name
            read: Property name
            args: Arguments
            kwargs: Keyword arguments
            is_const: Map of arg index → is constant
            guards: List of guards (RFC-038)
        """
        self._id = entity_id
        self._kind = kind
        self._base_type = base_type
        self._call = call
        self._read = read
        self._args = args or []
        self._kwargs = kwargs or {}
        self._is_const = is_const or {}
        self._guards: list[GuardType] = guards or []

    @property
    def id(self) -> str:
        return self._id

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def base_type(self) -> str | None:
        return self._base_type

    @property
    def call(self) -> str | None:
        return self._call

    @property
    def qualified_call(self) -> str | None:
        if self._base_type and self._call:
            return f"{self._base_type}.{self._call}"
        return self._call

    @property
    def read(self) -> str | None:
        return self._read

    @property
    def args(self) -> list[Any]:
        return self._args

    @property
    def kwargs(self) -> dict[str, Any]:
        return self._kwargs

    def get_arg(self, index: int) -> Any | None:
        if 0 <= index < len(self._args):
            return self._args[index]
        return None

    def get_kwarg(self, name: str) -> Any | None:
        return self._kwargs.get(name)

    def is_constant(self, arg_index: int) -> bool:
        return self._is_const.get(arg_index, False)

    def is_string_literal(self, arg_index: int) -> bool:
        arg = self.get_arg(arg_index)
        return isinstance(arg, str) and self.is_constant(arg_index)

    @property
    def guards(self) -> "list[GuardType]":
        """Get guards for this entity."""
        return self._guards
