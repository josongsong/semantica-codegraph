"""
Debug Mode

Analyzes errors and generates fixes.

Features:
- Error message parsing
- Stack trace analysis
- LLM-based fix generation
- Error location tracking
- Fix proposal and validation

Integrates with retrieval scenarios:
- 1-12: Error handling flow (exception → handler → response)
- 2-6: Exception throw/handle mapping
- 2-19: Debugging/log-based backtracing
"""

import re

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, Change, ModeContext, Result, Task
from src.contexts.agent_automation.infrastructure.utils import get_file_context, read_multiple_files

logger = get_logger(__name__)


@mode_registry.register(AgentMode.DEBUG)
class DebugMode(BaseModeHandler):
    """
    Debug mode for error analysis and fix generation.

    Analyzes errors and generates fixes using:
    - Error message parsing
    - Stack trace analysis
    - Related code context
    - LLM-based fix generation
    """

    def __init__(
        self,
        llm_client=None,
        graph_client=None,
    ):
        """
        Initialize Debug mode.

        Args:
            llm_client: LLM client for fix generation
            graph_client: Graph client for error flow analysis (scenario 1-12)
        """
        super().__init__(AgentMode.DEBUG)
        self.llm = llm_client
        self.graph = graph_client

    async def enter(self, context: ModeContext) -> None:
        """Enter debug mode."""
        await super().enter(context)
        self.logger.info("Starting error analysis")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute error analysis and fix generation.

        Flow:
        1. Parse error from task or context
        2. Analyze stack trace
        3. Find error location in code
        4. Generate fix using LLM
        5. Create Change objects
        6. Return result with fix_identified trigger

        Args:
            task: Debug task with error information
            context: Shared mode context

        Returns:
            Result with proposed fixes
        """
        self.logger.info(f"Debugging: {task.query}")

        # 1. Parse error from task or context
        error_info = self._parse_error(task, context)
        if not error_info:
            return self._create_result(
                data={"error": "No error information found"},
                trigger="error_occurred",
                explanation="Unable to parse error information",
                requires_approval=False,
            )

        # Store error in context
        context.last_error = error_info

        # 2. Analyze stack trace
        error_location = self._analyze_stacktrace(error_info)

        # 3. Find error flow using graph (scenario 1-12)
        error_flow = await self._find_error_flow(error_location, context)

        # 4. Get related code context
        related_code = await self._get_error_context(error_location, context)

        # 5. Generate fix using LLM
        try:
            fix_proposal = await self._generate_fix(error_info, error_location, related_code, context)
        except Exception as e:
            self.logger.error(f"Fix generation failed: {e}")
            return self._create_result(
                data={"error": str(e)},
                trigger="error_occurred",
                explanation=f"Failed to generate fix: {e}",
                requires_approval=False,
            )

        # 6. Create Change objects
        changes = self._create_fix_changes(fix_proposal, error_location, context)

        # 7. Add to context
        for change in changes:
            context.add_pending_change(
                {
                    "file_path": change.file_path,
                    "content": change.content,
                    "change_type": change.change_type,
                    "line_start": change.line_start,
                    "line_end": change.line_end,
                }
            )

        # 8. Record debug action
        context.add_action(
            {
                "type": "debug",
                "error_type": error_info.get("type"),
                "error_location": error_location,
                "fix_applied": True,
            }
        )

        return self._create_result(
            data={
                "error": error_info,
                "location": error_location,
                "flow": error_flow,
                "changes": [self._change_to_dict(c) for c in changes],
                "total_changes": len(changes),
            },
            trigger="fix_identified",  # Auto-transition to IMPLEMENTATION
            explanation=f"Generated {len(changes)} fixes for {error_info.get('type', 'error')}",
            requires_approval=True,  # Fixes should be reviewed
        )

    def _parse_error(self, task: Task, context: ModeContext) -> dict | None:
        """
        Parse error information from task or context.

        Args:
            task: Debug task
            context: Mode context with potential error info

        Returns:
            Error information dict or None
        """
        # Check context for last error
        if context.last_error:
            return context.last_error

        # Parse from task query
        query = task.query.lower()

        # Try to extract error type and message
        error_patterns = [
            r"(\w+Error):\s*(.+)",  # Python: ValueError: invalid literal
            r"(\w+Exception):\s*(.+)",  # Java: NullPointerException: ...
            r"Error:\s*(.+)",  # Generic error
            r"failed:\s*(.+)",  # Generic failure
        ]

        for pattern in error_patterns:
            match = re.search(pattern, task.query, re.IGNORECASE)
            if match:
                if len(match.groups()) == 2:
                    return {
                        "type": match.group(1),
                        "message": match.group(2).strip(),
                        "raw": task.query,
                    }
                else:
                    return {"type": "Error", "message": match.group(1).strip(), "raw": task.query}

        # Fallback: treat entire query as error description
        if any(keyword in query for keyword in ["error", "fail", "bug", "issue", "broken"]):
            return {"type": "Error", "message": task.query, "raw": task.query}

        return None

    def _analyze_stacktrace(self, error_info: dict) -> dict | None:
        """
        Analyze stack trace to find error location.

        Args:
            error_info: Parsed error information

        Returns:
            Error location dict or None
        """
        raw_error = error_info.get("raw", "")

        # Python stack trace pattern
        # File "/path/to/file.py", line 42, in function_name
        python_pattern = r'File "([^"]+)", line (\d+)(?:, in (\w+))?'
        matches = re.findall(python_pattern, raw_error)

        if matches:
            # Get the last frame (actual error location)
            file_path, line_num, func_name = matches[-1]
            return {
                "file_path": file_path,
                "line_number": int(line_num),
                "function": func_name or "unknown",
                "frames": [{"file": m[0], "line": int(m[1]), "function": m[2] or "unknown"} for m in matches],
            }

        # TypeScript/JavaScript stack trace pattern
        # at functionName (/path/to/file.ts:42:10)
        # Note: In JS stack traces, the FIRST frame is the error location (opposite of Python)
        js_pattern = r"at (?:(\w+) )?\(([^:]+):(\d+):(\d+)\)"
        matches = re.findall(js_pattern, raw_error)

        if matches:
            # Get the first frame (actual error location in JS)
            func_name, file_path, line_num, col_num = matches[0]
            return {
                "file_path": file_path,
                "line_number": int(line_num),
                "column": int(col_num),
                "function": func_name or "anonymous",
                "frames": [
                    {
                        "file": m[1],
                        "line": int(m[2]),
                        "column": int(m[3]),
                        "function": m[0] or "anonymous",
                    }
                    for m in matches
                ],
            }

        return None

    async def _find_error_flow(self, error_location: dict | None, context: ModeContext) -> list[dict]:
        """
        Find error handling flow using graph (scenario 1-12).

        Traces: exception → handler → response

        Args:
            error_location: Error location information from stack trace
            context: Mode context

        Returns:
            List of nodes in error flow
        """
        if not self.graph or not error_location:
            return []

        try:
            # Extract error location info
            file_path = error_location.get("file_path", "")
            line_number = error_location.get("line_number", 0)
            function_name = error_location.get("function", "")

            if not file_path or not function_name:
                self.logger.debug("Insufficient location info for error flow analysis")
                return []

            # Build symbol ID for the error site
            # Format: file_path::function_name
            error_symbol_id = f"{file_path}::{function_name}"

            self.logger.info(f"Tracing error flow from {error_symbol_id}")

            # Step 1: Find exception handlers in the same function (CFG_HANDLER edges)
            local_handlers = await self._find_local_handlers(error_symbol_id)

            # Step 2: Find callers who might handle this exception
            caller_handlers = await self._find_caller_handlers(error_symbol_id)

            # Step 3: Combine results
            error_flow = []

            # Add error site
            error_flow.append(
                {
                    "type": "error_site",
                    "symbol_id": error_symbol_id,
                    "function": function_name,
                    "file": file_path,
                    "line": line_number,
                }
            )

            # Add local handlers
            for handler in local_handlers:
                error_flow.append(
                    {
                        "type": "local_handler",
                        "symbol_id": handler.get("id", ""),
                        "handler_type": handler.get("handler_type", "try/except"),
                        "file": file_path,
                    }
                )

            # Add caller handlers
            for caller in caller_handlers:
                error_flow.append(
                    {
                        "type": "caller_handler",
                        "symbol_id": caller.get("id", ""),
                        "function": caller.get("name", ""),
                        "file": caller.get("file", ""),
                    }
                )

            self.logger.info(f"Found {len(error_flow)} nodes in error flow")
            return error_flow

        except Exception as e:
            self.logger.warning(f"Error flow analysis failed: {e}")
            return []

    async def _find_local_handlers(self, symbol_id: str) -> list[dict]:
        """
        Find exception handlers within the same function.

        Uses CFG_HANDLER edges to find try/except blocks.

        Args:
            symbol_id: Symbol ID of the error site

        Returns:
            List of handler nodes
        """
        if not self.graph:
            return []

        try:
            # Query graph for CFG_HANDLER edges from this symbol
            # This would use GraphStore's traverse method with CFG_HANDLER edge type
            handlers = self.graph.get_neighbors(node_id=symbol_id, edge_type="CFG_HANDLER", direction="outgoing")
            return handlers if handlers else []

        except Exception as e:
            self.logger.debug(f"Failed to find local handlers: {e}")
            return []

    async def _find_caller_handlers(self, symbol_id: str, max_depth: int = 3) -> list[dict]:
        """
        Find callers that might handle the exception.

        Traces up the call chain to find exception handlers.

        Args:
            symbol_id: Symbol ID of the error site
            max_depth: Maximum call chain depth to traverse

        Returns:
            List of caller nodes with handlers
        """
        if not self.graph:
            return []

        try:
            # Get callers of this function
            callers = await self.graph.get_callers(symbol_id)

            if not callers:
                return []

            # For each caller, check if they have exception handlers
            caller_handlers = []
            for caller in callers[:max_depth]:  # Limit depth
                caller_id = caller.get("id", "")

                # Check if this caller has exception handlers
                has_handler = self.graph.get_neighbors(node_id=caller_id, edge_type="CFG_HANDLER", direction="outgoing")

                if has_handler:
                    caller_handlers.append(caller)

            return caller_handlers

        except Exception as e:
            self.logger.debug(f"Failed to find caller handlers: {e}")
            return []

    async def _get_error_context(self, error_location: dict | None, context: ModeContext) -> str:
        """
        Get related code context around error location.

        Args:
            error_location: Error location information
            context: Mode context

        Returns:
            Related code as string
        """
        if not error_location:
            # Use files from context
            if context.current_files:
                return read_multiple_files(context.current_files[:3], max_lines_per_file=200)
            return ""

        # Read actual file around error line with context
        file_path = error_location.get("file_path", "")
        line_num = error_location.get("line_number", 0)

        if not file_path or not line_num:
            return ""

        # Get 10 lines of context before/after error
        return get_file_context(file_path, line_num, context_lines=10)

    async def _generate_fix(
        self,
        error_info: dict,
        error_location: dict | None,
        related_code: str,
        context: ModeContext,
    ) -> str:
        """
        Generate fix using LLM.

        Args:
            error_info: Error information
            error_location: Error location
            related_code: Related code context
            context: Mode context

        Returns:
            Generated fix code
        """
        if not self.llm:
            # Fallback: use rule-based fix generation
            self.logger.warning("No LLM client provided, using fallback fix generation")
            from src.contexts.agent_automation.infrastructure.fallback import SimpleLLMFallback

            error_type = error_info.get("type", "Error")
            error_message = error_info.get("message", "")
            return SimpleLLMFallback.generate_fix(error_type, error_message, related_code)

        # Build prompt
        prompt = self._build_fix_prompt(error_info, error_location, related_code, context)

        # Call LLM
        try:
            response = await self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2000,
            )

            generated = response.get("content", "")
            return self._extract_code(generated)

        except Exception as e:
            self.logger.error(f"LLM call failed: {e}")
            raise RuntimeError(f"Fix generation failed: {e}") from e

    def _build_fix_prompt(
        self,
        error_info: dict,
        error_location: dict | None,
        related_code: str,
        context: ModeContext,
    ) -> str:
        """
        Build LLM prompt for fix generation.

        Args:
            error_info: Error information
            error_location: Error location
            related_code: Related code
            context: Mode context

        Returns:
            Formatted prompt
        """
        error_type = error_info.get("type", "Error")
        error_msg = error_info.get("message", "")

        location_info = ""
        if error_location:
            location_info = f"""
