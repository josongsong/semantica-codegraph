"""
Patch Models

순수 데이터 모델 (외부 의존 없음)

NOTE: LoopState는 models.py에 정의됨
"""

from dataclasses import dataclass, field
from enum import Enum


class PatchStatus(Enum):
    """패치 상태"""

    GENERATED = "generated"
    VALIDATED = "validated"
    TESTED = "tested"
    FAILED = "failed"
    ACCEPTED = "accepted"


@dataclass(frozen=True)
class FileChange:
    """
    단일 파일 변경사항

    Multi-file patch를 위한 구조화된 diff
    """

    file_path: str
    old_content: str
    new_content: str
    diff_lines: list[str]  # Unified diff format

    def __post_init__(self):
        if not self.file_path:
            raise ValueError("file_path cannot be empty")


@dataclass(frozen=True)
class Patch:
    """
    불변 패치 객체 (Multi-file 지원)

    순수 데이터, 외부 의존 없음
    """

    id: str
    iteration: int
    files: list[FileChange]  # Multi-file 지원
    status: PatchStatus
    test_results: dict | None = None
    validation_errors: list[str] = field(default_factory=list)

    def __post_init__(self):
        # 빈 files 허용 (에러 케이스용 empty patch)
        pass

    @property
    def file_paths(self) -> list[str]:
        """모든 변경된 파일 경로"""
        return [f.file_path for f in self.files]

    @property
    def modified_files(self) -> set[str]:
        """변경된 파일 집합 (빠른 검색용)"""
        return set(self.file_paths)

    def get_file_change(self, file_path: str) -> FileChange | None:
        """특정 파일의 변경사항"""
        for f in self.files:
            if f.file_path == file_path:
                return f
        return None

    def with_status(self, status: PatchStatus) -> "Patch":
        """상태 변경 (불변)"""
        return Patch(
            id=self.id,
            iteration=self.iteration,
            files=self.files,
            status=status,
            test_results=self.test_results,
            validation_errors=self.validation_errors,
        )

    def with_test_results(self, results: dict) -> "Patch":
        """테스트 결과 추가"""
        return Patch(
            id=self.id,
            iteration=self.iteration,
            files=self.files,
            status=self.status,
            test_results=results,
            validation_errors=self.validation_errors,
        )

    def with_validation_errors(self, errors: list[str]) -> "Patch":
        """검증 에러 추가"""
        return Patch(
            id=self.id,
            iteration=self.iteration,
            files=self.files,
            status=self.status,
            test_results=self.test_results,
            validation_errors=errors,
        )

    def is_accepted(self) -> bool:
        """승인 여부"""
        return self.status == PatchStatus.ACCEPTED

    def is_rejected(self) -> bool:
        """거부 여부"""
        return self.status == PatchStatus.FAILED
