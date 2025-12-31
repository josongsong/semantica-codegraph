"""
Test suite for LLM Refactoring Engine (RFC-101 Phase 2).

Validates:
1. Domain models (RefactoringContext, LLMPatch, VerificationResult)
2. LLM patch generation with boundary awareness
3. Multi-layer verification (6 layers)
4. End-to-end refactoring workflow
5. Boundary integrity preservation
6. Error handling and edge cases
"""

import pytest

from codegraph_reasoning.domain import (
    BoundaryCandidate,
    BoundaryIntegrityCheck,
    BoundarySpec,
    BoundaryType,
    HTTPMethod,
    LLMGenerationConfig,
    LLMPatch,
    LLMRefactoringResult,
    RefactoringContext,
    RefactoringType,
    VerificationLevel,
    VerificationResult,
)
from codegraph_reasoning.infrastructure.refactoring import (
    LLMPatchGenerator,
    LLMRefactoringEngine,
    MultiLayerVerifier,
)


class TestDomainModels:
    """Test LLM refactoring domain models."""

    def test_refactoring_context_creation(self):
        """Test refactoring context creation."""
        context = RefactoringContext(
            code="def foo(): pass",
            file_path="test.py",
            module_name="test",
            refactoring_type=RefactoringType.EXTRACT_FUNCTION,
            instruction="Extract helper function",
        )

        assert context.code == "def foo(): pass"
        assert context.file_path == "test.py"
        assert context.refactoring_type == RefactoringType.EXTRACT_FUNCTION
        assert context.instruction == "Extract helper function"

    def test_refactoring_context_with_boundary(self):
        """Test refactoring context with boundary information."""
        boundary_spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/users/{id}",
            http_method=HTTPMethod.GET,
        )

        boundary_match = BoundaryCandidate(
            node_id="node_1",
            file_path="api/users.py",
            function_name="get_user",
            line_number=10,
            code_snippet="def get_user(user_id: int):",
            pattern_score=0.95,
        )

        context = RefactoringContext(
            code="def get_user(user_id: int): pass",
            file_path="api/users.py",
            refactoring_type=RefactoringType.REFACTOR_BOUNDARY,
            instruction="Add error handling",
            boundary_spec=boundary_spec,
            boundary_match=boundary_match,
        )

        assert context.boundary_spec is not None
        assert context.boundary_match is not None
        assert context.boundary_spec.endpoint == "/api/users/{id}"

    def test_llm_patch_creation(self):
        """Test LLM patch creation."""
        patch = LLMPatch(
            original_code="def foo(): pass",
            patched_code="def foo():\n    return None",
            description="Add explicit return",
            rationale="Improves clarity",
            confidence=0.9,
        )

        assert patch.original_code == "def foo(): pass"
        assert patch.patched_code == "def foo():\n    return None"
        assert patch.confidence == 0.9

    def test_llm_patch_boundary_awareness(self):
        """Test LLM patch with boundary impact."""
        patch = LLMPatch(
            original_code="def api_endpoint(): pass",
            patched_code="def api_endpoint():\n    return {}",
            description="Add return value",
            boundary_preserved=True,
            boundary_changes=[],
            breaking_change=False,
        )

        assert patch.boundary_preserved is True
        assert len(patch.boundary_changes) == 0
        assert patch.breaking_change is False

    def test_verification_result_creation(self):
        """Test verification result creation."""
        result = VerificationResult(
            success=True,
            syntax_valid=True,
            type_valid=True,
            effect_preserved=True,
            boundary_preserved=True,
        )

        assert result.success is True
        assert len(result.verified_levels) == 0  # Empty initially

    def test_verification_result_post_init(self):
        """Test verification result __post_init__ validation."""
        # Syntax failure should set success=False
        result = VerificationResult(
            success=True,  # Will be overridden
            syntax_valid=False,
            syntax_error="Invalid syntax",
        )

        assert result.success is False  # Overridden by __post_init__

    def test_boundary_integrity_check(self):
        """Test boundary integrity check."""
        boundary_spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        boundary_match = BoundaryCandidate(
            node_id="node_1",
            file_path="test.py",
            function_name="test_handler",
            line_number=10,
            code_snippet="def test_handler():",
        )

        check = BoundaryIntegrityCheck(
            boundary_spec=boundary_spec,
            boundary_match=boundary_match,
        )

        assert check.safe is True  # Default: all checks pass
        assert len(check.breaking_changes) == 0

    def test_boundary_integrity_check_with_violations(self):
        """Test boundary integrity check with violations."""
        boundary_spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        boundary_match = BoundaryCandidate(
            node_id="node_1",
            file_path="test.py",
            function_name="test_handler",
            line_number=10,
            code_snippet="def test_handler():",
        )

        check = BoundaryIntegrityCheck(
            boundary_spec=boundary_spec,
            boundary_match=boundary_match,
            signature_preserved=False,
            breaking_changes=["Function signature changed"],
        )

        assert check.safe is False  # Has breaking changes
        assert len(check.breaking_changes) == 1

    def test_llm_generation_config(self):
        """Test LLM generation configuration."""
        config = LLMGenerationConfig(
            model="gpt-4",
            temperature=0.2,
            max_tokens=4000,
            boundary_aware=True,
        )

        assert config.model == "gpt-4"
        assert config.temperature == 0.2
        assert config.boundary_aware is True

    def test_llm_refactoring_result(self):
        """Test LLM refactoring result."""
        patch = LLMPatch(
            original_code="def foo(): pass",
            patched_code="def foo():\n    return None",
            description="Add return",
        )

        verification = VerificationResult(success=True, syntax_valid=True, type_valid=True)

        result = LLMRefactoringResult(
            success=True,
            phase="complete",
            patch=patch,
            verification=verification,
            auto_approved=True,
        )

        assert result.success is True
        assert result.verified is True
        assert result.safe_to_apply is True


