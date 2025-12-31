"""
Code Context Domain Models

Pure domain models - no infrastructure dependencies
"""

from dataclasses import dataclass, field
from enum import Enum


class LanguageSupport(Enum):
    """지원 언어 (확장 가능)"""

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    JAVA = "java"
    KOTLIN = "kotlin"
    GO = "go"
    RUST = "rust"


@dataclass
class CodeContext:
    """
    코드 컨텍스트 (Domain Model)

    코드 파일의 구조와 복잡도를 표현하는 순수 도메인 모델.
    Infrastructure 의존성 없음.

    Attributes:
        file_path: 파일 경로
        language: 프로그래밍 언어
        ast_depth: AST 트리 최대 깊이 (중첩 수준)
        complexity_score: 순환 복잡도 (0.0~1.0 normalized)
        loc: 코드 라인 수
        classes: 정의된 클래스 목록
        functions: 정의된 함수 목록
        imports: Import된 모듈 목록
        depends_on: 이 파일이 의존하는 파일들
        depended_by: 이 파일을 의존하는 파일들
    """

    file_path: str
    language: LanguageSupport

    # AST Analysis
    ast_depth: int
    complexity_score: float  # 0.0 (simple) ~ 1.0 (complex)
    loc: int  # Lines of code

    # Symbols
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    # Dependencies
    depends_on: set[str] = field(default_factory=set)
    depended_by: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Runtime validation"""
        if not isinstance(self.language, LanguageSupport):
            raise TypeError(f"language must be LanguageSupport, got {type(self.language).__name__}")

        if self.ast_depth < 0:
            raise ValueError(f"ast_depth must be >= 0, got {self.ast_depth}")

        if not (0.0 <= self.complexity_score <= 1.0):
            raise ValueError(f"complexity_score must be in [0.0, 1.0], got {self.complexity_score}")

        if self.loc < 0:
            raise ValueError(f"loc must be >= 0, got {self.loc}")

    @property
    def is_simple(self) -> bool:
        """간단한 코드 여부 (System 1 적합)"""
        return self.complexity_score < 0.3 and self.ast_depth < 5 and self.loc < 200

    @property
    def is_complex(self) -> bool:
        """복잡한 코드 여부 (System 2 필요)"""
        return self.complexity_score > 0.6 or self.ast_depth > 10 or self.loc > 500

    @property
    def dependency_count(self) -> int:
        """총 의존성 개수"""
        return len(self.depends_on) + len(self.depended_by)


@dataclass
class ImpactReport:
    """
    영향 분석 보고서 (Domain Model)

    코드 변경이 시스템에 미치는 영향을 분석한 결과.

    Attributes:
        changed_files: 변경된 파일 목록
        directly_affected: 직접 영향받는 파일들
        transitively_affected: 간접 영향받는 파일들
        risk_score: 위험도 점수 (0.0~1.0)
        max_impact_depth: 최대 영향 전파 깊이
    """

    changed_files: set[str]
    directly_affected: set[str] = field(default_factory=set)
    transitively_affected: set[str] = field(default_factory=set)
    risk_score: float = 0.0  # 0.0 (safe) ~ 1.0 (risky)
    max_impact_depth: int = 0

    def __post_init__(self) -> None:
        """Runtime validation"""
        if not (0.0 <= self.risk_score <= 1.0):
            raise ValueError(f"risk_score must be in [0.0, 1.0], got {self.risk_score}")

        if self.max_impact_depth < 0:
            raise ValueError(f"max_impact_depth must be >= 0, got {self.max_impact_depth}")

    @property
    def total_affected(self) -> int:
        """총 영향받는 파일 수"""
        return len(self.directly_affected) + len(self.transitively_affected)

    @property
    def is_safe(self) -> bool:
        """안전한 변경 여부"""
        return self.risk_score < 0.2 and self.max_impact_depth < 3

    @property
    def is_risky(self) -> bool:
        """위험한 변경 여부"""
        return self.risk_score > 0.6 or self.max_impact_depth > 5
