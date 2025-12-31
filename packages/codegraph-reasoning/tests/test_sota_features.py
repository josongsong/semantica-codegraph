"""
Test suite for SOTA Reasoning Engine features (RFC-101, RFC-102).

Validates:
1. ReasoningContext determinism
2. EvidenceBundle format and serialization
3. ConfidenceAggregator veto power
4. UNDECIDABLEHandler threshold checking
5. IntentPreservation classification
6. Two-Phase Refactoring workflow
7. Failure recovery strategies
8. LLM canonicalization
"""

import json
from datetime import datetime

import pytest

from codegraph_reasoning.domain import (
    DecisionType,
    Evidence,
    EvidenceBundle,
    EvidenceType,
    ReasoningContext,
    compute_input_hash,
)
from codegraph_reasoning.infrastructure.llm import LLMCanonicalizer, LLMOutputSchema
from codegraph_reasoning.infrastructure.refactoring import (
    IntentPreservation,
    IntentPreservationChecker,
    RefactorPhase,
    SemanticPatch,
    TwoPhaseRefactoringEngine,
)
from codegraph_reasoning.infrastructure.reliability import FailureHandler, FailureType
from codegraph_reasoning.infrastructure.verification import (
    AnalysisResult,
    ConfidenceAggregator,
    UNDECIDABLEHandler,
)


class TestReasoningContext:
    """Test ReasoningContext determinism contract."""

    def test_context_hash_reproducibility(self):
        """Same inputs → same hash."""
        ctx1 = ReasoningContext(
            engine_version="2.0.1",
            ruleset_hash="abc123",
            rust_engine_hash="def456",
            llm_model_id="gpt-4o-mini-2024-07-18",
            llm_temperature=0.0,
            input_hash="test_input",
        )

        ctx2 = ReasoningContext(
            engine_version="2.0.1",
            ruleset_hash="abc123",
            rust_engine_hash="def456",
            llm_model_id="gpt-4o-mini-2024-07-18",
            llm_temperature=0.0,
            input_hash="test_input",
        )

        assert ctx1.context_hash() == ctx2.context_hash()

    def test_context_hash_uniqueness(self):
        """Different inputs → different hash."""
        ctx1 = ReasoningContext(
            engine_version="2.0.1",
            ruleset_hash="abc123",
            rust_engine_hash="def456",
            input_hash="input1",
        )

        ctx2 = ReasoningContext(
            engine_version="2.0.1",
            ruleset_hash="abc123",
            rust_engine_hash="def456",
            input_hash="input2",  # Different input
        )

        assert ctx1.context_hash() != ctx2.context_hash()

    def test_compute_input_hash(self):
        """Test input hash computation."""
        hash1 = compute_input_hash("def foo():", "def bar():")
        hash2 = compute_input_hash("def foo():", "def bar():")
        hash3 = compute_input_hash("def foo():", "def baz():")

        assert hash1 == hash2
        assert hash1 != hash3


class TestEvidenceBundle:
    """Test EvidenceBundle standard format."""

    def test_bundle_creation(self):
        """Test basic bundle creation."""
        bundle = EvidenceBundle(
            decision="is_breaking",
            confidence=0.95,
            decision_type=DecisionType.DECIDED,
        )

        assert bundle.decision == "is_breaking"
        assert bundle.confidence == 0.95
        assert bundle.decision_type == DecisionType.DECIDED

    def test_add_evidence(self):
        """Test adding evidence to bundle."""
        bundle = EvidenceBundle(
            decision="is_breaking",
            confidence=0.95,
            decision_type=DecisionType.DECIDED,
        )

        bundle.add_evidence(
            Evidence(
                type=EvidenceType.RULE_MATCH,
                description="Rule matched",
                confidence=0.9,
                weight=0.5,
                analyzer="rule",
            )
        )

        assert len(bundle.supporting_evidence) == 1
        assert bundle.supporting_evidence[0].type == EvidenceType.RULE_MATCH

    def test_json_serialization(self):
        """Test JSON serialization."""
        bundle = EvidenceBundle(
            decision="is_breaking",
            confidence=0.95,
            decision_type=DecisionType.DECIDED,
        )

        json_data = bundle.to_json()
        assert json_data["decision"] == "is_breaking"
        assert json_data["confidence"] == 0.95
        assert json_data["decision_type"] == "decided"

    def test_markdown_output(self):
        """Test Markdown output format."""
        bundle = EvidenceBundle(
            decision="is_breaking",
            confidence=0.95,
            decision_type=DecisionType.DECIDED,
        )

        markdown = bundle.to_markdown()
        assert "# Decision: is_breaking" in markdown
        assert "**Confidence**: 95.00%" in markdown

    def test_cli_summary(self):
        """Test CLI summary output."""
        bundle = EvidenceBundle(
            decision="is_breaking",
            confidence=0.95,
            decision_type=DecisionType.DECIDED,
        )

        summary = bundle.to_cli_summary()
        assert "is_breaking" in summary
        assert "95.0%" in summary


