"""
Refactoring Domain Models Unit Tests

/ss Rule 3 준수:
✅ Happy path
✅ Invalid input (type mismatch, nullable violation)
✅ Boundary / Edge Case
✅ 모든 validation 검증
"""

import pytest

from apps.orchestrator.orchestrator.domain.code_editing.refactoring import (
    ExtractMethodRequest,
    FileChange,
    RefactoringResult,
    RenameRequest,
    SymbolInfo,
    SymbolKind,
    SymbolLocation,
)

# ============================================================================
# SymbolLocation Tests
# ============================================================================


class TestSymbolLocation:
    """SymbolLocation 테스트"""

    def test_happy_path_basic(self):
        """Happy path: 기본 위치"""
        loc = SymbolLocation(
            file_path="/test/main.py",
            line=10,
            column=5,
        )
        assert loc.file_path == "/test/main.py"
        assert loc.line == 10
        assert loc.column == 5
        assert loc.end_line is None
        assert loc.end_column is None

    def test_happy_path_multiline(self):
        """Happy path: 여러 줄 범위"""
        loc = SymbolLocation(
            file_path="/test/main.py",
            line=10,
            column=0,
            end_line=15,
            end_column=10,
        )
        assert loc.end_line == 15
        assert loc.end_column == 10
        assert loc.is_multiline is True

    def test_line_boundary_min(self):
        """Boundary: line = 1 (최소값)"""
        loc = SymbolLocation(
            file_path="/test/main.py",
            line=1,
            column=0,
        )
        assert loc.line == 1

    def test_line_invalid_zero(self):
        """Invalid: line = 0"""
        with pytest.raises(ValueError, match="line must be > 0"):
            SymbolLocation(
                file_path="/test/main.py",
                line=0,
                column=0,
            )

    def test_line_invalid_negative(self):
        """Invalid: line < 0"""
        with pytest.raises(ValueError, match="line must be > 0"):
            SymbolLocation(
                file_path="/test/main.py",
                line=-1,
                column=0,
            )

    def test_column_boundary_zero(self):
        """Boundary: column = 0"""
        loc = SymbolLocation(
            file_path="/test/main.py",
            line=1,
            column=0,
        )
        assert loc.column == 0

    def test_column_invalid_negative(self):
        """Invalid: column < 0"""
        with pytest.raises(ValueError, match="column must be >= 0"):
            SymbolLocation(
                file_path="/test/main.py",
                line=1,
                column=-1,
            )

    def test_end_line_less_than_line_fails(self):
        """Invalid: end_line < line"""
        with pytest.raises(ValueError, match="end_line .* must be >= line"):
            SymbolLocation(
                file_path="/test/main.py",
                line=10,
                column=0,
                end_line=5,  # < line
                end_column=10,
            )

    def test_same_line_end_column_less_fails(self):
        """Invalid: 같은 줄인데 end_column <= column"""
        with pytest.raises(ValueError, match="end_column .* must be > column"):
            SymbolLocation(
                file_path="/test/main.py",
                line=10,
                column=5,
                end_line=10,  # same line
                end_column=5,  # <= column
            )

    def test_file_path_empty_fails(self):
        """Invalid: file_path 비어있음"""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            SymbolLocation(
                file_path="",
                line=1,
                column=0,
            )

    def test_is_multiline_false(self):
        """Property: is_multiline = False (단일 줄)"""
        loc = SymbolLocation(
            file_path="/test/main.py",
            line=10,
            column=0,
        )
        assert loc.is_multiline is False

    def test_is_multiline_true(self):
        """Property: is_multiline = True (여러 줄)"""
        loc = SymbolLocation(
            file_path="/test/main.py",
            line=10,
            column=0,
            end_line=12,
            end_column=5,
        )
        assert loc.is_multiline is True


# ============================================================================
# SymbolInfo Tests
# ============================================================================