Error Location:
- File: {error_location.get("file_path", "unknown")}
- Line: {error_location.get("line_number", "unknown")}
- Function: {error_location.get("function", "unknown")}
"""

        prompt = f"""You are an expert debugger. Fix the following error:

Error Type: {error_type}
Error Message: {error_msg}
{location_info}

Related code:
{related_code}

Generate a fix that:
1. Resolves the error
2. Maintains existing functionality
3. Includes error handling if appropriate
4. Has clear comments explaining the fix

Return ONLY the fixed code, no explanations.
"""
        return prompt

    def _extract_code(self, llm_response: str) -> str:
        """
        Extract code from LLM response.

        Args:
            llm_response: Raw LLM response

        Returns:
            Extracted code
        """
        # Remove markdown code blocks
        if "```python" in llm_response:
            parts = llm_response.split("```python")
            if len(parts) > 1:
                code_part = parts[1].split("```")[0]
                return code_part.strip()

        if "```" in llm_response:
            parts = llm_response.split("```")
            if len(parts) >= 3:
                return parts[1].strip()

        return llm_response.strip()

    def _create_fix_changes(self, fix_code: str, error_location: dict | None, context: ModeContext) -> list[Change]:
        """
        Create Change objects from fix code.

        Args:
            fix_code: Generated fix code
            error_location: Error location
            context: Mode context

        Returns:
            List of Change objects
        """
        # Determine target file
        if error_location and "file_path" in error_location:
            target_file = error_location["file_path"]
            line_start = error_location.get("line_number")
        elif context.current_files:
            target_file = context.current_files[0]
            line_start = None
        else:
            target_file = "fixed_file.py"
            line_start = None

        change = Change(
            file_path=target_file,
            content=fix_code,
            change_type="modify",
            line_start=line_start,
            line_end=line_start + 10 if line_start else None,  # Approximate end
        )

        return [change]

    def _change_to_dict(self, change: Change) -> dict:
        """Convert Change object to dict."""
        return {
            "file_path": change.file_path,
            "content": change.content,
            "change_type": change.change_type,
            "line_start": change.line_start,
            "line_end": change.line_end,
        }

    async def exit(self, context: ModeContext) -> None:
        """Exit debug mode."""
        self.logger.info(f"Exiting debug - {len(context.pending_changes)} fixes pending")
        await super().exit(context)


@mode_registry.register(AgentMode.DEBUG, simple=True)
class DebugModeSimple(BaseModeHandler):
    """
    Simplified Debug mode for testing without LLM.

    Returns mock fixes.
    """

    def __init__(self, mock_fix: str | None = None):
        """
        Initialize simple debug mode.

        Args:
            mock_fix: Optional mock fix to return
        """
        super().__init__(AgentMode.DEBUG)
        self.mock_fix = mock_fix or "# Fixed\ndef fixed_function():\n    return True"

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute simple debug with mock fix.

        Args:
            task: Debug task
            context: Mode context

        Returns:
            Result with mock fix
        """
        self.logger.info(f"Simple debug for: {task.query}")

        # Parse error (same as full mode)
        error_info = self._parse_error(task)

        # Create mock change
        change = Change(
            file_path="error_file.py",
            content=self.mock_fix,
            change_type="modify",
            line_start=10,
            line_end=15,
        )

        # Add to context
        context.add_pending_change(
            {
                "file_path": change.file_path,
                "content": change.content,
                "change_type": change.change_type,
                "line_start": change.line_start,
                "line_end": change.line_end,
            }
        )

        return self._create_result(
            data={
                "error": error_info,
                "changes": [
                    {
                        "file_path": change.file_path,
                        "content": change.content,
                        "change_type": change.change_type,
                        "line_start": change.line_start,
                        "line_end": change.line_end,
                    }
                ],
                "total_changes": 1,
            },
            trigger="fix_identified",
            explanation="Generated 1 fix (mock)",
            requires_approval=True,
        )

    def _parse_error(self, task: Task) -> dict:
        """Parse error from task (simplified)."""
        query = task.query.lower()
        if "valueerror" in query:
            return {"type": "ValueError", "message": "Invalid value"}
        elif "typeerror" in query:
            return {"type": "TypeError", "message": "Type mismatch"}
        else:
            return {"type": "Error", "message": task.query}
