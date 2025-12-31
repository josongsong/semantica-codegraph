"""
Verification Loop

추론 결과를 검증하고 수정하는 루프.
"""

import logging
from collections.abc import Callable

from .deep_models import DeepReasoningResult, ReasoningStep, VerificationResult

logger = logging.getLogger(__name__)


class VerificationLoop:
    """검증 루프"""

    def __init__(self, max_attempts: int = 3, threshold: float = 0.7):
        self.max_attempts = max_attempts
        self.threshold = threshold

    async def reason(
        self,
        problem: str,
        answer_fn: Callable[[str, int], str],
        verify_fn: Callable[[ReasoningStep], VerificationResult],
        refine_fn: Callable[[ReasoningStep, VerificationResult], ReasoningStep],
    ) -> DeepReasoningResult:
        """
        Complete reasoning with verification loop

        Args:
            problem: Problem to solve
            answer_fn: Function to generate answer
            verify_fn: Function to verify step
            refine_fn: Function to refine step

        Returns:
            DeepReasoningResult
        """
        steps: list[ReasoningStep] = []

        for iteration in range(self.max_attempts):
            # Generate answer
            answer = await answer_fn(problem, iteration)

            step = ReasoningStep(
                step_id=f"step_{iteration}",
                step_number=iteration,
                question=problem,
                answer=answer,
            )

            # Verify (handle async verify_fn)
            verification = await verify_fn(step)

            # Check if passed
            if verification.is_valid:
                steps.append(step)
                return DeepReasoningResult(
                    final_answer=step.answer,
                    final_code=self._extract_code_from_answer(step.answer),
                    reasoning_steps=steps,
                    total_thoughts=iteration + 1,
                    final_confidence=verification.confidence,
                )

            # Refine if not correct
            refined_step = await refine_fn(step, verification)
            steps.append(refined_step)

            # Check refined step
            if iteration == self.max_attempts - 1:
                # Last iteration
                final_verification = await verify_fn(refined_step)
                if final_verification.is_valid:
                    return DeepReasoningResult(
                        final_answer=refined_step.answer,
                        final_code=self._extract_code_from_answer(refined_step.answer),
                        reasoning_steps=steps,
                        total_thoughts=iteration + 1,
                        final_confidence=final_verification.confidence,
                    )

        # Max iterations reached
        final_ans = steps[-1].answer if steps else ""
        return DeepReasoningResult(
            final_answer=final_ans,
            final_code=self._extract_code_from_answer(final_ans),
            reasoning_steps=steps,
            total_thoughts=self.max_attempts,
            final_confidence=0.0,
        )

    def _extract_code_from_answer(self, answer: str) -> str:
        """Extract code from reasoning answer"""
        import re

        match = re.search(r"```python\s*(.*?)\s*```", answer, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    async def verify_and_refine(
        self,
        step: ReasoningStep,
        verify_fn: Callable[[ReasoningStep], VerificationResult],
        refine_fn: Callable[[ReasoningStep, VerificationResult], ReasoningStep],
    ) -> tuple[ReasoningStep, list[VerificationResult]]:
        """
        추론 단계를 검증하고 개선

        Args:
            step: 추론 단계
            verify_fn: 검증 함수
            refine_fn: 개선 함수

        Returns:
            (개선된 단계, 검증 결과 리스트)
        """
        verification_results: list[VerificationResult] = []
        current_step = step

        for attempt in range(self.max_attempts):
            logger.info(f"Verification attempt {attempt + 1}/{self.max_attempts}")

            try:
                # 검증
                result = verify_fn(current_step)
                verification_results.append(result)

                # 통과 여부 확인
                if result.is_valid and result.confidence >= self.threshold:
                    logger.info(f"Verification passed with confidence {result.confidence:.2f}")
                    current_step.is_correct = True
                    current_step.verification_attempts = attempt + 1
                    break

                # 개선
                logger.info(f"Verification failed (confidence={result.confidence:.2f}), refining...")
                current_step = refine_fn(current_step, result)
                current_step.verification_attempts = attempt + 1

            except Exception as e:
                logger.warning(f"Verification attempt {attempt + 1} failed: {e}")
                continue

        if not current_step.is_correct:
            logger.warning(f"Verification failed after {self.max_attempts} attempts")

        return current_step, verification_results

    def verify_and_refine_sync(
        self,
        step: ReasoningStep,
        verify_fn: Callable[[ReasoningStep], VerificationResult],
        refine_fn: Callable[[ReasoningStep, VerificationResult], ReasoningStep],
    ) -> tuple[ReasoningStep, list[VerificationResult]]:
        """동기 버전"""
        import asyncio

        return asyncio.run(self.verify_and_refine(step, verify_fn, refine_fn))
