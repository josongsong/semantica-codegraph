"""
o1/r1 Deep Reasoning

깊은 추론을 위한 Chain-of-Thought + 자체 검증.
"""

from .deep_models import (
    DeepReasoningConfig,
    DeepReasoningResult,
    ReasoningStep,
    ThoughtNode,
    VerificationResult,
)
from .o1_engine import O1Engine
from .r1_engine import R1Engine
from .reasoning_chain import ReasoningChain
from .thought_decomposer import ThoughtDecomposer
from .verification_loop import VerificationLoop

# Alias for backward compatibility
DeepReasoningEngine = VerificationLoop

__all__ = [
    "DeepReasoningConfig",
    "DeepReasoningResult",
    "ReasoningStep",
    "ThoughtNode",
    "VerificationResult",
    "O1Engine",
    "R1Engine",
    "ReasoningChain",
    "ThoughtDecomposer",
    "VerificationLoop",
    "DeepReasoningEngine",  # Alias
]
