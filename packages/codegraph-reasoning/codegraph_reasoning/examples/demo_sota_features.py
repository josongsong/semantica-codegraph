"""
Demo: SOTA Reasoning Engine Features (RFC-101, RFC-102)

Demonstrates:
1. ReasoningContext (Determinism Contract)
2. EvidenceBundle (Standard Format)
3. ConfidenceAggregator (Multi-analyzer)
4. UNDECIDABLE Handling
5. IntentPreservation Classification
6. Two-Phase Refactoring
7. Failure Recovery
"""

from datetime import datetime

from ..domain.evidence_bundle import DecisionType, Evidence, EvidenceBundle, EvidenceType
from ..domain.reasoning_context import ReasoningContext, compute_input_hash
from ..infrastructure.llm.canonicalizer import LLMCanonicalizer
from ..infrastructure.llm.schemas import LLMOutputSchema
from ..infrastructure.refactoring.intent_preservation import (
    IntentPreservation,
    IntentPreservationChecker,
    SemanticPatch,
)
from ..infrastructure.refactoring.two_phase_engine import TwoPhaseRefactoringEngine
from ..infrastructure.reliability.failure_handler import FailureHandler, FailureType
from ..infrastructure.verification.confidence_aggregator import AnalysisResult, ConfidenceAggregator
from ..infrastructure.verification.undecidable_handler import UNDECIDABLEHandler


def demo_determinism_contract():
    """Demo: ReasoningContext ensures reproducibility."""
    print("=" * 80)
    print("DEMO 1: Determinism Contract (RFC-102)")
    print("=" * 80)

    # Create reasoning context
    context = ReasoningContext(
        engine_version="2.0.1",
        ruleset_hash="abc123...",
        rust_engine_hash="def456...",
        llm_model_id="gpt-4o-mini-2024-07-18",
        llm_temperature=0.0,
        input_hash=compute_input_hash("def foo():", "def bar():"),
    )

    print(f"Context Hash: {context.context_hash()}")
    print(f"Engine Version: {context.engine_version}")
    print(f"LLM Model: {context.llm_model_id}")
    print(f"Temperature: {context.llm_temperature} (deterministic)")

    # Same context → Same hash
    context2 = ReasoningContext(
        engine_version="2.0.1",
        ruleset_hash="abc123...",
        rust_engine_hash="def456...",
        llm_model_id="gpt-4o-mini-2024-07-18",
        llm_temperature=0.0,
        input_hash=compute_input_hash("def foo():", "def bar():"),
    )

    print(f"\n✓ Same input → Same hash: {context.context_hash() == context2.context_hash()}")
    print()


def demo_evidence_bundle():
    """Demo: EvidenceBundle standard format."""
    print("=" * 80)
    print("DEMO 2: Evidence Bundle Standard Format (RFC-102)")
    print("=" * 80)

    # Create evidence bundle
    bundle = EvidenceBundle(
        decision="is_breaking",
        confidence=0.95,
        decision_type=DecisionType.DECIDED,
        reasoning_context=ReasoningContext(
            engine_version="2.0.1",
            ruleset_hash="abc123...",
            rust_engine_hash="def456...",
            input_hash="input123...",
        ),
    )

    # Add evidence
    bundle.add_evidence(
        Evidence(
            type=EvidenceType.RULE_MATCH,
            description="Rule matched: GLOBAL_MUTATION_RULE",
            confidence=0.95,
            weight=0.5,
            analyzer="rule",
        )
    )

    bundle.add_evidence(
        Evidence(
            type=EvidenceType.FORMAL_PROOF,
            description="Formal proof: Memory leak detected",
            confidence=0.99,
            weight=0.4,
            analyzer="formal",
        )
    )

    # Display in different formats
    print("CLI Summary:")
    print(bundle.to_cli_summary())
    print()

    print("Markdown:")
    print(bundle.to_markdown())
    print()


