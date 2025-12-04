"""
Parallel Tool Executor for Agent System

Executes multiple tools concurrently with:
- Dependency DAG resolution
- Parallel execution via asyncio.gather
- Timeout handling per tool and globally
- Result aggregation
"""

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.contexts.agent_automation.infrastructure.tools.base import BaseTool, ToolExecutionError
from src.infra.observability import get_logger, record_histogram

logger = get_logger(__name__)


class ExecutionStatus(Enum):
    """Tool execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


@dataclass
class ToolCall:
    """Single tool call request."""

    tool_name: str
    input_data: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)  # IDs of dependent calls
    call_id: str = ""
    timeout_seconds: float = 30.0

    def __post_init__(self):
        if not self.call_id:
            self.call_id = f"{self.tool_name}_{int(time.time() * 1000)}"


@dataclass
class ToolResult:
    """Result of tool execution."""

    call_id: str
    tool_name: str
    status: ExecutionStatus
    result: Any = None
    error: str | None = None
    elapsed_ms: float = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class ParallelToolExecutor:
    """
    Executes tools in parallel with dependency resolution.

    Features:
    - DAG-based execution ordering
    - Parallel execution of independent tools
    - Per-tool and global timeouts
    - Graceful degradation on failures

    Usage:
        executor = ParallelToolExecutor(tools={
            "search": SearchTool(),
            "read_file": ReadFileTool(),
        })

        calls = [
            ToolCall("search", {"query": "User class"}),
            ToolCall("read_file", {"path": "models.py"}, depends_on=["search_123"]),
        ]

        results = await executor.execute_parallel(calls)
    """

    def __init__(
        self,
        tools: dict[str, BaseTool],
        default_timeout: float = 30.0,
        global_timeout: float = 120.0,
        max_concurrent: int = 10,
        fail_fast: bool = False,
    ):
        """
        Initialize parallel executor.

        Args:
            tools: Map of tool name to tool instance
            default_timeout: Default timeout per tool (seconds)
            global_timeout: Maximum total execution time
            max_concurrent: Max concurrent tool executions
            fail_fast: Stop all on first failure
        """
        self.tools = tools
        self.default_timeout = default_timeout
        self.global_timeout = global_timeout
        self.max_concurrent = max_concurrent
        self.fail_fast = fail_fast

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._results: dict[str, ToolResult] = {}

    async def execute_parallel(
        self,
        calls: list[ToolCall],
    ) -> list[ToolResult]:
        """
        Execute tool calls in parallel respecting dependencies.

        Args:
            calls: List of tool calls to execute

        Returns:
            List of ToolResult objects
        """
        if not calls:
            return []

        start_time = time.time()
        self._results.clear()

        # Build dependency graph
        call_map = {c.call_id: c for c in calls}
        dependency_graph = self._build_dependency_graph(calls)

        # Execute in topological order
        try:
            async with asyncio.timeout(self.global_timeout):
                await self._execute_graph(call_map, dependency_graph)
        except TimeoutError:
            logger.error("global_timeout_exceeded", timeout=self.global_timeout)
            # Mark remaining as timeout
            for call_id, call in call_map.items():
                if call_id not in self._results:
                    self._results[call_id] = ToolResult(
                        call_id=call_id,
                        tool_name=call.tool_name,
                        status=ExecutionStatus.TIMEOUT,
                        error="Global timeout exceeded",
                    )

        elapsed = time.time() - start_time
        logger.info(
            "parallel_execution_complete",
            total_calls=len(calls),
            completed=sum(1 for r in self._results.values() if r.status == ExecutionStatus.COMPLETED),
            failed=sum(1 for r in self._results.values() if r.status == ExecutionStatus.FAILED),
            elapsed_ms=elapsed * 1000,
        )

        return [self._results[c.call_id] for c in calls if c.call_id in self._results]

    def _build_dependency_graph(
        self,
        calls: list[ToolCall],
    ) -> dict[str, set[str]]:
        """Build dependency graph for tool calls."""
        graph: dict[str, set[str]] = defaultdict(set)

        for call in calls:
            graph[call.call_id]  # Ensure node exists
            for dep_id in call.depends_on:
                graph[call.call_id].add(dep_id)

        return graph

    async def _execute_graph(
        self,
        call_map: dict[str, ToolCall],
        graph: dict[str, set[str]],
    ) -> None:
        """Execute tools in topological order."""
        # Track completion
        completed: set[str] = set()
        in_progress: set[str] = set()

        async def execute_ready() -> None:
            """Find and execute all ready calls."""
            ready = [
                call_id
                for call_id in graph
                if call_id not in completed and call_id not in in_progress and graph[call_id].issubset(completed)
            ]

            if not ready:
                return

            # Execute ready calls in parallel
            tasks = []
            for call_id in ready:
                in_progress.add(call_id)
                call = call_map[call_id]
                tasks.append(self._execute_single(call))

            # Wait for batch
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for call_id, result in zip(ready, results, strict=True):
                in_progress.discard(call_id)
                completed.add(call_id)

                if isinstance(result, Exception):
                    self._results[call_id] = ToolResult(
                        call_id=call_id,
                        tool_name=call_map[call_id].tool_name,
                        status=ExecutionStatus.FAILED,
                        error=str(result),
                    )
                    if self.fail_fast:
                        raise result
                else:
                    self._results[call_id] = result

        # Keep executing until all done
        while len(completed) < len(graph):
            await execute_ready()

            # Check for deadlock (circular dependencies)
            if not any(
                call_id not in completed and call_id not in in_progress and graph[call_id].issubset(completed)
                for call_id in graph
            ):
                # No more progress possible
                if len(completed) < len(graph):
                    remaining = set(graph.keys()) - completed
                    logger.error("dependency_deadlock", remaining=list(remaining))
                    for call_id in remaining:
                        self._results[call_id] = ToolResult(
                            call_id=call_id,
                            tool_name=call_map[call_id].tool_name,
                            status=ExecutionStatus.SKIPPED,
                            error="Dependency deadlock or missing dependency",
                        )
                break

            # Small delay to prevent tight loop
            await asyncio.sleep(0.01)

    async def _execute_single(self, call: ToolCall) -> ToolResult:
        """Execute single tool call with timeout."""
        tool = self.tools.get(call.tool_name)

        if not tool:
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.tool_name,
                status=ExecutionStatus.FAILED,
                error=f"Tool not found: {call.tool_name}",
            )

        timeout = call.timeout_seconds or self.default_timeout
        start_time = time.time()

        async with self._semaphore:
            try:
                async with asyncio.timeout(timeout):
                    result = await tool.execute(call.input_data)

                elapsed = (time.time() - start_time) * 1000
                record_histogram(
                    "agent_tool_execution_ms",
                    elapsed,
                )

                return ToolResult(
                    call_id=call.call_id,
                    tool_name=call.tool_name,
                    status=ExecutionStatus.COMPLETED,
                    result=result,
                    elapsed_ms=elapsed,
                )

            except TimeoutError:
                elapsed = (time.time() - start_time) * 1000
                logger.warning(
                    "tool_timeout",
                    tool=call.tool_name,
                    timeout=timeout,
                    elapsed_ms=elapsed,
                )
                return ToolResult(
                    call_id=call.call_id,
                    tool_name=call.tool_name,
                    status=ExecutionStatus.TIMEOUT,
                    error=f"Tool timed out after {timeout}s",
                    elapsed_ms=elapsed,
                )

            except ToolExecutionError as e:
                elapsed = (time.time() - start_time) * 1000
                return ToolResult(
                    call_id=call.call_id,
                    tool_name=call.tool_name,
                    status=ExecutionStatus.FAILED,
                    error=str(e),
                    elapsed_ms=elapsed,
                )

            except Exception as e:
                elapsed = (time.time() - start_time) * 1000
                logger.error(
                    "tool_execution_error",
                    tool=call.tool_name,
                    error=str(e),
                    exc_info=True,
                )
                return ToolResult(
                    call_id=call.call_id,
                    tool_name=call.tool_name,
                    status=ExecutionStatus.FAILED,
                    error=str(e),
                    elapsed_ms=elapsed,
                )

    async def execute_batch(
        self,
        tool_name: str,
        inputs: list[dict[str, Any]],
    ) -> list[ToolResult]:
        """
        Execute same tool with multiple inputs in parallel.

        Args:
            tool_name: Tool to execute
            inputs: List of input dicts

        Returns:
            List of results in same order as inputs
        """
        calls = [
            ToolCall(
                tool_name=tool_name,
                input_data=inp,
                call_id=f"{tool_name}_{i}_{int(time.time() * 1000)}",
            )
            for i, inp in enumerate(inputs)
        ]

        return await self.execute_parallel(calls)

    def get_tool_names(self) -> list[str]:
        """Get available tool names."""
        return list(self.tools.keys())

    def register_tool(self, name: str, tool: BaseTool) -> None:
        """Register new tool."""
        self.tools[name] = tool

    def unregister_tool(self, name: str) -> bool:
        """Unregister tool."""
        return self.tools.pop(name, None) is not None


class ToolChain:
    """
    Chain tools together with automatic output→input mapping.

    Usage:
        chain = ToolChain(executor)
        chain.add("search", {"query": "User class"})
        chain.add("read_file", lambda prev: {"path": prev["files"][0]})

        results = await chain.execute()
    """

    def __init__(self, executor: ParallelToolExecutor):
        """Initialize tool chain."""
        self.executor = executor
        self._steps: list[tuple[str, Any]] = []

    def add(
        self,
        tool_name: str,
        input_data: dict[str, Any] | Callable[[Any], dict[str, Any]],
    ) -> "ToolChain":
        """
        Add step to chain.

        Args:
            tool_name: Tool to execute
            input_data: Static dict or callable(prev_result) -> dict

        Returns:
            Self for chaining
        """
        self._steps.append((tool_name, input_data))
        return self

    async def execute(self) -> list[ToolResult]:
        """Execute chain sequentially."""
        results = []
        prev_result = None

        for tool_name, input_data in self._steps:
            # Resolve input
            if callable(input_data):
                try:
                    resolved_input = input_data(prev_result)
                except Exception as e:
                    results.append(
                        ToolResult(
                            call_id=f"chain_{len(results)}",
                            tool_name=tool_name,
                            status=ExecutionStatus.FAILED,
                            error=f"Input resolution failed: {e}",
                        )
                    )
                    break
            else:
                resolved_input = input_data

            # Execute
            call = ToolCall(
                tool_name=tool_name,
                input_data=resolved_input,
                call_id=f"chain_{len(results)}",
            )
            result = await self.executor._execute_single(call)
            results.append(result)

            if result.status != ExecutionStatus.COMPLETED:
                break  # Stop chain on failure

            prev_result = result.result

        return results

    def clear(self) -> None:
        """Clear chain steps."""
        self._steps.clear()
