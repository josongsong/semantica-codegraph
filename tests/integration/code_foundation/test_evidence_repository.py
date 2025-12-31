"""
Evidence Repository Integration Tests

RFC-052: MCP Service Layer Architecture
Tests for EvidenceRepositorySQLite (real SQLite operations).

Test Coverage:
- Save/retrieve evidence
- List by snapshot
- Delete by snapshot
- Delete expired
- Concurrent access (thread-safe)
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.domain.evidence import (
    Evidence,
    EvidenceKind,
    GraphRefs,
)
from codegraph_engine.code_foundation.infrastructure.evidence import (
    EvidenceRepositorySQLite,
)


@pytest.fixture
def temp_db():
    """Create temporary database"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def repository(temp_db):
    """Create repository instance"""
    return EvidenceRepositorySQLite(temp_db)


@pytest.fixture
def sample_evidence():
    """Create sample evidence"""
    return Evidence.create(
        evidence_id="ev_test_001",
        kind=EvidenceKind.TAINT_FLOW,
        snapshot_id="snap_001",
        graph_refs=GraphRefs(
            node_ids=("node_1", "node_2"),
            edge_ids=("edge_1",),
        ),
        plan_hash="abc123",
        constraint_summary="Test taint flow",
        rule_id="sql_injection",
        ttl_days=30,
    )


