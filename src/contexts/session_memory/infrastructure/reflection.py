"""
Memory Reflection System (Generative Agents style)

Implements reflection process to compress episodic memories into semantic knowledge:
1. Trigger Detection → When to reflect (importance threshold, time, count)
2. Episode Selection → Select related episodes for reflection
3. LLM Reflection → Generate higher-level insights
4. Semantic Storage → Store as semantic memory

Based on patterns from:
- Generative Agents (Park et al.): Reflection for memory compression
- MemGPT: Core memory updates from archival

Usage with LiteLLM:
    from src.infra.llm import LiteLLMAdapter
    from src.memory import create_reflection_job

    # Create reflection job with LiteLLM
    llm = LiteLLMAdapter(model="gpt-4o-mini")
    job = create_reflection_job(llm=llm, store=memory_store)

    # Run reflection
    results = await job.run(project_id="my-project")
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from src.common.observability import get_logger

from .models import (
    Episode,
    ReflectionResult,
    SemanticMemory,
    TaskStatus,
    TaskType,
)

logger = get_logger(__name__)
# ============================================================
# Reflection Triggers
# ============================================================


@dataclass
class ReflectionTriggerConfig:
    """Configuration for reflection triggers."""

    # Importance-based trigger (Generative Agents style)
    importance_threshold: float = 100.0  # Sum of importance scores to trigger
    importance_decay: float = 0.1  # Per-hour decay

    # Time-based trigger
    min_interval_hours: float = 1.0  # Minimum time between reflections
    max_interval_hours: float = 24.0  # Force reflection after this time

    # Count-based trigger
    episode_count_threshold: int = 10  # Reflect after N new episodes

    # Quality filter
    min_episode_importance: float = 0.3  # Skip low-importance episodes


class ReflectionTrigger:
    """
    Determines when to trigger reflection.

    Combines multiple signals:
    - Accumulated importance exceeds threshold
    - Enough time has passed
    - Enough episodes accumulated
    """

    def __init__(
        self,
        config: ReflectionTriggerConfig | None = None,
    ):
        """Initialize trigger with configuration."""
        self.config = config or ReflectionTriggerConfig()

        # State tracking
        self._accumulated_importance: float = 0.0
        self._last_reflection: datetime | None = None
        self._episode_count: int = 0

    def record_episode(self, importance: float) -> None:
        """Record a new episode for trigger calculation."""
        self._accumulated_importance += importance
        self._episode_count += 1

    def should_reflect(self, now: datetime | None = None) -> bool:
        """
        Check if reflection should be triggered.

        Args:
            now: Current time

        Returns:
            True if reflection should be triggered
        """
        now = now or datetime.now()

        # Apply time decay to accumulated importance
        if self._last_reflection:
            hours_since = (now - self._last_reflection).total_seconds() / 3600
            decay_factor = max(0.0, 1.0 - self.config.importance_decay * hours_since)
            self._accumulated_importance *= decay_factor

        # Check importance threshold
        if self._accumulated_importance >= self.config.importance_threshold:
            return True

        # Check max interval
        if self._last_reflection:
            hours_since = (now - self._last_reflection).total_seconds() / 3600
            if hours_since >= self.config.max_interval_hours:
                return True

        # Check episode count
        if self._episode_count >= self.config.episode_count_threshold:
            return True

        return False

    def mark_reflected(self, now: datetime | None = None) -> None:
        """Mark that reflection has occurred."""
        now = now or datetime.now()
        self._last_reflection = now
        self._accumulated_importance = 0.0
        self._episode_count = 0

    def get_state(self) -> dict[str, Any]:
        """Get current trigger state for debugging."""
        return {
            "accumulated_importance": self._accumulated_importance,
            "episode_count": self._episode_count,
            "last_reflection": self._last_reflection.isoformat() if self._last_reflection else None,
        }


# ============================================================
# Episode Clustering
# ============================================================


@dataclass
class EpisodeCluster:
    """Cluster of related episodes for reflection."""

    episodes: list[Episode]
    theme: str  # Common theme/pattern
    total_importance: float
    task_types: list[TaskType]


class EpisodeClusterer:
    """
    Cluster episodes for focused reflection.

    Groups episodes by:
    - Task type
    - Files involved
    - Error patterns
    - Time proximity
    """

    def __init__(self, min_cluster_size: int = 2):
        """Initialize clusterer."""
        self.min_cluster_size = min_cluster_size

    def cluster(self, episodes: list[Episode]) -> list[EpisodeCluster]:
        """
        Cluster episodes into reflection groups.

        Args:
            episodes: Episodes to cluster

        Returns:
            List of episode clusters
        """
        clusters: list[EpisodeCluster] = []

        # Cluster by task type
        type_clusters = self._cluster_by_task_type(episodes)
        clusters.extend(type_clusters)

        # Cluster by error patterns (for debug episodes)
        debug_episodes = [e for e in episodes if e.task_type == TaskType.DEBUG]
        if debug_episodes:
            error_clusters = self._cluster_by_error(debug_episodes)
            clusters.extend(error_clusters)

        # Cluster by files
        file_clusters = self._cluster_by_files(episodes)
        clusters.extend(file_clusters)

        # Merge overlapping clusters
        merged = self._merge_overlapping(clusters)

        # Filter by minimum size
        return [c for c in merged if len(c.episodes) >= self.min_cluster_size]

    def _cluster_by_task_type(self, episodes: list[Episode]) -> list[EpisodeCluster]:
        """Cluster by task type."""
        type_groups: dict[TaskType, list[Episode]] = {}

        for ep in episodes:
            if ep.task_type not in type_groups:
                type_groups[ep.task_type] = []
            type_groups[ep.task_type].append(ep)

        clusters = []
        for task_type, eps in type_groups.items():
            if len(eps) >= self.min_cluster_size:
                total_importance = sum(ep.usefulness_score for ep in eps)
                clusters.append(
                    EpisodeCluster(
                        episodes=eps,
                        theme=f"{task_type.value} tasks",
                        total_importance=total_importance,
                        task_types=[task_type],
                    )
                )

        return clusters

    def _cluster_by_error(self, episodes: list[Episode]) -> list[EpisodeCluster]:
        """Cluster debug episodes by error type."""
        error_groups: dict[str, list[Episode]] = {}

        for ep in episodes:
            for error in ep.error_types:
                if error not in error_groups:
                    error_groups[error] = []
                error_groups[error].append(ep)

        clusters = []
        for error_type, eps in error_groups.items():
            if len(eps) >= self.min_cluster_size:
                total_importance = sum(ep.usefulness_score for ep in eps)
                clusters.append(
                    EpisodeCluster(
                        episodes=eps,
                        theme=f"{error_type} debugging",
                        total_importance=total_importance,
                        task_types=[TaskType.DEBUG],
                    )
                )

        return clusters

    def _cluster_by_files(self, episodes: list[Episode]) -> list[EpisodeCluster]:
        """Cluster by overlapping files."""
        # Find episodes with overlapping files
        file_to_episodes: dict[str, list[Episode]] = {}

        for ep in episodes:
            for file_path in ep.files_involved:
                if file_path not in file_to_episodes:
                    file_to_episodes[file_path] = []
                file_to_episodes[file_path].append(ep)

        # Find files with multiple episodes
        hotspots = {f: eps for f, eps in file_to_episodes.items() if len(eps) >= self.min_cluster_size}

        clusters = []
        seen_episode_sets: list[frozenset[str]] = []

        for file_path, eps in sorted(hotspots.items(), key=lambda x: len(x[1]), reverse=True):
            ep_ids = frozenset(e.id for e in eps)

            # Skip if this episode set is already covered
            if any(ep_ids <= seen for seen in seen_episode_sets):
                continue

            total_importance = sum(ep.usefulness_score for ep in eps)
            task_types = list({ep.task_type for ep in eps})

            clusters.append(
                EpisodeCluster(
                    episodes=eps,
                    theme=f"Changes to {file_path}",
                    total_importance=total_importance,
                    task_types=task_types,
                )
            )

            seen_episode_sets.append(ep_ids)

        return clusters

    def _merge_overlapping(self, clusters: list[EpisodeCluster]) -> list[EpisodeCluster]:
        """Merge clusters with significant overlap."""
        if not clusters:
            return []

        # Sort by size descending
        clusters = sorted(clusters, key=lambda c: len(c.episodes), reverse=True)

        merged: list[EpisodeCluster] = []
        used_episodes: set[str] = set()

        for cluster in clusters:
            cluster_eps = {e.id for e in cluster.episodes}

            # If more than 50% overlap with used, skip
            overlap = len(cluster_eps & used_episodes)
            if overlap > len(cluster_eps) * 0.5:
                continue

            merged.append(cluster)
            used_episodes.update(cluster_eps)

        return merged


# ============================================================
# Reflection Generation
# ============================================================


class LLMProvider(Protocol):
    """
    Protocol for LLM providers.

    Compatible implementations:
    - LiteLLMAdapter (recommended) - Multi-provider support
    - OpenAIAdapter - Direct OpenAI API
    - Any class with async complete() method
    """

    async def complete(self, prompt: str) -> str:
        """Generate completion for prompt."""
        ...


class ReflectionGenerator:
    """
    Generate reflections using LLM.

    Creates higher-level insights from episode clusters.

    Example:
        from src.infra.llm import LiteLLMAdapter

        llm = LiteLLMAdapter(model="gpt-4o-mini")
        generator = ReflectionGenerator(llm=llm)
        result = await generator.generate_reflection(cluster, project_id)
    """

    # Reflection prompt templates
    REFLECTION_PROMPT = """You are analyzing a set of related task episodes to extract insights.

