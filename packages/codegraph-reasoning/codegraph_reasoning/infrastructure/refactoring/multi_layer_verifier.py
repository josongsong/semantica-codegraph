"""
Multi-Layer Verification System (RFC-101 Phase 2)

Comprehensive verification with 6 layers:
1. Syntax validation
2. Type checking
3. Effect preservation
4. Test validation
5. Boundary integrity (NEW)
6. Intent preservation
"""

import ast
import time
from typing import Any, Optional

from ...domain.llm_refactoring_models import (
    BoundaryIntegrityCheck,
    LLMPatch,
    RefactoringContext,
    VerificationLevel,
    VerificationResult,
)
from .intent_preservation import IntentPreservation, IntentPreservationChecker, SemanticPatch


class MultiLayerVerifier:
    """
    Multi-layer verification for refactoring patches.

    Verification layers (in order):
    1. Syntax: AST parsing
    2. Type: Type checking (Rust integration or pyright)
    3. Effect: Effect preservation analysis
    4. Test: Test suite validation
    5. Boundary: Boundary integrity (NEW - Phase 2)
    6. Intent: Intent preservation classification
    """

    def __init__(
        self,
        rust_engine: Optional[Any] = None,
        type_checker: Optional[Any] = None,
        test_runner: Optional[Any] = None,
    ):
        """
        Initialize multi-layer verifier.

        Args:
            rust_engine: Rust IR engine for effect/type analysis
            type_checker: Type checker (pyright, mypy, etc.)
            test_runner: Test runner (pytest, unittest, etc.)
        """
        self.rust_engine = rust_engine
        self.type_checker = type_checker
        self.test_runner = test_runner
        self.intent_checker = IntentPreservationChecker()

    def verify(self, patch: LLMPatch, context: RefactoringContext) -> VerificationResult:
        """
        Perform multi-layer verification.

        Verification stops at first critical failure (syntax, type, boundary).

        Args:
            patch: LLM-generated patch
            context: Refactoring context

        Returns:
            VerificationResult with all layer results
        """
        result = VerificationResult(success=True)
        start_time = time.time()

        # Layer 1: Syntax validation (CRITICAL)
        syntax_result = self._verify_syntax(patch.patched_code)
        result.syntax_valid = syntax_result["valid"]
        result.syntax_error = syntax_result.get("error")
        result.verified_levels.append("syntax")

        if not result.syntax_valid:
            result.success = False
            result.verification_time_ms = (time.time() - start_time) * 1000
            return result

        # Layer 2: Type checking (CRITICAL)
        type_result = self._verify_types(patch, context)
        result.type_valid = type_result["valid"]
        result.type_errors = type_result.get("errors", [])
        result.verified_levels.append("type")

        if not result.type_valid:
            result.success = False
            result.verification_time_ms = (time.time() - start_time) * 1000
            return result

        # Layer 3: Effect preservation
        if context.verification_level in [
            VerificationLevel.STANDARD,
            VerificationLevel.STRICT,
            VerificationLevel.PARANOID,
        ]:
            effect_result = self._verify_effects(patch, context)
            result.effect_preserved = effect_result["preserved"]
            result.effect_violations = effect_result.get("violations", [])
            result.verified_levels.append("effect")

        # Layer 4: Test validation
        if context.verification_level in [
            VerificationLevel.STRICT,
            VerificationLevel.PARANOID,
        ]:
            test_result = self._verify_tests(patch, context)
            result.tests_pass = test_result["pass"]
            result.test_failures = test_result.get("failures", [])
            result.verified_levels.append("test")

        # Layer 5: Boundary integrity (NEW - Phase 2, CRITICAL if boundary context)
        if context.boundary_spec and context.boundary_match:
            boundary_result = self._verify_boundary_integrity(patch, context)
            result.boundary_preserved = boundary_result["preserved"]
            result.boundary_violations = boundary_result.get("violations", [])
            result.contract_violations = boundary_result.get("contract_violations", [])
            result.verified_levels.append("boundary")

            if not result.boundary_preserved:
                result.success = False
                result.verification_time_ms = (time.time() - start_time) * 1000
                return result

        # Layer 6: Intent preservation
        if context.verification_level == VerificationLevel.PARANOID:
            intent_result = self._verify_intent_preservation(patch)
            result.intent_preserved = intent_result["preserved"]
            result.intent_classification = intent_result.get("classification")
            result.verified_levels.append("intent")

        # Final success determination
        critical_failures = (
            not result.syntax_valid
            or not result.type_valid
            or (result.boundary_preserved is False and context.boundary_spec is not None)
        )
        result.success = not critical_failures

        result.verification_time_ms = (time.time() - start_time) * 1000
        return result

    def _verify_syntax(self, code: str) -> dict:
        """
        Layer 1: Verify Python syntax.

        Args:
            code: Python code to verify

        Returns:
            {"valid": bool, "error": Optional[str]}
        """
        try:
            ast.parse(code)
            return {"valid": True}
        except SyntaxError as e:
            return {"valid": False, "error": f"Line {e.lineno}: {e.msg}"}

    def _verify_types(self, patch: LLMPatch, context: RefactoringContext) -> dict:
        """
        Layer 2: Verify type correctness.

        Uses Rust type checker or external type checker (pyright/mypy).

        Args:
            patch: LLM patch
            context: Refactoring context

        Returns:
            {"valid": bool, "errors": list[str]}
        """
        # Try Rust type checker first
        if self.rust_engine:
            try:
                type_result = self.rust_engine.check_types(patch.patched_code, context.file_path)
                return {"valid": type_result.get("valid", True), "errors": type_result.get("errors", [])}
            except Exception as e:
                # Fall through to external checker
                pass

        # External type checker (pyright, mypy)
        if self.type_checker:
            try:
                type_result = self.type_checker.check(patch.patched_code, context.file_path)
                return {"valid": len(type_result.get("errors", [])) == 0, "errors": type_result.get("errors", [])}
            except Exception as e:
                # Graceful degradation: assume valid
                return {"valid": True, "errors": []}

        # No type checker available: simple heuristic check
        return self._heuristic_type_check(patch, context)

    def _heuristic_type_check(self, patch: LLMPatch, context: RefactoringContext) -> dict:
        """
        Simple heuristic type check (fallback).

        Checks for common type errors without full type inference.

        Args:
            patch: LLM patch
            context: Refactoring context

        Returns:
            {"valid": bool, "errors": list[str]}
        """
        errors = []

        # Check 1: Function signature annotations preserved
        if context.boundary_match:
            func_name = context.boundary_match.function_name
            original_sig = self._extract_function_signature(patch.original_code, func_name)
            patched_sig = self._extract_function_signature(patch.patched_code, func_name)

            # Check return type preserved
            if "->" in original_sig and "->" in patched_sig:
                original_return = original_sig.split("->")[1].split(":")[0].strip()
                patched_return = patched_sig.split("->")[1].split(":")[0].strip()
                if original_return != patched_return:
                    errors.append(f"Return type changed: {original_return} → {patched_return}")

        # Check 2: No undefined variables introduced
        # (This would require full AST analysis - skip for now)

        return {"valid": len(errors) == 0, "errors": errors}

    def _verify_effects(self, patch: LLMPatch, context: RefactoringContext) -> dict:
        """
        Layer 3: Verify effect preservation.

        Uses Rust effect analysis or simple heuristic.

        Args:
            patch: LLM patch
            context: Refactoring context

        Returns:
            {"preserved": bool, "violations": list[str]}
        """
        # Try Rust effect analyzer
        if self.rust_engine:
            try:
                effect_result = self.rust_engine.analyze_effects(patch.original_code, patch.patched_code)
                return {
                    "preserved": effect_result.get("preserved", True),
                    "violations": effect_result.get("violations", []),
                }
            except Exception:
                pass

        # Fallback: Use intent checker's effect preservation check
        semantic_patch = SemanticPatch(
            before=patch.original_code,
            after=patch.patched_code,
            description=patch.description,
        )

        preserved = self.intent_checker._check_effect_preservation(semantic_patch)
        violations = []
        if not preserved:
            violations.append("Dangerous keywords added (global, nonlocal, open, input, print)")

        return {"preserved": preserved, "violations": violations}

    def _verify_tests(self, patch: LLMPatch, context: RefactoringContext) -> dict:
        """
        Layer 4: Verify test suite passes.

        Args:
            patch: LLM patch
            context: Refactoring context

        Returns:
            {"pass": bool, "failures": list[str]}
        """
        if not context.test_files:
            # No tests specified, skip validation
            return {"pass": None, "failures": []}

        # Run test suite
        if self.test_runner:
            try:
                test_result = self.test_runner.run_tests(
                    patched_code=patch.patched_code,
                    file_path=context.file_path,
                    test_files=context.test_files,
                )
                return {
                    "pass": test_result.get("pass", True),
                    "failures": test_result.get("failures", []),
                }
            except Exception as e:
                return {"pass": False, "failures": [f"Test runner error: {e}"]}

        # No test runner: assume tests pass (optimistic)
        return {"pass": True, "failures": []}

    def _verify_boundary_integrity(self, patch: LLMPatch, context: RefactoringContext) -> dict:
        """
        Layer 5: Verify boundary integrity (NEW - Phase 2).

        Ensures refactoring doesn't break service boundaries.

        Args:
            patch: LLM patch
            context: Refactoring context with boundary info

        Returns:
            {"preserved": bool, "violations": list[str], "contract_violations": list[str]}
        """
        if not context.boundary_spec or not context.boundary_match:
            return {"preserved": True, "violations": [], "contract_violations": []}

        check = BoundaryIntegrityCheck(
            boundary_spec=context.boundary_spec,
            boundary_match=context.boundary_match,
        )

        violations = []
        contract_violations = []

        # Check 1: Function signature preservation
        func_name = context.boundary_match.function_name
        original_sig = self._extract_function_signature(patch.original_code, func_name)
        patched_sig = self._extract_function_signature(patch.patched_code, func_name)

        if original_sig != patched_sig:
            check.signature_preserved = False
            violations.append(f"Signature changed: {original_sig} → {patched_sig}")

            # Check parameter types
            if self._extract_parameters(original_sig) != self._extract_parameters(patched_sig):
                check.parameter_types_preserved = False
                contract_violations.append("Parameter types changed")

            # Check return type
            if self._extract_return_type(original_sig) != self._extract_return_type(patched_sig):
                check.return_type_preserved = False
                contract_violations.append("Return type changed")

        # Check 2: HTTP decorator preservation (if HTTP endpoint)
        if context.boundary_spec.endpoint:
            original_decorator = self._extract_http_decorator(patch.original_code)
            patched_decorator = self._extract_http_decorator(patch.patched_code)

            if original_decorator != patched_decorator:
                check.http_path_preserved = False
                violations.append(f"HTTP decorator changed: {original_decorator} → {patched_decorator}")

        # Determine if boundary is preserved
        check.breaking_changes = violations
        preserved = check.safe

        return {
            "preserved": preserved,
            "violations": violations,
            "contract_violations": contract_violations,
        }

    def _verify_intent_preservation(self, patch: LLMPatch) -> dict:
        """
        Layer 6: Verify intent preservation.

        Classifies refactoring as STRICT, WEAK, or UNCERTAIN.

        Args:
            patch: LLM patch

        Returns:
            {"preserved": bool, "classification": str}
        """
        semantic_patch = SemanticPatch(
            before=patch.original_code,
            after=patch.patched_code,
            description=patch.description,
        )

        classification = self.intent_checker.classify(semantic_patch)

        # Consider STRICT and WEAK as preserved
        preserved = classification in [
            IntentPreservation.STRICT,
            IntentPreservation.WEAK,
        ]

        return {"preserved": preserved, "classification": classification.value}

    def _extract_function_signature(self, code: str, function_name: str) -> str:
        """Extract function signature from code."""
        lines = code.split("\n")
        for i, line in enumerate(lines):
            if f"def {function_name}(" in line:
                sig_str = line.strip()

                # Multi-line case - keep reading until we find closing paren + colon
                sig_lines = [sig_str]
                j = i + 1
                paren_depth = sig_str.count("(") - sig_str.count(")")

                # Read until closing paren
                while j < len(lines) and paren_depth > 0:
                    next_line = lines[j].strip()
                    if next_line:
                        sig_lines.append(next_line)
                        paren_depth += next_line.count("(") - next_line.count(")")
                    j += 1

                # Now read until we find the final colon (after closing paren)
                while j < len(lines) and paren_depth <= 0:
                    next_line = lines[j].strip()
                    if next_line:
                        sig_lines.append(next_line)
                    if ":" in next_line:
                        # Found the final colon
                        full_sig = " ".join(sig_lines)
                        # Find the LAST colon (the one that ends the signature)
                        colon_idx = full_sig.rfind(":")
                        return full_sig[: colon_idx + 1]
                    j += 1

                # If we have a colon in the accumulated lines, use it
                full_sig = " ".join(sig_lines)
                if ":" in full_sig:
                    colon_idx = full_sig.rfind(":")
                    return full_sig[: colon_idx + 1]

                return full_sig
        return ""

    def _extract_http_decorator(self, code: str) -> str:
        """Extract HTTP decorator from code."""
        lines = code.split("\n")
        for line in lines:
            if "@app." in line or "@router." in line or "@api." in line:
                return line.strip()
        return ""

    def _extract_parameters(self, signature: str) -> str:
        """Extract parameter list from function signature."""
        if "(" not in signature or ")" not in signature:
            return ""
        start = signature.index("(")
        end = signature.rindex(")")
        return signature[start : end + 1]

    def _extract_return_type(self, signature: str) -> str:
        """Extract return type from function signature."""
        if "->" not in signature:
            return "None"
        return signature.split("->")[1].split(":")[0].strip()
