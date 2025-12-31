"""
Atomic Edit Domain Models Unit Tests

/ss Rule 3 준수:
✅ Happy path
✅ Invalid input (type mismatch, nullable violation)
✅ Boundary / Edge Case
✅ 모든 validation 검증
"""

from datetime import datetime

import pytest

from apps.orchestrator.orchestrator.domain.code_editing.atomic_edit import (
    AtomicEditRequest,
    AtomicEditResult,
    ConflictInfo,
    ConflictType,
    FileEdit,
    IsolationLevel,
    RollbackInfo,
    TransactionState,
)

# ============================================================================
# FileEdit Tests
# ============================================================================


class TestFileEdit:
    """FileEdit 테스트"""

    def test_happy_path_basic(self):
        """Happy path: 기본 편집"""
        edit = FileEdit(
            file_path="/test/main.py",
            original_content="x = 1",
            new_content="x = 2",
        )
        assert edit.file_path == "/test/main.py"
        assert edit.original_content == "x = 1"
        assert edit.new_content == "x = 2"
        assert edit.expected_hash is not None  # auto-computed

    def test_happy_path_with_explicit_hash(self):
        """Happy path: 명시적 해시"""
        edit = FileEdit(
            file_path="/test/main.py",
            original_content="x = 1",
            new_content="x = 2",
            expected_hash="abcd1234",
        )
        assert edit.expected_hash == "abcd1234"

    def test_file_path_empty_fails(self):
        """Invalid: file_path 비어있음"""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            FileEdit(
                file_path="",
                original_content="x = 1",
                new_content="x = 2",
            )

    def test_no_changes_fails(self):
        """Invalid: original == new (변경 없음)"""
        with pytest.raises(ValueError, match="No changes detected"):
            FileEdit(
                file_path="/test/main.py",
                original_content="x = 1",
                new_content="x = 1",  # 동일
            )

    def test_content_hash_property(self):
        """Property: content_hash"""
        edit = FileEdit(
            file_path="/test/main.py",
            original_content="hello world",
            new_content="hello world!",
        )
        assert len(edit.content_hash) == 16  # SHA256 첫 16자

    def test_verify_hash_success(self):
        """Method: verify_hash (성공)"""
        edit = FileEdit(
            file_path="/test/main.py",
            original_content="x = 1",
            new_content="x = 2",
        )
        # 같은 내용이면 해시 일치
        assert edit.verify_hash("x = 1") is True

    def test_verify_hash_failure(self):
        """Method: verify_hash (실패)"""
        edit = FileEdit(
            file_path="/test/main.py",
            original_content="x = 1",
            new_content="x = 2",
        )
        # 다른 내용이면 해시 불일치
        assert edit.verify_hash("x = 999") is False


# ============================================================================
# ConflictInfo Tests
# ============================================================================


