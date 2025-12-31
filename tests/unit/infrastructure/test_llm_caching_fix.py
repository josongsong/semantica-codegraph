"""
Fix Verification: Caching 파라미터가 LLM Adapter에 전달됨

P2-4 Fix:
- LocalLLMAdapter.generate()에 **kwargs 추가
- LocalLLMAdapter.chat()에 **kwargs 추가
- payload.update(kwargs)로 추가 파라미터 전달
"""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCachingParameterFix:
    """Caching 파라미터 Fix 검증"""

    @pytest.mark.asyncio
    async def test_generate_signature_has_kwargs(self):
        """✅ Fix: generate() 시그니처에 **kwargs 있음"""
        # Arrange
        from codegraph_shared.infra.llm.local_llm import LocalLLMAdapter

        # Act
        sig = inspect.signature(LocalLLMAdapter.generate)

        # Assert
        params = sig.parameters
        assert "kwargs" in params, "Fix verified: **kwargs present in generate()"
        assert params["kwargs"].kind == inspect.Parameter.VAR_KEYWORD

    @pytest.mark.asyncio
    async def test_chat_signature_has_kwargs(self):
        """✅ Fix: chat() 시그니처에 **kwargs 있음"""
        # Arrange
        from codegraph_shared.infra.llm.local_llm import LocalLLMAdapter

        # Act
        sig = inspect.signature(LocalLLMAdapter.chat)

        # Assert
        params = sig.parameters
        assert "kwargs" in params, "Fix verified: **kwargs present in chat()"
        assert params["kwargs"].kind == inspect.Parameter.VAR_KEYWORD

    @pytest.mark.asyncio
    async def test_caching_parameter_passed_to_chat(self):
        """✅ Fix: caching 파라미터가 chat()으로 전달됨"""
        # Arrange
        from codegraph_shared.infra.llm.local_llm import LocalLLMAdapter

        llm = LocalLLMAdapter(base_url="http://localhost:8000")

        # Mock chat method
        with patch.object(llm, "chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "Test response"

            # Act - caching 파라미터 전달
            await llm.generate(
                prompt="Test",
                caching=True,  # ← 전달!
            )

            # Assert
            mock_chat.assert_called_once()
            call_kwargs = mock_chat.call_args[1]
            assert "caching" in call_kwargs, "Fix verified: caching passed to chat()"
            assert call_kwargs["caching"] is True

    @pytest.mark.asyncio
    async def test_kwargs_merged_into_payload(self):
        """✅ Fix: kwargs가 payload에 병합됨"""
        # Arrange
        from codegraph_shared.infra.llm.local_llm import LocalLLMAdapter

        llm = LocalLLMAdapter(base_url="http://localhost:8000")

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Test"}}]}

        with patch.object(llm.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            # Act - 추가 파라미터 전달
            await llm.chat(
                messages=[{"role": "user", "content": "Test"}],
                caching=True,  # ← 추가 파라미터
                seed=42,  # ← 추가 파라미터
            )

            # Assert
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]

            # payload에 caching과 seed가 포함됨
            assert "caching" in payload, "Fix verified: caching in payload"
            assert payload["caching"] is True
            assert "seed" in payload, "Fix verified: seed in payload"
            assert payload["seed"] == 42


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
