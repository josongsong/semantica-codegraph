-- Migration: Create SymbolGraph storage tables
-- Purpose: Store lightweight Symbol + Relation data for persistence
-- Usage: PostgreSQLSymbolGraphAdapter

-- ============================================================
-- Symbols Table
-- ============================================================

CREATE TABLE IF NOT EXISTS symbols (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    fqn TEXT NOT NULL,
    name TEXT NOT NULL,
    span_json JSONB,
    parent_id TEXT,
    signature_id TEXT,
    type_id TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_symbols_repo_snapshot
    ON symbols(repo_id, snapshot_id);

CREATE INDEX IF NOT EXISTS idx_symbols_kind
    ON symbols(kind);

CREATE INDEX IF NOT EXISTS idx_symbols_fqn
    ON symbols USING gin(fqn gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_symbols_parent
    ON symbols(parent_id) WHERE parent_id IS NOT NULL;


-- ============================================================
-- Relations Table
-- ============================================================

CREATE TABLE IF NOT EXISTS relations (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    span_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_relations_repo_snapshot
    ON relations(repo_id, snapshot_id);

CREATE INDEX IF NOT EXISTS idx_relations_kind
    ON relations(kind);

CREATE INDEX IF NOT EXISTS idx_relations_source
    ON relations(source_id);

CREATE INDEX IF NOT EXISTS idx_relations_target
    ON relations(target_id);

CREATE INDEX IF NOT EXISTS idx_relations_source_target
    ON relations(source_id, target_id);


-- ============================================================
-- Comments
-- ============================================================

COMMENT ON TABLE symbols IS 'Lightweight code symbols (200 bytes/symbol)';
COMMENT ON COLUMN symbols.id IS 'Unique symbol identifier (FQN-based)';
COMMENT ON COLUMN symbols.kind IS 'Symbol type (file, class, function, etc.)';
COMMENT ON COLUMN symbols.fqn IS 'Fully qualified name';
COMMENT ON COLUMN symbols.span_json IS 'Source location (start/end line/col)';
COMMENT ON COLUMN symbols.parent_id IS 'Parent symbol ID (for containment)';
COMMENT ON COLUMN symbols.signature_id IS 'Signature ID (for functions)';
COMMENT ON COLUMN symbols.type_id IS 'Type ID (for variables)';

COMMENT ON TABLE relations IS 'Semantic relationships between symbols';
COMMENT ON COLUMN relations.kind IS 'Relation type (calls, imports, contains, etc.)';
COMMENT ON COLUMN relations.source_id IS 'Source symbol ID';
COMMENT ON COLUMN relations.target_id IS 'Target symbol ID';