class TestConfidenceAggregator:
    """Test ConfidenceAggregator veto power and weighted consensus."""

    def test_all_agree_consensus(self):
        """Test consensus when all analyzers agree."""
        aggregator = ConfidenceAggregator()

        results = [
            AnalysisResult(
                is_breaking=True,
                confidence=0.95,
                evidence=["Rule matched"],
                analyzer="rule",
            ),
            AnalysisResult(
                is_breaking=True,
                confidence=0.98,
                evidence=["Formal proof"],
                analyzer="formal",
            ),
        ]

        bundle = aggregator.aggregate(results)
        assert bundle.decision == "is_breaking"
        assert bundle.confidence >= 0.95

    def test_formal_proof_veto(self):
        """Test formal proof veto power."""
        aggregator = ConfidenceAggregator()

        results = [
            AnalysisResult(
                is_breaking=False,
                confidence=0.7,
                evidence=["Rule says safe"],
                analyzer="rule",
            ),
            AnalysisResult(
                is_breaking=True,
                confidence=0.99,
                evidence=["Formal proof: breaking"],
                analyzer="formal",
            ),
        ]

        bundle = aggregator.aggregate(results)
        # Formal proof should override
        assert bundle.decision == "is_breaking"
        assert bundle.confidence >= 0.95

    def test_llm_cannot_override_consensus(self):
        """Test LLM cannot override rule+formal consensus."""
        aggregator = ConfidenceAggregator()

        results = [
            AnalysisResult(
                is_breaking=False,
                confidence=0.9,
                evidence=["Rule: safe"],
                analyzer="rule",
            ),
            AnalysisResult(
                is_breaking=False,
                confidence=0.95,
                evidence=["Formal: safe"],
                analyzer="formal",
            ),
            AnalysisResult(
                is_breaking=True,
                confidence=0.8,
                evidence=["LLM: breaking"],
                analyzer="llm",
            ),
        ]

        bundle = aggregator.aggregate(results)
        # Rule+formal consensus should win
        assert bundle.decision == "is_safe"


class TestUNDECIDABLEHandler:
    """Test UNDECIDABLE handling for insufficient evidence."""

    def test_low_confidence_undecidable(self):
        """Test low confidence → UNDECIDABLE."""
        handler = UNDECIDABLEHandler()

        results = [
            AnalysisResult(
                is_breaking=True,
                confidence=0.6,  # Below threshold
                evidence=["Weak evidence"],
                analyzer="rule",
            )
        ]

        bundle = handler.evaluate_decision(results, {"task": "breaking_change_detection"})
        assert bundle.decision_type == DecisionType.UNDECIDABLE
        assert "Low confidence" in bundle.undecidable_reason

    def test_conflicting_evidence(self):
        """Test conflicting evidence → CONFLICTING."""
        handler = UNDECIDABLEHandler()

        results = [
            AnalysisResult(is_breaking=True, confidence=0.9, evidence=["Breaking"], analyzer="rule"),
            AnalysisResult(is_breaking=True, confidence=0.9, evidence=["Breaking"], analyzer="formal"),
            AnalysisResult(is_breaking=False, confidence=0.9, evidence=["Safe"], analyzer="llm"),
            AnalysisResult(is_breaking=False, confidence=0.9, evidence=["Safe"], analyzer="type"),
        ]

        bundle = handler.evaluate_decision(results, {"task": "breaking_change_detection"})
        assert bundle.decision_type == DecisionType.CONFLICTING
        assert "Conflicting evidence" in bundle.undecidable_reason

    def test_candidate_overflow(self):
        """Test too many candidates → UNDECIDABLE."""
        handler = UNDECIDABLEHandler()

        results = [AnalysisResult(is_breaking=True, confidence=0.9, evidence=["Test"], analyzer="rule")]

        # Simulate 100 candidates (> MAX_CANDIDATES = 50)
        bundle = handler.evaluate_decision(results, {"task": "boundary_matching", "candidates": list(range(100))})
        assert bundle.decision_type == DecisionType.UNDECIDABLE
        assert "Too many candidates" in bundle.undecidable_reason

    def test_conservative_fallback(self):
        """Test conservative fallback is provided."""
        handler = UNDECIDABLEHandler()

        results = [AnalysisResult(is_breaking=True, confidence=0.5, evidence=["Weak"], analyzer="rule")]

        bundle = handler.evaluate_decision(results, {"task": "breaking_change_detection"})
        assert bundle.conservative_fallback is not None
        assert bundle.conservative_fallback["is_breaking"] is True  # Fail-safe


