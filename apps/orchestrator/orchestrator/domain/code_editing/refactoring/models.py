"""
Refactoring Domain Models (L11 SOTA)

순수 비즈니스 로직 - 외부 의존성 없음 (Pure Python)

책임:
- Refactoring 요청/응답 모델 정의
- Symbol 정보 모델
- 파일 변경 사항 모델
- 비즈니스 규칙 (validation)

DRY 원칙:
- Hash 계산: utils.hash_utils 사용
- Validation: utils.validators 사용
"""

from dataclasses import dataclass, field
from enum import Enum

from apps.orchestrator.orchestrator.domain.code_editing.utils.hash_utils import compute_content_hash
from apps.orchestrator.orchestrator.domain.code_editing.utils.validators import Validator


class RefactoringType(str, Enum):
    """
    리팩토링 종류

    RENAME: Symbol 이름 변경
    EXTRACT_METHOD: 메서드 추출
    EXTRACT_FUNCTION: 함수 추출
    INLINE_VARIABLE: 변수 인라인화
    MOVE_TO_FILE: 파일 이동
    """

    RENAME = "rename"
    EXTRACT_METHOD = "extract_method"
    EXTRACT_FUNCTION = "extract_function"
    INLINE_VARIABLE = "inline_variable"
    MOVE_TO_FILE = "move_to_file"


class SymbolKind(str, Enum):
    """
    Symbol 종류 (LSP 기반)

    Python 예시:
    - VARIABLE: x = 1
    - FUNCTION: def func():
    - CLASS: class MyClass:
    - METHOD: def method(self):
    - MODULE: import math
    """

    VARIABLE = "variable"
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    MODULE = "module"
    PROPERTY = "property"
    CONSTANT = "constant"


@dataclass
class SymbolLocation:
    """
    Symbol 위치 정보

    Attributes:
        file_path: 파일 경로
        line: 줄 번호 (1-based)
        column: 컬럼 번호 (0-based)
        end_line: 끝 줄 번호 (선택)
        end_column: 끝 컬럼 번호 (선택)
    """

    file_path: str
    line: int
    column: int
    end_line: int | None = None
    end_column: int | None = None

    def __post_init__(self) -> None:
        """Runtime validation (DRY - Validator 사용)"""
        # Validation 1: file_path 비어있으면 안 됨
        Validator.non_empty_string(self.file_path, "file_path")

        # Validation 2: line >= 1
        Validator.positive_number(self.line, "line")

        # Validation 3: column >= 0
        Validator.non_negative_number(self.column, "column")

        # Validation 4: end_line >= line
        if self.end_line is not None and self.end_line < self.line:
            raise ValueError(f"end_line ({self.end_line}) must be >= line ({self.line})")

        # Validation 5: 같은 줄이면 end_column > column
        if self.end_line == self.line and self.end_column is not None:
            if self.end_column <= self.column:
                raise ValueError(f"end_column ({self.end_column}) must be > column ({self.column})")

    @property
    def is_multiline(self) -> bool:
        """여러 줄에 걸쳐있는지"""
        return self.end_line is not None and self.end_line > self.line


@dataclass
class SymbolInfo:
    """
    Symbol 정보

    Attributes:
        name: Symbol 이름
        kind: Symbol 종류
        location: 위치 정보
        scope: 스코프 (module, class name, etc.)
        type_annotation: 타입 힌트 (선택)
        docstring: Docstring (선택)
    """

    name: str
    kind: SymbolKind
    location: SymbolLocation
    scope: str = ""
    type_annotation: str | None = None
    docstring: str | None = None

    def __post_init__(self) -> None:
        """Runtime validation (DRY - Validator 사용)"""
        # Validation 1: name 비어있으면 안 됨
        Validator.non_empty_string(self.name, "name")

        # Validation 2: kind 타입 체크
        Validator.type_check(self.kind, SymbolKind, "kind")

        # Validation 3: location 타입 체크
        Validator.type_check(self.location, SymbolLocation, "location")

    @property
    def qualified_name(self) -> str:
        """Fully qualified name (scope.name)"""
        if self.scope:
            return f"{self.scope}.{self.name}"
        return self.name

    @property
    def is_private(self) -> bool:
        """Private symbol 여부 (Python convention: _name)"""
        return self.name.startswith("_") and not self.name.startswith("__")


