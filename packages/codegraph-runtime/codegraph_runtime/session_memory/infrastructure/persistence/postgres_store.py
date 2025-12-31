"""
PostgreSQL-based Memory Store

Production-ready persistent storage for memory system.
Supports:
- Episode storage with full-text search
- Semantic memory (bug patterns, code patterns, project knowledge)
- Transaction safety
- Efficient indexing

Schema management is separated into schema.py for maintainability.
"""

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from codegraph_shared.common.observability import get_logger
from codegraph_runtime.session_memory.infrastructure.persistence.schema import create_memory_tables
from codegraph_shared.infra.storage.postgres import PostgresStore

logger = get_logger(__name__)


class PostgresMemoryStore:
    """
    PostgreSQL-based memory storage.

    Tables:
    - memory_episodes: Episodic memory (task execution records)
    - memory_bug_patterns: Bug patterns and solutions
    - memory_code_patterns: Code refactoring patterns
    - memory_project_knowledge: Project-specific knowledge
    - memory_user_preferences: User preferences
    - memory_entities: Graph memory entities
    - memory_relationships: Graph memory relationships
    """

    def __init__(self, postgres_store: PostgresStore):
        """
        Initialize PostgreSQL memory store.

        Args:
            postgres_store: PostgresStore instance with connection pool
        """
        self.db = postgres_store
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize database schema."""
        if self._initialized:
            return

        await self._create_tables()
        self._initialized = True
        logger.info("PostgresMemoryStore initialized")

    async def _create_tables(self) -> None:
        """
        Create memory tables if not exist.

        Delegates to schema.py for actual table creation.
        """
        await create_memory_tables(self.db)

    # ============================================================
    # Episode Operations
    # ============================================================

    async def save_episode(self, episode: dict[str, Any]) -> str:
        """
        Save episode to database.

        Args:
            episode: Episode data dictionary

        Returns:
            Episode ID
        """
        episode_id = episode.get("id") or str(uuid4())

        await self.db.execute(
            """
            INSERT INTO memory_episodes (
                id, project_id, session_id, task_type, task_description,
                task_complexity, files_involved, symbols_involved, error_types,
                stack_trace_signature, plan_summary, steps_count, tools_used,
                key_decisions, pivots, outcome_status, patches, tests_passed,
                user_feedback, problem_pattern, solution_pattern, gotchas, tips,
                duration_ms, tokens_used, retrieval_count, usefulness_score, created_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28
            )
            ON CONFLICT (id) DO UPDATE SET
                outcome_status = EXCLUDED.outcome_status,
                retrieval_count = memory_episodes.retrieval_count + 1,
                usefulness_score = EXCLUDED.usefulness_score,
                updated_at = NOW()
            """,
            episode_id,
            episode.get("project_id", "default"),
            episode.get("session_id", str(uuid4())),
            episode.get("task_type", "unknown"),
            episode.get("task_description", ""),
            episode.get("task_complexity", 0.5),
            json.dumps(episode.get("files_involved", [])),
            json.dumps(episode.get("symbols_involved", [])),
            json.dumps(episode.get("error_types", [])),
            episode.get("stack_trace_signature"),
            episode.get("plan_summary", ""),
            episode.get("steps_count", 0),
            json.dumps(episode.get("tools_used", [])),
            json.dumps(episode.get("key_decisions", [])),
            json.dumps(episode.get("pivots", [])),
            episode.get("outcome_status", "unknown"),
            json.dumps(episode.get("patches", [])),
            episode.get("tests_passed", False),
            episode.get("user_feedback"),
            episode.get("problem_pattern", ""),
            episode.get("solution_pattern", ""),
            json.dumps(episode.get("gotchas", [])),
            json.dumps(episode.get("tips", [])),
            episode.get("duration_ms", 0),
            episode.get("tokens_used", 0),
            episode.get("retrieval_count", 0),
            episode.get("usefulness_score", 0.5),
            episode.get("created_at", datetime.now()),
        )

        logger.debug(f"Episode saved: {episode_id}")
        return episode_id

    async def get_episode(self, episode_id: str) -> dict[str, Any] | None:
        """Get episode by ID."""
        row = await self.db.fetchrow(
            "SELECT * FROM memory_episodes WHERE id = $1",
            episode_id,
        )
        return self._row_to_episode(row) if row else None

    async def find_episodes(
        self,
        project_id: str | None = None,
        task_type: str | None = None,
        outcome_status: str | None = None,
        error_type: str | None = None,
        file_path: str | None = None,
        search_text: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Find episodes with filters.

        Args:
            project_id: Filter by project
            task_type: Filter by task type
            outcome_status: Filter by outcome
            error_type: Filter by error type
            file_path: Filter by file involved
            search_text: Full-text search in description
            limit: Max results
            offset: Pagination offset

        Returns:
            List of matching episodes
        """
        conditions = []
        params = []
        param_idx = 1

        if project_id:
            conditions.append(f"project_id = ${param_idx}")
            params.append(project_id)
            param_idx += 1

        if task_type:
            conditions.append(f"task_type = ${param_idx}")
            params.append(task_type)
            param_idx += 1

        if outcome_status:
            conditions.append(f"outcome_status = ${param_idx}")
            params.append(outcome_status)
            param_idx += 1

        if error_type:
            conditions.append(f"error_types @> ${param_idx}::jsonb")
            params.append(json.dumps([error_type]))
            param_idx += 1

        if file_path:
            conditions.append(f"files_involved @> ${param_idx}::jsonb")
            params.append(json.dumps([file_path]))
            param_idx += 1

        if search_text:
            conditions.append(f"task_description_tsv @@ plainto_tsquery('english', ${param_idx})")
            params.append(search_text)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        query = f"""
            SELECT * FROM memory_episodes
            WHERE {where_clause}
            ORDER BY usefulness_score DESC, created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])

        rows = await self.db.fetch(query, *params)
        return [self._row_to_episode(row) for row in rows]

    async def update_episode_feedback(
        self,
        episode_id: str,
        helpful: bool,
        user_feedback: str | None = None,
    ) -> None:
        """Update episode feedback and usefulness score."""
        # Exponential moving average for usefulness
        alpha = 0.3
        feedback_score = 1.0 if helpful else 0.0

        await self.db.execute(
            """
            UPDATE memory_episodes
            SET usefulness_score = $1 * $2 + (1 - $1) * usefulness_score,
                user_feedback = COALESCE($3, user_feedback),
                retrieval_count = retrieval_count + 1,
                updated_at = NOW()
            WHERE id = $4
            """,
            alpha,
            feedback_score,
            user_feedback,
            episode_id,
        )

    async def increment_retrieval_count(self, episode_id: str) -> None:
        """Increment retrieval count for episode."""
        await self.db.execute(
            """
            UPDATE memory_episodes
            SET retrieval_count = retrieval_count + 1,
                updated_at = NOW()
            WHERE id = $1
            """,
            episode_id,
        )

    async def delete_episode(self, episode_id: str) -> bool:
        """Delete episode."""
        result = await self.db.execute(
            "DELETE FROM memory_episodes WHERE id = $1",
            episode_id,
        )
        return "DELETE 1" in result

    async def cleanup_old_episodes(
        self,
        max_age_days: int = 90,
        min_usefulness: float = 0.3,
        min_retrievals: int = 2,
    ) -> int:
        """
        Remove old, low-value episodes.

        Args:
            max_age_days: Max age in days
            min_usefulness: Min usefulness to keep
            min_retrievals: Min retrievals to keep

        Returns:
            Number deleted
        """
        result = await self.db.execute(
            """
            DELETE FROM memory_episodes
            WHERE created_at < NOW() - INTERVAL '%s days'
              AND usefulness_score < $1
              AND retrieval_count < $2
            """,
            max_age_days,
            min_usefulness,
            min_retrievals,
        )
        # Extract count from "DELETE N"
        count = int(result.split()[-1]) if result else 0
        logger.info(f"Cleaned up {count} old episodes")
        return count

    def _row_to_episode(self, row) -> dict[str, Any]:
        """Convert database row to episode dict."""
        if not row:
            return {}

        return {
            "id": str(row["id"]),
            "project_id": row["project_id"],
            "session_id": str(row["session_id"]),
            "task_type": row["task_type"],
            "task_description": row["task_description"],
            "task_complexity": row["task_complexity"],
            "files_involved": row["files_involved"] or [],
            "symbols_involved": row["symbols_involved"] or [],
            "error_types": row["error_types"] or [],
            "stack_trace_signature": row["stack_trace_signature"],
            "plan_summary": row["plan_summary"],
            "steps_count": row["steps_count"],
            "tools_used": row["tools_used"] or [],
            "key_decisions": row["key_decisions"] or [],
            "pivots": row["pivots"] or [],
            "outcome_status": row["outcome_status"],
            "patches": row["patches"] or [],
            "tests_passed": row["tests_passed"],
            "user_feedback": row["user_feedback"],
            "problem_pattern": row["problem_pattern"],
            "solution_pattern": row["solution_pattern"],
            "gotchas": row["gotchas"] or [],
            "tips": row["tips"] or [],
            "duration_ms": row["duration_ms"],
            "tokens_used": row["tokens_used"],
            "retrieval_count": row["retrieval_count"],
            "usefulness_score": row["usefulness_score"],
            "created_at": row["created_at"],
        }

    # ============================================================
    # Bug Pattern Operations
    # ============================================================

    async def save_bug_pattern(self, pattern: dict[str, Any]) -> str:
        """Save bug pattern."""
        pattern_id = pattern.get("id") or str(uuid4())

        await self.db.execute(
            """
            INSERT INTO memory_bug_patterns (
                id, name, error_types, error_message_patterns, stack_trace_patterns,
                code_patterns, typical_file_types, typical_frameworks, common_causes,
                solutions, occurrence_count, resolution_count, avg_resolution_time_ms,
                related_pattern_ids, last_seen
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            ON CONFLICT (id) DO UPDATE SET
                occurrence_count = memory_bug_patterns.occurrence_count + 1,
                resolution_count = EXCLUDED.resolution_count,
                avg_resolution_time_ms = EXCLUDED.avg_resolution_time_ms,
                solutions = EXCLUDED.solutions,
                last_seen = NOW()
            """,
            pattern_id,
            pattern.get("name", ""),
            json.dumps(pattern.get("error_types", [])),
            json.dumps(pattern.get("error_message_patterns", [])),
            json.dumps(pattern.get("stack_trace_patterns", [])),
            json.dumps(pattern.get("code_patterns", [])),
            json.dumps(pattern.get("typical_file_types", [])),
            json.dumps(pattern.get("typical_frameworks", [])),
            json.dumps(pattern.get("common_causes", [])),
            json.dumps(pattern.get("solutions", [])),
            pattern.get("occurrence_count", 1),
            pattern.get("resolution_count", 0),
            pattern.get("avg_resolution_time_ms", 0),
            json.dumps(pattern.get("related_pattern_ids", [])),
            datetime.now(),
        )

        return pattern_id

    async def find_bug_patterns(
        self,
        error_type: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Find bug patterns."""
        if error_type:
            rows = await self.db.fetch(
                """
                SELECT * FROM memory_bug_patterns
                WHERE error_types @> $1::jsonb
                ORDER BY occurrence_count DESC, resolution_count DESC
                LIMIT $2
                """,
                json.dumps([error_type]),
                limit,
            )
        else:
            rows = await self.db.fetch(
                """
                SELECT * FROM memory_bug_patterns
                ORDER BY occurrence_count DESC
                LIMIT $1
                """,
                limit,
            )

        return [dict(row) for row in rows]

    # ============================================================
    # Project Knowledge Operations
    # ============================================================

    async def get_project_knowledge(self, project_id: str) -> dict[str, Any] | None:
        """Get project knowledge."""
        row = await self.db.fetchrow(
            "SELECT * FROM memory_project_knowledge WHERE project_id = $1",
            project_id,
        )
        return dict(row) if row else None

    async def save_project_knowledge(self, knowledge: dict[str, Any]) -> str:
        """Save project knowledge."""
        project_id = knowledge.get("project_id", "default")

        await self.db.execute(
            """
            INSERT INTO memory_project_knowledge (
                project_id, architecture_type, main_directories, entry_points,
                config_files, naming_conventions, file_organization, import_style,
                testing_patterns, documentation_style, languages, frameworks,
                testing_frameworks, build_tools, frequently_modified, high_complexity,
                bug_prone, critical_paths, common_issues, preferred_solutions,
                avoid_patterns, review_focus, total_sessions, total_tasks,
                success_rate, common_task_types, last_updated
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                      $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, NOW())
            ON CONFLICT (project_id) DO UPDATE SET
                total_sessions = memory_project_knowledge.total_sessions + 1,
                total_tasks = memory_project_knowledge.total_tasks + EXCLUDED.total_tasks,
                success_rate = EXCLUDED.success_rate,
                common_task_types = EXCLUDED.common_task_types,
                frequently_modified = EXCLUDED.frequently_modified,
                bug_prone = EXCLUDED.bug_prone,
                common_issues = EXCLUDED.common_issues,
                last_updated = NOW()
            """,
            project_id,
            knowledge.get("architecture_type", "monolith"),
            json.dumps(knowledge.get("main_directories", [])),
            json.dumps(knowledge.get("entry_points", [])),
            json.dumps(knowledge.get("config_files", [])),
            json.dumps(knowledge.get("naming_conventions", {})),
            knowledge.get("file_organization", ""),
            knowledge.get("import_style", ""),
            json.dumps(knowledge.get("testing_patterns", [])),
            knowledge.get("documentation_style", ""),
            json.dumps(knowledge.get("languages", [])),
            json.dumps(knowledge.get("frameworks", [])),
            json.dumps(knowledge.get("testing_frameworks", [])),
            json.dumps(knowledge.get("build_tools", [])),
            json.dumps(knowledge.get("frequently_modified", [])),
            json.dumps(knowledge.get("high_complexity", [])),
            json.dumps(knowledge.get("bug_prone", [])),
            json.dumps(knowledge.get("critical_paths", [])),
            json.dumps(knowledge.get("common_issues", [])),
            json.dumps(knowledge.get("preferred_solutions", {})),
            json.dumps(knowledge.get("avoid_patterns", [])),
            json.dumps(knowledge.get("review_focus", [])),
            knowledge.get("total_sessions", 0),
            knowledge.get("total_tasks", 0),
            knowledge.get("success_rate", 0.5),
            json.dumps(knowledge.get("common_task_types", {})),
        )

        return project_id

    # ============================================================
    # Graph Memory Operations (Mem0-style Entity-Relationship)
    # ============================================================

    async def upsert_entity(
        self,
        project_id: str,
        entity_type: str,
        name: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """
        Upsert entity in graph memory.

        Args:
            project_id: Project ID
            entity_type: Type (person, file, function, concept, etc.)
            name: Entity name
            properties: Additional properties

        Returns:
            Entity ID
        """
        entity_id = str(uuid4())

        row = await self.db.fetchrow(
            """
            INSERT INTO memory_entities (id, project_id, entity_type, name, properties)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (project_id, entity_type, name) DO UPDATE SET
                properties = memory_entities.properties || EXCLUDED.properties,
                mention_count = memory_entities.mention_count + 1,
                last_mentioned = NOW()
            RETURNING id
            """,
            entity_id,
            project_id,
            entity_type,
            name,
            json.dumps(properties or {}),
        )

        return str(row["id"])

    async def add_relationship(
        self,
        project_id: str,
        source_entity_id: str,
        target_entity_id: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
        weight: float = 1.0,
    ) -> str:
        """
        Add relationship between entities.

        Args:
            project_id: Project ID
            source_entity_id: Source entity ID
            target_entity_id: Target entity ID
            relationship_type: Relationship type (uses, calls, imports, etc.)
            properties: Additional properties
            weight: Relationship weight

        Returns:
            Relationship ID
        """
        rel_id = str(uuid4())

        row = await self.db.fetchrow(
            """
            INSERT INTO memory_relationships (
                id, project_id, source_entity_id, target_entity_id,
                relationship_type, properties, weight
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (source_entity_id, target_entity_id, relationship_type) DO UPDATE SET
                weight = memory_relationships.weight + EXCLUDED.weight,
                occurrence_count = memory_relationships.occurrence_count + 1,
                properties = memory_relationships.properties || EXCLUDED.properties,
                last_seen = NOW()
            RETURNING id
            """,
            rel_id,
            project_id,
            source_entity_id,
            target_entity_id,
            relationship_type,
            json.dumps(properties or {}),
            weight,
        )

        return str(row["id"])

    async def find_entities(
        self,
        project_id: str,
        entity_type: str | None = None,
        name_pattern: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Find entities by filters."""
        conditions = ["project_id = $1"]
        params: list[Any] = [project_id]
        param_idx = 2

        if entity_type:
            conditions.append(f"entity_type = ${param_idx}")
            params.append(entity_type)
            param_idx += 1

        if name_pattern:
            conditions.append(f"name ILIKE ${param_idx}")
            params.append(f"%{name_pattern}%")
            param_idx += 1

        where_clause = " AND ".join(conditions)

        rows = await self.db.fetch(
            f"""
            SELECT * FROM memory_entities
            WHERE {where_clause}
            ORDER BY mention_count DESC, last_mentioned DESC
            LIMIT ${param_idx}
            """,
            *params,
            limit,
        )

        return [dict(row) for row in rows]

    async def get_entity_relationships(
        self,
        entity_id: str,
        direction: str = "both",
        relationship_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Get relationships for an entity.

        Args:
            entity_id: Entity ID
            direction: 'outgoing', 'incoming', or 'both'
            relationship_type: Filter by type
            limit: Max results

        Returns:
            List of relationships with entity info
        """
        conditions = []
        params: list[Any] = []
        param_idx = 1

        if direction == "outgoing":
            conditions.append(f"r.source_entity_id = ${param_idx}")
            params.append(entity_id)
            param_idx += 1
        elif direction == "incoming":
            conditions.append(f"r.target_entity_id = ${param_idx}")
            params.append(entity_id)
            param_idx += 1
        else:  # both
            conditions.append(f"(r.source_entity_id = ${param_idx} OR r.target_entity_id = ${param_idx})")
            params.append(entity_id)
            param_idx += 1

        if relationship_type:
            conditions.append(f"r.relationship_type = ${param_idx}")
            params.append(relationship_type)
            param_idx += 1

        where_clause = " AND ".join(conditions)

        rows = await self.db.fetch(
            f"""
            SELECT
                r.*,
                s.name as source_name, s.entity_type as source_type,
                t.name as target_name, t.entity_type as target_type
            FROM memory_relationships r
            JOIN memory_entities s ON r.source_entity_id = s.id
            JOIN memory_entities t ON r.target_entity_id = t.id
            WHERE {where_clause}
            ORDER BY r.weight DESC, r.occurrence_count DESC
            LIMIT ${param_idx}
            """,
            *params,
            limit,
        )

        return [dict(row) for row in rows]

    async def find_path(
        self,
        source_entity_id: str,
        target_entity_id: str,
        max_depth: int = 3,
    ) -> list[dict[str, Any]] | None:
        """
        Find shortest path between two entities using BFS.

        Args:
            source_entity_id: Start entity
            target_entity_id: End entity
            max_depth: Maximum path length

        Returns:
            Path as list of relationships, or None if not found
        """
        # Use recursive CTE for path finding
        rows = await self.db.fetch(
            """
            WITH RECURSIVE path_search AS (
                -- Base case: start from source
                SELECT
                    ARRAY[source_entity_id] as path,
                    target_entity_id as current_node,
                    1 as depth,
                    ARRAY[id] as rel_ids
                FROM memory_relationships
                WHERE source_entity_id = $1

                UNION ALL

                -- Recursive case
                SELECT
                    p.path || r.source_entity_id,
                    r.target_entity_id,
                    p.depth + 1,
                    p.rel_ids || r.id
                FROM path_search p
                JOIN memory_relationships r ON r.source_entity_id = p.current_node
                WHERE p.depth < $3
                  AND r.target_entity_id != ALL(p.path)  -- Prevent cycles
            )
            SELECT rel_ids
            FROM path_search
            WHERE current_node = $2
            ORDER BY depth
            LIMIT 1
            """,
            source_entity_id,
            target_entity_id,
            max_depth,
        )

        if not rows:
            return None

        rel_ids = rows[0]["rel_ids"]

        # Fetch full relationship details
        relationships = []
        for rel_id in rel_ids:
            rel_rows = await self.db.fetch(
                """
                SELECT
                    r.*,
                    s.name as source_name, s.entity_type as source_type,
                    t.name as target_name, t.entity_type as target_type
                FROM memory_relationships r
                JOIN memory_entities s ON r.source_entity_id = s.id
                JOIN memory_entities t ON r.target_entity_id = t.id
                WHERE r.id = $1
                """,
                rel_id,
            )
            if rel_rows:
                relationships.append(dict(rel_rows[0]))

        return relationships

    # ============================================================
    # Code Rule Operations (RFC: Learned Transformation Rules)
    # Table schema is managed in schema.py
    # ============================================================

    async def save_code_rule(self, rule: dict[str, Any], project_id: str = "global") -> str:
        """
        Save or update a code rule.

        Args:
            rule: CodeRule as dictionary
            project_id: Project scope (default 'global' for cross-project rules)

        Returns:
            Rule ID
        """
        rule_id = rule.get("id") or str(uuid4())

        await self.db.execute(
            """
            INSERT INTO memory_code_rules (
                id, project_id, name, description, category,
                before_pattern, after_pattern, pattern_type, languages,
                confidence, observation_count, success_count, failure_count,
                min_confidence_threshold, promotion_threshold
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            ON CONFLICT (id) DO UPDATE SET
                confidence = EXCLUDED.confidence,
                observation_count = EXCLUDED.observation_count,
                success_count = EXCLUDED.success_count,
                failure_count = EXCLUDED.failure_count,
                updated_at = NOW()
            """,
            rule_id,
            project_id,
            rule.get("name", ""),
            rule.get("description", ""),
            rule.get("category", "other"),
            rule.get("before_pattern", ""),
            rule.get("after_pattern", ""),
            rule.get("pattern_type", "literal"),
            json.dumps(rule.get("languages", ["python"])),
            rule.get("confidence", 0.5),
            rule.get("observation_count", 1),
            rule.get("success_count", 0),
            rule.get("failure_count", 0),
            rule.get("min_confidence_threshold", 0.3),
            rule.get("promotion_threshold", 0.8),
        )

        logger.debug(f"Code rule saved: {rule_id} ({rule.get('name')})")
        return rule_id

    async def get_code_rule(self, rule_id: str) -> dict[str, Any] | None:
        """Get code rule by ID."""
        row = await self.db.fetchrow(
            "SELECT * FROM memory_code_rules WHERE id = $1",
            rule_id,
        )
        return self._row_to_code_rule(row) if row else None

    async def find_code_rules(
        self,
        project_id: str | None = None,
        category: str | None = None,
        language: str | None = None,
        name_pattern: str | None = None,
        min_confidence: float | None = None,
        trusted_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Find code rules with filters.

        Args:
            project_id: Filter by project (None = include global)
            category: Filter by category
            language: Filter by language
            name_pattern: Filter by name pattern (ILIKE)
            min_confidence: Minimum confidence threshold
            trusted_only: Only return trusted rules (confidence >= promotion_threshold)
            limit: Max results

        Returns:
            List of matching code rules
        """
        conditions = []
        params: list[Any] = []
        param_idx = 1

        # Include global rules or specific project
        if project_id:
            conditions.append(f"(project_id = ${param_idx} OR project_id = 'global')")
            params.append(project_id)
            param_idx += 1

        if category:
            conditions.append(f"category = ${param_idx}")
            params.append(category)
            param_idx += 1

        if language:
            conditions.append(f"languages @> ${param_idx}::jsonb")
            params.append(json.dumps([language]))
            param_idx += 1

        if name_pattern:
            conditions.append(f"name ILIKE ${param_idx}")
            params.append(f"%{name_pattern}%")
            param_idx += 1

        if min_confidence is not None:
            conditions.append(f"confidence >= ${param_idx}")
            params.append(min_confidence)
            param_idx += 1

        if trusted_only:
            conditions.append("confidence >= promotion_threshold AND observation_count >= 5")

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        query = f"""
            SELECT * FROM memory_code_rules
            WHERE {where_clause}
            ORDER BY confidence DESC, observation_count DESC
            LIMIT ${param_idx}
        """
        params.append(limit)

        rows = await self.db.fetch(query, *params)
        return [self._row_to_code_rule(row) for row in rows]

    async def update_code_rule_confidence(
        self,
        rule_id: str,
        success: bool,
        ema_alpha: float = 0.2,
    ) -> dict[str, Any] | None:
        """
        Update rule confidence based on outcome.

        Uses EMA: new_confidence = α * outcome + (1-α) * old_confidence

        Args:
            rule_id: Rule ID
            success: Whether application was successful
            ema_alpha: EMA smoothing factor

        Returns:
            Updated rule or None if not found
        """
        outcome_value = 1.0 if success else 0.0

        row = await self.db.fetchrow(
            """
            UPDATE memory_code_rules
            SET confidence = $1 * $2 + (1 - $1) * confidence,
                observation_count = observation_count + 1,
                success_count = success_count + CASE WHEN $3 THEN 1 ELSE 0 END,
                failure_count = failure_count + CASE WHEN $3 THEN 0 ELSE 1 END,
                updated_at = NOW()
            WHERE id = $4
            RETURNING *
            """,
            ema_alpha,
            outcome_value,
            success,
            rule_id,
        )

        if row:
            logger.debug(
                f"Code rule confidence updated: {rule_id} (success={success}, new_confidence={row['confidence']:.3f})"
            )
            return self._row_to_code_rule(row)
        return None

    async def delete_code_rule(self, rule_id: str) -> bool:
        """Delete a code rule."""
        result = await self.db.execute(
            "DELETE FROM memory_code_rules WHERE id = $1",
            rule_id,
        )
        deleted = "DELETE 1" in result
        if deleted:
            logger.debug(f"Code rule deleted: {rule_id}")
        return deleted

    async def cleanup_weak_rules(
        self,
        project_id: str | None = None,
        min_observations: int = 3,
    ) -> int:
        """
        Remove rules with low confidence after sufficient observations.

        Args:
            project_id: Limit cleanup to project (None = all)
            min_observations: Minimum observations before removal

        Returns:
            Number of rules deleted
        """
        conditions = [
            "observation_count >= $1",
            "confidence < min_confidence_threshold",
        ]
        params: list[Any] = [min_observations]
        param_idx = 2

        if project_id:
            conditions.append(f"project_id = ${param_idx}")
            params.append(project_id)

        where_clause = " AND ".join(conditions)

        result = await self.db.execute(
            f"DELETE FROM memory_code_rules WHERE {where_clause}",
            *params,
        )

        count = int(result.split()[-1]) if result and "DELETE" in result else 0
        if count > 0:
            logger.info(f"Cleaned up {count} weak code rules")
        return count

    async def find_similar_rules(
        self,
        name: str,
        category: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Find similar rules for potential merging.

        Args:
            name: Rule name to match
            category: Category to match
            limit: Max results

        Returns:
            List of similar rules
        """
        rows = await self.db.fetch(
            """
            SELECT * FROM memory_code_rules
            WHERE category = $1
              AND (name = $2 OR name ILIKE $3)
            ORDER BY confidence DESC
            LIMIT $4
            """,
            category,
            name,
            f"%{name}%",
            limit,
        )
        return [self._row_to_code_rule(row) for row in rows]

    def _row_to_code_rule(self, row) -> dict[str, Any]:
        """Convert database row to code rule dict."""
        if not row:
            return {}

        return {
            "id": str(row["id"]),
            "project_id": row["project_id"],
            "name": row["name"],
            "description": row["description"],
            "category": row["category"],
            "before_pattern": row["before_pattern"],
            "after_pattern": row["after_pattern"],
            "pattern_type": row["pattern_type"],
            "languages": row["languages"] or ["python"],
            "confidence": row["confidence"],
            "observation_count": row["observation_count"],
            "success_count": row["success_count"],
            "failure_count": row["failure_count"],
            "min_confidence_threshold": row["min_confidence_threshold"],
            "promotion_threshold": row["promotion_threshold"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # ============================================================
    # Statistics
    # ============================================================

    async def get_statistics(self) -> dict[str, Any]:
        """Get memory store statistics."""
        episode_count = await self.db.fetchval("SELECT COUNT(*) FROM memory_episodes")
        bug_pattern_count = await self.db.fetchval("SELECT COUNT(*) FROM memory_bug_patterns")
        code_pattern_count = await self.db.fetchval("SELECT COUNT(*) FROM memory_code_patterns")
        project_count = await self.db.fetchval("SELECT COUNT(*) FROM memory_project_knowledge")
        entity_count = await self.db.fetchval("SELECT COUNT(*) FROM memory_entities")
        relationship_count = await self.db.fetchval("SELECT COUNT(*) FROM memory_relationships")

        # Code rules statistics
        code_rules_count = await self.db.fetchval("SELECT COUNT(*) FROM memory_code_rules")
        trusted_rules_count = await self.db.fetchval(
            "SELECT COUNT(*) FROM memory_code_rules WHERE confidence >= promotion_threshold AND observation_count >= 5"
        )

        return {
            "episodes": episode_count,
            "bug_patterns": bug_pattern_count,
            "code_patterns": code_pattern_count,
            "projects": project_count,
            "entities": entity_count,
            "relationships": relationship_count,
            "code_rules": code_rules_count,
            "trusted_rules": trusted_rules_count,
        }

    async def close(self) -> None:
        """Close database connection."""
        # PostgresStore manages its own pool
        pass
