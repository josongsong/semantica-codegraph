-- RFC-074 Storage Backend - Initial PostgreSQL Schema
-- SOTA-grade production schema with proper indexing and constraints
-- Compatible with SQLite schema but using PostgreSQL best practices

-- 1. Repositories table
CREATE TABLE IF NOT EXISTS repositories (
    repo_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    remote_url TEXT,
    local_path TEXT,
    default_branch TEXT NOT NULL DEFAULT 'main',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_repositories_name ON repositories(name);

-- 2. Snapshots table (commit/branch snapshots)
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    commit_hash TEXT,
    branch_name TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (repo_id) REFERENCES repositories(repo_id) ON DELETE CASCADE
);

CREATE INDEX idx_snapshots_repo ON snapshots(repo_id);
CREATE INDEX idx_snapshots_commit ON snapshots(commit_hash);
CREATE INDEX idx_snapshots_branch ON snapshots(branch_name);

-- 3. Chunks table (code chunks with FQN)
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    kind TEXT NOT NULL,
    fqn TEXT,
    language TEXT NOT NULL,
    symbol_visibility TEXT,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    summary TEXT,
    importance REAL NOT NULL DEFAULT 0.5,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (repo_id) REFERENCES repositories(repo_id) ON DELETE CASCADE,
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
);

-- Performance indexes for chunks
CREATE INDEX idx_chunks_snapshot ON chunks(snapshot_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_chunks_repo ON chunks(repo_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_chunks_fqn ON chunks(fqn) WHERE fqn IS NOT NULL AND is_deleted = FALSE;
CREATE INDEX idx_chunks_file ON chunks(repo_id, snapshot_id, file_path) WHERE is_deleted = FALSE;
CREATE INDEX idx_chunks_hash ON chunks(content_hash);
CREATE INDEX idx_chunks_kind ON chunks(kind);

-- Full-text search index (PostgreSQL native)
CREATE INDEX idx_chunks_content_fts ON chunks USING GIN(to_tsvector('english', content)) WHERE is_deleted = FALSE;

-- 4. Dependencies table (dependency graph)
CREATE TABLE IF NOT EXISTS dependencies (
    id TEXT PRIMARY KEY,
    from_chunk_id TEXT NOT NULL,
    to_chunk_id TEXT NOT NULL,
    relationship TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    FOREIGN KEY (to_chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE
);

-- Graph traversal indexes
CREATE INDEX idx_deps_from ON dependencies(from_chunk_id);
CREATE INDEX idx_deps_to ON dependencies(to_chunk_id);
CREATE INDEX idx_deps_relationship ON dependencies(relationship);

-- Unique constraint: one relationship per chunk pair
CREATE UNIQUE INDEX idx_deps_unique ON dependencies(from_chunk_id, to_chunk_id, relationship);

-- 5. File metadata table (for incremental updates)
CREATE TABLE IF NOT EXISTS file_metadata (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    last_analyzed TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (repo_id) REFERENCES repositories(repo_id) ON DELETE CASCADE,
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
);

-- File lookup index
CREATE UNIQUE INDEX idx_file_metadata_snapshot_file ON file_metadata(repo_id, snapshot_id, file_path);
CREATE INDEX idx_file_metadata_hash ON file_metadata(content_hash);

-- PostgreSQL-specific optimizations
-- Enable auto-vacuum for better performance
ALTER TABLE chunks SET (autovacuum_vacuum_scale_factor = 0.01);
ALTER TABLE dependencies SET (autovacuum_vacuum_scale_factor = 0.01);

-- Add table comments for documentation
COMMENT ON TABLE repositories IS 'RFC-074: Repository metadata';
COMMENT ON TABLE snapshots IS 'RFC-074: Git commit/branch snapshots';
COMMENT ON TABLE chunks IS 'RFC-074: Code chunks with FQN and content-addressable storage';
COMMENT ON TABLE dependencies IS 'RFC-074: Dependency graph edges';
COMMENT ON TABLE file_metadata IS 'RFC-074: File-level tracking for incremental updates';

COMMENT ON COLUMN chunks.content_hash IS 'SHA256 hash for content-addressable storage';
COMMENT ON COLUMN chunks.is_deleted IS 'Soft delete flag (RFC-074 design principle)';
COMMENT ON COLUMN chunks.attrs IS 'Extensible metadata as JSONB';