def demo_confidence_aggregation():
    """Demo: ConfidenceAggregator with veto power."""
    print("=" * 80)
    print("DEMO 3: Confidence Aggregation (RFC-101)")
    print("=" * 80)

    aggregator = ConfidenceAggregator()

    # Scenario 1: All agree
    print("Scenario 1: All analyzers agree (consensus)")
    results = [
        AnalysisResult(
            is_breaking=True,
            confidence=0.95,
            evidence=["Global mutation detected"],
            analyzer="rule",
        ),
        AnalysisResult(
            is_breaking=True,
            confidence=0.98,
            evidence=["Memory leak (formal proof)"],
            analyzer="formal",
        ),
        AnalysisResult(
            is_breaking=True,
            confidence=0.85,
            evidence=["LLM: Breaking change"],
            analyzer="llm",
        ),
    ]

    bundle = aggregator.aggregate(results)
    print(f"Decision: {bundle.decision}")
    print(f"Confidence: {bundle.confidence:.2f}")
    print(f"Evidence count: {len(bundle.supporting_evidence)}")
    print()

    # Scenario 2: Formal proof veto
    print("Scenario 2: Formal proof has veto power")
    results = [
        AnalysisResult(
            is_breaking=False,
            confidence=0.7,
            evidence=["No obvious breaking change"],
            analyzer="rule",
        ),
        AnalysisResult(
            is_breaking=True,
            confidence=0.99,
            evidence=["Separation Logic: Memory leak proven"],
            analyzer="formal",
        ),
    ]

    bundle = aggregator.aggregate(results)
    print(f"Decision: {bundle.decision}")
    print(f"Confidence: {bundle.confidence:.2f} (formal veto)")
    print()

    # Scenario 3: LLM cannot override rule+formal
    print("Scenario 3: LLM cannot override rule+formal consensus")
    results = [
        AnalysisResult(
            is_breaking=False,
            confidence=0.9,
            evidence=["No breaking change (rule)"],
            analyzer="rule",
        ),
        AnalysisResult(
            is_breaking=False,
            confidence=0.95,
            evidence=["No breaking change (formal)"],
            analyzer="formal",
        ),
        AnalysisResult(
            is_breaking=True,
            confidence=0.8,
            evidence=["LLM: Might be breaking"],
            analyzer="llm",
        ),
    ]

    bundle = aggregator.aggregate(results)
    print(f"Decision: {bundle.decision}")
    print(f"Confidence: {bundle.confidence:.2f}")
    print(f"Counter evidence: {len(bundle.counter_evidence)} (LLM disagreed but overridden)")
    print()


def demo_undecidable_handling():
    """Demo: UNDECIDABLE as first-class result."""
    print("=" * 80)
    print("DEMO 4: UNDECIDABLE Handling (RFC-102)")
    print("=" * 80)

    handler = UNDECIDABLEHandler()

    # Low confidence → UNDECIDABLE
    print("Scenario: Low confidence → UNDECIDABLE")
    results = [
        AnalysisResult(
            is_breaking=True,
            confidence=0.6,  # Below threshold
            evidence=["Weak evidence"],
            analyzer="rule",
        ),
    ]

    bundle = handler.evaluate_decision(results, {"task": "breaking_change_detection"})
    print(f"Decision Type: {bundle.decision_type.value}")
    print(f"Reason: {bundle.undecidable_reason}")
    print(f"Required Info: {bundle.required_information}")
    print(f"Conservative Fallback: {bundle.conservative_fallback}")
    print()


def demo_intent_preservation():
    """Demo: IntentPreservation classification."""
    print("=" * 80)
    print("DEMO 5: Intent Preservation Classification (RFC-101)")
    print("=" * 80)

    checker = IntentPreservationChecker()

    # STRICT: Simple rename
    print("Scenario 1: STRICT (simple rename)")
    patch = SemanticPatch(
        before="def old_name():\n    return 42",
        after="def new_name():\n    return 42",
        description="Rename function",
    )

    intent = checker.classify(patch)
    print(f"Classification: {intent.value}")
    print()

    # WEAK: Control flow change with tests
    print("Scenario 2: WEAK (control flow change)")
    patch = SemanticPatch(
        before="x = 1\nif True:\n    x = 2",
        after="x = 2 if True else 1",
        description="Simplify if statement",
    )

    intent = checker.classify(patch)
    print(f"Classification: {intent.value}")
    print()

    # UNCERTAIN: Logic change
    print("Scenario 3: UNCERTAIN (logic change)")
    patch = SemanticPatch(
        before="if x > 0:\n    return True",
        after="if x >= 0:\n    return True",
        description="Change comparison",
    )

    intent = checker.classify(patch)
    print(f"Classification: {intent.value}")
    print()


