"""
Base Tool

Abstract base class for all agent tools.

Design principles:
- Each tool has clear input/output schemas (Pydantic models)
- Tools are stateless and can be called multiple times
- Tools handle their own error cases gracefully
- Tools return structured data suitable for LLM consumption
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from src.common.observability import get_logger

logger = get_logger(__name__)
# Type variables for input/output schemas
InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""

    pass


class BaseTool(ABC, Generic[InputT, OutputT]):
    """
    Abstract base class for agent tools.

    Each tool must implement:
    - name: Unique tool identifier
    - description: What the tool does (for LLM)
    - input_schema: Pydantic model for input validation
    - output_schema: Pydantic model for output validation
    - _execute: Core tool logic

    Usage:
        class MyTool(BaseTool[MyInput, MyOutput]):
            name = "my_tool"
            description = "Does something useful"
            input_schema = MyInput
            output_schema = MyOutput

            async def _execute(self, input_data: MyInput) -> MyOutput:
                # Tool logic here
                return MyOutput(...)

        # Use tool
        tool = MyTool()
        result = await tool.execute(MyInput(...))
    """

    # Subclasses must define these
    name: str
    description: str
    input_schema: type[InputT]
    output_schema: type[OutputT]

    def __init__(self):
        """Initialize tool."""
        # Validate that subclass defined required attributes
        if not hasattr(self, "name"):
            raise NotImplementedError("Tool must define 'name' attribute")
        if not hasattr(self, "description"):
            raise NotImplementedError("Tool must define 'description' attribute")
        if not hasattr(self, "input_schema"):
            raise NotImplementedError("Tool must define 'input_schema' attribute")
        if not hasattr(self, "output_schema"):
            raise NotImplementedError("Tool must define 'output_schema' attribute")

    async def execute(self, input_data: InputT | dict[str, Any]) -> OutputT:
        """
        Execute tool with given input.

        Args:
            input_data: Tool input (Pydantic model or dict)

        Returns:
            Tool output (Pydantic model)

        Raises:
            ToolExecutionError: If tool execution fails
        """
        start_time = time.time()

        try:
            # Validate and convert input if needed
            if isinstance(input_data, dict):
                input_data = self.input_schema(**input_data)
            elif not isinstance(input_data, self.input_schema):
                raise ToolExecutionError(
                    f"Invalid input type: expected {self.input_schema.__name__}, got {type(input_data).__name__}"
                )

            # Execute tool logic
            logger.info(f"Executing tool: {self.name}")
            result = await self._execute(input_data)

            # Validate output
            if not isinstance(result, self.output_schema):
                raise ToolExecutionError(
                    f"Invalid output type: expected {self.output_schema.__name__}, got {type(result).__name__}"
                )

            execution_time = time.time() - start_time
            logger.info(f"Tool {self.name} completed in {execution_time:.2f}s")

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Tool {self.name} failed after {execution_time:.2f}s: {e}", exc_info=True)

            # Return error result if possible
            try:
                # Try to create an error result using the output schema
                error_result = self.output_schema(
                    success=False,
                    error=str(e),
                )
                return error_result
            except Exception:
                # If we can't create error result, raise original exception
                raise ToolExecutionError(f"Tool {self.name} failed: {e}") from e

    @abstractmethod
    async def _execute(self, input_data: InputT) -> OutputT:
        """
        Core tool execution logic (must be implemented by subclass).

        Args:
            input_data: Validated input data

        Returns:
            Tool output

        Raises:
            Exception: Any exception will be caught and converted to error result
        """
        pass

    def get_schema(self) -> dict[str, Any]:
        """
        Get tool schema for LLM (OpenAI function calling format).

        Returns:
            Dict with tool name, description, and parameters schema
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema.model_json_schema(),
        }

    def __repr__(self) -> str:
        """String representation."""
        return f"{self.__class__.__name__}(name='{self.name}')"
