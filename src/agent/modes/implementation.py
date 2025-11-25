"""
Implementation Mode

Generates and modifies code based on user requirements.

Features:
- LLM-based code generation
- Context-aware implementation
- Human-in-the-loop approval
- Change tracking and application
"""

import logging

from src.agent.modes.base import BaseModeHandler
from src.agent.types import AgentMode, ApprovalLevel, Change, ModeContext, Result, Task
from src.agent.utils import read_multiple_files

logger = logging.getLogger(__name__)


class ImplementationMode(BaseModeHandler):
    """
    Implementation mode for code generation and modification.

    Uses LLM to generate code based on:
    - User requirements (task.query)
    - Current context (files, symbols)
    - Existing code patterns
    """

    def __init__(
        self,
        llm_client=None,
        approval_callback=None,
    ):
        """
        Initialize Implementation mode.

        Args:
            llm_client: LLM client for code generation (e.g., OpenAIAdapter)
            approval_callback: Optional async function for human approval
                             Signature: async (changes: list[Change], context: ModeContext) -> bool
        """
        super().__init__(AgentMode.IMPLEMENTATION)
        self.llm = llm_client
        self.approval_callback = approval_callback

    async def enter(self, context: ModeContext) -> None:
        """Enter implementation mode."""
        await super().enter(context)
        self.logger.info(f"Starting implementation for: {context.current_task}")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute code implementation.

        Flow:
        1. Get related code from context
        2. Generate code using LLM
        3. Request approval (if needed)
        4. Create Change objects
        5. Return result with code_complete trigger

        Args:
            task: Implementation task with requirements
            context: Shared mode context

        Returns:
            Result with generated changes
        """
        self.logger.info(f"Implementing: {task.query}")

        # 1. Get related code from context
        related_code = self._get_related_code(context)

        # 2. Generate code using LLM
        try:
            generated_code = await self._generate_code(task, related_code, context)
        except Exception as e:
            self.logger.error(f"Code generation failed: {e}")
            return self._create_result(
                data={"error": str(e)},
                trigger="error_occurred",
                explanation=f"Failed to generate code: {e}",
                requires_approval=False,
            )

        # 3. Create Change objects
        changes = self._create_changes(generated_code, context)

        # 4. Human-in-the-loop approval (if needed)
        requires_approval = context.approval_level >= ApprovalLevel.MEDIUM
        if requires_approval:
            approved = await self._request_approval(changes, context)
            if not approved:
                return self._create_result(
                    data={"changes": changes, "status": "rejected"},
                    trigger="rejected",
                    explanation="Changes rejected by user",
                    requires_approval=False,
                )

        # 5. Add changes to context
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

        # 6. Return result
        return self._create_result(
            data={
                "changes": [self._change_to_dict(c) for c in changes],
                "generated_code": generated_code,
                "total_changes": len(changes),
            },
            trigger="code_complete",  # Auto-transition to TEST
            explanation=f"Generated {len(changes)} changes",
            requires_approval=False,  # Already approved
        )

    def _get_related_code(self, context: ModeContext) -> str:
        """
        Get related code from context.

        Args:
            context: Mode context with current files

        Returns:
            Concatenated code from context files
        """
        if not context.current_files:
            return ""

        # Read actual files (limit to first 5 files, 500 lines each)
        files_to_read = context.current_files[:5]
        return read_multiple_files(files_to_read, max_lines_per_file=500)

    async def _generate_code(self, task: Task, related_code: str, context: ModeContext) -> str:
        """
        Generate code using LLM.

        Args:
            task: Implementation task
            related_code: Related code from context
            context: Mode context

        Returns:
            Generated code as string
        """
        if not self.llm:
            # Fallback: return placeholder
            self.logger.warning("No LLM client provided, using placeholder")
            return f"# TODO: Implement {task.query}\npass"

        # Build prompt
        prompt = self._build_prompt(task, related_code, context)

        # Call LLM
        try:
            response = await self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,  # Lower temperature for code
                max_tokens=2000,
            )

            generated = response.get("content", "")
            return self._extract_code(generated)

        except Exception as e:
            self.logger.error(f"LLM call failed: {e}")
            raise RuntimeError(f"Code generation failed: {e}") from e

    def _build_prompt(self, task: Task, related_code: str, context: ModeContext) -> str:
        """
        Build LLM prompt for code generation.

        Args:
            task: Implementation task
            related_code: Related code from context
            context: Mode context

        Returns:
            Formatted prompt string
        """
        prompt = f"""You are an expert programmer. Generate code based on the following requirement:

Requirement: {task.query}

Related code context:
{related_code}

Current symbols in context: {", ".join(context.current_symbols[:5]) if context.current_symbols else "None"}

Generate clean, well-documented code that:
1. Follows existing code patterns
2. Includes type hints
3. Has clear docstrings
4. Handles errors appropriately

Return ONLY the code, no explanations.
"""
        return prompt

    def _extract_code(self, llm_response: str) -> str:
        """
        Extract code from LLM response.

        Removes markdown code blocks if present.

        Args:
            llm_response: Raw LLM response

        Returns:
            Extracted code
        """
        # Remove markdown code blocks
        if "```python" in llm_response:
            # Extract code between ```python and ```
            parts = llm_response.split("```python")
            if len(parts) > 1:
                code_part = parts[1].split("```")[0]
                return code_part.strip()

        if "```" in llm_response:
            # Generic code block
            parts = llm_response.split("```")
            if len(parts) >= 3:
                return parts[1].strip()

        return llm_response.strip()

    def _create_changes(self, generated_code: str, context: ModeContext) -> list[Change]:
        """
        Create Change objects from generated code.

        Args:
            generated_code: Generated code string
            context: Mode context

        Returns:
            List of Change objects
        """
        # Determine target file
        target_file = context.current_files[0] if context.current_files else "new_file.py"

        # Create single change for now
        # In real implementation, would parse code and create per-function changes
        change = Change(
            file_path=target_file,
            content=generated_code,
            change_type="modify",  # or "add" for new files
            line_start=None,  # Would be determined by code analysis
            line_end=None,
        )

        return [change]

    async def _request_approval(self, changes: list[Change], context: ModeContext) -> bool:
        """
        Request human approval for changes.

        Args:
            changes: List of proposed changes
            context: Mode context

        Returns:
            True if approved, False otherwise
        """
        if self.approval_callback:
            try:
                approved = await self.approval_callback(changes, context)
                return bool(approved)
            except Exception as e:
                self.logger.error(f"Approval callback failed: {e}")
                return False

        # Default: auto-approve if no callback
        self.logger.warning("No approval callback provided, auto-approving")
        return True

    def _change_to_dict(self, change: Change) -> dict:
        """Convert Change object to dict for JSON serialization."""
        return {
            "file_path": change.file_path,
            "content": change.content,
            "change_type": change.change_type,
            "line_start": change.line_start,
            "line_end": change.line_end,
        }

    async def exit(self, context: ModeContext) -> None:
        """Exit implementation mode."""
        self.logger.info(f"Exiting implementation - {len(context.pending_changes)} changes pending")
        await super().exit(context)


class ImplementationModeSimple(BaseModeHandler):
    """
    Simplified Implementation mode for testing without LLM.

    Returns mock generated code.
    """

    def __init__(self, mock_code: str | None = None):
        """
        Initialize simple implementation mode.

        Args:
            mock_code: Optional mock code to return
        """
        super().__init__(AgentMode.IMPLEMENTATION)
        self.mock_code = mock_code or "# Generated code\ndef example():\n    pass"

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute simple implementation with mock code.

        Args:
            task: Implementation task
            context: Mode context

        Returns:
            Result with mock code
        """
        self.logger.info(f"Simple implementation for: {task.query}")

        # Create mock change
        change = Change(
            file_path="test.py",
            content=self.mock_code,
            change_type="modify",
        )

        # Add to context
        context.add_pending_change(
            {
                "file_path": change.file_path,
                "content": change.content,
                "change_type": change.change_type,
            }
        )

        return self._create_result(
            data={
                "changes": [
                    {
                        "file_path": change.file_path,
                        "content": change.content,
                        "change_type": change.change_type,
                    }
                ],
                "total_changes": 1,
            },
            trigger="code_complete",
            explanation="Generated 1 change (mock)",
            requires_approval=False,
        )
