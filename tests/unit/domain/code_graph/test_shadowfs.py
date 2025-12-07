"""ShadowFS Tests

안전한 샌드박스 파일시스템 테스트
"""

import shutil
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.execution.shadowfs import FileDiff, ShadowFS

print("=" * 70)
print("🔥 ShadowFS Tests")
print("=" * 70)
print()


def create_test_workspace():
    """테스트 워크스페이스 생성"""
    workspace = Path(tempfile.mkdtemp(prefix="shadowfs_test_"))

    # 샘플 파일 생성
    (workspace / "src").mkdir()
    (workspace / "src" / "app.py").write_text("""def hello():
    print("Hello, World!")

def calculate(a, b):
    return a + b
""")

    (workspace / "src" / "utils.py").write_text("""def helper():
    return "helper"
""")

    return workspace


def cleanup_workspace(workspace: Path):
    """워크스페이스 정리"""
    if workspace.exists():
        shutil.rmtree(workspace)


def test_1_initialization():
    """Test 1: ShadowFS 초기화"""
    print("🔍 Test 1: Initialization...")

    workspace = create_test_workspace()

    try:
        fs = ShadowFS(str(workspace))

        assert fs.workspace == workspace
        assert len(fs.overlay) == 0
        assert len(fs.original) == 0
        assert not fs.has_changes()

        print("  ✅ ShadowFS initialized")
        print(f"  ✅ Workspace: {workspace}")
        print()

    finally:
        cleanup_workspace(workspace)


def test_2_read_file():
    """Test 2: 파일 읽기"""
    print("🔍 Test 2: Read File...")

    workspace = create_test_workspace()

    try:
        fs = ShadowFS(str(workspace))

        # 파일 읽기
        content = fs.read_file("src/app.py")

        assert "def hello():" in content
        assert "def calculate(a, b):" in content

        # 원본 백업 확인
        assert "src/app.py" in fs.original
        assert fs.original["src/app.py"] == content

        print("  ✅ File read successfully")
        print(f"  ✅ Content length: {len(content)} chars")
        print("  ✅ Original backed up")
        print()

    finally:
        cleanup_workspace(workspace)


def test_3_write_file():
    """Test 3: 파일 쓰기 (overlay)"""
    print("🔍 Test 3: Write File (overlay)...")

    workspace = create_test_workspace()

    try:
        fs = ShadowFS(str(workspace))

        # 원본 읽기
        original_content = fs.read_file("src/app.py")

        # 수정
        modified_content = """def hello():
    print("Hello, ShadowFS!")  # Modified

def calculate(a, b):
    if a is None or b is None:  # Added null check
        return 0
    return a + b
"""
        fs.write_file("src/app.py", modified_content)

        # Overlay 확인
        assert "src/app.py" in fs.overlay
        assert fs.overlay["src/app.py"] == modified_content

        # 원본 파일은 변경 안됨
        real_content = (workspace / "src" / "app.py").read_text()
        assert real_content == original_content

        # ShadowFS에서 읽으면 modified_content
        shadow_content = fs.read_file("src/app.py")
        assert shadow_content == modified_content

        assert fs.has_changes()

        print("  ✅ File written to overlay")
        print("  ✅ Real file unchanged")
        print("  ✅ Shadow read returns modified content")
        print()

    finally:
        cleanup_workspace(workspace)


def test_4_get_diff():
    """Test 4: Diff 생성"""
    print("🔍 Test 4: Get Diff...")

    workspace = create_test_workspace()

    try:
        fs = ShadowFS(str(workspace))

        # 수정
        fs.read_file("src/app.py")
        fs.write_file(
            "src/app.py",
            """def hello():
    print("Modified!")
""",
        )

        # Diff 생성
        diffs = fs.get_diff()

        assert len(diffs) == 1
        diff = diffs[0]

        assert diff.file_path == "src/app.py"
        assert diff.lines_added > 0 or diff.lines_removed > 0
        assert len(diff.unified_diff) > 0

        print(f"  ✅ Diff generated: {diff}")
        print(f"  ✅ Lines added: {diff.lines_added}")
        print(f"  ✅ Lines removed: {diff.lines_removed}")
        print(f"  ✅ Unified diff length: {len(diff.unified_diff)} chars")
        print()

    finally:
        cleanup_workspace(workspace)


def test_5_commit():
    """Test 5: Commit (실제 파일에 적용)"""
    print("🔍 Test 5: Commit...")

    workspace = create_test_workspace()

    try:
        fs = ShadowFS(str(workspace))

        # 수정
        modified_content = "# Modified by ShadowFS\n"
        fs.write_file("src/app.py", modified_content)

        assert fs.has_changes()

        # Commit
        fs.commit()

        # Overlay 클리어 확인
        assert len(fs.overlay) == 0
        assert len(fs.original) == 0
        assert not fs.has_changes()

        # 실제 파일 변경 확인
        real_content = (workspace / "src" / "app.py").read_text()
        assert real_content == modified_content

        print("  ✅ Committed successfully")
        print("  ✅ Overlay cleared")
        print("  ✅ Real file updated")
        print()

    finally:
        cleanup_workspace(workspace)