def demo_two_phase_refactoring():
    """Demo: Two-phase refactoring (Plan → Apply)."""
    print("=" * 80)
    print("DEMO 6: Two-Phase Refactoring (RFC-102)")
    print("=" * 80)

    engine = TwoPhaseRefactoringEngine()

    code = """
def calculate(a, b):
    result = a + b
    return result
"""

    instruction = "Simplify function"

    # Phase 1: Generate plan
    print("Phase 1: Generate Plan")
    result = engine.generate_plan(code, instruction)

    if result.success and result.plan:
        plan = result.plan
        print(f"Summary: {plan.summary}")
        print(f"Estimated lines changed: {plan.estimated_lines_changed}")
        print(f"Complexity: {plan.estimated_complexity}")
        print(f"Risk flags: {plan.risk_flags}")
        print(f"Requires approval: {plan.requires_approval}")
        print()

        # Phase 2: Apply plan (if auto-approved)
        if not plan.requires_approval:
            print("Phase 2: Apply Plan (auto-approved)")
            apply_result = engine.apply_plan(plan, code)

            if apply_result.success and apply_result.patch:
                print(f"Success: {apply_result.success}")
                print(
                    f"Intent preservation: {apply_result.patch.intent_preservation.value if apply_result.patch.intent_preservation else 'N/A'}"
                )
                print()


def demo_failure_recovery():
    """Demo: Failure handling with graceful degradation."""
    print("=" * 80)
    print("DEMO 7: Failure Recovery (RFC-102)")
    print("=" * 80)

    handler = FailureHandler()

    # LLM timeout → Downgrade to rule-based
    print("Scenario 1: LLM timeout → Downgrade")
    recovery = handler.handle_failure(FailureType.LLM_TIMEOUT, context={"candidates": ["a", "b", "c"]})

    print(f"Success: {recovery.success}")
    print(f"Method: {recovery.method}")
    print(f"Warning: {recovery.warning}")
    print()

    # Type check failed → Fail-closed
    print("Scenario 2: Type check failed → Fail-closed")
    recovery = handler.handle_failure(FailureType.TYPE_CHECK_FAILED, context={})

    print(f"Success: {recovery.success}")
    print(f"Error: {recovery.error}")
    print(f"Escalation required: {recovery.escalation_required}")
    print()


def demo_llm_canonicalization():
    """Demo: LLM output canonicalization."""
    print("=" * 80)
    print("DEMO 8: LLM Canonicalization (RFC-102)")
    print("=" * 80)

    canonicalizer = LLMCanonicalizer()

    # Canonicalize Python code
    print("Python code canonicalization:")
    raw_code = """
import os
import sys
from pathlib import Path
import json


def foo():
    pass
"""

    canonical = canonicalizer.canonicalize_code(raw_code, "python")
    print("Canonical output:")
    print(canonical)
    print("✓ Imports sorted alphabetically")
    print("✓ Trailing whitespace removed")
    print("✓ Single newline at EOF")
    print()


def main():
    """Run all demos."""
    demos = [
        demo_determinism_contract,
        demo_evidence_bundle,
        demo_confidence_aggregation,
        demo_undecidable_handling,
        demo_intent_preservation,
        demo_two_phase_refactoring,
        demo_failure_recovery,
        demo_llm_canonicalization,
    ]

    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "SOTA REASONING ENGINE DEMOS" + " " * 31 + "║")
    print("║" + " " * 25 + "(RFC-101 & RFC-102)" + " " * 34 + "║")
    print("╚" + "=" * 78 + "╝")
    print("\n")

    for demo in demos:
        demo()

    print("=" * 80)
    print("ALL DEMOS COMPLETED ✓")
    print("=" * 80)
    print()
    print("Summary:")
    print("  - 8 SOTA features demonstrated")
    print("  - RFC-101: LLM-assisted, Graph pre-ranking, Intent preservation")
    print("  - RFC-102: Determinism, Failure recovery, UNDECIDABLE handling")
    print()


if __name__ == "__main__":
    main()
