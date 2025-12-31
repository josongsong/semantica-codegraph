"""
Memory Retrieval Service (SOTA Application Layer)

Orchestrates memory retrieval across all memory layers:
- Working Memory (current session)
- Episodic Memory (past experiences)
- Semantic Memory (learned patterns)

SOTA: Implements MemoryRetrievalPort with clean dependency injection.
"""

from __future__ import annotations

from typing import Any

from codegraph_runtime.session_memory.domain.models import (
    Episode,
    ErrorObservation,
    Guidance,
    TaskStatus,
    TaskType,
)
from codegraph_runtime.session_memory.domain.ports import (
    CachePort,
    EmbeddingProviderPort,
    EpisodeRepositoryPort,
    MemoryScorerPort,
    PatternRepositoryPort,
    ProjectKnowledgePort,
)


class MemoryRetrievalService:
    """
    Application service for memory retrieval operations.

    Coordinates across multiple repositories and services:
    - Episode repository for past experiences
    - Pattern repositories for learned patterns
    - Embedding provider for semantic search
    - Scorer for ranking results
    - Cache for performance

    SOTA Features:
    - 3-axis scoring (Similarity + Recency + Importance)
    - L1/L2 caching for performance
    - Hybrid search (embedding + keyword)
    """

    def __init__(
        self,
        episode_repository: EpisodeRepositoryPort,
        bug_pattern_repository: PatternRepositoryPort,
        code_rule_repository: PatternRepositoryPort,
        project_knowledge: ProjectKnowledgePort,
        embedding_provider: EmbeddingProviderPort | None = None,
        scorer: MemoryScorerPort | None = None,
        cache: CachePort | None = None,
    ) -> None:
        """
        Initialize memory retrieval service.

        All dependencies injected via ports - no concrete implementations.

        Args:
            episode_repository: Repository for episodes
            bug_pattern_repository: Repository for bug patterns
            code_rule_repository: Repository for code rules
            project_knowledge: Project knowledge port
            embedding_provider: Optional embedding provider
            scorer: Optional memory scorer
            cache: Optional cache (L1/L2)
        """
        self._episodes = episode_repository
        self._bug_patterns = bug_pattern_repository
        self._code_rules = code_rule_repository
        self._project_knowledge = project_knowledge
        self._embeddings = embedding_provider
        self._scorer = scorer
        self._cache = cache

    async def load_relevant_memories(
        self,
        task_description: str,
        task_type: TaskType,
        project_id: str = "default",
        files: list[str] | None = None,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Load all relevant memories for a task.

        Main entry point for memory-augmented task execution.

        Args:
            task_description: Natural language task description
            task_type: Type of task
            project_id: Project identifier
            files: Optional file context
            error_type: Optional error type (for debugging)

        Returns:
            Dictionary with categorized memories:
            - episodes: Similar past experiences
            - patterns: Relevant bug/code patterns
            - project_knowledge: Project-specific knowledge
            - guidance: Synthesized guidance
        """
        # Check cache first
        if self._cache:
            cache_key = f"memories:{project_id}:{task_type.value}:{hash(task_description)}"
            cached = await self._cache.get(cache_key)
            if cached:
                return cached

        memories: dict[str, Any] = {
            "episodes": [],
            "bug_patterns": [],
            "code_rules": [],
            "project_knowledge": None,
            "guidance": None,
        }

        # Get query embedding
        if self._embeddings:
            try:
                await self._embeddings.embed(task_description)
            except Exception:
                pass  # Continue without embeddings

        # 1. Find similar episodes
        from codegraph_runtime.session_memory.domain.models import SimilarityQuery

        query = SimilarityQuery(
            description=task_description,
            task_type=task_type,
            files=files,
            error_type=error_type,
            limit=5,
        )

        episode_results = await self._episodes.find_similar(query)
        memories["episodes"] = [{"episode": ep, "score": score} for ep, score in episode_results]

        # 2. Find relevant patterns
        if error_type:
            patterns = await self._bug_patterns.find_by_criteria(
                error_type=error_type,
                limit=5,
            )
            memories["bug_patterns"] = patterns

        # 3. Find applicable code rules
        if task_type in (TaskType.REFACTOR, TaskType.IMPLEMENT, TaskType.DEBUG):
            rules = await self._code_rules.find_by_criteria(
                trusted_only=True,
                limit=10,
            )
            memories["code_rules"] = rules

        # 4. Get project knowledge
        knowledge = await self._project_knowledge.get_or_create(project_id)
        memories["project_knowledge"] = knowledge

        # 5. Synthesize guidance
        memories["guidance"] = await self.synthesize_guidance(memories, task_type)

        # Cache result
        if self._cache:
            await self._cache.put(cache_key, memories, ttl_seconds=300)

        return memories

    async def query_similar_error(
        self,
        error_type: str,
        error_message: str | None = None,
        stack_trace: str | None = None,
        language: str = "python",
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Query memories for similar error resolution.

        Specialized retrieval for debugging tasks.

        Args:
            error_type: Error type (e.g., "TypeError")
            error_message: Optional error message
            stack_trace: Optional stack trace
            language: Programming language
            project_id: Optional project filter

        Returns:
            Dictionary with:
            - matching_patterns: Bug patterns with solutions
            - successful_fixes: Past successful resolutions
            - failed_attempts: Past failed attempts (to avoid)
            - guidance: Synthesized debugging guidance
        """
        result: dict[str, Any] = {
            "matching_patterns": [],
            "successful_fixes": [],
            "failed_attempts": [],
            "guidance": None,
        }

        # Create observation for pattern matching
        observation = ErrorObservation(
            error_type=error_type,
            error_message=error_message or "",
            stacktrace=stack_trace,
            language=language,
        )

        # Embed error message if possible
        if self._embeddings and error_message:
            try:
                observation.message_embedding = await self._embeddings.embed(error_message)
            except Exception:
                pass

        # Find matching bug patterns
        patterns = await self._bug_patterns.find_by_criteria(
            error_type=error_type,
            language=language,
            limit=5,
        )
        result["matching_patterns"] = patterns

        # Find successful past fixes
        successful = await self._episodes.find_by_error(
            error_type=error_type,
            project_id=project_id,
            limit=5,
        )
        # Filter to successful ones
        result["successful_fixes"] = [ep for ep in successful if ep.outcome_status == TaskStatus.SUCCESS]

        # Find failed attempts
        result["failed_attempts"] = [ep for ep in successful if ep.outcome_status == TaskStatus.FAILURE][:3]

        # Synthesize debugging guidance
        result["guidance"] = self._synthesize_debug_guidance(result)

        return result

    async def synthesize_guidance(
        self,
        memories: dict[str, Any],
        task_type: TaskType,
    ) -> Guidance:
        """
        Synthesize actionable guidance from retrieved memories.

        Combines insights from:
        - Past successful episodes
        - Learned patterns
        - Project conventions

        Args:
            memories: Retrieved memories
            task_type: Type of task

        Returns:
            Guidance object with recommendations
        """
        guidance = Guidance()

        # Extract from successful episodes
        episodes = memories.get("episodes", [])
        successful = [e["episode"] for e in episodes if e["episode"].outcome_status == TaskStatus.SUCCESS]

        if successful:
            best = successful[0]
            guidance.suggested_approach = best.solution_pattern or best.plan_summary or ""
            guidance.things_to_try = best.tips[:5]
            guidance.confidence += 0.3

        # Extract from patterns
        patterns = memories.get("bug_patterns", [])
        for pattern in patterns[:3]:
            if pattern.solutions:
                best_solution = max(pattern.solutions, key=lambda s: s.success_rate)
                if best_solution.description not in guidance.things_to_try:
                    guidance.things_to_try.append(best_solution.description)

            guidance.expected_challenges.extend(pattern.common_causes[:2])
            guidance.confidence += 0.1

        # Extract from failed episodes (things to avoid)
        for ep_data in episodes:
            ep = ep_data["episode"]
            if ep.outcome_status == TaskStatus.FAILURE:
                guidance.things_to_avoid.extend(ep.gotchas[:2])

        # Extract from project knowledge
        knowledge = memories.get("project_knowledge")
        if knowledge:
            guidance.things_to_avoid.extend(knowledge.avoid_patterns[:3])
            guidance.expected_challenges.extend(knowledge.common_issues[:2])

        # Deduplicate and limit
        guidance.things_to_try = list(dict.fromkeys(guidance.things_to_try))[:5]
        guidance.things_to_avoid = list(dict.fromkeys(guidance.things_to_avoid))[:5]
        guidance.expected_challenges = list(dict.fromkeys(guidance.expected_challenges))[:5]

        # Estimate complexity
        if successful:
            avg_steps = sum(e.steps_count for e in successful) / len(successful)
            if avg_steps > 30:
                guidance.estimated_complexity = "high"
            elif avg_steps > 10:
                guidance.estimated_complexity = "medium"
            else:
                guidance.estimated_complexity = "low"

        # Normalize confidence
        guidance.confidence = min(guidance.confidence, 1.0)

        return guidance

    def _synthesize_debug_guidance(
        self,
        result: dict[str, Any],
    ) -> Guidance:
        """Synthesize guidance specifically for debugging."""
        guidance = Guidance()

        # From patterns
        for pattern in result.get("matching_patterns", [])[:3]:
            if pattern.solutions:
                best = max(pattern.solutions, key=lambda s: s.success_rate)
                guidance.things_to_try.append(best.description)

            guidance.expected_challenges.extend(pattern.common_causes[:2])

        # From successful fixes
        for episode in result.get("successful_fixes", [])[:3]:
            if episode.solution_pattern:
                guidance.things_to_try.append(episode.solution_pattern)
            guidance.things_to_try.extend(episode.tips[:2])

        # From failed attempts
        for episode in result.get("failed_attempts", []):
            guidance.things_to_avoid.extend(episode.gotchas[:2])

        # Deduplicate
        guidance.things_to_try = list(dict.fromkeys(guidance.things_to_try))[:5]
        guidance.things_to_avoid = list(dict.fromkeys(guidance.things_to_avoid))[:3]
        guidance.expected_challenges = list(dict.fromkeys(guidance.expected_challenges))[:3]

        # Set confidence based on available data
        if result.get("matching_patterns"):
            guidance.confidence += 0.3
        if result.get("successful_fixes"):
            guidance.confidence += 0.4

        guidance.confidence = min(guidance.confidence, 1.0)

        return guidance

    async def learn_from_session(self, episode: Episode) -> None:
        """
        Learn from a completed session.

        Updates:
        - Episode repository (store experience)
        - Pattern repositories (reinforce/create patterns)
        - Project knowledge (update statistics)

        Args:
            episode: Completed episode to learn from
        """
        # Store episode
        await self._episodes.save(episode)

        # Update project knowledge
        await self._project_knowledge.update_from_episode(episode)

        # Learn bug pattern if debugging was successful
        if episode.outcome_status == TaskStatus.SUCCESS and episode.task_type == TaskType.DEBUG and episode.error_types:
            for error_type in episode.error_types:
                await self._bug_patterns.add(
                    {
                        "error_type": error_type,
                        "solution_description": episode.solution_pattern or "",
                        "solution_approach": episode.plan_summary,
                        "language": "python",  # TODO: Extract from episode
                    }
                )