class TestConflictInfo:
    """ConflictInfo 테스트"""

    def test_happy_path_hash_mismatch(self):
        """Happy path: HASH_MISMATCH"""
        conflict = ConflictInfo(
            file_path="/test/main.py",
            conflict_type=ConflictType.HASH_MISMATCH,
            expected_hash="abc123",
            actual_hash="def456",
            message="File was modified",
        )
        assert conflict.conflict_type == ConflictType.HASH_MISMATCH
        assert conflict.expected_hash == "abc123"
        assert conflict.actual_hash == "def456"

    def test_happy_path_lock_held(self):
        """Happy path: LOCK_HELD"""
        conflict = ConflictInfo(
            file_path="/test/main.py",
            conflict_type=ConflictType.LOCK_HELD,
            locked_by="agent-123",
            message="File is locked",
        )
        assert conflict.conflict_type == ConflictType.LOCK_HELD
        assert conflict.locked_by == "agent-123"

    def test_happy_path_file_deleted(self):
        """Happy path: FILE_DELETED"""
        conflict = ConflictInfo(
            file_path="/test/main.py",
            conflict_type=ConflictType.FILE_DELETED,
            message="File was deleted",
        )
        assert conflict.conflict_type == ConflictType.FILE_DELETED

    def test_file_path_empty_fails(self):
        """Invalid: file_path 비어있음"""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            ConflictInfo(
                file_path="",
                conflict_type=ConflictType.HASH_MISMATCH,
            )

    def test_conflict_type_invalid_type_fails(self):
        """Invalid: conflict_type이 ConflictType이 아님"""
        with pytest.raises(TypeError, match="conflict_type must be ConflictType"):
            ConflictInfo(
                file_path="/test/main.py",
                conflict_type="hash_mismatch",  # type: ignore
            )

    def test_hash_mismatch_without_hashes_fails(self):
        """Invalid: HASH_MISMATCH인데 해시 없음"""
        with pytest.raises(ValueError, match="expected_hash and actual_hash required"):
            ConflictInfo(
                file_path="/test/main.py",
                conflict_type=ConflictType.HASH_MISMATCH,
                # 해시 누락
            )

    def test_lock_held_without_locked_by_fails(self):
        """Invalid: LOCK_HELD인데 locked_by 없음"""
        with pytest.raises(ValueError, match="locked_by cannot be empty"):
            ConflictInfo(
                file_path="/test/main.py",
                conflict_type=ConflictType.LOCK_HELD,
                # locked_by 누락
            )

    def test_is_resolvable_hash_mismatch(self):
        """Property: is_resolvable (HASH_MISMATCH)"""
        conflict = ConflictInfo(
            file_path="/test/main.py",
            conflict_type=ConflictType.HASH_MISMATCH,
            expected_hash="abc",
            actual_hash="def",
        )
        assert conflict.is_resolvable is True

    def test_is_resolvable_lock_held(self):
        """Property: is_resolvable (LOCK_HELD)"""
        conflict = ConflictInfo(
            file_path="/test/main.py",
            conflict_type=ConflictType.LOCK_HELD,
            locked_by="agent-1",
        )
        assert conflict.is_resolvable is True

    def test_is_resolvable_file_deleted(self):
        """Property: is_resolvable (FILE_DELETED)"""
        conflict = ConflictInfo(
            file_path="/test/main.py",
            conflict_type=ConflictType.FILE_DELETED,
        )
        assert conflict.is_resolvable is False


# ============================================================================
# AtomicEditRequest Tests
# ============================================================================


class TestAtomicEditRequest:
    """AtomicEditRequest 테스트"""

    def test_happy_path_single_file(self):
        """Happy path: 단일 파일"""
        req = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path="/test/main.py",
                    original_content="x = 1",
                    new_content="x = 2",
                ),
            ],
        )
        assert len(req.edits) == 1
        assert req.isolation_level == IsolationLevel.READ_COMMITTED  # default
        assert req.dry_run is False  # default
        assert req.timeout_seconds == 30.0  # default
        assert req.agent_id == "default"  # default

    def test_happy_path_multi_file(self):
        """Happy path: 다중 파일"""
        req = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path="/test/main.py",
                    original_content="x = 1",
                    new_content="x = 2",
                ),
                FileEdit(
                    file_path="/test/util.py",
                    original_content="y = 1",
                    new_content="y = 2",
                ),
            ],
            isolation_level=IsolationLevel.SERIALIZABLE,
            timeout_seconds=60.0,
            agent_id="agent-123",
        )
        assert len(req.edits) == 2
        assert req.isolation_level == IsolationLevel.SERIALIZABLE
        assert req.timeout_seconds == 60.0
        assert req.agent_id == "agent-123"

    def test_edits_empty_fails(self):
        """Invalid: edits 비어있음"""
        with pytest.raises(ValueError, match="edits cannot be empty"):
            AtomicEditRequest(edits=[])

    def test_timeout_boundary_very_small(self):
        """Boundary: timeout = 0.001 (매우 작음)"""
        req = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path="/test/main.py",
                    original_content="x = 1",
                    new_content="x = 2",
                ),
            ],
            timeout_seconds=0.001,
        )
        assert req.timeout_seconds == 0.001

    def test_timeout_invalid_zero(self):
        """Invalid: timeout = 0"""
        with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
            AtomicEditRequest(
                edits=[
                    FileEdit(
                        file_path="/test/main.py",
                        original_content="x = 1",
                        new_content="x = 2",
                    ),
                ],
                timeout_seconds=0,
            )

    def test_timeout_invalid_negative(self):
        """Invalid: timeout < 0"""
        with pytest.raises(ValueError, match="timeout_seconds must be > 0"):
            AtomicEditRequest(
                edits=[
                    FileEdit(
                        file_path="/test/main.py",
                        original_content="x = 1",
                        new_content="x = 2",
                    ),
                ],
                timeout_seconds=-10.0,
            )

    def test_agent_id_empty_fails(self):
        """Invalid: agent_id 비어있음"""
        with pytest.raises(ValueError, match="agent_id cannot be empty"):
            AtomicEditRequest(
                edits=[
                    FileEdit(
                        file_path="/test/main.py",
                        original_content="x = 1",
                        new_content="x = 2",
                    ),
                ],
                agent_id="",
            )

    def test_duplicate_file_paths_fails(self):
        """Invalid: 중복 파일 경로"""
        with pytest.raises(ValueError, match="Duplicate file paths"):
            AtomicEditRequest(
                edits=[
                    FileEdit(
                        file_path="/test/main.py",
                        original_content="x = 1",
                        new_content="x = 2",
                    ),
                    FileEdit(
                        file_path="/test/main.py",  # 중복!
                        original_content="x = 2",
                        new_content="x = 3",
                    ),
                ],
            )

    def test_file_count_property(self):
        """Property: file_count"""
        req = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path="/test/a.py",
                    original_content="a = 1",
                    new_content="a = 2",
                ),
                FileEdit(
                    file_path="/test/b.py",
                    original_content="b = 1",
                    new_content="b = 2",
                ),
            ],
        )
        assert req.file_count == 2

    def test_is_multi_file_true(self):
        """Property: is_multi_file = True"""
        req = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path="/test/a.py",
                    original_content="a = 1",
                    new_content="a = 2",
                ),
                FileEdit(
                    file_path="/test/b.py",
                    original_content="b = 1",
                    new_content="b = 2",
                ),
            ],
        )
        assert req.is_multi_file is True

    def test_is_multi_file_false(self):
        """Property: is_multi_file = False"""
        req = AtomicEditRequest(
            edits=[
                FileEdit(
                    file_path="/test/main.py",
                    original_content="x = 1",
                    new_content="x = 2",
                ),
            ],
        )
        assert req.is_multi_file is False