class TestLLMPatchGenerator:
    """Test LLM patch generator."""

    def test_generator_initialization(self):
        """Test patch generator initialization."""
        generator = LLMPatchGenerator()

        assert generator.llm_client is None
        assert generator.config is not None

    def test_generator_initialization_with_config(self):
        """Test patch generator with custom config."""
        config = LLMGenerationConfig(model="gpt-3.5-turbo", temperature=0.5)
        generator = LLMPatchGenerator(config=config)

        assert generator.config.model == "gpt-3.5-turbo"
        assert generator.config.temperature == 0.5

    def test_generate_mock_patch(self):
        """Test mock patch generation (no LLM)."""
        generator = LLMPatchGenerator()

        context = RefactoringContext(
            code="def foo(): pass",
            file_path="test.py",
            refactoring_type=RefactoringType.EXTRACT_FUNCTION,
            instruction="Add docstring",
        )

        patch = generator.generate_patch(context)

        assert patch is not None
        assert patch.original_code == "def foo(): pass"
        assert "Refactored:" in patch.patched_code  # Mock adds comment
        assert patch.confidence > 0

    def test_generate_patch_with_boundary_context(self):
        """Test patch generation with boundary context."""
        generator = LLMPatchGenerator()

        boundary_spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        boundary_match = BoundaryCandidate(
            node_id="node_1",
            file_path="test.py",
            function_name="test_handler",
            line_number=10,
            code_snippet="def test_handler():",
        )

        context = RefactoringContext(
            code="def test_handler(): pass",
            file_path="test.py",
            refactoring_type=RefactoringType.REFACTOR_BOUNDARY,
            instruction="Add error handling",
            boundary_spec=boundary_spec,
            boundary_match=boundary_match,
        )

        patch = generator.generate_patch(context)

        # Boundary impact should be checked
        assert patch.boundary_preserved is not None

    def test_build_prompt_with_boundary(self):
        """Test prompt building with boundary constraints."""
        generator = LLMPatchGenerator()

        boundary_spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.POST,
        )

        boundary_match = BoundaryCandidate(
            node_id="node_1",
            file_path="test.py",
            function_name="test_handler",
            line_number=10,
            code_snippet="def test_handler():",
        )

        context = RefactoringContext(
            code="def test_handler(): pass",
            file_path="test.py",
            refactoring_type=RefactoringType.REFACTOR_BOUNDARY,
            instruction="Add logging",
            boundary_spec=boundary_spec,
            boundary_match=boundary_match,
        )

        prompt = generator._build_prompt(context)

        # Should include boundary warnings
        assert "Boundary Constraints" in prompt or "CRITICAL" in prompt
        assert "MUST preserve" in prompt

    def test_extract_function_signature(self):
        """Test function signature extraction."""
        generator = LLMPatchGenerator()

        code = """
def foo(x: int, y: str) -> bool:
    return True
"""

        sig = generator._extract_function_signature(code, "foo")
        assert "def foo(x: int, y: str) -> bool:" in sig

    def test_extract_http_decorator(self):
        """Test HTTP decorator extraction."""
        generator = LLMPatchGenerator()

        code = """
@app.get('/api/users/{id}')
def get_user(user_id: int):
    pass
"""

        decorator = generator._extract_http_decorator(code)
        assert "@app.get('/api/users/{id}')" in decorator


