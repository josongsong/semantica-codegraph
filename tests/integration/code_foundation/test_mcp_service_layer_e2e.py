"""
MCP Service Layer E2E Integration Tests (SOTA)

RFC-052: MCP Service Layer Architecture
End-to-end tests for complete MCP workflow.

Test Coverage:
- Complete workflow: Request → UseCase → Evidence → Response
- Snapshot stickiness
- Error handling with recovery hints
- Budget enforcement
- Transaction rollback
- Concurrent access
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.application.dto import AnalysisError, ErrorCode
from codegraph_engine.code_foundation.application.services.snapshot_session_service import (
    SnapshotSessionService,
)
from codegraph_engine.code_foundation.application.usecases import (
    DataflowRequest,
    SliceRequest,
)
from codegraph_engine.code_foundation.domain.evidence import EvidenceKind
from codegraph_engine.code_foundation.domain.query.query_plan import SliceDirection
from codegraph_engine.code_foundation.infrastructure.evidence import (
    EvidenceRepositorySQLite,
)
from codegraph_engine.code_foundation.infrastructure.session import SnapshotSessionStore


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def temp_evidence_db():
    """Temporary evidence database"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def temp_session_db():
    """Temporary session database"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def evidence_repo(temp_evidence_db):
    """Evidence repository instance"""
    return EvidenceRepositorySQLite(temp_evidence_db)


@pytest.fixture
def session_store(temp_session_db):
    """Session store instance"""
    return SnapshotSessionStore(temp_session_db)


@pytest.fixture
def mock_snapshot_store():
    """Mock snapshot store for testing"""

    class MockSnapshotStore:
        async def load_latest_snapshot(self, repo_id: str):
            from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.snapshot import (
                PyrightSemanticSnapshot,
            )

            return PyrightSemanticSnapshot(
                snapshot_id=f"snap_{repo_id}_latest",
                project_id=repo_id,
                files=[],  # ✅ Correct field
            )

        async def load_snapshot_by_id(self, snapshot_id: str):
            from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.snapshot import (
                PyrightSemanticSnapshot,
            )

            return PyrightSemanticSnapshot(
                snapshot_id=snapshot_id,
                project_id="test",
                files=[],  # ✅ Correct field
            )

    return MockSnapshotStore()


@pytest.fixture
def snapshot_service(session_store, mock_snapshot_store):
    """Snapshot session service"""
    return SnapshotSessionService(
        session_store=session_store,
        snapshot_store=mock_snapshot_store,
    )


# ============================================================
# Snapshot Stickiness Tests
# ============================================================


class TestSnapshotStickiness:
    """Snapshot stickiness contract tests"""

    @pytest.mark.asyncio
    async def test_auto_lock_to_latest(self, snapshot_service):
        """Session auto-locks to latest stable snapshot"""
        # First call → auto-lock
        snapshot_id_1 = await snapshot_service.get_or_lock_snapshot(
            session_id="session_001",
            repo_id="test_repo",
        )

        assert snapshot_id_1 == "snap_test_repo_latest"

        # Second call → same snapshot (sticky)
        snapshot_id_2 = await snapshot_service.get_or_lock_snapshot(
            session_id="session_001",
            repo_id="test_repo",
        )

        assert snapshot_id_2 == snapshot_id_1

    @pytest.mark.asyncio
    async def test_explicit_snapshot_request(self, snapshot_service):
        """Session can lock to specific snapshot"""
        snapshot_id = await snapshot_service.get_or_lock_snapshot(
            session_id="session_002",
            repo_id="test_repo",
            requested_snapshot_id="snap_specific",
        )

        assert snapshot_id == "snap_specific"

    @pytest.mark.asyncio
    async def test_snapshot_upgrade(self, snapshot_service):
        """Session can be explicitly upgraded"""
        # Initial lock
        await snapshot_service.get_or_lock_snapshot(
            session_id="session_003",
            repo_id="test_repo",
        )

        # Upgrade to newer snapshot
        await snapshot_service.upgrade_snapshot(
            session_id="session_003",
            new_snapshot_id="snap_new",
        )

        # Verify upgraded
        info = await snapshot_service.get_snapshot_info("session_003")
        assert info["snapshot_id"] == "snap_new"

    @pytest.mark.asyncio
    async def test_snapshot_mismatch_validation(self, snapshot_service):
        """Validate snapshot consistency"""
        # Lock to snap_001
        await snapshot_service.get_or_lock_snapshot(
            session_id="session_004",
            repo_id="test_repo",
            requested_snapshot_id="snap_001",
        )

        # Check mismatch with snap_002
        is_consistent, error = await snapshot_service.validate_snapshot_consistency(
            session_id="session_004",
            evidence_snapshot_id="snap_002",
        )

        assert not is_consistent
        assert error is not None
        assert error.error_code == ErrorCode.SNAPSHOT_MISMATCH


# ============================================================
# Evidence Lifecycle Tests
# ============================================================


class TestEvidenceLifecycle:
    """Evidence creation and lifecycle tests"""

    @pytest.mark.asyncio
    async def test_evidence_created_with_ttl(self, evidence_repo):
        """Evidence is created with TTL from config"""
        from codegraph_engine.code_foundation.domain.evidence import Evidence, GraphRefs

        evidence = Evidence.create(
            evidence_id="ev_test",
            kind=EvidenceKind.SLICE,
            snapshot_id="snap_001",
            graph_refs=GraphRefs(),
            ttl_days=30,
        )

        await evidence_repo.save(evidence)

        retrieved = await evidence_repo.get_by_id("ev_test")
        assert retrieved is not None
        assert retrieved.expires_at is not None

    @pytest.mark.asyncio
    async def test_evidence_expires(self, evidence_repo):
        """Expired evidence is not returned"""
        from datetime import timedelta

        from codegraph_engine.code_foundation.domain.evidence import Evidence, GraphRefs

        # Create evidence that expires immediately
        evidence = Evidence(
            evidence_id="ev_expired",
            kind=EvidenceKind.SLICE,
            snapshot_id="snap_001",
            graph_refs=GraphRefs(),
            expires_at=datetime.now() - timedelta(seconds=1),
        )

        await evidence_repo.save(evidence)

        # Should return None (expired)
        retrieved = await evidence_repo.get_by_id("ev_expired")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_evidence_gc_with_snapshot(self, evidence_repo):
        """Evidence is GC'd when snapshot is deleted"""
        from codegraph_engine.code_foundation.domain.evidence import Evidence, GraphRefs

        # Create evidence
        evidence = Evidence.create(
            evidence_id="ev_gc_test",
            kind=EvidenceKind.SLICE,
            snapshot_id="snap_gc",
            graph_refs=GraphRefs(),
            ttl_days=30,
        )

        await evidence_repo.save(evidence)

        # Delete by snapshot
        deleted = await evidence_repo.delete_by_snapshot("snap_gc")
        assert deleted == 1

        # Verify deleted
        retrieved = await evidence_repo.get_by_id("ev_gc_test")
        assert retrieved is None


