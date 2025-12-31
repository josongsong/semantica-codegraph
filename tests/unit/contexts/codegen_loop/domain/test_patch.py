"""
Patch & FileChange Tests

SOTA-Level: Base, Edge, Extreme Cases
"""

import pytest

from codegraph_runtime.codegen_loop.domain.models import Budget, LoopState, LoopStatus
from codegraph_runtime.codegen_loop.domain.patch import (
    FileChange,
    Patch,
    PatchStatus,
)


class TestFileChange:
    """FileChange 테스트 (Base + Edge + Extreme)"""

    def test_valid_file_change(self):
        """Base: 유효한 FileChange 생성"""
        change = FileChange(
            file_path="src/main.py",
            old_content="def foo(): pass",
            new_content="def foo(): return 42",
            diff_lines=["-def foo(): pass", "+def foo(): return 42"],
        )

        assert change.file_path == "src/main.py"
        assert "def foo(): pass" in change.old_content
        assert "return 42" in change.new_content
        assert len(change.diff_lines) == 2

    def test_empty_file_path_raises(self):
        """Edge: 빈 file_path는 에러"""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            FileChange(
                file_path="",
                old_content="",
                new_content="",
                diff_lines=[],
            )

    def test_new_file_creation(self):
        """Edge: 새 파일 생성 (old_content 없음)"""
        change = FileChange(
            file_path="new_file.py",
            old_content="",
            new_content="def new_function(): pass",
            diff_lines=["+def new_function(): pass"],
        )

        assert change.old_content == ""
        assert len(change.new_content) > 0

    def test_file_deletion(self):
        """Edge: 파일 삭제 (new_content 없음)"""
        change = FileChange(
            file_path="deleted.py",
            old_content="def old(): pass",
            new_content="",
            diff_lines=["-def old(): pass"],
        )

        assert len(change.old_content) > 0
        assert change.new_content == ""

    def test_huge_file_change(self):
        """Extreme: 거대한 파일 변경 (1K lines, 축소)"""
        old = "\n".join([f"line_{i}" for i in range(1000)])  # 10000 → 1000
        new = "\n".join([f"line_{i}_modified" for i in range(1000)])  # 10000 → 1000
        diff = [f"-line_{i}\n+line_{i}_modified" for i in range(100)]  # Sample

        change = FileChange(
            file_path="huge.py",
            old_content=old,
            new_content=new,
            diff_lines=diff,
        )

        assert len(change.old_content.splitlines()) == 10000
        assert len(change.new_content.splitlines()) == 10000

    def test_unicode_content(self):
        """Edge: Unicode 문자 처리"""
        change = FileChange(
            file_path="unicode.py",
            old_content="# 한글 주석",
            new_content="# 日本語コメント",
            diff_lines=["-# 한글 주석", "+# 日本語コメント"],
        )

        assert "한글" in change.old_content
        assert "日本語" in change.new_content

    def test_path_with_spaces(self):
        """Edge: 공백 포함 경로"""
        change = FileChange(
            file_path="src/path with spaces/file.py",
            old_content="x",
            new_content="y",
            diff_lines=[],
        )

        assert " " in change.file_path


