"""
LLM Helper

Provides standardized LLM integration for mode handlers.

Features:
- Async LLM completion with retry
- Prompt templates for common operations
- Structured output parsing
- Token counting and rate limiting
- Error handling and fallback
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.common.observability import get_logger

logger = get_logger(__name__)
# Pre-compiled regex patterns for JSON extraction (performance optimization)
_JSON_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"```json\s*\n?(.*?)\n?```", re.DOTALL),
    re.compile(r"```\s*\n?(.*?)\n?```", re.DOTALL),
    re.compile(r"\{[\s\S]*\}", re.DOTALL),  # Match any JSON object
]

# ============================================================
# LLM Client Protocol
# ============================================================


class LLMClient(Protocol):
    """Protocol for LLM client implementations."""

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Generate completion from LLM.

        Args:
            messages: Chat messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            **kwargs: Additional provider-specific options

        Returns:
            Response dict with 'content' key
        """
        ...


# ============================================================
# Prompt Templates
# ============================================================


@dataclass
class PromptTemplate:
    """Reusable prompt template."""

    template: str
    description: str
    required_vars: list[str] = field(default_factory=list)
    optional_vars: list[str] = field(default_factory=list)

    def format(self, **kwargs) -> str:
        """Format template with variables."""
        for var in self.required_vars:
            if var not in kwargs:
                raise ValueError(f"Missing required variable: {var}")
        return self.template.format(**kwargs)


# Common prompt templates for agent modes
PROMPT_TEMPLATES = {
    "code_review": PromptTemplate(
        template="""Review the following code change and provide feedback:

{diff}

Focus on:
1. Code correctness
2. Potential bugs
3. Performance issues
4. Code style and readability
5. Security concerns

Provide your review in the following JSON format:
{{
    "summary": "Brief summary of the change",
    "issues": [
        {{
            "severity": "high|medium|low",
            "type": "bug|performance|style|security",
            "line": <line_number>,
            "message": "Description of the issue",
            "suggestion": "How to fix it"
        }}
    ],
    "approved": true|false
}}""",
        description="Code review prompt",
        required_vars=["diff"],
    ),
    "fix_bug": PromptTemplate(
        template="""Analyze the following error and suggest a fix:

Error message:
{error_message}

Relevant code:
```{language}
{code}
```

Provide your analysis in the following JSON format:
{{
    "root_cause": "Explanation of what's causing the error",
    "fix": {{
        "file": "path/to/file.py",
        "start_line": <line>,
        "end_line": <line>,
        "new_code": "The corrected code"
    }},
    "explanation": "Why this fix resolves the issue"
}}""",
        description="Bug fix analysis prompt",
        required_vars=["error_message", "code", "language"],
    ),
    "implement_feature": PromptTemplate(
        template="""Implement the following feature:

Requirement:
{requirement}

Existing code context:
```{language}
{context}
```

Constraints:
{constraints}

Provide your implementation in the following JSON format:
{{
    "approach": "High-level approach description",
    "files": [
        {{
            "path": "path/to/file.py",
            "action": "create|modify",
            "content": "Full file content or diff"
        }}
    ],
    "tests": [
        {{
            "name": "test_description",
            "code": "Test code"
        }}
    ]
}}""",
        description="Feature implementation prompt",
        required_vars=["requirement", "context", "language"],
        optional_vars=["constraints"],
    ),
    "refactor": PromptTemplate(
        template="""Refactor the following code to improve {improvement_goal}:

```{language}
{code}
```

Requirements:
- Maintain existing functionality
- {additional_requirements}

Provide your refactored code in the following JSON format:
{{
    "summary": "What was refactored and why",
    "before_metrics": {{
        "complexity": <number>,
        "lines": <number>
    }},
    "after_metrics": {{
        "complexity": <number>,
        "lines": <number>
    }},
    "refactored_code": "The refactored code"
}}""",
        description="Code refactoring prompt",
        required_vars=["code", "language", "improvement_goal"],
        optional_vars=["additional_requirements"],
    ),
    "explain_code": PromptTemplate(
        template="""Explain the following code:

```{language}
{code}
```

Provide explanation covering:
1. Purpose: What does this code do?
2. How it works: Step-by-step explanation
3. Key concepts: Important patterns or algorithms used
4. Dependencies: External libraries or modules used
5. Potential issues: Any bugs or improvements needed

Format as markdown.""",
        description="Code explanation prompt",
        required_vars=["code", "language"],
    ),
}

# ============================================================
# LLM Helper Class
# ============================================================


