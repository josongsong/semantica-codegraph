"""
Project Knowledge Manager

Manages project-specific knowledge and statistics.
"""

from __future__ import annotations

import asyncio
from typing import Any

from codegraph_runtime.session_memory.infrastructure.models import Episode, ProjectKnowledge, TaskType
from codegraph_shared.infra.observability import get_logger, record_counter

logger = get_logger(__name__)


class ProjectKnowledgeManager:
    """
    Manages project-specific knowledge.

    Responsibilities:
    - Track project knowledge (files, patterns, success rates)
    - Update knowledge from episodes
    - Retrieve relevant knowledge for tasks
    """

    def __init__(self, max_projects: int = 100):
        """
        Initialize project knowledge manager.

        Args:
            max_projects: Maximum project knowledge entries
        """
        self.max_projects = max_projects
        self.knowledge: dict[str, ProjectKnowledge] = {}
        self._lock = asyncio.Lock()

    def get_or_create(self, project_id: str) -> ProjectKnowledge:
        """
        Get or create project knowledge with memory limits.

        Args:
            project_id: Project identifier

        Returns:
            Project knowledge
        """
        if project_id not in self.knowledge:
            # Check memory limit
            if len(self.knowledge) >= self.max_projects:
                # Remove least recently updated project
                sorted_projects = sorted(
                    self.knowledge.items(),
                    key=lambda x: x[1].last_updated,
                )
                removed_id = sorted_projects[0][0]
                del self.knowledge[removed_id]
                logger.debug("project_knowledge_removed_for_space", removed_id=removed_id)
                record_counter("memory_project_knowledge_trimmed_total")

            self.knowledge[project_id] = ProjectKnowledge(project_id=project_id)
            logger.info("project_knowledge_created", project_id=project_id)
            record_counter("memory_project_knowledge_total")

        return self.knowledge[project_id]

    async def update_from_episode(self, episode: Episode) -> None:
        """
        Update project knowledge from episode with thread safety.

        Args:
            episode: Episode to learn from
        """
        async with self._lock:
            knowledge = self.get_or_create(episode.project_id)

            # Update file tracking
            self._update_file_tracking(knowledge, episode)

            # Update statistics
            knowledge.total_sessions += 1
            knowledge.total_tasks += 1

            # Update success rate
            self._update_success_rate(knowledge, episode)

            # Update task type counts
            task_type_key = episode.task_type.value
            knowledge.common_task_types[task_type_key] = knowledge.common_task_types.get(task_type_key, 0) + 1

            # Add gotchas (limit list growth)
            for gotcha in episode.gotchas:
                if gotcha not in knowledge.common_issues:
                    knowledge.common_issues.append(gotcha)
                    # Keep only top 100 issues
                    if len(knowledge.common_issues) > 100:
                        knowledge.common_issues = knowledge.common_issues[-100:]

            logger.debug(
                "project_knowledge_updated",
                project_id=episode.project_id,
                total_sessions=knowledge.total_sessions,
            )

    def _update_file_tracking(self, knowledge: ProjectKnowledge, episode: Episode) -> None:
        """Update file hotspots and bug-prone tracking."""
        for file_path in episode.files_involved:
            if file_path not in knowledge.frequently_modified:
                knowledge.frequently_modified.append(file_path)
                # Keep only top 100 most frequently modified files
                if len(knowledge.frequently_modified) > 100:
                    knowledge.frequently_modified = knowledge.frequently_modified[-100:]

            # Track bug-prone files (limit list growth)
            if episode.error_types and file_path not in knowledge.bug_prone:
                knowledge.bug_prone.append(file_path)
                # Keep only top 50 bug-prone files
                if len(knowledge.bug_prone) > 50:
                    knowledge.bug_prone = knowledge.bug_prone[-50:]

    def _update_success_rate(self, knowledge: ProjectKnowledge, episode: Episode) -> None:
        """Update success rate using exponential moving average."""
        if episode.outcome_status.value == "success":
            success_value = 1.0
        elif episode.outcome_status.value == "partial":
            success_value = 0.5
        else:
            success_value = 0.0

        alpha = 0.1
        knowledge.success_rate = alpha * success_value + (1 - alpha) * knowledge.success_rate

    def get_relevant(
        self,
        project_id: str,
        task_type: TaskType | None = None,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Get relevant knowledge for current task.

        Args:
            project_id: Project identifier
            task_type: Task type
            error_type: Error type if debugging

        Returns:
            Dictionary of relevant knowledge
        """
        result: dict[str, Any] = {}

        # Project knowledge
        if project_id in self.knowledge:
            pk = self.knowledge[project_id]
            result["project"] = pk

            # Add context-specific info
            if task_type:
                result["task_type_frequency"] = pk.common_task_types.get(task_type.value, 0)

            if error_type:
                # Check if any bug-prone files match common patterns
                result["bug_prone_files"] = pk.bug_prone[:10]  # Top 10

            result["common_issues"] = pk.common_issues[:5]  # Top 5 issues
            result["hotspot_files"] = pk.frequently_modified[:10]  # Top 10 hotspots

        return result

    def get_statistics(self) -> dict[str, Any]:
        """Get project knowledge statistics."""
        total_sessions = sum(pk.total_sessions for pk in self.knowledge.values())
        total_tasks = sum(pk.total_tasks for pk in self.knowledge.values())
        avg_success_rate = (
            sum(pk.success_rate for pk in self.knowledge.values()) / len(self.knowledge) if self.knowledge else 0.0
        )

        return {
            "total_projects": len(self.knowledge),
            "max_projects": self.max_projects,
            "total_sessions": total_sessions,
            "total_tasks": total_tasks,
            "avg_success_rate": avg_success_rate,
            "top_projects": sorted(
                self.knowledge.items(),
                key=lambda x: x[1].total_sessions,
                reverse=True,
            )[:5],
        }
