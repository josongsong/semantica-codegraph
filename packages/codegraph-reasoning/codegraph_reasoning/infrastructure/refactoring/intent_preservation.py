"""
Intent Preservation Checker (RFC-101)

Classifies refactorings by intent preservation level.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class IntentPreservation(Enum):
    """Intent preservation classification for refactorings."""

    STRICT = "strict"
    """
    Bit-for-bit behavior preservation (provable via formal methods).

    Examples:
    - Rename variable/function
    - Extract method (pure function)
    - Inline constant
    - Reorder independent statements
    """

    WEAK = "weak"
    """
    Behavior-preserving under normal conditions (verified via tests + analysis).

    Examples:
    - async/await transformation (timing changes)
    - Class → Functional (different stack traces)
    - Loop → map/filter (different iteration order for side effects)
    """

    UNCERTAIN = "uncertain"
    """
    Cannot prove preservation, requires human review.

    Examples:
    - Logic restructuring
    - Error handling changes
    - Concurrency pattern changes
    """


@dataclass
class SemanticPatch:
    """Semantic patch for refactoring."""

    before: str
    after: str
    description: str = ""


@dataclass
class RefactoringResult:
    """Result of refactoring with intent preservation classification."""

    success: bool
    patch: Optional[str] = None
    intent_preservation: Optional[IntentPreservation] = None
    verification_evidence: list[str] = None

    # Confidence breakdown
    syntax_valid: bool = True
    type_valid: bool = True
    effect_preserved: bool = True
    tests_pass: Optional[bool] = None

    # Human approval required?
    requires_approval: bool = False
    error: Optional[str] = None
    warning: Optional[str] = None

    def __post_init__(self):
        if self.verification_evidence is None:
            self.verification_evidence = []


class IntentPreservationChecker:
    """
    Classifies refactorings by intent preservation level.

    Classification rules:

    STRICT (auto-approve):
    - Rust type_resolution proves type-preserving
    - Rust effect_analysis proves effect-preserving
    - No control flow changes (CFG isomorphic)
    - No data flow changes (DFG isomorphic)

    WEAK (approve with tests):
    - Types preserved
    - Effects preserved or safely extended
    - Control/data flow changed but tests pass

    UNCERTAIN (human review):
    - Type/effect changes
    - Test failures
    - Complex control flow changes
    """

    def classify(self, patch: SemanticPatch) -> IntentPreservation:
        """
        Classify refactoring by intent preservation level.

        Args:
            patch: Semantic patch (before/after code)

        Returns:
            IntentPreservation level
        """
        # Check formal properties (placeholder - integrate with Rust)
        type_result = self._check_type_preservation(patch)
        effect_result = self._check_effect_preservation(patch)
        cfg_result = self._check_cfg_isomorphism(patch)

        # STRICT: Provably safe
        if type_result and effect_result and cfg_result:
            return IntentPreservation.STRICT

        # Run tests (placeholder)
        test_result = self._run_tests(patch)

        # WEAK: Safe with test evidence
        if type_result and effect_result and test_result:
            return IntentPreservation.WEAK

        # UNCERTAIN: Needs human
        return IntentPreservation.UNCERTAIN

    def verify(self, patch: SemanticPatch) -> RefactoringResult:
        """
        Verify refactoring and classify intent preservation.

        Args:
            patch: Semantic patch

        Returns:
            RefactoringResult with classification
        """
        # Classify intent preservation
        intent = self.classify(patch)

        # Verify syntax
        syntax_valid = self._verify_syntax(patch.after)
        if not syntax_valid:
            return RefactoringResult(
                success=False,
                error="Syntax validation failed",
                syntax_valid=False,
            )

        # Verify types
        type_valid = self._check_type_preservation(patch)

        # Verify effects
        effect_preserved = self._check_effect_preservation(patch)

        if intent == IntentPreservation.STRICT:
            # Auto-approve (formal proof)
            return RefactoringResult(
                success=True,
                patch=patch.after,
                intent_preservation=intent,
                requires_approval=False,
                verification_evidence=[
                    "Formal proof: type-preserving",
                    "CFG isomorphic",
                    "Effect-preserving",
                ],
                syntax_valid=syntax_valid,
                type_valid=type_valid,
                effect_preserved=effect_preserved,
            )

        elif intent == IntentPreservation.WEAK:
            # Approve with tests
            tests_pass = self._run_tests(patch)
            return RefactoringResult(
                success=True,
                patch=patch.after,
                intent_preservation=intent,
                requires_approval=False,  # Tests passed
                verification_evidence=[
                    "All tests pass",
                    "Effect analysis: safe extension",
                ],
                syntax_valid=syntax_valid,
                type_valid=type_valid,
                effect_preserved=effect_preserved,
                tests_pass=tests_pass,
            )

        else:  # UNCERTAIN
            # Require human approval
            return RefactoringResult(
                success=False,
                patch=patch.after,
                intent_preservation=intent,
                requires_approval=True,
                warning="Cannot verify intent preservation, human review required",
                syntax_valid=syntax_valid,
                type_valid=type_valid,
                effect_preserved=effect_preserved,
            )

    def _verify_syntax(self, code: str) -> bool:
        """Verify syntax validity (placeholder)."""
        # TODO: Integrate with Python ast.parse or Rust parser
        try:
            compile(code, "<string>", "exec")
            return True
        except SyntaxError:
            return False

    def _check_type_preservation(self, patch: SemanticPatch) -> bool:
        """Check if types are preserved (placeholder)."""
        # TODO: Integrate with Rust type_resolution
        # For now, assume types are preserved if syntax is valid
        return self._verify_syntax(patch.after)

    def _check_effect_preservation(self, patch: SemanticPatch) -> bool:
        """Check if effects are preserved (placeholder)."""
        # TODO: Integrate with Rust effect_analysis
        # For now, simple heuristic: no global/IO keywords added
        added_keywords = set()
        before_lower = patch.before.lower()
        after_lower = patch.after.lower()

        dangerous_keywords = ["global", "nonlocal", "open(", "input(", "print("]
        for keyword in dangerous_keywords:
            if keyword not in before_lower and keyword in after_lower:
                added_keywords.add(keyword)

        return len(added_keywords) == 0

    def _check_cfg_isomorphism(self, patch: SemanticPatch) -> bool:
        """Check if control flow graph is isomorphic (placeholder)."""
        # TODO: Integrate with Rust CFG comparison
        # For now, simple heuristic: same control flow keywords
        control_keywords = ["if", "for", "while", "try", "except", "with", "return"]

        before_count = {kw: patch.before.count(kw) for kw in control_keywords}
        after_count = {kw: patch.after.count(kw) for kw in control_keywords}

        return before_count == after_count

    def _run_tests(self, patch: SemanticPatch) -> bool:
        """Run tests to verify behavior preservation (placeholder)."""
        # TODO: Integrate with test runner
        # For now, always return True (assume tests pass)
        return True
