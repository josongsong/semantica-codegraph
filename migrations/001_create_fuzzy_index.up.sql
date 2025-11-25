-- Migration: 001 - Create Fuzzy Identifier Index
-- Description: Creates PostgreSQL pg_trgm-based fuzzy search for identifiers
-- Dependencies: PostgreSQL with pg_trgm extension
-- Author: Semantica Codegraph
-- Date: 2025-01-24

-- ============================================================
-- Enable pg_trgm Extension
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- Create fuzzy_identifiers Table
-- ============================================================

CREATE TABLE IF NOT EXISTS fuzzy_identifiers (
    id SERIAL PRIMARY KEY,
    repo_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    file_path TEXT,
    symbol_id TEXT,
    identifier TEXT NOT NULL,
    kind TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT fuzzy_identifiers_identifier_not_empty CHECK (identifier <> '')
);

-- ============================================================
-- Create Indexes
-- ============================================================

-- Composite index for repo and snapshot filtering
CREATE INDEX IF NOT EXISTS idx_fuzzy_repo_snapshot
ON fuzzy_identifiers(repo_id, snapshot_id);

-- Index for chunk_id lookups (used in delete/upsert)
CREATE INDEX IF NOT EXISTS idx_fuzzy_chunk
ON fuzzy_identifiers(chunk_id);

-- GIN trigram index for fuzzy matching (core search index)
CREATE INDEX IF NOT EXISTS idx_fuzzy_identifier_trgm
ON fuzzy_identifiers
USING GIN (identifier gin_trgm_ops);

-- Optional: Index on identifier kind for filtering
CREATE INDEX IF NOT EXISTS idx_fuzzy_kind
ON fuzzy_identifiers(kind)
WHERE kind IS NOT NULL;

-- Optional: GIN index on metadata for JSON queries
CREATE INDEX IF NOT EXISTS idx_fuzzy_metadata
ON fuzzy_identifiers
USING GIN (metadata jsonb_path_ops);

-- ============================================================
-- Comments
-- ============================================================

COMMENT ON TABLE fuzzy_identifiers IS
'Fuzzy identifier search index using PostgreSQL pg_trgm for typo-tolerant matching';

COMMENT ON COLUMN fuzzy_identifiers.repo_id IS
'Repository identifier';

COMMENT ON COLUMN fuzzy_identifiers.snapshot_id IS
'Git commit hash or snapshot identifier';

COMMENT ON COLUMN fuzzy_identifiers.chunk_id IS
'Chunk ID from the chunk store';

COMMENT ON COLUMN fuzzy_identifiers.identifier IS
'Searchable identifier (function name, class name, variable, etc.)';

COMMENT ON COLUMN fuzzy_identifiers.kind IS
'Identifier kind (function, class, variable, fqn_part, extracted)';

COMMENT ON COLUMN fuzzy_identifiers.metadata IS
'Additional metadata (fqn, node_type, etc.)';

COMMENT ON INDEX idx_fuzzy_identifier_trgm IS
'GIN trigram index for fast fuzzy matching using similarity operator (%)';

-- ============================================================
-- Grant Permissions (adjust as needed for your environment)
-- ============================================================

-- Example: Grant to application user
-- GRANT SELECT, INSERT, UPDATE, DELETE ON fuzzy_identifiers TO semantica_app;
-- GRANT USAGE, SELECT ON SEQUENCE fuzzy_identifiers_id_seq TO semantica_app;
