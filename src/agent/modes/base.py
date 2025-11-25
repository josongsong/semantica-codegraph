"""
Base Mode Handler

Provides abstract base class for mode implementations with common utilities.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from src.agent.types import AgentMode, ModeContext, Result, Task

logger = logging.getLogger(__name__)


class BaseModeHandler(ABC):
    """
    Abstract base class for mode handlers.

    Provides common utilities and enforces the mode handler interface.
    """

    def __init__(self, mode: AgentMode):
        """
        Initialize base mode handler.

        Args:
            mode: The mode this handler implements
        """
        self.mode = mode
        self.logger = logging.getLogger(f"{__name__}.{mode.value}")

    async def enter(self, context: ModeContext) -> None:
        """
        Called when entering this mode.

        Default implementation logs entry. Override for custom behavior.

        Args:
            context: Shared mode context
        """
        self.logger.info(f"Entering {self.mode.value} mode")
        self.logger.debug(f"Context: {len(context.current_files)} files, {len(context.current_symbols)} symbols")

    @abstractmethod
    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute mode logic.

        Must be implemented by subclasses.

        Args:
            task: Task to execute
            context: Shared mode context

        Returns:
            Result of execution
        """
        raise NotImplementedError

    async def exit(self, context: ModeContext) -> None:
        """
        Called when exiting this mode.

        Default implementation logs exit. Override for custom cleanup.

        Args:
            context: Shared mode context
        """
        self.logger.info(f"Exiting {self.mode.value} mode")

    def _create_result(
        self,
        data: Any,
        trigger: str | None = None,
        explanation: str = "",
        requires_approval: bool = False,
        **metadata,
    ) -> Result:
        """
        Helper to create Result objects.

        Args:
            data: Result data
            trigger: Optional trigger for next mode
            explanation: Human-readable explanation
            requires_approval: Whether approval is needed
            **metadata: Additional metadata

        Returns:
            Result object
        """
        return Result(
            mode=self.mode,
            data=data,
            trigger=trigger,
            explanation=explanation,
            requires_approval=requires_approval,
            metadata=metadata,
        )
