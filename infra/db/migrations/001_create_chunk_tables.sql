-- Chunk storage table with file+line mapping support
--
-- This migration creates the chunks table with optimized indexes for:
-- 1. Chunk CRUD operations
-- 2. Zoekt file+line → chunk mapping
-- 3. Repository/snapshot queries
-- 4. Incremental updates (content_hash, version tracking)

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,

    -- Hierarchy
    project_id TEXT,
    module_path TEXT,
    file_path TEXT,
    parent_id TEXT,

    -- Chunk metadata
    kind TEXT NOT NULL,  -- repo, project, module, file, class, function, service, etc
    fqn TEXT NOT NULL,   -- Fully qualified name
    language TEXT,
    symbol_visibility TEXT,  -- public, internal, private

    -- Symbol mapping
    symbol_id TEXT,
    symbol_owner_id TEXT,

    -- Source location (critical for Zoekt mapping)
    start_line INTEGER,
    end_line INTEGER,

    -- Span drift tracking (Phase B)
    original_start_line INTEGER,
    original_end_line INTEGER,

    -- Incremental update tracking (Phase A)
    content_hash TEXT,  -- Hash of chunk code for change detection
    version INTEGER NOT NULL DEFAULT 1,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    last_indexed_commit TEXT,

    -- LLM-generated content
    summary TEXT,
    importance REAL DEFAULT 0.0,

    -- Extensible attributes
    attrs JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for Zoekt file+line → chunk mapping (CRITICAL)
-- This enables fast lookup: WHERE repo_id = ? AND file_path = ? AND start_line <= ? AND end_line >= ?
CREATE INDEX IF NOT EXISTS idx_chunks_file_span
ON chunks (repo_id, file_path, start_line, end_line);

-- Index for repository queries
CREATE INDEX IF NOT EXISTS idx_chunks_repo_snapshot
ON chunks (repo_id, snapshot_id);

-- Index for symbol queries
CREATE INDEX IF NOT EXISTS idx_chunks_symbol
ON chunks (symbol_id)
WHERE symbol_id IS NOT NULL;

-- Index for FQN queries
CREATE INDEX IF NOT EXISTS idx_chunks_fqn
ON chunks (fqn)
WHERE fqn IS NOT NULL;

-- Index for file-level chunks (fallback)
CREATE INDEX IF NOT EXISTS idx_chunks_file
ON chunks (repo_id, file_path, kind)
WHERE kind = 'file';

-- Index for content hash (incremental update optimization)
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash
ON chunks (repo_id, file_path, content_hash)
WHERE content_hash IS NOT NULL;

-- Index for parent-child hierarchy queries
CREATE INDEX IF NOT EXISTS idx_chunks_parent
ON chunks (parent_id)
WHERE parent_id IS NOT NULL;

-- Index for non-deleted chunks (filter deleted in queries)
CREATE INDEX IF NOT EXISTS idx_chunks_active
ON chunks (repo_id, snapshot_id, is_deleted)
WHERE is_deleted = FALSE;

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_chunks_updated_at
BEFORE UPDATE ON chunks
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Comments
COMMENT ON TABLE chunks IS 'Chunk storage with file+line mapping for Zoekt integration';
COMMENT ON INDEX idx_chunks_file_span IS 'Critical index for Zoekt file+line → chunk mapping';
