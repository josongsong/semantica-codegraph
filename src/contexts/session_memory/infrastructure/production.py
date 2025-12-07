"""
Production Memory System

Integrates all memory components with production storage:
- PostgresMemoryStore for structured data
- EmbeddingMemoryStore for semantic search
- Graph memory for entity relationships

Usage:
    from src.contexts.session_memory.infrastructure.production import create_production_memory_system

    memory = await create_production_memory_system(
        postgres_store=postgres,
        qdrant_adapter=qdrant,
        embedding_provider=embedder,
    )

    # Store episode
    await memory.store_episode(episode)

    # Recall relevant memories
    memories = await memory.recall(query="how to fix authentication bug")
"""

from dataclasses import asdict
from datetime import datetime
from typing import Any

from src.common.observability import get_logger
from src.infra.storage.postgres import PostgresStore
from src.infra.vector.qdrant import QdrantAdapter

from .models import (
    Episode,
    Guidance,
    ProjectKnowledge,
    TaskStatus,
    TaskType,
)
from .persistence.embedding_store import EmbeddingMemoryStore, EmbeddingProvider
from .persistence.postgres_store import PostgresMemoryStore
from .working import WorkingMemoryManager

logger = get_logger(__name__)


class ProductionMemorySystem:
    """
    Production-ready memory system integrating all storage backends.

    Features:
    - PostgreSQL for structured storage (episodes, patterns, knowledge)
    - Qdrant for semantic similarity search
    - Graph memory for entity relationships
    - Unified API for memory operations
    """

    def __init__(
        self,
        postgres_store: PostgresMemoryStore,
        embedding_store: EmbeddingMemoryStore | None = None,
        cache_manager: Any | None = None,
        reflection_engine: Any | None = None,
    ):
        """
        Initialize production memory system.

        Args:
            postgres_store: PostgreSQL memory store
            embedding_store: Optional Qdrant embedding store for semantic search
            cache_manager: SOTA cache manager (L1+L2)
            reflection_engine: SOTA reflection engine for pattern extraction
        """
        self.postgres = postgres_store
        self.embeddings = embedding_store
        self.cache = cache_manager  # SOTA: L1+L2 caching
        self.reflection = reflection_engine  # SOTA: Reflection
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all storage backends + SOTA components."""
        if self._initialized:
            return

        await self.postgres.initialize()

        if self.embeddings:
            await self.embeddings.initialize()

        # SOTA: Initialize cache
        if self.cache:
            await self.cache.initialize()
            logger.info("SOTA cache initialized (L1+L2)")

        self._initialized = True
        logger.info(
            "ProductionMemorySystem initialized with SOTA components",
            has_cache=self.cache is not None,
            has_reflection=self.reflection is not None,
        )

    # ============================================================
    # Session Management
    # ============================================================

    def create_working_memory(
        self,
        session_id: str | None = None,
    ) -> WorkingMemoryManager:
        """
        Create a new working memory for a session.

        Args:
            session_id: Optional session ID

        Returns:
            WorkingMemoryManager instance (with SOTA config)
        """
        # SOTA: Use config from central config system
        from .config import get_config

        config = get_config()
        return WorkingMemoryManager(session_id=session_id, config=config.working)

    async def consolidate_session(
        self,
        working_memory: WorkingMemoryManager,
        project_id: str = "default",
    ) -> str:
        """
        Consolidate working memory into long-term storage.

        Args:
            working_memory: Working memory to consolidate
            project_id: Project ID

        Returns:
            Episode ID
        """
        # Create episode from working memory
        episode = working_memory.consolidate()

        # Store in PostgreSQL
        episode_dict = self._episode_to_dict(episode)
        episode_dict["project_id"] = project_id
        episode_id = await self.postgres.save_episode(episode_dict)

        # Index in Qdrant for semantic search
        if self.embeddings and episode.task_description:
            try:
                await self.embeddings.index_episode(
                    episode_id=episode_id,
                    task_description=episode.task_description,
                    metadata={
                        "project_id": project_id,
                        "task_type": episode.task_type.value,
                        "outcome_status": episode.outcome_status.value,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to index episode in Qdrant: {e}")

        # Extract and store entities from session
        await self._extract_entities_from_episode(episode, project_id)

        # Learn patterns if successful
        if episode.outcome_status == TaskStatus.SUCCESS and episode.error_types:
            await self._learn_from_successful_debug(episode)

        # Update project knowledge
        await self._update_project_knowledge(episode, project_id)

        # SOTA: Trigger reflection if needed
        if self.reflection:
            try:
                # Get episode count for this project
                episode_count = await self.postgres.count_episodes(project_id=project_id)

                if await self.reflection.should_reflect(episode_count):
                    logger.info("Reflection triggered", episode_count=episode_count)

                    # Get recent episodes for reflection
                    recent_episodes_data = await self.postgres.list_episodes(
                        project_id=project_id, limit=20, order_by="created_at DESC"
                    )

                    # Convert to Episode objects
                    recent_episodes = [self._dict_to_episode(ep) for ep in recent_episodes_data]

                    # Perform reflection
                    reflections = await self.reflection.reflect_on_episodes(recent_episodes, project_id=project_id)

                    # Store reflections as semantic memories
                    for reflection_result in reflections:
                        semantic_memory = reflection_result.semantic_memory
                        await self.postgres.save_semantic_memory(
                            {
                                "id": semantic_memory.id,
                                "project_id": semantic_memory.project_id,
                                "title": semantic_memory.title,
                                "summary": semantic_memory.summary,
                                "key_insights": semantic_memory.key_insights,
                                "source_episode_ids": semantic_memory.source_episode_ids,
                                "category": semantic_memory.category,
                                "tags": semantic_memory.tags,
                                "importance": semantic_memory.importance,
                            }
                        )

                    logger.info(f"Reflection complete: {len(reflections)} patterns extracted")
            except Exception as e:
                logger.warning(f"Reflection failed: {e}")

        logger.info(f"Session consolidated: {episode_id}")
        return episode_id

    # ============================================================
    # Memory Recall (Main Query Interface)
    # ============================================================

    async def recall(
        self,
        query: str,
        project_id: str = "default",
        task_type: TaskType | None = None,
        include_episodes: bool = True,
        include_facts: bool = True,
        include_patterns: bool = True,
        limit: int = 5,
    ) -> dict[str, Any]:
        """
        Recall relevant memories for a query.

        This is the main entry point for memory retrieval.

        Args:
            query: Natural language query
            project_id: Project ID
            task_type: Optional task type filter
            include_episodes: Include similar episodes
            include_facts: Include relevant facts
            include_patterns: Include matching patterns
            limit: Maximum results per category

        Returns:
            Dictionary with categorized memories:
            - episodes: Similar past episodes
            - facts: Relevant extracted facts
            - patterns: Matching bug/code patterns
            - entities: Related entities
            - guidance: Synthesized guidance
        """
        # SOTA: Check L1/L2 cache first
        if self.cache:
            cache_key = f"recall:{project_id}:{query}:{task_type}:{limit}"
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                logger.info("Cache HIT for recall", project_id=project_id)
                return cached_result

        memories: dict[str, Any] = {
            "episodes": [],
            "facts": [],
            "patterns": [],
            "entities": [],
            "guidance": None,
        }

        # Semantic search for similar episodes
        if include_episodes and self.embeddings:
            try:
                similar_episodes = await self.embeddings.search_similar_episodes(
                    query=query,
                    limit=limit,
                    filters={"must": [{"key": "project_id", "match": {"value": project_id}}]} if project_id else None,
                )

                # Enrich with full episode data
                for ep in similar_episodes:
                    full_episode = await self.postgres.get_episode(ep["episode_id"])
                    if full_episode:
                        full_episode["similarity_score"] = ep["score"]
                        memories["episodes"].append(full_episode)

                        # Increment retrieval count
                        await self.postgres.increment_retrieval_count(ep["episode_id"])

            except Exception as e:
                logger.warning(f"Episode semantic search failed: {e}")
                # Fallback to text search
                memories["episodes"] = await self.postgres.find_episodes(
                    project_id=project_id,
                    task_type=task_type.value if task_type else None,
                    search_text=query,
                    limit=limit,
                )

        # Recall facts
        if include_facts and self.embeddings:
            try:
                memories["facts"] = await self.embeddings.recall_facts(
                    query=query,
                    project_id=project_id,
                    limit=limit,
                )
            except Exception as e:
                logger.warning(f"Fact recall failed: {e}")

        # Find matching patterns
        if include_patterns:
            # Extract potential error type from query
            error_type = self._extract_error_type(query)
            if error_type:
                memories["patterns"] = await self.postgres.find_bug_patterns(
                    error_type=error_type,
                    limit=limit,
                )

        # Find related entities
        entities = await self.postgres.find_entities(
            project_id=project_id,
            name_pattern=self._extract_entity_hint(query),
            limit=limit,
        )
        memories["entities"] = entities

        # Synthesize guidance
        memories["guidance"] = self._synthesize_guidance(memories)

        # SOTA: Cache the result (L1+L2)
        if self.cache:
            cache_key = f"recall:{project_id}:{query}:{task_type}:{limit}"
            await self.cache.put(cache_key, memories)
            logger.info("Cache WRITE for recall", project_id=project_id)

        return memories

    async def recall_for_error(
        self,
        error_type: str,
        error_message: str | None = None,
        project_id: str = "default",
        limit: int = 5,
    ) -> dict[str, Any]:
        """
        Recall memories specifically for error resolution.

        Args:
            error_type: Error type (e.g., "TypeError", "KeyError")
            error_message: Optional error message
            project_id: Project ID
            limit: Maximum results

        Returns:
            Specialized memories for debugging
        """
        memories: dict[str, Any] = {
            "patterns": [],
            "successful_fixes": [],
            "failed_attempts": [],
            "related_files": [],
        }

        # Find bug patterns
        memories["patterns"] = await self.postgres.find_bug_patterns(
            error_type=error_type,
            limit=limit,
        )

        # Find successful resolutions
        successful = await self.postgres.find_episodes(
            project_id=project_id,
            error_type=error_type,
            outcome_status="success",
            limit=limit,
        )
        memories["successful_fixes"] = successful

        # Find failed attempts (to avoid)
        failed = await self.postgres.find_episodes(
            project_id=project_id,
            error_type=error_type,
            outcome_status="failure",
            limit=3,
        )
        memories["failed_attempts"] = failed

        # Extract related files from episodes
        related_files = set()
        for ep in successful + failed:
            related_files.update(ep.get("files_involved", []))
        memories["related_files"] = list(related_files)[:20]

        return memories

    # ============================================================
    # Fact Management (Mem0-style)
    # ============================================================

    async def remember(
        self,
        fact: str,
        project_id: str = "default",
        source: str = "user",
    ) -> str:
        """
        Store a fact for future recall.

        Args:
            fact: Fact to remember
            project_id: Project ID
            source: Source of fact (user, conversation, episode)

        Returns:
            Fact ID
        """
        if not self.embeddings:
            logger.warning("Embedding store not configured, fact not stored")
            return ""

        return await self.embeddings.store_fact(
            fact_text=fact,
            project_id=project_id,
            source_type=source,
        )

    async def forget(self, fact_id: str) -> None:
        """Delete a stored fact."""
        if self.embeddings:
            await self.embeddings.delete_fact(fact_id)

    # ============================================================
    # Graph Memory Operations
    # ============================================================

    async def track_entity(
        self,
        project_id: str,
        entity_type: str,
        name: str,
        properties: dict[str, Any] | None = None,
        context: str | None = None,
    ) -> str:
        """
        Track an entity in graph memory.

        Args:
            project_id: Project ID
            entity_type: Entity type (function, class, file, concept, person)
            name: Entity name
            properties: Additional properties
            context: Optional context for embedding

        Returns:
            Entity ID
        """
        entity_id = await self.postgres.upsert_entity(
            project_id=project_id,
            entity_type=entity_type,
            name=name,
            properties=properties,
        )

        # Index in embedding store
        if self.embeddings and context:
            try:
                await self.embeddings.index_entity(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    name=name,
                    context=context,
                )
            except Exception as e:
                logger.warning(f"Failed to index entity in Qdrant: {e}")

        return entity_id

    async def track_relationship(
        self,
        project_id: str,
        source_entity_id: str,
        target_entity_id: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """
        Track a relationship between entities.

        Args:
            project_id: Project ID
            source_entity_id: Source entity
            target_entity_id: Target entity
            relationship_type: Relationship type (calls, imports, uses, etc.)
            properties: Additional properties

        Returns:
            Relationship ID
        """
        return await self.postgres.add_relationship(
            project_id=project_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relationship_type=relationship_type,
            properties=properties,
        )

    async def find_related_entities(
        self,
        entity_id: str,
        relationship_types: list[str] | None = None,
        direction: str = "both",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Find entities related to a given entity.

        Args:
            entity_id: Entity ID
            relationship_types: Filter by relationship types
            direction: 'outgoing', 'incoming', or 'both'
            limit: Maximum results

        Returns:
            Related entities with relationship info
        """
        all_relationships = []

        if relationship_types:
            for rel_type in relationship_types:
                rels = await self.postgres.get_entity_relationships(
                    entity_id=entity_id,
                    direction=direction,
                    relationship_type=rel_type,
                    limit=limit,
                )
                all_relationships.extend(rels)
        else:
            all_relationships = await self.postgres.get_entity_relationships(
                entity_id=entity_id,
                direction=direction,
                limit=limit,
            )

        return all_relationships[:limit]

    async def find_path_between_entities(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 3,
    ) -> list[dict[str, Any]] | None:
        """
        Find path between two entities in the knowledge graph.

        Args:
            source_id: Source entity ID
            target_id: Target entity ID
            max_depth: Maximum path length

        Returns:
            Path as list of relationships, or None if not found
        """
        return await self.postgres.find_path(
            source_entity_id=source_id,
            target_entity_id=target_id,
            max_depth=max_depth,
        )

    # ============================================================
    # Project Knowledge
    # ============================================================

    async def get_project_knowledge(
        self,
        project_id: str,
    ) -> ProjectKnowledge | None:
        """Get accumulated project knowledge."""
        data = await self.postgres.get_project_knowledge(project_id)
        if not data:
            return None

        return ProjectKnowledge(
            project_id=data["project_id"],
            architecture_type=data.get("architecture_type", "monolith"),
            main_directories=data.get("main_directories", []),
            entry_points=data.get("entry_points", []),
            config_files=data.get("config_files", []),
            naming_conventions=data.get("naming_conventions", {}),
            file_organization=data.get("file_organization", ""),
            import_style=data.get("import_style", ""),
            testing_patterns=data.get("testing_patterns", []),
            documentation_style=data.get("documentation_style", ""),
            languages=data.get("languages", []),
            frameworks=data.get("frameworks", []),
            testing_frameworks=data.get("testing_frameworks", []),
            build_tools=data.get("build_tools", []),
            frequently_modified=data.get("frequently_modified", []),
            high_complexity=data.get("high_complexity", []),
            bug_prone=data.get("bug_prone", []),
            critical_paths=data.get("critical_paths", []),
            common_issues=data.get("common_issues", []),
            preferred_solutions=data.get("preferred_solutions", {}),
            avoid_patterns=data.get("avoid_patterns", []),
            review_focus=data.get("review_focus", []),
            total_sessions=data.get("total_sessions", 0),
            total_tasks=data.get("total_tasks", 0),
            success_rate=data.get("success_rate", 0.5),
            common_task_types=data.get("common_task_types", {}),
        )

    # ============================================================
    # Feedback & Learning
    # ============================================================

    async def record_feedback(
        self,
        episode_id: str,
        helpful: bool,
        feedback_text: str | None = None,
    ) -> None:
        """Record feedback on episode usefulness."""
        await self.postgres.update_episode_feedback(
            episode_id=episode_id,
            helpful=helpful,
            user_feedback=feedback_text,
        )

    # ============================================================
    # Maintenance
    # ============================================================

    async def cleanup(
        self,
        max_age_days: int = 90,
        min_usefulness: float = 0.3,
        min_retrievals: int = 2,
    ) -> dict[str, int]:
        """
        Cleanup old, low-value memories.

        Args:
            max_age_days: Maximum age in days
            min_usefulness: Minimum usefulness score to keep
            min_retrievals: Minimum retrieval count to keep

        Returns:
            Cleanup statistics
        """
        deleted = await self.postgres.cleanup_old_episodes(
            max_age_days=max_age_days,
            min_usefulness=min_usefulness,
            min_retrievals=min_retrievals,
        )

        return {"episodes_deleted": deleted}

    async def get_statistics(self) -> dict[str, Any]:
        """Get memory system statistics."""
        stats = {"postgres": await self.postgres.get_statistics()}

        if self.embeddings:
            stats["embeddings"] = await self.embeddings.get_statistics()

        return stats

    async def close(self) -> None:
        """Close all connections."""
        await self.postgres.close()
        if self.embeddings:
            await self.embeddings.close()

    # ============================================================
    # Internal Helpers
    # ============================================================

    def _episode_to_dict(self, episode: Episode) -> dict[str, Any]:
        """Convert Episode dataclass to dict."""
        data = asdict(episode)
        # Convert enums to values
        data["task_type"] = episode.task_type.value
        data["outcome_status"] = episode.outcome_status.value
        # Convert datetime to ISO format
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = data["created_at"]
        return data

    async def _extract_entities_from_episode(
        self,
        episode: Episode,
        project_id: str,
    ) -> None:
        """Extract and store entities from episode."""
        # Track files as entities
        for file_path in episode.files_involved:
            await self.track_entity(
                project_id=project_id,
                entity_type="file",
                name=file_path,
            )

        # Track symbols as entities
        for symbol in episode.symbols_involved:
            await self.track_entity(
                project_id=project_id,
                entity_type="symbol",
                name=symbol,
            )

    async def _learn_from_successful_debug(self, episode: Episode) -> None:
        """Learn bug pattern from successful debugging."""
        for error_type in episode.error_types:
            pattern = {
                "name": f"Pattern for {error_type}",
                "error_types": [error_type],
                "solutions": [
                    {
                        "description": episode.solution_pattern or episode.plan_summary,
                        "approach": episode.plan_summary,
                        "success_rate": 1.0,
                    }
                ]
                if episode.solution_pattern
                else [],
                "occurrence_count": 1,
                "resolution_count": 1,
                "avg_resolution_time_ms": episode.duration_ms,
            }
            await self.postgres.save_bug_pattern(pattern)

    async def _update_project_knowledge(
        self,
        episode: Episode,
        project_id: str,
    ) -> None:
        """Update project knowledge from episode."""
        # Get existing knowledge or create new
        existing = await self.postgres.get_project_knowledge(project_id)

        knowledge = {
            "project_id": project_id,
            "total_sessions": (existing or {}).get("total_sessions", 0) + 1,
            "total_tasks": 1,
            "frequently_modified": episode.files_involved[:50],
            "bug_prone": episode.files_involved[:20] if episode.error_types else [],
            "common_issues": episode.gotchas[:20],
            "success_rate": 1.0 if episode.outcome_status == TaskStatus.SUCCESS else 0.0,
            "common_task_types": {episode.task_type.value: 1},
        }

        await self.postgres.save_project_knowledge(knowledge)

    def _synthesize_guidance(self, memories: dict[str, Any]) -> Guidance:
        """Synthesize guidance from retrieved memories."""
        guidance = Guidance()

        # Extract from successful episodes
        successful = [ep for ep in memories.get("episodes", []) if ep.get("outcome_status") == "success"]

        if successful:
            best = successful[0]
            guidance.suggested_approach = best.get("solution_pattern") or best.get("plan_summary", "")
            guidance.things_to_try = best.get("tips", [])[:5]
            guidance.confidence += 0.3

        # Extract from patterns
        for pattern in memories.get("patterns", []):
            if pattern.get("solutions"):
                solutions = pattern["solutions"]
                if isinstance(solutions, list) and solutions:
                    guidance.things_to_try.append(solutions[0].get("description", ""))
            guidance.expected_challenges.extend(pattern.get("common_causes", [])[:3])
            guidance.confidence += 0.2

        # Extract from failed episodes
        failed = [ep for ep in memories.get("episodes", []) if ep.get("outcome_status") == "failure"]
        for ep in failed[:3]:
            guidance.things_to_avoid.extend(ep.get("gotchas", [])[:2])

        # Normalize confidence
        guidance.confidence = min(guidance.confidence, 1.0)

        # Deduplicate
        guidance.things_to_try = list(dict.fromkeys(guidance.things_to_try))[:5]
        guidance.things_to_avoid = list(dict.fromkeys(guidance.things_to_avoid))[:5]
        guidance.expected_challenges = list(dict.fromkeys(guidance.expected_challenges))[:5]

        return guidance

    def _extract_error_type(self, query: str) -> str | None:
        """Extract error type from query."""
        # Common error patterns
        error_keywords = [
            "TypeError",
            "KeyError",
            "ValueError",
            "AttributeError",
            "IndexError",
            "NameError",
            "ImportError",
            "RuntimeError",
            "FileNotFoundError",
            "ConnectionError",
            "TimeoutError",
        ]

        query_upper = query.upper()
        for error in error_keywords:
            if error.upper() in query_upper:
                return error

        return None

    def _extract_entity_hint(self, query: str) -> str | None:
        """Extract potential entity name from query."""
        # Simple heuristic: look for CamelCase or snake_case words
        import re

        # CamelCase
        camel_matches = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", query)
        if camel_matches:
            return camel_matches[0]

        # snake_case
        snake_matches = re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", query)
        if snake_matches:
            return snake_matches[0]

        return None