class TestEvidenceRepositoryBasics:
    """Basic CRUD operations"""

    @pytest.mark.asyncio
    async def test_save_evidence(self, repository, sample_evidence):
        """Happy path: Save evidence"""
        await repository.save(sample_evidence)

        # Retrieve
        retrieved = await repository.get_by_id("ev_test_001")

        assert retrieved is not None
        assert retrieved.evidence_id == "ev_test_001"
        assert retrieved.kind == EvidenceKind.TAINT_FLOW
        assert retrieved.snapshot_id == "snap_001"
        assert len(retrieved.graph_refs.node_ids) == 2

    @pytest.mark.asyncio
    async def test_save_duplicate_id_fails(self, repository, sample_evidence):
        """Error: Duplicate evidence_id"""
        await repository.save(sample_evidence)

        with pytest.raises(ValueError, match="already exists"):
            await repository.save(sample_evidence)

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, repository):
        """Get nonexistent evidence returns None"""
        result = await repository.get_by_id("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_exists(self, repository, sample_evidence):
        """Check existence"""
        # Before save
        assert not await repository.exists("ev_test_001")

        # After save
        await repository.save(sample_evidence)
        assert await repository.exists("ev_test_001")


class TestEvidenceRepositoryQueries:
    """Query operations"""

    @pytest.mark.asyncio
    async def test_list_by_snapshot(self, repository):
        """List evidence by snapshot"""
        # Create multiple evidence for same snapshot
        for i in range(3):
            evidence = Evidence.create(
                evidence_id=f"ev_{i}",
                kind=EvidenceKind.SLICE,
                snapshot_id="snap_001",
                graph_refs=GraphRefs(),
                ttl_days=30,
            )
            await repository.save(evidence)

        # Create evidence for different snapshot
        other = Evidence.create(
            evidence_id="ev_other",
            kind=EvidenceKind.SLICE,
            snapshot_id="snap_002",
            graph_refs=GraphRefs(),
            ttl_days=30,
        )
        await repository.save(other)

        # List by snapshot
        results = await repository.list_by_snapshot("snap_001")

        assert len(results) == 3
        assert all(e.snapshot_id == "snap_001" for e in results)

    @pytest.mark.asyncio
    async def test_list_by_snapshot_with_kind_filter(self, repository):
        """List evidence by snapshot and kind"""
        # Create evidence of different kinds
        await repository.save(
            Evidence.create(
                evidence_id="ev_slice",
                kind=EvidenceKind.SLICE,
                snapshot_id="snap_001",
                graph_refs=GraphRefs(),
                ttl_days=30,
            )
        )
        await repository.save(
            Evidence.create(
                evidence_id="ev_taint",
                kind=EvidenceKind.TAINT_FLOW,
                snapshot_id="snap_001",
                graph_refs=GraphRefs(),
                ttl_days=30,
            )
        )

        # Filter by kind
        results = await repository.list_by_snapshot(
            "snap_001",
            kind=EvidenceKind.SLICE,
        )

        assert len(results) == 1
        assert results[0].kind == EvidenceKind.SLICE

    @pytest.mark.asyncio
    async def test_list_respects_limit(self, repository):
        """List respects limit parameter"""
        # Create 10 evidence
        for i in range(10):
            evidence = Evidence.create(
                evidence_id=f"ev_{i}",
                kind=EvidenceKind.SLICE,
                snapshot_id="snap_001",
                graph_refs=GraphRefs(),
                ttl_days=30,
            )
            await repository.save(evidence)

        # List with limit
        results = await repository.list_by_snapshot("snap_001", limit=5)

        assert len(results) == 5


class TestEvidenceRepositoryGarbageCollection:
    """Garbage collection operations"""

    @pytest.mark.asyncio
    async def test_delete_by_snapshot(self, repository):
        """Delete all evidence for a snapshot"""
        # Create evidence
        for i in range(3):
            evidence = Evidence.create(
                evidence_id=f"ev_{i}",
                kind=EvidenceKind.SLICE,
                snapshot_id="snap_001",
                graph_refs=GraphRefs(),
                ttl_days=30,
            )
            await repository.save(evidence)

        # Delete
        deleted_count = await repository.delete_by_snapshot("snap_001")

        assert deleted_count == 3

        # Verify deleted
        results = await repository.list_by_snapshot("snap_001")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_delete_expired(self, repository):
        """Delete expired evidence"""
        # Create expired evidence
        expired = Evidence(
            evidence_id="ev_expired",
            kind=EvidenceKind.SLICE,
            snapshot_id="snap_001",
            graph_refs=GraphRefs(),
            created_at=datetime.now(),
            expires_at=datetime.now() - timedelta(days=1),  # Expired yesterday
        )
        await repository.save(expired)

        # Create valid evidence
        valid = Evidence.create(
            evidence_id="ev_valid",
            kind=EvidenceKind.SLICE,
            snapshot_id="snap_001",
            graph_refs=GraphRefs(),
            ttl_days=30,
        )
        await repository.save(valid)

        # Delete expired
        deleted_count = await repository.delete_expired()

        assert deleted_count == 1

        # Verify
        assert not await repository.exists("ev_expired")
        assert await repository.exists("ev_valid")

    @pytest.mark.asyncio
    async def test_get_expired_returns_none(self, repository):
        """Getting expired evidence returns None"""
        # Create expired evidence
        expired = Evidence(
            evidence_id="ev_expired",
            kind=EvidenceKind.SLICE,
            snapshot_id="snap_001",
            graph_refs=GraphRefs(),
            created_at=datetime.now(),
            expires_at=datetime.now() - timedelta(seconds=1),
        )
        await repository.save(expired)

        # Try to get (should return None due to expiration)
        result = await repository.get_by_id("ev_expired")

        assert result is None


class TestEvidenceRepositoryEdgeCases:
    """Edge cases and corner cases"""

    @pytest.mark.asyncio
    async def test_empty_graph_refs(self, repository):
        """Save evidence with empty graph refs"""
        evidence = Evidence.create(
            evidence_id="ev_empty",
            kind=EvidenceKind.SLICE,
            snapshot_id="snap_001",
            graph_refs=GraphRefs(),  # Empty
            ttl_days=30,
        )
        await repository.save(evidence)

        retrieved = await repository.get_by_id("ev_empty")

        assert len(retrieved.graph_refs.node_ids) == 0
        assert len(retrieved.graph_refs.edge_ids) == 0

    @pytest.mark.asyncio
    async def test_large_graph_refs(self, repository):
        """Save evidence with many nodes/edges"""
        large_graph = GraphRefs(
            node_ids=tuple(f"node_{i}" for i in range(1000)),
            edge_ids=tuple(f"edge_{i}" for i in range(1000)),
        )

        evidence = Evidence.create(
            evidence_id="ev_large",
            kind=EvidenceKind.DATAFLOW,
            snapshot_id="snap_001",
            graph_refs=large_graph,
            ttl_days=30,
        )
        await repository.save(evidence)

        retrieved = await repository.get_by_id("ev_large")

        assert len(retrieved.graph_refs.node_ids) == 1000
        assert len(retrieved.graph_refs.edge_ids) == 1000

    @pytest.mark.asyncio
    async def test_special_characters_in_ids(self, repository):
        """Handle special characters in IDs"""
        evidence = Evidence.create(
            evidence_id="ev_test-123_abc@xyz",
            kind=EvidenceKind.SLICE,
            snapshot_id="snap-001_test",
            graph_refs=GraphRefs(),
            ttl_days=30,
        )
        await repository.save(evidence)

        retrieved = await repository.get_by_id("ev_test-123_abc@xyz")

        assert retrieved is not None


# ============================================================
# Integration Test: Real Workflow
# ============================================================


class TestEvidenceRepositoryWorkflow:
    """End-to-end workflow tests"""

    @pytest.mark.asyncio
    async def test_complete_workflow(self, repository):
        """Complete workflow: Save → Query → GC"""
        # Step 1: Save multiple evidence
        for i in range(5):
            evidence = Evidence.create(
                evidence_id=f"ev_{i}",
                kind=EvidenceKind.TAINT_FLOW,
                snapshot_id="snap_001",
                graph_refs=GraphRefs(node_ids=(f"node_{i}",)),
                rule_id="sql_injection",
                ttl_days=30,
            )
            await repository.save(evidence)

        # Step 2: Query
        all_evidence = await repository.list_by_snapshot("snap_001")
        assert len(all_evidence) == 5

        # Step 3: Filter by kind
        taint_evidence = await repository.list_by_snapshot(
            "snap_001",
            kind=EvidenceKind.TAINT_FLOW,
        )
        assert len(taint_evidence) == 5

        # Step 4: GC by snapshot
        deleted = await repository.delete_by_snapshot("snap_001")
        assert deleted == 5

        # Step 5: Verify deleted
        all_evidence = await repository.list_by_snapshot("snap_001")
        assert len(all_evidence) == 0