# ============================================================================
# RollbackInfo Tests
# ============================================================================


class TestRollbackInfo:
    """RollbackInfo 테스트"""

    def test_happy_path(self):
        """Happy path: 기본 Rollback"""
        rollback = RollbackInfo(
            rollback_id="rollback-123",
            original_state={
                "/test/main.py": "x = 1",
                "/test/util.py": "y = 1",
            },
            timestamp=datetime.now(),
            reason="Hash mismatch detected",
        )
        assert rollback.rollback_id == "rollback-123"
        assert len(rollback.original_state) == 2
        assert rollback.reason == "Hash mismatch detected"

    def test_rollback_id_empty_fails(self):
        """Invalid: rollback_id 비어있음"""
        with pytest.raises(ValueError, match="rollback_id cannot be empty"):
            RollbackInfo(
                rollback_id="",
                original_state={"/test/main.py": "x = 1"},
                timestamp=datetime.now(),
                reason="Test",
            )

    def test_original_state_empty_fails(self):
        """Invalid: original_state 비어있음"""
        with pytest.raises(ValueError, match="original_state cannot be empty"):
            RollbackInfo(
                rollback_id="rollback-123",
                original_state={},
                timestamp=datetime.now(),
                reason="Test",
            )

    def test_reason_empty_fails(self):
        """Invalid: reason 비어있음"""
        with pytest.raises(ValueError, match="reason cannot be empty"):
            RollbackInfo(
                rollback_id="rollback-123",
                original_state={"/test/main.py": "x = 1"},
                timestamp=datetime.now(),
                reason="",
            )

    def test_file_count_property(self):
        """Property: file_count"""
        rollback = RollbackInfo(
            rollback_id="rollback-123",
            original_state={
                "/test/a.py": "a = 1",
                "/test/b.py": "b = 1",
                "/test/c.py": "c = 1",
            },
            timestamp=datetime.now(),
            reason="Test",
        )
        assert rollback.file_count == 3


# ============================================================================
# AtomicEditResult Tests
# ============================================================================


