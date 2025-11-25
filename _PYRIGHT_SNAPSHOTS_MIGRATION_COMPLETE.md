# Pyright Snapshots Migration Complete ✅

**Date**: 2025-11-25
**RFC**: RFC-023 M1 (Milestone 1)
**Status**: Database Schema Ready

---

## Summary

Successfully created database schema for **Pyright Semantic Snapshot Storage**.

This is **Milestone 1** of RFC-023 (Pyright LSP Integration), enabling persistent storage of Pyright's semantic analysis results.

---

## What Was Done

### 1. Created Migration Files ✅

Created up/down migration pair for Pyright snapshots:

| File | Purpose |
|------|---------|
| [`migrations/005_create_pyright_snapshots.up.sql`](migrations/005_create_pyright_snapshots.up.sql) | Create table and indexes |
| [`migrations/005_create_pyright_snapshots.down.sql`](migrations/005_create_pyright_snapshots.down.sql) | Rollback schema changes |

### 2. Applied Migrations ✅

Applied all pending migrations to PostgreSQL (port 7201):

```
✓ Applied migration 001: create_fuzzy_index
✓ Applied migration 002: create_domain_index
✓ Applied migration 005: create_pyright_snapshots
```

### 3. Verified Schema ✅

**Table**: `pyright_semantic_snapshots`

**Columns**:
- `snapshot_id` (TEXT, PRIMARY KEY) - Unique snapshot identifier
- `project_id` (TEXT, NOT NULL) - Project/repository identifier
- `timestamp` (TIMESTAMP, NOT NULL) - Snapshot creation time
- `data` (JSONB, NOT NULL) - Semantic snapshot data (types, symbols, etc.)
- `created_at` (TIMESTAMP, NOT NULL) - Record creation timestamp

**Indexes**:
- `pyright_semantic_snapshots_pkey` - Primary key on snapshot_id
- `idx_snapshots_project_timestamp` - Fast project-based queries (timestamp DESC)
- `idx_snapshots_id` - Explicit snapshot_id index

---

## Database Connection

**Environment Variable**:
```bash
SEMANTICA_DATABASE_URL="postgresql://codegraph:codegraph_dev@localhost:7201/codegraph"
```

**Docker Compose Service**: `codegraph-postgres` (port 7201)

---

## Migration Status

```
Migration Status:
------------------------------------------------------------
001 ✓ Applied    create_fuzzy_index
002 ✓ Applied    create_domain_index
005 ✓ Applied    create_pyright_snapshots
------------------------------------------------------------
Total: 3 migrations, 3 applied
```

---

## Next Steps (RFC-023 M2-M4)

### Milestone 2: Pyright LSP Client ⏭️

**Goal**: Implement PyrightLSPClient for semantic analysis

**Components**:
```python
class PyrightLSPClient:
    async def start() -> None
    async def stop() -> None
    async def analyze_workspace() -> str  # Returns snapshot_id
    async def update_files(files: list, mode: str) -> None
    async def export_semantic(snapshot_id: str) -> PyrightSemanticSnapshot
```

**Files to Create**:
- `src/foundation/ir/external_analyzers/pyright_lsp_client.py`
- `src/foundation/ir/external_analyzers/pyright_types.py`

**Dependencies**:
- `pylsp` or `pyright` language server
- LSP protocol implementation (pygls?)

### Milestone 3: Snapshot Storage Service ⏭️

**Goal**: Implement SemanticSnapshotStore for CRUD operations

**Components**:
```python
class SemanticSnapshotStore:
    async def save_snapshot(snapshot: PyrightSemanticSnapshot) -> None
    async def load_latest_snapshot(project_id: str) -> PyrightSemanticSnapshot | None
    async def load_snapshot_by_id(snapshot_id: str) -> PyrightSemanticSnapshot | None
    async def list_snapshots(project_id: str, limit: int) -> list[dict]
    async def delete_old_snapshots(project_id: str, keep_count: int) -> int
```

**Files to Create**:
- `src/foundation/ir/external_analyzers/semantic_snapshot_store.py`