class TestPatch:
    """Patch 테스트 (Multi-file + All Cases)"""

    def test_single_file_patch(self):
        """Base: 단일 파일 패치"""
        patch = Patch(
            id="patch-001",
            iteration=1,
            files=[
                FileChange(
                    file_path="main.py",
                    old_content="old",
                    new_content="new",
                    diff_lines=["-old", "+new"],
                )
            ],
            status=PatchStatus.GENERATED,
        )

        assert patch.id == "patch-001"
        assert patch.iteration == 1
        assert len(patch.files) == 1
        assert patch.status == PatchStatus.GENERATED

    def test_multi_file_patch(self):
        """Base: Multi-file 패치"""
        patch = Patch(
            id="patch-002",
            iteration=2,
            files=[
                FileChange("file1.py", "a", "b", []),
                FileChange("file2.py", "c", "d", []),
                FileChange("file3.py", "e", "f", []),
            ],
            status=PatchStatus.GENERATED,
        )

        assert len(patch.files) == 3
        assert len(patch.file_paths) == 3
        assert "file1.py" in patch.modified_files
        assert "file2.py" in patch.modified_files
        assert "file3.py" in patch.modified_files

    def test_empty_files_allowed(self):
        """Edge: 빈 파일 패치 허용 (에러 케이스용)"""
        # 에러 케이스에서 empty patch 생성 가능
        patch = Patch(
            id="empty",
            iteration=0,
            files=[],
            status=PatchStatus.FAILED,
        )
        assert len(patch.files) == 0
        assert patch.status == PatchStatus.FAILED

    def test_get_file_change_exists(self):
        """Base: 특정 파일 변경사항 조회"""
        patch = Patch(
            id="p",
            iteration=1,
            files=[
                FileChange("a.py", "1", "2", []),
                FileChange("b.py", "3", "4", []),
            ],
            status=PatchStatus.GENERATED,
        )

        change = patch.get_file_change("a.py")

        assert change is not None
        assert change.file_path == "a.py"
        assert change.old_content == "1"

    def test_get_file_change_not_exists(self):
        """Edge: 존재하지 않는 파일 조회"""
        patch = Patch(
            id="p",
            iteration=1,
            files=[FileChange("a.py", "", "", [])],
            status=PatchStatus.GENERATED,
        )

        change = patch.get_file_change("nonexistent.py")

        assert change is None

    def test_with_status_immutable(self):
        """Base: 상태 변경은 새 객체 반환"""
        patch1 = Patch(
            id="p",
            iteration=1,
            files=[FileChange("a.py", "", "", [])],
            status=PatchStatus.GENERATED,
        )

        patch2 = patch1.with_status(PatchStatus.VALIDATED)

        # 원본 불변
        assert patch1.status == PatchStatus.GENERATED
        # 새 객체
        assert patch2.status == PatchStatus.VALIDATED
        assert patch2.id == patch1.id
        assert patch2.iteration == patch1.iteration

    def test_with_test_results(self):
        """Base: 테스트 결과 추가"""
        patch = Patch(
            id="p",
            iteration=1,
            files=[FileChange("a.py", "", "", [])],
            status=PatchStatus.TESTED,
        )

        results = {"pass_rate": 1.0, "passed": 10, "failed": 0}
        patch_with_results = patch.with_test_results(results)

        assert patch.test_results is None  # 원본 불변
        assert patch_with_results.test_results == results

    def test_with_validation_errors(self):
        """Base: 검증 에러 추가"""
        patch = Patch(
            id="p",
            iteration=1,
            files=[FileChange("a.py", "", "", [])],
            status=PatchStatus.FAILED,
        )

        errors = ["Error 1", "Error 2"]
        patch_with_errors = patch.with_validation_errors(errors)

        assert len(patch.validation_errors) == 0  # 원본
        assert patch_with_errors.validation_errors == errors

    def test_modified_files_set_fast_lookup(self):
        """Performance: modified_files는 set (O(1) lookup)"""
        patch = Patch(
            id="p",
            iteration=1,
            files=[FileChange(f"file{i}.py", "", "", []) for i in range(1000)],
            status=PatchStatus.GENERATED,
        )

        # Set이므로 빠른 조회
        assert "file500.py" in patch.modified_files
        assert "nonexistent.py" not in patch.modified_files
        assert len(patch.modified_files) == 1000

    def test_extreme_multi_file_patch(self):
        """Extreme: 100개 파일 동시 변경"""
        files = [FileChange(f"module{i}/file.py", f"old{i}", f"new{i}", []) for i in range(100)]

        patch = Patch(
            id="massive",
            iteration=1,
            files=files,
            status=PatchStatus.GENERATED,
        )

        assert len(patch.files) == 100
        assert len(patch.file_paths) == 100
        assert len(patch.modified_files) == 100

    def test_patch_status_lifecycle(self):
        """Integration: 패치 상태 생명주기"""
        patch = Patch(
            id="lifecycle",
            iteration=1,
            files=[FileChange("test.py", "", "", [])],
            status=PatchStatus.GENERATED,
        )

        # GENERATED → VALIDATED
        validated = patch.with_status(PatchStatus.VALIDATED)
        assert validated.status == PatchStatus.VALIDATED

        # VALIDATED → TESTED
        tested = validated.with_status(PatchStatus.TESTED)
        assert tested.status == PatchStatus.TESTED

        # TESTED → ACCEPTED (with results)
        results = {"pass_rate": 1.0}
        accepted = tested.with_test_results(results).with_status(PatchStatus.ACCEPTED)
        assert accepted.status == PatchStatus.ACCEPTED
        assert accepted.test_results == results


