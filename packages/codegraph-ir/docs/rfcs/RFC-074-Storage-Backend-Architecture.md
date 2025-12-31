# RFC-074: Storage Backend Architecture for Multi-Repo Indexing

**Status**: Draft
**Author**: Claude
**Date**: 2025-12-28
**Updated**: 2025-12-28 (Self-Review Applied)

---

## 📝 Changelog

### 2025-12-28 (Self-Review Applied)
**Critical Fixes**:
1. ✅ **Added `content` field** to chunks table - stores actual source code (was missing!)
2. ✅ **Added `is_deleted` field** for soft delete pattern (prevents cascading deletes)
3. ✅ **Updated incremental update algorithm** to use UPSERT instead of DELETE+INSERT
4. ✅ **Clarified Chunk ID format** to include line range: `"repo:path:symbol:10-20"`
5. ✅ **Updated performance targets** to be realistic (< 5ms UPSERT instead of < 1ms)
6. ✅ **Updated storage estimates** to account for content field (~2KB per chunk vs 500B)
7. ✅ **Added comprehensive "Scenarios and Purpose" section** explaining all 6 use cases

**Schema Changes**:
- `chunks.content TEXT NOT NULL` - Actual code content
- `chunks.is_deleted BOOLEAN DEFAULT FALSE` - Soft delete flag
- `idx_chunks_active` - Index for active chunks only

**Algorithm Improvements**:
- Transactional UPSERT pattern instead of DELETE+INSERT
- Soft delete marks chunks as deleted, UPSERT revives them
- No more cascading foreign key deletes during updates

---

## 📋 Summary

Rust-native storage backend for chunk persistence, enabling:
- **Multi-repository** indexing and search
- **Multi-snapshot** (branch/commit) versioning
- **Incremental updates** (change detection)
- **Cross-file dependency** persistence
- **Multi-user** concurrent access
- **Time-travel** queries (historical analysis)

**Design Philosophy**: SQLite-first (simplicity), PostgreSQL-ready (scalability), Port/Adapter pattern (flexibility).

---

## 🎯 Scenarios and Purpose

### What Problems Does This Solve?

This RFC addresses the critical gap between **in-memory ephemeral analysis** and **persistent, scalable code intelligence** by implementing a storage backend that enables:

### 1️⃣ Multi-Repository Code Intelligence

**Scenario**: Enterprise with multiple codebases (backend, frontend, mobile, infra)

```
❌ Before (In-Memory):
- Index backend → Search → Exit → Data lost
- Index frontend → No cross-repo search
- Restart required for each repo

✅ After (Persistent Storage):
┌─────────────────────────────────────────┐
│ Indexed Repositories                    │
├─────────────────────────────────────────┤
│ ✓ backend-api     (120K LOC, 50K chunks)│
│ ✓ frontend-web    (80K LOC, 35K chunks) │
│ ✓ mobile-ios      (60K LOC, 25K chunks) │
│ ✓ infrastructure  (40K LOC, 15K chunks) │
└─────────────────────────────────────────┘

Query: Find all usages of "UserService" across ALL repos
Result: 47 matches in 4 repositories (instant, no re-indexing)
```

**Business Value**: Engineers can search across entire codebase ecosystem without rebuilding indices.

---

### 2️⃣ Pull Request Review Intelligence

**Scenario**: Code review comparing feature branch against main

```
❌ Before (No Snapshots):
- Can only analyze current HEAD
- No historical comparison
- "What changed?" requires git diff + manual analysis

✅ After (Multi-Snapshot):
$ codegraph index --branch main        # Index main
$ codegraph index --branch feature/auth # Index feature branch

Query: Compare snapshots
┌──────────────────────────────────────────────┐
│ Changes in feature/auth vs main              │
├──────────────────────────────────────────────┤
│ MODIFIED: src/auth/login.py                  │
│   • authenticate() - 3 new dependencies      │
│   • hash_password() - security improvement   │
│ NEW:      src/auth/oauth.py                  │
│   • OAuthProvider class (15 methods)         │
│ DELETED:  src/auth/legacy_auth.py            │
└──────────────────────────────────────────────┘

Question: "What new security vulnerabilities did this PR introduce?"
Answer: Taint analysis shows 2 new sources, 0 new sinks → Low risk
```

**Business Value**: Automated PR impact analysis, regression detection, security review.

---

### 3️⃣ Incremental Indexing for Watch Mode

**Scenario**: Developer working on large repo (500K LOC)

```
❌ Before (Full Re-analysis):
- Save file → Trigger re-index
- Process ALL 500K LOC → 50 seconds
- Developer waits, flow disrupted

✅ After (Incremental Updates):
1. Save src/api/users.py (500 LOC)
2. Backend:
   - Compute SHA256: abc123...
   - Check DB: Old hash = def456... (different!)
   - Re-analyze ONLY users.py → 0.5 seconds
   - Update chunks + dependencies
3. Developer continues working → 100x faster

Statistics:
- Changed files: 1 / 1000 files
- Time: 0.5s instead of 50s
- Speedup: 100x
```

