"""Refactoring infrastructure for reasoning engine."""

from .intent_preservation import (
    IntentPreservation,
    IntentPreservationChecker,
    RefactoringResult,
    SemanticPatch,
)
from .two_phase_engine import (
    RefactorPhase,
    RefactorPlan,
    RefactorResult,
    TwoPhaseRefactoringEngine,
)
from .llm_patch_generator import LLMPatchGenerator
from .multi_layer_verifier import MultiLayerVerifier
from .llm_refactoring_engine import LLMRefactoringEngine

__all__ = [
    # RFC-102: Two-Phase Refactoring
    "IntentPreservation",
    "IntentPreservationChecker",
    "SemanticPatch",
    "RefactoringResult",
    "TwoPhaseRefactoringEngine",
    "RefactorPhase",
    "RefactorPlan",
    "RefactorResult",
    # RFC-101 Phase 2: LLM Refactoring
    "LLMPatchGenerator",
    "MultiLayerVerifier",
    "LLMRefactoringEngine",
]
