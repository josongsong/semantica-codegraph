"""
Reproduction-First Strategy Adapter (SOTA 구현)
버그 재현 스크립트 생성 및 검증
"""

import logging
import re
from pathlib import Path

from codegraph_agent.ports.cascade import (
    IReproductionEngine,
    ReproductionResult,
    ReproductionScript,
    ReproductionStatus,
)
from codegraph_shared.ports import ILLMProvider

logger = logging.getLogger(__name__)


class ReproductionEngineAdapter(IReproductionEngine):
    """Reproduction-First Strategy 구현체"""

    # 테스트 프레임워크별 템플릿
    TEMPLATES = {
        "pytest": """
import pytest

# Bug Reproduction Test
# Issue: {issue_description}

def test_reproduce_bug():
    \"\"\"
    This test SHOULD FAIL before the fix.
    Expected failure pattern: {expected_failure}
    \"\"\"
    {test_body}
""",
        "jest": """
// Bug Reproduction Test
// Issue: {issue_description}

test('reproduce bug', () => {{
    // This test SHOULD FAIL before the fix
    // Expected failure pattern: {expected_failure}
    {test_body}
}});
""",
        "unittest": """
import unittest

class BugReproductionTest(unittest.TestCase):
    \"\"\"
    Bug Reproduction Test
    Issue: {issue_description}
    \"\"\"

    def test_reproduce_bug(self):
        \"\"\"
        This test SHOULD FAIL before the fix.
        Expected failure pattern: {expected_failure}
        \"\"\"
        {test_body}

if __name__ == '__main__':
    unittest.main()
""",
    }

    def __init__(
        self,
        llm: ILLMProvider,
        command_executor,  # ICommandExecutor
        filesystem,  # IFileSystem
        default_timeout: float = 30.0,
    ):
        self.llm = llm
        self.command_executor = command_executor
        self.filesystem = filesystem
        self.default_timeout = default_timeout

    async def generate_reproduction_script(
        self, issue_description: str, context_files: list[str], tech_stack: dict[str, str]
    ) -> ReproductionScript:
        """버그 재현 스크립트 생성"""

        # 1. 테스트 프레임워크 감지
        test_framework = tech_stack.get("test_framework", "pytest")

        # 2. LLM으로 테스트 코드 생성
        test_body = await self._generate_test_body(issue_description, context_files, test_framework)

        # 3. 예상 실패 패턴 추출
        failure_pattern = self._extract_failure_pattern(issue_description)

        # 4. 템플릿 적용
        template = self.TEMPLATES.get(test_framework, self.TEMPLATES["pytest"])
        script_content = template.format(
            issue_description=issue_description, expected_failure=failure_pattern, test_body=test_body
        )

        # 5. 임시 파일로 저장
        script_path = await self._save_temp_script(script_content, test_framework)

        logger.info(f"Generated reproduction script: {script_path}")

        return ReproductionScript(
            script_path=script_path,
            content=script_content,
            issue_description=issue_description,
            expected_failure_pattern=failure_pattern,
        )

    async def verify_failure(self, script: ReproductionScript) -> ReproductionResult:
        """스크립트 실행 및 실패 확인"""

        logger.info(f"Verifying failure: {script.script_path}")

        # 스크립트 실행
        result = await self._execute_script(script)

        # 실패 확인
        if result.exit_code == 0:
            # 예상과 다르게 성공 (버그가 이미 수정됨?)
            logger.warning("Script passed unexpectedly - bug may be already fixed")
            return ReproductionResult(
                status=ReproductionStatus.PASS_UNEXPECTED,
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time_ms=result.execution_time_ms,
            )

        # 실패 패턴 매칭
        if self._matches_expected_failure(script, result):
            logger.info("Bug successfully reproduced")
            return ReproductionResult(
                status=ReproductionStatus.FAIL_CONFIRMED,
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time_ms=result.execution_time_ms,
            )
        else:
            logger.error("Unexpected failure pattern")
            return ReproductionResult(
                status=ReproductionStatus.ERROR,
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time_ms=result.execution_time_ms,
            )

    async def verify_fix(self, script: ReproductionScript, after_changes: bool = True) -> ReproductionResult:
        """수정 후 스크립트 성공 확인"""

        logger.info(f"Verifying fix: {script.script_path}")

        # 스크립트 실행
        result = await self._execute_script(script)

        # 성공 확인
        if result.exit_code == 0:
            logger.info("Fix verified - test now passes")
            return ReproductionResult(
                status=ReproductionStatus.PASS_UNEXPECTED,  # 수정 후니까 PASS가 정상
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time_ms=result.execution_time_ms,
            )
        else:
            logger.error("Fix failed - test still fails")
            return ReproductionResult(
                status=ReproductionStatus.FAIL_CONFIRMED,  # 수정 후에도 실패
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time_ms=result.execution_time_ms,
            )

    # ========================================================================
    # Private Methods
    # ========================================================================

    async def _generate_test_body(self, issue_description: str, context_files: list[str], test_framework: str) -> str:
        """LLM으로 테스트 본문 생성"""

        # 컨텍스트 파일 읽기
        context_content = ""
        for file_path in context_files[:3]:  # 최대 3개 파일
            try:
                content = Path(file_path).read_text()
                context_content += f"\n# File: {file_path}\n{content[:500]}\n"
            except Exception as e:
                logger.warning(f"Failed to read context file {file_path}: {e}")

        # LLM 프롬프트
        prompt = f"""
Generate a {test_framework} test that reproduces this bug:

Issue: {issue_description}

Context:
{context_content}

Requirements:
1. The test MUST fail before the bug is fixed
2. Keep it minimal and focused on the bug
3. Include assertions that demonstrate the failure
4. Only return the test function body (no import, no decorator)

Test body:
"""

        response = await self.llm.complete(prompt=prompt, task_type="generate", temperature=0.3)

        # 코드 블록 추출
        test_body = self._extract_code_block(response)

        return test_body

    def _extract_failure_pattern(self, issue_description: str) -> str:
        """이슈 설명에서 예상 실패 패턴 추출"""

        # 일반적인 에러 패턴
        patterns = [
            r"(AttributeError:.*)",
            r"(TypeError:.*)",
            r"(ValueError:.*)",
            r"(KeyError:.*)",
            r"(IndexError:.*)",
            r"(AssertionError:.*)",
            r"(NullPointerException)",
            r"(undefined is not a function)",
        ]

        for pattern in patterns:
            match = re.search(pattern, issue_description, re.IGNORECASE)
            if match:
                return match.group(1)

        # 기본 패턴
        return "Error|Exception|Failed|Assertion"

    async def _save_temp_script(self, content: str, test_framework: str) -> str:
        """
        임시 스크립트 파일 저장

        Hexagonal: IFileSystem Port 사용
        """

        # 확장자 결정
        ext_map = {
            "pytest": "py",
            "unittest": "py",
            "jest": "js",
            "mocha": "js",
        }
        ext = ext_map.get(test_framework, "py")

        # 임시 파일 생성 (IFileSystem)
        path = await self.filesystem.create_temp_file(suffix=f"_reproduction.{ext}", prefix="test_", content=content)

        return path

    async def _execute_script(self, script: ReproductionScript) -> ReproductionResult:
        """
        스크립트 실행

        Hexagonal: ICommandExecutor Port 사용
        """

        # 테스트 프레임워크 감지
        if script.script_path.endswith(".py"):
            command = ["pytest", script.script_path, "-v"]
        elif script.script_path.endswith(".js"):
            command = ["npm", "test", script.script_path]
        else:
            raise ValueError(f"Unknown script type: {script.script_path}")

        # ICommandExecutor로 실행
        result = await self.command_executor.execute(command=command, timeout=self.default_timeout, capture_output=True)

        return ReproductionResult(
            status=ReproductionStatus.FAIL_CONFIRMED,  # 임시, 나중에 판단
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            execution_time_ms=result.execution_time_ms,
        )

    def _matches_expected_failure(self, script: ReproductionScript, result: ReproductionResult) -> bool:
        """실행 결과가 예상 실패 패턴과 매칭되는지 확인"""

        output = result.stdout + result.stderr
        pattern = script.expected_failure_pattern

        return bool(re.search(pattern, output, re.IGNORECASE))

    def _extract_code_block(self, text: str) -> str:
        """마크다운 코드 블록 추출"""

        # ```python ... ``` 형식
        match = re.search(r"```(?:python|javascript)?\n(.*?)\n```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 그냥 전체 반환
        return text.strip()
