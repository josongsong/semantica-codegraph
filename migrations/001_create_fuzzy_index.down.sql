-- Migration: 001 - Rollback Fuzzy Identifier Index
-- Description: Drops fuzzy_identifiers table and related indexes
-- Author: Semantica Codegraph
-- Date: 2025-01-24

-- ============================================================
-- Drop Indexes
-- ============================================================

DROP INDEX IF EXISTS idx_fuzzy_metadata;
DROP INDEX IF EXISTS idx_fuzzy_kind;
DROP INDEX IF EXISTS idx_fuzzy_identifier_trgm;
DROP INDEX IF EXISTS idx_fuzzy_chunk;
DROP INDEX IF EXISTS idx_fuzzy_repo_snapshot;

-- ============================================================
-- Drop Table
-- ============================================================

DROP TABLE IF EXISTS fuzzy_identifiers;

-- ============================================================
-- Note: pg_trgm Extension
-- ============================================================

-- We do NOT drop the pg_trgm extension as it may be used by other tables
-- If you need to drop it, uncomment the following line:
-- DROP EXTENSION IF EXISTS pg_trgm;
