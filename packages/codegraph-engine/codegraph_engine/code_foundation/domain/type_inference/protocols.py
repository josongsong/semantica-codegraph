"""
RFC-034: Type Inference Protocols

Domain-level interfaces for type inference components.

SOTA: Dependency Inversion Principle (DIP)
- Domain defines interfaces
- Infrastructure implements
- Enables testing, mocking, swapping implementations
"""

from typing import Protocol, runtime_checkable

from .models import ReturnTypeSummary


@runtime_checkable
class GenericInstantiator(Protocol):
    """
    Protocol for generic type instantiation.

    Enables dependency inversion:
    - VariableTypeEnricher depends on protocol (domain)
    - GenericConstraintTracker implements protocol (infrastructure)

    SOTA: Interface segregation + Dependency inversion
    """

    def instantiate_return_type(
        self,
        summary: ReturnTypeSummary,
        arg_types: list[str],
    ) -> str | None:
        """
        Instantiate generic return type with concrete argument types.

        Args:
            summary: Function summary with generic info
            arg_types: Concrete argument types

        Returns:
            Instantiated return type or None if cannot instantiate

        Example:
            summary: identity<T>(x: T) -> T
            arg_types: [int]
            → "int"
        """
        ...


@runtime_checkable
class ClassResolver(Protocol):
    """
    Protocol for class resolution.

    Enables dependency inversion for class-related operations.
    """

    def resolve_constructor_call(
        self,
        class_name: str,
        arg_types: list[str],
    ) -> str | None:
        """
        Resolve constructor call to instantiated class type.

        Args:
            class_name: Class name
            arg_types: Constructor argument types

        Returns:
            Instantiated class type (e.g., "Box[int]") or None
        """
        ...
