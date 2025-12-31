# codegraph-storage

**RFC-100**: Commit-based Persistent Storage for Code Intelligence

## Purpose

> "commit 단위의 코드 스냅샷을 한 번 만들고, 여러 번 안정적으로 활용한다."

`CodeSnapshotStore`는 git commit 기준으로 생성된 코드 인덱싱 결과를 **불변 자산**으로 저장·교체·조회하기 위한 핵심 스토리지 모듈입니다.

## Core Principles (RFC-100)

### 1. Two-State Rule (절대 혼합 금지)

| State | Trigger | Storage | 성격 |
|-------|---------|---------|------|
| **Ephemeral** | file save | local only | 가변, UX용 |
| **Committed** | git commit | CodeSnapshotStore | **불변, 재현 필수** |

> ⚠️ **CodeSnapshotStore는 Committed State만 다룹니다.**

### 2. Snapshot Identity

```
snapshot_id = commit_hash
```

- Snapshot은 생성 후 **immutable**
- Branch는 저장 대상이 아니라 commit을 가리키는 **포인터(view)**

```
branch(main) ──▶ commit A (snapshot)
branch(feature) ──▶ commit B (snapshot)
```

### 3. Core Contract: File-level Replace

```rust
replace_file(
  repo_id,
  base_snapshot_id,   // 이전 commit
  new_snapshot_id,    // 현재 commit
  file_path,
  new_chunks,
  new_dependencies
)
```

- **외부 계약**: 파일 단위 원자적 교체
- **내부 구현**: chunk 단위 UPSERT (투명)

## Guaranteed Scenarios

### P0 (반드시 만족)
- ✅ Commit Snapshot Persistence (서버 재시작 후에도 재사용)
- ✅ Index Once, Query Many (재인덱싱 없이 반복 질의)
- ✅ File-level Replace Primitive (파일 단위 원자적 교체)

### P1 (실사용 핵심)
- ✅ Commit-based Incremental Snapshot (변경 파일만 재인덱싱)
- ✅ PR / Commit Comparison (두 snapshot 간 semantic diff)
- ✅ Multi-Repository Coexistence (여러 repo snapshot 관리)

### P2 (확장 시나리오)
- ⏳ Time-travel / Regression Analysis
- ⏳ Multi-user Server Access (MVCC)

## Non-Goals (명시적으로 하지 않음)
- ❌ IDE watch/save 상태 저장
- ❌ save 단위 서버 증분 반영
- ❌ 분석 알고리즘(Fixpoint, Bi-abduction 등) 실행
- ❌ Git object storage 대체
- ❌ 실시간 협업 상태 관리

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  CodeSnapshotStore (Port)                   │
│                                                             │
│  - save_snapshot()         - get_snapshot()                │
│  - replace_file()          - compare_snapshots()           │
│  - get_chunks()            - get_dependencies()            │
└──────────────────┬──────────────────────────────────────────┘
                   │ implements
        ┌──────────┴──────────┐
        │                     │
┌───────▼────────┐   ┌────────▼────────┐
│ SqliteAdapter  │   │ PostgresAdapter │
│   (RFC-102)    │   │   (RFC-103)     │
└────────────────┘   └─────────────────┘
```

## Backend Strategy

| Environment | Backend |
|-------------|---------|
| Local / CLI | SQLite |
| Server / SaaS | PostgreSQL |

## Usage Example

```rust
use codegraph_storage::{CodeSnapshotStore, Snapshot, Chunk};

// 1. Create snapshot (commit-based)
let snapshot = Snapshot::new("abc123def", "my-repo");
store.save_snapshot(&snapshot).await?;

// 2. Save chunks (immutable)
let chunks = analyze_files(&files)?;
for chunk in chunks {
    store.save_chunk(&snapshot.id, &chunk).await?;
}

// 3. Query (Index Once, Query Many)
let results = store.get_chunks(&snapshot.id, "auth.py").await?;

// 4. Compare snapshots (PR diff)
let diff = store.compare_snapshots("abc123def", "def456abc").await?;

// 5. Replace file (commit incremental)
store.replace_file(
    "my-repo",
    "abc123def",  // old commit
    "def456abc",  // new commit
    "auth.py",
    new_chunks,
    new_deps
).await?;
```

## RFC Lineage

이 모듈은 다음 RFC들의 기준이 됩니다:

- **RFC-101**: Snapshot Replace API & Transaction Model
- **RFC-102**: SQLite Adapter for CodeSnapshotStore
- **RFC-103**: PostgreSQL Adapter & MVCC Guarantees
- **RFC-104**: Snapshot Diff & PR Analysis
- **RFC-105**: Retention & History Policy

## Development

```bash
# Build
cargo build -p codegraph-storage

# Test (SQLite)
cargo test -p codegraph-storage

# Test (PostgreSQL, future)
cargo test -p codegraph-storage --features postgres
```

## Status

- ✅ RFC-100: Core principles defined
- ⏳ RFC-101: API design
- ⏳ RFC-102: SQLite adapter (migrating from codegraph-ir)
- ⏳ RFC-103: PostgreSQL adapter
- ⏳ RFC-104: Snapshot diff
- ⏳ RFC-105: Retention policy

## License

Same as parent workspace.
