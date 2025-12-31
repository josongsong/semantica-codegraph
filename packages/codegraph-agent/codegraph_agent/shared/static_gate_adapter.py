"""
Static Analysis Gate Adapter

RFC-060 Section 2.2: Ruff + Pyright + Self-Correct Pipeline

Pipeline:
1. Ruff (Linter) - 빠른 문법/스타일 검사 (~0.05초)
2. Pyright (Type Checker) - 타입 오류 검출 (~0.1초)
3. LLM Self-Correct - 자동 수정 (실패 시)
"""

import json
import logging
import tempfile
from pathlib import Path
from typing import Protocol

from codegraph_agent.ports.infrastructure import IInfraCommandExecutor
from codegraph_agent.ports.static_gate import (
    AnalysisIssue,
    AnalysisLevel,
    IStaticAnalysisGate,
    IssueSeverity,
    StaticAnalysisResult,
)

logger = logging.getLogger(__name__)


class ISelfCorrector(Protocol):
    """LLM Self-Correct Port"""

    async def correct(
        self,
        code: str,
        errors: list[AnalysisIssue],
    ) -> str:
        """
        오류를 수정한 코드 반환

        Args:
            code: 원본 코드
            errors: 발견된 오류들

        Returns:
            수정된 코드
        """
        ...


