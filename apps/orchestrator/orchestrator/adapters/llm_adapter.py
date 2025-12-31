"""
LLM Adapter Implementation

실제 LLM (OpenAI, Anthropic) 연동.
"""

import logging
import os

from apps.orchestrator.orchestrator.ports.llm_port import LLMError, LLMPort, LLMTimeoutError

logger = logging.getLogger(__name__)


class OpenAIAdapter(LLMPort):
    """OpenAI LLM Adapter"""

    def __init__(self, api_key: str | None = None, model: str = "gpt-4"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY required")

        self.model = model

        try:
            import openai

            self.client = openai.OpenAI(api_key=self.api_key)
        except ImportError:
            raise RuntimeError("openai package required. Install: pip install openai")

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        텍스트 생성

        Args:
            prompt: 프롬프트
            **kwargs: temperature, max_tokens 등

        Returns:
            생성된 텍스트

        Raises:
            LLMError: 생성 실패
            LLMTimeoutError: 타임아웃
        """
        try:
            response = self.client.chat.completions.create(
                model=kwargs.get("model", self.model),
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 1000),
                timeout=kwargs.get("timeout", 30.0),
            )

            content = response.choices[0].message.content
            if not content:
                raise LLMError("Empty response from LLM")

            logger.debug(f"Generated {len(content)} chars")
            return content

        except TimeoutError as e:
            raise LLMTimeoutError(f"LLM timeout: {e}") from e
        except Exception as e:
            raise LLMError(f"LLM generation failed: {e}") from e

    async def generate_batch(self, prompts: list[str], **kwargs) -> list[str]:
        """
        배치 생성

        Args:
            prompts: 프롬프트 리스트
            **kwargs: 추가 설정

        Returns:
            생성된 텍스트 리스트
        """
        import asyncio

        tasks = [self.generate(prompt, **kwargs) for prompt in prompts]
        return await asyncio.gather(*tasks, return_exceptions=False)


class MockLLMAdapter(LLMPort):
    """Mock LLM (테스트용)"""

    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or ["Mock response"]
        self.call_count = 0

    async def generate(self, prompt: str, **kwargs) -> str:
        """Mock 응답 반환"""
        response = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        logger.debug(f"Mock generated: {response[:50]}...")
        return response

    async def generate_batch(self, prompts: list[str], **kwargs) -> list[str]:
        """Mock 배치 응답"""
        return [await self.generate(p, **kwargs) for p in prompts]
