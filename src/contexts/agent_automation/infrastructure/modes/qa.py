"""
QA Mode

Performs code review and quality assurance on pending changes.

Features:
- Code review (LLM-based or template-based)
- Quality score calculation (0-100)
- Static analysis integration (lint, type check)
- Approval/rejection based on quality threshold
"""

import ast
import re
from typing import Any

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)


@mode_registry.register(AgentMode.QA)
class QAMode(BaseModeHandler):
    """
    QA mode for code review and quality assurance.

    Flow:
    1. Check for pending changes
    2. Perform code review (LLM or template)
    3. Calculate quality score
    4. Approve (>= 70) or request improvements

    Transitions:
    - approved → GIT_WORKFLOW (quality score >= 70)
    - improvement_needed → REFACTOR (quality score < 70)
    - issues_found → IMPLEMENTATION (critical issues)
    """

    APPROVAL_THRESHOLD = 70

    def __init__(self, llm_client=None):
        """
        Initialize QA mode.

        Args:
            llm_client: Optional LLM client for AI-powered code review
        """
        super().__init__(AgentMode.QA)
        self.llm = llm_client

    async def enter(self, context: ModeContext) -> None:
        """Enter QA mode."""
        await super().enter(context)
        self.logger.info(f"🔍 QA mode: Reviewing {len(context.pending_changes)} changes")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute QA mode.

        Args:
            task: QA task
            context: Shared mode context with pending changes

        Returns:
            Result with review, quality score, and approval status
        """
        self.logger.info(f"Reviewing: {task.query}")

        # 1. Check for pending changes
        if not context.pending_changes:
            return self._create_result(
                data={"no_changes": True, "quality_score": 0, "approved": False},
                trigger="no_changes",
                explanation="No changes to review",
            )

        # 2. Perform code review
        review = await self._perform_review(context.pending_changes)

        # 3. Calculate quality score
        quality_score = self._calculate_quality_score(context.pending_changes, review)

        # 4. Determine approval
        approved = quality_score >= self.APPROVAL_THRESHOLD

        # 5. Determine trigger
        if approved:
            trigger = "approved"
            explanation = f"Code approved (score: {quality_score}/100)"
        elif quality_score >= 50:
            trigger = "improvement_needed"
            explanation = f"Improvements needed (score: {quality_score}/100)"
        else:
            trigger = "issues_found"
            explanation = f"Critical issues found (score: {quality_score}/100)"

        return self._create_result(
            data={
                "review": review,
                "quality_score": quality_score,
                "approved": approved,
            },
            trigger=trigger,
            explanation=explanation,
        )

    async def _perform_review(self, pending_changes: list[dict]) -> dict[str, Any]:
        """
        Perform code review on pending changes.

        Args:
            pending_changes: List of pending code changes

        Returns:
            Review dictionary
        """
        if self.llm:
            try:
                return await self._llm_review(pending_changes)
            except Exception as e:
                self.logger.warning(f"LLM review failed: {e}, using template")

        # Fallback: Template-based review
        return self._template_review(pending_changes)

    async def _llm_review(self, pending_changes: list[dict]) -> dict[str, Any]:
        """
        Perform LLM-based code review.

        Args:
            pending_changes: List of pending changes

        Returns:
            Review dictionary with feedback
        """
        # Build review prompt
        changes_text = "\n\n".join(
            [f"File: {change['file_path']}\n```python\n{change['content']}\n```" for change in pending_changes]
        )

        prompt = f"""Review the following code changes:

{changes_text}

Provide a code review with:
1. Overall assessment
2. Strengths
3. Issues (if any)
4. Suggestions for improvement
5. Quality rating (0-10)

