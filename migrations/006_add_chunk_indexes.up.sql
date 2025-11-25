-- Migration: Add performance-critical indexes for chunks table
--
-- These indexes are essential for query performance on large repositories (50K+ chunks).
-- Without them, many queries will perform full table scans, causing 100-1000x slowdowns.

-- Index 1: File span lookup (Zoekt integration - file+line → chunk mapping)
-- Used by: find_chunk_by_file_and_line()
-- Benefit: O(log n) instead of O(n) for line-based chunk lookups
CREATE INDEX IF NOT EXISTS idx_chunks_file_span
ON chunks(repo_id, file_path, start_line, end_line)
WHERE is_deleted = FALSE;

-- Index 2: Repository snapshot queries
-- Used by: find_chunks_by_repo(), get_chunks_by_file()
-- Benefit: Fast filtering by repo and snapshot
CREATE INDEX IF NOT EXISTS idx_chunks_repo_snapshot
ON chunks(repo_id, snapshot_id)
WHERE is_deleted = FALSE;

-- Index 3: Content hash lookup (incremental updates - change detection)
-- Used by: ChunkIncrementalRefresher._compare_chunks(), rename detection
-- Benefit: O(1) content deduplication and rename detection
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash
ON chunks(repo_id, file_path, content_hash)
WHERE is_deleted = FALSE AND content_hash IS NOT NULL;

-- Index 4: Symbol lookup (for symbol-based queries)
-- Used by: Symbol search and navigation
-- Benefit: Fast symbol-based chunk retrieval
CREATE INDEX IF NOT EXISTS idx_chunks_symbol
ON chunks(symbol_id)
WHERE is_deleted = FALSE AND symbol_id IS NOT NULL;

COMMENT ON INDEX idx_chunks_file_span IS
'Zoekt integration: Maps file+line to chunk (function > class > file priority)';

COMMENT ON INDEX idx_chunks_repo_snapshot IS
'Repository queries: Fast filtering by repo and snapshot';

COMMENT ON INDEX idx_chunks_content_hash IS
'Incremental updates: Content-based deduplication and rename detection';

COMMENT ON INDEX idx_chunks_symbol IS
'Symbol navigation: Fast symbol-based chunk retrieval';
