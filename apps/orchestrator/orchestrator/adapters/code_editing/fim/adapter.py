"""
LiteLLM FIM Adapter

Port: FIMPort
Technology: LiteLLM (multi-provider)

책임:
- OpenAI/Anthropic/Codestral/DeepSeek FIM 통합
- 스트리밍 지원
- 다중 후보 생성
- 점수 계산 (log_prob 기반)
"""

import asyncio
import time
from collections.abc import AsyncIterator

from apps.orchestrator.orchestrator.domain.code_editing import Completion, FIMEngine, FIMRequest, FIMResult
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

# LiteLLM import
try:
    import litellm

    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    litellm = None


class LiteLLMFIMAdapter:
    """
    LiteLLM 기반 FIM Adapter

    FIMPort 구현체

    지원 엔진:
    - OpenAI: gpt-4o, gpt-4o-mini (FIM 실험적 지원)
    - Codestral: mistral-codestral-latest (코드 특화)
    - DeepSeek: deepseek-coder (코드 특화)
    - Anthropic: claude-* (prefix+suffix concatenation)
    """

    # 엔진별 모델 매핑
    ENGINE_MODEL_MAP = {
        FIMEngine.OPENAI: "gpt-4o-mini",
        FIMEngine.CODESTRAL: "codestral-latest",
        FIMEngine.DEEPSEEK: "deepseek/deepseek-coder",
        FIMEngine.ANTHROPIC: "claude-3-5-sonnet-20241022",
    }

    def __init__(
        self,
        default_engine: FIMEngine = FIMEngine.OPENAI,
        timeout: float = 30.0,
        fallback_engines: list[FIMEngine] | None = None,
    ):
        """
        Args:
            default_engine: 기본 엔진 (요청에 명시 안 되면 사용)
            timeout: LLM 타임아웃 (초)
            fallback_engines: Fallback 엔진 리스트
        """
        if not LITELLM_AVAILABLE:
            raise ImportError("LiteLLM not installed. Install with: pip install litellm")

        self.default_engine = default_engine
        self.timeout = timeout
        self.fallback_engines = fallback_engines or []

        # LiteLLM 설정
        litellm.drop_params = True  # Unsupported params 자동 제거

        logger.info(
            f"LiteLLMFIMAdapter initialized: engine={default_engine.value}, "
            f"timeout={timeout}s, fallback={[e.value for e in self.fallback_engines]}"
        )

    def _build_fim_messages(self, request: FIMRequest) -> list[dict[str, str]]:
        """
        FIM 프롬프트 구성

        Format:
        ```
        [System] You are a code completion assistant.
        [User] Complete the code:

        PREFIX:
        {prefix}

        SUFFIX:
        {suffix}

        Complete the middle part (MIDDLE):
        ```

        Args:
            request: FIM 요청

        Returns:
            Messages (OpenAI format)
        """
        system_message = {
            "role": "system",
            "content": f"You are a {request.language} code completion assistant. "
            f"Complete the code between PREFIX and SUFFIX. "
            f"Return ONLY the middle part without explanations.",
        }

        user_content = f"""Complete the code in {request.language}:

File: {request.file_path}

PREFIX:
```{request.language}
{request.prefix}
```

SUFFIX:
```{request.language}
{request.suffix}
```

Complete the middle part (MIDDLE) that connects PREFIX and SUFFIX:"""

        user_message = {"role": "user", "content": user_content}

        return [system_message, user_message]

    async def _call_litellm(
        self,
        request: FIMRequest,
        engine: FIMEngine,
        n: int = 1,
    ) -> dict:
        """
        LiteLLM 호출 (단일 엔진)

        Args:
            request: FIM 요청
            engine: 사용할 엔진
            n: 생성할 후보 수

        Returns:
            LiteLLM response

        Raises:
            TimeoutError: Timeout
            RuntimeError: LLM API error
        """
        model = self.ENGINE_MODEL_MAP[engine]
        messages = self._build_fim_messages(request)

        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                n=n,  # 다중 후보
                timeout=self.timeout,
                # logprobs=True,  # OpenAI only (점수 계산용)
            )
            return response

        except asyncio.TimeoutError as e:
            raise TimeoutError(f"LLM timeout after {self.timeout}s") from e
        except Exception as e:
            raise RuntimeError(f"LLM API error ({engine.value}): {e}") from e

    def _calculate_score(
        self,
        text: str,
        logprobs: dict | None,
        finish_reason: str,
    ) -> float:
        """
        완성 점수 계산

        기준:
        - finish_reason == "stop": +0.3
        - logprobs 평균: 0~0.7
        - 길이 보정: 너무 짧으면 감점

        Args:
            text: 생성된 텍스트
            logprobs: Log probabilities (OpenAI only)
            finish_reason: 완료 이유

        Returns:
            Score (0.0~1.0)
        """
        score = 0.0

        # 1. finish_reason 점수
        if finish_reason == "stop":
            score += 0.3
        elif finish_reason == "length":
            score += 0.1

        # 2. logprobs 점수 (없으면 0.5 기본)
        if logprobs and "token_logprobs" in logprobs:
            # 평균 log_prob를 0~1로 정규화
            # log_prob는 음수이므로 exp()로 확률 변환 후 평균
            import math

            token_logprobs = logprobs["token_logprobs"]
            valid_logprobs = [lp for lp in token_logprobs if lp is not None]
            if valid_logprobs:
                avg_prob = sum(math.exp(lp) for lp in valid_logprobs) / len(valid_logprobs)
                score += min(0.7, avg_prob)
            else:
                score += 0.5  # 기본값
        else:
            score += 0.5  # logprobs 없으면 중간 점수

        # 3. 길이 보정 (너무 짧으면 감점)
        if len(text.strip()) < 5:
            score *= 0.5

        return min(1.0, max(0.0, score))

    async def complete(self, request: FIMRequest) -> FIMResult:
        """
        코드 완성 (일반 모드)

        Args:
            request: FIM 요청

        Returns:
            FIMResult: 완성 결과 (다중 후보 포함)

        Raises:
            ValueError: Invalid request
            TimeoutError: LLM timeout
            RuntimeError: LLM API error
        """
        start_time = time.perf_counter()

        # 엔진 선택
        engine = request.engine or self.default_engine
        engines_to_try = [engine] + self.fallback_engines

        last_error = None
        for current_engine in engines_to_try:
            try:
                logger.info(
                    f"FIM request: engine={current_engine.value}, "
                    f"file={request.file_path}, "
                    f"num_completions={request.num_completions}"
                )

                # LiteLLM 호출
                response = await self._call_litellm(
                    request=request,
                    engine=current_engine,
                    n=request.num_completions,
                )

                # Completion 변환
                completions: list[Completion] = []
                total_tokens = 0

                for choice in response.choices:
                    text = choice.message.content or ""
                    finish_reason = choice.finish_reason or "unknown"

                    # logprobs 추출 (OpenAI only)
                    logprobs = getattr(choice, "logprobs", None)

                    # 점수 계산
                    score = self._calculate_score(text, logprobs, finish_reason)

                    # tokens_used 추출 (choice.usage는 보통 없음)
                    # 일단 0으로 설정하고 나중에 response.usage에서 계산
                    tokens_used = 0

                    completions.append(
                        Completion(
                            text=text,
                            score=score,
                            reasoning=f"Engine: {current_engine.value}, Finish: {finish_reason}",
                            tokens_used=tokens_used,
                            finish_reason=finish_reason,
                        )
                    )

                # 총 토큰 (response.usage에서)
                if hasattr(response, "usage") and response.usage:
                    total_tokens = getattr(response.usage, "total_tokens", 0)

                # 각 completion에 균등 배분
                if total_tokens > 0 and completions:
                    tokens_per_completion = total_tokens // len(completions)
                    for comp in completions:
                        comp.tokens_used = tokens_per_completion

                execution_time_ms = (time.perf_counter() - start_time) * 1000

                logger.info(
                    f"FIM success: completions={len(completions)}, "
                    f"tokens={total_tokens}, "
                    f"time={execution_time_ms:.1f}ms"
                )

                return FIMResult(
                    completions=completions,
                    execution_time_ms=execution_time_ms,
                    total_tokens=total_tokens,
                    engine_used=current_engine,
                )

            except (TimeoutError, RuntimeError) as e:
                last_error = e
                logger.warning(f"FIM failed with {current_engine.value}: {e}")

                # Fallback 시도
                if current_engine != engines_to_try[-1]:
                    continue
                else:
                    # 모든 엔진 실패
                    execution_time_ms = (time.perf_counter() - start_time) * 1000
                    return FIMResult(
                        completions=[],
                        execution_time_ms=execution_time_ms,
                        error=f"All engines failed. Last error: {last_error}",
                    )

        # Should not reach here
        raise RuntimeError("Unexpected error in complete()")

    async def complete_streaming(
        self,
        request: FIMRequest,
    ) -> AsyncIterator[Completion]:
        """
        코드 완성 (스트리밍 모드)

        주의: num_completions > 1이면 첫 번째만 스트리밍

        Args:
            request: FIM 요청

        Yields:
            Completion: 완성 후보 (실시간 스트리밍)

        Raises:
            ValueError: Invalid request
            TimeoutError: LLM timeout
            RuntimeError: LLM API error
        """
        engine = request.engine or self.default_engine
        model = self.ENGINE_MODEL_MAP[engine]
        messages = self._build_fim_messages(request)

        logger.info(f"FIM streaming: engine={engine.value}, file={request.file_path}")

        try:
            # LiteLLM 스트리밍 호출
            response_stream = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                timeout=self.timeout,
                stream=True,  # 스트리밍 활성화
            )

            accumulated_text = ""
            tokens_used = 0
            finish_reason = "stop"

            # 스트림 처리
            async for chunk in response_stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                if not delta:
                    continue

                # 텍스트 누적
                content = getattr(delta, "content", "") or ""
                if content:
                    accumulated_text += content
                    tokens_used += 1  # 대략적 추정

                    # 중간 완성 yield (score는 임시)
                    yield Completion(
                        text=accumulated_text,
                        score=0.5,  # 스트리밍 중에는 임시 점수
                        reasoning=f"Streaming: {tokens_used} tokens",
                        tokens_used=tokens_used,
                        finish_reason="streaming",
                    )

                # finish_reason 추출
                if hasattr(chunk.choices[0], "finish_reason"):
                    finish_reason = chunk.choices[0].finish_reason or finish_reason

            # 최종 완성 (실제 점수 계산)
            final_score = self._calculate_score(accumulated_text, None, finish_reason)

            yield Completion(
                text=accumulated_text,
                score=final_score,
                reasoning=f"Final: {engine.value}",
                tokens_used=tokens_used,
                finish_reason=finish_reason,
            )

            logger.info(f"FIM streaming done: tokens={tokens_used}, score={final_score:.2f}")

        except asyncio.TimeoutError as e:
            raise TimeoutError(f"LLM streaming timeout after {self.timeout}s") from e
        except Exception as e:
            raise RuntimeError(f"LLM streaming error ({engine.value}): {e}") from e
