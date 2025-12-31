# PostgreSQL Storage - Quick Start Guide

**Status**: ✅ Production Ready
**Last Updated**: 2025-12-28

---

## 🚀 Quick Start (5 minutes)

### 1. Start PostgreSQL

```bash
# Using existing Docker container
docker start codegraph-postgres

# OR create new container
docker run -d -p 5432:5432 \
  --name codegraph-postgres \
  -e POSTGRES_DB=codegraph \
  -e POSTGRES_USER=codegraph \
  -e POSTGRES_PASSWORD=codegraph_dev \
  postgres:15
```

### 2. Set Database URL

```bash
export DATABASE_URL="postgres://codegraph:codegraph_dev@localhost:5432/codegraph"
```

### 3. Run Migrations

```bash
cd codegraph-ir
sqlx migrate run
```

### 4. Build & Test

```bash
# Build
cargo build --release

# Run tests
cargo test --test test_postgres_edge_cases -- --ignored --test-threads=1
```

### 5. Use in Code

```rust
use codegraph_ir::features::storage::{PostgresChunkStore, Chunk, ChunkStore};

#[tokio::main]
async fn main() -> Result<()> {
    let database_url = "postgres://codegraph:codegraph_dev@localhost:5432/codegraph";
    let store = PostgresChunkStore::new(database_url).await?;

    // Save a chunk
    let chunk = Chunk { /* ... */ };
    store.save_chunk(&chunk).await?;

    // Query chunks
    let chunks = store.get_chunks("repo_id", "snapshot_id").await?;

    Ok(())
}
```

---

## 📋 Common Commands

### Docker Management

```bash
# Start
docker start codegraph-postgres

# Stop
docker stop codegraph-postgres

# View logs
docker logs codegraph-postgres -f

# Connect with psql
docker exec -it codegraph-postgres psql -U codegraph -d codegraph
```

### Database Operations

```bash
# Check connection
psql $DATABASE_URL -c "SELECT version();"

# List tables
psql $DATABASE_URL -c "\dt"

# View indexes
psql $DATABASE_URL -c "\di"

# Count chunks
psql $DATABASE_URL -c "SELECT COUNT(*) FROM chunks WHERE is_deleted = FALSE;"
```

### Build & Test

```bash
# Quick check
cargo check

# Full build
cargo build --release

# Run edge case tests
DATABASE_URL="postgres://..." \
  cargo test --test test_postgres_edge_cases -- --ignored --test-threads=1

# Run specific test
cargo test test_edge_case_unicode_content -- --ignored --exact
```

---

## 🔍 Troubleshooting

### "DATABASE_URL not set"

```bash
export DATABASE_URL="postgres://codegraph:codegraph_dev@localhost:5432/codegraph"
```

### "Connection refused"

```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Start if not running
docker start codegraph-postgres
```

### "Migration failed"

```bash
# Check migrations directory
ls -la migrations/

# Re-run migrations
sqlx migrate run --source migrations
```

### "Tests fail with FK violations"

```bash
# Run sequentially (required)
cargo test -- --test-threads=1
```

---

## 📊 Performance Benchmarks

| Operation | Performance | Command |
|-----------|-------------|---------|
| Single chunk insert | 2-5ms | `store.save_chunk(&chunk).await?` |
| Batch insert (100) | ~10ms | `store.save_chunks(&chunks).await?` |
| Batch insert (1000) | ~350ms | See test_performance_large_batch |
| Full-text search | <5ms | `store.search_content(query, 50).await?` |
| Transitive deps | <15ms | `store.get_transitive_dependencies(id, 10).await?` |

---

## 🗂️ Schema Overview

### Tables (5)

1. **repositories** - Git repositories
2. **snapshots** - Commit/branch snapshots
3. **chunks** - Code chunks (main table)
4. **dependencies** - Dependency graph
5. **file_metadata** - Incremental updates

### Key Indexes (22 total)

- `idx_chunks_content_fts` - GIN full-text search
- `idx_chunks_fqn` - FQN lookup
- `idx_chunks_file` - File-based queries
- `idx_deps_from` / `idx_deps_to` - Graph traversal
- `idx_deps_unique` - Prevent duplicate edges

---

## 🧪 Test Coverage

### Edge Cases (4)
- ✅ Empty strings
- ✅ Unicode (Chinese, Japanese, emoji)
- ✅ Boundary values (2 billion lines)
- ✅ Large content (1MB)

### Corner Cases (6)
- ✅ All optional fields None
- ✅ UPSERT reviving deleted chunks
- ✅ Circular dependencies
- ✅ Concurrent writes (10 parallel)
- ✅ Batch duplicates
- ✅ Complex nested JSONB

### Performance (1)
- ✅ 1000 chunks in 350ms

**Total**: 12/12 tests passed ✅

---

## 📚 Documentation

- [POSTGRES_MIGRATION_COMPLETE.md](./POSTGRES_MIGRATION_COMPLETE.md) - Full migration report
- [POSTGRES_EDGE_CASE_TEST_REPORT.md](./POSTGRES_EDGE_CASE_TEST_REPORT.md) - Test results
- [POSTGRESQL_MIGRATION_VERIFICATION.md](./POSTGRESQL_MIGRATION_VERIFICATION.md) - Implementation verification
- [migrations/20250101000001_initial_schema.sql](./migrations/20250101000001_initial_schema.sql) - Schema definition

---

## 🎯 Quick Reference

### Environment Variables

```bash
# Development
export DATABASE_URL="postgres://codegraph:codegraph_dev@localhost:5432/codegraph"

# Test
export DATABASE_URL="postgres://codegraph:codegraph_dev@localhost:7201/codegraph_rfc074_test"

# Production
export DATABASE_URL="postgres://codegraph:codegraph_prod@prod-host:5432/codegraph"
```

### Connection Pooling

Default settings (in PostgresChunkStore::new):
- Max connections: 20
- Min connections: 2
- Acquire timeout: 5 seconds
- Idle timeout: 600 seconds
- Max lifetime: 1800 seconds

### Type Mappings

| Rust | PostgreSQL | Notes |
|------|------------|-------|
| `String` | TEXT | Direct |
| `u32` | INTEGER | Cast to i32 on write |
| `i32` | INTEGER | Cast to u32 on read |
| `f32` | REAL | Direct |
| `bool` | BOOLEAN | Direct |
| `DateTime<Utc>` | TIMESTAMP WITH TIME ZONE | chrono |
| `HashMap<String, JsonValue>` | JSONB | serde_json |

---

## ✅ Production Checklist

- [x] PostgreSQL 15+ installed
- [x] DATABASE_URL configured
- [x] Migrations applied
- [x] Build successful
- [x] Tests passing (12/12)
- [x] Connection pool configured
- [x] Indexes created
- [x] Foreign keys enforced
- [ ] Monitoring setup (pg_stat_*)
- [ ] Backups configured (pg_dump)

---

**Questions?** See detailed documentation in:
- [POSTGRES_MIGRATION_COMPLETE.md](./POSTGRES_MIGRATION_COMPLETE.md)
- [POSTGRES_EDGE_CASE_TEST_REPORT.md](./POSTGRES_EDGE_CASE_TEST_REPORT.md)