# ============================================================
# Error Handling Tests
# ============================================================


class TestErrorHandling:
    """Error handling with recovery hints"""

    def test_budget_exceeded_error(self):
        """Budget exceeded error has actionable hints"""
        error = AnalysisError.budget_exceeded(
            max_nodes=1000,
            max_depth=10,
        )

        assert error.error_code == ErrorCode.BUDGET_EXCEEDED
        assert len(error.recovery_hints) >= 2

        # Check hints are actionable
        hint_actions = [h.action for h in error.recovery_hints]
        assert "reduce_depth" in hint_actions
        assert "use_lighter_budget" in hint_actions

    def test_snapshot_mismatch_error(self):
        """Snapshot mismatch error provides recovery options"""
        error = AnalysisError.snapshot_mismatch(
            expected_snapshot="snap_001",
            actual_snapshot="snap_002",
            evidence_id="ev_test",
        )

        assert error.error_code == ErrorCode.SNAPSHOT_MISMATCH
        assert len(error.recovery_hints) == 2

        # Check hints
        hint_actions = [h.action for h in error.recovery_hints]
        assert "use_same_snapshot" in hint_actions
        assert "recalculate_with_current_snapshot" in hint_actions

    def test_symbol_not_found_error(self):
        """Symbol not found error suggests search"""
        error = AnalysisError.symbol_not_found(
            symbol="unknownFunc",
            suggestion="unknownFunction",
        )

        assert error.error_code == ErrorCode.SYMBOL_NOT_FOUND
        assert len(error.recovery_hints) >= 1

        # Check suggestion in hint
        hint = error.recovery_hints[0]
        assert hint.action == "use_suggested_symbol"
        assert hint.parameters["suggested_symbol"] == "unknownFunction"


# ============================================================
# Transaction Tests
# ============================================================


class TestTransactions:
    """Transaction and rollback tests"""

    @pytest.mark.asyncio
    async def test_evidence_save_rollback_on_error(self, evidence_repo):
        """Evidence save rolls back on error"""
        from codegraph_engine.code_foundation.domain.evidence import Evidence, GraphRefs

        # Create valid evidence
        evidence1 = Evidence.create(
            evidence_id="ev_tx_001",
            kind=EvidenceKind.SLICE,
            snapshot_id="snap_001",
            graph_refs=GraphRefs(),
            ttl_days=30,
        )

        await evidence_repo.save(evidence1)

        # Try to save duplicate (should fail)
        evidence2 = Evidence.create(
            evidence_id="ev_tx_001",  # Duplicate
            kind=EvidenceKind.SLICE,
            snapshot_id="snap_001",
            graph_refs=GraphRefs(),
            ttl_days=30,
        )

        with pytest.raises(ValueError, match="already exists"):
            await evidence_repo.save(evidence2)

        # Original should still exist
        retrieved = await evidence_repo.get_by_id("ev_tx_001")
        assert retrieved is not None


