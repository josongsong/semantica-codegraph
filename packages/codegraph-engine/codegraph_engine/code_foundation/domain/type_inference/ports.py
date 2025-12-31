"""
Type Inference Ports (Hexagonal)

RFC-030: Self-contained Type Inference with Pyright Fallback

Ports:
- ITypeInferencer: Main type inference interface
- IBuiltinMethodRegistry: Builtin method return type registry

Hexagonal Pattern:
    ┌─────────────────────┐
    │   Domain            │
    │  ITypeInferencer    │ ← Port (interface)
    │  IBuiltinMethod...  │
    └─────────────────────┘
              ↑ implements
    ┌─────────────────────┐
    │  Infrastructure     │
    │  InferredType...    │ ← Adapter (concrete)
    │  YamlBuiltinMethod..│
    └─────────────────────┘

SOLID:
    - Single Responsibility: Type inference only
    - Open/Closed: New strategies via chain
    - Liskov: All adapters substitutable
    - Interface Segregation: Minimal ports
    - Dependency Inversion: Domain defines contracts
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .models import ExpressionTypeRequest, InferContext, InferResult

if TYPE_CHECKING:
    from pathlib import Path


@runtime_checkable
class ITypeInferencer(Protocol):
    """
    Type inference port (Hexagonal).

    Responsibility:
        Infer types for expressions using fallback chain:
        1. Annotation
        2. Literal
        3. Call Graph
        4. Builtin Method
        5. Pyright (fallback)

    Implementation:
        Infrastructure Layer: InferredTypeResolver

    Usage:
        inferencer = container.get(ITypeInferencer)
        result = inferencer.infer(request, context)
        print(f"{result.inferred_type} via {result.source}")

    Thread-Safety:
        Implementations should be thread-safe for read operations.
    """

    def infer(
        self,
        request: ExpressionTypeRequest,
        context: InferContext,
    ) -> InferResult:
        """
        Infer type for an expression.

        Args:
            request: Expression type request
            context: Inference context (signatures, SCCP, etc.)

        Returns:
            InferResult with inferred type and source

        Post-condition:
            - Always returns a valid InferResult
            - If inference fails, returns InferResult.unknown()
            - result.source indicates where type came from

        Performance:
            - Self-contained inference: O(1) lookups
            - Pyright fallback: LSP call (slower)
        """
        ...

    def infer_batch(
        self,
        requests: list[ExpressionTypeRequest],
        context: InferContext,
    ) -> list[InferResult]:
        """
        Infer types for multiple expressions.

        Args:
            requests: List of expression type requests
            context: Shared inference context

        Returns:
            List of InferResults (same order as requests)

        Performance:
            Batch operations may be more efficient for Pyright fallback.
        """
        ...

    @property
    def stats(self) -> dict[str, int]:
        """
        Get inference statistics.

        Returns:
            {
                "total_inferences": N,
                "annotation_hits": M,
                "literal_hits": K,
                "call_graph_hits": J,
                "builtin_method_hits": L,
                "pyright_fallbacks": P,
                "unknown_count": U,
            }
        """
        ...

    def reset_stats(self) -> None:
        """Reset inference statistics."""
        ...


@runtime_checkable
class IBuiltinMethodRegistry(Protocol):
    """
    Builtin method return type registry port.

    Responsibility:
        Provide return types for builtin methods (str.upper, list.append, etc.)

    Implementation:
        Infrastructure Layer: YamlBuiltinMethodRegistry

    Usage:
        registry = container.get(IBuiltinMethodRegistry)
        return_type = registry.get_return_type("str", "upper")  # → "str"

    Data Source:
        YAML configuration files with builtin method definitions.
    """

    def get_return_type(
        self,
        receiver_type: str,
        method_name: str,
    ) -> str | None:
        """
        Get return type for builtin method.

        Args:
            receiver_type: Receiver type (e.g., "str", "list", "dict")
            method_name: Method name (e.g., "upper", "append", "get")

        Returns:
            Return type string or None if not found

        Examples:
            get_return_type("str", "upper") → "str"
            get_return_type("list", "pop") → "T"  (generic)
            get_return_type("dict", "get") → "V | None"
            get_return_type("unknown", "foo") → None

        Note:
            Generic placeholders (T, V, K) are returned as-is.
            Caller should resolve them based on context.
        """
        ...

    def get_all_methods(self, receiver_type: str) -> dict[str, str]:
        """
        Get all methods for a receiver type.

        Args:
            receiver_type: Receiver type (e.g., "str")

        Returns:
            Dict of method_name → return_type
        """
        ...

    def has_type(self, receiver_type: str) -> bool:
        """Check if receiver type is registered."""
        ...

    def supported_types(self) -> list[str]:
        """Get list of supported receiver types."""
        ...


@runtime_checkable
class IPyrightFallback(Protocol):
    """
    Pyright fallback port for type inference.

    Responsibility:
        Query Pyright LSP for type information when self-contained
        inference fails.

    Implementation:
        Infrastructure Layer: PyrightFallbackAdapter

    Usage:
        This is an internal port used by ITypeInferencer.
        Not typically used directly by application code.

    Thread-Safety:
        Must handle LSP server lifecycle appropriately.
    """

    def query_type(
        self,
        file_path: "Path",
        line: int,
        column: int,
    ) -> str | None:
        """
        Query type at position.

        Args:
            file_path: Source file path
            line: Line number (1-indexed)
            column: Column number (0-indexed)

        Returns:
            Type string or None if not found

        Raises:
            RuntimeError: If Pyright LSP is not available
        """
        ...

    def is_available(self) -> bool:
        """Check if Pyright LSP is available."""
        ...

    @property
    def call_count(self) -> int:
        """Number of Pyright calls made."""
        ...