def test_6_rollback():
    """Test 6: Rollback (변경사항 폐기)"""
    print("🔍 Test 6: Rollback...")

    workspace = create_test_workspace()

    try:
        fs = ShadowFS(str(workspace))

        # 원본 읽기
        original_content = fs.read_file("src/app.py")

        # 수정
        fs.write_file("src/app.py", "# This will be rolled back")

        assert fs.has_changes()

        # Rollback
        fs.rollback()

        # Overlay 클리어 확인
        assert len(fs.overlay) == 0
        assert len(fs.original) == 0
        assert not fs.has_changes()

        # 실제 파일은 변경 안됨
        real_content = (workspace / "src" / "app.py").read_text()
        assert real_content == original_content

        print("  ✅ Rolled back successfully")
        print("  ✅ Overlay cleared")
        print("  ✅ Real file unchanged")
        print()

    finally:
        cleanup_workspace(workspace)


def test_7_multiple_files():
    """Test 7: 여러 파일 수정"""
    print("🔍 Test 7: Multiple Files...")

    workspace = create_test_workspace()

    try:
        fs = ShadowFS(str(workspace))

        # 여러 파일 수정
        fs.write_file("src/app.py", "# Modified app")
        fs.write_file("src/utils.py", "# Modified utils")

        # 새 파일 추가
        fs.write_file("src/new_file.py", "# New file")

        # State 확인
        state = fs.get_state()
        assert len(state.modified_files) == 3
        assert "src/app.py" in state.modified_files
        assert "src/utils.py" in state.modified_files
        assert "src/new_file.py" in state.modified_files

        # Diff 확인
        diffs = fs.get_diff()
        assert len(diffs) == 3

        # Commit
        fs.commit()

        # 모든 파일 확인
        assert (workspace / "src" / "app.py").read_text() == "# Modified app"
        assert (workspace / "src" / "utils.py").read_text() == "# Modified utils"
        assert (workspace / "src" / "new_file.py").read_text() == "# New file"

        print("  ✅ 3 files modified")
        print(f"  ✅ State: {state.modified_files}")
        print("  ✅ All committed successfully")
        print()

    finally:
        cleanup_workspace(workspace)


def test_8_state_tracking():
    """Test 8: State 추적"""
    print("🔍 Test 8: State Tracking...")

    workspace = create_test_workspace()

    try:
        fs = ShadowFS(str(workspace))

        # 초기 상태
        state1 = fs.get_state()
        assert len(state1.modified_files) == 0
        assert state1.total_lines_added == 0
        assert state1.total_lines_removed == 0
        assert state1.is_committed

        # 수정 후 상태
        fs.write_file("src/app.py", "# Short file\n")
        state2 = fs.get_state()
        assert len(state2.modified_files) == 1
        assert state2.total_lines_added > 0 or state2.total_lines_removed > 0
        assert not state2.is_committed

        # Commit 후 상태
        fs.commit()
        state3 = fs.get_state()
        assert len(state3.modified_files) == 0
        assert state3.is_committed

        print(f"  ✅ Initial state: {state1.modified_files}")
        print(
            f"  ✅ Modified state: {state2.modified_files} (+{state2.total_lines_added}/-{state2.total_lines_removed})"
        )
        print(f"  ✅ After commit: {state3.modified_files}")
        print()

    finally:
        cleanup_workspace(workspace)


def main():
    print("Starting ShadowFS Tests...\n")

    tests = [
        test_1_initialization,
        test_2_read_file,
        test_3_write_file,
        test_4_get_diff,
        test_5_commit,
        test_6_rollback,
        test_7_multiple_files,
        test_8_state_tracking,
    ]

    passed_count = 0
    for i, test_func in enumerate(tests):
        try:
            test_func()
            passed_count += 1
        except AssertionError as e:
            print(f"❌ {test_func.__name__.replace('test_', '').replace('_', ' ').title()} FAILED: {e}")
        except Exception as e:
            print(f"❌ {test_func.__name__.replace('test_', '').replace('_', ' ').title()} ERROR: {e}")
            import traceback

            traceback.print_exc()

    print("=" * 70)
    print(f"📊 최종 결과: {passed_count}/{len(tests)} 통과")
    print("=" * 70)

    if passed_count == len(tests):
        print("\n🎉 ShadowFS 테스트 성공!")
        print("\n✅ 검증된 기능:")
        print("  1. Initialization")
        print("  2. Read file")
        print("  3. Write file (overlay)")
        print("  4. Generate diff")
        print("  5. Commit (apply changes)")
        print("  6. Rollback (discard changes)")
        print("  7. Multiple files")
        print("  8. State tracking")
        print("\n🏆 ShadowFS 구현 완료!")
    else:
        print("\n⚠️  테스트 실패")
        print("재작업 필요!")


if __name__ == "__main__":
    main()