**Business Value**: Real-time code intelligence for IDE integration, minimal latency.

---

### 4️⃣ Cross-File Dependency Graph Survival

**Scenario**: API server with persistent dependency analysis

```
❌ Before (In-Memory Graph):
- Build dependency graph → Takes 2 minutes
- Server restarts (deploy/crash) → Graph lost
- Rebuild on every startup → Cold start problem

✅ After (Persistent Graph):
┌─────────────────────────────────────────┐
│ dependencies table                      │
├─────────────────────────────────────────┤
│ auth.login → db.query_user (CALLS)      │
│ auth.login → crypto.hash (CALLS)        │
│ api.UserAPI → auth.login (CALLS)        │
│ ... (200K relationships)                │
└─────────────────────────────────────────┘

Server restart:
1. Load graph from DB → 0.2 seconds
2. Ready to serve queries → Instant cold start

Query: "What breaks if I change crypto.hash signature?"
Answer: 23 functions affected across 12 files
```

**Business Value**: Zero-downtime deployments, fast cold starts, reliable impact analysis.

---

### 5️⃣ Multi-User Concurrent Access (SaaS)

**Scenario**: Team using hosted CodeGraph API server

```
❌ Before (Single Process):
- User A: Indexing repo → Locks entire system
- User B: Query blocked → Wait 2 minutes
- User C: Cannot start indexing → Queue builds up

✅ After (PostgreSQL MVCC):
┌───────────────────────────────────────────┐
│ Concurrent Operations                     │
├───────────────────────────────────────────┤
│ User A: Indexing backend-api (writing)    │
│ User B: Searching frontend-web (reading)  │
│ User C: Indexing mobile-ios (writing)     │
│ User D: PR review query (reading)         │
└───────────────────────────────────────────┘

PostgreSQL MVCC:
- Writers: N (row-level locks, no blocking)
- Readers: N (MVCC snapshots, always consistent)
- Throughput: 1000 qps (read-heavy workload)
```

**Business Value**: Multi-tenant SaaS, horizontal scaling, enterprise deployment.

---

### 6️⃣ Time-Travel Debugging

**Scenario**: "When did this bug get introduced?"

```
❌ Before (No History):
- Bug found in production
- Git bisect manually
- Re-analyze each commit → Hours of work

✅ After (Chunk History):
Query: "Show me taint analysis for auth.login across last 10 commits"

┌─────────────────────────────────────────────────┐
│ Commit History for auth.login                   │
├─────────────────────────────────────────────────┤
│ abc123 (2025-12-20): ✓ No taint flows           │
│ def456 (2025-12-21): ✓ No taint flows           │
│ ghi789 (2025-12-22): ⚠️  NEW: user_input → SQL │ ← BUG!
│ jkl012 (2025-12-23): ⚠️  Still vulnerable       │
│ ...                                             │
└─────────────────────────────────────────────────┘

Answer: SQL injection introduced in commit ghi789
Responsible: @developer (2025-12-22 14:32)
```

**Business Value**: Root cause analysis, regression tracking, compliance auditing.

---

### Key Use Cases Summary

| Use Case | Without Storage | With Storage | Impact |
|----------|----------------|--------------|--------|
| **Multi-Repo Search** | Re-index every query | Index once, query forever | 1000x faster queries |
| **PR Review** | Manual git diff | Automated semantic diff | 10x faster reviews |
| **Watch Mode** | 50s full re-analysis | 0.5s incremental | 100x faster updates |
| **API Server** | Cold start 2 min | Cold start 0.2s | 10x faster startup |
| **Multi-User** | Serialized access | Concurrent access | 10x throughput |
| **Debugging** | Manual bisect | Automated history | 100x faster RCA |

---

### Target Personas

1. **Solo Developer (CLI)**: SQLite, zero-config, watch mode
2. **Small Team (10-50)**: SQLite + file sharing, PR reviews
3. **Enterprise (100+)**: PostgreSQL, multi-tenant SaaS, compliance
4. **CI/CD Pipeline**: Incremental indexing, artifact caching
5. **Security Team**: Historical taint analysis, vulnerability tracking

---

## 🎯 Motivation

### Current State (In-Memory Only)

```rust
// codegraph-ir/src/features/chunking/infrastructure/chunk_builder.rs
pub struct ChunkBuilder {
    chunks: Vec<Chunk>,  // ❌ Volatile, single-process, single-repo
}
```

**Problems**:
| Scenario | Current | Impact |
|----------|---------|--------|
| Multi-repo | ❌ Only 1 repo per process | Can't index multiple codebases |
| Multi-user | ❌ Single process only | No API server support |
| Incremental | ❌ Full re-analysis every time | Slow for large repos |
| History | ❌ No versioning | Can't track changes over time |
| Dependency | ❌ Ephemeral graph | Lost on restart |

### Why Now?

1. **API Server Use Case**: Multi-tenant SaaS requires persistent storage
2. **Watch Mode**: Incremental updates need change tracking
3. **Branch Comparison**: PR review needs multi-snapshot support
4. **Performance**: Avoid re-indexing unchanged files (10-100x speedup)

