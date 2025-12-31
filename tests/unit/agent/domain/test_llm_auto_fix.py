"""
Tests for LLM-based Auto-fix
"""

import pytest

from apps.orchestrator.orchestrator.domain.feedback.auto_retry_loop import ErrorType


@pytest.mark.asyncio
class TestLLMAutoFixer:
    """Test LLM auto-fixer"""

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM provider"""

        class MockLLM:
            async def complete(self, prompt, temperature, max_tokens):
                # Return fixed code based on error type in prompt
                if "Type Error" in prompt:
                    return "```python\nresult = str(x) + '1'\n```"
                elif "Test Error" in prompt or "failing test" in prompt:
                    return "```python\ndef fixed(): return True\n```"
                elif "Runtime Error" in prompt:
                    return "```python\nif x: result = x.value\n```"
                else:
                    return "```python\nfixed_code = 'generic fix'\n```"

        return MockLLM()

    async def test_fix_type_error(self, mock_llm):
        """Test LLM fixing type error"""
        from apps.orchestrator.orchestrator.domain.feedback.llm_auto_fix import LLMAutoFixer

        fixer = LLMAutoFixer(mock_llm)

        code = "result = x + '1'"
        error = "TypeError: unsupported operand type"

        fixed = await fixer.fix_with_llm(code, ErrorType.TYPE, error)

        assert "str(x)" in fixed or "fixed" in fixed.lower()
        assert fixed != code  # Should be different

    async def test_fix_test_failure(self, mock_llm):
        """Test LLM fixing test failure"""
        from apps.orchestrator.orchestrator.domain.feedback.llm_auto_fix import LLMAutoFixer

        fixer = LLMAutoFixer(mock_llm)

        code = "def func(): return False"
        error = "AssertionError: expected True"

        fixed = await fixer.fix_with_llm(code, ErrorType.TEST_FAILURE, error, context={"test_output": "FAILED"})

        assert "fixed" in fixed.lower() or "return True" in fixed
        assert fixed != code

    async def test_extract_code_from_response(self, mock_llm):
        """Test code extraction from LLM response"""
        from apps.orchestrator.orchestrator.domain.feedback.llm_auto_fix import LLMAutoFixer

        fixer = LLMAutoFixer(mock_llm)

        response = "Here's the fix:\n```python\ndef foo(): pass\n```\nDone!"
        extracted = fixer._extract_code(response)

        assert extracted == "def foo(): pass"

    async def test_llm_error_handling(self):
        """Test LLM error handling"""
        from apps.orchestrator.orchestrator.domain.feedback.llm_auto_fix import LLMAutoFixer

        class FailingLLM:
            async def complete(self, prompt, temperature, max_tokens):
                raise RuntimeError("API Error")

        fixer = LLMAutoFixer(FailingLLM())

        code = "original"
        fixed = await fixer.fix_with_llm(code, ErrorType.TYPE, "error")

        # Should return original on error
        assert fixed == code


@pytest.mark.asyncio
class TestEnhancedAutoRetryLoop:
    """Test enhanced auto-retry with LLM"""

    async def test_rule_based_fix_works(self):
        """Test rule-based fixes work without LLM"""
        from apps.orchestrator.orchestrator.domain.feedback.llm_auto_fix import EnhancedAutoRetryLoop

        class MockLLM:
            async def complete(self, prompt, temperature, max_tokens):
                return "should not be called"

        retry_loop = EnhancedAutoRetryLoop(MockLLM(), max_retries=2)

        attempts = [0]

        def execute_fn(code):
            attempts[0] += 1
            # Succeed on import fix (rule-based)
            if "import json" in code:
                return True, "success", ""
            return False, "", "ModuleNotFoundError: No module named 'json'"

        result = await retry_loop.execute_with_hybrid_fix(
            initial_code="data = json.dumps({})",
            execute_fn=execute_fn,
        )

        # Should succeed with rule-based fix
        assert result.success
        assert "import json" in result.final_code

    async def test_enhanced_retry_creation(self):
        """Test EnhancedAutoRetryLoop can be created"""
        from apps.orchestrator.orchestrator.domain.feedback.llm_auto_fix import EnhancedAutoRetryLoop

        class MockLLM:
            async def complete(self, prompt, temperature, max_tokens):
                return "fixed"

        retry_loop = EnhancedAutoRetryLoop(MockLLM(), max_retries=5)

        assert retry_loop.base_retry.max_retries == 5
        assert retry_loop.llm_fixer is not None
