"""
LiteLLM Provider Adapter

ILLMProvider 포트 구현.

특징:
- LiteLLM으로 다양한 LLM 통합 (OpenAI, Anthropic, etc.)
- Fallback 지원
- Cost tracking
- Rate limiting
"""

from typing import Any

import litellm

from src.ports import ILLMProvider

# Global 설정: Unsupported params 자동 제거 (O-series 모델 등)
litellm.drop_params = True


class LiteLLMProviderAdapter(ILLMProvider):
    """
    LiteLLM → ILLMProvider Adapter.

    LiteLLM으로 다양한 LLM을 통합하고, fallback/retry 지원.
    """

    def __init__(
        self,
        primary_model: str = "gpt-4o-mini",
        fallback_models: list[str] | None = None,
        api_key: str | None = None,
        timeout: int = 60,
    ):
        """
        Args:
            primary_model: 기본 모델 (예: "gpt-4", "claude-3-sonnet")
            fallback_models: Fallback 모델 리스트
            api_key: API 키 (환경변수에서도 가능)
            timeout: 타임아웃 (초)
        """
        self.primary_model = primary_model
        self.fallback_models = fallback_models or []
        self.api_key = api_key
        self.timeout = timeout

        # LiteLLM import (lazy)
        self._litellm = None

    def _get_litellm(self):
        """LiteLLM lazy import"""
        if self._litellm is None:
            try:
                import litellm

                self._litellm = litellm

                # API 키 설정
                if self.api_key:
                    import os

                    os.environ["OPENAI_API_KEY"] = self.api_key

            except ImportError:
                raise ImportError("litellm not installed. Run: pip install litellm")

        return self._litellm

    async def complete(self, messages: list[dict[str, str]], model_tier: str = "medium", **kwargs: Any) -> str:
        """
        Text completion.

        Args:
            messages: OpenAI format 메시지 리스트
            model_tier: "fast" | "medium" | "strong"
            **kwargs: temperature, max_tokens 등

        Returns:
            생성된 텍스트
        """
        litellm = self._get_litellm()

        # 모델 선택 (tier 기반)
        model_map = {
            "fast": "gpt-4o-mini",
            "medium": "gpt-4o",
            "strong": "o1-preview",
        }
        model = kwargs.get("model", model_map.get(model_tier, self.primary_model))
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 2000)

        # Fallback chain
        models_to_try = [model] + self.fallback_models

        last_error = None
        for current_model in models_to_try:
            try:
                response = await litellm.acompletion(
                    model=current_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=self.timeout,
                )

                # 응답 추출
                return response.choices[0].message.content

            except Exception as e:
                last_error = e
                # Fallback 시도
                if current_model != models_to_try[-1]:
                    continue
                else:
                    # 모든 모델 실패
                    raise RuntimeError(f"All models failed. Last error: {last_error}") from last_error

        # Should not reach here
        raise RuntimeError("Unexpected error in complete()")

    async def complete_with_schema(
        self,
        messages: list[dict[str, str]],
        schema: type,
        model_tier: str = "medium",
        **kwargs: Any,
    ) -> Any:
        """
        Structured output (Pydantic schema).

        Args:
            messages: 메시지 리스트
            schema: Pydantic BaseModel 클래스
            model_tier: 모델 등급
            **kwargs: temperature, max_tokens 등

        Returns:
            schema 인스턴스 (파싱 보장)
        """
        litellm = self._get_litellm()

        # 모델 선택
        model_map = {
            "fast": "gpt-4o-mini",
            "medium": "gpt-4o",
            "strong": "o1-preview",
        }
        model = kwargs.get("model", model_map.get(model_tier, self.primary_model))
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 2000)

        # JSON schema 추출
        json_schema = schema.model_json_schema()

        # System message로 schema 전달
        system_message = f"""You must respond in JSON format matching this schema:
{json_schema}

Respond ONLY with valid JSON, no additional text."""

        # 기존 messages에 system message 추가
        full_messages = [{"role": "system", "content": system_message}] + messages

        try:
            response = await litellm.acompletion(
                model=model,
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=self.timeout,
                response_format={"type": "json_object"} if "gpt" in model.lower() else None,
            )

            # JSON 파싱
            import json

            content = response.choices[0].message.content
            data = json.loads(content)

            # Pydantic 검증
            return schema(**data)

        except Exception as e:
            raise RuntimeError(f"Structured output failed: {e}") from e

    async def get_embedding(self, text: str, model: str = "text-embedding-3-small") -> list[float]:
        """
        Text embedding.

        Args:
            text: 입력 텍스트
            model: Embedding 모델 (기본: text-embedding-3-small)

        Returns:
            Embedding vector
        """
        litellm = self._get_litellm()

        try:
            response = await litellm.aembedding(
                model=model,
                input=text,
                timeout=self.timeout,
            )

            return response.data[0]["embedding"]

        except Exception as e:
            raise RuntimeError(f"Embedding failed: {e}") from e


# ============================================================
# Stub LLM Provider (테스트용)
# ============================================================


class StubLLMProvider(ILLMProvider):
    """
    Stub LLM Provider.

    테스트/개발용 Mock LLM.
    실제 API 호출 없이 하드코딩된 응답 반환.
    """

    async def complete(self, messages: list[dict[str, str]], model_tier: str = "medium", **kwargs: Any) -> str:
        """Stub completion"""
        # 마지막 메시지 내용 추출
        if messages:
            content = messages[-1].get("content", "")
        else:
            content = ""

        # 간단한 휴리스틱 응답
        if "bug" in content.lower() or "fix" in content.lower():
            return "The bug is in the discount calculation. Change `return price - discount_rate` to `discount = price * discount_rate; return price - discount`."

        if "plan" in content.lower():
            return "1. Analyze the code\n2. Identify the bug\n3. Fix the calculation\n4. Run tests"

        return "Mock LLM response"

    async def complete_with_schema(
        self,
        messages: list[dict[str, str]],
        schema: type,
        model_tier: str = "medium",
        **kwargs: Any,
    ) -> Any:
        """Stub structured output"""
        # 기본값으로 Pydantic 모델 생성
        # (실제로는 필드를 분석해서 채워야 하지만 stub이므로 간단히)
        return schema()

    async def get_embedding(self, text: str, model: str = "text-embedding-3-small") -> list[float]:
        """Stub embedding"""
        # 간단한 hash 기반 embedding (실제로는 의미 없음)
        import hashlib

        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)

        # 384-dim vector (text-embedding-3-small)
        return [(hash_val % 1000) / 1000.0] * 384