class TestMultiLayerVerifier:
    """Test multi-layer verification system."""

    def test_verifier_initialization(self):
        """Test verifier initialization."""
        verifier = MultiLayerVerifier()

        assert verifier.rust_engine is None
        assert verifier.type_checker is None
        assert verifier.test_runner is None

    def test_syntax_verification_valid(self):
        """Test syntax verification with valid code."""
        verifier = MultiLayerVerifier()

        result = verifier._verify_syntax("def foo(): pass")

        assert result["valid"] is True
        assert "error" not in result

    def test_syntax_verification_invalid(self):
        """Test syntax verification with invalid code."""
        verifier = MultiLayerVerifier()

        result = verifier._verify_syntax("def foo( invalid syntax")

        assert result["valid"] is False
        assert "error" in result

    def test_verify_basic_level(self):
        """Test verification at BASIC level (syntax + type only)."""
        verifier = MultiLayerVerifier()

        patch = LLMPatch(
            original_code="def foo(): pass",
            patched_code="def foo():\n    return None",
            description="Add return",
        )

        context = RefactoringContext(
            code="def foo(): pass",
            file_path="test.py",
            refactoring_type=RefactoringType.EXTRACT_FUNCTION,
            instruction="Add return",
            verification_level=VerificationLevel.BASIC,
        )

        result = verifier.verify(patch, context)

        assert result.success is True
        assert result.syntax_valid is True
        assert result.type_valid is True
        assert "syntax" in result.verified_levels
        assert "type" in result.verified_levels

    def test_verify_standard_level(self):
        """Test verification at STANDARD level (+ effect preservation)."""
        verifier = MultiLayerVerifier()

        patch = LLMPatch(
            original_code="def foo(): pass",
            patched_code="def foo():\n    return None",
            description="Add return",
        )

        context = RefactoringContext(
            code="def foo(): pass",
            file_path="test.py",
            refactoring_type=RefactoringType.EXTRACT_FUNCTION,
            instruction="Add return",
            verification_level=VerificationLevel.STANDARD,
        )

        result = verifier.verify(patch, context)

        assert result.success is True
        assert "effect" in result.verified_levels

    def test_verify_with_boundary_preservation(self):
        """Test verification with boundary integrity check."""
        verifier = MultiLayerVerifier()

        boundary_spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        boundary_match = BoundaryCandidate(
            node_id="node_1",
            file_path="test.py",
            function_name="test_handler",
            line_number=10,
            code_snippet="def test_handler():",
        )

        # Patch that preserves signature
        patch = LLMPatch(
            original_code="def test_handler(): pass",
            patched_code="def test_handler():\n    return {}",
            description="Add return value",
        )

        context = RefactoringContext(
            code="def test_handler(): pass",
            file_path="test.py",
            refactoring_type=RefactoringType.REFACTOR_BOUNDARY,
            instruction="Add return value",
            boundary_spec=boundary_spec,
            boundary_match=boundary_match,
        )

        result = verifier.verify(patch, context)

        assert result.success is True
        assert result.boundary_preserved is True
        assert "boundary" in result.verified_levels

    def test_verify_boundary_violation(self):
        """Test verification catches boundary violations."""
        verifier = MultiLayerVerifier()

        boundary_spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        boundary_match = BoundaryCandidate(
            node_id="node_1",
            file_path="test.py",
            function_name="test_handler",
            line_number=10,
            code_snippet="def test_handler():",
        )

        # Patch that changes signature (boundary violation)
        patch = LLMPatch(
            original_code="def test_handler(): pass",
            patched_code="def test_handler(new_param: str):\n    return {}",
            description="Add parameter",
        )

        context = RefactoringContext(
            code="def test_handler(): pass",
            file_path="test.py",
            refactoring_type=RefactoringType.REFACTOR_BOUNDARY,
            instruction="Add parameter",
            boundary_spec=boundary_spec,
            boundary_match=boundary_match,
        )

        result = verifier.verify(patch, context)

        assert result.success is False  # Boundary violation is critical
        assert result.boundary_preserved is False
        assert len(result.boundary_violations) > 0


