-- Migration: 002 - Rollback Domain Metadata Index
-- Description: Drops domain_documents table, trigger, function, and related indexes
-- Author: Semantica Codegraph
-- Date: 2025-01-24

-- ============================================================
-- Drop Trigger
-- ============================================================

DROP TRIGGER IF EXISTS domain_documents_tsvector_update ON domain_documents;

-- ============================================================
-- Drop Function
-- ============================================================

DROP FUNCTION IF EXISTS domain_documents_tsvector_update_trigger();

-- ============================================================
-- Drop Indexes
-- ============================================================

DROP INDEX IF EXISTS idx_domain_metadata;
DROP INDEX IF EXISTS idx_domain_title;
DROP INDEX IF EXISTS idx_domain_content_fts;
DROP INDEX IF EXISTS idx_domain_type;
DROP INDEX IF EXISTS idx_domain_chunk;
DROP INDEX IF EXISTS idx_domain_repo_snapshot;

-- ============================================================
-- Drop Table
-- ============================================================

DROP TABLE IF EXISTS domain_documents;
