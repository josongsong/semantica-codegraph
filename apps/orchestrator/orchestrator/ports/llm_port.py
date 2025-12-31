"""
LLM Port Interface

추론 전략에서 사용하는 LLM 인터페이스 (Hexagonal Architecture).
"""

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from apps.orchestrator.orchestrator.shared.reasoning.beam.beam_models import BeamCandidate
from apps.orchestrator.orchestrator.shared.reasoning.deep.deep_models import (
    ReasoningStep,
    VerificationResult,
)
from apps.orchestrator.orchestrator.shared.reasoning.sampling.alphacode_models import SampleCandidate

# =============================================================================
# Core LLM Interface
# =============================================================================


class LLMPort(ABC):
    """LLM 추상 인터페이스"""

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        텍스트 생성

        Args:
            prompt: 프롬프트
            **kwargs: 추가 설정 (temperature, max_tokens 등)

        Returns:
            생성된 텍스트

        Raises:
            LLMError: 생성 실패
        """
        pass

    @abstractmethod
    async def generate_batch(self, prompts: list[str], **kwargs) -> list[str]:
        """
        배치 생성

        Args:
            prompts: 프롬프트 리스트
            **kwargs: 추가 설정

        Returns:
            생성된 텍스트 리스트
        """
        pass


# =============================================================================
# Strategy-Specific Protocols
# =============================================================================


@runtime_checkable
class ExpandFunction(Protocol):
    """Beam Search expand 함수"""

    def __call__(self, candidate: BeamCandidate) -> list[BeamCandidate]:
        """
        후보 확장

        Args:
            candidate: 현재 후보

        Returns:
            확장된 후보 리스트
        """
        ...


@runtime_checkable
class EvaluateFunction(Protocol):
    """후보 평가 함수"""

    def __call__(self, candidate: BeamCandidate) -> float:
        """
        후보 평가

        Args:
            candidate: 평가할 후보

        Returns:
            점수 (0.0 ~ 1.0)
        """
        ...


@runtime_checkable
class GenerateFunction(Protocol):
    """샘플 생성 함수"""

    def __call__(self, prompt: str, count: int) -> list[SampleCandidate]:
        """
        샘플 생성

        Args:
            prompt: 프롬프트
            count: 생성할 샘플 수

        Returns:
            생성된 샘플 리스트
        """
        ...


@runtime_checkable
class AnswerFunction(Protocol):
    """답변 생성 함수 (Deep Reasoning)"""

    def __call__(self, question: str) -> str:
        """
        질문에 대한 답변 생성

        Args:
            question: 질문

        Returns:
            답변
        """
        ...


@runtime_checkable
class VerifyFunction(Protocol):
    """검증 함수 (Deep Reasoning)"""

    def __call__(self, step: ReasoningStep) -> VerificationResult:
        """
        추론 단계 검증

        Args:
            step: 추론 단계

        Returns:
            검증 결과
        """
        ...


@runtime_checkable
class RefineFunction(Protocol):
    """개선 함수 (Deep Reasoning)"""

    def __call__(self, step: ReasoningStep, verification: VerificationResult) -> ReasoningStep:
        """
        추론 단계 개선

        Args:
            step: 현재 단계
            verification: 검증 결과

        Returns:
            개선된 단계
        """
        ...


# =============================================================================
# Errors
# =============================================================================


class LLMError(Exception):
    """LLM 관련 에러"""

    pass


class LLMTimeoutError(LLMError):
    """LLM 타임아웃"""

    pass


class LLMRateLimitError(LLMError):
    """LLM Rate Limit"""

    pass