**Uses**: `pyright_semantic_snapshots` table (✅ created)

### Milestone 4: Integration ⏭️

**Goal**: Integrate Pyright into IndexingOrchestrator

**Changes**:
```python
class IndexingOrchestrator:
    async def index_repo_full(
        repo_id: str,
        files: list[Path],
        enable_pyright: bool = True,  # NEW
    ) -> dict
```

**Flow**:
1. Parse files → IR generation
2. **Run Pyright analysis** (if enabled)
3. **Store semantic snapshot**
4. Build graph (with Pyright types)
5. Index to Kuzu/Qdrant/Zoekt

---

## Decision Point: Real Infrastructure Ready ✅

### Status Check

| Component | Status | Notes |
|-----------|--------|-------|
| **Docker Compose** | ✅ Running | All services healthy |
| **Postgres** | ✅ Ready | Migrations applied |
| **Kuzu** | ✅ Verified | Symbol index works |
| **Qdrant** | ✅ Running | Needs OPENAI_API_KEY for embeddings |
| **Zoekt** | ✅ Running | Lexical search ready |
| **Pyright DB** | ✅ Ready | Schema created (this migration) |

### Recommendations

Based on [`_REAL_INFRASTRUCTURE_VERIFIED.md`](_REAL_INFRASTRUCTURE_VERIFIED.md):

**Option 1**: Accept Mock Results ✅ **SELECTED**
- Mock validated Fusion v2 (+9.6% NDCG vs v1)
- Real infrastructure ready for production
- Proceed with:
  1. ✅ Pyright schema (THIS MIGRATION)
  2. ⏭️ Implement Pyright LSP Client (M2)
  3. ⏭️ Deploy to production with real infrastructure

**Option 2**: Improve Real Search (Deferred)
- Target: Kuzu search 25% → 70% precision
- Effort: 2-3 days
- Can be done post-deployment with real usage data

---

## Commands Reference

### Migration Commands

```bash
# Set database URL
export SEMANTICA_DATABASE_URL="postgresql://codegraph:codegraph_dev@localhost:7201/codegraph"

# Check status
python migrations/migrate.py status

# Apply all pending
python migrations/migrate.py up

# Rollback last
python migrations/migrate.py down

# Rollback to version
python migrations/migrate.py down --to 002
```

### Verify Table

```bash
python -c "
import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect('$SEMANTICA_DATABASE_URL')
    result = await conn.fetch('SELECT * FROM pyright_semantic_snapshots LIMIT 1')
    print(f'Table exists: {len(result) >= 0}')
    await conn.close()

asyncio.run(check())
"
```

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [`_RFC023_IMPLEMENTATION_PLAN.md`](_RFC023_IMPLEMENTATION_PLAN.md) | Full RFC-023 implementation plan |
| [`_REAL_INFRASTRUCTURE_VERIFIED.md`](_REAL_INFRASTRUCTURE_VERIFIED.md) | Real infrastructure verification |
| [`_COMPREHENSIVE_BENCHMARK_SUMMARY.md`](_COMPREHENSIVE_BENCHMARK_SUMMARY.md) | Retriever benchmark (41 scenarios) |
| [`_MOCK_VS_REAL_INFRASTRUCTURE.md`](_MOCK_VS_REAL_INFRASTRUCTURE.md) | Mock vs Real comparison |

---

## Completion Summary

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RFC-023 MILESTONE 1: DATABASE SCHEMA ✅
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Migration Files:   ✅ Created (up/down)
Migration Applied: ✅ Successfully applied
Table Created:     ✅ pyright_semantic_snapshots
Indexes Created:   ✅ 3 indexes (PRIMARY KEY + 2 custom)
Schema Verified:   ✅ All columns and types correct

Next Milestone:
  📋 M2: Implement PyrightLSPClient
  📋 M3: Implement SemanticSnapshotStore
  📋 M4: Integrate with IndexingOrchestrator

Status: Ready for M2 implementation ⏭️

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Date**: 2025-11-25
**Status**: RFC-023 M1 Complete ✅
**Next**: Implement Pyright LSP Client (M2)