class StaticAnalysisGateAdapter(IStaticAnalysisGate):
    """
    Static Analysis Gate Adapter

    책임:
    - Ruff로 빠른 린트 + 자동 수정
    - Pyright로 타입 검사
    - 실패 시 LLM Self-Correct

    Dependency Injection:
    - executor: 명령 실행
    - self_corrector: LLM 자동 수정 (Optional)
    """

    def __init__(
        self,
        executor: IInfraCommandExecutor,
        self_corrector: ISelfCorrector | None = None,
    ):
        self._executor = executor
        self._corrector = self_corrector

    async def validate(
        self,
        file_path: str,
        content: str,
        level: AnalysisLevel = AnalysisLevel.FULL,
    ) -> StaticAnalysisResult:
        """정적 분석 실행"""
        issues: list[AnalysisIssue] = []
        ruff_passed = True
        pyright_passed = True

        # Syntax check (always)
        if not self._check_syntax(content):
            issues.append(
                AnalysisIssue(
                    file_path=file_path,
                    line=1,
                    column=0,
                    message="Syntax error",
                    code="E999",
                    severity=IssueSeverity.ERROR,
                    source="syntax",
                )
            )
            return StaticAnalysisResult(
                passed=False,
                issues=issues,
                ruff_passed=False,
                pyright_passed=False,
            )

        if level == AnalysisLevel.SYNTAX:
            return StaticAnalysisResult(passed=True, issues=[])

        # Ruff
        if level in (AnalysisLevel.LINT, AnalysisLevel.FULL):
            _, ruff_issues = await self.run_ruff(file_path, content, fix=False)
            issues.extend(ruff_issues)
            ruff_passed = not any(i.severity == IssueSeverity.ERROR for i in ruff_issues)

        # Pyright
        if level in (AnalysisLevel.TYPE, AnalysisLevel.FULL):
            pyright_issues = await self.run_pyright(file_path, content)
            issues.extend(pyright_issues)
            pyright_passed = not any(i.severity == IssueSeverity.ERROR for i in pyright_issues)

        passed = ruff_passed and pyright_passed

        return StaticAnalysisResult(
            passed=passed,
            issues=issues,
            ruff_passed=ruff_passed,
            pyright_passed=pyright_passed,
        )

    async def validate_and_fix(
        self,
        file_path: str,
        content: str,
        max_attempts: int = 2,
    ) -> tuple[str, bool]:
        """분석 + 자동 수정"""
        current = content

        for attempt in range(max_attempts + 1):
            # 1. Ruff --fix
            fixed, ruff_issues = await self.run_ruff(file_path, current, fix=True)
            current = fixed

            # 2. Pyright 검사
            pyright_issues = await self.run_pyright(file_path, current)

            # 에러 없으면 성공
            errors = [i for i in pyright_issues if i.severity == IssueSeverity.ERROR]
            if not errors:
                return current, True

            # 3. Self-Correct (마지막 시도가 아닐 때만)
            if attempt < max_attempts and self._corrector:
                logger.info(f"Self-correcting attempt {attempt + 1}/{max_attempts}")
                current = await self._corrector.correct(current, errors)

        return current, False

    async def run_ruff(
        self,
        file_path: str,
        content: str,
        fix: bool = True,
    ) -> tuple[str, list[AnalysisIssue]]:
        """Ruff 실행"""
        issues: list[AnalysisIssue] = []

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=Path(file_path).suffix or ".py",
            delete=False,
        ) as f:
            f.write(content)
            temp_path = f.name

        try:
            # Ruff check
            cmd = ["ruff", "check", "--output-format=json"]
            if fix:
                cmd.append("--fix")
            cmd.append(temp_path)

            result = await self._executor.execute(
                command=cmd,
                timeout=30.0,
            )

            # Parse JSON output
            if result.stdout.strip():
                try:
                    ruff_output = json.loads(result.stdout)
                    for item in ruff_output:
                        issues.append(
                            AnalysisIssue(
                                file_path=file_path,
                                line=item.get("location", {}).get("row", 1),
                                column=item.get("location", {}).get("column", 0),
                                message=item.get("message", ""),
                                code=item.get("code", ""),
                                severity=self._ruff_severity(item.get("code", "")),
                                source="ruff",
                            )
                        )
                except json.JSONDecodeError:
                    pass

            # 수정된 파일 읽기
            fixed_content = Path(temp_path).read_text()
            return fixed_content, issues

        finally:
            Path(temp_path).unlink(missing_ok=True)

    async def run_pyright(
        self,
        file_path: str,
        content: str,
    ) -> list[AnalysisIssue]:
        """Pyright 실행"""
        issues: list[AnalysisIssue] = []

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=Path(file_path).suffix or ".py",
            delete=False,
        ) as f:
            f.write(content)
            temp_path = f.name

        try:
            result = await self._executor.execute(
                command=["pyright", "--outputjson", temp_path],
                timeout=60.0,
            )

            # Parse JSON output
            if result.stdout.strip():
                try:
                    pyright_output = json.loads(result.stdout)
                    for diag in pyright_output.get("generalDiagnostics", []):
                        issues.append(
                            AnalysisIssue(
                                file_path=file_path,
                                line=diag.get("range", {}).get("start", {}).get("line", 0) + 1,
                                column=diag.get("range", {}).get("start", {}).get("character", 0),
                                message=diag.get("message", ""),
                                code=diag.get("rule", ""),
                                severity=self._pyright_severity(diag.get("severity", "error")),
                                source="pyright",
                            )
                        )
                except json.JSONDecodeError:
                    pass

            return issues

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def _check_syntax(self, content: str) -> bool:
        """Python 문법 검사"""
        try:
            import ast

            ast.parse(content)
            return True
        except SyntaxError:
            return False

    def _ruff_severity(self, code: str) -> IssueSeverity:
        """Ruff 코드 → 심각도"""
        # E: Error, W: Warning, F: Pyflakes, etc.
        if code.startswith("E") or code.startswith("F"):
            return IssueSeverity.ERROR
        if code.startswith("W"):
            return IssueSeverity.WARNING
        return IssueSeverity.INFO

    def _pyright_severity(self, severity: str) -> IssueSeverity:
        """Pyright severity → 심각도"""
        mapping = {
            "error": IssueSeverity.ERROR,
            "warning": IssueSeverity.WARNING,
            "information": IssueSeverity.INFO,
        }
        return mapping.get(severity.lower(), IssueSeverity.ERROR)