Focus on:
- Code quality and readability
- Type hints and documentation
- Error handling
- Security concerns
- Performance considerations
"""

        if self.llm is None:
            return {"quality_score": 0, "issues": [], "suggestions": []}

        response = await self.llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000,
        )

        review_text = response.get("content", "")

        # Parse quality rating from response
        quality_match = re.search(r"quality[:\s]+(\d+)/10", review_text.lower())
        llm_quality = int(quality_match.group(1)) if quality_match else 7

        return {
            "type": "llm",
            "content": review_text,
            "llm_quality": llm_quality,
            "issues": self._extract_issues_from_review(review_text),
            "strengths": self._extract_strengths_from_review(review_text),
        }

    def _template_review(self, pending_changes: list[dict]) -> dict[str, Any]:
        """
        Perform template-based code review.

        Args:
            pending_changes: List of pending changes

        Returns:
            Review dictionary
        """
        issues = []
        strengths = []
        total_lines = 0

        for change in pending_changes:
            content = change.get("content", "")
            total_lines += len(content.split("\n"))

            # Check for basic quality indicators
            has_docstring = '"""' in content or "'''" in content
            has_type_hints = "->" in content or ": int" in content or ": str" in content

            if has_docstring:
                strengths.append("Has docstrings")
            else:
                issues.append("Missing docstrings")

            if has_type_hints:
                strengths.append("Has type hints")
            else:
                issues.append("Missing type hints")

            # Check for syntax errors
            try:
                ast.parse(content)
            except SyntaxError as e:
                issues.append(f"Syntax error: {e}")

        review_text = f"""Code Review Summary:

Files reviewed: {len(pending_changes)}
Total lines: {total_lines}

Strengths:
{chr(10).join(f"- {s}" for s in strengths) if strengths else "- None identified"}

Issues:
{chr(10).join(f"- {i}" for i in issues) if issues else "- None identified"}
"""

        return {
            "type": "template",
            "content": review_text,
            "issues": issues,
            "strengths": strengths,
        }

    def _calculate_quality_score(self, pending_changes: list[dict], review: dict) -> int:
        """
        Calculate quality score (0-100).

        Args:
            pending_changes: List of pending changes
            review: Review dictionary

        Returns:
            Quality score between 0 and 100
        """
        score = 100

        # If LLM review, use LLM quality rating as base
        if review.get("type") == "llm" and "llm_quality" in review:
            score = review["llm_quality"] * 10

        # Deduct for issues
        issues = review.get("issues", [])
        for issue in issues:
            if "syntax" in issue.lower() or "error" in issue.lower():
                score -= 15  # Critical issues
            elif "missing" in issue.lower():
                score -= 5  # Quality issues
            else:
                score -= 3  # Minor issues

        # Add for strengths
        strengths = review.get("strengths", [])
        for _ in strengths:
            score += 2

        # Analyze code quality indicators
        for change in pending_changes:
            content = change.get("content", "")

            # Check for good practices
            if '"""' in content or "'''" in content:
                score += 3  # Has docstrings

            if "->" in content:
                score += 2  # Has return type hints

            # Check for bad practices
            if "import *" in content:
                score -= 5  # Star imports

            if re.search(r"except:\s*pass", content):
                score -= 5  # Bare except

            # Check naming conventions
            functions = re.findall(r"def\s+(\w+)\(", content)
            for func in functions:
                if len(func) <= 2:
                    score -= 2  # Too short function names

        # Clamp score to 0-100
        return max(0, min(100, score))

    def _extract_issues_from_review(self, review_text: str) -> list[str]:
        """Extract issues from LLM review text."""
        issues = []
        lines = review_text.split("\n")

        in_issues_section = False
        for line in lines:
            line = line.strip()

            if "issue" in line.lower() and ":" in line:
                in_issues_section = True
                continue

            if in_issues_section:
                if line.startswith("-") or line.startswith("*"):
                    issues.append(line.lstrip("-* "))
                elif line and not line[0].isspace():
                    in_issues_section = False

        return issues

    def _extract_strengths_from_review(self, review_text: str) -> list[str]:
        """Extract strengths from LLM review text."""
        strengths = []
        lines = review_text.split("\n")

        in_strengths_section = False
        for line in lines:
            line = line.strip()

            if "strength" in line.lower() and ":" in line:
                in_strengths_section = True
                continue

            if in_strengths_section:
                if line.startswith("-") or line.startswith("*"):
                    strengths.append(line.lstrip("-* "))
                elif line and not line[0].isspace():
                    in_strengths_section = False

        return strengths

    async def exit(self, context: ModeContext) -> None:
        """Exit QA mode."""
        self.logger.info("QA mode complete")
        await super().exit(context)