# ============================================================
# Factory Function
# ============================================================


async def create_production_memory_system(
    postgres_store: PostgresStore,
    qdrant_adapter: QdrantAdapter | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> ProductionMemorySystem:
    """
    Create and initialize production memory system.

    Args:
        postgres_store: PostgreSQL store instance
        qdrant_adapter: Optional Qdrant adapter for semantic search
        embedding_provider: Optional embedding provider

    Returns:
        Initialized ProductionMemorySystem

    Example:
        from src.infra.storage.postgres import PostgresStore
        from src.infra.vector.qdrant import QdrantAdapter

        postgres = PostgresStore(connection_string="postgresql://...")
        qdrant = QdrantAdapter(host="localhost", port=6333)

        memory = await create_production_memory_system(
            postgres_store=postgres,
            qdrant_adapter=qdrant,
        )
    """
    # Create PostgreSQL memory store
    pg_memory = PostgresMemoryStore(postgres_store)

    # Create embedding store if Qdrant provided
    embedding_store = None
    if qdrant_adapter:
        embedding_store = EmbeddingMemoryStore(
            qdrant_adapter=qdrant_adapter,
            embedding_provider=embedding_provider,
        )

    # Create and initialize system
    system = ProductionMemorySystem(
        postgres_store=pg_memory,
        embedding_store=embedding_store,
    )
    await system.initialize()

    return system
