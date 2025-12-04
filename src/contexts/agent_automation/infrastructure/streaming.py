"""
Streaming Executor for Agent System

Provides async generator-based streaming for LLM responses and tool execution.

Features:
- Real-time token streaming from LLM
- SSE (Server-Sent Events) compatible output
- Partial result streaming for long-running tools
- Backpressure handling
"""

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.contexts.agent_automation.infrastructure.types import Result, Task
from src.infra.observability import get_logger

logger = get_logger(__name__)


class StreamEventType(Enum):
    """Types of streaming events."""

    # LLM events
    TOKEN = "token"  # Single token from LLM
    THINKING = "thinking"  # Model reasoning (CoT)
    CONTENT = "content"  # Final content chunk

    # Tool events
    TOOL_START = "tool_start"  # Tool execution started
    TOOL_PROGRESS = "tool_progress"  # Tool progress update
    TOOL_RESULT = "tool_result"  # Tool execution completed

    # Flow events
    MODE_CHANGE = "mode_change"  # FSM mode transition
    APPROVAL_NEEDED = "approval_needed"  # Human approval required
    ERROR = "error"  # Error occurred
    DONE = "done"  # Stream completed


@dataclass
class StreamEvent:
    """Single streaming event."""

    event_type: StreamEventType
    data: Any
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        """Convert to SSE format."""
        payload = {
            "type": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            **self.metadata,
        }
        return f"data: {json.dumps(payload)}\n\n"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class StreamingExecutor:
    """
    Executes agent tasks with streaming output.

    Provides real-time updates during:
    - LLM response generation
    - Tool execution
    - Mode transitions

    Usage:
        executor = StreamingExecutor(fsm, llm_adapter)

        async for event in executor.execute_streaming(task):
            if event.event_type == StreamEventType.TOKEN:
                print(event.data, end="", flush=True)
            elif event.event_type == StreamEventType.TOOL_RESULT:
                print(f"\\nTool result: {event.data}")
    """

    def __init__(
        self,
        fsm: Any,  # AgentFSM
        llm_adapter: Any | None = None,
        stream_buffer_size: int = 100,
        token_delay_ms: float = 0,  # Artificial delay for UI smoothing
    ):
        """
        Initialize streaming executor.

        Args:
            fsm: Agent FSM instance
            llm_adapter: LLM adapter with streaming support
            stream_buffer_size: Max events to buffer
            token_delay_ms: Artificial delay between tokens (for UI)
        """
        self.fsm = fsm
        self.llm = llm_adapter
        self._buffer_size = stream_buffer_size
        self._token_delay = token_delay_ms / 1000  # Convert to seconds
        self._active_streams: dict[str, asyncio.Queue] = {}

    async def execute_streaming(
        self,
        task: Task,
        session_id: str | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Execute task with streaming output.

        Args:
            task: Task to execute
            session_id: Optional session identifier

        Yields:
            StreamEvent objects as execution progresses
        """
        session_id = session_id or f"stream-{int(time.time() * 1000)}"
        queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue(maxsize=self._buffer_size)
        self._active_streams[session_id] = queue

        try:
            # Start execution in background
            exec_task = asyncio.create_task(self._execute_with_events(task, queue, session_id))

            # Yield events as they arrive
            while True:
                event = await queue.get()
                if event is None:  # Sentinel for completion
                    break
                yield event

                if event.event_type == StreamEventType.DONE:
                    break

            # Ensure execution task completes
            await exec_task

        except asyncio.CancelledError:
            logger.info("stream_cancelled", session_id=session_id)
            yield StreamEvent(
                event_type=StreamEventType.ERROR,
                data={"message": "Stream cancelled"},
            )
        finally:
            self._active_streams.pop(session_id, None)

    async def _execute_with_events(
        self,
        task: Task,
        queue: asyncio.Queue,
        session_id: str,
    ) -> None:
        """Execute task and push events to queue."""
        try:
            # Emit mode info
            await queue.put(
                StreamEvent(
                    event_type=StreamEventType.MODE_CHANGE,
                    data={
                        "mode": self.fsm.current_mode.value,
                        "task_id": task.task_id if hasattr(task, "task_id") else None,
                    },
                )
            )

            # Execute through FSM
            result = await self._execute_with_streaming(task, queue)

            # Emit final result
            await queue.put(
                StreamEvent(
                    event_type=StreamEventType.DONE,
                    data={
                        "success": result.trigger != "error",
                        "trigger": result.trigger,
                        "data": result.data,
                    },
                )
            )

        except Exception as e:
            logger.error("streaming_execution_error", error=str(e), exc_info=True)
            await queue.put(
                StreamEvent(
                    event_type=StreamEventType.ERROR,
                    data={"message": str(e), "type": type(e).__name__},
                )
            )
        finally:
            await queue.put(None)  # Sentinel

    async def _execute_with_streaming(
        self,
        task: Task,
        queue: asyncio.Queue,
    ) -> Result:
        """Execute task with streaming LLM and tool calls."""
        # Get current mode handler
        mode = self.fsm.current_mode
        handler = self.fsm._modes.get(mode)

        if not handler:
            return Result(trigger="error", data={"message": f"No handler for mode {mode}"})

        # If LLM is available and supports streaming, use it
        if self.llm and hasattr(self.llm, "stream_generate"):
            # Stream LLM response
            async for token in self._stream_llm_response(task.query):
                await queue.put(StreamEvent(event_type=StreamEventType.TOKEN, data=token))
                if self._token_delay > 0:
                    await asyncio.sleep(self._token_delay)

        # Execute mode handler
        result = await handler.execute(task, self.fsm.context)

        # Check for mode transition
        if result.trigger:
            new_mode = self.fsm._get_next_mode(result.trigger)
            if new_mode and new_mode != mode:
                await self.fsm.transition(result.trigger)
                await queue.put(
                    StreamEvent(
                        event_type=StreamEventType.MODE_CHANGE,
                        data={"mode": new_mode.value, "trigger": result.trigger},
                    )
                )

        return result

    async def _stream_llm_response(
        self,
        prompt: str,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from LLM."""
        if not self.llm:
            return

        try:
            async for token in self.llm.stream_generate(prompt):
                yield token
        except Exception as e:
            logger.warning("llm_streaming_error", error=str(e))
            # Fall back to non-streaming
            response = await self.llm.generate(prompt)
            yield response

    async def stream_tool_execution(
        self,
        tool: Any,  # BaseTool
        input_data: dict[str, Any],
        queue: asyncio.Queue,
    ) -> Any:
        """
        Execute tool with progress streaming.

        Args:
            tool: Tool to execute
            input_data: Tool input
            queue: Event queue

        Returns:
            Tool result
        """
        tool_name = getattr(tool, "name", tool.__class__.__name__)

        # Emit start event
        await queue.put(
            StreamEvent(
                event_type=StreamEventType.TOOL_START,
                data={"tool": tool_name, "input": input_data},
            )
        )

        try:
            # Execute tool
            start_time = time.time()
            result = await tool.execute(input_data)
            elapsed = time.time() - start_time

            # Emit result event
            await queue.put(
                StreamEvent(
                    event_type=StreamEventType.TOOL_RESULT,
                    data={
                        "tool": tool_name,
                        "result": result.model_dump() if hasattr(result, "model_dump") else result,
                        "elapsed_ms": elapsed * 1000,
                    },
                )
            )

            return result

        except Exception as e:
            await queue.put(
                StreamEvent(
                    event_type=StreamEventType.ERROR,
                    data={"tool": tool_name, "error": str(e)},
                )
            )
            raise

    def cancel_stream(self, session_id: str) -> bool:
        """
        Cancel an active stream.

        Args:
            session_id: Session to cancel

        Returns:
            True if cancelled, False if not found
        """
        if session_id in self._active_streams:
            # Put cancellation sentinel
            try:
                self._active_streams[session_id].put_nowait(None)
                return True
            except asyncio.QueueFull:
                return False
        return False

    @property
    def active_sessions(self) -> list[str]:
        """Get list of active streaming sessions."""
        return list(self._active_streams.keys())


class SSEFormatter:
    """Format streaming events for Server-Sent Events."""

    @staticmethod
    def format_event(event: StreamEvent) -> str:
        """Format single event as SSE."""
        return event.to_sse()

    @staticmethod
    async def format_stream(
        events: AsyncGenerator[StreamEvent, None],
    ) -> AsyncGenerator[str, None]:
        """Format event stream as SSE stream."""
        async for event in events:
            yield SSEFormatter.format_event(event)

    @staticmethod
    def keepalive() -> str:
        """Generate keepalive comment for SSE."""
        return ": keepalive\n\n"
