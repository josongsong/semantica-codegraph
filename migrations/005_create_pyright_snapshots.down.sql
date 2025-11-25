-- Migration: 005_create_pyright_snapshots (DOWN)
-- RFC-023 M1: Rollback Pyright Semantic Snapshot Storage
-- Date: 2024-11-25

-- Drop indexes
DROP INDEX IF EXISTS idx_snapshots_id;
DROP INDEX IF EXISTS idx_snapshots_project_timestamp;

-- Drop table
DROP TABLE IF EXISTS pyright_semantic_snapshots;
