"""
Static Analysis Gate Port (Hexagonal Architecture)

RFC-060 Section 2.2: Static Analysis Gate
- Ruff (Linter) → 빠른 문법 검사
- Pyright (Type Checker) → 타입 오류 검출
- Self-Correct → LLM으로 자동 수정
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class AnalysisLevel(Enum):
    """분석 레벨"""

    SYNTAX = "syntax"  # 문법만 (ast.parse)
    LINT = "lint"  # Ruff
    TYPE = "type"  # Pyright
    FULL = "full"  # Lint + Type


class IssueSeverity(Enum):
    """이슈 심각도"""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class AnalysisIssue:
    """분석 이슈 (Immutable Value Object)"""

    file_path: str
    line: int
    column: int
    message: str
    code: str  # E.g., "F401", "reportMissingImports"
    severity: IssueSeverity
    source: str  # "ruff" | "pyright"

    @property
    def location(self) -> str:
        return f"{self.file_path}:{self.line}:{self.column}"


@dataclass
class StaticAnalysisResult:
    """분석 결과"""

    passed: bool
    issues: list[AnalysisIssue] = field(default_factory=list)
    fixed_content: str | None = None  # Self-correct 후 수정된 코드
    ruff_passed: bool = True
    pyright_passed: bool = True

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)


class IStaticAnalysisGate(Protocol):
    """Static Analysis Gate Port

    Pipeline: Ruff → Pyright → Self-Correct

    책임:
    - 빠른 문법/타입 검사 (테스트 전)
    - 자동 수정 가능한 이슈 fix
    - 수정 불가 시 LLM Self-Correct
    """

    async def validate(
        self,
        file_path: str,
        content: str,
        level: AnalysisLevel = AnalysisLevel.FULL,
    ) -> StaticAnalysisResult:
        """
        정적 분석 실행

        Args:
            file_path: 파일 경로 (타입 검사에 필요)
            content: 검사할 코드
            level: 분석 레벨

        Returns:
            StaticAnalysisResult: 분석 결과
        """
        ...

    async def validate_and_fix(
        self,
        file_path: str,
        content: str,
        max_attempts: int = 2,
    ) -> tuple[str, bool]:
        """
        분석 + 자동 수정

        Pipeline:
        1. Ruff --fix (자동 수정)
        2. Pyright 검사
        3. 실패 시 LLM Self-Correct (최대 max_attempts)

        Args:
            file_path: 파일 경로
            content: 원본 코드
            max_attempts: Self-correct 최대 시도 횟수

        Returns:
            (수정된_코드, 성공_여부)
        """
        ...

    async def run_ruff(
        self,
        file_path: str,
        content: str,
        fix: bool = True,
    ) -> tuple[str, list[AnalysisIssue]]:
        """
        Ruff 실행

        Args:
            file_path: 파일 경로
            content: 코드
            fix: 자동 수정 적용 여부

        Returns:
            (수정된_코드, 이슈_목록)
        """
        ...

    async def run_pyright(
        self,
        file_path: str,
        content: str,
    ) -> list[AnalysisIssue]:
        """
        Pyright 실행

        Returns:
            이슈 목록
        """
        ...