---

## 🔬 SOTA Analysis

### Industry Standards

| System | Storage Strategy | Strengths | Weaknesses |
|--------|-----------------|-----------|------------|
| **Sourcegraph** | PostgreSQL + RocksDB | Scalable, multi-repo | Complex setup |
| **GitHub CodeQL** | SQLite (local), Cloud (remote) | Simple local, powerful remote | Dual architecture |
| **Semgrep** | SQLite (cache), no server mode | Fast local cache | Limited multi-user |
| **Meta Infer** | In-memory + JSON export | Fast analysis | No incremental |
| **Coverity** | Oracle DB | Enterprise scale | Heavyweight |

### Our Position

**Hybrid Approach** (Best of Both Worlds):
```
Development/CLI:     SQLite (simple, fast, zero-config)
Production/Server:   PostgreSQL (scalable, concurrent, ACID)
Interface:           Port/Adapter (switch backends seamlessly)
```

**Why SQLite First?**
1. **Zero Configuration**: Embedded, no daemon
2. **ACID Transactions**: Same guarantees as PostgreSQL
3. **Performance**: 10-100x faster than disk I/O for local use
4. **Simplicity**: Single file, easy backup/restore
5. **Industry Proven**: Used by Chromium, Firefox, Android, iOS

**PostgreSQL Second** (when needed):
1. **Multi-user**: Concurrent writes (MVCC)
2. **Scale**: TB-scale databases
3. **Advanced Features**: Full-text search, JSON operators, partitioning
4. **Cloud Native**: AWS RDS, Google Cloud SQL

---

## 🏗️ Architecture

### Port/Adapter Pattern

```
┌─────────────────────────────────────────────────┐
│           Application Layer                     │
│  (ChunkBuilder, IRIndexingOrchestrator)         │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────┐
│         Port (ChunkStore trait)                │
│  - save_chunk()                                │
│  - get_chunks()                                │
│  - query_dependencies()                        │
│  - get_snapshots()                             │
└─────┬──────────────────────────────────────────┘
      │
      ├──────────────┬──────────────┬─────────────┐
      ▼              ▼              ▼             ▼
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ SQLite   │  │Postgres  │  │ InMemory │  │ Future:  │
│ Adapter  │  │ Adapter  │  │  (Test)  │  │ RocksDB  │
└──────────┘  └──────────┘  └──────────┘  └──────────┘
```

### Domain Model

```rust
// Core entities
pub struct Chunk {
    // Identity
    pub chunk_id: String,          // PK: "repo:path:symbol:10-20" (MUST include line range!)
    pub repo_id: String,           // FK: Repository
    pub snapshot_id: String,       // FK: Branch/Commit

    // Location
    pub file_path: String,
    pub start_line: u32,
    pub end_line: u32,

    // Semantics
    pub kind: ChunkKind,           // Function, Class, Module, etc.
    pub fqn: Option<String>,       // Fully Qualified Name
    pub language: String,
    pub symbol_visibility: SymbolVisibility,

    // Content (CRITICAL: actual source code)
    pub content: String,           // Actual code content for search/display
    pub content_hash: String,      // SHA256 for change detection
    pub summary: Option<String>,   // AI-generated summary
    pub importance: f32,           // PageRank score

    // Soft Delete
    pub is_deleted: bool,          // Soft delete flag (default: false)

    // Metadata
    pub attrs: HashMap<String, Value>,  // JSON
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

pub struct Dependency {
    pub id: String,
    pub from_chunk_id: String,
    pub to_chunk_id: String,
    pub relationship: DependencyType,  // CALLS, IMPORTS, EXTENDS, etc.
    pub confidence: f32,
}

pub struct Snapshot {
    pub snapshot_id: String,       // PK: "main", "feature/auth", "abc123def"
    pub repo_id: String,
    pub commit_hash: Option<String>,
    pub branch_name: Option<String>,
    pub created_at: DateTime<Utc>,
}
```

---

## 📊 Schema Design (SQLite + PostgreSQL Compatible)

### Core Tables

