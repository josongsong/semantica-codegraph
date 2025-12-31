# RFC-100 Implementation Notes

**Status**: Storage module separated from `codegraph-ir`
**Date**: 2025-12-28
**Session**: Migration from codegraph-ir/src/features/storage

---

## Migration Summary

### What Was Moved
The initial storage implementation from `codegraph-ir/src/features/storage/` has been extracted into a separate workspace crate `codegraph-storage` to align with RFC-100 principles.

### Why Separated
1. **RFC-100 Scope**: Storage is a distinct concern (commit-based persistence) separate from IR analysis
2. **Backend Strategy**: SQLite (local) vs PostgreSQL (server) requires modular architecture
3. **Future RFCs**: RFC-101~105 will build on this foundation
4. **Clean Dependencies**: IR analysis should not depend on storage implementation details

### What Changed (RFC-100 Alignment)

#### Before (RFC-074 Design)
```rust
// Multi-snapshot with branch tracking
pub struct Snapshot {
    pub snapshot_id: SnapshotId,  // "repo-id:branch-name"
    pub repo_id: RepoId,
    pub commit_hash: Option<String>,  // Optional
    pub branch_name: Option<String>,  // Optional
}

// Soft delete for incremental updates
pub struct Chunk {
    pub is_deleted: bool,  // Mutable state
    // ...
}
```

#### After (RFC-100 Design)
```rust
// Commit-based immutable snapshots
pub struct Snapshot {
    pub id: CommitHash,  // Required: "abc123def"
    pub repo_id: RepoId,
    // NO branch_name - branches are pointers, not storage entities
}

// Immutable chunks (no soft delete)
pub struct Chunk {
    // NO is_deleted - snapshots are immutable
    // Deletion = create new snapshot without the chunk
}
```

### Key Design Changes

| Aspect | RFC-074 | RFC-100 |
|--------|---------|---------|
| **Snapshot ID** | `repo:branch` | `commit_hash` |
| **Mutability** | Soft delete (UPSERT) | Immutable |
| **Incremental** | Chunk-level UPSERT | File-level replace → new snapshot |
| **Branch Tracking** | Stored in DB | External (git pointers) |
| **Core Contract** | Chunk CRUD | `replace_file()` |

---

## Implementation Plan

### Phase 1: Domain Models (RFC-100)
- [ ] `Snapshot` (commit-based, immutable)
- [ ] `Chunk` (no soft delete)
- [ ] `Repository` (metadata only)
- [ ] `Dependency` (cross-chunk references)

### Phase 2: Port Definition (RFC-101)
- [ ] `CodeSnapshotStore` trait
- [ ] `replace_file()` API (core contract)
- [ ] `compare_snapshots()` API
- [ ] Transaction model

### Phase 3: SQLite Adapter (RFC-102)
- [ ] Schema design (immutable snapshots)
- [ ] `replace_file()` implementation
- [ ] Snapshot comparison queries
- [ ] Migration from old schema

### Phase 4: PostgreSQL Adapter (RFC-103)
- [ ] MVCC guarantees
- [ ] Multi-user access
- [ ] Connection pooling
- [ ] Performance optimization

### Phase 5: Snapshot Diff (RFC-104)
- [ ] Diff algorithm
- [ ] PR comparison API
- [ ] Semantic diff (not just text diff)

### Phase 6: Retention Policy (RFC-105)
- [ ] Snapshot lifecycle
- [ ] Garbage collection
- [ ] Storage limits

---

## Current Status

### Completed
- ✅ Workspace structure created
- ✅ Cargo.toml with feature flags
- ✅ README with RFC-100 principles
- ✅ This implementation notes document

### In Progress
- 🔄 Domain models redesign (removing mutable state)

### Pending
- ⏳ Port trait definition
- ⏳ SQLite adapter migration
- ⏳ Tests migration

---

## Design Rationale

### Why Immutable Snapshots?

