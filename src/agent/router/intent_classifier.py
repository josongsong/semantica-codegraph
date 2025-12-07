"""Intent 분류기 (LLM 기반)

사용자 입력을 분석하여 Intent로 분류
Prompt Manager를 사용하여 중앙화된 프롬프트 관리
"""

import json
from typing import Any

from src.agent.prompts.manager import PromptManager
from src.infra.llm.litellm_adapter import LiteLLMAdapter

from .models import Intent, IntentResult


class IntentClassifier:
    """사용자 입력을 Intent로 분류"""

    def __init__(self, llm: LiteLLMAdapter, prompt_manager: PromptManager | None = None):
        self.llm = llm
        self.prompts = prompt_manager or PromptManager()

    async def classify(self, user_input: str, context: dict[str, Any] | None = None) -> IntentResult:
        """
        Intent 분류

        Args:
            user_input: 사용자 입력 텍스트
            context: 추가 컨텍스트 정보

        Returns:
            IntentResult: 분류 결과 (intent, confidence, reasoning)
        """
        prompt = self.prompts.get_intent_prompt(user_input)

        # LLM 호출
        response_text = await self.llm.complete(
            prompt=prompt,
            model="gpt-4o-mini",  # Layer0용 작은 모델
            temperature=0.0,
        )

        # JSON 파싱
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError as e:
            # Fallback: 파싱 실패 시 UNKNOWN
            return IntentResult(
                intent=Intent.UNKNOWN,
                confidence=0.0,
                reasoning=f"Failed to parse LLM response: {e}",
                context=context or {},
            )

        # Intent enum으로 변환
        try:
            intent = Intent(result["intent"].lower())
        except (KeyError, ValueError):
            intent = Intent.UNKNOWN

        return IntentResult(
            intent=intent,
            confidence=result.get("confidence", 0.0),
            reasoning=result.get("reasoning", ""),
            context=context or {},
        )