```sql
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 1. Repositories
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CREATE TABLE repositories (
    repo_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    remote_url TEXT,
    local_path TEXT,
    default_branch TEXT DEFAULT 'main',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_repos_name ON repositories(name);

-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 2. Snapshots (Branches/Commits)
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CREATE TABLE snapshots (
    snapshot_id TEXT PRIMARY KEY,        -- "repo-id:branch-name" or "repo-id:commit-hash"
    repo_id TEXT NOT NULL,
    commit_hash TEXT,                    -- Git commit SHA
    branch_name TEXT,                    -- Git branch name
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (repo_id) REFERENCES repositories(repo_id) ON DELETE CASCADE
);

CREATE INDEX idx_snapshots_repo ON snapshots(repo_id);
CREATE INDEX idx_snapshots_commit ON snapshots(commit_hash);
CREATE INDEX idx_snapshots_branch ON snapshots(repo_id, branch_name);

-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 3. Chunks (Core Entity)
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CREATE TABLE chunks (
    -- Identity
    chunk_id TEXT PRIMARY KEY,           -- "repo:path:symbol:10-20" (includes line range!)
    repo_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,

    -- Location
    file_path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,

    -- Semantics
    kind TEXT NOT NULL,                  -- "function", "class", "module", etc.
    fqn TEXT,                            -- Fully Qualified Name
    language TEXT NOT NULL,              -- "python", "typescript", etc.
    symbol_visibility TEXT,              -- "public", "private", "internal"

    -- Content (CRITICAL: stores actual source code)
    content TEXT NOT NULL,               -- Actual code content for search/display
    content_hash TEXT NOT NULL,          -- SHA256 of content (for change detection)
    summary TEXT,                        -- AI-generated summary
    importance REAL DEFAULT 0.5,         -- PageRank (0.0-1.0)

    -- Soft Delete (for safe incremental updates)
    is_deleted BOOLEAN DEFAULT FALSE,    -- Soft delete flag (never hard DELETE)

    -- Metadata
    attrs TEXT,                          -- JSON: {"children": [...], "docstring": "..."}

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign Keys
    FOREIGN KEY (repo_id) REFERENCES repositories(repo_id) ON DELETE CASCADE,
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX idx_chunks_repo_snapshot ON chunks(repo_id, snapshot_id);
CREATE INDEX idx_chunks_file ON chunks(repo_id, file_path);
CREATE INDEX idx_chunks_fqn ON chunks(fqn) WHERE fqn IS NOT NULL;
CREATE INDEX idx_chunks_hash ON chunks(repo_id, file_path, content_hash);
CREATE INDEX idx_chunks_kind ON chunks(kind);
CREATE INDEX idx_chunks_active ON chunks(repo_id, snapshot_id) WHERE is_deleted = FALSE;  -- Active chunks only

-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 4. Dependencies (Cross-Chunk Relationships)
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CREATE TABLE dependencies (
    id TEXT PRIMARY KEY,
    from_chunk_id TEXT NOT NULL,
    to_chunk_id TEXT NOT NULL,
    relationship TEXT NOT NULL,          -- "CALLS", "IMPORTS", "EXTENDS", "IMPLEMENTS"
    confidence REAL DEFAULT 1.0,         -- 0.0-1.0 (for fuzzy matching)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (from_chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    FOREIGN KEY (to_chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE,

    UNIQUE(from_chunk_id, to_chunk_id, relationship)
);

CREATE INDEX idx_deps_from ON dependencies(from_chunk_id);
CREATE INDEX idx_deps_to ON dependencies(to_chunk_id);
CREATE INDEX idx_deps_type ON dependencies(relationship);

-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 5. Chunk History (Time-Travel Support)
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CREATE TABLE chunk_history (
    id TEXT PRIMARY KEY,
    chunk_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    operation TEXT NOT NULL,             -- "INSERT", "UPDATE", "DELETE"
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Snapshot of chunk at this point in time (JSON)
    snapshot_data TEXT NOT NULL,         -- Serialized Chunk

    FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE
);

CREATE INDEX idx_history_chunk ON chunk_history(chunk_id);
CREATE INDEX idx_history_snapshot ON chunk_history(snapshot_id);
CREATE INDEX idx_history_time ON chunk_history(changed_at);

-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 6. File Metadata (For Incremental Updates)
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CREATE TABLE file_metadata (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,          -- SHA256 of entire file
    last_indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (repo_id) REFERENCES repositories(repo_id) ON DELETE CASCADE,
    UNIQUE(repo_id, snapshot_id, file_path)
);

CREATE INDEX idx_files_repo_snapshot ON file_metadata(repo_id, snapshot_id);
CREATE INDEX idx_files_hash ON file_metadata(content_hash);
```

### Rationale for Schema Choices

#### 1. **Chunk ID Format (CRITICAL)**
**Format**: `"<repo_id>:<file_path>:<symbol_name>:<start_line>-<end_line>"`

**Examples**:
```
"backend-api:src/auth.py:login:10-25"
"frontend:components/Button.tsx:Button:5-15"
"mobile:Auth/LoginVC.swift:viewDidLoad:42-56"
```

**Why Line Range is Required**:
- **Uniqueness**: Same function name can appear multiple times in file (overloads, nested functions)
- **Change Detection**: Line shifts don't break identity if content hash differs
- **Debugging**: Human-readable, points to exact location

**Collision Handling**:
```rust
// If multiple symbols at same location (rare edge case)
// Append index: "repo:file:symbol:10-20#1", "repo:file:symbol:10-20#2"
fn generate_chunk_id(repo_id: &str, path: &str, symbol: &str, start: u32, end: u32) -> String {
    format!("{}:{}:{}:{}-{}", repo_id, path, symbol, start, end)
}
```

#### 2. **Content Field (CRITICAL)**
- **Added**: `content TEXT NOT NULL` - stores actual source code
- **Why**:
  - **Search**: Full-text search requires actual code content
  - **Display**: Show code snippets in search results
  - **Analysis**: AI summarization, embedding generation
  - **Storage**: ~1.5KB per chunk (acceptable overhead)