**Problem with Soft Delete**:
```rust
// RFC-074 approach (mutable)
UPDATE chunks SET is_deleted = TRUE WHERE file_path = 'auth.py';
// Later...
INSERT INTO chunks (...) ON CONFLICT DO UPDATE SET is_deleted = FALSE;
```

**Issues**:
1. Snapshot state is mutable (not reproducible)
2. Time-travel queries are complex (need WHERE is_deleted = FALSE everywhere)
3. Concurrent updates require careful locking

**RFC-100 Approach (immutable)**:
```rust
// Create new snapshot = new commit
let new_snapshot = Snapshot::new("def456abc", "my-repo");

// Copy unchanged chunks from old snapshot
copy_chunks_except(old_snapshot, new_snapshot, "auth.py")?;

// Add new chunks for changed file
save_chunks(new_snapshot, new_chunks)?;
```

**Benefits**:
1. Snapshots are immutable (reproducible)
2. Time-travel = just query different snapshot_id
3. No locking needed for reads (MVCC-friendly)
4. Append-only storage (easier to replicate)

### Why File-level Replace?

**External Contract**:
```rust
// User perspective: "I changed auth.py"
replace_file(repo, old_commit, new_commit, "auth.py", new_chunks)?;
```

**Internal Implementation**:
```rust
// Implementation: chunk-level operations
fn replace_file(...) {
    let tx = begin_transaction()?;

    // 1. Identify chunks to remove
    let old_chunks = get_chunks(old_commit, "auth.py")?;

    // 2. Insert new chunks
    for chunk in new_chunks {
        insert_chunk(new_commit, chunk)?;
    }

    tx.commit()?;
}
```

**Rationale**:
- User thinks in **files** (git diff shows file changes)
- Storage thinks in **chunks** (granular indexing)
- API bridges the gap

---

## Migration Path (Old Code → New Code)

### Old Code (codegraph-ir/src/features/storage/)
```
storage/
├── domain/
│   ├── models.rs        # Chunk with is_deleted
│   ├── ports.rs         # ChunkStore trait
│   └── mod.rs
├── infrastructure/
│   ├── sqlite_store.rs  # UPSERT-based
│   └── mod.rs
└── mod.rs
```

### New Code (codegraph-storage/src/)
```
codegraph-storage/src/
├── domain/
│   ├── snapshot.rs      # Immutable snapshot
│   ├── chunk.rs         # No is_deleted
│   ├── repository.rs    # Minimal metadata
│   ├── dependency.rs    # Cross-chunk refs
│   └── mod.rs
├── infrastructure/
│   └── sqlite/
│       ├── schema.rs    # Immutable design
│       ├── adapter.rs   # CodeSnapshotStore impl
│       └── mod.rs
├── api/
│   └── mod.rs           # Public API
└── lib.rs
```

### Migration Checklist
- [ ] Copy models, remove mutable fields
- [ ] Redesign `Snapshot` (commit_hash required)
- [ ] Remove `is_deleted` from `Chunk`
- [ ] Redesign `ports.rs` → `replace_file()` API
- [ ] Update SQLite schema (immutable snapshots)
- [ ] Migrate tests
- [ ] Update documentation

---

## Next Session (RFC-101~105)

This storage module is now ready for RFC-101~105 implementation in a separate session:

1. **RFC-101**: Define `replace_file()` API and transaction model
2. **RFC-102**: Implement SQLite adapter with immutable schema
3. **RFC-103**: Add PostgreSQL adapter with MVCC
4. **RFC-104**: Implement snapshot diff for PR analysis
5. **RFC-105**: Add retention and garbage collection

---

## Current Session Focus

This session will continue with:
- ✅ Storage separation (done)
- 🎯 **Expression IR → Node IR Progressive Lowering** (main focus)
- 🎯 Expression Builder infrastructure
- 🎯 Type inference integration

Storage implementation will resume in a dedicated RFC-101+ session.
