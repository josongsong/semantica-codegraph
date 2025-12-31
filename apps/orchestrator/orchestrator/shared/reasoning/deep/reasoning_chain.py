"""
Reasoning Chain

Chain-of-Thought 기반 추론 체인.
"""

import logging
import uuid
from collections.abc import Callable

from .deep_models import (
    DeepReasoningConfig,
    ReasoningStep,
    ThoughtNode,
    ThoughtType,
)

logger = logging.getLogger(__name__)


class ReasoningChain:
    """추론 체인"""

    def __init__(self, config: DeepReasoningConfig):
        self.config = config

    async def build_chain(
        self,
        initial_question: str,
        answer_fn: Callable[[str], str],
    ) -> list[ReasoningStep]:
        """
        추론 체인 구축

        Args:
            initial_question: 초기 질문
            answer_fn: 답변 생성 함수 (LLM)

        Returns:
            추론 단계 리스트
        """
        steps: list[ReasoningStep] = []
        current_question = initial_question

        for step_num in range(1, self.config.max_steps + 1):
            logger.info(f"Building reasoning step {step_num}/{self.config.max_steps}")

            try:
                # 답변 생성
                answer = answer_fn(current_question)

                # 사고 노드 생성
                thought_node = ThoughtNode(
                    node_id=str(uuid.uuid4()),
                    depth=0,
                    thought_type=ThoughtType.ANALYSIS,
                    content=answer,
                    reasoning=f"Answer to: {current_question}",
                    confidence=0.8,  # 기본값
                )

                # 추론 단계 생성
                step = ReasoningStep(
                    step_id=str(uuid.uuid4()),
                    step_number=step_num,
                    question=current_question,
                    answer=answer,
                    thought_nodes=[thought_node],
                )

                steps.append(step)

                # 다음 질문 생성 (마지막 단계가 아니면)
                if step_num < self.config.max_steps:
                    current_question = self._generate_next_question(answer)
                else:
                    break

            except Exception as e:
                logger.warning(f"Failed to build step {step_num}: {e}")
                break

        logger.info(f"Built reasoning chain with {len(steps)} steps")
        return steps

    def _generate_next_question(self, previous_answer: str) -> str:
        """
        이전 답변을 기반으로 다음 질문 생성

        Args:
            previous_answer: 이전 답변

        Returns:
            다음 질문
        """
        # 간단한 휴리스틱: "그렇다면..." 으로 시작
        return f"Given that: {previous_answer[:100]}..., what should we do next?"

    def build_chain_sync(
        self,
        initial_question: str,
        answer_fn: Callable[[str], str],
    ) -> list[ReasoningStep]:
        """동기 버전"""
        import asyncio

        return asyncio.run(self.build_chain(initial_question, answer_fn))