**Alternative Considered**: Store content in separate blob storage (S3, file system)
- **Rejected**: Adds complexity, latency for 95% of queries
- **Future**: Optionally offload old snapshots to cold storage

#### 3. **Soft Delete (CRITICAL)**
- **Added**: `is_deleted BOOLEAN DEFAULT FALSE`
- **Why**:
  - **UPSERT Safety**: Revive chunks instead of cascading deletes
  - **Incremental Updates**: Mark old chunks as deleted, restore if re-analyzed
  - **Transaction Safety**: Avoid foreign key violations during updates
  - **Audit Trail**: Track deletions in history table

**Hard Delete Strategy**:
```sql
-- Periodic cleanup (run monthly)
DELETE FROM chunks
WHERE is_deleted = TRUE
  AND updated_at < datetime('now', '-90 days');
```

#### 4. **JSON Attrs Column**
- **Alternative**: Separate `chunk_attributes` table (normalized)
- **Choice**: Single JSON column
- **Why**:
  - Flexible schema (language-specific attributes)
  - SQLite/PostgreSQL both have excellent JSON support
  - Avoids JOIN overhead for rare queries
  - PostgreSQL: JSONB indexing for performance

#### 5. **Snapshot Model**
- **Alternative 1**: One snapshot per commit (bloat)
- **Alternative 2**: No snapshots, only `commit_hash` in chunks (no branch tracking)
- **Choice**: Hybrid (branch name OR commit hash)
- **Why**:
  - Branch tracking: "main", "develop" (common case)
  - Commit tracking: PR diffs, bisect (advanced case)
  - Space efficient: Only track indexed snapshots

#### 6. **History Table**
- **Alternative 1**: Temporal tables (PostgreSQL 11+)
- **Alternative 2**: Append-only chunks table
- **Choice**: Separate history table
- **Why**:
  - SQLite compatibility (no temporal tables)
  - Explicit control over retention policy
  - Easier to prune old history

#### 7. **Denormalization**
- `file_path` in chunks (redundant with `chunk_id`)
- **Why**: Query performance (avoid parsing chunk_id)

---

## 🔬 SOTA Verification

### 1. Multi-Repository Support ✅

**Industry Comparison**:
| System | Strategy | Our Approach |
|--------|----------|--------------|
| Sourcegraph | `repositories` table with `external_id` | ✅ Similar: `repositories` table |
| GitHub CodeQL | Database per repo | ❌ Too heavyweight |
| Semgrep | Flat file structure | ❌ No isolation |

**Our Design**:
```sql
-- Query: Get all chunks for repo "backend-api"
SELECT * FROM chunks WHERE repo_id = 'backend-api';

-- Index support: O(log n) lookup
idx_chunks_repo_snapshot(repo_id, snapshot_id)
```

**SOTA Level**: ✅ Matches Sourcegraph architecture

---

### 2. Multi-Snapshot (Branch/Commit) Support ✅

**Industry Comparison**:
| System | Strategy | Our Approach |
|--------|----------|--------------|
| GitHub | Git-native (ref history) | ✅ Similar: `snapshots` table |
| GitLab CI | Pipeline artifacts per commit | ❌ Too storage-heavy |
| Coverity | Single snapshot | ❌ No versioning |

**Our Design**:
```sql
-- Query: Compare main vs feature branch
SELECT c1.fqn, c1.content_hash AS main_hash, c2.content_hash AS feature_hash
FROM chunks c1
LEFT JOIN chunks c2 ON c1.fqn = c2.fqn
WHERE c1.snapshot_id = 'backend:main'
  AND c2.snapshot_id = 'backend:feature/auth'
  AND c1.content_hash != c2.content_hash;
```

**SOTA Level**: ✅ Better than most (explicit snapshot tracking)

---

### 3. Incremental Updates ✅

**Industry Comparison**:
| System | Strategy | Our Approach |
|--------|----------|--------------|
| Bazel | Content-addressable cache | ✅ Similar: `content_hash` |
| Buck2 | File hash + mtime | ✅ Better: SHA256 only (reliable) |
| Make | mtime only | ❌ Unreliable |

