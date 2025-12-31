"""
LLMAdapter Tests

SOTA-Level: Real LiteLLM behavior, Base + Edge + Corner
Production-Grade: 실제 integration (API key 없으면 skip)
"""

from unittest.mock import AsyncMock
from unittest.mock import patch as mock_patch

import pytest

from codegraph_runtime.codegen_loop.domain.patch import PatchStatus
from codegraph_runtime.codegen_loop.infrastructure.llm_adapter import (
    LITELLM_AVAILABLE,
    ClaudeAdapter,
    LLMConfig,
)


class TestLLMConfig:
    """LLMConfig 데이터 클래스"""

    def test_default_config(self):
        """Base: 기본 설정"""
        config = LLMConfig()

        assert config.model == "claude-3-5-sonnet-20241022"
        assert config.temperature == 0.7
        assert config.max_tokens == 8000

    def test_custom_config(self):
        """Base: 커스텀 설정"""
        config = LLMConfig(
            model="gpt-4",
            temperature=0.5,
            max_tokens=4000,
        )

        assert config.model == "gpt-4"
        assert config.temperature == 0.5


class TestClaudeAdapter:
    """ClaudeAdapter - 실제 동작"""

    def test_adapter_creation_requires_litellm(self):
        """Base: LiteLLM 필요"""
        if not LITELLM_AVAILABLE:
            with pytest.raises(RuntimeError, match="litellm not installed"):
                ClaudeAdapter()
        else:
            adapter = ClaudeAdapter()
            assert adapter is not None

    def test_adapter_with_config(self):
        """Base: Config 주입"""
        if not LITELLM_AVAILABLE:
            pytest.skip("litellm not available")

        config = LLMConfig(temperature=0.3)
        adapter = ClaudeAdapter(config=config)

        assert adapter.config.temperature == 0.3

    def test_system_prompt(self):
        """Base: System prompt 생성"""
        if not LITELLM_AVAILABLE:
            pytest.skip("litellm not available")

        adapter = ClaudeAdapter()
        prompt = adapter._get_system_prompt()

        assert "expert software engineer" in prompt.lower()
        assert "output format" in prompt.lower()

    def test_build_prompt_single_file(self):
        """Base: 단일 파일 prompt"""
        if not LITELLM_AVAILABLE:
            pytest.skip("litellm not available")

        adapter = ClaudeAdapter()
        prompt = adapter._build_prompt(
            task="Fix bug",
            file_paths=["main.py"],
            existing_code={"main.py": "def foo(): pass"},
            feedback="",
        )

        assert "Fix bug" in prompt
        assert "main.py" in prompt
        assert "def foo(): pass" in prompt

    def test_build_prompt_with_feedback(self):
        """Base: Feedback 포함"""
        if not LITELLM_AVAILABLE:
            pytest.skip("litellm not available")

        adapter = ClaudeAdapter()
        prompt = adapter._build_prompt(
            task="Fix bug",
            file_paths=["main.py"],
            existing_code={"main.py": "code"},
            feedback="Previous attempt had syntax error",
        )

        assert "Previous Attempt Feedback" in prompt
        assert "syntax error" in prompt

    def test_create_file_change_simple_diff(self):
        """Base: FileChange 생성"""
        if not LITELLM_AVAILABLE:
            pytest.skip("litellm not available")

        adapter = ClaudeAdapter()
        file_change = adapter._create_file_change(
            file_path="main.py",
            old_content="def foo(): pass",
            new_content="def foo():\n    return 42",
        )

        assert file_change.file_path == "main.py"
        assert file_change.old_content == "def foo(): pass"
        assert file_change.new_content == "def foo():\n    return 42"
        assert len(file_change.diff_lines) > 0

    def test_create_file_change_identical_content(self):
        """Corner: 동일한 내용"""
        if not LITELLM_AVAILABLE:
            pytest.skip("litellm not available")

        adapter = ClaudeAdapter()
        file_change = adapter._create_file_change(
            file_path="main.py",
            old_content="same",
            new_content="same",
        )

        # diff_lines는 비어있어야 함 (no changes)
        assert file_change.diff_lines == []

    @pytest.mark.asyncio
    async def test_generate_patch_without_api_key_raises(self):
        """Edge: API key 없이 생성 시도"""
        if not LITELLM_AVAILABLE:
            pytest.skip("litellm not available")

        adapter = ClaudeAdapter()

        # Real LLM call will fail without API key
        with pytest.raises(RuntimeError, match="LLM patch generation failed"):
            await adapter.generate_patch(
                task_description="Fix bug",
                file_paths=["main.py"],
                existing_code={"main.py": "code"},
            )

    @pytest.mark.asyncio
    async def test_parse_response_filename_format(self):
        """Base: Response 파싱"""
        if not LITELLM_AVAILABLE:
            pytest.skip("litellm not available")

        adapter = ClaudeAdapter()

        response = """```filename: main.py
def foo():
    return 42
```"""

        file_changes = adapter._parse_response(
            response,
            file_paths=["main.py"],
            existing_code={"main.py": "old"},
        )

        assert len(file_changes) == 1
        assert file_changes[0].file_path == "main.py"
        assert "return 42" in file_changes[0].new_content

    @pytest.mark.asyncio
    async def test_parse_response_fallback_single_file(self):
        """Edge: Fallback - 전체 응답을 코드로"""
        if not LITELLM_AVAILABLE:
            pytest.skip("litellm not available")

        adapter = ClaudeAdapter()

        response = """def foo():
    return 42"""

        file_changes = adapter._parse_response(
            response,
            file_paths=["main.py"],
            existing_code={"main.py": ""},
        )

        assert len(file_changes) == 1
        assert "return 42" in file_changes[0].new_content

    @pytest.mark.asyncio
    async def test_parse_response_no_files_raises(self):
        """Edge: 파싱 실패"""
        if not LITELLM_AVAILABLE:
            pytest.skip("litellm not available")

        adapter = ClaudeAdapter()

        with pytest.raises(ValueError, match="No file changes detected"):
            adapter._parse_response(
                "random text",
                file_paths=[],  # No files!
                existing_code={},
            )
