"""Code Validator

생성된 코드 검증 (ADR-017)

검증 레벨:
1. Syntax (파싱 가능?)
2. Imports (모든 import 유효?)
3. Type hints (타입 체크)
4. Lint (코딩 스타일)
5. Tests (기존 테스트 통과?) - Optional
"""

import ast
import asyncio
import sys
from pathlib import Path

from src.common.observability import get_logger
from src.execution.code_generation.models import CodeChange

from .models import ValidationResult

logger = get_logger(__name__)


class CodeValidator:
    """
    코드 검증

    Multi-level validation:
    - Level 1: Syntax (필수)
    - Level 2: Imports (필수)
    - Level 3: Type hints (선택)
    - Level 4: Lint (선택)
    - Level 5: Tests (선택)
    """

    def __init__(self, enable_type_check: bool = False, enable_lint: bool = False, enable_tests: bool = False):
        """
        Initialize CodeValidator

        Args:
            enable_type_check: mypy 타입 체크 활성화
            enable_lint: ruff lint 활성화
            enable_tests: pytest 실행 활성화
        """
        self.enable_type_check = enable_type_check
        self.enable_lint = enable_lint
        self.enable_tests = enable_tests

        logger.info(
            f"CodeValidator initialized: type_check={enable_type_check}, lint={enable_lint}, tests={enable_tests}"
        )

    async def validate(self, code_change: CodeChange, workspace: Path | None = None) -> ValidationResult:
        """
        종합 검증

        Args:
            code_change: 생성된 코드
            workspace: 작업 디렉토리 (optional)

        Returns:
            ValidationResult
        """
        result = ValidationResult(is_valid=True)

        logger.info(f"Validating {code_change.file_path}...")

        # Level 1: Syntax (필수)
        if not self._validate_syntax(code_change.content, result):
            logger.error(f"Syntax validation failed: {code_change.file_path}")
            return result  # Syntax 실패 시 즉시 종료

        # Level 2: Imports (필수)
        self._validate_imports(code_change.content, result)

        # Level 3: Type check (선택)
        if self.enable_type_check and workspace:
            await self._validate_types(code_change, workspace, result)

        # Level 4: Lint (선택)
        if self.enable_lint:
            await self._validate_lint(code_change, result)

        # Level 5: Tests (선택)
        if self.enable_tests and workspace:
            await self._run_tests(workspace, result)

        logger.info(f"Validation complete: {result}")
        return result

    def _validate_syntax(self, code: str, result: ValidationResult) -> bool:
        """
        Syntax 검증

        Args:
            code: 코드
            result: 결과 객체

        Returns:
            성공 여부
        """
        try:
            ast.parse(code)
            logger.debug("Syntax validation: OK")
            result.metadata["syntax"] = "valid"
            return True

        except SyntaxError as e:
            error_msg = f"Syntax error at line {e.lineno}: {e.msg}"
            result.add_error(error_msg)
            result.metadata["syntax"] = "invalid"
            logger.error(error_msg)
            return False

    def _validate_imports(self, code: str, result: ValidationResult):
        """
        Import 검증

        Args:
            code: 코드
            result: 결과 객체
        """
        try:
            tree = ast.parse(code)
            imports = []

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)

            # 표준 라이브러리 + 설치된 패키지 확인 (간단 버전)
            invalid_imports = []
            for imp in imports:
                if not self._import_exists(imp):
                    invalid_imports.append(imp)

            if invalid_imports:
                warning = f"Potentially missing imports: {', '.join(invalid_imports)}"
                result.add_warning(warning)
                logger.warning(warning)

            result.metadata["imports"] = {"total": len(imports), "invalid": len(invalid_imports), "list": imports}

            logger.debug(f"Import validation: {len(imports)} imports, {len(invalid_imports)} warnings")

        except Exception as e:
            logger.warning(f"Import validation error: {e}")

    def _import_exists(self, module_name: str) -> bool:
        """
        Import 존재 확인

        Args:
            module_name: 모듈 이름

        Returns:
            존재 여부
        """
        # 표준 라이브러리 체크
        if module_name in sys.stdlib_module_names:
            return True

        # 설치된 패키지 체크
        try:
            __import__(module_name)
            return True
        except ImportError:
            return False

    async def _validate_types(self, code_change: CodeChange, workspace: Path, result: ValidationResult):
        """
        Type 검증 (mypy)

        Args:
            code_change: 코드 변경
            workspace: 작업 디렉토리
            result: 결과 객체
        """
        try:
            # 임시 파일에 코드 작성
            temp_file = workspace / ".temp_validate.py"
            temp_file.write_text(code_change.content)

            # mypy 실행
            proc = await asyncio.create_subprocess_exec(
                "mypy",
                "--ignore-missing-imports",
                str(temp_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            # 정리
            temp_file.unlink()

            if proc.returncode != 0:
                error_msg = f"Type check failed: {stdout.decode()}"
                result.add_warning(error_msg)
                logger.warning(error_msg)

            result.metadata["type_check"] = "completed"
            logger.debug("Type validation: completed")

        except FileNotFoundError:
            result.add_warning("mypy not found, skipping type check")
        except Exception as e:
            logger.warning(f"Type validation error: {e}")

    async def _validate_lint(self, code_change: CodeChange, result: ValidationResult):
        """
        Lint 검증 (ruff)

        Args:
            code_change: 코드 변경
            result: 결과 객체
        """
        try:
            # ruff를 stdin으로 실행
            proc = await asyncio.create_subprocess_exec(
                "ruff",
                "check",
                "--stdin-filename",
                code_change.file_path,
                "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate(input=code_change.content.encode())

            if proc.returncode != 0:
                warning_msg = f"Lint issues: {stdout.decode()}"
                result.add_warning(warning_msg)
                logger.warning(warning_msg)

            result.metadata["lint"] = "completed"
            logger.debug("Lint validation: completed")

        except FileNotFoundError:
            result.add_warning("ruff not found, skipping lint check")
        except Exception as e:
            logger.warning(f"Lint validation error: {e}")

    async def _run_tests(self, workspace: Path, result: ValidationResult):
        """
        테스트 실행 (pytest)

        Args:
            workspace: 작업 디렉토리
            result: 결과 객체
        """
        try:
            # pytest 실행
            proc = await asyncio.create_subprocess_exec(
                "pytest",
                str(workspace),
                "--tb=short",
                "-q",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = f"Tests failed: {stdout.decode()}"
                result.add_error(error_msg)
                logger.error(error_msg)

            result.metadata["tests"] = "completed"
            logger.debug("Test validation: completed")

        except FileNotFoundError:
            result.add_warning("pytest not found, skipping tests")
        except Exception as e:
            logger.warning(f"Test validation error: {e}")

    def validate_sync(self, code: str) -> ValidationResult:
        """
        동기 검증 (Syntax + Imports만)

        Args:
            code: 코드

        Returns:
            ValidationResult
        """
        result = ValidationResult(is_valid=True)

        self._validate_syntax(code, result)
        if result.is_valid:
            self._validate_imports(code, result)

        return result
