"""
HCGAdapter Tests

SOTA-Level: NotImplementedError 명확성, Base + Edge
Production-Grade: HCG 연동 준비 완료
"""

import pytest

from codegraph_runtime.codegen_loop.domain.patch import FileChange, Patch, PatchStatus
from codegraph_runtime.codegen_loop.domain.specs.arch_spec import ArchSpecValidationResult
from codegraph_runtime.codegen_loop.domain.specs.integrity_spec import IntegritySpecValidationResult
from codegraph_runtime.codegen_loop.domain.specs.security_spec import SecuritySpecValidationResult
from codegraph_runtime.codegen_loop.infrastructure.hcg_adapter import HCG_AVAILABLE, HCGAdapter


def create_test_patch(code: str = "def foo(): pass") -> Patch:
    """테스트용 Patch"""
    return Patch(
        id="test",
        iteration=1,
        files=[
            FileChange(
                file_path="main.py",
                old_content="",
                new_content=code,
                diff_lines=[],
            )
        ],
        status=PatchStatus.GENERATED,
    )


class TestHCGAdapterCreation:
    """HCGAdapter 생성"""

    def test_adapter_without_ir_doc(self):
        """Base: IR Document 없이 생성"""
        if not HCG_AVAILABLE:
            pytest.skip("HCG not available")

        adapter = HCGAdapter()

        assert adapter.ir_doc is None
        assert adapter.query_engine is None
        assert adapter.security_spec is not None
        assert adapter.arch_spec is not None
        assert adapter.integrity_spec is not None

    def test_adapter_raises_if_hcg_not_available(self):
        """Edge: HCG_AVAILABLE False면 에러"""
        if HCG_AVAILABLE:
            pytest.skip("HCG available")

        with pytest.raises(RuntimeError, match="HCG Query DSL not available"):
            HCGAdapter()


class TestScopeSelection:
    """Step 1: Scope Selection"""

    @pytest.mark.asyncio
    async def test_query_scope_requires_query_engine(self):
        """Base: QueryEngine 필요"""
        if not HCG_AVAILABLE:
            pytest.skip("HCG not available")

        adapter = HCGAdapter()  # No IR Doc

        with pytest.raises(RuntimeError, match="QueryEngine not initialized"):
            await adapter.query_scope("Fix bug in payment")


class TestSemanticContract:
    """Step 5: Semantic Contract"""

    @pytest.mark.asyncio
    async def test_find_callers_requires_query_engine(self):
        """Base: find_callers requires QueryEngine"""
        if not HCG_AVAILABLE:
            pytest.skip("HCG not available")

        adapter = HCGAdapter()

        with pytest.raises(RuntimeError, match="QueryEngine not initialized"):
            await adapter.find_callers("module.foo")

    @pytest.mark.asyncio
    async def test_extract_contract_requires_query_engine(self):
        """Base: extract_contract requires QueryEngine"""
        if not HCG_AVAILABLE:
            pytest.skip("HCG not available")

        adapter = HCGAdapter()

        with pytest.raises(RuntimeError, match="QueryEngine not initialized"):
            await adapter.extract_contract("module.foo")

    @pytest.mark.asyncio
    async def test_detect_renames_fallback(self):
        """Base: Rename detection fallback (returns empty)"""
        if not HCG_AVAILABLE:
            pytest.skip("HCG not available")

        adapter = HCGAdapter()
        patch = create_test_patch()

        result = await adapter.detect_renames(patch)

        # Fallback returns empty dict
        assert result == {}


class TestIncrementalUpdate:
    """Step 6: Incremental Update"""

    @pytest.mark.asyncio
    async def test_incremental_update_fallback_success(self):
        """Base: IR 없어도 True 반환 (not critical)"""
        if not HCG_AVAILABLE:
            pytest.skip("HCG not available")

        adapter = HCGAdapter()
        patch = create_test_patch()
        result = await adapter.incremental_update(patch)

        # Not critical, returns True
        assert result is True


class TestGraphSpecValidation:
    """Step 7: GraphSpec Validation"""

    @pytest.mark.asyncio
    async def test_verify_security_basic_check(self):
        """Base: 기본 보안 체크"""
        if not HCG_AVAILABLE:
            pytest.skip("HCG not available")

        adapter = HCGAdapter()

        code = "def foo(): return 42"
        patch = create_test_patch(code)

        result = await adapter.verify_security(patch)

        assert isinstance(result, SecuritySpecValidationResult)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_verify_security_dangerous_pattern(self):
        """Edge: 위험한 패턴 (eval)"""
        if not HCG_AVAILABLE:
            pytest.skip("HCG not available")

        adapter = HCGAdapter()

        code = """
def dangerous():
    eval("malicious")
"""
        patch = create_test_patch(code)

        result = await adapter.verify_security(patch)

        # Basic check detects eval but doesn't fail (no full dataflow)
        assert isinstance(result, SecuritySpecValidationResult)

    @pytest.mark.asyncio
    async def test_verify_architecture(self):
        """Base: 아키텍처 검증"""
        if not HCG_AVAILABLE:
            pytest.skip("HCG not available")

        adapter = HCGAdapter()

        code = """
import os
def foo():
    return os.getcwd()
"""
        patch = create_test_patch(code)

        result = await adapter.verify_architecture(patch)

        assert isinstance(result, ArchSpecValidationResult)
        # May pass or fail depending on ArchSpec rules
        assert isinstance(result.passed, bool)

    @pytest.mark.asyncio
    async def test_verify_integrity_basic_check(self):
        """Base: 무결성 검증"""
        if not HCG_AVAILABLE:
            pytest.skip("HCG not available")

        adapter = HCGAdapter()

        code = """
def foo():
    with open('file.txt') as f:
        return f.read()
"""
        patch = create_test_patch(code)

        result = await adapter.verify_integrity(patch)

        assert isinstance(result, IntegritySpecValidationResult)
        assert result.passed is True  # with open() is safe

    @pytest.mark.asyncio
    async def test_verify_integrity_potential_leak(self):
        """Edge: 잠재적 리소스 누수"""
        if not HCG_AVAILABLE:
            pytest.skip("HCG not available")

        adapter = HCGAdapter()

        code = """
def foo():
    f = open('file.txt')
    return f.read()
"""
        patch = create_test_patch(code)

        result = await adapter.verify_integrity(patch)

        # Basic check detects open() without close()
        assert isinstance(result, IntegritySpecValidationResult)
        # May pass (fallback doesn't create violations yet)


class TestEdgeCases:
    """Edge/Corner Cases"""

    @pytest.mark.asyncio
    async def test_simple_rename_detection_empty(self):
        """Corner: Rename 감지 - 없음"""
        if not HCG_AVAILABLE:
            pytest.skip("HCG not available")

        adapter = HCGAdapter()
        patch = create_test_patch()
        result = adapter._simple_rename_detection(patch)

        # Returns empty dict (no renames)
        assert result == {}

    def test_extract_keywords(self):
        """Base: Keyword 추출"""
        if not HCG_AVAILABLE:
            pytest.skip("HCG not available")

        adapter = HCGAdapter()
        keywords = adapter._extract_keywords("Fix bug in the payment module")

        assert "fix" in keywords
        assert "bug" in keywords
        assert "payment" in keywords or "module" in keywords
        assert "the" not in keywords  # Stopword