class TestLoopState:
    """LoopState 테스트 (models.py의 immutable LoopState)"""

    def test_initial_state(self):
        """Base: 초기 상태"""
        state = LoopState(
            task_id="test-task",
            status=LoopStatus.RUNNING,
            current_iteration=0,
            patches=[],
            budget=Budget(),
        )

        assert state.current_iteration == 0
        assert len(state.patches) == 0
        assert state.status == LoopStatus.RUNNING
        assert not state.should_stop()

    def test_with_patch_immutable(self):
        """Base: 패치 추가 (불변 - 새 객체 반환)"""
        state = LoopState(
            task_id="test",
            status=LoopStatus.RUNNING,
            current_iteration=0,
            patches=[],
            budget=Budget(),
        )
        patch = Patch(
            id="p1",
            iteration=1,
            files=[FileChange("a.py", "", "", [])],
            status=PatchStatus.GENERATED,
        )

        new_state = state.with_patch(patch)

        # 원본 불변
        assert len(state.patches) == 0
        # 새 객체
        assert len(new_state.patches) == 1
        assert new_state.patches[0] == patch

    def test_with_status_immutable(self):
        """Base: 상태 변경 (불변 - 새 객체 반환)"""
        state = LoopState(
            task_id="test",
            status=LoopStatus.RUNNING,
            current_iteration=0,
            patches=[],
            budget=Budget(),
        )

        converged_state = state.with_status(LoopStatus.CONVERGED)

        # 원본 불변
        assert state.status == LoopStatus.RUNNING
        # 새 객체
        assert converged_state.status == LoopStatus.CONVERGED

    def test_next_iteration_immutable(self):
        """Base: 다음 반복 (불변 - 새 객체 반환)"""
        state = LoopState(
            task_id="test",
            status=LoopStatus.RUNNING,
            current_iteration=0,
            patches=[],
            budget=Budget(),
        )

        next_state = state.next_iteration()

        # 원본 불변
        assert state.current_iteration == 0
        # 새 객체
        assert next_state.current_iteration == 1

    def test_should_stop_converged(self):
        """Base: 수렴 시 종료"""
        state = LoopState(
            task_id="test",
            status=LoopStatus.CONVERGED,
            current_iteration=5,
            patches=[],
            budget=Budget(),
        )

        assert state.should_stop()

    def test_should_stop_oscillating(self):
        """Base: 진동 시 종료"""
        state = LoopState(
            task_id="test",
            status=LoopStatus.OSCILLATING,
            current_iteration=5,
            patches=[],
            budget=Budget(),
        )

        assert state.should_stop()

    def test_should_stop_budget_exceeded(self):
        """Base: 예산 초과 시 종료"""
        budget = Budget(max_iterations=5, current_iterations=5)
        state = LoopState(
            task_id="test",
            status=LoopStatus.RUNNING,
            current_iteration=5,
            patches=[],
            budget=budget,
        )

        assert state.should_stop()

    def test_not_terminal(self):
        """Base: 종료 아님"""
        state = LoopState(
            task_id="test",
            status=LoopStatus.RUNNING,
            current_iteration=0,
            patches=[],
            budget=Budget(),
        )

        assert not state.should_stop()

    def test_get_recent_patches(self):
        """Base: 최근 N개 패치 조회"""
        patches = [
            Patch(id=f"p{i}", iteration=i, files=[FileChange("a.py", "", "", [])], status=PatchStatus.GENERATED)
            for i in range(5)
        ]
        state = LoopState(
            task_id="test",
            status=LoopStatus.RUNNING,
            current_iteration=5,
            patches=patches,
            budget=Budget(),
        )

        recent = state.get_recent_patches(3)

        assert len(recent) == 3
        assert recent[0].id == "p2"
        assert recent[2].id == "p4"


# Boundary & Extreme Cases
class TestBoundaryAndExtreme:
    """경계 및 극한 케이스"""

    def test_patch_with_null_bytes(self):
        """Extreme: Null byte 포함"""
        # Python은 null byte를 허용하지만 파일 시스템은 아님
        change = FileChange(
            file_path="test.py",
            old_content="hello\x00world",
            new_content="hello world",
            diff_lines=[],
        )

        assert "\x00" in change.old_content

    def test_patch_with_very_long_path(self):
        """Extreme: 매우 긴 경로 (255+ chars)"""
        long_path = "a/" * 200 + "file.py"  # > 400 chars

        change = FileChange(
            file_path=long_path,
            old_content="",
            new_content="",
            diff_lines=[],
        )

        assert len(change.file_path) > 400

    def test_duplicate_file_paths_in_patch(self):
        """Edge: 중복 파일 경로 (허용되지만 주의)"""
        patch = Patch(
            id="dup",
            iteration=1,
            files=[
                FileChange("same.py", "v1", "v2", []),
                FileChange("same.py", "v2", "v3", []),  # 중복
            ],
            status=PatchStatus.GENERATED,
        )

        # 마지막 것만 반환됨 (expected behavior)
        change = patch.get_file_change("same.py")
        assert change.old_content == "v1"  # 첫 번째

    def test_iteration_zero(self):
        """Edge: Iteration 0 (초기)"""
        patch = Patch(
            id="init",
            iteration=0,
            files=[FileChange("a.py", "", "", [])],
            status=PatchStatus.GENERATED,
        )

        assert patch.iteration == 0

    def test_negative_iteration(self):
        """Edge: 음수 iteration (허용)"""
        patch = Patch(
            id="neg",
            iteration=-1,
            files=[FileChange("a.py", "", "", [])],
            status=PatchStatus.GENERATED,
        )

        assert patch.iteration == -1

    def test_patch_id_empty_string(self):
        """Edge: 빈 ID (허용)"""
        patch = Patch(
            id="",
            iteration=1,
            files=[FileChange("a.py", "", "", [])],
            status=PatchStatus.GENERATED,
        )

        assert patch.id == ""

    def test_patch_id_uuid(self):
        """Base: UUID ID"""
        import uuid

        uid = str(uuid.uuid4())
        patch = Patch(
            id=uid,
            iteration=1,
            files=[FileChange("a.py", "", "", [])],
            status=PatchStatus.GENERATED,
        )

        assert patch.id == uid
        assert len(patch.id) == 36
