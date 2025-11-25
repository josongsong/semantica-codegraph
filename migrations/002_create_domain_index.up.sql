-- Migration: 002 - Create Domain Metadata Index
-- Description: Creates PostgreSQL full-text search for documentation (README, ADR, API specs)
-- Dependencies: PostgreSQL (no additional extensions required)
-- Author: Semantica Codegraph
-- Date: 2025-01-24

-- ============================================================
-- Create domain_documents Table
-- ============================================================

CREATE TABLE IF NOT EXISTS domain_documents (
    id SERIAL PRIMARY KEY,
    repo_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    file_path TEXT,
    symbol_id TEXT,
    doc_type TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    content_vector TSVECTOR,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT domain_documents_content_not_empty CHECK (content <> ''),
    CONSTRAINT domain_documents_doc_type_valid CHECK (
        doc_type IN (
            'readme', 'changelog', 'license', 'contributing',
            'adr', 'api_spec', 'markdown_doc', 'rst_doc',
            'asciidoc', 'other'
        )
    )
);

-- ============================================================
-- Create Indexes
-- ============================================================

-- Composite index for repo and snapshot filtering
CREATE INDEX IF NOT EXISTS idx_domain_repo_snapshot
ON domain_documents(repo_id, snapshot_id);

-- Index for chunk_id lookups (used in delete/upsert)
CREATE INDEX IF NOT EXISTS idx_domain_chunk
ON domain_documents(chunk_id);

-- Index on document type for filtering
CREATE INDEX IF NOT EXISTS idx_domain_type
ON domain_documents(doc_type);

-- GIN index for full-text search (core search index)
CREATE INDEX IF NOT EXISTS idx_domain_content_fts
ON domain_documents
USING GIN (content_vector);

-- Optional: Index on title for quick title searches
CREATE INDEX IF NOT EXISTS idx_domain_title
ON domain_documents(title)
WHERE title IS NOT NULL;

-- Optional: GIN index on metadata for JSON queries
CREATE INDEX IF NOT EXISTS idx_domain_metadata
ON domain_documents
USING GIN (metadata jsonb_path_ops);

-- ============================================================
-- Create Trigger for Automatic tsvector Updates
-- ============================================================

-- Function to automatically update content_vector when content or title changes
CREATE OR REPLACE FUNCTION domain_documents_tsvector_update_trigger()
RETURNS TRIGGER AS $$
BEGIN
    NEW.content_vector := to_tsvector('english', COALESCE(NEW.title, '') || ' ' || COALESCE(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to call the function on INSERT and UPDATE
CREATE TRIGGER domain_documents_tsvector_update
BEFORE INSERT OR UPDATE ON domain_documents
FOR EACH ROW
EXECUTE FUNCTION domain_documents_tsvector_update_trigger();

-- ============================================================
-- Comments
-- ============================================================

COMMENT ON TABLE domain_documents IS
'Domain metadata index for documentation search (README, ADR, API specs) using PostgreSQL full-text search';

COMMENT ON COLUMN domain_documents.repo_id IS
'Repository identifier';

COMMENT ON COLUMN domain_documents.snapshot_id IS
'Git commit hash or snapshot identifier';

COMMENT ON COLUMN domain_documents.chunk_id IS
'Chunk ID from the chunk store';

COMMENT ON COLUMN domain_documents.doc_type IS
'Document type classification (readme, adr, api_spec, changelog, etc.)';

COMMENT ON COLUMN domain_documents.title IS
'Document title extracted from H1 header or first line';

COMMENT ON COLUMN domain_documents.content IS
'Full document content for search';

COMMENT ON COLUMN domain_documents.content_vector IS
'Automatically generated tsvector for full-text search';

COMMENT ON COLUMN domain_documents.metadata IS
'Additional metadata (fqn, node_type, importance_score, etc.)';

COMMENT ON INDEX idx_domain_content_fts IS
'GIN index for full-text search using ts_rank scoring';

COMMENT ON FUNCTION domain_documents_tsvector_update_trigger() IS
'Automatically updates content_vector on INSERT/UPDATE';

-- ============================================================
-- Example Queries
-- ============================================================

/*
-- Search for "authentication" in documentation:
SELECT chunk_id, doc_type, title,
       ts_rank(content_vector, plainto_tsquery('english', 'authentication')) AS score
FROM domain_documents
WHERE repo_id = 'my_repo'
  AND snapshot_id = 'commit123'
  AND content_vector @@ plainto_tsquery('english', 'authentication')
ORDER BY score DESC
LIMIT 10;

-- Find all ADR documents:
SELECT chunk_id, title, file_path
FROM domain_documents
WHERE repo_id = 'my_repo'
  AND snapshot_id = 'commit123'
  AND doc_type = 'adr'
ORDER BY title;

-- Full-text search with multiple terms:
SELECT chunk_id, title,
       ts_rank(content_vector, to_tsquery('english', 'API & endpoint')) AS score
FROM domain_documents
WHERE content_vector @@ to_tsquery('english', 'API & endpoint')
ORDER BY score DESC;
*/

-- ============================================================
-- Grant Permissions (adjust as needed for your environment)
-- ============================================================

-- Example: Grant to application user
-- GRANT SELECT, INSERT, UPDATE, DELETE ON domain_documents TO semantica_app;
-- GRANT USAGE, SELECT ON SEQUENCE domain_documents_id_seq TO semantica_app;
-- GRANT EXECUTE ON FUNCTION domain_documents_tsvector_update_trigger() TO semantica_app;
