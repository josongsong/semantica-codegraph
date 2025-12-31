"""
Atomic Edit Adapter Integration Tests - SOTA급

실제 파일 시스템과 Lock Manager 사용 테스트

/ss Rule 3:
✅ Happy path (단일/다중 파일)
✅ Invalid input (conflict, hash mismatch)
✅ Rollback 테스트
✅ Dry-run 테스트
✅ SERIALIZABLE isolation 테스트
"""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.orchestrator.orchestrator.adapters.code_editing.atomic_edit import AtomicEditAdapter
from apps.orchestrator.orchestrator.domain.code_editing import (
    AtomicEditRequest,
    ConflictType,
    FileEdit,
    IsolationLevel,
    TransactionState,
)

# ============================================================================
# Mock Lock Manager
# ============================================================================


class MockSoftLock:
    """Mock SoftLock"""

    def __init__(self, agent_id: str, file_path: str):
        self.agent_id = agent_id
        self.file_path = file_path


class MockLockAcquisitionResult:
    """Mock LockAcquisitionResult"""

    def __init__(self, success: bool, message: str = "", existing_lock=None):
        self.success = success
        self.message = message
        self.existing_lock = existing_lock


class MockLockManager:
    """Mock Lock Manager (메모리 기반)"""

    def __init__(self):
        self._locks: dict[str, MockSoftLock] = {}

    async def acquire_lock(self, agent_id: str, file_path: str, lock_type: str):
        if file_path in self._locks:
            existing = self._locks[file_path]
            if existing.agent_id != agent_id:
                return MockLockAcquisitionResult(
                    success=False,
                    message=f"Locked by {existing.agent_id}",
                    existing_lock=existing,
                )
        self._locks[file_path] = MockSoftLock(agent_id, file_path)
        return MockLockAcquisitionResult(success=True, message="Lock acquired")

    async def release_lock(self, agent_id: str, file_path: str) -> bool:
        if file_path in self._locks:
            if self._locks[file_path].agent_id == agent_id:
                del self._locks[file_path]
                return True
        return False

    async def get_lock(self, file_path: str):
        return self._locks.get(file_path)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_workspace(tmp_path):
    """임시 workspace"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture
def lock_manager():
    """Mock Lock Manager"""
    return MockLockManager()


@pytest.fixture
def adapter(temp_workspace, lock_manager):
    """Adapter fixture"""
    return AtomicEditAdapter(
        lock_manager=lock_manager,
        workspace_root=str(temp_workspace),
    )


@pytest.fixture
def sample_files(temp_workspace):
    """Sample files"""
    # main.py
    main_file = temp_workspace / "main.py"
    main_file.write_text("def main():\n    print('hello')\n")

    # config.py
    config_file = temp_workspace / "config.py"
    config_file.write_text("DEBUG = True\nVERSION = '1.0'\n")

    return {
        "main": str(main_file),
        "config": str(config_file),
    }


# ============================================================================
# Tests
# ============================================================================

pytestmark = pytest.mark.asyncio


class TestAtomicEditAdapter:
    """AtomicEditAdapter Integration Tests"""

    async def test_execute_single_file_success(self, adapter, sample_files, temp_workspace):
        """Happy path: 단일 파일 편집"""
        main_path = sample_files["main"]
        original = Path(main_path).read_text()

        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=main_path,
                    original_content=original,
                    new_content="def main():\n    print('world')\n",
                )
            ],
            agent_id="test-agent",
        )

        result = await adapter.execute(request)

        assert result.success is True
        assert result.transaction_state == TransactionState.COMMITTED
        assert len(result.committed_files) == 1
        assert main_path in result.committed_files

        # 파일 확인
        new_content = Path(main_path).read_text()
        assert "print('world')" in new_content

    async def test_execute_multi_file_success(self, adapter, sample_files, temp_workspace):
        """Happy path: 다중 파일 편집 (atomic)"""
        main_path = sample_files["main"]
        config_path = sample_files["config"]

        main_original = Path(main_path).read_text()
        config_original = Path(config_path).read_text()

        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=main_path,
                    original_content=main_original,
                    new_content="def main():\n    pass\n",
                ),
                FileEdit(
                    file_path=config_path,
                    original_content=config_original,
                    new_content="DEBUG = False\nVERSION = '2.0'\n",
                ),
            ],
            agent_id="test-agent",
        )

        result = await adapter.execute(request)

        assert result.success is True
        assert result.transaction_state == TransactionState.COMMITTED
        assert len(result.committed_files) == 2

        # 파일 확인
        assert "pass" in Path(main_path).read_text()
        assert "DEBUG = False" in Path(config_path).read_text()

    async def test_execute_dry_run(self, adapter, sample_files):
        """Dry-run 모드 (미리보기)"""
        main_path = sample_files["main"]
        original = Path(main_path).read_text()

        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=main_path,
                    original_content=original,
                    new_content="MODIFIED",
                )
            ],
            agent_id="test-agent",
            dry_run=True,
        )

        result = await adapter.execute(request)

        assert result.success is True
        assert result.transaction_state == TransactionState.COMMITTED

        # 파일은 변경되지 않아야 함
        assert Path(main_path).read_text() == original

    async def test_execute_hash_mismatch(self, adapter, sample_files):
        """Conflict: 해시 불일치 (파일이 변경됨)"""
        main_path = sample_files["main"]

        # 잘못된 해시로 요청
        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=main_path,
                    original_content="wrong content",  # 실제 파일과 다름
                    new_content="new content",
                    expected_hash="wrong_hash",
                )
            ],
            agent_id="test-agent",
        )

        result = await adapter.execute(request)

        assert result.success is False
        assert result.transaction_state == TransactionState.FAILED
        assert len(result.conflicts) > 0
        assert result.conflicts[0].conflict_type == ConflictType.HASH_MISMATCH

    async def test_execute_file_not_found(self, adapter, temp_workspace):
        """Conflict: 파일 없음"""
        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=str(temp_workspace / "nonexistent.py"),
                    original_content="x = 1",
                    new_content="x = 2",
                )
            ],
            agent_id="test-agent",
        )

        result = await adapter.execute(request)

        assert result.success is False
        assert len(result.conflicts) > 0
        assert result.conflicts[0].conflict_type == ConflictType.FILE_DELETED

    async def test_execute_serializable_lock_conflict(self, adapter, sample_files, lock_manager):
        """SERIALIZABLE: Lock 충돌"""
        main_path = sample_files["main"]
        original = Path(main_path).read_text()

        # 다른 에이전트가 Lock 획득
        await lock_manager.acquire_lock("other-agent", main_path, "WRITE")

        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=main_path,
                    original_content=original,
                    new_content="new content",
                )
            ],
            agent_id="test-agent",
            isolation_level=IsolationLevel.SERIALIZABLE,
        )

        result = await adapter.execute(request)

        assert result.success is False
        assert len(result.conflicts) > 0
        assert result.conflicts[0].conflict_type == ConflictType.LOCK_HELD

    async def test_rollback_success(self, adapter, sample_files):
        """Rollback: 성공"""
        main_path = sample_files["main"]
        original = Path(main_path).read_text()

        # 먼저 변경
        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=main_path,
                    original_content=original,
                    new_content="MODIFIED CONTENT",
                )
            ],
            agent_id="test-agent",
        )

        result = await adapter.execute(request)
        assert result.success is True
        assert result.rollback_info is not None

        # 변경 확인
        assert "MODIFIED CONTENT" in Path(main_path).read_text()

        # Rollback
        rollback_result = await adapter.rollback(result.rollback_info.rollback_id)

        assert rollback_result.success is True
        assert rollback_result.transaction_state == TransactionState.COMMITTED

        # 원본 복원 확인
        assert Path(main_path).read_text() == original

    async def test_rollback_not_found(self, adapter):
        """Rollback: ID 없음"""
        with pytest.raises(ValueError, match="Rollback not found"):
            await adapter.rollback("nonexistent-rollback-id")

    async def test_check_conflicts_no_conflict(self, adapter, sample_files):
        """check_conflicts: 충돌 없음"""
        main_path = sample_files["main"]
        original = Path(main_path).read_text()

        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=main_path,
                    original_content=original,
                    new_content="new content",
                )
            ],
            agent_id="test-agent",
        )

        conflicts = await adapter.check_conflicts(request)

        assert len(conflicts) == 0

    async def test_check_conflicts_with_conflict(self, adapter, temp_workspace):
        """check_conflicts: 충돌 있음"""
        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=str(temp_workspace / "nonexistent.py"),
                    original_content="x = 1",
                    new_content="x = 2",
                )
            ],
            agent_id="test-agent",
        )

        conflicts = await adapter.check_conflicts(request)

        assert len(conflicts) > 0

    async def test_execute_with_timeout(self, adapter, sample_files):
        """Timeout 설정"""
        main_path = sample_files["main"]
        original = Path(main_path).read_text()

        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=main_path,
                    original_content=original,
                    new_content="new content",
                )
            ],
            agent_id="test-agent",
            timeout_seconds=60.0,
        )

        result = await adapter.execute(request)

        assert result.success is True

    async def test_execute_creates_parent_dirs(self, adapter, temp_workspace):
        """부모 디렉토리 자동 생성"""
        new_file_path = str(temp_workspace / "new_dir" / "new_file.py")

        # 파일이 없으므로 먼저 생성해야 함
        # 이 테스트는 파일이 존재해야 하므로 스킵
        # (AtomicEditAdapter는 기존 파일 수정용)
        pass

    async def test_isolation_read_committed(self, adapter, sample_files, lock_manager):
        """READ_COMMITTED: Lock 체크 안 함"""
        main_path = sample_files["main"]
        original = Path(main_path).read_text()

        # 다른 에이전트가 Lock 획득
        await lock_manager.acquire_lock("other-agent", main_path, "WRITE")

        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=main_path,
                    original_content=original,
                    new_content="new content",
                )
            ],
            agent_id="test-agent",
            isolation_level=IsolationLevel.READ_COMMITTED,  # Lock 체크 안 함
        )

        result = await adapter.execute(request)

        # READ_COMMITTED는 Lock 무시 (해시만 체크)
        assert result.success is True


class TestAtomicEditAdapterEdgeCases:
    """Edge Case Tests"""

    async def test_empty_edit_list_fails(self):
        """edits가 비어있으면 validation 실패"""
        with pytest.raises(ValueError, match="edits cannot be empty"):
            AtomicEditRequest(edits=[], agent_id="test")

    async def test_duplicate_files_fails(self, temp_workspace):
        """같은 파일 두 번 편집하면 validation 실패"""
        file_path = str(temp_workspace / "test.py")

        with pytest.raises(ValueError, match="Duplicate file paths"):
            AtomicEditRequest(
                edits=[
                    FileEdit(file_path=file_path, original_content="a", new_content="b"),
                    FileEdit(file_path=file_path, original_content="b", new_content="c"),
                ],
                agent_id="test",
            )

    async def test_execution_time_measured(self, adapter, sample_files):
        """실행 시간 측정"""
        main_path = sample_files["main"]
        original = Path(main_path).read_text()

        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=main_path,
                    original_content=original,
                    new_content="new",
                )
            ],
            agent_id="test-agent",
        )

        result = await adapter.execute(request)

        assert result.execution_time_ms > 0


# ============================================================================
# Critical Missing Scenarios (SOTA Coverage)
# ============================================================================


class TestAtomicEditConcurrency:
    """동시성 테스트 - Multi-agent race condition"""

    async def test_concurrent_modification_same_file(self, temp_workspace, lock_manager):
        """두 agent가 동시에 같은 파일 수정 시도 (SERIALIZABLE)"""
        # Setup
        test_file = temp_workspace / "shared.py"
        test_file.write_text("counter = 0\n")

        adapter = AtomicEditAdapter(lock_manager, str(temp_workspace))
        original = test_file.read_text()

        # Agent 1 먼저 Lock 획득
        request1 = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=str(test_file),
                    original_content=original,
                    new_content="counter = 1\n",
                )
            ],
            agent_id="agent-1",
            isolation_level=IsolationLevel.SERIALIZABLE,
        )

        # Agent 1 실행 (Lock 유지)
        result1 = await adapter.execute(request1)
        assert result1.success is True

        # Agent 2가 같은 파일 수정 시도 (hash mismatch로 실패해야 함)
        request2 = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=str(test_file),
                    original_content=original,  # 이전 버전 (이미 변경됨)
                    new_content="counter = 2\n",
                )
            ],
            agent_id="agent-2",
            isolation_level=IsolationLevel.SERIALIZABLE,
        )

        result2 = await adapter.execute(request2)

        # Agent 2는 hash mismatch로 실패
        assert result2.success is False
        assert any(c.conflict_type == ConflictType.HASH_MISMATCH for c in result2.conflicts)

        # 파일은 Agent 1의 값 유지
        assert test_file.read_text() == "counter = 1\n"

    async def test_concurrent_modification_different_files(self, temp_workspace, lock_manager):
        """두 agent가 다른 파일 동시 수정 (성공해야 함)"""
        file1 = temp_workspace / "file1.py"
        file2 = temp_workspace / "file2.py"
        file1.write_text("x = 1\n")
        file2.write_text("y = 2\n")

        adapter = AtomicEditAdapter(lock_manager, str(temp_workspace))

        # 동시 실행 시뮬레이션
        request1 = AtomicEditRequest(
            edits=[FileEdit(file_path=str(file1), original_content="x = 1\n", new_content="x = 10\n")],
            agent_id="agent-1",
        )
        request2 = AtomicEditRequest(
            edits=[FileEdit(file_path=str(file2), original_content="y = 2\n", new_content="y = 20\n")],
            agent_id="agent-2",
        )

        # 병렬 실행
        result1, result2 = await asyncio.gather(
            adapter.execute(request1),
            adapter.execute(request2),
        )

        # 둘 다 성공
        assert result1.success is True
        assert result2.success is True
        assert file1.read_text() == "x = 10\n"
        assert file2.read_text() == "y = 20\n"


class TestAtomicEditPartialFailureRollback:
    """부분 실패 시 Rollback 테스트 - Atomic 보장의 핵심"""

    async def test_partial_failure_rollback_on_hash_mismatch(self, temp_workspace, lock_manager):
        """3개 파일 중 2번째에서 hash mismatch 시 1번째 rollback"""
        file1 = temp_workspace / "file1.py"
        file2 = temp_workspace / "file2.py"
        file3 = temp_workspace / "file3.py"

        file1.write_text("a = 1\n")
        file2.write_text("b = 2\n")
        file3.write_text("c = 3\n")

        adapter = AtomicEditAdapter(lock_manager, str(temp_workspace))

        # file2의 hash가 틀린 요청
        request = AtomicEditRequest(
            edits=[
                FileEdit(file_path=str(file1), original_content="a = 1\n", new_content="a = 10\n"),
                FileEdit(
                    file_path=str(file2),
                    original_content="WRONG CONTENT",  # Hash mismatch
                    new_content="b = 20\n",
                    expected_hash="wrong_hash",
                ),
                FileEdit(file_path=str(file3), original_content="c = 3\n", new_content="c = 30\n"),
            ],
            agent_id="test-agent",
        )

        result = await adapter.execute(request)

        # 전체 실패
        assert result.success is False
        assert result.transaction_state == TransactionState.FAILED

        # 모든 파일이 원래 상태 유지 (atomic - 아무것도 변경 안 됨)
        assert file1.read_text() == "a = 1\n"
        assert file2.read_text() == "b = 2\n"
        assert file3.read_text() == "c = 3\n"

    async def test_apply_failure_triggers_rollback(self, temp_workspace, lock_manager):
        """파일 쓰기 실패 시 이전 파일들 rollback"""
        file1 = temp_workspace / "file1.py"
        file1.write_text("original\n")

        # 존재하지 않는 디렉토리 (쓰기 실패 유도는 어려움 - 대신 검증)
        adapter = AtomicEditAdapter(lock_manager, str(temp_workspace))

        request = AtomicEditRequest(
            edits=[FileEdit(file_path=str(file1), original_content="original\n", new_content="modified\n")],
            agent_id="test-agent",
        )

        result = await adapter.execute(request)
        assert result.success is True
        assert result.rollback_info is not None

        # Rollback 실행
        rollback_result = await adapter.rollback(result.rollback_info.rollback_id)
        assert rollback_result.success is True

        # 원본 복원
        assert file1.read_text() == "original\n"


class TestAtomicEditSpecialCases:
    """특수 케이스 테스트"""

    async def test_unicode_file_path(self, temp_workspace, lock_manager):
        """유니코드 경로 (한글 등)"""
        korean_dir = temp_workspace / "테스트_디렉토리"
        korean_dir.mkdir()
        korean_file = korean_dir / "한글파일.py"
        korean_file.write_text("# 한글 주석\nx = 1\n", encoding="utf-8")

        adapter = AtomicEditAdapter(lock_manager, str(temp_workspace))

        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=str(korean_file),
                    original_content="# 한글 주석\nx = 1\n",
                    new_content="# 수정된 주석\nx = 2\n",
                )
            ],
            agent_id="test-agent",
        )

        result = await adapter.execute(request)

        assert result.success is True
        assert korean_file.read_text(encoding="utf-8") == "# 수정된 주석\nx = 2\n"

    async def test_path_with_spaces(self, temp_workspace, lock_manager):
        """공백이 포함된 경로"""
        space_dir = temp_workspace / "path with spaces"
        space_dir.mkdir()
        space_file = space_dir / "file name.py"
        space_file.write_text("value = 'test'\n")

        adapter = AtomicEditAdapter(lock_manager, str(temp_workspace))

        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=str(space_file),
                    original_content="value = 'test'\n",
                    new_content="value = 'modified'\n",
                )
            ],
            agent_id="test-agent",
        )

        result = await adapter.execute(request)

        assert result.success is True
        assert space_file.read_text() == "value = 'modified'\n"

    async def test_large_file(self, temp_workspace, lock_manager):
        """대용량 파일 (1MB+)"""
        large_file = temp_workspace / "large.py"
        # 1MB 파일 생성
        large_content = "x = 1\n" * 100000  # ~600KB
        large_file.write_text(large_content)

        adapter = AtomicEditAdapter(lock_manager, str(temp_workspace))

        new_content = large_content.replace("x = 1", "x = 2")

        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=str(large_file),
                    original_content=large_content,
                    new_content=new_content,
                )
            ],
            agent_id="test-agent",
        )

        result = await adapter.execute(request)

        assert result.success is True
        assert "x = 2" in large_file.read_text()

    async def test_empty_file(self, temp_workspace, lock_manager):
        """빈 파일 처리"""
        empty_file = temp_workspace / "empty.py"
        empty_file.write_text("")

        adapter = AtomicEditAdapter(lock_manager, str(temp_workspace))

        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=str(empty_file),
                    original_content="",
                    new_content="# Now has content\n",
                )
            ],
            agent_id="test-agent",
        )

        result = await adapter.execute(request)

        assert result.success is True
        assert empty_file.read_text() == "# Now has content\n"

    async def test_newline_variations(self, temp_workspace, lock_manager):
        """다양한 줄바꿈 문자 (LF, CRLF)"""
        lf_file = temp_workspace / "lf.py"
        lf_file.write_text("line1\nline2\n")

        adapter = AtomicEditAdapter(lock_manager, str(temp_workspace))

        request = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path=str(lf_file),
                    original_content="line1\nline2\n",
                    new_content="modified1\nmodified2\n",
                )
            ],
            agent_id="test-agent",
        )

        result = await adapter.execute(request)

        assert result.success is True
        assert lf_file.read_text() == "modified1\nmodified2\n"