class TestSymbolInfo:
    """SymbolInfo 테스트"""

    def test_happy_path_basic(self):
        """Happy path: 기본 Symbol"""
        info = SymbolInfo(
            name="my_function",
            kind=SymbolKind.FUNCTION,
            location=SymbolLocation(
                file_path="/test/main.py",
                line=10,
                column=0,
            ),
        )
        assert info.name == "my_function"
        assert info.kind == SymbolKind.FUNCTION
        assert info.scope == ""  # default
        assert info.type_annotation is None  # default
        assert info.docstring is None  # default

    def test_happy_path_full_params(self):
        """Happy path: 모든 파라미터"""
        info = SymbolInfo(
            name="my_method",
            kind=SymbolKind.METHOD,
            location=SymbolLocation(
                file_path="/test/main.py",
                line=20,
                column=4,
            ),
            scope="MyClass",
            type_annotation="(self, x: int) -> str",
            docstring="My method docstring",
        )
        assert info.scope == "MyClass"
        assert info.type_annotation == "(self, x: int) -> str"
        assert info.docstring == "My method docstring"

    def test_name_empty_fails(self):
        """Invalid: name 비어있음"""
        with pytest.raises(ValueError, match="name cannot be empty"):
            SymbolInfo(
                name="",
                kind=SymbolKind.FUNCTION,
                location=SymbolLocation(
                    file_path="/test/main.py",
                    line=1,
                    column=0,
                ),
            )

    def test_kind_invalid_type_fails(self):
        """Invalid: kind가 SymbolKind가 아님"""
        with pytest.raises(TypeError, match="kind must be SymbolKind"):
            SymbolInfo(
                name="test",
                kind="function",  # type: ignore
                location=SymbolLocation(
                    file_path="/test/main.py",
                    line=1,
                    column=0,
                ),
            )

    def test_location_invalid_type_fails(self):
        """Invalid: location이 SymbolLocation이 아님"""
        with pytest.raises(TypeError, match="location must be SymbolLocation"):
            SymbolInfo(
                name="test",
                kind=SymbolKind.FUNCTION,
                location={"line": 1},  # type: ignore
            )

    def test_qualified_name_without_scope(self):
        """Property: qualified_name (scope 없음)"""
        info = SymbolInfo(
            name="my_function",
            kind=SymbolKind.FUNCTION,
            location=SymbolLocation(
                file_path="/test/main.py",
                line=1,
                column=0,
            ),
        )
        assert info.qualified_name == "my_function"

    def test_qualified_name_with_scope(self):
        """Property: qualified_name (scope 있음)"""
        info = SymbolInfo(
            name="my_method",
            kind=SymbolKind.METHOD,
            location=SymbolLocation(
                file_path="/test/main.py",
                line=1,
                column=0,
            ),
            scope="MyClass",
        )
        assert info.qualified_name == "MyClass.my_method"

    def test_is_private_true(self):
        """Property: is_private = True"""
        info = SymbolInfo(
            name="_private_func",
            kind=SymbolKind.FUNCTION,
            location=SymbolLocation(
                file_path="/test/main.py",
                line=1,
                column=0,
            ),
        )
        assert info.is_private is True

    def test_is_private_false_public(self):
        """Property: is_private = False (public)"""
        info = SymbolInfo(
            name="public_func",
            kind=SymbolKind.FUNCTION,
            location=SymbolLocation(
                file_path="/test/main.py",
                line=1,
                column=0,
            ),
        )
        assert info.is_private is False

    def test_is_private_false_dunder(self):
        """Property: is_private = False (__dunder__)"""
        info = SymbolInfo(
            name="__init__",
            kind=SymbolKind.METHOD,
            location=SymbolLocation(
                file_path="/test/main.py",
                line=1,
                column=0,
            ),
        )
        assert info.is_private is False


# ============================================================================
# FileChange Tests
# ============================================================================


