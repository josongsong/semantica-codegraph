-- CodeGraph Database Schema

-- Nodes table
CREATE TABLE IF NOT EXISTS nodes (
    id VARCHAR(255) PRIMARY KEY,
    type VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    path TEXT,
    language VARCHAR(50),
    start_line INTEGER,
    end_line INTEGER,
    content TEXT,
    metadata JSONB,
    file_hash VARCHAR(64),
    signature TEXT,
    docstring TEXT,
    level INTEGER DEFAULT 0,
    embedding_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Edges table
CREATE TABLE IF NOT EXISTS edges (
    id VARCHAR(255) PRIMARY KEY,
    type VARCHAR(50) NOT NULL,
    source_id VARCHAR(255) NOT NULL,
    target_id VARCHAR(255) NOT NULL,
    weight FLOAT DEFAULT 1.0,
    metadata JSONB,
    call_site_line INTEGER,
    import_type VARCHAR(50),
    usage_count INTEGER DEFAULT 1,
    reference_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES nodes(id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_nodes_path ON nodes(path);
CREATE INDEX IF NOT EXISTS idx_nodes_language ON nodes(language);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);
CREATE INDEX IF NOT EXISTS idx_edges_source_type ON edges(source_id, type);
CREATE INDEX IF NOT EXISTS idx_edges_target_type ON edges(target_id, type);

-- Full-text search index (PostgreSQL)
CREATE INDEX IF NOT EXISTS idx_nodes_content_fts ON nodes USING gin(to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_nodes_name_fts ON nodes USING gin(to_tsvector('english', name));