Theme: {theme}
Number of episodes: {episode_count}

Episodes:
{episode_summaries}

Based on these episodes, generate a reflection that:
1. Identifies common patterns or approaches that worked
2. Notes any pitfalls or mistakes to avoid
3. Extracts reusable knowledge

Format your response as:
TITLE: [Brief descriptive title]
SUMMARY: [2-3 sentence summary of the key insight]
KEY_INSIGHTS:
- [Insight 1]
- [Insight 2]
- [Insight 3]
TAGS: [comma-separated tags]"""

    DEBUG_REFLECTION_PROMPT = """You are analyzing debugging episodes to extract bug-fixing patterns.

Error type: {error_type}
Number of episodes: {episode_count}

Debugging episodes:
{episode_summaries}

Based on these episodes, generate a reflection that:
1. Identifies the root causes of this error type
2. Documents effective debugging approaches
3. Notes common mistakes to avoid

Format your response as:
TITLE: [Brief descriptive title]
SUMMARY: [2-3 sentence summary]
ROOT_CAUSES:
- [Cause 1]
- [Cause 2]
SOLUTIONS:
- [Solution 1]
- [Solution 2]
AVOID:
- [Pitfall 1]
- [Pitfall 2]
TAGS: [comma-separated tags]"""

    def __init__(self, llm: LLMProvider):
        """Initialize generator with LLM provider."""
        self.llm = llm

    async def generate_reflection(
        self,
        cluster: EpisodeCluster,
        project_id: str,
    ) -> ReflectionResult:
        """
        Generate reflection for an episode cluster.

        Args:
            cluster: Episode cluster to reflect on
            project_id: Project ID

        Returns:
            ReflectionResult with generated semantic memory
        """
        # Select appropriate prompt
        is_debug = TaskType.DEBUG in cluster.task_types
        prompt_template = self.DEBUG_REFLECTION_PROMPT if is_debug else self.REFLECTION_PROMPT

        # Build episode summaries
        summaries = self._build_episode_summaries(cluster.episodes)

        # Format prompt
        if is_debug:
            error_type = self._extract_primary_error(cluster.episodes)
            prompt = prompt_template.format(
                error_type=error_type,
                episode_count=len(cluster.episodes),
                episode_summaries=summaries,
            )
        else:
            prompt = prompt_template.format(
                theme=cluster.theme,
                episode_count=len(cluster.episodes),
                episode_summaries=summaries,
            )

        # Generate reflection
        response = await self.llm.complete(prompt)

        # Parse response
        semantic_memory = self._parse_reflection(
            response=response,
            cluster=cluster,
            project_id=project_id,
        )

        return ReflectionResult(
            semantic_memory=semantic_memory,
            source_episodes=[e.id for e in cluster.episodes],
            reflection_prompt=prompt,
            llm_response=response,
            confidence=self._calculate_confidence(cluster),
        )

    def _build_episode_summaries(self, episodes: list[Episode]) -> str:
        """Build text summaries of episodes."""
        summaries = []

        for i, ep in enumerate(episodes[:10], 1):  # Limit to 10 episodes
            status = "✓" if ep.outcome_status == TaskStatus.SUCCESS else "✗"
            summary = f"""Episode {i} [{status}]:
- Task: {ep.task_description[:100]}...
- Files: {", ".join(ep.files_involved[:3])}
- Approach: {ep.plan_summary[:100]}...
- Outcome: {ep.solution_pattern or "N/A"}
"""
            if ep.gotchas:
                summary += f"- Gotchas: {', '.join(ep.gotchas[:2])}\n"

            summaries.append(summary)

        return "\n".join(summaries)

    def _extract_primary_error(self, episodes: list[Episode]) -> str:
        """Extract most common error type."""
        error_counts: dict[str, int] = {}
        for ep in episodes:
            for error in ep.error_types:
                error_counts[error] = error_counts.get(error, 0) + 1

        if error_counts:
            return max(error_counts, key=error_counts.get)
        return "Unknown"

    def _parse_reflection(
        self,
        response: str,
        cluster: EpisodeCluster,
        project_id: str,
    ) -> SemanticMemory:
        """Parse LLM response into SemanticMemory."""
        import re
        import uuid

        # Parse sections
        title_match = re.search(r"TITLE:\s*(.+?)(?:\n|$)", response)
        summary_match = re.search(r"SUMMARY:\s*(.+?)(?:\n[A-Z_]+:|$)", response, re.DOTALL)
        tags_match = re.search(r"TAGS:\s*(.+?)(?:\n|$)", response)

        # Extract insights (can be KEY_INSIGHTS, ROOT_CAUSES, SOLUTIONS, etc.)
        insight_patterns = [
            r"KEY_INSIGHTS:\s*\n((?:- .+\n?)+)",
            r"ROOT_CAUSES:\s*\n((?:- .+\n?)+)",
            r"SOLUTIONS:\s*\n((?:- .+\n?)+)",
        ]

        insights = []
        for pattern in insight_patterns:
            match = re.search(pattern, response)
            if match:
                items = re.findall(r"- (.+)", match.group(1))
                insights.extend(items)

        # Build semantic memory
        title = title_match.group(1).strip() if title_match else cluster.theme
        summary = summary_match.group(1).strip() if summary_match else response[:200]
        tags = [t.strip() for t in tags_match.group(1).split(",")] if tags_match else []

        # Determine category
        category = "debug_pattern" if TaskType.DEBUG in cluster.task_types else "general_insight"

        return SemanticMemory(
            id=str(uuid.uuid4()),
            project_id=project_id,
            title=title,
            summary=summary,
            key_insights=insights[:5],
            source_episode_ids=[e.id for e in cluster.episodes],
            source_count=len(cluster.episodes),
            category=category,
            tags=tags,
            importance=cluster.total_importance / len(cluster.episodes),
            recency_score=1.0,
        )

    def _calculate_confidence(self, cluster: EpisodeCluster) -> float:
        """Calculate confidence in reflection based on cluster quality."""
        # More episodes = higher confidence
        episode_factor = min(1.0, len(cluster.episodes) / 10)

        # Higher importance = higher confidence
        avg_importance = cluster.total_importance / len(cluster.episodes)
        importance_factor = avg_importance

        # Success rate = higher confidence
        success_count = sum(1 for ep in cluster.episodes if ep.outcome_status == TaskStatus.SUCCESS)
        success_factor = success_count / len(cluster.episodes)

        return episode_factor * 0.3 + importance_factor * 0.3 + success_factor * 0.4


# ============================================================
# Reflection Job
# ============================================================


class MemoryStore(Protocol):
    """Protocol for memory storage."""

    async def get_unreflected_episodes(
        self,
        project_id: str,
        min_importance: float,
        limit: int,
    ) -> list[Episode]:
        """Get episodes not yet used in reflection."""
        ...

    async def save_semantic_memory(
        self,
        memory: SemanticMemory,
    ) -> str:
        """Save semantic memory."""
        ...

    async def mark_episodes_reflected(
        self,
        episode_ids: list[str],
        semantic_memory_id: str,
    ) -> None:
        """Mark episodes as used in reflection."""
        ...


@dataclass
class ReflectionJobConfig:
    """Configuration for reflection job."""

    # Trigger
    trigger: ReflectionTriggerConfig = field(default_factory=ReflectionTriggerConfig)

    # Clustering
    min_cluster_size: int = 2
    max_episodes_per_reflection: int = 50

    # Generation
    max_reflections_per_run: int = 5

    # Storage
    min_episode_importance: float = 0.3


class ReflectionJob:
    """
    Background job for memory reflection.

    Periodically processes episodic memories to extract semantic knowledge.

    Example:
        from src.infra.llm import LiteLLMAdapter

        llm = LiteLLMAdapter(model="gpt-4o-mini")
        job = ReflectionJob(llm=llm, store=memory_store)
        results = await job.run(project_id="my-project")
    """

    def __init__(
        self,
        llm: LLMProvider,
        store: MemoryStore,
        config: ReflectionJobConfig | None = None,
    ):
        """
        Initialize reflection job.

        Args:
            llm: LLM provider for reflection generation.
                 Use LiteLLMAdapter for multi-provider support.
            store: Memory storage backend
            config: Job configuration
        """
        self.llm = llm
        self.store = store
        self.config = config or ReflectionJobConfig()

        self.trigger = ReflectionTrigger(self.config.trigger)
        self.clusterer = EpisodeClusterer(self.config.min_cluster_size)
        self.generator = ReflectionGenerator(llm)

    async def run(self, project_id: str) -> list[ReflectionResult]:
        """
        Run reflection job for a project.

        Args:
            project_id: Project ID

        Returns:
            List of generated reflections
        """
        logger.info(f"Starting reflection job for project {project_id}")

        # Get unreflected episodes
        episodes = await self.store.get_unreflected_episodes(
            project_id=project_id,
            min_importance=self.config.min_episode_importance,
            limit=self.config.max_episodes_per_reflection,
        )

        if not episodes:
            logger.info("No episodes to reflect on")
            return []

        # Cluster episodes
        clusters = self.clusterer.cluster(episodes)

        if not clusters:
            logger.info("No clusters formed from episodes")
            return []

        # Generate reflections for top clusters
        reflections: list[ReflectionResult] = []

        for cluster in clusters[: self.config.max_reflections_per_run]:
            try:
                result = await self.generator.generate_reflection(
                    cluster=cluster,
                    project_id=project_id,
                )

                # Save semantic memory
                memory_id = await self.store.save_semantic_memory(result.semantic_memory)

                # Mark episodes as reflected
                await self.store.mark_episodes_reflected(
                    episode_ids=[e.id for e in cluster.episodes],
                    semantic_memory_id=memory_id,
                )

                reflections.append(result)

                logger.info(
                    f"Generated reflection '{result.semantic_memory.title}' from {len(cluster.episodes)} episodes"
                )

            except Exception as e:
                logger.error(f"Reflection generation failed for cluster '{cluster.theme}': {e}")
                continue

        # Update trigger state
        self.trigger.mark_reflected()

        logger.info(f"Reflection job completed: {len(reflections)} reflections generated")
        return reflections

    async def run_if_needed(self, project_id: str) -> list[ReflectionResult]:
        """
        Run reflection job only if triggered.

        Args:
            project_id: Project ID

        Returns:
            List of generated reflections, or empty if not triggered
        """
        if not self.trigger.should_reflect():
            return []

        return await self.run(project_id)

    def record_episode(self, importance: float) -> None:
        """Record episode for trigger calculation."""
        self.trigger.record_episode(importance)


# ============================================================
# Factory Functions
# ============================================================


def create_reflection_job(
    llm: LLMProvider,
    store: MemoryStore,
    config: ReflectionJobConfig | None = None,
) -> ReflectionJob:
    """
    Create configured reflection job.

    Args:
        llm: LLM provider for reflection generation.
             Use LiteLLMAdapter for multi-provider support.
        store: Memory storage backend
        config: Job configuration

    Returns:
        Configured ReflectionJob

    Example:
        from src.infra.llm import LiteLLMAdapter

        llm = LiteLLMAdapter(model="gpt-4o-mini")
        job = create_reflection_job(llm=llm, store=memory_store)
        results = await job.run(project_id="my-project")
    """
    return ReflectionJob(
        llm=llm,
        store=store,
        config=config or ReflectionJobConfig(),
    )