class TestFileChange:
    """FileChange 테스트"""

    def test_happy_path_modification(self):
        """Happy path: 파일 수정"""
        change = FileChange(
            file_path="/test/main.py",
            original_content="x = 1",
            new_content="x = 2",
        )
        assert change.file_path == "/test/main.py"
        assert change.original_content == "x = 1"
        assert change.new_content == "x = 2"
        assert change.is_new_file is False
        assert change.is_deleted is False
        assert change.is_modified is True

    def test_happy_path_new_file(self):
        """Happy path: 새 파일 생성"""
        change = FileChange(
            file_path="/test/new.py",
            original_content="",
            new_content="print('hello')",
            is_new_file=True,
        )
        assert change.is_new_file is True
        assert change.is_deleted is False
        assert change.is_modified is False

    def test_happy_path_deletion(self):
        """Happy path: 파일 삭제"""
        change = FileChange(
            file_path="/test/old.py",
            original_content="old content",
            new_content="",
            is_deleted=True,
        )
        assert change.is_new_file is False
        assert change.is_deleted is True
        assert change.is_modified is False

    def test_file_path_empty_fails(self):
        """Invalid: file_path 비어있음"""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            FileChange(
                file_path="",
                original_content="x",
                new_content="y",
            )

    def test_new_file_with_original_content_fails(self):
        """Invalid: 새 파일인데 original_content 있음"""
        with pytest.raises(ValueError, match="original_content must be empty for new files"):
            FileChange(
                file_path="/test/new.py",
                original_content="old",
                new_content="new",
                is_new_file=True,
            )

    def test_deleted_file_with_new_content_fails(self):
        """Invalid: 삭제인데 new_content 있음"""
        with pytest.raises(ValueError, match="new_content must be empty for deleted files"):
            FileChange(
                file_path="/test/old.py",
                original_content="old",
                new_content="new",
                is_deleted=True,
            )

    def test_new_and_deleted_fails(self):
        """Invalid: 새 파일이면서 삭제는 모순"""
        with pytest.raises(ValueError, match="cannot be both new_file and deleted"):
            FileChange(
                file_path="/test/file.py",
                original_content="",
                new_content="",
                is_new_file=True,
                is_deleted=True,
            )

    def test_content_hash_property(self):
        """Property: content_hash"""
        change = FileChange(
            file_path="/test/main.py",
            original_content="hello world",
            new_content="hello world!",
        )
        # SHA256 hash는 예측 가능
        assert len(change.content_hash) == 8  # 첫 8자


# ============================================================================
# RenameRequest Tests
# ============================================================================


class TestRenameRequest:
    """RenameRequest 테스트"""

    def test_happy_path(self):
        """Happy path: 기본 Rename"""
        req = RenameRequest(
            symbol=SymbolInfo(
                name="old_name",
                kind=SymbolKind.FUNCTION,
                location=SymbolLocation(
                    file_path="/test/main.py",
                    line=1,
                    column=0,
                ),
            ),
            new_name="new_name",
        )
        assert req.symbol.name == "old_name"
        assert req.new_name == "new_name"
        assert req.dry_run is False  # default

    def test_dry_run_mode(self):
        """Happy path: dry_run 모드"""
        req = RenameRequest(
            symbol=SymbolInfo(
                name="old_name",
                kind=SymbolKind.FUNCTION,
                location=SymbolLocation(
                    file_path="/test/main.py",
                    line=1,
                    column=0,
                ),
            ),
            new_name="new_name",
            dry_run=True,
        )
        assert req.dry_run is True

    def test_new_name_empty_fails(self):
        """Invalid: new_name 비어있음"""
        with pytest.raises(ValueError, match="new_name cannot be empty"):
            RenameRequest(
                symbol=SymbolInfo(
                    name="old_name",
                    kind=SymbolKind.FUNCTION,
                    location=SymbolLocation(
                        file_path="/test/main.py",
                        line=1,
                        column=0,
                    ),
                ),
                new_name="",
            )

    def test_new_name_same_as_old_fails(self):
        """Invalid: new_name이 old_name과 같음"""
        with pytest.raises(ValueError, match="new_name .* must be different from old name"):
            RenameRequest(
                symbol=SymbolInfo(
                    name="same_name",
                    kind=SymbolKind.FUNCTION,
                    location=SymbolLocation(
                        file_path="/test/main.py",
                        line=1,
                        column=0,
                    ),
                ),
                new_name="same_name",
            )

    def test_new_name_invalid_identifier_fails(self):
        """Invalid: new_name이 유효한 Python identifier가 아님"""
        with pytest.raises(ValueError, match="is not a valid Python identifier"):
            RenameRequest(
                symbol=SymbolInfo(
                    name="old_name",
                    kind=SymbolKind.FUNCTION,
                    location=SymbolLocation(
                        file_path="/test/main.py",
                        line=1,
                        column=0,
                    ),
                ),
                new_name="123invalid",  # 숫자로 시작
            )


