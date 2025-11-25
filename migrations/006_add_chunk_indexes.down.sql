-- Rollback: Remove chunk indexes

DROP INDEX IF EXISTS idx_chunks_file_span;
DROP INDEX IF EXISTS idx_chunks_repo_snapshot;
DROP INDEX IF EXISTS idx_chunks_content_hash;
DROP INDEX IF EXISTS idx_chunks_symbol;
