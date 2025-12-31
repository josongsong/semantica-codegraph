"""
Two-Phase Refactoring Engine (RFC-102)

Separates Plan generation from Apply to prevent runaway refactorings.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .intent_preservation import IntentPreservation, IntentPreservationChecker, SemanticPatch


class RefactorPhase(Enum):
    """Refactoring phases."""

    PLAN = "plan"
    APPLY = "apply"


@dataclass
class RefactorPlan:
    """Refactoring plan (Phase 1)."""

    # Summary
    summary: str  # Single-line description
    instruction: str  # Original instruction

    # Scope
    changed_files: list[str] = field(default_factory=list)  # Files to be modified (sorted)
    changed_symbols: list[str] = field(default_factory=list)  # Symbols to be modified (sorted)
    new_symbols: list[str] = field(default_factory=list)  # Symbols to be created (sorted)
    deleted_symbols: list[str] = field(default_factory=list)  # Symbols to be deleted (sorted)

    # Estimates
    estimated_lines_changed: int = 0
    estimated_complexity: str = "simple"  # "simple" | "medium" | "complex"

    # Risk assessment
    risk_flags: list[str] = field(default_factory=list)  # ["breaking", "performance", "style", "logic"]
    breaking_analysis: Optional[dict] = None

    # Approval
    requires_approval: bool = False
    approval_reason: Optional[str] = None


@dataclass
class RefactorPatch:
    """Refactoring patch (Phase 2)."""

    # Plan reference
    plan: RefactorPlan

    # Patches (per file)
    file_patches: dict[str, str] = field(default_factory=dict)  # {file_path: patch_content}

    # Verification results
    syntax_valid: bool = True
    type_valid: bool = True
    effect_preserved: bool = True
    tests_pass: Optional[bool] = None

    # Intent preservation
    intent_preservation: Optional[IntentPreservation] = None

    # Scope enforcement
    scope_violations: list[str] = field(default_factory=list)  # Files/symbols changed outside plan


@dataclass
class RefactorResult:
    """Final refactoring result."""

    success: bool
    phase: RefactorPhase  # PLAN or APPLY
    plan: Optional[RefactorPlan] = None
    patch: Optional[RefactorPatch] = None
    error: Optional[str] = None
    warning: Optional[str] = None


class TwoPhaseRefactoringEngine:
    """
    Two-phase refactoring: Plan → Apply.

    Phase 1: Generate plan (scope, risks, estimates)
    Phase 2: Generate patch (within plan scope)
    """

    def __init__(self):
        self.intent_checker = IntentPreservationChecker()

    def refactor(self, code: str, instruction: str) -> RefactorResult:
        """
        Two-phase refactoring.

        Args:
            code: Original code
            instruction: Refactoring instruction

        Returns:
            RefactorResult (plan or patch)
        """
        # Phase 1: Generate plan
        plan_result = self.generate_plan(code, instruction)
        if not plan_result.success:
            return plan_result

        plan = plan_result.plan

        # Check if approval required
        if plan.requires_approval:
            # Return plan for user approval
            return RefactorResult(
                success=True,
                phase=RefactorPhase.PLAN,
                plan=plan,
                warning=f"Approval required: {plan.approval_reason}",
            )

        # Phase 2: Generate patch (auto-approved)
        patch_result = self.apply_plan(plan, code)
        return patch_result

    def generate_plan(self, code: str, instruction: str) -> RefactorResult:
        """
        Phase 1: Generate refactoring plan.

        Steps:
        1. Analyze code and instruction
        2. Estimate scope & risks
        3. Determine if approval needed

        Args:
            code: Original code
            instruction: Refactoring instruction

        Returns:
            RefactorResult with plan
        """
        # Simple analysis (placeholder - integrate with LLM)
        plan = self._analyze_refactoring_scope(code, instruction)

        # Determine approval requirement
        requires_approval = (
            plan.estimated_lines_changed > 50
            or plan.estimated_complexity == "complex"
            or "breaking" in plan.risk_flags
            or "logic" in plan.risk_flags
        )

        approval_reason = None
        if requires_approval:
            reasons = []
            if plan.estimated_lines_changed > 50:
                reasons.append(f"Large change ({plan.estimated_lines_changed} lines)")
            if "breaking" in plan.risk_flags:
                reasons.append("Breaking change detected")
            if "logic" in plan.risk_flags:
                reasons.append("Logic change (behavior modification)")
            approval_reason = ", ".join(reasons)

        plan.requires_approval = requires_approval
        plan.approval_reason = approval_reason

        return RefactorResult(success=True, phase=RefactorPhase.PLAN, plan=plan)

    def apply_plan(self, plan: RefactorPlan, code: str) -> RefactorResult:
        """
        Phase 2: Apply refactoring plan.

        Steps:
        1. Generate patch (within plan scope)
        2. Verify scope enforcement
        3. Verify safety (type, effect, intent)
        4. Apply patch

        Args:
            plan: Approved refactoring plan
            code: Original code

        Returns:
            RefactorResult with patch
        """
        # Generate patch (placeholder - integrate with LLM)
        patched_code = self._generate_patch(code, plan)

        # Scope enforcement
        scope_violations = self._check_scope_violations(plan, code, patched_code)
        if scope_violations:
            return RefactorResult(
                success=False,
                phase=RefactorPhase.APPLY,
                plan=plan,
                error=f"Scope violations: {', '.join(scope_violations)}",
            )

        # Safety verification
        syntax_valid = self._verify_syntax(patched_code)
        if not syntax_valid:
            return RefactorResult(
                success=False,
                phase=RefactorPhase.APPLY,
                plan=plan,
                error="Syntax validation failed",
            )

        # Intent preservation
        patch_obj = SemanticPatch(before=code, after=patched_code, description=plan.instruction)
        intent_result = self.intent_checker.verify(patch_obj)

        if not intent_result.success:
            return RefactorResult(
                success=False,
                phase=RefactorPhase.APPLY,
                plan=plan,
                error=intent_result.error or "Intent preservation check failed",
            )

        # Success
        patch = RefactorPatch(
            plan=plan,
            file_patches={plan.changed_files[0] if plan.changed_files else "unknown": patched_code},
            syntax_valid=syntax_valid,
            type_valid=intent_result.type_valid,
            effect_preserved=intent_result.effect_preserved,
            tests_pass=intent_result.tests_pass,
            intent_preservation=intent_result.intent_preservation,
            scope_violations=[],
        )

        return RefactorResult(success=True, phase=RefactorPhase.APPLY, plan=plan, patch=patch)

    def _analyze_refactoring_scope(self, code: str, instruction: str) -> RefactorPlan:
        """Analyze refactoring scope (placeholder)."""
        # Simple heuristics (TODO: integrate with LLM)
        lines_changed = len(code.split("\n")) // 4  # Estimate 25% change

        risk_flags = []
        if "class" in instruction.lower() or "async" in instruction.lower():
            risk_flags.append("breaking")
        if "if" in instruction.lower() or "loop" in instruction.lower():
            risk_flags.append("logic")

        complexity = "simple"
        if lines_changed > 100:
            complexity = "complex"
        elif lines_changed > 50:
            complexity = "medium"

        return RefactorPlan(
            summary=instruction[:100],
            instruction=instruction,
            changed_files=["<inferred>"],
            changed_symbols=["<inferred>"],
            estimated_lines_changed=lines_changed,
            estimated_complexity=complexity,
            risk_flags=risk_flags,
        )

    def _generate_patch(self, code: str, plan: RefactorPlan) -> str:
        """Generate patch (placeholder)."""
        # TODO: Integrate with LLM
        # For now, return original code with comment
        return f"# Refactored: {plan.summary}\n{code}"

    def _check_scope_violations(self, plan: RefactorPlan, before: str, after: str) -> list[str]:
        """Check if patch violates plan scope."""
        violations = []

        # Check if lines changed exceeds estimate by >50%
        before_lines = len(before.split("\n"))
        after_lines = len(after.split("\n"))
        actual_changed = abs(after_lines - before_lines)

        if actual_changed > plan.estimated_lines_changed * 1.5:
            violations.append(
                f"Lines changed ({actual_changed}) exceeds estimate ({plan.estimated_lines_changed}) by >50%"
            )

        return violations

    def _verify_syntax(self, code: str) -> bool:
        """Verify syntax validity."""
        try:
            compile(code, "<string>", "exec")
            return True
        except SyntaxError:
            return False
