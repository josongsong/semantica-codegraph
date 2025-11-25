-- RepoMap storage tables
--
-- This migration creates RepoMap tables for storing project structure maps with:
-- 1. Hierarchical tree structure (repo → dir → file → symbol)
-- 2. Importance metrics (PageRank, LOC, change frequency)
-- 3. LLM summaries for navigation
-- 4. Fast queries for Retriever/Index layers

-- Snapshots metadata table
CREATE TABLE IF NOT EXISTS repomap_snapshots (
    repo_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    root_node_id TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '1.0',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (repo_id, snapshot_id)
);

-- Nodes table with JSONB for flexibility
CREATE TABLE IF NOT EXISTS repomap_nodes (
    id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,

    -- Node metadata
    kind TEXT NOT NULL,  -- repo, project, module, dir, file, class, function, symbol
    name TEXT NOT NULL,
    path TEXT,           -- File/directory path (for file/dir nodes)
    fqn TEXT,            -- Fully qualified name (for symbol nodes)

    -- Tree structure
    parent_id TEXT,
    children_ids TEXT[] NOT NULL DEFAULT '{}',
    depth INTEGER NOT NULL DEFAULT 0,

    -- Cross-references
    chunk_ids TEXT[] NOT NULL DEFAULT '{}',
    graph_node_ids TEXT[] NOT NULL DEFAULT '{}',

    -- Metrics (stored as JSONB for flexibility)
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- metrics structure:
    --   {
    --     "loc": 100,
    --     "symbol_count": 10,
    --     "edge_degree": 5,
    --     "pagerank": 0.85,
    --     "change_freq": 0.3,
    --     "hot_score": 0.5,
    --     "error_score": 0.1,
    --     "importance": 0.75,
    --     "drift_score": 0.0
    --   }

    -- Summary (stored as JSONB for flexibility)
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- summary structure:
    --   {
    --     "title": "One-line summary",
    --     "body": "Detailed summary (2-3 sentences)",
    --     "tags": ["indexing", "pipeline"],
    --     "text": "Full text for vector index"
    --   }

    -- Metadata
    language TEXT,
    is_entrypoint BOOLEAN NOT NULL DEFAULT FALSE,
    is_test BOOLEAN NOT NULL DEFAULT FALSE,
    attrs JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Foreign key to snapshot
    CONSTRAINT fk_repomap_nodes_snapshot
      FOREIGN KEY (repo_id, snapshot_id)
      REFERENCES repomap_snapshots (repo_id, snapshot_id)
      ON DELETE CASCADE
);

-- ============================================================
-- Indexes for Performance
-- ============================================================

-- Index for repo/snapshot queries (most common query pattern)
CREATE INDEX IF NOT EXISTS idx_repomap_nodes_repo_snapshot
  ON repomap_nodes (repo_id, snapshot_id);

-- Index for tree traversal (get children of a node)
CREATE INDEX IF NOT EXISTS idx_repomap_nodes_parent
  ON repomap_nodes (repo_id, snapshot_id, parent_id);

-- Index for kind + path queries (e.g., "get all file nodes in src/")
CREATE INDEX IF NOT EXISTS idx_repomap_nodes_kind_path
  ON repomap_nodes (repo_id, snapshot_id, kind, path);

-- Index for FQN queries (symbol lookup)
CREATE INDEX IF NOT EXISTS idx_repomap_nodes_fqn
  ON repomap_nodes (repo_id, snapshot_id, fqn)
  WHERE fqn IS NOT NULL;

-- Index for importance-based sorting (get top K nodes by importance)
CREATE INDEX IF NOT EXISTS idx_repomap_nodes_importance
  ON repomap_nodes (
      repo_id,
      snapshot_id,
      ((metrics->>'importance')::double precision) DESC NULLS LAST
  );

-- Index for entrypoint queries (find all entrypoints)
CREATE INDEX IF NOT EXISTS idx_repomap_nodes_entrypoint
  ON repomap_nodes (repo_id, snapshot_id, is_entrypoint)
  WHERE is_entrypoint = TRUE;

-- GIN index for summary tags (fast tag-based search)
CREATE INDEX IF NOT EXISTS idx_repomap_nodes_summary_tags_gin
  ON repomap_nodes USING GIN ((summary->'tags'));

-- Optional: Path fuzzy search using pg_trgm (enable if needed)
-- Requires: CREATE EXTENSION IF NOT EXISTS pg_trgm;
-- CREATE INDEX IF NOT EXISTS idx_repomap_nodes_path_trgm
--   ON repomap_nodes USING GIN (path gin_trgm_ops)
--   WHERE path IS NOT NULL;

-- ============================================================
-- Triggers
-- ============================================================

-- Update timestamp trigger (reuse function from chunks migration)
CREATE TRIGGER update_repomap_nodes_updated_at
  BEFORE UPDATE ON repomap_nodes
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- Comments
-- ============================================================

COMMENT ON TABLE repomap_snapshots IS 'RepoMap snapshot metadata';
COMMENT ON TABLE repomap_nodes IS 'RepoMap tree nodes with metrics and summaries';
COMMENT ON INDEX idx_repomap_nodes_importance IS 'Index for get_topk_by_importance queries';
COMMENT ON INDEX idx_repomap_nodes_summary_tags_gin IS 'GIN index for fast tag-based filtering';