class TestLLMRefactoringEngine:
    """Test end-to-end LLM refactoring engine."""

    def test_engine_initialization(self):
        """Test engine initialization."""
        engine = LLMRefactoringEngine()

        assert engine.boundary_matcher is not None
        assert engine.patch_generator is not None
        assert engine.verifier is not None

    def test_refactor_simple_code(self):
        """Test simple refactoring without boundary."""
        engine = LLMRefactoringEngine()

        code = "def foo(): pass"
        instruction = "Add docstring"

        result = engine.refactor(code, instruction)

        assert result is not None
        assert result.success is True or result.error is not None
        assert result.patch is not None

    def test_refactor_with_boundary_detection(self):
        """Test refactoring with boundary detection."""
        engine = LLMRefactoringEngine()

        code = "@app.get('/api/test')\ndef test_handler(): pass"
        instruction = "Add error handling"

        boundary_spec = BoundarySpec(
            boundary_type=BoundaryType.HTTP_ENDPOINT,
            endpoint="/api/test",
            http_method=HTTPMethod.GET,
        )

        result = engine.refactor(
            code,
            instruction,
            file_path="api/test.py",
            boundary_spec=boundary_spec,
            ir_docs=[{}],  # Mock IR docs
        )

        assert result is not None
        assert result.patch is not None

    def test_infer_refactoring_type(self):
        """Test refactoring type inference from instruction."""
        engine = LLMRefactoringEngine()

        # Extract function
        refactoring_type = engine._infer_refactoring_type("Extract helper function")
        assert refactoring_type == RefactoringType.EXTRACT_FUNCTION

        # Rename
        refactoring_type = engine._infer_refactoring_type("Rename variable to user_id")
        assert refactoring_type == RefactoringType.RENAME_SYMBOL

        # Optimize
        refactoring_type = engine._infer_refactoring_type("Optimize for performance")
        assert refactoring_type == RefactoringType.OPTIMIZE_LOGIC

    def test_auto_approval_conditions(self):
        """Test auto-approval conditions."""
        engine = LLMRefactoringEngine()

        code = "def foo(): pass"
        instruction = "Add explicit return None"

        result = engine.refactor(code, instruction, verification_level=VerificationLevel.BASIC)

        # Should auto-approve if:
        # - All verification passed
        # - High confidence
        # - No boundary concerns
        if result.success and result.verification and result.verification.success:
            # May be auto-approved
            assert result.auto_approved is True or result.requires_approval is True


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_code(self):
        """Test refactoring with empty code."""
        engine = LLMRefactoringEngine()

        result = engine.refactor("", "Add function")

        # Should handle gracefully
        assert result is not None

    def test_invalid_syntax_code(self):
        """Test refactoring with invalid syntax."""
        verifier = MultiLayerVerifier()

        patch = LLMPatch(
            original_code="def foo() pass",  # Invalid syntax
            patched_code="def foo(): pass",
            description="Fix syntax",
        )

        context = RefactoringContext(
            code="def foo() pass",
            file_path="test.py",
            refactoring_type=RefactoringType.OPTIMIZE_LOGIC,
            instruction="Fix syntax",
        )

        # Verification should catch the issue in patched code being checked
        result = verifier.verify(patch, context)
        # Original code has invalid syntax, but we're verifying the patch
        assert result.syntax_valid is True  # Patched code is valid

    def test_very_long_code(self):
        """Test refactoring with very long code."""
        generator = LLMPatchGenerator()

        long_code = "def foo():\n" + "    pass\n" * 10000  # 10K lines

        context = RefactoringContext(
            code=long_code,
            file_path="test.py",
            refactoring_type=RefactoringType.EXTRACT_FUNCTION,
            instruction="Extract helper",
        )

        # Should handle without crashing
        patch = generator.generate_patch(context)
        assert patch is not None

    def test_unicode_in_code(self):
        """Test refactoring with unicode characters."""
        generator = LLMPatchGenerator()

        code = "def 사용자_핸들러(): pass"  # Korean function name

        context = RefactoringContext(
            code=code,
            file_path="test.py",
            refactoring_type=RefactoringType.RENAME_SYMBOL,
            instruction="Add docstring",
        )

        patch = generator.generate_patch(context)
        assert patch is not None

    def test_multiple_http_decorators(self):
        """Test code with multiple HTTP decorators."""
        generator = LLMPatchGenerator()

        code = """
@app.get('/api/users')
def get_users(): pass

@app.post('/api/users')
def create_user(): pass
"""

        context = RefactoringContext(
            code=code,
            file_path="api/users.py",
            refactoring_type=RefactoringType.REFACTOR_BOUNDARY,
            instruction="Add error handling",
        )

        patch = generator.generate_patch(context)
        assert patch is not None

    def test_nested_function_signatures(self):
        """Test extraction of nested function signatures."""
        generator = LLMPatchGenerator()

        code = """
def outer():
    def inner(x: int) -> str:
        return str(x)
    return inner
"""

        sig = generator._extract_function_signature(code, "inner")
        assert "def inner(x: int) -> str:" in sig

    def test_multiline_function_signature(self):
        """Test extraction of multi-line function signatures."""
        generator = LLMPatchGenerator()

        code = """
def complex_function(
    param1: int,
    param2: str,
    param3: bool
) -> dict:
    return {}
"""

        sig = generator._extract_function_signature(code, "complex_function")
        assert "def complex_function" in sig
        assert "-> dict:" in sig

    def test_verification_without_boundary_context(self):
        """Test verification without boundary context (should skip boundary layer)."""
        verifier = MultiLayerVerifier()

        patch = LLMPatch(
            original_code="def foo(): pass",
            patched_code="def foo():\n    return None",
            description="Add return",
        )

        context = RefactoringContext(
            code="def foo(): pass",
            file_path="test.py",
            refactoring_type=RefactoringType.EXTRACT_FUNCTION,
            instruction="Add return",
            # No boundary_spec or boundary_match
        )

        result = verifier.verify(patch, context)

        # Boundary layer should be skipped
        assert "boundary" not in result.verified_levels
        assert result.boundary_preserved is True  # Default

    def test_verification_time_tracking(self):
        """Test that verification tracks time."""
        verifier = MultiLayerVerifier()

        patch = LLMPatch(
            original_code="def foo(): pass",
            patched_code="def foo():\n    return None",
            description="Add return",
        )

        context = RefactoringContext(
            code="def foo(): pass",
            file_path="test.py",
            refactoring_type=RefactoringType.EXTRACT_FUNCTION,
            instruction="Add return",
        )

        result = verifier.verify(patch, context)

        # Should have timing information
        assert result.verification_time_ms > 0
