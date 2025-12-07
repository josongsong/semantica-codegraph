"""Git Manager Tests"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.execution.vcs import CommitInfo, GitManager

print("=" * 70)
print("🔥 Git Manager Tests")
print("=" * 70)
print()


def create_git_repo():
    """Git 저장소 생성"""
    workspace = Path(tempfile.mkdtemp(prefix="git_test_"))

    # Git 초기화
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=workspace, check=True, capture_output=True)

    # 초기 파일 생성
    (workspace / "README.md").write_text("# Test Repo")
    subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=workspace, check=True, capture_output=True)

    return workspace


def cleanup_repo(workspace: Path):
    """저장소 정리"""
    if workspace.exists():
        shutil.rmtree(workspace)


def test_1_initialization():
    """Test 1: GitManager 초기화"""
    print("🔍 Test 1: Initialization...")

    workspace = create_git_repo()

    try:
        manager = GitManager(workspace)

        assert manager.workspace == workspace
        assert manager.is_git_repo

        current_branch = manager.get_current_branch()
        assert current_branch in ["main", "master"]

        print("  ✅ GitManager initialized")
        print(f"  ✅ Current branch: {current_branch}")
        print()

    finally:
        cleanup_repo(workspace)


def test_2_create_branch():
    """Test 2: 브랜치 생성"""
    print("🔍 Test 2: Create Branch...")

    workspace = create_git_repo()

    try:
        manager = GitManager(workspace)

        # 새 브랜치 생성
        branch_name = "feature/test-feature"
        created_branch = manager.create_branch(branch_name)

        assert created_branch == branch_name

        # 현재 브랜치 확인
        current = manager.get_current_branch()
        assert current == branch_name

        print(f"  ✅ Branch created: {branch_name}")
        print(f"  ✅ Current branch: {current}")
        print()

    finally:
        cleanup_repo(workspace)


def test_3_commit_changes():
    """Test 3: 변경사항 커밋"""
    print("🔍 Test 3: Commit Changes...")

    workspace = create_git_repo()

    try:
        manager = GitManager(workspace)

        # 파일 수정
        test_file = workspace / "test.py"
        test_file.write_text("def test(): pass")

        # 커밋
        commit_info = manager.commit_changes(message="Add test function", files=["test.py"], author="Agent")

        assert isinstance(commit_info, CommitInfo)
        assert commit_info.message == "Add test function"
        assert commit_info.author == "Agent"
        assert len(commit_info.hash) == 40  # Full SHA
        assert "test.py" in commit_info.files_changed

        print(f"  ✅ Committed: {commit_info}")
        print(f"  ✅ Hash: {commit_info.short_hash()}")
        print(f"  ✅ Files: {commit_info.files_changed}")
        print()

    finally:
        cleanup_repo(workspace)


def test_4_get_diff():
    """Test 4: Diff 조회"""
    print("🔍 Test 4: Get Diff...")

    workspace = create_git_repo()

    try:
        manager = GitManager(workspace)

        # 파일 수정
        test_file = workspace / "app.py"
        test_file.write_text("def hello():\n    print('Hello!')")

        # 커밋
        commit_info = manager.commit_changes("Add hello function")

        # Diff 조회
        diff = manager.get_diff(commit_info.hash)

        assert len(diff) > 0
        assert "def hello():" in diff
        assert "+def hello():" in diff  # Added line

        print(f"  ✅ Diff retrieved: {len(diff)} chars")
        print("  ✅ Contains changes")
        print()

    finally:
        cleanup_repo(workspace)


def test_5_commit_history():
    """Test 5: 커밋 히스토리"""
    print("🔍 Test 5: Commit History...")

    workspace = create_git_repo()

    try:
        manager = GitManager(workspace)

        # 여러 커밋 생성
        for i in range(3):
            file = workspace / f"file{i}.py"
            file.write_text(f"# File {i}")
            manager.commit_changes(f"Add file {i}")

        # 히스토리 조회
        history = manager.get_commit_history(limit=5)

        assert len(history) >= 3  # 3 new + 1 initial
        assert all(isinstance(c, CommitInfo) for c in history)

        # 최신 커밋이 먼저
        assert "Add file 2" in history[0].message

        print(f"  ✅ History retrieved: {len(history)} commits")
        for i, commit in enumerate(history[:3], 1):
            print(f"     {i}. {commit}")
        print()

    finally:
        cleanup_repo(workspace)


def test_6_rollback():
    """Test 6: Rollback"""
    print("🔍 Test 6: Rollback...")

    workspace = create_git_repo()

    try:
        manager = GitManager(workspace)

        # 첫 번째 커밋
        file1 = workspace / "file1.py"
        file1.write_text("# File 1")
        commit1 = manager.commit_changes("Add file 1")

        # 두 번째 커밋
        file2 = workspace / "file2.py"
        file2.write_text("# File 2")
        commit2 = manager.commit_changes("Add file 2")

        # file2가 존재
        assert file2.exists()

        # Rollback to commit1
        manager.rollback_to(commit1.hash, hard=True)

        # file2가 사라짐
        assert not file2.exists()
        assert file1.exists()

        print(f"  ✅ Rolled back to {commit1.short_hash()}")
        print("  ✅ file2 removed")
        print()

    finally:
        cleanup_repo(workspace)


def test_7_non_git_repo():
    """Test 7: Git 저장소 아닌 경우"""
    print("🔍 Test 7: Non-Git Repo...")

    workspace = Path(tempfile.mkdtemp(prefix="non_git_"))

    try:
        manager = GitManager(workspace)

        assert not manager.is_git_repo

        # 기능은 작동하지만 mock으로
        branch = manager.create_branch("test")
        assert branch == "test"

        commit = manager.commit_changes("test", ["file.py"])
        assert commit.hash == "0" * 40  # Mock hash

        print("  ✅ Non-git repo handled gracefully")
        print("  ✅ Mock operations work")
        print()

    finally:
        cleanup_repo(workspace)


def test_8_commit_info_serialization():
    """Test 8: CommitInfo 직렬화"""
    print("🔍 Test 8: CommitInfo Serialization...")

    from datetime import datetime

    commit = CommitInfo(
        hash="abc123def456",
        message="Test commit",
        author="Agent",
        timestamp=datetime.now(),
        branch="main",
        files_changed=["file1.py", "file2.py"],
    )

    # to_dict
    commit_dict = commit.to_dict()

    assert commit_dict["hash"] == "abc123def456"
    assert commit_dict["short_hash"] == "abc123d"
    assert commit_dict["message"] == "Test commit"
    assert len(commit_dict["files_changed"]) == 2

    # __str__
    commit_str = str(commit)
    assert "abc123d" in commit_str
    assert "Test commit" in commit_str

    print("  ✅ Serialization works")
    print(f"  ✅ Short hash: {commit.short_hash()}")
    print(f"  ✅ String: {commit_str}")
    print()


def main():
    print("Starting Git Manager Tests...\n")

    tests = [
        test_1_initialization,
        test_2_create_branch,
        test_3_commit_changes,
        test_4_get_diff,
        test_5_commit_history,
        test_6_rollback,
        test_7_non_git_repo,
        test_8_commit_info_serialization,
    ]

    passed_count = 0
    for test_func in tests:
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
        print("\n🎉 Git Manager 테스트 성공!")
        print("\n✅ 검증된 기능:")
        print("  1. Initialization")
        print("  2. Create branch")
        print("  3. Commit changes")
        print("  4. Get diff")
        print("  5. Commit history")
        print("  6. Rollback")
        print("  7. Non-git repo handling")
        print("  8. CommitInfo serialization")
        print("\n🏆 Git Manager 구현 완료!")
    else:
        print("\n⚠️  테스트 실패")


if __name__ == "__main__":
    main()
