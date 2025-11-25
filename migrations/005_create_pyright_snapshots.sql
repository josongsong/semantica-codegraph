-- Migration: 005_create_pyright_snapshots
-- RFC-023 M1: Pyright Semantic Snapshot Storage
-- Date: 2024-11-25

-- Create table for storing Pyright semantic snapshots
CREATE TABLE IF NOT EXISTS pyright_semantic_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    data JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Index for fast project-based queries (most recent first)
CREATE INDEX IF NOT EXISTS idx_snapshots_project_timestamp
ON pyright_semantic_snapshots(project_id, timestamp DESC);

-- Index for snapshot_id lookups (already primary key, but explicit)
CREATE INDEX IF NOT EXISTS idx_snapshots_id
ON pyright_semantic_snapshots(snapshot_id);

-- Comments
COMMENT ON TABLE pyright_semantic_snapshots IS 'RFC-023 M1: Stores Pyright semantic analysis snapshots';
COMMENT ON COLUMN pyright_semantic_snapshots.snapshot_id IS 'Unique snapshot identifier (e.g., snapshot-1732545600)';
COMMENT ON COLUMN pyright_semantic_snapshots.project_id IS 'Project identifier (repository name or ID)';
COMMENT ON COLUMN pyright_semantic_snapshots.timestamp IS 'Snapshot creation timestamp';
COMMENT ON COLUMN pyright_semantic_snapshots.data IS 'Snapshot data as JSONB (typing_info, files, etc.)';
COMMENT ON COLUMN pyright_semantic_snapshots.created_at IS 'Record creation timestamp';
