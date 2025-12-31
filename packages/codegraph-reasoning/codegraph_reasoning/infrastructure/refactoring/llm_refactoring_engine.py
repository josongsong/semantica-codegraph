"""
LLM Refactoring Engine (RFC-101 Phase 2)

Integrates:
- Boundary Matcher (Phase 1)
- LLM Patch Generator
- Multi-Layer Verifier
- Two-Phase Refactoring (RFC-102)
"""

import time
from typing import Any, Optional

from ...domain.boundary_models import BoundarySpec
from ...domain.llm_refactoring_models import (
    LLMGenerationConfig,
    LLMRefactoringResult,
    RefactoringContext,
    RefactoringType,
    VerificationLevel,
)
from ..boundary.sota_matcher import SOTABoundaryMatcher
from .llm_patch_generator import LLMPatchGenerator
from .multi_layer_verifier import MultiLayerVerifier


class LLMRefactoringEngine:
    """
    LLM-guided refactoring engine with boundary awareness.

    Workflow:
    1. Detect boundaries (using SOTA Boundary Matcher)
    2. Generate patch (LLM with boundary constraints)
    3. Verify patch (multi-layer verification)
    4. Apply patch (if verified)

    Performance targets:
    - Accuracy: 95%+ (safe refactorings)
    - Latency: < 5s (LLM + verification)
    - Safety: 100% (no broken boundaries)
    """

    def __init__(
        self,
        boundary_matcher: Optional[SOTABoundaryMatcher] = None,
        patch_generator: Optional[LLMPatchGenerator] = None,
        verifier: Optional[MultiLayerVerifier] = None,
        config: Optional[LLMGenerationConfig] = None,
    ):
        """
        Initialize LLM refactoring engine.

        Args:
            boundary_matcher: SOTA Boundary Matcher (Phase 1)
            patch_generator: LLM patch generator
            verifier: Multi-layer verifier
            config: Generation configuration
        """
        self.boundary_matcher = boundary_matcher or SOTABoundaryMatcher()
        self.patch_generator = patch_generator or LLMPatchGenerator(config=config)
        self.verifier = verifier or MultiLayerVerifier()
        self.config = config or LLMGenerationConfig()

    def refactor(
        self,
        code: str,
        instruction: str,
        file_path: str = "unknown.py",
        module_name: str = "",
        boundary_spec: Optional[BoundarySpec] = None,
        ir_docs: Optional[list[Any]] = None,
        verification_level: VerificationLevel = VerificationLevel.STANDARD,
    ) -> LLMRefactoringResult:
        """
        Perform LLM-guided refactoring with boundary awareness.

        Args:
            code: Original code
            instruction: Refactoring instruction
            file_path: File path
            module_name: Python module name
            boundary_spec: Optional boundary specification (auto-detect if None)
            ir_docs: IR documents for boundary detection
            verification_level: Verification rigor level

        Returns:
            LLMRefactoringResult
        """
        result = LLMRefactoringResult(success=False, phase="detect")
        start_time = time.time()

        # Phase 1: Detect boundaries (if boundary_spec provided or auto-detect)
        boundary_match = None
        if boundary_spec and ir_docs:
            match_result = self.boundary_matcher.match_boundary(boundary_spec, ir_docs)
            if match_result.success:
                boundary_match = match_result.best_match
                result.phase = "detect_success"
            else:
                result.warning = f"Boundary detection failed: {match_result}"

        # Phase 2: Generate patch with LLM
        result.phase = "generate"
        llm_start = time.time()

        context = RefactoringContext(
            code=code,
            file_path=file_path,
            module_name=module_name,
            refactoring_type=self._infer_refactoring_type(instruction),
            instruction=instruction,
            boundary_spec=boundary_spec,
            boundary_match=boundary_match,
            verification_level=verification_level,
        )

        try:
            patch = self.patch_generator.generate_patch(context)
            result.patch = patch
            result.llm_time_ms = (time.time() - llm_start) * 1000
            result.phase = "generate_success"

        except Exception as e:
            result.error = f"LLM generation failed: {e}"
            result.total_time_ms = (time.time() - start_time) * 1000
            return result

        # Check if LLM detected breaking boundary change
        if patch.breaking_change and not self.config.allow_breaking:
            result.success = False
            result.error = "Refactoring would break boundary (LLM detected)"
            result.requires_approval = True
            result.approval_reason = f"Breaking changes: {', '.join(patch.boundary_changes)}"
            result.total_time_ms = (time.time() - start_time) * 1000
            return result

        # Phase 3: Verify patch (multi-layer)
        result.phase = "verify"
        verify_start = time.time()

        verification = self.verifier.verify(patch, context)
        result.verification = verification
        result.verification_time_ms = (time.time() - verify_start) * 1000

        if not verification.success:
            result.success = False
            result.phase = "verify_failed"

            # Determine if approval can override
            if not verification.syntax_valid or not verification.type_valid:
                # Critical failures: cannot approve
                result.error = "Critical verification failure (syntax/type)"
                result.requires_approval = False  # Cannot be overridden
            elif not verification.boundary_preserved:
                # Boundary violations: require approval
                result.error = "Boundary integrity violated"
                result.requires_approval = True
                result.approval_reason = f"Boundary violations: {', '.join(verification.boundary_violations)}"
            else:
                # Other failures: may require approval
                result.requires_approval = True
                result.approval_reason = "Verification concerns (see details)"

            result.total_time_ms = (time.time() - start_time) * 1000
            return result

        # Phase 4: Approval decision
        result.phase = "approve"

        # Auto-approve if:
        # - All verification layers passed
        # - No boundary violations
        # - High LLM confidence (>= 0.8)
        # - Strict intent preservation
        auto_approve_conditions = [
            verification.success,
            verification.boundary_preserved,
            patch.confidence >= 0.8,
            verification.intent_classification in ["strict", "weak", None],  # None means not checked
        ]

        if all(auto_approve_conditions):
            result.auto_approved = True
            result.requires_approval = False
        else:
            # Require human approval
            result.requires_approval = True
            reasons = []
            if patch.confidence < 0.8:
                reasons.append(f"Low LLM confidence ({patch.confidence:.2%})")
            if verification.intent_classification == "uncertain":
                reasons.append("Uncertain intent preservation")
            if not verification.boundary_preserved:
                reasons.append("Boundary concerns")

            result.approval_reason = ", ".join(reasons) if reasons else "Manual review recommended"

        # Success!
        result.success = True
        result.phase = "complete"
        result.total_time_ms = (time.time() - start_time) * 1000

        return result

    def refactor_with_alternatives(
        self,
        code: str,
        instruction: str,
        file_path: str = "unknown.py",
        module_name: str = "",
        boundary_spec: Optional[BoundarySpec] = None,
        ir_docs: Optional[list[Any]] = None,
        num_alternatives: int = 3,
        verification_level: VerificationLevel = VerificationLevel.STANDARD,
    ) -> list[LLMRefactoringResult]:
        """
        Generate multiple refactoring alternatives.

        Args:
            code: Original code
            instruction: Refactoring instruction
            file_path: File path
            module_name: Module name
            boundary_spec: Boundary specification
            ir_docs: IR documents
            num_alternatives: Number of alternatives to generate
            verification_level: Verification level

        Returns:
            List of LLMRefactoringResult (sorted by confidence + verification)
        """
        # Detect boundary once
        boundary_match = None
        if boundary_spec and ir_docs:
            match_result = self.boundary_matcher.match_boundary(boundary_spec, ir_docs)
            if match_result.success:
                boundary_match = match_result.best_match

        # Create context
        context = RefactoringContext(
            code=code,
            file_path=file_path,
            module_name=module_name,
            refactoring_type=self._infer_refactoring_type(instruction),
            instruction=instruction,
            boundary_spec=boundary_spec,
            boundary_match=boundary_match,
            verification_level=verification_level,
        )

        # Generate alternatives
        alternatives = self.patch_generator.generate_alternatives(context, num_alternatives)

        # Verify each alternative
        results = []
        for i, patch in enumerate(alternatives):
            verification = self.verifier.verify(patch, context)

            result = LLMRefactoringResult(
                success=verification.success,
                phase="complete",
                patch=patch,
                verification=verification,
                auto_approved=verification.success and verification.boundary_preserved and patch.confidence >= 0.8,
            )

            # Compute score: confidence * verification success
            score = patch.confidence * (1.0 if verification.success else 0.5)
            results.append((score, result))

        # Sort by score (descending)
        results.sort(key=lambda x: x[0], reverse=True)

        return [r[1] for r in results]

    def _infer_refactoring_type(self, instruction: str) -> RefactoringType:
        """
        Infer refactoring type from instruction.

        Args:
            instruction: Natural language instruction

        Returns:
            RefactoringType
        """
        instruction_lower = instruction.lower()

        if "extract" in instruction_lower and "function" in instruction_lower:
            return RefactoringType.EXTRACT_FUNCTION
        elif "rename" in instruction_lower:
            return RefactoringType.RENAME_SYMBOL
        elif "move" in instruction_lower:
            return RefactoringType.MOVE_CODE
        elif "split" in instruction_lower:
            return RefactoringType.SPLIT_FUNCTION
        elif "merge" in instruction_lower:
            return RefactoringType.MERGE_FUNCTIONS
        elif "optimize" in instruction_lower or "refactor" in instruction_lower:
            return RefactoringType.OPTIMIZE_LOGIC
        elif "error" in instruction_lower or "exception" in instruction_lower:
            return RefactoringType.ADD_ERROR_HANDLING
        elif "boundary" in instruction_lower or "endpoint" in instruction_lower:
            return RefactoringType.REFACTOR_BOUNDARY
        else:
            return RefactoringType.OPTIMIZE_LOGIC  # Default
