-- Lexical Index metadata tables
--
-- Tracks Zoekt indexing state and jobs for snapshot consistency.

-- Lexical index snapshots (tracks Zoekt index state per repo+snapshot)
CREATE TABLE IF NOT EXISTS lexical_index_snapshots (
    repo_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,  -- 엔진 공통 snapshot (예: commit:abc12345)
    backend TEXT NOT NULL,       -- 'zoekt'
    index_version TEXT NOT NULL, -- Zoekt index directory or identifier
    is_ready BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (repo_id, snapshot_id, backend)
);

-- Index for ready state queries
CREATE INDEX IF NOT EXISTS idx_lexical_snapshots_ready
ON lexical_index_snapshots (repo_id, backend, is_ready);

-- Lexical index jobs (tracks indexing job status)
CREATE TABLE IF NOT EXISTS lexical_index_jobs (
    job_id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    backend TEXT NOT NULL,     -- 'zoekt'
    status TEXT NOT NULL,      -- PENDING, RUNNING, SUCCESS, FAILED
    log_path TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_snapshot
        FOREIGN KEY (repo_id, snapshot_id, backend)
        REFERENCES lexical_index_snapshots (repo_id, snapshot_id, backend)
        ON DELETE CASCADE
);

-- Index for job status queries
CREATE INDEX IF NOT EXISTS idx_lexical_jobs_status
ON lexical_index_jobs (repo_id, status, created_at);

-- Update timestamp trigger for snapshots
CREATE TRIGGER update_lexical_snapshots_updated_at
BEFORE UPDATE ON lexical_index_snapshots
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Comments
COMMENT ON TABLE lexical_index_snapshots IS 'Zoekt index state tracking per repo+snapshot';
COMMENT ON TABLE lexical_index_jobs IS 'Zoekt indexing job status tracking';
COMMENT ON COLUMN lexical_index_snapshots.snapshot_id IS 'Engine-wide snapshot ID (commit:abc12345)';
COMMENT ON COLUMN lexical_index_snapshots.is_ready IS 'True only after Zoekt indexing completes';