**Our Design**:
```rust
// Incremental update algorithm (UPSERT-based, transactional)
pub async fn incremental_update(
    &self,
    repo_id: &str,
    snapshot_id: &str,
    changed_files: Vec<&str>,
) -> Result<()> {
    for file_path in changed_files {
        // 1. Compute new content hash
        let new_hash = sha256(read_file(file_path)?);

        // 2. Check if changed
        let old_hash = self.get_file_hash(repo_id, snapshot_id, file_path).await?;

        if Some(&new_hash) == old_hash.as_ref() {
            continue;  // ⚡ Skip unchanged files
        }

        // 3. Begin transaction (ACID guarantees)
        let tx = self.begin_transaction().await?;

        // 4. Soft-delete old chunks (mark as deleted, don't CASCADE!)
        tx.execute(
            "UPDATE chunks SET is_deleted = TRUE, updated_at = CURRENT_TIMESTAMP
             WHERE repo_id = $1 AND snapshot_id = $2 AND file_path = $3",
            &[repo_id, snapshot_id, file_path]
        ).await?;

        // 5. Re-analyze and UPSERT new chunks
        let chunks = analyze_file(file_path)?;
        for chunk in chunks {
            tx.execute(
                "INSERT INTO chunks (chunk_id, repo_id, snapshot_id, content, content_hash, is_deleted, ...)
                 VALUES ($1, $2, $3, $4, $5, FALSE, ...)
                 ON CONFLICT (chunk_id) DO UPDATE SET
                   content = EXCLUDED.content,
                   content_hash = EXCLUDED.content_hash,
                   is_deleted = FALSE,
                   updated_at = CURRENT_TIMESTAMP",
                &[&chunk.chunk_id, repo_id, snapshot_id, &chunk.content, &chunk.content_hash]
            ).await?;
        }

        // 6. Update file metadata
        self.update_file_metadata(&tx, repo_id, snapshot_id, file_path, new_hash).await?;

        // 7. Commit transaction
        tx.commit().await?;
    }

    Ok(())
}
```

**Performance**:
```
Full re-analysis:  1000 files × 100ms = 100s
Incremental:       10 changed files × 100ms = 1s  (100x faster!)
```

**SOTA Level**: ✅ Content-addressable (industry standard)

---

### 4. Dependency Graph Persistence ✅

**Industry Comparison**:
| System | Strategy | Our Approach |
|--------|----------|--------------|
| Sourcegraph | Graph stored in DB | ✅ Same |
| Neo4j (graph DB) | Native graph storage | ❌ Overkill (RDBMS sufficient) |
| In-memory only | Recompute on startup | ❌ Slow |

**Our Design**:
```sql
-- Query: Get all callees of function "auth.login"
SELECT c.fqn, d.relationship
FROM dependencies d
JOIN chunks c ON d.to_chunk_id = c.chunk_id
WHERE d.from_chunk_id = (
    SELECT chunk_id FROM chunks WHERE fqn = 'auth.login' LIMIT 1
);

-- Index support: O(log n) traversal
idx_deps_from(from_chunk_id)
```

**Graph Traversal** (BFS/DFS):
```rust
pub async fn get_transitive_dependencies(
    &self,
    chunk_id: &str,
    max_depth: usize,
) -> Result<HashSet<String>> {
    let mut visited = HashSet::new();
    let mut queue = VecDeque::from([chunk_id.to_string()]);
    let mut depth = 0;

    while let Some(current) = queue.pop_front() {
        if visited.contains(&current) || depth >= max_depth {
            continue;
        }

        visited.insert(current.clone());

        // Get direct dependencies from DB
        let deps = self.get_dependencies(&current).await?;
        queue.extend(deps.into_iter().map(|d| d.to_chunk_id));

        depth += 1;
    }

    Ok(visited)
}
```

**SOTA Level**: ✅ Standard RDBMS approach (proven at scale)

---

### 5. Multi-User Concurrent Access ✅

**Industry Comparison**:
| System | Strategy | Our Approach |
|--------|----------|--------------|
| PostgreSQL | MVCC (row-level locking) | ✅ Use PostgreSQL for multi-user |
| SQLite | Database-level locking | ✅ OK for single-user CLI |
| Redis | In-memory, atomic ops | ❌ Not durable |

**Concurrency Model**:

**SQLite** (Development):
```
Writer: 1 (exclusive lock)
Readers: N (concurrent reads during write via WAL mode)
Use case: CLI, single developer
```

**PostgreSQL** (Production):
```
Writers: N (MVCC, row-level locks)
Readers: N (no blocking)
Use case: API server, multi-tenant SaaS
```

**SOTA Level**: ✅ Industry standard (SQLite → PostgreSQL migration path)

---

### 6. Time-Travel Queries ✅

**Industry Comparison**:
| System | Strategy | Our Approach |
|--------|----------|--------------|
| Git | Commit history | ✅ Similar: `chunk_history` table |
| Dolt | Git for data | ✅ Same concept, simpler |
| PostgreSQL Temporal Tables | Built-in (PG 11+) | ❌ SQLite incompatible |

**Our Design**:
```sql
-- Query: Get chunk at specific commit
SELECT snapshot_data
FROM chunk_history
WHERE chunk_id = 'repo:src/auth.py:login:10-20'
  AND snapshot_id = 'backend:abc123def'
ORDER BY changed_at DESC
LIMIT 1;
```

**History Retention Policy**:
```rust
// Prune history older than 90 days
DELETE FROM chunk_history
WHERE changed_at < datetime('now', '-90 days');
```

**SOTA Level**: ✅ Git-like versioning (proven approach)

---

## 🚀 Implementation Plan

### Phase 1: SQLite Foundation (Week 1-2)

**Goals**:
- [x] Schema design (this RFC)
- [ ] Port trait definition
- [ ] SQLite adapter implementation
- [ ] Basic CRUD operations
- [ ] Unit tests (in-memory DB)

