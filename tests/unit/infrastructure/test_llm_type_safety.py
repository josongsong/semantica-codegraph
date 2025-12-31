"""
Unit Tests: Type-Safe LLM kwargs (P2 SOTA)

Test Coverage:
- LLMKwargs TypedDict 필드
- IDE 자동완성 지원
- Type-safe 파라미터 전달
- Backward Compatibility
"""

from typing import get_type_hints
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codegraph_shared.infra.llm.local_llm import LLMKwargs, LocalLLMAdapter


class TestTypeSafeLLMKwargs:
    """Type-Safe kwargs 테스트"""

    def test_llm_kwargs_has_all_fields(self):
        """LLMKwargs에 모든 필수 필드 있음"""
        # Arrange & Act
        hints = get_type_hints(LLMKwargs)

        # Assert - P2-4 필드
        assert "caching" in hints, "Should have caching field (P2-4)"
        assert hints["caching"] is bool  # noqa: E721

        # Assert - Determinism 필드
        assert "seed" in hints, "Should have seed field"
        assert hints["seed"] is int  # noqa: E721

        # Assert - Sampling 필드
        assert "top_p" in hints, "Should have top_p field"
        assert hints["top_p"] is float  # noqa: E721

        assert "top_k" in hints, "Should have top_k field"
        assert hints["top_k"] is int  # noqa: E721

        assert "frequency_penalty" in hints, "Should have frequency_penalty field"
        assert hints["frequency_penalty"] is float  # noqa: E721

        assert "presence_penalty" in hints, "Should have presence_penalty field"
        assert hints["presence_penalty"] is float  # noqa: E721

        # Assert - Response Control 필드
        assert "stop" in hints, "Should have stop field"
        # stop은 list[str] | str

        assert "logprobs" in hints, "Should have logprobs field"
        assert hints["logprobs"] is bool  # noqa: E721

        assert "n" in hints, "Should have n field"
        assert hints["n"] is int  # noqa: E721

        # Assert - Advanced 필드
        assert "user" in hints, "Should have user field"
        assert hints["user"] is str  # noqa: E721

        assert "response_format" in hints, "Should have response_format field"

    def test_llm_kwargs_is_typed_dict(self):
        """LLMKwargs가 TypedDict임"""
        # Arrange & Act
        import typing
        from typing import get_origin

        # Assert
        # TypedDict는 get_origin이 None이지만, __annotations__가 있음
        assert hasattr(LLMKwargs, "__annotations__"), "Should be TypedDict"
        assert hasattr(LLMKwargs, "__total__"), "Should have __total__ attribute"
        assert LLMKwargs.__total__ is False, "Should be total=False (all fields optional)"

    @pytest.mark.asyncio
    async def test_generate_accepts_type_safe_kwargs(self):
        """generate()가 Type-safe kwargs를 받음"""
        # Arrange
        llm = LocalLLMAdapter(base_url="http://localhost:8000")

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Test"}}]}

        # Mock HTTP client
        with patch.object(llm.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            # Act - Type-safe 파라미터 전달
            await llm.generate(
                prompt="Test",
                caching=True,  # ✅ Type-safe!
                seed=42,  # ✅ Type-safe!
                top_p=0.9,  # ✅ Type-safe!
                stop=["END"],  # ✅ Type-safe!
            )

            # Assert
            mock_post.assert_called_once()
            payload = mock_post.call_args.kwargs["json"]

            assert payload["caching"] is True, "Should include caching"
            assert payload["seed"] == 42, "Should include seed"
            assert payload["top_p"] == 0.9, "Should include top_p"
            assert payload["stop"] == ["END"], "Should include stop"

    @pytest.mark.asyncio
    async def test_chat_accepts_type_safe_kwargs(self):
        """chat()가 Type-safe kwargs를 받음"""
        # Arrange
        llm = LocalLLMAdapter(base_url="http://localhost:8000")

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Test"}}]}

        with patch.object(llm.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            # Act - Type-safe 파라미터 전달
            await llm.chat(
                messages=[{"role": "user", "content": "Test"}],
                caching=True,
                seed=42,
                frequency_penalty=0.5,
                presence_penalty=0.3,
                response_format={"type": "json_object"},
            )

            # Assert
            mock_post.assert_called_once()
            payload = mock_post.call_args.kwargs["json"]

            assert payload["caching"] is True
            assert payload["seed"] == 42
            assert payload["frequency_penalty"] == 0.5
            assert payload["presence_penalty"] == 0.3
            assert payload["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_backward_compatibility_with_any_kwargs(self):
        """Backward Compatibility: 기존 코드 동작"""
        # Arrange
        llm = LocalLLMAdapter(base_url="http://localhost:8000")

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Test"}}]}

        with patch.object(llm.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            # Act - 기존 방식 (kwargs로 전달)
            await llm.generate(
                prompt="Test",
                custom_param="custom_value",  # ← TypedDict에 없는 파라미터
            )

            # Assert - 에러 없이 동작 (Backward Compatibility)
            mock_post.assert_called_once()
            payload = mock_post.call_args.kwargs["json"]

            # custom_param도 포함됨 (TypedDict는 runtime에 강제하지 않음)
            assert payload["custom_param"] == "custom_value"

    def test_llm_kwargs_documentation(self):
        """LLMKwargs에 문서화 있음"""
        # Arrange & Act
        doc = LLMKwargs.__doc__

        # Assert
        assert doc is not None, "Should have docstring"
        assert "Type-safe" in doc or "SOTA" in doc, "Should document SOTA feature"
        assert "IDE autocomplete" in doc, "Should document IDE support"

    @pytest.mark.asyncio
    async def test_all_kwargs_fields_work(self):
        """모든 LLMKwargs 필드가 작동함"""
        # Arrange
        llm = LocalLLMAdapter(base_url="http://localhost:8000")

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Test"}}]}

        with patch.object(llm.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            # Act - 모든 필드 전달
            await llm.chat(
                messages=[{"role": "user", "content": "Test"}],
                # Prompt Caching
                caching=True,
                # Determinism
                seed=42,
                # Sampling
                top_p=0.9,
                top_k=50,
                frequency_penalty=0.5,
                presence_penalty=0.3,
                # Response Control
                stop=["END", "STOP"],
                logprobs=True,
                n=3,
                # Advanced
                user="test-user",
                response_format={"type": "json_object"},
            )

            # Assert
            mock_post.assert_called_once()
            payload = mock_post.call_args.kwargs["json"]

            # 모든 필드 확인
            assert payload["caching"] is True
            assert payload["seed"] == 42
            assert payload["top_p"] == 0.9
            assert payload["top_k"] == 50
            assert payload["frequency_penalty"] == 0.5
            assert payload["presence_penalty"] == 0.3
            assert payload["stop"] == ["END", "STOP"]
            assert payload["logprobs"] is True
            assert payload["n"] == 3
            assert payload["user"] == "test-user"
            assert payload["response_format"] == {"type": "json_object"}


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
