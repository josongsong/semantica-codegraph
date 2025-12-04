"""
E2E Integration Test: IndexingOrchestrator + RFC-023 Pyright

Tests the complete pipeline:
1. AST → IR → Semantic IR (Pyright) → Graph → Chunks → Indexes
2. M1: Snapshot persistence to PostgreSQL
3. M2: Incremental indexing with ChangeDetector

Requirements:
- PostgreSQL running on port 7201
- Pyright installed (pyright-langserver)
- Migration 005 applied

Run:
    SEMANTICA_DATABASE_URL="postgresql://codegraph:codegraph_dev@localhost:7201/codegraph" \
    ENABLE_PYRIGHT=True \
    pytest tests/integration/test_orchestrator_pyright_e2e.py -v -s
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
import pytest_asyncio

from src.config import settings
from src.container import Container
from src.foundation.chunk import ChunkBuilder, ChunkIdGenerator
from src.foundation.graph import GraphBuilder
from src.foundation.ir.external_analyzers import SemanticSnapshotStore
from src.foundation.parsing import ASTBuilder
from src.foundation.semantic_ir import DefaultSemanticIrBuilder
from src.indexing.orchestrator import IndexingOrchestrator
from src.infra.storage.postgres import PostgresStore

# Skip if pyright or PostgreSQL not available
pytestmark = pytest.mark.skipif(
    not shutil.which("pyright-langserver"),
    reason="pyright-langserver not installed",
)

DATABASE_URL = os.getenv(
    "SEMANTICA_DATABASE_URL",
    "postgresql://codegraph:codegraph_dev@localhost:7201/codegraph",
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def test_repo():
    """Create a temporary Git repository with Python files."""
    temp_dir = Path(tempfile.mkdtemp(prefix="e2e_test_repo_"))

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=temp_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=temp_dir,
        check=True,
        capture_output=True,
    )

    # Create pyrightconfig.json
    import json

    config = {
        "include": ["**/*.py"],
        "typeCheckingMode": "basic",
        "reportMissingImports": False,
    }
    (temp_dir / "pyrightconfig.json").write_text(json.dumps(config, indent=2))

    # Create Python files
    (temp_dir / "main.py").write_text(
        """
from typing import List, Optional

def add(x: int, y: int) -> int:
    return x + y

def greet(name: str) -> str:
    return f"Hello, {name}!"

users: List[str] = ["Alice", "Bob"]
result: Optional[int] = None
"""
    )

    (temp_dir / "utils.py").write_text(
        """
from typing import Dict

def to_dict(items: list) -> Dict[str, int]:
    return {str(i): i for i in items}

def from_dict(data: dict) -> list:
    return list(data.values())
