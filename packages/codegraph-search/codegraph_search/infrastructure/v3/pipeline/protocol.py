"""
Pipeline Step Protocol

SOLID: Interface Segregation, Dependency Inversion
"""

from typing import Protocol

from .context import SearchContext


class SearchPipelineStep(Protocol):
    """
    Protocol for search pipeline steps.

    Each step:
    - Receives immutable SearchContext
    - Performs one responsibility (SRP)
    - Returns new SearchContext
    - Is independently testable
    """

    async def execute(self, context: SearchContext) -> SearchContext:
        """
        Execute pipeline step.

        Args:
            context: Current search context (immutable)

        Returns:
            New search context with step results
        """
        ...


__all__ = ["SearchPipelineStep"]