**Deliverables**:
```rust
// Port
pub trait ChunkStore: Send + Sync {
    async fn save_chunk(&self, chunk: &Chunk) -> Result<()>;
    async fn get_chunks(&self, repo_id: &str, snapshot_id: &str) -> Result<Vec<Chunk>>;
    async fn query_dependencies(&self, chunk_id: &str) -> Result<Vec<Dependency>>;
}

// Adapter
pub struct SqliteChunkStore {
    conn: Arc<Mutex<Connection>>,
}
```

### Phase 2: Incremental Updates (Week 3)

**Goals**:
- [ ] File metadata tracking
- [ ] Content hash comparison
- [ ] Incremental update algorithm
- [ ] Integration tests (watch mode)

### Phase 3: PostgreSQL Adapter (Week 4)

**Goals**:
- [ ] SQLx integration
- [ ] Schema migration (SQLite → PostgreSQL)
- [ ] Connection pooling
- [ ] Multi-user concurrency tests

### Phase 4: Advanced Features (Week 5-6)

**Goals**:
- [ ] Graph traversal APIs (BFS/DFS)
- [ ] History queries (time-travel)
- [ ] Performance benchmarks
- [ ] Production deployment guide

---

## 📊 Performance Targets

### Latency

| Operation | Target | Rationale |
|-----------|--------|-----------|
| Save chunk (single, UPSERT) | < 5ms | SSD write + index update + soft delete check |
| Save chunks (batch 100) | < 50ms | Transaction batching with UPSERT |
| Get chunks by repo (active only) | < 10ms | Indexed lookup (100K chunks, idx_chunks_active) |
| Query dependencies | < 10ms | Graph traversal (depth=3) with JOINs |
| Incremental update | < 100ms/file | Hash check + soft delete + UPSERT |

### Throughput

| Scenario | Target | Rationale |
|----------|--------|-----------|
| Full indexing | 10K chunks/sec | Parallel processing |
| Incremental update | 100 files/sec | Hot path optimization |
| Concurrent queries | 1K qps | Read-heavy workload |

### Storage

| Data | Size | Rationale |
|------|------|-----------|
| Chunk (with content) | ~2 KB | 500B metadata + ~1.5KB code content (avg) |
| Chunk (metadata only) | ~500 bytes | FQN, hashes, attrs (if content stored elsewhere) |
| Dependency | ~100 bytes | Two chunk IDs + type |
| 1M LOC repo | ~200 MB | 100K chunks × 2KB (with content) |
| 1M LOC repo (no content) | ~70 MB | 100K chunks × 500B + 200K deps × 100B |
| History (90 days) | ~2 GB | 10 snapshots × 200 MB |

---

## 🔒 Security Considerations

### SQL Injection Prevention

```rust
// ✅ Use parameterized queries (sqlx/rusqlite auto-escapes)
sqlx::query!("SELECT * FROM chunks WHERE repo_id = $1", repo_id)

// ❌ Never concatenate user input
format!("SELECT * FROM chunks WHERE repo_id = '{}'", repo_id)  // UNSAFE!
```

### Access Control

**Repository-Level Isolation**:
```rust
pub struct ChunkStoreWithAuth {
    store: Box<dyn ChunkStore>,
    user_repos: HashMap<UserId, Vec<RepoId>>,  // ACL
}

impl ChunkStoreWithAuth {
    pub async fn get_chunks(&self, user_id: &str, repo_id: &str) -> Result<Vec<Chunk>> {
        // Check permission
        if !self.user_repos.get(user_id)?.contains(repo_id) {
            return Err(Error::Unauthorized);
        }

        self.store.get_chunks(repo_id, None).await
    }
}
```

### Data Encryption (Future)

**At-Rest Encryption** (SQLite):
```rust
// Use SQLCipher for encrypted SQLite databases
let conn = Connection::open_with_flags(
    "codegraph.db",
    OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_CREATE,
)?;
conn.execute("PRAGMA key = 'encryption-key';", [])?;
```

---

## 🧪 Testing Strategy

### Unit Tests (In-Memory SQLite)

```rust
#[tokio::test]
async fn test_save_and_retrieve_chunk() {
    let store = SqliteChunkStore::in_memory().unwrap();

    let chunk = Chunk {
        chunk_id: "repo:main.py:foo:1-10".into(),
        repo_id: "test-repo".into(),
        snapshot_id: "main".into(),
        // ...
    };

    store.save_chunk(&chunk).await.unwrap();

    let chunks = store.get_chunks("test-repo", "main").await.unwrap();
    assert_eq!(chunks.len(), 1);
    assert_eq!(chunks[0].chunk_id, "repo:main.py:foo:1-10");
}
```

### Integration Tests (Real SQLite File)

```rust
#[tokio::test]
async fn test_incremental_update() {
    let temp_dir = tempfile::tempdir().unwrap();
    let db_path = temp_dir.path().join("test.db");
    let store = SqliteChunkStore::new(db_path.to_str().unwrap()).unwrap();

    // Initial index
    let chunks = analyze_repo("fixtures/test-repo")?;
    store.save_chunks(&chunks).await?;

    // Modify file
    std::fs::write("fixtures/test-repo/main.py", "# changed")?;

    // Incremental update
    store.incremental_update("test-repo", "main", vec!["main.py"]).await?;

    // Verify only 1 file re-analyzed
    assert_eq!(metrics.files_analyzed, 1);
}
```

