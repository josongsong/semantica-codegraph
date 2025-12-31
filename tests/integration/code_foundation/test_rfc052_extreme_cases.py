"""
RFC-052 Extreme Edge Cases (L11 SOTA)

Tests for extreme scenarios that could break in production:
- Massive concurrent load
- Memory pressure
- Disk full
- Corrupt data
- Unicode/special characters
- Timezone edge cases
- Resource exhaustion
"""

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.domain.evidence import Evidence, EvidenceKind, GraphRefs
from codegraph_engine.code_foundation.domain.query.query_plan import Budget, slice_plan
from codegraph_engine.code_foundation.infrastructure.evidence import EvidenceRepositorySQLite
from codegraph_engine.code_foundation.infrastructure.query.query_plan_cache import QueryPlanCache
from codegraph_engine.code_foundation.infrastructure.session import SnapshotSessionStore


# ============================================================
# Extreme Concurrency Tests
# ============================================================


class TestExtremeConcurrency:
    """Extreme concurrent load tests"""

    @pytest.mark.asyncio
    async def test_1000_concurrent_evidence_saves(self):
        """Extreme: 1000 concurrent saves"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = EvidenceRepositorySQLite(Path(tmpdir) / "evidence.db", pool_size=10)

            async def save_evidence(i: int):
                evidence = Evidence.create(
                    evidence_id=f"ev_extreme_{i}",
                    kind=EvidenceKind.SLICE,
                    snapshot_id="snap_extreme",
                    graph_refs=GraphRefs(),
                    ttl_days=30,
                )
                await repo.save(evidence)

            # 1000 concurrent operations
            start = asyncio.get_event_loop().time()
            await asyncio.gather(*[save_evidence(i) for i in range(1000)])
            elapsed = asyncio.get_event_loop().time() - start

            # Should complete in reasonable time (< 30s even with 1000)
            assert elapsed < 30.0

            # Verify all saved
            results = await repo.list_by_snapshot("snap_extreme", limit=1000)
            assert len(results) == 1000

            repo.close()

    @pytest.mark.asyncio
    async def test_concurrent_read_write_no_deadlock(self):
        """Extreme: Concurrent reads and writes (no deadlock)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = EvidenceRepositorySQLite(Path(tmpdir) / "evidence.db", pool_size=5)

            # Seed data
            for i in range(10):
                evidence = Evidence.create(
                    evidence_id=f"ev_rw_{i}",
                    kind=EvidenceKind.SLICE,
                    snapshot_id="snap_rw",
                    graph_refs=GraphRefs(),
                    ttl_days=30,
                )
                await repo.save(evidence)

            # Concurrent reads and writes
            async def read_task():
                for _ in range(100):
                    await repo.get_by_id("ev_rw_5")

            async def write_task(i):
                evidence = Evidence.create(
                    evidence_id=f"ev_rw_new_{i}",
                    kind=EvidenceKind.DATAFLOW,
                    snapshot_id="snap_rw",
                    graph_refs=GraphRefs(),
                    ttl_days=30,
                )
                await repo.save(evidence)

            # Mix reads and writes
            tasks = [read_task() for _ in range(10)] + [write_task(i) for i in range(10)]

            # Should not deadlock
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=10.0)

            repo.close()


# ============================================================
# Memory Pressure Tests
# ============================================================


class TestMemoryPressure:
    """Memory pressure and limits"""

    def test_cache_bounded_memory(self):
        """Cache respects size limit under memory pressure"""
        cache = QueryPlanCache(max_size=100)

        # Add 1000 plans (10x limit)
        for i in range(1000):
            plan = slice_plan(f"func{i}")
            cache.put(f"snap_{i % 10}", plan, {"large_data": "x" * 1000})

        # Cache should be bounded
        assert cache.get_stats()["size"] <= 100

    @pytest.mark.asyncio
    async def test_large_graph_refs(self):
        """Large graph refs don't cause issues"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = EvidenceRepositorySQLite(Path(tmpdir) / "evidence.db")

            # Extreme: 10,000 nodes
            large_graph = GraphRefs(
                node_ids=tuple(f"node_{i}" for i in range(10000)),
                edge_ids=tuple(f"edge_{i}" for i in range(10000)),
            )

            evidence = Evidence.create(
                evidence_id="ev_large_extreme",
                kind=EvidenceKind.DATAFLOW,
                snapshot_id="snap_large",
                graph_refs=large_graph,
                ttl_days=30,
            )

            await repo.save(evidence)
            retrieved = await repo.get_by_id("ev_large_extreme")

            assert len(retrieved.graph_refs.node_ids) == 10000

            repo.close()


# ============================================================
# Data Corruption Tests
# ============================================================


class TestDataCorruption:
    """Data corruption and recovery"""

    @pytest.mark.asyncio
    async def test_corrupted_graph_refs_json(self):
        """Corrupted graph_refs JSON is handled"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = EvidenceRepositorySQLite(Path(tmpdir) / "evidence.db")

            # Save valid evidence
            evidence = Evidence.create(
                evidence_id="ev_valid",
                kind=EvidenceKind.SLICE,
                snapshot_id="snap_corrupt",
                graph_refs=GraphRefs(node_ids=("n1",)),
                ttl_days=30,
            )
            await repo.save(evidence)

            # Manually corrupt the data
            import sqlite3

            with sqlite3.connect(Path(tmpdir) / "evidence.db") as conn:
                conn.execute(
                    "UPDATE evidence_ledger SET graph_refs = ? WHERE evidence_id = ?",
                    ("{invalid json", "ev_valid"),
                )
                conn.commit()

            # Should raise (not silently fail)
            with pytest.raises(Exception):  # JSON decode error
                await repo.get_by_id("ev_valid")

            repo.close()


