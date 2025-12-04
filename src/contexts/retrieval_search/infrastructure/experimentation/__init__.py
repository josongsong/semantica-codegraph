"""
Experimentation Framework

A/B testing and shadow mode experimentation for retriever improvements.
"""

from typing import TYPE_CHECKING

from src.contexts.retrieval_search.infrastructure.experimentation.ab_testing import ABTest, ExperimentResult, Variant
from src.contexts.retrieval_search.infrastructure.experimentation.shadow_mode import ShadowResult

if TYPE_CHECKING:
    from src.contexts.retrieval_search.infrastructure.experimentation.ab_testing import ABTestManager
    from src.contexts.retrieval_search.infrastructure.experimentation.shadow_mode import ShadowModeRunner


def __getattr__(name: str):
    """Lazy import for heavy manager classes."""
    if name == "ABTestManager":
        from src.contexts.retrieval_search.infrastructure.experimentation.ab_testing import ABTestManager

        return ABTestManager
    if name == "ShadowModeRunner":
        from src.contexts.retrieval_search.infrastructure.experimentation.shadow_mode import ShadowModeRunner

        return ShadowModeRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Models (lightweight)
    "ABTest",
    "ExperimentResult",
    "Variant",
    "ShadowResult",
    # Managers (heavy - lazy import via TYPE_CHECKING)
    "ABTestManager",
    "ShadowModeRunner",
]