### Benchmarks (Criterion)

```rust
fn bench_save_chunks(c: &mut Criterion) {
    let store = SqliteChunkStore::in_memory().unwrap();
    let chunks: Vec<Chunk> = (0..1000).map(|i| mock_chunk(i)).collect();

    c.bench_function("save_1000_chunks", |b| {
        b.to_async(Runtime::new().unwrap()).iter(|| async {
            store.save_chunks(&chunks).await.unwrap();
        });
    });
}
```

---

## 🔄 Migration Path

### From In-Memory to SQLite

```rust
// Before
let mut chunks = Vec::new();

// After
let store = SqliteChunkStore::new("codegraph.db")?;
store.save_chunks(&chunks).await?;
```

### From SQLite to PostgreSQL

```bash
# Export SQLite to SQL dump
sqlite3 codegraph.db .dump > dump.sql

# Import to PostgreSQL
psql -U user -d codegraph < dump.sql
```

**Application Code** (no change needed):
```rust
// Same interface!
let store: Box<dyn ChunkStore> = if production {
    Box::new(PostgresChunkStore::new(&db_url).await?)
} else {
    Box::new(SqliteChunkStore::new("codegraph.db")?)
};
```

---

## 📚 References

### Academic

1. **Temporal Databases**: Snodgrass (1999) - "Developing Time-Oriented Database Applications in SQL"
2. **Content-Addressable Storage**: Git (2005) - Linus Torvalds
3. **MVCC**: PostgreSQL (1996) - Michael Stonebraker

### Industry

1. **Sourcegraph**: [Architecture Docs](https://docs.sourcegraph.com/dev/background-information/architecture)
2. **GitHub CodeQL**: [Database Schema](https://codeql.github.com/docs/codeql-overview/codeql-database/)
3. **Bazel**: [Content Addressable Storage](https://bazel.build/remote/caching)

### Tools

1. **SQLite**: https://sqlite.org/
2. **SQLx**: https://github.com/launchbadge/sqlx
3. **Rusqlite**: https://github.com/rusqlite/rusqlite

---

## 🎯 Success Criteria

### Functional

- [ ] Multi-repo indexing (10+ repos)
- [ ] Multi-snapshot support (branch/commit)
- [ ] Incremental updates (10x speedup vs full re-analysis)
- [ ] Dependency graph persistence
- [ ] Time-travel queries (90-day history)

### Non-Functional

- [ ] Latency: < 10ms for common queries
- [ ] Throughput: 10K chunks/sec indexing
- [ ] Storage: < 100 MB per 1M LOC repo
- [ ] Zero-config: SQLite works out-of-box
- [ ] Scalability: PostgreSQL handles 100+ concurrent users

### Code Quality

- [ ] 90%+ test coverage
- [ ] Port/Adapter pattern strictly enforced
- [ ] No SQL injection vulnerabilities
- [ ] Comprehensive benchmarks

---

## 🚧 Future Work

### Phase 5+

1. **Distributed Storage**: Shard by repo_id (multi-node PostgreSQL)
2. **Full-Text Search**: PostgreSQL `tsvector` or Tantivy integration
3. **Real-Time Sync**: WebSocket-based change notifications
4. **Compression**: ZSTD for `attrs` JSON column
5. **Partitioning**: Partition `chunk_history` by month
6. **GraphQL API**: Expose storage via GraphQL (not just Rust API)

---

## 📝 Decision Log

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| SQLite first, PostgreSQL second | Simplicity + future scalability | Redis (not durable), RocksDB (complex) |
| Port/Adapter pattern | Backend flexibility | Direct SQLite coupling |
| **Store `content` in chunks table** | 95% queries need it, low latency | Blob storage (too complex) |
| **Soft delete with `is_deleted`** | UPSERT safety, no cascades | Hard DELETE (breaks dependencies) |
| **UPSERT for incremental updates** | Idempotent, transactional | DELETE+INSERT (race conditions) |
| **Chunk ID includes line range** | Uniqueness for overloads | Symbol name only (collisions) |
| JSON `attrs` column | Schema flexibility | Separate `chunk_attributes` table |
| `content_hash` for incremental | Reliability (mtime unreliable) | mtime-based (fragile) |
| Separate `chunk_history` table | SQLite compatibility | PostgreSQL temporal tables |
| `repo_id + snapshot_id` composite | Multi-tenant isolation | Single-repo per DB |

---

## ✅ Approval

**Reviewers**: TBD
**Status**: Draft → Review → Approved → Implemented

**Open Questions**:
1. Should we support S3-backed storage (for cloud deployments)?
2. Should `chunk_history` be optional (flag to disable for storage savings)?
3. Should we add Prometheus metrics (counter, histogram for queries)?

---

**End of RFC-074**
