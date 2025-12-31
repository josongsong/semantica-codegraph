"""
Memory Store Database Schema

Table creation and schema management for PostgresMemoryStore.
"""

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


async def create_memory_tables(db) -> None:
    """
    Create memory tables if not exist.

    Uses transaction to ensure atomic schema creation.
    All tables are created or none (rollback on failure).
    """
    try:
        await _create_episodes_table(db)
        await _create_bug_patterns_table(db)
        await _create_code_patterns_table(db)
        await _create_project_knowledge_table(db)
        await _create_user_preferences_table(db)
        await _create_graph_memory_tables(db)
        await _create_triggers(db)
        await _create_code_rules_table(db)

        logger.info("Memory tables created/verified successfully")

    except Exception as e:
        logger.error(f"Failed to create memory tables: {e}")
        raise RuntimeError(f"Memory schema initialization failed: {e}") from e


async def _create_episodes_table(db) -> None:
    """Create episodes table and indexes."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_episodes (
            id UUID PRIMARY KEY,
            project_id VARCHAR(255) NOT NULL,
            session_id UUID NOT NULL,
            task_type VARCHAR(50) NOT NULL,
            task_description TEXT NOT NULL,
            task_description_tsv TSVECTOR,
            task_complexity FLOAT DEFAULT 0.5,
            files_involved JSONB DEFAULT '[]',
            symbols_involved JSONB DEFAULT '[]',
            error_types JSONB DEFAULT '[]',
            stack_trace_signature TEXT,
            plan_summary TEXT,
            steps_count INT DEFAULT 0,
            tools_used JSONB DEFAULT '[]',
            key_decisions JSONB DEFAULT '[]',
            pivots JSONB DEFAULT '[]',
            outcome_status VARCHAR(50) DEFAULT 'unknown',
            patches JSONB DEFAULT '[]',
            tests_passed BOOLEAN DEFAULT FALSE,
            user_feedback VARCHAR(20),
            problem_pattern TEXT,
            solution_pattern TEXT,
            gotchas JSONB DEFAULT '[]',
            tips JSONB DEFAULT '[]',
            duration_ms FLOAT DEFAULT 0,
            tokens_used INT DEFAULT 0,
            retrieval_count INT DEFAULT 0,
            usefulness_score FLOAT DEFAULT 0.5,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """
    )

    # Create indexes for episodes
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_episodes_project
        ON memory_episodes(project_id)
    """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_episodes_task_type
        ON memory_episodes(task_type)
    """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_episodes_outcome
        ON memory_episodes(outcome_status)
    """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_episodes_created
        ON memory_episodes(created_at DESC)
    """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_episodes_usefulness
        ON memory_episodes(usefulness_score DESC)
    """
    )

    # Full-text search index
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_episodes_fts
        ON memory_episodes USING GIN(task_description_tsv)
    """
    )

    # GIN indexes for JSONB arrays
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_episodes_files
        ON memory_episodes USING GIN(files_involved)
    """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_episodes_errors
        ON memory_episodes USING GIN(error_types)
    """
    )


