"""
Span Immutability Guard (Runtime Validation)

Detects accidental Span mutation at runtime.
Only enabled in development/test environments.

Design:
- Monkey-patch __setattr__ in dev mode
- Zero overhead in production (disabled by default)
- Clear error messages for debugging
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import Span


class SpanMutationError(Exception):
    """Raised when attempting to mutate frozen Span"""

    pass


def enable_span_mutation_guard():
    """
    Enable runtime guard against Span mutation (dev/test only).

    This monkey-patches Span.__setattr__ to raise SpanMutationError
    on any mutation attempt.

    WARNING: Only use in development/test. Has performance overhead.

    Usage:
        # In conftest.py or test setup
        from codegraph_engine.code_foundation.infrastructure.ir.models.span_guard import (
            enable_span_mutation_guard
        )

        enable_span_mutation_guard()
    """
    from .core import Span

    original_setattr = Span.__setattr__

    def guarded_setattr(self, name, value):
        # Allow __init__ to set attributes
        if not hasattr(self, "start_line"):
            return original_setattr(self, name, value)

        # After init: mutation not allowed
        raise SpanMutationError(
            f"Attempted to mutate frozen Span.{name} = {value!r}. "
            f"Span is immutable (frozen=True). "
            f"Create a new Span instead using SpanPool.intern()."
        )

    Span.__setattr__ = guarded_setattr  # type: ignore


def disable_span_mutation_guard():
    """Disable runtime guard (restore original behavior)"""
    from .core import Span

    # Restore to dataclass default
    Span.__setattr__ = object.__setattr__  # type: ignore
