#!/usr/bin/env python3
"""
RFC-023 M1: Snapshot Persistence Example

Demonstrates:
1. Parse Python code to AST
2. Extract locations from IR (simulated)
3. Create PyrightSemanticSnapshot with typing info
4. Save snapshot to PostgreSQL
5. Load snapshot from PostgreSQL
6. Query type information

This shows the complete M1 flow with database persistence.

Requirements:
- PostgreSQL running on port 7201
- Migration 005 applied

Run:
    SEMANTICA_DATABASE_URL="postgresql://codegraph:codegraph_dev@localhost:7201/codegraph" python examples/m1_snapshot_persistence_example.py
"""

import asyncio
import os
import time

from src.foundation.ir.external_analyzers import (
    PyrightSemanticSnapshot,
    SemanticSnapshotStore,
    Span,
)
from src.infra.storage.postgres import PostgresStore

# ============================================================
# Example Code
# ============================================================

EXAMPLE_CODE = """
from typing import List, Dict, Optional

class User:
    \"\"\"User model.\"\"\"

    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age

    def greet(self) -> str:
        return f"Hello, I'm {self.name}!"

def create_user(name: str, age: int) -> User:
    \"\"\"Create a new user.\"\"\"
    return User(name, age)

def get_users() -> List[User]:
    \"\"\"Get all users.\"\"\"
    return [
        User("Alice", 30),
        User("Bob", 25),
    ]

# Module-level variables
users: List[User] = get_users()
active_users: Optional[List[User]] = None
user_ages: Dict[str, int] = {"Alice": 30, "Bob": 25}
"""


# ============================================================
# Main Example
# ============================================================


