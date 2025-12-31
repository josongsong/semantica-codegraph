"""
Deep Reasoning Models

o1/r1 스타일 깊은 추론을 위한 데이터 모델.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ThoughtType(str, Enum):
    """사고 타입"""

    ANALYSIS = "analysis"  # 문제 분석
    DECOMPOSITION = "decomposition"  # 문제 분해
    HYPOTHESIS = "hypothesis"  # 가설 생성
    VERIFICATION = "verification"  # 가설 검증
    REFLECTION = "reflection"  # 반성적 사고
    SYNTHESIS = "synthesis"  # 통합


@dataclass
class ThoughtNode:
    """사고 노드 (단계별 추론)"""

    # Identity
    node_id: str
    depth: int
    parent_id: str | None = None

    # Content
    thought_type: ThoughtType = ThoughtType.ANALYSIS
    content: str = ""
    reasoning: str = ""

    # Verification
    is_verified: bool = False
    confidence: float = 0.0  # 0.0 ~ 1.0

    # Child nodes
    children: list[str] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ReasoningStep:
    """추론 단계"""

    step_id: str
    step_number: int

    # Content
    question: str  # 이 단계에서 답해야 할 질문
    answer: str  # 답변
    thought_nodes: list[ThoughtNode] = field(default_factory=list)

    # Verification
    is_correct: bool = False
    verification_attempts: int = 0

    def get_depth(self) -> int:
        """최대 깊이 반환"""
        if not self.thought_nodes:
            return 0
        return max(node.depth for node in self.thought_nodes)


@dataclass
class VerificationResult:
    """검증 결과"""

    is_valid: bool
    confidence: float  # 0.0 ~ 1.0
    errors: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class DeepReasoningConfig:
    """Deep Reasoning 설정"""

    # Chain of Thought
    max_depth: int = 5  # 최대 사고 깊이
    max_steps: int = 10  # 최대 추론 단계

    # Verification
    verification_threshold: float = 0.7  # 검증 통과 임계값
    max_verification_attempts: int = 3  # 최대 검증 시도

    # o1/r1 specific
    use_self_reflection: bool = True  # 자체 반성 사용
    use_hypothesis_testing: bool = True  # 가설 검증 사용


@dataclass
class DeepReasoningResult:
    """Deep Reasoning 결과"""

    # Final answer
    final_answer: str = ""
    final_code: str = ""

    # Reasoning trace
    reasoning_steps: list[ReasoningStep] = field(default_factory=list)
    total_thoughts: int = 0

    # Verification
    verification_results: list[VerificationResult] = field(default_factory=list)
    final_confidence: float = 0.0

    # Metrics
    total_depth: int = 0
    total_steps: int = 0
    total_verifications: int = 0
    reasoning_time: float = 0.0

    def get_reasoning_trace(self) -> str:
        """
        추론 과정을 텍스트로 반환

        Returns:
            추론 trace
        """
        trace_lines = []

        for step in self.reasoning_steps:
            trace_lines.append(f"\n## Step {step.step_number}: {step.question}")
            trace_lines.append(f"Answer: {step.answer}")

            # Thought nodes
            for node in step.thought_nodes:
                indent = "  " * node.depth
                trace_lines.append(f"{indent}- [{node.thought_type.value}] {node.content}")

        return "\n".join(trace_lines)

    def get_final_confidence(self) -> float:
        """
        최종 신뢰도 계산

        Returns:
            평균 신뢰도
        """
        if not self.verification_results:
            return 0.0

        valid_results = [v for v in self.verification_results if v.is_valid]
        if not valid_results:
            return 0.0

        return sum(v.confidence for v in valid_results) / len(valid_results)
