-- v8.1 Experience Store Schema
-- PostgreSQL Migration

-- Agent Experience 테이블
CREATE TABLE IF NOT EXISTS agent_experience (
    id SERIAL PRIMARY KEY,
    
    -- Problem
    problem_description TEXT NOT NULL,
    problem_type VARCHAR(50) NOT NULL,
    
    -- Strategy
    strategy_id VARCHAR(100),
    strategy_type VARCHAR(100) NOT NULL,
    
    -- Code References (Qdrant)
    code_chunk_ids TEXT[] NOT NULL DEFAULT '{}',
    file_paths TEXT[] NOT NULL DEFAULT '{}',
    
    -- Results
    success BOOLEAN NOT NULL DEFAULT FALSE,
    tot_score FLOAT NOT NULL DEFAULT 0.0,
    reflection_verdict VARCHAR(50),
    
    -- Metrics
    execution_time_ms FLOAT,
    tokens_used INTEGER,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Strategy Results 테이블
CREATE TABLE IF NOT EXISTS strategy_results (
    id SERIAL PRIMARY KEY,
    experience_id INTEGER REFERENCES agent_experience(id) ON DELETE CASCADE,
    
    -- Strategy
    strategy_id VARCHAR(100) NOT NULL,
    strategy_type VARCHAR(100) NOT NULL,
    
    -- Scores
    tot_score FLOAT NOT NULL,
    correctness_score FLOAT,
    quality_score FLOAT,
    security_score FLOAT,
    maintainability_score FLOAT,
    performance_score FLOAT,
    
    -- Execution
    execution_success BOOLEAN NOT NULL DEFAULT FALSE,
    execution_time_ms FLOAT,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_experience_problem_type ON agent_experience(problem_type);
CREATE INDEX IF NOT EXISTS idx_experience_success ON agent_experience(success);
CREATE INDEX IF NOT EXISTS idx_experience_created ON agent_experience(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_strategy_experience ON strategy_results(experience_id);

-- Updated trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_experience_updated_at ON agent_experience;
CREATE TRIGGER update_experience_updated_at
    BEFORE UPDATE ON agent_experience
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Comments
COMMENT ON TABLE agent_experience IS 'v8.1 Agent experiences for learning';
COMMENT ON TABLE strategy_results IS 'Individual strategy execution results';