async def main():
    print("=" * 80)
    print("RFC-023 M1: Snapshot Persistence Example")
    print("=" * 80)
    print()

    # Get database URL
    database_url = os.getenv(
        "SEMANTICA_DATABASE_URL",
        "postgresql://codegraph:codegraph_dev@localhost:7201/codegraph",
    )

    print(f"Database: {database_url}")
    print()

    # ========================================
    # Step 1: Initialize PostgreSQL Store
    # ========================================
    print("Step 1: Initializing PostgreSQL connection...")
    start = time.perf_counter()

    postgres_store = PostgresStore(connection_string=database_url)
    await postgres_store.initialize()

    init_time = (time.perf_counter() - start) * 1000
    print(f"  ✓ Connected in {init_time:.2f}ms")
    print()

    # ========================================
    # Step 2: Create SemanticSnapshotStore
    # ========================================
    print("Step 2: Creating SemanticSnapshotStore...")

    snapshot_store = SemanticSnapshotStore(postgres_store)

    print("  ✓ Store ready")
    print()

    # ========================================
    # Step 3: Create Semantic Snapshot
    # ========================================
    print("Step 3: Creating semantic snapshot...")
    start = time.perf_counter()

    # In real scenario, this would come from Pyright Daemon
    # For this example, we'll simulate the typing info
    snapshot = PyrightSemanticSnapshot(
        snapshot_id=f"snapshot-{int(time.time())}",
        project_id="semantica-codegraph",
        files=["example.py"],
    )

    # Simulate type information (as if from Pyright)
    # In real flow: daemon.export_semantic_for_locations() would populate this
    type_annotations = [
        # class User
        ("example.py", Span(4, 6, 4, 10), "type[User]"),
        # def __init__
        ("example.py", Span(7, 8, 7, 16), "(self: User, name: str, age: int) -> None"),
        # def greet
        ("example.py", Span(11, 8, 11, 13), "(self: User) -> str"),
        # def create_user
        ("example.py", Span(14, 4, 14, 15), "(name: str, age: int) -> User"),
        # def get_users
        ("example.py", Span(18, 4, 18, 13), "() -> List[User]"),
        # users variable
        ("example.py", Span(25, 0, 25, 5), "List[User]"),
        # active_users variable
        ("example.py", Span(26, 0, 26, 12), "Optional[List[User]]"),
        # user_ages variable
        ("example.py", Span(27, 0, 27, 9), "Dict[str, int]"),
    ]

    for file_path, span, type_str in type_annotations:
        snapshot.add_type_info(file_path, span, type_str)

    create_time = (time.perf_counter() - start) * 1000
    print(f"  ✓ Created snapshot with {len(snapshot.typing_info)} type annotations")
    print(f"  ✓ Snapshot ID: {snapshot.snapshot_id}")
    print(f"  ✓ Creation time: {create_time:.2f}ms")
    print()

    # ========================================
    # Step 4: Save Snapshot to PostgreSQL
    # ========================================
    print("Step 4: Saving snapshot to PostgreSQL...")
    start = time.perf_counter()

    await snapshot_store.save_snapshot(snapshot)

    save_time = (time.perf_counter() - start) * 1000
    print(f"  ✓ Saved to database in {save_time:.2f}ms")
    print()

    # ========================================
    # Step 5: Load Latest Snapshot
    # ========================================
    print("Step 5: Loading latest snapshot from PostgreSQL...")
    start = time.perf_counter()

    loaded_snapshot = await snapshot_store.load_latest_snapshot("semantica-codegraph")

    load_time = (time.perf_counter() - start) * 1000

    if loaded_snapshot:
        print(f"  ✓ Loaded snapshot: {loaded_snapshot.snapshot_id}")
        print(f"  ✓ Files: {loaded_snapshot.files}")
        print(f"  ✓ Type annotations: {len(loaded_snapshot.typing_info)}")
        print(f"  ✓ Load time: {load_time:.2f}ms")
    else:
        print("  ✗ No snapshot found")
        return
    print()

    # ========================================
    # Step 6: Query Type Information
    # ========================================
    print("Step 6: Querying type information...")
    print()

    # Query some specific locations
    queries = [
        ("example.py", Span(4, 6, 4, 10), "User class"),
        ("example.py", Span(14, 4, 14, 15), "create_user function"),
        ("example.py", Span(18, 4, 18, 13), "get_users function"),
        ("example.py", Span(25, 0, 25, 5), "users variable"),
        ("example.py", Span(26, 0, 26, 12), "active_users variable"),
        ("example.py", Span(27, 0, 27, 9), "user_ages variable"),
    ]

    for file_path, span, description in queries:
        type_str = loaded_snapshot.get_type_at(file_path, span)
        if type_str:
            print(f"  {description:25s} → {type_str}")
        else:
            print(f"  {description:25s} → (not found)")

    print()

    # ========================================
    # Step 7: List All Snapshots
    # ========================================
    print("Step 7: Listing all snapshots for project...")

    snapshots = await snapshot_store.list_snapshots("semantica-codegraph", limit=5)

    print(f"  ✓ Found {len(snapshots)} snapshot(s)")
    for snap in snapshots:
        print(f"    - {snap['snapshot_id']} (created: {snap['created_at']})")
    print()

    # ========================================
    # Step 8: Demonstrate Cache
    # ========================================
    print("Step 8: Demonstrating cache performance...")

    # First load (cache miss)
    start = time.perf_counter()
    await snapshot_store.load_latest_snapshot("semantica-codegraph")
    first_load_time = (time.perf_counter() - start) * 1000

    # Second load (cache hit)
    start = time.perf_counter()
    await snapshot_store.load_latest_snapshot("semantica-codegraph")
    second_load_time = (time.perf_counter() - start) * 1000

    print(f"  First load (DB):    {first_load_time:.3f}ms")
    print(f"  Second load (cache): {second_load_time:.3f}ms")
    print(f"  Speedup: {first_load_time / second_load_time:.1f}x")
    print()

    # ========================================
    # Step 9: Load by Specific ID
    # ========================================
    print("Step 9: Loading snapshot by specific ID...")

    loaded_by_id = await snapshot_store.load_snapshot_by_id(snapshot.snapshot_id)

    if loaded_by_id:
        print(f"  ✓ Loaded: {loaded_by_id.snapshot_id}")
        print(f"  ✓ Project: {loaded_by_id.project_id}")
        print(f"  ✓ Type annotations: {len(loaded_by_id.typing_info)}")
    else:
        print("  ✗ Snapshot not found")
    print()

    # ========================================
    # Step 10: Cleanup Old Snapshots
    # ========================================
    print("Step 10: Demonstrating snapshot cleanup...")

    # Check current count
    before_count = len(
        await snapshot_store.list_snapshots("semantica-codegraph", limit=100)
    )
    print(f"  Snapshots before cleanup: {before_count}")

    # Keep only 3 most recent
    deleted_count = await snapshot_store.delete_old_snapshots(
        "semantica-codegraph", keep_count=3
    )
    print(f"  ✓ Deleted {deleted_count} old snapshot(s)")

    # Check after count
    after_count = len(
        await snapshot_store.list_snapshots("semantica-codegraph", limit=100)
    )
    print(f"  Snapshots after cleanup: {after_count}")
    print()

    # ========================================
    # Performance Summary
    # ========================================
    print("=" * 80)
    print("Performance Summary")
    print("=" * 80)
    print(f"  PostgreSQL Init:    {init_time:8.2f}ms")
    print(f"  Snapshot Creation:  {create_time:8.2f}ms")
    print(f"  Save to DB:         {save_time:8.2f}ms")
    print(f"  Load from DB:       {load_time:8.2f}ms")
    print(f"  Cache hit:          {second_load_time:8.2f}ms ({first_load_time / second_load_time:.1f}x faster)")
    print()

    total_time = init_time + create_time + save_time + load_time
    print(f"  Total workflow:     {total_time:8.2f}ms")
    print()

    # ========================================
    # Cleanup
    # ========================================
    await postgres_store.close()

    print("=" * 80)
    print("✅ M1 Example Complete!")
    print("=" * 80)
    print()
    print("What was demonstrated:")
    print("  1. PostgreSQL connection and pool management")
    print("  2. Semantic snapshot creation with type annotations")
    print("  3. Snapshot persistence to JSONB column")
    print("  4. Loading snapshots (latest and by ID)")
    print("  5. Listing snapshots for a project")
    print("  6. In-memory caching for performance")
    print("  7. Cleanup of old snapshots")
    print()
    print("Next steps (M2):")
    print("  - Incremental updates (compute_delta, merge_with)")
    print("  - Multi-file change tracking")
    print("  - Pyright Daemon integration")
    print()


if __name__ == "__main__":
    asyncio.run(main())