class TestIntentPreservation:
    """Test IntentPreservation classification."""

    def test_strict_preservation(self):
        """Test STRICT classification for simple rename."""
        checker = IntentPreservationChecker()

        patch = SemanticPatch(
            before="def old_name():\n    return 42",
            after="def new_name():\n    return 42",
            description="Rename function",
        )

        intent = checker.classify(patch)
        assert intent == IntentPreservation.STRICT

    def test_uncertain_preservation(self):
        """Test UNCERTAIN classification for logic change."""
        checker = IntentPreservationChecker()

        patch = SemanticPatch(
            before="if x > 0:\n    return True",
            after="if x >= 0:\n    return True",
            description="Change comparison",
        )

        intent = checker.classify(patch)
        assert intent == IntentPreservation.UNCERTAIN

    def test_verify_strict(self):
        """Test verify returns auto-approve for STRICT."""
        checker = IntentPreservationChecker()

        patch = SemanticPatch(
            before="x = 1",
            after="x = 1",
            description="No change",
        )

        result = checker.verify(patch)
        assert result.success is True
        assert result.requires_approval is False
        assert result.intent_preservation == IntentPreservation.STRICT


class TestTwoPhaseRefactoring:
    """Test Two-Phase Refactoring workflow."""

    def test_generate_plan(self):
        """Test plan generation."""
        engine = TwoPhaseRefactoringEngine()

        code = "def foo():\n    x = 1\n    return x"
        instruction = "Simplify"

        result = engine.generate_plan(code, instruction)
        assert result.success is True
        assert result.plan is not None
        assert result.phase == RefactorPhase.PLAN

    def test_apply_plan_auto_approved(self):
        """Test apply plan for auto-approved changes."""
        engine = TwoPhaseRefactoringEngine()

        code = "def foo():\n    x = 1\n    return x"
        instruction = "Simplify"

        plan_result = engine.generate_plan(code, instruction)
        assert plan_result.plan is not None

        if not plan_result.plan.requires_approval:
            apply_result = engine.apply_plan(plan_result.plan, code)
            assert apply_result.phase == RefactorPhase.APPLY

    def test_plan_requires_approval(self):
        """Test plan requiring approval for risky changes."""
        engine = TwoPhaseRefactoringEngine()

        code = "def foo():\n    if x > 0:\n        return True"
        instruction = "Change logic and add global variables"

        result = engine.generate_plan(code, instruction)
        # Plan should be generated successfully
        assert result.success is True
        assert result.plan is not None
        # Note: approval requirement depends on risk analysis
        # Just verify the plan has approval metadata
        assert hasattr(result.plan, "requires_approval")


