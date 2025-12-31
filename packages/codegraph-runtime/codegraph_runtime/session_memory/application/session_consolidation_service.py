"""
Session Consolidation Service (SOTA Application Layer)

Handles the consolidation of working memory into long-term storage
(episodic and semantic memory).

SOTA: Implements Generative Agents style reflection and pattern extraction.
"""

from __future__ import annotations

from typing import Any

from codegraph_runtime.session_memory.domain.models import (
    Episode,
    TaskStatus,
    TaskType,
)
from codegraph_runtime.session_memory.domain.ports import (
    EmbeddingProviderPort,
    EpisodeRepositoryPort,
    PatternRepositoryPort,
    ProjectKnowledgePort,
    ReflectionEnginePort,
)


class SessionConsolidationService:
    """
    Application service for session consolidation.

    Coordinates the process of:
    1. Converting working memory to episode
    2. Storing episode in long-term memory
    3. Extracting and storing patterns
    4. Updating project knowledge
    5. Triggering reflection if needed

    SOTA Features:
    - Automatic pattern extraction from successful sessions
    - Reflection-based insight generation
    - Project knowledge accumulation
    """

    def __init__(
        self,
        episode_repository: EpisodeRepositoryPort,
        bug_pattern_repository: PatternRepositoryPort,
        code_rule_repository: PatternRepositoryPort,
        project_knowledge: ProjectKnowledgePort,
        embedding_provider: EmbeddingProviderPort | None = None,
        reflection_engine: ReflectionEnginePort | None = None,
    ) -> None:
        """
        Initialize session consolidation service.

        Args:
            episode_repository: Repository for episodes
            bug_pattern_repository: Repository for bug patterns
            code_rule_repository: Repository for code rules
            project_knowledge: Project knowledge port
            embedding_provider: Optional embedding provider
            reflection_engine: Optional reflection engine
        """
        self._episodes = episode_repository
        self._bug_patterns = bug_pattern_repository
        self._code_rules = code_rule_repository
        self._project_knowledge = project_knowledge
        self._embeddings = embedding_provider
        self._reflection = reflection_engine

    async def consolidate_session(
        self,
        episode: Episode,
    ) -> str:
        """
        Consolidate a session into long-term memory.

        Main entry point for session consolidation.

        Args:
            episode: Episode created from working memory

        Returns:
            Episode ID
        """
        # Generate embedding for task description
        if self._embeddings and episode.task_description:
            try:
                episode.task_description_embedding = await self._embeddings.embed(episode.task_description)
            except Exception:
                pass  # Continue without embedding

        # Store episode
        episode_id = await self._episodes.save(episode)

        # Extract and store patterns
        await self._extract_patterns(episode)

        # Update project knowledge
        await self._project_knowledge.update_from_episode(episode)

        # Trigger reflection if appropriate
        if self._reflection:
            await self._maybe_reflect(episode.project_id)

        return episode_id

    async def _extract_patterns(self, episode: Episode) -> None:
        """
        Extract patterns from episode.

        Creates or reinforces patterns based on:
        - Error types and solutions (for debugging)
        - Code transformations (for refactoring)
        - Successful approaches (for general tasks)
        """
        if episode.outcome_status != TaskStatus.SUCCESS:
            return  # Only learn from successful episodes

        # Extract bug patterns
        if episode.task_type == TaskType.DEBUG and episode.error_types:
            await self._extract_bug_patterns(episode)

        # Extract code rules
        if episode.task_type in (TaskType.REFACTOR, TaskType.IMPLEMENT):
            await self._extract_code_rules(episode)

    async def _extract_bug_patterns(self, episode: Episode) -> None:
        """Extract bug patterns from debugging episode."""
        for error_type in episode.error_types:
            await self._bug_patterns.add(
                {
                    "error_type": error_type,
                    "solution_description": episode.solution_pattern or "",
                    "solution_approach": episode.plan_summary,
                    "common_causes": episode.gotchas[:5],
                    "language": "python",
                }
            )

    async def _extract_code_rules(self, episode: Episode) -> None:
        """Extract code rules from implementation/refactoring episode."""
        # For now, just reinforce existing rules based on files touched
        # More sophisticated extraction would analyze actual patches

        if episode.solution_pattern:
            from codegraph_runtime.session_memory.domain.models import PatternCategory

            await self._code_rules.add(
                {
                    "name": f"rule_from_episode_{episode.id[:8]}",
                    "description": episode.solution_pattern,
                    "category": PatternCategory.REFACTORING,
                    "initial_confidence": 0.6,
                }
            )

    async def _maybe_reflect(self, project_id: str) -> None:
        """Trigger reflection if conditions are met."""
        if not self._reflection:
            return

        # Check if we should reflect
        # (e.g., every N episodes)
        # This is simplified - full implementation would track episode count

        try:
            episodes = await self._episodes.find_by_project(
                project_id=project_id,
                limit=20,
            )

            if len(episodes) >= 10 and await self._reflection.should_reflect(len(episodes)):
                await self._reflection.reflect_on_episodes(episodes, project_id)
        except Exception:
            pass  # Reflection is optional, don't fail consolidation

    async def cleanup_old_memories(
        self,
        max_age_days: int = 90,
        min_usefulness: float = 0.3,
        min_retrievals: int = 2,
    ) -> dict[str, int]:
        """
        Cleanup old, low-value memories.

        Removes:
        - Episodes older than max_age_days with low usefulness
        - Low-confidence patterns with enough observations

        Args:
            max_age_days: Maximum age for episodes
            min_usefulness: Minimum usefulness to keep
            min_retrievals: Minimum retrievals to keep

        Returns:
            Dictionary with cleanup statistics
        """
        stats: dict[str, int] = {}

        # Cleanup episodes
        episodes_deleted = await self._episodes.cleanup_old(
            max_age_days=max_age_days,
            min_usefulness=min_usefulness,
            min_retrievals=min_retrievals,
        )
        stats["episodes_deleted"] = episodes_deleted

        # Cleanup weak code rules
        # (Bug patterns typically don't need cleanup - they're valuable)
        rules_deleted = await self._code_rules.cleanup_weak_rules(min_observations=5)
        stats["rules_deleted"] = rules_deleted

        return stats

    async def get_consolidation_statistics(self) -> dict[str, Any]:
        """Get statistics about consolidated memories."""
        episode_stats = await self._episodes.get_statistics()
        bug_pattern_stats = await self._bug_patterns.get_statistics()
        code_rule_stats = await self._code_rules.get_statistics()

        return {
            "episodes": episode_stats,
            "bug_patterns": bug_pattern_stats,
            "code_rules": code_rule_stats,
        }