@dataclass
class FileChange:
    """
    파일 변경 사항

    Attributes:
        file_path: 파일 경로
        original_content: 원본 내용 (해시 검증용)
        new_content: 새 내용
        is_new_file: 새 파일 생성 여부
        is_deleted: 파일 삭제 여부
    """

    file_path: str
    original_content: str
    new_content: str
    is_new_file: bool = False
    is_deleted: bool = False

    def __post_init__(self) -> None:
        """Runtime validation (DRY - Validator 사용)"""
        # Validation 1: file_path 비어있으면 안 됨
        Validator.non_empty_string(self.file_path, "file_path")

        # Validation 2: 새 파일이면 original_content 비어야 함
        if self.is_new_file and self.original_content:
            raise ValueError("original_content must be empty for new files")

        # Validation 3: 삭제이면 new_content 비어야 함
        if self.is_deleted and self.new_content:
            raise ValueError("new_content must be empty for deleted files")

        # Validation 4: 새 파일이면서 삭제는 모순
        if self.is_new_file and self.is_deleted:
            raise ValueError("cannot be both new_file and deleted")

    @property
    def is_modified(self) -> bool:
        """수정 여부"""
        return not self.is_new_file and not self.is_deleted

    @property
    def content_hash(self) -> str:
        """원본 내용 해시 (충돌 감지용) - DRY: utils 사용"""
        return compute_content_hash(self.original_content, length=8)


# ============================================================================
# Refactoring Request Models
# ============================================================================


@dataclass
class RenameRequest:
    """
    Symbol Rename 요청

    Attributes:
        symbol: 변경할 Symbol 정보
        new_name: 새 이름
        dry_run: 미리보기 모드
    """

    symbol: SymbolInfo
    new_name: str
    dry_run: bool = False

    def __post_init__(self) -> None:
        """Runtime validation (DRY - Validator 사용)"""
        # Validation 1: new_name 비어있으면 안 됨
        Validator.non_empty_string(self.new_name, "new_name")

        # Validation 2: new_name이 old_name과 같으면 안 됨
        if self.new_name == self.symbol.name:
            raise ValueError(f"new_name ({self.new_name}) must be different from old name ({self.symbol.name})")

        # Validation 3: Python identifier 체크
        Validator.python_identifier(self.new_name, "new_name")


@dataclass
class ExtractMethodRequest:
    """
    Method/Function 추출 요청

    Attributes:
        file_path: 파일 경로
        start_line: 추출 시작 줄 (1-based)
        end_line: 추출 끝 줄 (1-based, inclusive)
        new_function_name: 새 함수 이름
        target_scope: 추출 위치 (class name or "module")
        dry_run: 미리보기 모드
    """

    file_path: str
    start_line: int
    end_line: int
    new_function_name: str
    target_scope: str = "module"
    dry_run: bool = False

    def __post_init__(self) -> None:
        """Runtime validation (DRY - Validator 사용)"""
        # Validation 1: file_path 비어있으면 안 됨
        Validator.non_empty_string(self.file_path, "file_path")

        # Validation 2: line numbers
        Validator.positive_number(self.start_line, "start_line")
        if self.end_line < self.start_line:
            raise ValueError(f"end_line ({self.end_line}) must be >= start_line ({self.start_line})")

        # Validation 3: new_function_name (비어있지 않음 + Python identifier)
        Validator.non_empty_string(self.new_function_name, "new_function_name")
        Validator.python_identifier(self.new_function_name, "new_function_name")

    @property
    def line_count(self) -> int:
        """추출할 줄 수"""
        return self.end_line - self.start_line + 1


# ============================================================================
# Refactoring Result Models
# ============================================================================


@dataclass
class RefactoringResult:
    """
    Refactoring 결과

    Attributes:
        success: 성공 여부
        changes: 파일 변경 사항 리스트
        affected_files: 영향받은 파일 목록
        warnings: 경고 메시지
        errors: 에러 메시지
        execution_time_ms: 실행 시간
    """

    success: bool
    changes: list[FileChange]
    affected_files: list[str]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    execution_time_ms: float = 0

    def __post_init__(self) -> None:
        """Runtime validation (DRY - Validator 사용)"""
        # Validation 1: execution_time_ms
        Validator.non_negative_number(self.execution_time_ms, "execution_time_ms")

        # Validation 2: 성공 시 errors 비어야 함
        if self.success and self.errors:
            raise ValueError("errors must be empty when success is True")

        # Validation 3: 실패 시 errors 필수
        if not self.success and not self.errors:
            raise ValueError("errors must be provided when success is False")

    @property
    def total_files_changed(self) -> int:
        """변경된 파일 수"""
        return len(self.changes)

    @property
    def has_warnings(self) -> bool:
        """경고 있는지"""
        return len(self.warnings) > 0
