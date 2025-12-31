"""
o1 Engine

OpenAI o1 스타일 추론 엔진.
- Chain-of-Thought
- 자체 검증
- 단계별 분해
"""

import logging
import time
from collections.abc import Callable

from .deep_models import (
    DeepReasoningConfig,
    DeepReasoningResult,
    ReasoningStep,
    VerificationResult,
)
from .reasoning_chain import ReasoningChain
from .thought_decomposer import ThoughtDecomposer
from .verification_loop import VerificationLoop

logger = logging.getLogger(__name__)


class O1Engine:
    """o1 스타일 추론 엔진"""

    def __init__(self, config: DeepReasoningConfig | None = None):
        self.config = config or DeepReasoningConfig()
        self.chain_builder = ReasoningChain(self.config)
        self.decomposer = ThoughtDecomposer(self.config.max_depth)
        self.verifier = VerificationLoop(
            self.config.max_verification_attempts,
            self.config.verification_threshold,
        )

    async def reason(
        self,
        problem: str,
        answer_fn: Callable[[str], str],
        verify_fn: Callable[[ReasoningStep], VerificationResult],
        refine_fn: Callable[[ReasoningStep, VerificationResult], ReasoningStep],
    ) -> DeepReasoningResult:
        """
        o1 스타일 추론 실행

        Args:
            problem: 문제
            answer_fn: 답변 생성 함수
            verify_fn: 검증 함수
            refine_fn: 개선 함수

        Returns:
            추론 결과
        """
        start_time = time.time()
        logger.info(f"o1 reasoning started for: {problem[:100]}...")

        # 1. Chain-of-Thought 구축
        logger.info("Building reasoning chain...")
        steps = await self.chain_builder.build_chain(problem, answer_fn)

        # 2. 각 단계 검증 및 개선
        verified_steps = []
        all_verifications = []

        for step in steps:
            logger.info(f"Verifying step {step.step_number}...")

            verified_step, verifications = await self.verifier.verify_and_refine(step, verify_fn, refine_fn)

            verified_steps.append(verified_step)
            all_verifications.extend(verifications)

        # 3. 최종 답변 합성
        final_answer = self._synthesize_answer(verified_steps)
        final_code = self._extract_code(verified_steps)

        # 4. 결과 생성
        reasoning_time = time.time() - start_time

        total_thoughts = sum(len(step.thought_nodes) for step in verified_steps)
        max_depth = max((step.get_depth() for step in verified_steps), default=0)

        result = DeepReasoningResult(
            final_answer=final_answer,
            final_code=final_code,
            reasoning_steps=verified_steps,
            total_thoughts=total_thoughts,
            verification_results=all_verifications,
            total_depth=max_depth,
            total_steps=len(verified_steps),
            total_verifications=len(all_verifications),
            reasoning_time=reasoning_time,
        )

        result.final_confidence = result.get_final_confidence()

        logger.info(
            f"o1 reasoning completed in {reasoning_time:.2f}s: "
            f"{len(verified_steps)} steps, confidence={result.final_confidence:.2f}"
        )

        return result

    def _synthesize_answer(self, steps: list[ReasoningStep]) -> str:
        """
        단계들로부터 최종 답변 합성

        Args:
            steps: 추론 단계들

        Returns:
            최종 답변
        """
        if not steps:
            return ""

        # 마지막 단계의 답변 사용
        return steps[-1].answer

    def _extract_code(self, steps: list[ReasoningStep]) -> str:
        """
        단계들로부터 코드 추출

        Args:
            steps: 추론 단계들

        Returns:
            추출된 코드
        """
        # 모든 답변에서 코드 블록 찾기
        code_blocks = []

        for step in steps:
            answer = step.answer
            # 간단한 코드 블록 추출
            if "```" in answer:
                parts = answer.split("```")
                for i in range(1, len(parts), 2):
                    code_blocks.append(parts[i].strip())

        return "\n\n".join(code_blocks) if code_blocks else ""

    def reason_sync(
        self,
        problem: str,
        answer_fn: Callable[[str], str],
        verify_fn: Callable[[ReasoningStep], VerificationResult],
        refine_fn: Callable[[ReasoningStep, VerificationResult], ReasoningStep],
    ) -> DeepReasoningResult:
        """동기 버전"""
        import asyncio

        return asyncio.run(self.reason(problem, answer_fn, verify_fn, refine_fn))