class LLMHelper:
    """
    Helper for LLM operations in mode handlers.

    Provides:
    - Standardized prompt formatting
    - Retry logic with exponential backoff
    - Response parsing and validation
    - Structured output extraction
    """

    def __init__(
        self,
        client: LLMClient | None = None,
        default_temperature: float = 0.7,
        default_max_tokens: int = 2000,
        max_retries: int = 3,
    ):
        """
        Initialize LLM helper.

        Args:
            client: LLM client instance
            default_temperature: Default sampling temperature
            default_max_tokens: Default max tokens
            max_retries: Maximum retry attempts
        """
        self.client = client
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        self.max_retries = max_retries

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        parse_json: bool = False,
    ) -> str | dict[str, Any]:
        """
        Get completion from LLM.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            parse_json: Whether to parse response as JSON

        Returns:
            Response string or parsed JSON dict
        """
        if not self.client:
            raise ValueError("LLM client not configured")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        temperature = temperature or self.default_temperature
        max_tokens = max_tokens or self.default_max_tokens

        # Retry with exponential backoff
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = await self.client.complete(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                content = response.get("content", "")

                if parse_json:
                    return self._parse_json_response(content)

                return content

            except Exception as e:
                last_error = e
                wait_time = 2**attempt
                logger.warning(f"LLM request failed (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(wait_time)

        raise RuntimeError(f"LLM request failed after {self.max_retries} attempts: {last_error}")

    async def complete_with_template(
        self,
        template_name: str,
        parse_json: bool = True,
        **template_vars,
    ) -> str | dict[str, Any]:
        """
        Complete using a predefined template.

        Args:
            template_name: Name of template from PROMPT_TEMPLATES
            parse_json: Whether to parse response as JSON
            **template_vars: Variables to fill in template

        Returns:
            Response string or parsed JSON dict
        """
        if template_name not in PROMPT_TEMPLATES:
            raise ValueError(f"Unknown template: {template_name}")

        template = PROMPT_TEMPLATES[template_name]
        prompt = template.format(**template_vars)

        return await self.complete(
            prompt=prompt,
            temperature=0.3 if parse_json else 0.7,  # Lower temp for structured output
            parse_json=parse_json,
        )

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        """
        Parse JSON from LLM response.

        Handles:
        - Raw JSON
        - JSON in markdown code blocks
        - JSON with surrounding text

        Args:
            content: LLM response content

        Returns:
            Parsed JSON dict
        """
        # Try direct JSON parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code blocks using pre-compiled patterns
        for pattern in _JSON_PATTERNS:
            match = pattern.search(content)
            if match:
                try:
                    json_str = match.group(1) if match.lastindex else match.group(0)
                    return json.loads(json_str.strip())
                except json.JSONDecodeError:
                    continue

        raise ValueError(f"Could not parse JSON from response: {content[:200]}...")

    async def review_code(self, diff: str) -> dict[str, Any]:
        """
        Review code changes.

        Args:
            diff: Unified diff of changes

        Returns:
            Review result dict
        """
        result = await self.complete_with_template("code_review", diff=diff)
        return result if isinstance(result, dict) else {"content": result}

    async def analyze_bug(
        self,
        error_message: str,
        code: str,
        language: str = "python",
    ) -> dict[str, Any]:
        """
        Analyze a bug and suggest fix.

        Args:
            error_message: Error message
            code: Relevant code
            language: Programming language

        Returns:
            Analysis result dict
        """
        result = await self.complete_with_template(
            "fix_bug",
            error_message=error_message,
            code=code,
            language=language,
        )
        return result if isinstance(result, dict) else {"content": result}

    async def implement_feature(
        self,
        requirement: str,
        context: str,
        language: str = "python",
        constraints: str = "None",
    ) -> dict[str, Any]:
        """
        Generate feature implementation.

        Args:
            requirement: Feature requirement
            context: Existing code context
            language: Programming language
            constraints: Implementation constraints

        Returns:
            Implementation result dict
        """
        result = await self.complete_with_template(
            "implement_feature",
            requirement=requirement,
            context=context,
            language=language,
            constraints=constraints,
        )
        return result if isinstance(result, dict) else {"content": result}

    async def refactor_code(
        self,
        code: str,
        improvement_goal: str,
        language: str = "python",
        additional_requirements: str = "None",
    ) -> dict[str, Any]:
        """
        Refactor code.

        Args:
            code: Code to refactor
            improvement_goal: What to improve
            language: Programming language
            additional_requirements: Additional requirements

        Returns:
            Refactoring result dict
        """
        result = await self.complete_with_template(
            "refactor",
            code=code,
            improvement_goal=improvement_goal,
            language=language,
            additional_requirements=additional_requirements,
        )
        return result if isinstance(result, dict) else {"content": result}

    async def explain_code(self, code: str, language: str = "python") -> str:
        """
        Explain code.

        Args:
            code: Code to explain
            language: Programming language

        Returns:
            Explanation string (markdown)
        """
        result = await self.complete_with_template(
            "explain_code",
            code=code,
            language=language,
            parse_json=False,
        )
        return result if isinstance(result, str) else str(result)