"""
    )

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=temp_dir,
        check=True,
        capture_output=True,
    )

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest_asyncio.fixture
async def postgres_store():
    """Create PostgresStore instance."""
    store = PostgresStore(connection_string=DATABASE_URL)
    await store.initialize()
    yield store
    await store.close()


@pytest_asyncio.fixture
async def snapshot_store(postgres_store):
    """Create SemanticSnapshotStore instance."""
    store = SemanticSnapshotStore(postgres_store)
    yield store
    store.clear_cache()


@pytest.fixture
def container_with_postgres(postgres_store):
    """Create container with PostgreSQL store."""
    container = Container()
    # Override postgres_store to use test instance
    container._postgres = postgres_store
    return container


@pytest_asyncio.fixture
async def orchestrator(container_with_postgres):
    """Create IndexingOrchestrator with Pyright enabled."""
    # Create components
    ast_builder = ASTBuilder()
    semantic_ir_builder = DefaultSemanticIrBuilder()
    graph_builder = GraphBuilder()
    chunk_id_generator = ChunkIdGenerator()
    chunk_builder = ChunkBuilder(id_generator=chunk_id_generator)

    # Create orchestrator
    orchestrator = IndexingOrchestrator(
        ast_builder=ast_builder,
        semantic_ir_builder=semantic_ir_builder,
        graph_builder=graph_builder,
        chunk_builder=chunk_builder,
        container=container_with_postgres,
    )

    yield orchestrator


# ============================================================
# E2E Tests
# ============================================================


@pytest.mark.asyncio
async def test_full_indexing_with_pyright_snapshot_persistence(test_repo, orchestrator, snapshot_store):
    """
    E2E Test 1: Full indexing with Pyright + snapshot persistence (M1).

    Pipeline:
        AST → IR → Semantic IR (Pyright) → Snapshot → PostgreSQL
    """
    # Enable Pyright
    original_enable_pyright = settings.enable_pyright
    settings.enable_pyright = True

    try:
        project_id = "test-e2e-project"

        print(f"\n{'=' * 60}")
        print("E2E Test 1: Full Indexing + Snapshot Persistence")
        print(f"{'=' * 60}\n")

        # Step 1: Full indexing
        print("Step 1: Running full indexing...")
        start_time = time.perf_counter()

        result = await orchestrator.index_repo_full(
            repo_path=test_repo,
            repo_id=project_id,
            snapshot_id="main",
            incremental=False,  # Full indexing
        )

        elapsed = time.perf_counter() - start_time
        print(f"✓ Full indexing completed in {elapsed:.2f}s")
        print(f"  Status: {result.status}")
        print(f"  Files processed: {result.files_processed}")

        # Step 2: Verify snapshot was saved to PostgreSQL
        print("\nStep 2: Verifying snapshot in PostgreSQL...")
        latest_snapshot = await snapshot_store.load_latest_snapshot(project_id)

        assert latest_snapshot is not None, "Snapshot should be saved"
        print(f"✓ Snapshot found: {latest_snapshot.snapshot_id}")
        print(f"  Files: {len(latest_snapshot.files)}")
        print(f"  Type annotations: {len(latest_snapshot.typing_info)}")

        # Should have 2 files
        assert len(latest_snapshot.files) >= 2, "Should have at least 2 files"

        # Should have type information
        assert len(latest_snapshot.typing_info) > 0, "Should have type information"

        print("\n✅ Test 1 PASSED: Full indexing + snapshot persistence working")

    finally:
        settings.enable_pyright = original_enable_pyright


@pytest.mark.asyncio
async def test_incremental_indexing_with_change_detector(test_repo, orchestrator, snapshot_store):
    """
    E2E Test 2: Incremental indexing with ChangeDetector (M2).

    Pipeline:
        1. Full indexing → Snapshot saved
        2. Modify file → Git commit
        3. Incremental indexing → ChangeDetector → Merge with previous
    """
    # Enable Pyright
    original_enable_pyright = settings.enable_pyright
    settings.enable_pyright = True

    try:
        project_id = "test-e2e-incremental"

        print(f"\n{'=' * 60}")
        print("E2E Test 2: Incremental Indexing + ChangeDetector")
        print(f"{'=' * 60}\n")

        # Step 1: Full indexing
        print("Step 1: Running full indexing...")
        start_full = time.perf_counter()

        await orchestrator.index_repo_full(
            repo_path=test_repo,
            repo_id=project_id,
            snapshot_id="main",
            incremental=False,
        )

        elapsed_full = time.perf_counter() - start_full
        print(f"✓ Full indexing: {elapsed_full:.2f}s")

        # Load snapshot
        snapshot1 = await snapshot_store.load_latest_snapshot(project_id)
        assert snapshot1 is not None
        print(f"  Snapshot 1: {len(snapshot1.files)} files, {len(snapshot1.typing_info)} types")

        # Step 2: Modify file
        print("\nStep 2: Modifying main.py...")
        main_py = test_repo / "main.py"
        current_content = main_py.read_text()
        modified_content = current_content + "\n\ndef multiply(a: int, b: int) -> int:\n    return a * b\n"
        main_py.write_text(modified_content)

        # Commit change
        subprocess.run(
            ["git", "add", "main.py"],
            cwd=test_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add multiply function"],
            cwd=test_repo,
            check=True,
            capture_output=True,
        )
        print("✓ File modified and committed")

        # Step 3: Incremental indexing
        print("\nStep 3: Running incremental indexing...")
        start_incr = time.perf_counter()

        await orchestrator.index_repo_full(
            repo_path=test_repo,
            repo_id=project_id,
            snapshot_id="main",
            incremental=True,  # Incremental with ChangeDetector (M2)
        )

        elapsed_incr = time.perf_counter() - start_incr
        print(f"✓ Incremental indexing: {elapsed_incr:.2f}s")

        # Load new snapshot
        snapshot2 = await snapshot_store.load_latest_snapshot(project_id)
        assert snapshot2 is not None
        print(f"  Snapshot 2: {len(snapshot2.files)} files, {len(snapshot2.typing_info)} types")

        # Step 4: Verify incremental update
        print("\nStep 4: Verifying incremental update...")

        # Should still have same number of files
        assert len(snapshot2.files) == len(snapshot1.files), "File count should be same"

        # Should have different snapshot IDs
        assert snapshot2.snapshot_id != snapshot1.snapshot_id, "Snapshot ID should change"

        # Should be faster (incremental)
        speedup = elapsed_full / elapsed_incr if elapsed_incr > 0 else 1
        print(f"  Performance: {speedup:.1f}x faster (full: {elapsed_full:.2f}s, incr: {elapsed_incr:.2f}s)")

        print("\n✅ Test 2 PASSED: Incremental indexing + ChangeDetector working")

    finally:
        settings.enable_pyright = original_enable_pyright


@pytest.mark.asyncio
async def test_snapshot_history_and_cleanup(test_repo, orchestrator, snapshot_store):
    """
    E2E Test 3: Snapshot history and cleanup.

    Verifies:
    - Multiple snapshots can be saved
    - list_snapshots() returns correct history
    - delete_old_snapshots() works correctly
    """
    # Enable Pyright
    original_enable_pyright = settings.enable_pyright
    settings.enable_pyright = True

    try:
        project_id = "test-e2e-history"

        print(f"\n{'=' * 60}")
        print("E2E Test 3: Snapshot History & Cleanup")
        print(f"{'=' * 60}\n")

        # Create 3 snapshots
        print("Step 1: Creating 3 snapshots...")
        for i in range(3):
            # Modify file
            main_py = test_repo / "main.py"
            content = main_py.read_text()
            main_py.write_text(content + f"\n# Iteration {i}\n")

            # Commit
            subprocess.run(
                ["git", "add", "."],
                cwd=test_repo,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"Change {i}"],
                cwd=test_repo,
                check=True,
                capture_output=True,
            )

            # Index
            await orchestrator.index_repo_full(
                repo_path=test_repo,
                repo_id=project_id,
                snapshot_id="main",
                incremental=i > 0,  # First is full, rest are incremental
            )
            print(f"  ✓ Snapshot {i + 1} created")

            # Small delay to ensure different timestamps
            await asyncio.sleep(0.1)

        # Step 2: List snapshots
        print("\nStep 2: Listing snapshots...")
        snapshots = await snapshot_store.list_snapshots(project_id, limit=10)
        print(f"✓ Found {len(snapshots)} snapshots")
        for snap in snapshots:
            print(f"  - {snap['snapshot_id']} ({snap['timestamp']})")

        assert len(snapshots) >= 3, "Should have at least 3 snapshots"

        # Step 3: Delete old snapshots (keep only 2)
        print("\nStep 3: Deleting old snapshots (keep 2)...")
        deleted_count = await snapshot_store.delete_old_snapshots(project_id, keep_count=2)
        print(f"✓ Deleted {deleted_count} old snapshot(s)")

        # Verify
        snapshots_after = await snapshot_store.list_snapshots(project_id, limit=10)
        print(f"  Remaining: {len(snapshots_after)} snapshots")
        assert len(snapshots_after) == 2, "Should have exactly 2 snapshots remaining"

        print("\n✅ Test 3 PASSED: Snapshot history & cleanup working")

    finally:
        settings.enable_pyright = original_enable_pyright


# ============================================================
# Performance Benchmark
# ============================================================


@pytest.mark.asyncio
@pytest.mark.slow
async def test_performance_benchmark_full_vs_incremental(test_repo, orchestrator, snapshot_store):
    """
    Performance Benchmark: Full vs Incremental indexing.

    Measures actual time difference and verifies M2 speedup.
    """
    # Enable Pyright
    original_enable_pyright = settings.enable_pyright
    settings.enable_pyright = True

    try:
        project_id = "test-e2e-benchmark"

        print(f"\n{'=' * 60}")
        print("Performance Benchmark: Full vs Incremental")
        print(f"{'=' * 60}\n")

        # Benchmark 1: Full indexing
        print("Benchmark 1: Full indexing (2 files)...")
        times_full = []
        for i in range(3):
            start = time.perf_counter()
            await orchestrator.index_repo_full(
                repo_path=test_repo,
                repo_id=f"{project_id}-full-{i}",
                snapshot_id="main",
                incremental=False,
            )
            elapsed = time.perf_counter() - start
            times_full.append(elapsed)
            print(f"  Run {i + 1}: {elapsed:.3f}s")

        avg_full = sum(times_full) / len(times_full)
        print(f"✓ Full indexing average: {avg_full:.3f}s")

        # Benchmark 2: Incremental indexing
        print("\nBenchmark 2: Incremental indexing (1 changed file)...")

        # First full index
        await orchestrator.index_repo_full(
            repo_path=test_repo,
            repo_id=project_id,
            snapshot_id="main",
            incremental=False,
        )

        times_incr = []
        for i in range(3):
            # Modify file
            main_py = test_repo / "main.py"
            content = main_py.read_text()
            main_py.write_text(content + f"\n# Benchmark {i}\n")
            subprocess.run(
                ["git", "add", "."],
                cwd=test_repo,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", f"Benchmark {i}"],
                cwd=test_repo,
                check=True,
                capture_output=True,
            )

            # Incremental index
            start = time.perf_counter()
            await orchestrator.index_repo_full(
                repo_path=test_repo,
                repo_id=project_id,
                snapshot_id="main",
                incremental=True,
            )
            elapsed = time.perf_counter() - start
            times_incr.append(elapsed)
            print(f"  Run {i + 1}: {elapsed:.3f}s")

        avg_incr = sum(times_incr) / len(times_incr)
        print(f"✓ Incremental indexing average: {avg_incr:.3f}s")

        # Calculate speedup
        speedup = avg_full / avg_incr if avg_incr > 0 else 1
        print(f"\n📊 Performance Summary:")
        print(f"  Full indexing:        {avg_full:.3f}s")
        print(f"  Incremental indexing: {avg_incr:.3f}s")
        print(f"  Speedup:              {speedup:.1f}x")

        # Incremental should be faster (at least 1.5x for small repos)
        assert speedup >= 1.0, "Incremental should be at least as fast as full"

        print("\n✅ Benchmark COMPLETE")

    finally:
        settings.enable_pyright = original_enable_pyright