class TestAtomicEditResult:
    """AtomicEditResult 테스트"""

    def test_happy_path_success(self):
        """Happy path: 성공"""
        result = AtomicEditResult(
            success=True,
            transaction_state=TransactionState.COMMITTED,
            committed_files=["/test/main.py"],
            execution_time_ms=100.0,
        )
        assert result.success is True
        assert result.transaction_state == TransactionState.COMMITTED
        assert len(result.committed_files) == 1
        assert result.conflicts == []
        assert result.rollback_info is None
        assert result.errors == []

    def test_happy_path_failure_with_conflicts(self):
        """Happy path: 실패 (충돌)"""
        result = AtomicEditResult(
            success=False,
            transaction_state=TransactionState.ROLLED_BACK,
            committed_files=[],
            conflicts=[
                ConflictInfo(
                    file_path="/test/main.py",
                    conflict_type=ConflictType.HASH_MISMATCH,
                    expected_hash="abc",
                    actual_hash="def",
                ),
            ],
            rollback_info=RollbackInfo(
                rollback_id="rollback-123",
                original_state={"/test/main.py": "x = 1"},
                timestamp=datetime.now(),
                reason="Hash mismatch",
            ),
            errors=["Hash mismatch in /test/main.py"],
            execution_time_ms=50.0,
        )
        assert result.success is False
        assert result.transaction_state == TransactionState.ROLLED_BACK
        assert result.has_conflicts is True
        assert result.rollback_info is not None

    def test_execution_time_boundary_zero(self):
        """Boundary: execution_time_ms = 0"""
        result = AtomicEditResult(
            success=True,
            transaction_state=TransactionState.COMMITTED,
            committed_files=["/test/main.py"],
            execution_time_ms=0,
        )
        assert result.execution_time_ms == 0

    def test_execution_time_invalid_negative(self):
        """Invalid: execution_time_ms < 0"""
        with pytest.raises(ValueError, match="execution_time_ms must be >= 0"):
            AtomicEditResult(
                success=True,
                transaction_state=TransactionState.COMMITTED,
                committed_files=["/test/main.py"],
                execution_time_ms=-10.0,
            )

    def test_success_but_not_committed_fails(self):
        """Invalid: success=True인데 state != COMMITTED"""
        with pytest.raises(ValueError, match="success=True requires COMMITTED state"):
            AtomicEditResult(
                success=True,
                transaction_state=TransactionState.PENDING,
                committed_files=["/test/main.py"],
                execution_time_ms=100.0,
            )

    def test_failure_without_errors_fails(self):
        """Invalid: success=False인데 errors 없음"""
        with pytest.raises(ValueError, match="errors must be provided when success is False"):
            AtomicEditResult(
                success=False,
                transaction_state=TransactionState.FAILED,
                committed_files=[],
                errors=[],
                execution_time_ms=100.0,
            )

    def test_rolled_back_without_rollback_info_fails(self):
        """Invalid: ROLLED_BACK인데 rollback_info 없음"""
        with pytest.raises(ValueError, match="rollback_info required for ROLLED_BACK"):
            AtomicEditResult(
                success=False,
                transaction_state=TransactionState.ROLLED_BACK,
                committed_files=[],
                errors=["Failed"],
                execution_time_ms=100.0,
                # rollback_info 누락
            )

    def test_has_conflicts_true(self):
        """Property: has_conflicts = True"""
        result = AtomicEditResult(
            success=False,
            transaction_state=TransactionState.ROLLED_BACK,
            committed_files=[],
            conflicts=[
                ConflictInfo(
                    file_path="/test/main.py",
                    conflict_type=ConflictType.HASH_MISMATCH,
                    expected_hash="abc",
                    actual_hash="def",
                ),
            ],
            rollback_info=RollbackInfo(
                rollback_id="rollback-123",
                original_state={"/test/main.py": "x = 1"},
                timestamp=datetime.now(),
                reason="Test",
            ),
            errors=["Conflict"],
            execution_time_ms=100.0,
        )
        assert result.has_conflicts is True

    def test_has_conflicts_false(self):
        """Property: has_conflicts = False"""
        result = AtomicEditResult(
            success=True,
            transaction_state=TransactionState.COMMITTED,
            committed_files=["/test/main.py"],
            execution_time_ms=100.0,
        )
        assert result.has_conflicts is False

    def test_total_files_committed_property(self):
        """Property: total_files_committed"""
        result = AtomicEditResult(
            success=True,
            transaction_state=TransactionState.COMMITTED,
            committed_files=["/test/a.py", "/test/b.py", "/test/c.py"],
            execution_time_ms=100.0,
        )
        assert result.total_files_committed == 3
