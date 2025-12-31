"""
Memory Retrieval System

Coordinates all memory layers to provide relevant context for agent tasks:
- Loads relevant memories at task start
- Queries memories during execution
- Synthesizes guidance from multiple memory sources
"""

from typing import Any

from codegraph_shared.common.observability import get_logger

# Import from semantic.py module (not semantic/ package)
from codegraph_runtime.session_memory.infrastructure.semantic import SemanticMemoryManager

from .episodic import EpisodicMemoryManager
from .models import Episode, Guidance, SimilarityQuery, TaskType

logger = get_logger(__name__)


class MemoryRetrievalSystem:
    """
    Orchestrates memory retrieval across all memory layers.

    Provides unified interface for:
    - Loading relevant memories for new tasks
    - Querying memories during execution
    - Synthesizing guidance from multiple sources
    """

    def __init__(
        self,
        episodic_memory: EpisodicMemoryManager | None = None,
        semantic_memory: SemanticMemoryManager | None = None,
    ):
        """
        Initialize memory retrieval system.

        Args:
            episodic_memory: Episodic memory manager
            semantic_memory: Semantic memory manager
        """
        self.episodic = episodic_memory or EpisodicMemoryManager()
        self.semantic = semantic_memory or SemanticMemoryManager()

        logger.info("MemoryRetrievalSystem initialized")

    # ============================================================
    # Task Initialization
    # ============================================================

    async def load_relevant_memories(
        self,
        task_description: str,
        task_type: TaskType,
        project_id: str = "default",
        files: list[str] | None = None,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Load relevant memories for a new task.

        Args:
            task_description: Description of the task
            task_type: Type of task
            project_id: Project identifier
            files: Files involved (if known)
            error_type: Error type if debugging

        Returns:
            Dictionary containing:
            - similar_episodes: Similar past episodes
            - bug_patterns: Matching bug patterns (if error)
            - project_knowledge: Project-specific knowledge
            - user_preferences: User preferences
            - guidance: Synthesized guidance
        """
        logger.info(f"Loading relevant memories: task_type={task_type.value}, project={project_id}")

        # Query episodic memory for similar episodes
        similar_episodes = await self.episodic.find_similar(
            SimilarityQuery(
                description=task_description,
                task_type=task_type,
                files=files,
                error_type=error_type,
                limit=3,
            )
        )

        # Query semantic memory for bug patterns (if debugging)
        bug_patterns = []
        if error_type:
            bug_patterns = await self.semantic.match_bug_pattern(error_type=error_type)

        # Get project knowledge
        project_knowledge = self.semantic.get_or_create_project_knowledge(project_id)

        # Get user preferences
        user_preferences = self.semantic.user_preferences

        # Synthesize guidance
        guidance = self._synthesize_guidance(
            episodes=similar_episodes,
            bug_patterns=bug_patterns,
            project_knowledge=project_knowledge,
            user_preferences=user_preferences,
            task_type=task_type,
            files=files or [],
        )

        loaded_memories = {
            "similar_episodes": similar_episodes,
            "bug_patterns": bug_patterns,
            "project_knowledge": project_knowledge,
            "user_preferences": user_preferences,
            "guidance": guidance,
        }

        logger.info(
            f"Memories loaded: "
            f"episodes={len(similar_episodes)}, "
            f"patterns={len(bug_patterns)}, "
            f"guidance_confidence={guidance.confidence:.2f}"
        )

        return loaded_memories

    # ============================================================
    # Runtime Queries
    # ============================================================

    async def query_similar_error(
        self,
        error_type: str,
        error_message: str | None = None,
        stack_trace: str | None = None,
    ) -> dict[str, Any]:
        """
        Query for similar errors during execution.

        Args:
            error_type: Error type/class name
            error_message: Error message
            stack_trace: Stack trace

        Returns:
            Dictionary with episodes, patterns, and recommendations
        """
        logger.info(f"Querying similar error: {error_type}")

        # Search episodic memory
        episodes = await self.episodic.find_by_error_pattern(error_type, error_message)

        # Search semantic memory for patterns
        patterns = await self.semantic.match_bug_pattern(
            error_type=error_type,
            error_message=error_message,
            stack_trace=stack_trace,
        )

        # Extract recommendations
        recommendations: list[dict[str, Any]] = []

        # From successful episodes
        for episode in episodes:
            if episode.outcome_status.value == "success":
                recommendations.append(
                    {
                        "source": "episode",
                        "approach": episode.solution_pattern,
                        "confidence": episode.usefulness_score,
                    }
                )

        # From bug patterns
        for match in patterns:
            if match.recommended_solution:
                recommendations.append(
                    {
                        "source": "pattern",
                        "approach": match.recommended_solution.description,
                        "confidence": match.score * match.recommended_solution.success_rate,
                    }
                )

        # Sort by confidence (cast to float for type safety)
        recommendations.sort(key=lambda r: float(r.get("confidence", 0.0)), reverse=True)

        result = {
            "episodes": episodes[:3],
            "patterns": patterns[:3],
            "recommendations": recommendations[:3],
            "found_solutions": len(recommendations) > 0,
        }

        logger.info(f"Similar error query complete: {len(recommendations)} recommendations")
        return result

    async def query_project_conventions(self, project_id: str) -> dict[str, Any]:
        """
        Query project-specific conventions.

        Args:
            project_id: Project identifier

        Returns:
            Project conventions and preferences
        """
        knowledge = self.semantic.get_or_create_project_knowledge(project_id)

        return {
            "naming_conventions": knowledge.naming_conventions,
            "file_organization": knowledge.file_organization,
            "testing_patterns": knowledge.testing_patterns,
            "avoid_patterns": knowledge.avoid_patterns,
            "preferred_solutions": knowledge.preferred_solutions,
        }

    async def query_past_approaches(
        self,
        task_type: TaskType,
        files: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Query past approaches for similar tasks.

        Args:
            task_type: Type of task
            files: Files involved
            limit: Maximum results

        Returns:
            List of past approaches with outcomes
        """
        episodes = await self.episodic.find_similar(
            SimilarityQuery(
                task_type=task_type,
                files=files,
                limit=limit,
            )
        )

        approaches = []
        for episode in episodes:
            approaches.append(
                {
                    "description": episode.task_description,
                    "approach": episode.plan_summary,
                    "outcome": episode.outcome_status.value,
                    "success": episode.outcome_status.value == "success",
                    "duration_ms": episode.duration_ms,
                    "key_learnings": {
                        "tips": episode.tips,
                        "gotchas": episode.gotchas,
                    },
                }
            )

        return approaches

    # ============================================================
    # Guidance Synthesis
    # ============================================================

    def _synthesize_guidance(
        self,
        episodes: list[Episode],
        bug_patterns: list[Any],
        project_knowledge: Any,
        user_preferences: Any,
        task_type: TaskType,
        files: list[str],
    ) -> Guidance:
        """
        Synthesize guidance from multiple memory sources.

        Args:
            episodes: Similar episodes
            bug_patterns: Matching bug patterns
            project_knowledge: Project knowledge
            user_preferences: User preferences
            task_type: Task type
            files: Files involved

        Returns:
            Synthesized guidance
        """
        guidance = Guidance()

        # Extract from successful episodes
        successful_episodes = [e for e in episodes if e.outcome_status.value == "success"]

        if successful_episodes:
            # Use most relevant successful episode
            best_episode = successful_episodes[0]
            guidance.suggested_approach = best_episode.solution_pattern or best_episode.plan_summary
            guidance.things_to_try = best_episode.tips[:5]
            guidance.confidence += 0.2

        # Extract from failed episodes
        failed_episodes = [e for e in episodes if e.outcome_status.value == "failure"]
        guidance.things_to_avoid = [gotcha for e in failed_episodes for gotcha in e.gotchas][:5]

        # Extract from bug patterns
        if bug_patterns:
            best_pattern = bug_patterns[0]
            if not guidance.suggested_approach and best_pattern.recommended_solution:
                guidance.suggested_approach = best_pattern.recommended_solution.description

            guidance.expected_challenges = best_pattern.pattern.common_causes[:3]
            guidance.confidence += best_pattern.score * 0.3

        # Consider project knowledge
        if project_knowledge:
            # Add project-specific warnings
            guidance.things_to_avoid.extend(project_knowledge.avoid_patterns[:3])

            # Adjust complexity based on hotspots
            affected_hotspots = [f for f in files if f in project_knowledge.high_complexity]
            if affected_hotspots:
                guidance.estimated_complexity = "high"
                guidance.expected_challenges.append(f"Involves complex code areas: {len(affected_hotspots)} files")

        # Consider user preferences
        if user_preferences:
            # Filter out rejected patterns
            guidance.things_to_avoid.extend(user_preferences.frequently_rejected[:3])

        # Ensure confidence is in valid range
        guidance.confidence = min(guidance.confidence, 1.0)

        # Deduplicate lists
        guidance.things_to_try = list(dict.fromkeys(guidance.things_to_try))
        guidance.things_to_avoid = list(dict.fromkeys(guidance.things_to_avoid))
        guidance.expected_challenges = list(dict.fromkeys(guidance.expected_challenges))

        return guidance

    # ============================================================
    # Learning
    # ============================================================

    async def learn_from_session(self, episode: Episode) -> None:
        """
        Learn from completed session.

        Args:
            episode: Episode to learn from
        """
        logger.info(f"Learning from session: {episode.id}")

        # Store in episodic memory
        await self.episodic.store(episode)

        # Extract patterns in semantic memory
        await self.semantic.learn_from_episode(episode)

        logger.info(f"Learning complete: {episode.id}")

    async def record_episode_feedback(
        self,
        episode_id: str,
        helpful: bool,
        user_feedback: str | None = None,
    ) -> None:
        """
        Record feedback on episode usefulness.

        Args:
            episode_id: Episode ID
            helpful: Whether episode was helpful
            user_feedback: Optional user feedback
        """
        await self.episodic.record_feedback(episode_id, helpful, user_feedback)

    # ============================================================
    # Statistics & Monitoring
    # ============================================================

    def get_memory_statistics(self) -> dict[str, Any]:
        """
        Get comprehensive memory statistics.

        Returns:
            Statistics from all memory layers
        """
        return {
            "episodic": self.episodic.get_statistics(),
            "semantic": self.semantic.get_statistics(),
        }

    def get_recent_activity(self, limit: int = 10) -> list[Episode]:
        """
        Get recent memory activity.

        Args:
            limit: Number of episodes to return

        Returns:
            Recent episodes
        """
        return self.episodic.get_recent(limit)


# ============================================================
# Convenience Factory
# ============================================================


def create_memory_system(
    storage: Any | None = None,
    embedder: Any | None = None,
    llm: Any | None = None,
) -> MemoryRetrievalSystem:
    """
    Create complete memory system.

    Args:
        storage: Storage backend
        embedder: Embedding model
        llm: LLM for knowledge extraction

    Returns:
        Configured MemoryRetrievalSystem
    """
    episodic = EpisodicMemoryManager(storage=storage, embedder=embedder)
    semantic = SemanticMemoryManager(llm=llm)

    return MemoryRetrievalSystem(
        episodic_memory=episodic,
        semantic_memory=semantic,
    )
