"""
LLM Adapter - Real LiteLLM Implementation

Production-Grade: 실제 LLM 연동, No Mock/Fake
"""

import uuid
from dataclasses import dataclass

from codegraph_runtime.codegen_loop.application.ports import LLMPort
from codegraph_runtime.codegen_loop.domain.patch import FileChange, Patch, PatchStatus

# Real import (not fake)
try:
    import litellm

    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False


@dataclass
class LLMConfig:
    """LLM 설정"""

    model: str = "claude-3-5-sonnet-20241022"
    temperature: float = 0.7
    max_tokens: int = 8000
    timeout: int = 60


class ClaudeAdapter(LLMPort):
    """
    Claude LLM Adapter (Real Implementation)

    ADR-011 Section 3: LLM Patch Generation
    """

    def __init__(
        self,
        api_key: str | None = None,
        config: LLMConfig | None = None,
    ):
        if not LITELLM_AVAILABLE:
            raise RuntimeError("litellm not installed. Run: pip install litellm")

        self.api_key = api_key
        self.config = config or LLMConfig()

        # Set API key if provided
        if self.api_key:
            litellm.api_key = self.api_key

    async def generate_patch(
        self,
        task_description: str,
        file_paths: list[str],
        existing_code: dict[str, str],
        feedback: str = "",
    ) -> Patch:
        """
        실제 LLM 호출로 Patch 생성

        Args:
            task_description: 작업 설명
            file_paths: 대상 파일 경로들
            existing_code: {file_path: code} 매핑
            feedback: 이전 피드백

        Returns:
            생성된 Patch
        """
        # Build prompt
        prompt = self._build_prompt(
            task_description,
            file_paths,
            existing_code,
            feedback,
        )

        # Real LLM call
        try:
            response = await litellm.acompletion(
                model=self.config.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt(),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                timeout=self.config.timeout,
            )

            # Extract content
            content = response.choices[0].message.content

            # Parse response to FileChanges
            file_changes = self._parse_response(content, file_paths, existing_code)

            return Patch(
                id=str(uuid.uuid4()),
                iteration=0,  # Set by application layer
                files=file_changes,
                status=PatchStatus.GENERATED,
            )

        except Exception as e:
            # LLM 호출 실패 시 명확한 에러
            raise RuntimeError(f"LLM patch generation failed: {e}") from e

    def _get_system_prompt(self) -> str:
        """System prompt"""
        return """You are an expert software engineer specialized in code generation.

Generate precise, production-ready code changes.

OUTPUT FORMAT:
For each file, return:
```filename: path/to/file.py
<complete new file content>
```

Requirements:
- Preserve existing functionality
- Follow project conventions
- Include type hints
- Add docstrings
- No breaking changes unless explicitly requested"""

    def _build_prompt(
        self,
        task: str,
        file_paths: list[str],
        existing_code: dict[str, str],
        feedback: str,
    ) -> str:
        """프롬프트 생성"""
        prompt = f"# Task\n{task}\n\n"

        # Existing code
        prompt += "# Current Code\n"
        for path in file_paths:
            code = existing_code.get(path, "# File does not exist yet")
            prompt += f"\n## {path}\n```python\n{code}\n```\n"

        # Feedback from previous attempt
        if feedback:
            prompt += f"\n# Previous Attempt Feedback\n{feedback}\n"

        prompt += "\n# Instructions\nGenerate complete new file contents for each file that needs to be changed."

        return prompt

    def _parse_response(
        self,
        content: str,
        file_paths: list[str],
        existing_code: dict[str, str],
    ) -> list[FileChange]:
        """
        LLM 응답 파싱

        Format:
        ```filename: main.py
        <code>
        ```
        """
        file_changes = []

        # Simple parser (production에서는 더 robust하게)
        current_file = None
        current_content = []

        for line in content.split("\n"):
            if line.startswith("```filename:"):
                # Save previous
                if current_file:
                    file_changes.append(
                        self._create_file_change(
                            current_file,
                            existing_code.get(current_file, ""),
                            "\n".join(current_content),
                        )
                    )

                # Start new file
                current_file = line.split("```filename:")[1].strip()
                current_content = []

            elif line.startswith("```") and current_file:
                # End of file
                if current_content:
                    file_changes.append(
                        self._create_file_change(
                            current_file,
                            existing_code.get(current_file, ""),
                            "\n".join(current_content),
                        )
                    )
                current_file = None
                current_content = []

            elif current_file:
                current_content.append(line)

        # Fallback: Single file
        if not file_changes and len(file_paths) == 1:
            # Entire content is the new code
            file_changes.append(
                self._create_file_change(
                    file_paths[0],
                    existing_code.get(file_paths[0], ""),
                    content,
                )
            )

        if not file_changes:
            raise ValueError("Failed to parse LLM response. No file changes detected.")

        return file_changes

    def _create_file_change(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
    ) -> FileChange:
        """FileChange 생성 with diff"""
        # Simple diff (production에서는 difflib 사용)
        old_lines = old_content.split("\n")
        new_lines = new_content.split("\n")

        diff_lines = []
        # Simplified diff
        for _i, (old, new) in enumerate(zip(old_lines, new_lines, strict=False)):
            if old != new:
                diff_lines.append(f"-{old}")
                diff_lines.append(f"+{new}")

        # Handle length mismatch
        if len(new_lines) > len(old_lines):
            for line in new_lines[len(old_lines) :]:
                diff_lines.append(f"+{line}")
        elif len(old_lines) > len(new_lines):
            for line in old_lines[len(new_lines) :]:
                diff_lines.append(f"-{line}")

        return FileChange(
            file_path=file_path,
            old_content=old_content,
            new_content=new_content,
            diff_lines=diff_lines,
        )