# ============================================================
# Unicode & Special Characters
# ============================================================


class TestUnicodeHandling:
    """Unicode and special character handling"""

    @pytest.mark.asyncio
    async def test_unicode_in_ids(self):
        """Unicode in IDs is handled"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = EvidenceRepositorySQLite(Path(tmpdir) / "evidence.db")

            evidence = Evidence.create(
                evidence_id="ev_한글_test_🔥",
                kind=EvidenceKind.SLICE,
                snapshot_id="snap_unicode_テスト",
                graph_refs=GraphRefs(),
                ttl_days=30,
            )

            await repo.save(evidence)
            retrieved = await repo.get_by_id("ev_한글_test_🔥")

            assert retrieved is not None
            assert retrieved.snapshot_id == "snap_unicode_テスト"

            repo.close()

    @pytest.mark.asyncio
    async def test_sql_injection_attempt(self):
        """SQL injection attempts are prevented"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = EvidenceRepositorySQLite(Path(tmpdir) / "evidence.db")

            # Try SQL injection in evidence_id
            malicious_id = "ev_test'; DROP TABLE evidence_ledger; --"

            evidence = Evidence.create(
                evidence_id=malicious_id,
                kind=EvidenceKind.SLICE,
                snapshot_id="snap_injection",
                graph_refs=GraphRefs(),
                ttl_days=30,
            )

            await repo.save(evidence)

            # Verify table still exists
            retrieved = await repo.get_by_id(malicious_id)
            assert retrieved is not None  # Table not dropped

            # Verify table structure intact
            results = await repo.list_by_snapshot("snap_injection")
            assert len(results) == 1

            repo.close()


# ============================================================
# Time-based Edge Cases
# ============================================================


class TestTimezoneEdgeCases:
    """Timezone and time-based edge cases"""

    @pytest.mark.asyncio
    async def test_evidence_expires_exactly_at_boundary(self):
        """Evidence expiration at exact boundary"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = EvidenceRepositorySQLite(Path(tmpdir) / "evidence.db")

            # Expires in 1 second
            evidence = Evidence(
                evidence_id="ev_boundary",
                kind=EvidenceKind.SLICE,
                snapshot_id="snap_time",
                graph_refs=GraphRefs(),
                expires_at=datetime.now() + timedelta(seconds=1),
            )

            await repo.save(evidence)

            # Should be valid now
            retrieved = await repo.get_by_id("ev_boundary")
            assert retrieved is not None

            # Wait for expiration
            await asyncio.sleep(1.1)

            # Should be expired
            expired = await repo.get_by_id("ev_boundary")
            assert expired is None

            repo.close()


# ============================================================
# Resource Exhaustion Tests
# ============================================================


class TestResourceExhaustion:
    """Resource exhaustion scenarios"""

    def test_cache_under_extreme_churn(self):
        """Cache performs well under extreme churn"""
        cache = QueryPlanCache(max_size=10)

        # Add 10,000 plans (1000x limit)
        for i in range(10000):
            plan = slice_plan(f"func{i}")
            cache.put(f"snap_{i % 100}", plan, f"data{i}")

        # Cache should remain bounded
        assert cache.get_stats()["size"] <= 10

        # LRU should still work
        latest_plan = slice_plan("func9999")
        cached = cache.get("snap_99", latest_plan)
        assert cached is not None  # Most recent should be cached

    @pytest.mark.asyncio
    async def test_pool_exhaustion_recovery(self):
        """Pool exhaustion is handled gracefully"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = EvidenceRepositorySQLite(Path(tmpdir) / "evidence.db", pool_size=2)  # Small pool

            # More concurrent ops than pool size
            async def save_evidence(i):
                evidence = Evidence.create(
                    evidence_id=f"ev_exhaust_{i}",
                    kind=EvidenceKind.SLICE,
                    snapshot_id="snap_exhaust",
                    graph_refs=GraphRefs(),
                    ttl_days=30,
                )
                await repo.save(evidence)

            # 20 concurrent (10x pool size)
            await asyncio.gather(*[save_evidence(i) for i in range(20)])

            # All should succeed (pool creates temp connections)
            results = await repo.list_by_snapshot("snap_exhaust", limit=25)
            assert len(results) == 20

            repo.close()


# ============================================================
# Budget Edge Cases
# ============================================================


class TestBudgetEdgeCases:
    """Budget extreme values"""

    def test_zero_budget(self):
        """Zero budget is handled"""
        budget = Budget(
            max_nodes=0,
            max_edges=0,
            max_paths=0,
            max_depth=0,
            timeout_ms=0,
        )

        # Should not crash (validation at executor level)
        assert budget.max_nodes == 0

    def test_extreme_budget(self):
        """Extreme budget values"""
        budget = Budget(
            max_nodes=1000000,  # 1M nodes
            max_edges=10000000,  # 10M edges
            max_paths=100000,  # 100K paths
            max_depth=1000,  # 1000 depth
            timeout_ms=3600000,  # 1 hour
        )

        assert budget.max_nodes == 1000000


# ============================================================
# QueryPlan Hash Collision Test
# ============================================================


class TestHashCollision:
    """Hash collision resistance"""

    def test_no_collision_in_100k_plans(self):
        """No hash collisions in 100K plans"""
        from codegraph_engine.code_foundation.domain.query.query_plan import dataflow_plan

        hashes = set()

        for i in range(100000):
            plan = dataflow_plan(f"source_{i}", f"sink_{i % 1000}")
            hash_value = plan.compute_hash()

            # No collision
            assert hash_value not in hashes
            hashes.add(hash_value)

        # All unique
        assert len(hashes) == 100000