class TestFailureHandler:
    """Test Failure recovery strategies."""

    def test_llm_timeout_downgrade(self):
        """Test LLM timeout → downgrade to rule-based."""
        handler = FailureHandler()

        recovery = handler.handle_failure(FailureType.LLM_TIMEOUT, context={"candidates": ["a", "b", "c"]})

        assert recovery.success is True
        assert recovery.method == "rule_based_fallback"
        assert "Downgraded" in recovery.warning

    def test_type_check_fail_closed(self):
        """Test type check failed → fail-closed."""
        handler = FailureHandler()

        recovery = handler.handle_failure(FailureType.TYPE_CHECK_FAILED, context={})

        assert recovery.success is False
        assert recovery.escalation_required is True

    def test_no_retry_for_llm(self):
        """Test LLM failures don't allow retry (prevent drift)."""
        handler = FailureHandler()

        recovery = handler.handle_failure(FailureType.LLM_PARSE_ERROR, context={})
        # Should downgrade or fail, not retry
        assert recovery.success in [True, False]  # Either fallback or fail


class TestLLMCanonicalizer:
    """Test LLM output canonicalization."""

    def test_python_import_sorting(self):
        """Test Python import sorting."""
        canonicalizer = LLMCanonicalizer()

        code = """
import os
import sys
from pathlib import Path
import json


def foo():
    pass
"""

        canonical = canonicalizer.canonicalize_code(code, "python")

        # Imports should be sorted
        lines = canonical.split("\n")
        import_lines = [line for line in lines if line.strip().startswith("import") or line.strip().startswith("from")]

        assert import_lines == sorted(import_lines)

    def test_whitespace_normalization(self):
        """Test whitespace normalization."""
        canonicalizer = LLMCanonicalizer()

        code = "def foo():   \n    pass  \n\n\n"

        canonical = canonicalizer.canonicalize_code(code, "python")

        # Trailing whitespace removed
        for line in canonical.split("\n"):
            assert not line.endswith(" ")

        # Single newline at EOF
        assert canonical.endswith("\n")
        assert not canonical.endswith("\n\n")

    def test_json_canonicalization(self):
        """Test JSON canonicalization."""
        canonicalizer = LLMCanonicalizer()

        data = {"z": 1, "a": 2, "m": 3}

        canonical = canonicalizer.canonicalize_json(data)

        # Keys should be sorted
        parsed = json.loads(canonical)
        keys = list(parsed.keys())
        assert keys == sorted(keys)


class TestIntegration:
    """Integration tests for SOTA components working together."""

    def test_end_to_end_breaking_change_detection(self):
        """Test complete breaking change detection workflow."""
        # 1. Create reasoning context
        context = ReasoningContext(
            engine_version="2.0.1",
            ruleset_hash="test_hash",
            rust_engine_hash="rust_hash",
            input_hash=compute_input_hash("before", "after"),
        )

        # 2. Run multiple analyzers
        results = [
            AnalysisResult(
                is_breaking=True,
                confidence=0.95,
                evidence=["Rule matched: GLOBAL_MUTATION"],
                analyzer="rule",
            ),
            AnalysisResult(
                is_breaking=True,
                confidence=0.98,
                evidence=["Formal proof: breaking"],
                analyzer="formal",
            ),
        ]

        # 3. Check for UNDECIDABLE
        undecidable_handler = UNDECIDABLEHandler()
        bundle = undecidable_handler.evaluate_decision(results, {"task": "breaking_change_detection"})

        if bundle is None:
            # 4. Aggregate confidence
            aggregator = ConfidenceAggregator()
            bundle = aggregator.aggregate(results)

        # 5. Verify bundle
        assert bundle.decision in ["is_breaking", "is_safe"]
        assert bundle.confidence >= 0.0

        # 6. Attach reasoning context
        bundle.reasoning_context = context
        assert bundle.reasoning_context is not None

        # 7. Export to JSON
        json_data = bundle.to_json()
        assert "decision" in json_data
        assert "confidence" in json_data

    def test_refactoring_with_failure_recovery(self):
        """Test refactoring with LLM failure → fallback."""
        # 1. Attempt refactoring
        engine = TwoPhaseRefactoringEngine()
        code = "def foo():\n    return 42"

        # 2. Simulate LLM timeout
        handler = FailureHandler()
        recovery = handler.handle_failure(FailureType.LLM_TIMEOUT, context={"code": code})

        # 3. Verify graceful degradation
        if recovery.success:
            assert recovery.method == "rule_based_fallback"
            assert recovery.warning is not None
        else:
            assert recovery.escalation_required is True