# ============================================================================
# ExtractMethodRequest Tests
# ============================================================================


class TestExtractMethodRequest:
    """ExtractMethodRequest 테스트"""

    def test_happy_path_basic(self):
        """Happy path: 기본 Extract"""
        req = ExtractMethodRequest(
            file_path="/test/main.py",
            start_line=10,
            end_line=15,
            new_function_name="extracted_func",
        )
        assert req.file_path == "/test/main.py"
        assert req.start_line == 10
        assert req.end_line == 15
        assert req.new_function_name == "extracted_func"
        assert req.target_scope == "module"  # default
        assert req.dry_run is False  # default

    def test_happy_path_class_scope(self):
        """Happy path: Class scope로 추출"""
        req = ExtractMethodRequest(
            file_path="/test/main.py",
            start_line=20,
            end_line=25,
            new_function_name="extracted_method",
            target_scope="MyClass",
            dry_run=True,
        )
        assert req.target_scope == "MyClass"
        assert req.dry_run is True

    def test_start_line_boundary_min(self):
        """Boundary: start_line = 1"""
        req = ExtractMethodRequest(
            file_path="/test/main.py",
            start_line=1,
            end_line=1,
            new_function_name="func",
        )
        assert req.start_line == 1

    def test_start_line_invalid_zero(self):
        """Invalid: start_line = 0"""
        with pytest.raises(ValueError, match="start_line must be > 0"):
            ExtractMethodRequest(
                file_path="/test/main.py",
                start_line=0,
                end_line=5,
                new_function_name="func",
            )

    def test_end_line_less_than_start_fails(self):
        """Invalid: end_line < start_line"""
        with pytest.raises(ValueError, match="end_line .* must be >= start_line"):
            ExtractMethodRequest(
                file_path="/test/main.py",
                start_line=10,
                end_line=5,
                new_function_name="func",
            )

    def test_new_function_name_empty_fails(self):
        """Invalid: new_function_name 비어있음"""
        with pytest.raises(ValueError, match="new_function_name cannot be empty"):
            ExtractMethodRequest(
                file_path="/test/main.py",
                start_line=1,
                end_line=5,
                new_function_name="",
            )

    def test_new_function_name_invalid_identifier_fails(self):
        """Invalid: new_function_name이 유효한 identifier가 아님"""
        with pytest.raises(ValueError, match="is not a valid Python identifier"):
            ExtractMethodRequest(
                file_path="/test/main.py",
                start_line=1,
                end_line=5,
                new_function_name="invalid-name",  # 하이픈 포함
            )

    def test_file_path_empty_fails(self):
        """Invalid: file_path 비어있음"""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            ExtractMethodRequest(
                file_path="",
                start_line=1,
                end_line=5,
                new_function_name="func",
            )

    def test_line_count_property(self):
        """Property: line_count"""
        req = ExtractMethodRequest(
            file_path="/test/main.py",
            start_line=10,
            end_line=15,
            new_function_name="func",
        )
        assert req.line_count == 6  # 10~15 (inclusive)


# ============================================================================
# RefactoringResult Tests
# ============================================================================


