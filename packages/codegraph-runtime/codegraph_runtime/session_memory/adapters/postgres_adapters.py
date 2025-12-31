"""
PostgreSQL Adapters for Session Memory

Adapts PostgresMemoryStore to domain ports
"""

from typing import Any

from codegraph_runtime.session_memory.domain.models import Episode
from codegraph_runtime.session_memory.domain.ports import EpisodeRepositoryPort, ProjectKnowledgePort


class PostgresEpisodeRepository(EpisodeRepositoryPort):
    """PostgreSQL Episode Repository Adapter"""

    def __init__(self, postgres_store: Any):
        self._store = postgres_store

    async def save(self, episode: Episode) -> str:
        """Save episode"""
        # Convert to dict
        episode_dict = {
            "id": episode.id,
            "project_id": episode.project_id,
            "session_id": episode.session_id,
            "task_type": episode.task_type.value,
            "task_description": episode.task_description,
            "outcome_status": episode.outcome_status.value,
            "usefulness_score": episode.usefulness_score,
        }
        return await self._store.save_episode(episode_dict)

    async def find_similar(self, query: Any) -> list[tuple[Episode, float]]:
        """Find similar episodes"""
        # Simplified for MVP
        return []


class PostgresProjectKnowledge(ProjectKnowledgePort):
    """PostgreSQL Project Knowledge Adapter"""

    def __init__(self, postgres_store: Any):
        self._store = postgres_store

    async def update_from_episode(self, episode: Episode) -> None:
        """Update project knowledge from episode"""
        # Simplified for MVP
        pass

    async def get(self, project_id: str) -> Any:
        """Get project knowledge"""
        return None