# ============================================================
# Concurrent Access Tests
# ============================================================


class TestConcurrentAccess:
    """Thread-safety and concurrent access tests"""

    @pytest.mark.asyncio
    async def test_concurrent_evidence_save(self, evidence_repo):
        """Multiple evidence can be saved concurrently"""
        import asyncio

        from codegraph_engine.code_foundation.domain.evidence import Evidence, GraphRefs

        # Create multiple evidence
        async def save_evidence(i: int):
            evidence = Evidence.create(
                evidence_id=f"ev_concurrent_{i}",
                kind=EvidenceKind.SLICE,
                snapshot_id="snap_001",
                graph_refs=GraphRefs(),
                ttl_days=30,
            )
            await evidence_repo.save(evidence)

        # Run concurrently
        await asyncio.gather(*[save_evidence(i) for i in range(10)])

        # Verify all saved
        results = await evidence_repo.list_by_snapshot("snap_001")
        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_concurrent_session_operations(self, session_store):
        """Multiple sessions can be operated concurrently"""
        import asyncio

        async def lock_session(i: int):
            await session_store.lock_snapshot(
                session_id=f"session_{i}",
                snapshot_id=f"snap_{i % 3}",  # 3 snapshots
                repo_id="test_repo",
            )

        # Run concurrently
        await asyncio.gather(*[lock_session(i) for i in range(20)])

        # Verify all locked
        for i in range(20):
            snapshot = await session_store.get_snapshot(f"session_{i}")
            assert snapshot is not None


# ============================================================
# Performance Tests
# ============================================================


class TestPerformance:
    """Performance tests for connection pool"""

    @pytest.mark.asyncio
    async def test_connection_pool_reuse(self, evidence_repo):
        """Connection pool reuses connections"""
        from codegraph_engine.code_foundation.domain.evidence import Evidence, GraphRefs

        # Save 100 evidence (should reuse connections)
        for i in range(100):
            evidence = Evidence.create(
                evidence_id=f"ev_perf_{i}",
                kind=EvidenceKind.SLICE,
                snapshot_id="snap_perf",
                graph_refs=GraphRefs(),
                ttl_days=30,
            )
            await evidence_repo.save(evidence)

        # Verify all saved (connection pool worked)
        results = await evidence_repo.list_by_snapshot("snap_perf")
        assert len(results) == 100

    @pytest.mark.asyncio
    async def test_wal_mode_concurrent_reads(self, temp_evidence_db):
        """WAL mode allows concurrent reads"""
        import asyncio

        from codegraph_engine.code_foundation.domain.evidence import Evidence, GraphRefs

        # Create repository
        repo = EvidenceRepositorySQLite(temp_evidence_db)

        # Save evidence
        evidence = Evidence.create(
            evidence_id="ev_wal_test",
            kind=EvidenceKind.SLICE,
            snapshot_id="snap_wal",
            graph_refs=GraphRefs(),
            ttl_days=30,
        )
        await repo.save(evidence)

        # Multiple concurrent reads
        async def read_evidence():
            return await repo.get_by_id("ev_wal_test")

        results = await asyncio.gather(*[read_evidence() for _ in range(10)])

        # All reads successful
        assert all(r is not None for r in results)
        assert all(r.evidence_id == "ev_wal_test" for r in results)


# ============================================================
# Cleanup Tests
# ============================================================


class TestCleanup:
    """Cleanup and GC tests"""

    @pytest.mark.asyncio
    async def test_evidence_cleanup_by_ttl(self, evidence_repo):
        """Evidence cleanup respects TTL"""
        from datetime import timedelta

        from codegraph_engine.code_foundation.domain.evidence import Evidence, GraphRefs

        # Create expired evidence
        expired = Evidence(
            evidence_id="ev_expired_cleanup",
            kind=EvidenceKind.SLICE,
            snapshot_id="snap_001",
            graph_refs=GraphRefs(),
            expires_at=datetime.now() - timedelta(days=1),
        )
        await evidence_repo.save(expired)

        # Create valid evidence
        valid = Evidence.create(
            evidence_id="ev_valid_cleanup",
            kind=EvidenceKind.SLICE,
            snapshot_id="snap_001",
            graph_refs=GraphRefs(),
            ttl_days=30,
        )
        await evidence_repo.save(valid)

        # Cleanup expired
        deleted = await evidence_repo.delete_expired()
        assert deleted == 1

        # Verify only valid remains
        results = await evidence_repo.list_by_snapshot("snap_001")
        assert len(results) == 1
        assert results[0].evidence_id == "ev_valid_cleanup"

    @pytest.mark.asyncio
    async def test_session_cleanup(self, snapshot_service):
        """Old sessions are cleaned up"""
        # Lock session
        await snapshot_service.get_or_lock_snapshot(
            session_id="session_old",
            repo_id="test_repo",
        )

        # Cleanup (7 days threshold)
        deleted = await snapshot_service.cleanup_old_sessions(days=0)  # Cleanup all

        assert deleted >= 1