class TestRefactoringResult:
    """RefactoringResult 테스트"""

    def test_happy_path_success(self):
        """Happy path: 성공"""
        result = RefactoringResult(
            success=True,
            changes=[
                FileChange(
                    file_path="/test/main.py",
                    original_content="x = 1",
                    new_content="x = 2",
                ),
            ],
            affected_files=["/test/main.py"],
            execution_time_ms=50.0,
        )
        assert result.success is True
        assert len(result.changes) == 1
        assert len(result.affected_files) == 1
        assert result.warnings == []
        assert result.errors == []

    def test_happy_path_failure(self):
        """Happy path: 실패"""
        result = RefactoringResult(
            success=False,
            changes=[],
            affected_files=[],
            errors=["Syntax error"],
            execution_time_ms=30.0,
        )
        assert result.success is False
        assert result.errors == ["Syntax error"]

    def test_happy_path_with_warnings(self):
        """Happy path: 경고 포함"""
        result = RefactoringResult(
            success=True,
            changes=[
                FileChange(
                    file_path="/test/main.py",
                    original_content="x = 1",
                    new_content="x = 2",
                ),
            ],
            affected_files=["/test/main.py"],
            warnings=["Type hint missing"],
            execution_time_ms=50.0,
        )
        assert result.has_warnings is True
        assert len(result.warnings) == 1

    def test_execution_time_boundary_zero(self):
        """Boundary: execution_time_ms = 0"""
        result = RefactoringResult(
            success=True,
            changes=[
                FileChange(
                    file_path="/test/main.py",
                    original_content="x = 1",
                    new_content="x = 2",
                ),
            ],
            affected_files=["/test/main.py"],
            execution_time_ms=0,
        )
        assert result.execution_time_ms == 0

    def test_execution_time_invalid_negative(self):
        """Invalid: execution_time_ms < 0"""
        with pytest.raises(ValueError, match="execution_time_ms must be >= 0"):
            RefactoringResult(
                success=True,
                changes=[
                    FileChange(
                        file_path="/test/main.py",
                        original_content="x = 1",
                        new_content="x = 2",
                    ),
                ],
                affected_files=["/test/main.py"],
                execution_time_ms=-10.0,
            )

    def test_success_with_errors_fails(self):
        """Invalid: 성공인데 errors 있음"""
        with pytest.raises(ValueError, match="errors must be empty when success is True"):
            RefactoringResult(
                success=True,
                changes=[
                    FileChange(
                        file_path="/test/main.py",
                        original_content="x = 1",
                        new_content="x = 2",
                    ),
                ],
                affected_files=["/test/main.py"],
                errors=["Some error"],
                execution_time_ms=50.0,
            )

    def test_failure_without_errors_fails(self):
        """Invalid: 실패인데 errors 없음"""
        with pytest.raises(ValueError, match="errors must be provided when success is False"):
            RefactoringResult(
                success=False,
                changes=[],
                affected_files=[],
                errors=[],
                execution_time_ms=50.0,
            )

    def test_total_files_changed_property(self):
        """Property: total_files_changed"""
        result = RefactoringResult(
            success=True,
            changes=[
                FileChange(
                    file_path="/test/main.py",
                    original_content="x = 1",
                    new_content="x = 2",
                ),
                FileChange(
                    file_path="/test/util.py",
                    original_content="y = 1",
                    new_content="y = 2",
                ),
            ],
            affected_files=["/test/main.py", "/test/util.py"],
            execution_time_ms=100.0,
        )
        assert result.total_files_changed == 2

    def test_has_warnings_false(self):
        """Property: has_warnings = False"""
        result = RefactoringResult(
            success=True,
            changes=[
                FileChange(
                    file_path="/test/main.py",
                    original_content="x = 1",
                    new_content="x = 2",
                ),
            ],
            affected_files=["/test/main.py"],
            execution_time_ms=50.0,
        )
        assert result.has_warnings is False
