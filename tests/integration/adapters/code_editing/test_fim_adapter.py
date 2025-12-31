"""
FIM Adapter Integration Tests

실제 LiteLLM 호출을 Mock으로 대체하여 테스트

/ss Rule 3:
✅ Happy path
✅ Invalid input
✅ Timeout handling
✅ Fallback 테스트
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.orchestrator.orchestrator.adapters.code_editing.fim import LiteLLMFIMAdapter
from apps.orchestrator.orchestrator.domain.code_editing import FIMEngine, FIMRequest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_litellm_response():
    """Mock LiteLLM response"""
    response = MagicMock()
    response.choices = [
        MagicMock(
            message=MagicMock(content="    result = a + b\n"),
            finish_reason="stop",
            logprobs=None,
        )
    ]
    response.usage = MagicMock(total_tokens=50)
    return response


@pytest.fixture
def mock_litellm_streaming_response():
    """Mock LiteLLM streaming response"""

    async def async_generator():
        # Chunk 1
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock(delta=MagicMock(content="    result"), finish_reason=None)]
        yield chunk1

        # Chunk 2
        chunk2 = MagicMock()
        chunk2.choices = [MagicMock(delta=MagicMock(content=" = a"), finish_reason=None)]
        yield chunk2

        # Chunk 3
        chunk3 = MagicMock()
        chunk3.choices = [MagicMock(delta=MagicMock(content=" + b\n"), finish_reason="stop")]
        yield chunk3

    return async_generator()


class TestLiteLLMFIMAdapter:
    """LiteLLMFIMAdapter Integration Tests"""

    @pytest.fixture
    def adapter(self):
        """Adapter fixture"""
        return LiteLLMFIMAdapter(
            default_engine=FIMEngine.OPENAI,
            timeout=30.0,
        )

    @pytest.fixture
    def sample_request(self):
        """Sample FIM request"""
        return FIMRequest(
            prefix="def add(a, b):\n",
            suffix="\n    return result",
            file_path="/test/math.py",
            language="python",
            max_tokens=100,
            temperature=0.7,
            num_completions=1,
        )

    async def test_complete_success(self, adapter, sample_request, mock_litellm_response):
        """Happy path: 성공적인 완성"""
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_litellm_response

            result = await adapter.complete(sample_request)

            assert result.success is True
            assert len(result.completions) == 1
            assert result.completions[0].text == "    result = a + b\n"
            assert result.completions[0].finish_reason == "stop"
            assert result.total_tokens == 50
            assert result.engine_used == FIMEngine.OPENAI

    async def test_complete_multiple_candidates(self, adapter, sample_request, mock_litellm_response):
        """다중 후보 생성"""
        # 3개 후보 요청
        sample_request.num_completions = 3

        # 3개 choice mock
        mock_litellm_response.choices = [
            MagicMock(
                message=MagicMock(content="    result = a + b\n"),
                finish_reason="stop",
                logprobs=None,
            ),
            MagicMock(
                message=MagicMock(content="    return a + b\n"),
                finish_reason="stop",
                logprobs=None,
            ),
            MagicMock(
                message=MagicMock(content="    ans = a + b\n"),
                finish_reason="stop",
                logprobs=None,
            ),
        ]

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_litellm_response

            result = await adapter.complete(sample_request)

            assert result.success is True
            assert len(result.completions) == 3
            # 점수 내림차순 정렬 확인
            assert result.completions[0].score >= result.completions[1].score
            assert result.completions[1].score >= result.completions[2].score

    async def test_complete_timeout(self, adapter, sample_request):
        """Timeout 처리"""
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            import asyncio

            mock_acompletion.side_effect = asyncio.TimeoutError("Timeout")

            result = await adapter.complete(sample_request)

            assert result.success is False
            assert result.error is not None
            assert "timeout" in result.error.lower()

    async def test_complete_api_error(self, adapter, sample_request):
        """API 에러 처리"""
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.side_effect = RuntimeError("API error")

            result = await adapter.complete(sample_request)

            assert result.success is False
            assert result.error is not None
            assert "API error" in result.error

    async def test_complete_with_fallback(self, sample_request, mock_litellm_response):
        """Fallback 엔진 테스트"""
        adapter = LiteLLMFIMAdapter(
            default_engine=FIMEngine.OPENAI,
            fallback_engines=[FIMEngine.CODESTRAL],
        )

        call_count = 0

        async def mock_acompletion_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 첫 번째 호출 실패
                raise RuntimeError("Primary failed")
            else:
                # 두 번째 호출 (fallback) 성공
                return mock_litellm_response

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.side_effect = mock_acompletion_side_effect

            result = await adapter.complete(sample_request)

            assert result.success is True
            assert result.engine_used == FIMEngine.CODESTRAL  # Fallback 사용됨
            assert call_count == 2  # 2번 호출 (primary + fallback)

    async def test_complete_streaming_success(self, adapter, sample_request, mock_litellm_streaming_response):
        """Happy path: 스트리밍 완성"""
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_litellm_streaming_response

            completions = []
            async for completion in adapter.complete_streaming(sample_request):
                completions.append(completion)

            # 스트리밍 중간 + 최종 완성
            assert len(completions) >= 2
            # 마지막이 최종 완성
            final_completion = completions[-1]
            assert final_completion.finish_reason == "stop"
            assert final_completion.text == "    result = a + b\n"
            assert final_completion.score > 0.0

    async def test_complete_streaming_timeout(self, adapter, sample_request):
        """스트리밍 Timeout"""
        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            import asyncio

            mock_acompletion.side_effect = asyncio.TimeoutError("Timeout")

            with pytest.raises(TimeoutError, match="streaming timeout"):
                async for _ in adapter.complete_streaming(sample_request):
                    pass

    def test_build_fim_messages(self, adapter, sample_request):
        """FIM 메시지 구성 테스트"""
        messages = adapter._build_fim_messages(sample_request)

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "python" in messages[0]["content"].lower()

        assert messages[1]["role"] == "user"
        assert "def add(a, b):" in messages[1]["content"]
        assert "return result" in messages[1]["content"]

    def test_calculate_score_stop(self, adapter):
        """점수 계산: finish_reason=stop"""
        score = adapter._calculate_score(
            text="result = a + b",
            logprobs=None,
            finish_reason="stop",
        )
        # stop이면 0.3 + 0.5(logprobs 없음) = 0.8
        assert score == pytest.approx(0.8, abs=0.1)

    def test_calculate_score_length(self, adapter):
        """점수 계산: finish_reason=length"""
        score = adapter._calculate_score(
            text="result = a + b",
            logprobs=None,
            finish_reason="length",
        )
        # length이면 0.1 + 0.5(logprobs 없음) = 0.6
        assert score == pytest.approx(0.6, abs=0.1)

    def test_calculate_score_too_short(self, adapter):
        """점수 계산: 너무 짧은 텍스트"""
        score = adapter._calculate_score(
            text="a",
            logprobs=None,
            finish_reason="stop",
        )
        # 길이 보정으로 절반 감점
        assert score < 0.5

    async def test_complete_with_explicit_engine(self, sample_request, mock_litellm_response):
        """명시적 엔진 지정"""
        adapter = LiteLLMFIMAdapter()

        # 요청에 엔진 명시
        sample_request.engine = FIMEngine.CODESTRAL

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_litellm_response

            result = await adapter.complete(sample_request)

            # Codestral 모델이 사용되었는지 확인
            call_args = mock_acompletion.call_args
            assert "codestral" in call_args.kwargs["model"].lower()
