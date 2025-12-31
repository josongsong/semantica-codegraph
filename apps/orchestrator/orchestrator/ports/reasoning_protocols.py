"""
Reasoning Strategy Protocols

추론 전략에서 사용하는 함수 타입 정의 (순환 참조 방지).
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from apps.orchestrator.orchestrator.shared.reasoning.beam.beam_models import BeamCandidate
    from apps.orchestrator.orchestrator.shared.reasoning.deep.deep_models import (
        ReasoningStep,
        VerificationResult,
    )
    from apps.orchestrator.orchestrator.shared.reasoning.sampling.alphacode_models import SampleCandidate


# =============================================================================
# Protocols
# =============================================================================


@runtime_checkable
class ExpandFunction(Protocol):
    """Beam Search expand 함수"""

    def __call__(self, candidate: "BeamCandidate") -> list["BeamCandidate"]:
        """후보 확장"""
        ...


@runtime_checkable
class EvaluateFunction(Protocol):
    """후보 평가 함수"""

    def __call__(self, candidate: "BeamCandidate") -> float:
        """후보 평가"""
        ...


@runtime_checkable
class GenerateFunction(Protocol):
    """샘플 생성 함수"""

    def __call__(self, prompt: str, count: int) -> list["SampleCandidate"]:
        """샘플 생성"""
        ...


@runtime_checkable
class AnswerFunction(Protocol):
    """답변 생성 함수"""

    def __call__(self, question: str) -> str:
        """답변 생성"""
        ...


@runtime_checkable
class VerifyFunction(Protocol):
    """검증 함수"""

    def __call__(self, step: "ReasoningStep") -> "VerificationResult":
        """추론 단계 검증"""
        ...


@runtime_checkable
class RefineFunction(Protocol):
    """개선 함수"""

    def __call__(self, step: "ReasoningStep", verification: "VerificationResult") -> "ReasoningStep":
        """추론 단계 개선"""
        ...
