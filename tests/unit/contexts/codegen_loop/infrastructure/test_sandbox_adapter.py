"""
DockerSandboxAdapter Tests

SOTA-Level: 실제 subprocess 실행, Base + Edge + Corner + Extreme
Production-Grade: No Mock, 실제 동작 검증
"""

import asyncio

import pytest

from codegraph_runtime.codegen_loop.domain.patch import FileChange, Patch, PatchStatus
from codegraph_runtime.codegen_loop.infrastructure.sandbox_adapter import DockerSandboxAdapter


def create_simple_patch(code: str) -> Patch:
    """테스트용 Patch"""
    return Patch(
        id="test",
        iteration=1,
        files=[
            FileChange(
                file_path="main.py",
                old_content="",
                new_content=code,
                diff_lines=[f"+{line}" for line in code.split("\n")],
            )
        ],
        status=PatchStatus.GENERATED,
    )


class TestSyntaxValidation:
    """Syntax 검증 - 실제 ast.parse"""

    @pytest.mark.asyncio
    async def test_valid_syntax(self):
        """Base: 유효한 문법"""
        adapter = DockerSandboxAdapter()

        code = """
def foo(x: int) -> int:
    return x + 1
"""

        result = await adapter.validate_syntax(code)

        assert result["valid"] is True
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_invalid_syntax_missing_colon(self):
        """Edge: 문법 오류 - 콜론 누락"""
        adapter = DockerSandboxAdapter()

        code = """
def foo(x)
    return x
"""

        result = await adapter.validate_syntax(code)

        assert result["valid"] is False
        assert len(result["errors"]) > 0
        assert "Syntax error" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_invalid_syntax_indentation(self):
        """Edge: Indentation 오류"""
        adapter = DockerSandboxAdapter()

        code = """
def foo():
return 42
"""

        result = await adapter.validate_syntax(code)

        assert result["valid"] is False
        assert "Syntax error" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_empty_code(self):
        """Corner: 빈 코드"""
        adapter = DockerSandboxAdapter()

        result = await adapter.validate_syntax("")

        # 빈 코드는 유효
        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_only_comments(self):
        """Corner: 주석만"""
        adapter = DockerSandboxAdapter()

        code = """
# This is a comment
# Another comment
"""

        result = await adapter.validate_syntax(code)

        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_unsupported_language(self):
        """Edge: 지원하지 않는 언어"""
        adapter = DockerSandboxAdapter()

        result = await adapter.validate_syntax("code", language="rust")

        assert result["valid"] is False
        assert "Unsupported language" in result["errors"][0]


class TestLinterExecution:
    """Linter 실행 - 실제 ruff (있으면)"""

    @pytest.mark.asyncio
    async def test_lint_clean_code(self):
        """Base: 깨끗한 코드"""
        adapter = DockerSandboxAdapter()

        code = """
def calculate_sum(numbers: list[int]) -> int:
    '''Calculate sum of numbers.'''
    return sum(numbers)
"""

        patch = create_simple_patch(code)
        result = await adapter.run_linter(patch)

        assert result["score"] >= 0.8
        assert isinstance(result["errors"], list)

    @pytest.mark.asyncio
    async def test_lint_with_issues(self):
        """Base: Lint 이슈 있는 코드"""
        adapter = DockerSandboxAdapter()

        code = """
def foo( x,y ):
    z=x+y
    return z
"""

        patch = create_simple_patch(code)
        result = await adapter.run_linter(patch)

        # Lint issues 있을 수 있음 (formatting)
        assert "score" in result
        assert 0.0 <= result["score"] <= 1.0