async def _create_bug_patterns_table(db) -> None:
    """Create bug patterns table and indexes."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_bug_patterns (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            error_types JSONB DEFAULT '[]',
            error_message_patterns JSONB DEFAULT '[]',
            stack_trace_patterns JSONB DEFAULT '[]',
            code_patterns JSONB DEFAULT '[]',
            typical_file_types JSONB DEFAULT '[]',
            typical_frameworks JSONB DEFAULT '[]',
            common_causes JSONB DEFAULT '[]',
            solutions JSONB DEFAULT '[]',
            occurrence_count INT DEFAULT 0,
            resolution_count INT DEFAULT 0,
            avg_resolution_time_ms FLOAT DEFAULT 0,
            related_pattern_ids JSONB DEFAULT '[]',
            last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """
    )

    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_bug_patterns_errors
        ON memory_bug_patterns USING GIN(error_types)
    """
    )


async def _create_code_patterns_table(db) -> None:
    """Create code patterns table."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_code_patterns (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            category VARCHAR(50) NOT NULL,
            ast_pattern TEXT,
            code_smell TEXT,
            metrics_threshold JSONB DEFAULT '{}',
            transformation_description TEXT,
            before_template TEXT,
            after_template TEXT,
            template_variables JSONB DEFAULT '[]',
            applicable_languages JSONB DEFAULT '[]',
            prerequisites JSONB DEFAULT '[]',
            contraindications JSONB DEFAULT '[]',
            readability_impact FLOAT DEFAULT 0,
            performance_impact FLOAT DEFAULT 0,
            maintainability_impact FLOAT DEFAULT 0,
            testability_impact FLOAT DEFAULT 0,
            application_count INT DEFAULT 0,
            success_rate FLOAT DEFAULT 0.5,
            avg_improvement FLOAT DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """
    )


async def _create_project_knowledge_table(db) -> None:
    """Create project knowledge table."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_project_knowledge (
            project_id VARCHAR(255) PRIMARY KEY,
            architecture_type VARCHAR(100) DEFAULT 'monolith',
            main_directories JSONB DEFAULT '[]',
            entry_points JSONB DEFAULT '[]',
            config_files JSONB DEFAULT '[]',
            naming_conventions JSONB DEFAULT '{}',
            file_organization TEXT,
            import_style TEXT,
            testing_patterns JSONB DEFAULT '[]',
            documentation_style TEXT,
            languages JSONB DEFAULT '[]',
            frameworks JSONB DEFAULT '[]',
            testing_frameworks JSONB DEFAULT '[]',
            build_tools JSONB DEFAULT '[]',
            frequently_modified JSONB DEFAULT '[]',
            high_complexity JSONB DEFAULT '[]',
            bug_prone JSONB DEFAULT '[]',
            critical_paths JSONB DEFAULT '[]',
            common_issues JSONB DEFAULT '[]',
            preferred_solutions JSONB DEFAULT '{}',
            avoid_patterns JSONB DEFAULT '[]',
            review_focus JSONB DEFAULT '[]',
            total_sessions INT DEFAULT 0,
            total_tasks INT DEFAULT 0,
            success_rate FLOAT DEFAULT 0.5,
            common_task_types JSONB DEFAULT '{}',
            last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """
    )


async def _create_user_preferences_table(db) -> None:
    """Create user preferences table."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_user_preferences (
            user_id VARCHAR(255) PRIMARY KEY DEFAULT 'default',
            verbosity VARCHAR(20) DEFAULT 'moderate',
            comment_style VARCHAR(20) DEFAULT 'minimal',
            variable_naming VARCHAR(20) DEFAULT 'descriptive',
            function_size VARCHAR(20) DEFAULT 'medium',
            explanation_depth VARCHAR(20) DEFAULT 'moderate',
            confirmation_frequency VARCHAR(20) DEFAULT 'important',
            proactivity VARCHAR(20) DEFAULT 'moderate',
            preferred_test_approach VARCHAR(20) DEFAULT 'after',
            patch_style VARCHAR(20) DEFAULT 'minimal',
            refactoring_aggressiveness VARCHAR(20) DEFAULT 'moderate',
            frequently_accepted JSONB DEFAULT '[]',
            frequently_rejected JSONB DEFAULT '[]',
            custom_shortcuts JSONB DEFAULT '{}',
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """
    )


async def _create_graph_memory_tables(db) -> None:
    """Create graph memory tables (entities and relationships)."""
    # Entities table (Mem0-style)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_entities (
            id UUID PRIMARY KEY,
            project_id VARCHAR(255) NOT NULL,
            entity_type VARCHAR(100) NOT NULL,
            name VARCHAR(500) NOT NULL,
            properties JSONB DEFAULT '{}',
            mention_count INT DEFAULT 1,
            last_mentioned TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(project_id, entity_type, name)
        )
    """
    )

    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_entities_project
        ON memory_entities(project_id)
    """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_entities_type
        ON memory_entities(entity_type)
    """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_entities_name
        ON memory_entities(name)
    """
    )

    # Graph memory - Relationships table
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_relationships (
            id UUID PRIMARY KEY,
            project_id VARCHAR(255) NOT NULL,
            source_entity_id UUID NOT NULL REFERENCES memory_entities(id) ON DELETE CASCADE,
            target_entity_id UUID NOT NULL REFERENCES memory_entities(id) ON DELETE CASCADE,
            relationship_type VARCHAR(100) NOT NULL,
            properties JSONB DEFAULT '{}',
            weight FLOAT DEFAULT 1.0,
            occurrence_count INT DEFAULT 1,
            last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(source_entity_id, target_entity_id, relationship_type)
        )
    """
    )

    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_relationships_source
        ON memory_relationships(source_entity_id)
    """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_relationships_target
        ON memory_relationships(target_entity_id)
    """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_relationships_type
        ON memory_relationships(relationship_type)
    """
    )


async def _create_triggers(db) -> None:
    """Create triggers for automatic data updates."""
    # Trigger for updating tsvector
    await db.execute(
        """
        CREATE OR REPLACE FUNCTION update_episode_tsv()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.task_description_tsv := to_tsvector('english', COALESCE(NEW.task_description, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """
    )

    # Check if trigger exists before creating
    trigger_exists = await db.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM pg_trigger
            WHERE tgname = 'trg_episode_tsv'
        )
    """
    )

    if not trigger_exists:
        await db.execute(
            """
            CREATE TRIGGER trg_episode_tsv
            BEFORE INSERT OR UPDATE ON memory_episodes
            FOR EACH ROW EXECUTE FUNCTION update_episode_tsv()
        """
        )


async def _create_code_rules_table(db) -> None:
    """Create code_rules table if not exists."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_code_rules (
            id UUID PRIMARY KEY,
            project_id VARCHAR(255) DEFAULT 'global',
            name VARCHAR(255) NOT NULL,
            description TEXT DEFAULT '',
            category VARCHAR(50) NOT NULL,
            before_pattern TEXT DEFAULT '',
            after_pattern TEXT DEFAULT '',
            pattern_type VARCHAR(20) DEFAULT 'literal',
            languages JSONB DEFAULT '["python"]',
            confidence FLOAT DEFAULT 0.5,
            observation_count INT DEFAULT 1,
            success_count INT DEFAULT 0,
            failure_count INT DEFAULT 0,
            min_confidence_threshold FLOAT DEFAULT 0.3,
            promotion_threshold FLOAT DEFAULT 0.8,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
        """
    )

    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_code_rules_project
        ON memory_code_rules(project_id)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_code_rules_category
        ON memory_code_rules(category)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_code_rules_confidence
        ON memory_code_rules(confidence DESC)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_code_rules_name
        ON memory_code_rules(name)
        """
    )
