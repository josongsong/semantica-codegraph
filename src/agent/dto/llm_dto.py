"""
LLM Structured Output용 DTO (Pydantic)

Domain Layer와 분리:
- Domain Service는 이 파일을 import하지 않음
- LLM Adapter에서만 사용
"""

from pydantic import BaseModel, Field

# ============================================================
# LLM Structured Output DTOs
# ============================================================


class AnalysisOutputDTO(BaseModel):
    """코드 분석 결과 DTO"""

    summary: str = Field(description="분석 요약")
    impacted_files: list[str] = Field(description="영향받는 파일들")
    complexity_score: int = Field(description="복잡도 점수 (1-5)")
    requires_tests: bool = Field(description="테스트 필요 여부")


class PlanOutputDTO(BaseModel):
    """수정 계획 DTO"""

    steps: list[str] = Field(description="수정 단계들")
    estimated_changes: int = Field(description="예상 변경 파일 수")
    risk_level: str = Field(description="위험도 (low/medium/high)")


class CodeChangeOutputDTO(BaseModel):
    """코드 변경 DTO"""

    file_path: str = Field(description="파일 경로")
    change_type: str = Field(description="변경 타입: modify, create, delete")
    start_line: int = Field(description="시작 라인 (0-based)")
    end_line: int = Field(description="종료 라인 (0-based)")
    new_content: str = Field(description="새로운 코드 내용")
    rationale: str = Field(description="변경 이유")


class CodeChangesOutputDTO(BaseModel):
    """여러 코드 변경 DTO"""

    changes: list[CodeChangeOutputDTO] = Field(description="코드 변경 리스트")


class CritiqueOutputDTO(BaseModel):
    """코드 검토 결과 DTO"""

    has_issues: bool = Field(description="문제 있는지 여부")
    issues: list[str] = Field(description="발견된 문제들")
    suggestions: list[str] = Field(description="개선 제안")
    approved: bool = Field(description="승인 여부")