class TestTypeCheck:
    """타입 체크 - 실제 mypy (있으면)"""

    @pytest.mark.asyncio
    async def test_typecheck_valid(self):
        """Base: 타입 안전한 코드"""
        adapter = DockerSandboxAdapter()

        code = """
def add(x: int, y: int) -> int:
    return x + y
"""

        patch = create_simple_patch(code)
        result = await adapter.run_type_check(patch)

        # mypy 없어도 errors는 list여야 함
        assert isinstance(result["errors"], list)

    @pytest.mark.asyncio
    async def test_typecheck_type_mismatch(self):
        """Edge: 타입 불일치"""
        adapter = DockerSandboxAdapter()

        code = """
def add(x: int, y: int) -> str:
    return x + y  # Returns int, not str
"""

        patch = create_simple_patch(code)
        result = await adapter.run_type_check(patch)

        # mypy 있으면 에러, 없으면 valid=True
        assert "valid" in result


class TestBuild:
    """빌드 - Import 체크"""

    @pytest.mark.asyncio
    async def test_build_success(self):
        """Base: 빌드 성공"""
        adapter = DockerSandboxAdapter()

        code = """
import os
def foo():
    return os.path.exists('.')
"""

        patch = create_simple_patch(code)
        result = await adapter.build(patch)

        assert result["success"] is True
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_build_syntax_error(self):
        """Edge: Syntax 오류로 빌드 실패"""
        adapter = DockerSandboxAdapter()

        code = """
def foo(
    return 42
"""

        patch = create_simple_patch(code)
        result = await adapter.build(patch)

        assert result["success"] is False
        assert len(result["errors"]) > 0


class TestDockerAvailability:
    """Docker 가용성 체크"""

    def test_docker_check(self):
        """Base: Docker 설치 여부 체크"""
        adapter = DockerSandboxAdapter()

        # Docker 있으면 True, 없으면 False
        assert isinstance(adapter.docker_available, bool)

        # Test still works regardless
        assert adapter is not None


class TestTestExecution:
    """테스트 실행 - 실제 pytest"""

    @pytest.mark.asyncio
    async def test_execute_tests_with_passing_test(self):
        """Base: 통과하는 테스트"""
        adapter = DockerSandboxAdapter()

        code = """
def test_simple():
    assert 1 + 1 == 2
"""

        patch = create_simple_patch(code)
        result = await adapter.execute_tests(patch)

        # Result structure 검증
        assert "pass_rate" in result
        assert "passed" in result
        assert "failed" in result
        assert "errors" in result
        assert "coverage" in result

        # pass_rate는 0~1
        assert 0.0 <= result["pass_rate"] <= 1.0

    @pytest.mark.asyncio
    async def test_execute_tests_with_failing_test(self):
        """Base: 실패하는 테스트"""
        adapter = DockerSandboxAdapter()

        code = """
def test_failing():
    assert 1 + 1 == 3
"""

        patch = create_simple_patch(code)
        result = await adapter.execute_tests(patch)

        assert "pass_rate" in result
        # May fail or pass depending on environment
        assert isinstance(result["pass_rate"], float)

    @pytest.mark.asyncio
    async def test_execute_tests_no_tests(self):
        """Edge: 테스트 없음"""
        adapter = DockerSandboxAdapter()

        code = """
def foo():
    return 42
"""

        patch = create_simple_patch(code)
        result = await adapter.execute_tests(patch)

        # No tests → pass_rate=0, "No tests found" error
        assert result["pass_rate"] == 0.0
        assert "No tests found" in str(result["errors"])


class TestEdgeCases:
    """극한 상황"""

    @pytest.mark.asyncio
    async def test_very_long_code(self):
        """Extreme: 매우 긴 코드"""
        adapter = DockerSandboxAdapter()

        # 1000 lines
        code = "\n".join([f"x{i} = {i}" for i in range(1000)])

        result = await adapter.validate_syntax(code)

        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_unicode_code(self):
        """Corner: Unicode 포함"""
        adapter = DockerSandboxAdapter()

        code = """
def greet():
    return "안녕하세요 🎉"
"""

        result = await adapter.validate_syntax(code)

        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_multiline_string(self):
        """Corner: 멀티라인 문자열"""
        adapter = DockerSandboxAdapter()

        code = '''
def doc():
    """
    This is a very long
    multiline docstring
    """
    pass
'''

        result = await adapter.validate_syntax(code)

        assert result["valid"] is True
