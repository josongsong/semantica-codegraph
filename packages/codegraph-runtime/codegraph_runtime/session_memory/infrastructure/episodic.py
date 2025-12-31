"""
Episodic Memory Manager

Manages mid-term memory of completed task executions:
- Store episodes (task execution records)
- Search by similarity (vector search)
- Search by attributes (structured queries)
- Track usage and usefulness
"""

import asyncio
import re
from datetime import datetime
from typing import Any, Literal

from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from codegraph_shared.infra.observability import get_logger, record_counter, record_histogram

from .models import Episode, SimilarityQuery, TaskStatus, TaskType

logger = get_logger(__name__)

# Default stop words for keyword extraction (can be overridden via constructor)
DEFAULT_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "from",
        "with",
        "after",
        "before",
        "into",
        "that",
        "this",
        "have",
        "has",
        "had",
        "was",
        "were",
        "been",
        "being",
        "are",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "not",
        "but",
        "then",
        "than",
        "when",
        "where",
        "while",
        "which",
        "what",
        "error",
        "exception",
        "failed",
        "failure",  # Common error terms
    }
)


class EpisodicMemoryManager:
    """
    Manages episodic memory - records of past task executions.

    Episodes are stored with both structured attributes and vector embeddings
    for hybrid search capabilities.
    """

    def __init__(
        self,
        storage: Any | None = None,
        embedder: Any | None = None,
        stop_words: frozenset[str] | None = None,
        cache_size: int = 100,
        cache_ttl_seconds: int = 300,
        scoring_engine: Any | None = None,
    ):
        """
        Initialize episodic memory manager.

        Args:
            storage: Storage backend (dict for now, DB later)
            embedder: Embedding model for similarity search
            stop_words: Custom stop words for keyword extraction (uses DEFAULT_STOP_WORDS if not provided)
            cache_size: Maximum number of cached similarity results
            cache_ttl_seconds: Cache TTL in seconds (default 5 minutes)
            scoring_engine: MemoryScoringEngine for 3-axis scoring (NEW)
        """
        self.storage: dict[str, Episode] = storage or {}
        self.embedder = embedder
        self.stop_words = stop_words if stop_words is not None else DEFAULT_STOP_WORDS

        # SOTA: 3-axis scoring engine
        self.scoring_engine = scoring_engine
        if scoring_engine:
            logger.info("episodic_memory_with_3axis_scoring_enabled")

        # Indices for fast lookup
        self.by_project: dict[str, list[str]] = {}
        self.by_task_type: dict[TaskType, list[str]] = {}
        self.by_status: dict[TaskStatus, list[str]] = {}
        self.by_file: dict[str, list[str]] = {}
        self.by_error_type: dict[str, list[str]] = {}

        # Locks for thread safety
        self._storage_lock = asyncio.Lock()
        self._episode_locks: dict[str, asyncio.Lock] = {}

        # Cache for similarity search results (LRU with TTL)
        self._cache_size = cache_size
        self._cache_ttl = cache_ttl_seconds
        self._similarity_cache: dict[str, tuple[list[Episode], float]] = {}  # key -> (results, timestamp)
        self._embedding_cache: dict[str, list[float]] = {}  # text -> embedding

        logger.info(
            "episodic_memory_initialized",
            storage_type=type(self.storage).__name__,
            has_embedder=embedder is not None,
            cache_size=cache_size,
        )
        record_counter("memory_episodic_initialized_total")

    def _get_episode_lock(self, episode_id: str) -> asyncio.Lock:
        """Get or create lock for specific episode."""
        if episode_id not in self._episode_locks:
            self._episode_locks[episode_id] = asyncio.Lock()
        return self._episode_locks[episode_id]

    @staticmethod
    def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=True))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    # ============================================================
    # Storage Operations
    # ============================================================

    async def store(self, episode: Episode) -> str:
        """
        Store episode in memory with transaction safety.

        Args:
            episode: Episode to store

        Returns:
            Episode ID

        Raises:
            Exception: If storage or index update fails
        """
        async with self._storage_lock:
            try:
                # Generate embedding if embedder available
                if self.embedder and not episode.task_description_embedding:
                    embedding_text = f"{episode.task_description} {episode.plan_summary or ''}"
                    try:
                        episode.task_description_embedding = await self.embedder.embed(embedding_text)
                        logger.debug(
                            "episode_embedding_generated",
                            episode_id=episode.id,
                            embedding_dim=len(episode.task_description_embedding),
                        )
                    except Exception as e:
                        logger.warning(
                            "episode_embedding_failed",
                            episode_id=episode.id,
                            error=str(e),
                        )
                        episode.task_description_embedding = []

                # Store episode first
                self.storage[episode.id] = episode

                # Update indices (if this fails, we can rebuild)
                try:
                    self._update_indices(episode)
                except Exception as e:
                    logger.error("index_update_failed", episode_id=episode.id, error=str(e), exc_info=True)
                    record_counter("memory_episodic_index_errors_total", labels={"operation": "update"})
                    # Remove from storage to maintain consistency
                    self.storage.pop(episode.id, None)
                    raise

                logger.info(
                    "episode_stored",
                    episode_id=episode.id,
                    task_type=episode.task_type.value,
                    project_id=episode.project_id,
                )
                record_counter("memory_episodes_stored_total", labels={"task_type": episode.task_type.value})
                record_histogram("memory_episode_duration_ms", episode.duration_ms)
                return episode.id

            except Exception as e:
                logger.error("episode_store_failed", error=str(e), exc_info=True)
                record_counter("memory_episodic_store_errors_total")
                raise

    def get(self, episode_id: str) -> Episode | None:
        """
        Get episode by ID.

        Args:
            episode_id: Episode ID

        Returns:
            Episode or None if not found
        """
        return self.storage.get(episode_id)

    async def delete(self, episode_id: str) -> bool:
        """
        Delete episode with transaction safety.

        Args:
            episode_id: Episode ID

        Returns:
            True if deleted, False if not found
        """
        async with self._storage_lock:
            episode = self.storage.get(episode_id)
            if not episode:
                return False

            try:
                # Remove from storage
                del self.storage[episode_id]

                # Remove from indices
                self._remove_from_indices(episode)

                # Clean up lock
                self._episode_locks.pop(episode_id, None)

                logger.info("episode_deleted", episode_id=episode_id, task_type=episode.task_type.value)
                record_counter("memory_episodes_deleted_total", labels={"task_type": episode.task_type.value})
                return True

            except Exception as e:
                logger.error("episode_delete_failed", episode_id=episode_id, error=str(e), exc_info=True)
                record_counter("memory_episodic_delete_errors_total")
                # Try to restore (best effort)
                self.storage[episode_id] = episode
                return False

    # ============================================================
    # Index Management
    # ============================================================

    def _update_indices(self, episode: Episode) -> None:
        """Update all indices with new episode."""
        # Project index
        if episode.project_id not in self.by_project:
            self.by_project[episode.project_id] = []
        self.by_project[episode.project_id].append(episode.id)

        # Task type index
        if episode.task_type not in self.by_task_type:
            self.by_task_type[episode.task_type] = []
        self.by_task_type[episode.task_type].append(episode.id)

        # Status index
        if episode.outcome_status not in self.by_status:
            self.by_status[episode.outcome_status] = []
        self.by_status[episode.outcome_status].append(episode.id)

        # File index
        for file_path in episode.files_involved:
            if file_path not in self.by_file:
                self.by_file[file_path] = []
            self.by_file[file_path].append(episode.id)

        # Error type index
        for error_type in episode.error_types:
            if error_type not in self.by_error_type:
                self.by_error_type[error_type] = []
            self.by_error_type[error_type].append(episode.id)

    def _remove_from_index(self, index: dict, key: Any, episode_id: str, index_name: str) -> None:
        """Helper to remove episode from a single index."""
        if key in index:
            try:
                index[key].remove(episode_id)
            except ValueError:
                logger.warning("episode_not_in_index", episode_id=episode_id, index_name=index_name, key=str(key))
                record_counter("memory_episodic_index_warnings_total", labels={"index": index_name})

    def _remove_from_indices(self, episode: Episode) -> None:
        """
        Remove episode from all indices with error handling.

        Args:
            episode: Episode to remove
        """
        # Remove from simple indices
        self._remove_from_index(self.by_project, episode.project_id, episode.id, "project")
        self._remove_from_index(self.by_task_type, episode.task_type, episode.id, "task_type")
        self._remove_from_index(self.by_status, episode.outcome_status, episode.id, "status")

        # Remove from file index
        for file_path in episode.files_involved:
            self._remove_from_index(self.by_file, file_path, episode.id, f"file({file_path})")

        # Remove from error type index
        for error_type in episode.error_types:
            self._remove_from_index(self.by_error_type, error_type, episode.id, f"error_type({error_type})")

    # ============================================================
    # Search Operations
    # ============================================================

    async def find_similar(self, query: SimilarityQuery) -> list[Episode]:
        """
        Find similar episodes.

        Args:
            query: Similarity query parameters

        Returns:
            List of matching episodes, sorted by relevance
        """
        # Start with all episodes
        candidates = list(self.storage.values())

        # Apply filters
        if query.task_type:
            episode_ids = self.by_task_type.get(query.task_type, [])
            candidates = [e for e in candidates if e.id in episode_ids]

        if query.outcome:
            episode_ids = self.by_status.get(query.outcome, [])
            candidates = [e for e in candidates if e.id in episode_ids]

        if query.files:
            # Episodes that involve any of the specified files
            relevant_ids = set()
            for file_path in query.files:
                relevant_ids.update(self.by_file.get(file_path, []))
            candidates = [e for e in candidates if e.id in relevant_ids]

        if query.error_type:
            episode_ids = self.by_error_type.get(query.error_type, [])
            candidates = [e for e in candidates if e.id in episode_ids]

        # SOTA: 3-axis scoring (similarity + recency + importance)
        if self.scoring_engine and query.description and self.embedder:
            try:
                query_embedding = await self.embedder.embed(query.description)

                # Use 3-axis scoring engine
                scored_episodes = []
                for episode in candidates:
                    if episode.task_description_embedding:
                        # Check min_similarity first (optimization)
                        similarity = self._cosine_similarity(query_embedding, episode.task_description_embedding)
                        if similarity >= query.min_similarity:
                            # Calculate 3-axis score
                            score = self.scoring_engine.score_episode(episode, query_embedding)
                            scored_episodes.append((episode, score))

                # Sort by composite score (similarity + recency + importance)
                scored_episodes.sort(key=lambda x: x[1].composite_score, reverse=True)
                candidates = [ep for ep, _ in scored_episodes]

                logger.debug(
                    "3axis_scoring_completed",
                    query_len=len(query.description),
                    candidates_after_filter=len(candidates),
                    scoring_enabled=True,
                )
            except Exception as e:
                logger.warning("3axis_scoring_failed_fallback_to_simple", error=str(e))
                # Fallback to simple vector search
                if query.description and self.embedder:
                    try:
                        query_embedding = await self.embedder.embed(query.description)
                        candidates_with_scores: list[tuple[Episode, float]] = []
                        for episode in candidates:
                            if episode.task_description_embedding:
                                similarity = self._cosine_similarity(
                                    query_embedding, episode.task_description_embedding
                                )
                                if similarity >= query.min_similarity:
                                    candidates_with_scores.append((episode, similarity))
                        candidates_with_scores.sort(key=lambda x: x[1], reverse=True)
                        candidates = [ep for ep, _ in candidates_with_scores]
                    except Exception:  # noqa: S110
                        pass  # Fall through to simple sort

        # Vector similarity search if description provided (no scoring engine)
        elif query.description and self.embedder:
            try:
                query_embedding = await self.embedder.embed(query.description)
                # Calculate cosine similarity and filter/sort by it
                candidates_with_scores: list[tuple[Episode, float]] = []
                for episode in candidates:
                    if episode.task_description_embedding:
                        similarity = self._cosine_similarity(query_embedding, episode.task_description_embedding)
                        if similarity >= query.min_similarity:
                            candidates_with_scores.append((episode, similarity))

                # Sort by similarity (descending)
                candidates_with_scores.sort(key=lambda x: x[1], reverse=True)
                candidates = [ep for ep, _ in candidates_with_scores]

                logger.debug(
                    "vector_search_completed",
                    query_len=len(query.description),
                    candidates_after_filter=len(candidates),
                )
            except Exception as e:
                logger.warning("vector_search_failed", error=str(e))
                # Fall back to non-vector search

        # Fallback: Simple sort by usefulness score and retrieval count
        if not query.description or not self.embedder:
            candidates.sort(
                key=lambda e: e.usefulness_score * (1 + e.retrieval_count * 0.1),
                reverse=True,
            )

        # Limit results
        results = candidates[: query.limit]

        # Update retrieval counts atomically
        for episode in results:
            async with self._get_episode_lock(episode.id):
                episode.retrieval_count += 1

        logger.info(
            "similar_episodes_found",
            result_count=len(results),
            candidate_count=len(candidates),
            filters_applied=bool(query.task_type or query.outcome or query.files or query.error_type),
        )
        record_counter("memory_similarity_searches_total")
        record_histogram("memory_similarity_results", len(results))
        record_histogram("memory_similarity_candidates", len(candidates))
        return results

    async def find_by_error_pattern(
        self,
        error_type: str,
        error_message: str | None = None,
        use_fuzzy: bool = True,
        fuzzy_threshold: float = 0.6,
    ) -> list[Episode]:
        """
        Find episodes by error pattern with regex and fuzzy matching.

        Args:
            error_type: Error type/class name
            error_message: Optional error message pattern (supports regex or plain text)
            use_fuzzy: Whether to use fuzzy matching for non-regex patterns
            fuzzy_threshold: Minimum similarity for fuzzy match (0.0-1.0)

        Returns:
            Matching episodes with scores, sorted by match quality and success status
        """
        episode_ids = self.by_error_type.get(error_type, [])
        episodes = [self.storage[eid] for eid in episode_ids if eid in self.storage]

        # Apply error message pattern matching if provided
        if error_message and episodes:
            scored_episodes: list[tuple[Episode, float]] = []

            for episode in episodes:
                score = self._match_error_message(
                    episode=episode,
                    pattern=error_message,
                    use_fuzzy=use_fuzzy,
                    fuzzy_threshold=fuzzy_threshold,
                )
                if score > 0:
                    scored_episodes.append((episode, score))

            # Sort by match score first, then by success and usefulness
            scored_episodes.sort(
                key=lambda x: (
                    x[1],  # Match score
                    x[0].outcome_status == TaskStatus.SUCCESS,
                    x[0].usefulness_score,
                ),
                reverse=True,
            )
            episodes = [ep for ep, _ in scored_episodes]
        else:
            # No message filter - sort by success and usefulness
            episodes.sort(
                key=lambda e: (
                    e.outcome_status == TaskStatus.SUCCESS,
                    e.usefulness_score,
                ),
                reverse=True,
            )

        logger.info(
            "error_pattern_episodes_found",
            error_type=error_type,
            episode_count=len(episodes),
            has_message_filter=error_message is not None,
            use_fuzzy=use_fuzzy,
        )
        record_counter("memory_error_pattern_searches_total", labels={"error_type": error_type})
        record_histogram("memory_error_pattern_results", len(episodes))
        return episodes

    def _match_error_message(
        self,
        episode: Episode,
        pattern: str,
        use_fuzzy: bool = True,
        fuzzy_threshold: float = 0.6,
    ) -> float:
        """
        Match error message against pattern using regex or fuzzy matching.

        Args:
            episode: Episode to check
            pattern: Pattern to match (regex or plain text)
            use_fuzzy: Whether to use fuzzy matching
            fuzzy_threshold: Minimum similarity threshold

        Returns:
            Match score (0.0-1.0), 0.0 if no match
        """
        # Get episode's error messages
        episode_messages = self._get_episode_error_messages(episode)
        if not episode_messages:
            return 0.0

        best_score = 0.0

        for msg in episode_messages:
            # Try regex match first
            try:
                if re.search(pattern, msg, re.IGNORECASE):
                    return 1.0  # Exact regex match
            except re.error:
                pass  # Invalid regex, fall through to other methods

            # Try exact substring match (pattern in message)
            if pattern.lower() in msg.lower():
                return 0.95  # Substring match

            # Try reverse substring match (message in pattern) for short messages
            if msg.lower() in pattern.lower():
                return 0.90  # Message is substring of pattern

            # Try keyword overlap matching
            keyword_score = self._keyword_overlap_score(pattern, msg)
            if keyword_score >= 0.5:  # At least 50% keyword overlap
                best_score = max(best_score, keyword_score * 0.85)

            # Try fuzzy matching
            if use_fuzzy:
                similarity = self._fuzzy_similarity(pattern.lower(), msg.lower())
                if similarity >= fuzzy_threshold:
                    best_score = max(best_score, similarity)

        return best_score

    def _keyword_overlap_score(self, text1: str, text2: str) -> float:
        """
        Calculate keyword overlap score between two texts.

        Focuses on significant words (3+ characters) for better matching.
        Uses instance's stop_words for filtering.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Overlap score (0.0-1.0)
        """

        def extract_keywords(text: str) -> set[str]:
            words = set(text.lower().split())
            return {w for w in words if len(w) >= 3 and w not in self.stop_words}

        kw1 = extract_keywords(text1)
        kw2 = extract_keywords(text2)

        if not kw1 or not kw2:
            return 0.0

        intersection = kw1 & kw2
        # Use minimum set size for stricter matching
        return len(intersection) / min(len(kw1), len(kw2))

    def _get_episode_error_messages(self, episode: Episode) -> list[str]:
        """Extract error messages from episode."""
        messages: list[str] = []

        # From solution pattern (often contains error description)
        if episode.solution_pattern:
            messages.append(episode.solution_pattern)

        # From task description
        if episode.task_description:
            messages.append(episode.task_description)

        # From gotchas (often contain error details)
        messages.extend(episode.gotchas)

        return messages

    def _fuzzy_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate fuzzy similarity between two strings using rapidfuzz.

        Combines multiple similarity metrics for robust matching:
        - Token set ratio: Handles word order and partial matches
        - Levenshtein ratio: Character-level similarity

        Performance: ~10-100x faster than pure Python implementation.

        Args:
            s1: First string
            s2: Second string

        Returns:
            Similarity score (0.0-1.0)
        """
        if not s1 or not s2:
            return 0.0

        if s1 == s2:
            return 1.0

        # rapidfuzz returns 0-100 scale, normalize to 0-1
        # token_set_ratio handles word reordering and partial matches well
        token_score = fuzz.token_set_ratio(s1, s2) / 100.0

        # Levenshtein normalized similarity for character-level matching
        lev_score = Levenshtein.normalized_similarity(s1, s2)

        # Combine both metrics (weighted average)
        # Token score for semantic matching, Levenshtein for typo tolerance
        return 0.5 * token_score + 0.5 * lev_score

    def find_by_project(self, project_id: str, limit: int = 10) -> list[Episode]:
        """
        Find episodes for a specific project.

        Args:
            project_id: Project identifier
            limit: Maximum results

        Returns:
            Episodes for project, sorted by recency
        """
        episode_ids = self.by_project.get(project_id, [])
        episodes = [self.storage[eid] for eid in episode_ids if eid in self.storage]

        # Sort by recency
        episodes.sort(key=lambda e: e.created_at, reverse=True)

        return episodes[:limit]

    def find_by_file(self, file_path: str, limit: int = 10) -> list[Episode]:
        """
        Find episodes involving a specific file.

        Args:
            file_path: File path
            limit: Maximum results

        Returns:
            Episodes involving file
        """
        episode_ids = self.by_file.get(file_path, [])
        episodes = [self.storage[eid] for eid in episode_ids if eid in self.storage]

        # Sort by recency and relevance
        episodes.sort(
            key=lambda e: (e.usefulness_score, e.created_at),
            reverse=True,
        )

        return episodes[:limit]

    # ============================================================
    # Feedback & Learning
    # ============================================================

    async def record_feedback(
        self,
        episode_id: str,
        helpful: bool,
        user_feedback: Literal["positive", "negative", "neutral"] | None = None,
    ) -> None:
        """
        Record feedback on episode usefulness with atomic update.

        Args:
            episode_id: Episode ID
            helpful: Whether episode was helpful
            user_feedback: Optional user feedback
        """
        episode = self.get(episode_id)
        if not episode:
            logger.warning("feedback_for_nonexistent_episode", episode_id=episode_id)
            record_counter("memory_feedback_errors_total", labels={"error": "episode_not_found"})
            return

        # Atomic update with lock
        async with self._get_episode_lock(episode_id):
            # Update usefulness score (exponential moving average)
            alpha = 0.3  # Learning rate
            feedback_score = 1.0 if helpful else 0.0
            episode.usefulness_score = alpha * feedback_score + (1 - alpha) * episode.usefulness_score

            # Store user feedback
            if user_feedback:
                episode.user_feedback = user_feedback

            logger.info(
                "feedback_recorded",
                episode_id=episode_id,
                helpful=helpful,
                new_score=episode.usefulness_score,
                has_user_feedback=user_feedback is not None,
            )
            record_counter("memory_feedback_recorded_total", labels={"helpful": str(helpful)})
            record_histogram("memory_usefulness_score", episode.usefulness_score)

    # ============================================================
    # Analytics
    # ============================================================

    def get_statistics(self) -> dict[str, Any]:
        """
        Get episodic memory statistics.

        Returns:
            Statistics dictionary
        """
        episodes = list(self.storage.values())

        if not episodes:
            return {
                "total_episodes": 0,
                "by_type": {},
                "by_status": {},
                "avg_duration_ms": 0,
                "avg_usefulness": 0,
            }

        # Calculate statistics
        total = len(episodes)
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        total_duration = 0.0
        total_usefulness = 0.0

        for episode in episodes:
            # Count by type
            type_key = episode.task_type.value
            by_type[type_key] = by_type.get(type_key, 0) + 1

            # Count by status
            status_key = episode.outcome_status.value
            by_status[status_key] = by_status.get(status_key, 0) + 1

            # Sum duration and usefulness
            total_duration += episode.duration_ms
            total_usefulness += episode.usefulness_score

        # Safe division (already checked total > 0, but explicit is better)
        return {
            "total_episodes": total,
            "by_type": by_type,
            "by_status": by_status,
            "avg_duration_ms": total_duration / total if total > 0 else 0.0,
            "avg_usefulness": total_usefulness / total if total > 0 else 0.0,
            "success_rate": by_status.get(TaskStatus.SUCCESS.value, 0) / total if total > 0 else 0.0,
            "most_referenced": sorted(episodes, key=lambda e: e.retrieval_count, reverse=True)[:5],
        }

    def get_recent(self, limit: int = 10) -> list[Episode]:
        """
        Get most recent episodes.

        Args:
            limit: Number of episodes to return

        Returns:
            Recent episodes
        """
        episodes = list(self.storage.values())
        episodes.sort(key=lambda e: e.created_at, reverse=True)
        return episodes[:limit]

    # ============================================================
    # Cleanup
    # ============================================================

    async def cleanup_old_episodes(
        self,
        max_age_days: int = 90,
        min_usefulness: float = 0.3,
        min_retrievals: int = 2,
    ) -> int:
        """
        Remove old, low-value episodes with index rebuild.

        Args:
            max_age_days: Maximum age in days
            min_usefulness: Minimum usefulness score to keep
            min_retrievals: Minimum retrieval count to keep

        Returns:
            Number of episodes removed
        """
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=max_age_days)

        # Find episodes to remove
        to_remove = []
        for episode in self.storage.values():
            if (
                episode.created_at < cutoff_date
                and episode.usefulness_score < min_usefulness
                and episode.retrieval_count < min_retrievals
            ):
                to_remove.append(episode)

        # Batch delete with index rebuild
        async with self._storage_lock:
            for episode in to_remove:
                self.storage.pop(episode.id, None)
                self._episode_locks.pop(episode.id, None)

            # Rebuild indices once
            if to_remove:
                self._rebuild_indices()

        removed_count = len(to_remove)
        logger.info(
            "episodes_cleaned_up",
            removed_count=removed_count,
            max_age_days=max_age_days,
            min_usefulness=min_usefulness,
            min_retrievals=min_retrievals,
        )
        record_counter("memory_cleanup_operations_total")
        record_histogram("memory_cleanup_removed_count", removed_count)
        return removed_count

    def _rebuild_indices(self) -> None:
        """
        Rebuild all indices from storage.

        Called after batch operations to ensure consistency.
        """
        # Clear all indices
        self.by_project.clear()
        self.by_task_type.clear()
        self.by_status.clear()
        self.by_file.clear()
        self.by_error_type.clear()

        # Rebuild from storage
        for episode in self.storage.values():
            self._update_indices(episode)

        logger.debug(
            "indices_rebuilt",
            episode_count=len(self.storage),
            index_counts={
                "by_project": len(self.by_project),
                "by_task_type": len(self.by_task_type),
                "by_status": len(self.by_status),
                "by_file": len(self.by_file),
                "by_error_type": len(self.by_error_type),
            },
        )
        record_counter("memory_index_rebuilds_total")

    # ============================================================
    # Embedding-based Semantic Matching
    # ============================================================

    async def find_by_semantic_similarity(
        self,
        query_text: str,
        top_k: int = 10,
        min_similarity: float = 0.5,
        use_cache: bool = True,
    ) -> list[tuple[Episode, float]]:
        """
        Find episodes using embedding-based semantic similarity.

        Uses vector embeddings for semantic matching beyond keyword/fuzzy matching.

        Args:
            query_text: Query text to match against episodes
            top_k: Maximum number of results
            min_similarity: Minimum cosine similarity threshold (0.0-1.0)
            use_cache: Whether to use cached results

        Returns:
            List of (Episode, similarity_score) tuples, sorted by similarity
        """
        if not self.embedder:
            logger.warning("semantic_search_no_embedder")
            return []

        # Check cache
        cache_key = f"semantic:{hash(query_text)}:{top_k}:{min_similarity}"
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                record_counter("memory_cache_hits_total", labels={"cache_type": "semantic"})
                return [(ep, 1.0) for ep in cached]  # Cached results don't have scores

        # Get query embedding (with caching)
        query_embedding = await self._get_cached_embedding(query_text)
        if not query_embedding:
            return []

        # Calculate similarities for all episodes with embeddings
        scored_episodes: list[tuple[Episode, float]] = []

        for episode in self.storage.values():
            if not episode.task_description_embedding:
                continue

            similarity = self._cosine_similarity(query_embedding, episode.task_description_embedding)
            if similarity >= min_similarity:
                scored_episodes.append((episode, similarity))

        # Sort by similarity (descending)
        scored_episodes.sort(key=lambda x: x[1], reverse=True)
        results = scored_episodes[:top_k]

        # Cache results
        if use_cache and results:
            self._put_in_cache(cache_key, [ep for ep, _ in results])

        logger.info(
            "semantic_search_completed",
            query_len=len(query_text),
            results=len(results),
            total_candidates=len(self.storage),
        )
        record_counter("memory_semantic_searches_total")
        record_histogram("memory_semantic_results", len(results))

        return results

    async def _get_cached_embedding(self, text: str) -> list[float] | None:
        """Get embedding from cache or compute it."""
        if text in self._embedding_cache:
            record_counter("memory_cache_hits_total", labels={"cache_type": "embedding"})
            return self._embedding_cache[text]

        try:
            embedding = await self.embedder.embed(text)
            # Cache embedding (limit cache size)
            if len(self._embedding_cache) >= self._cache_size:
                # Remove oldest entry (simple FIFO, could use LRU)
                oldest_key = next(iter(self._embedding_cache))
                del self._embedding_cache[oldest_key]
            self._embedding_cache[text] = embedding
            return embedding
        except Exception as e:
            logger.warning("embedding_computation_failed", error=str(e))
            return None

    # ============================================================
    # Async Batch Processing
    # ============================================================

    async def find_similar_batch(
        self,
        queries: list[SimilarityQuery],
        max_concurrency: int = 5,
    ) -> list[list[Episode]]:
        """
        Process multiple similarity queries concurrently.

        Optimized for batch processing with controlled concurrency.

        Args:
            queries: List of SimilarityQuery objects
            max_concurrency: Maximum concurrent searches

        Returns:
            List of results for each query (in same order as input)
        """
        if not queries:
            return []

        # Use semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrency)

        async def search_with_limit(query: SimilarityQuery) -> list[Episode]:
            async with semaphore:
                return await self.find_similar(query)

        # Execute all searches concurrently
        tasks = [search_with_limit(q) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions
        processed_results: list[list[Episode]] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("batch_search_failed", query_index=i, error=str(result))
                processed_results.append([])
            else:
                processed_results.append(result)

        logger.info(
            "batch_search_completed",
            query_count=len(queries),
            success_count=sum(1 for r in processed_results if r),
            max_concurrency=max_concurrency,
        )
        record_counter("memory_batch_searches_total")
        record_histogram("memory_batch_query_count", len(queries))

        return processed_results

    async def match_error_patterns_batch(
        self,
        error_patterns: list[tuple[str, str | None]],  # (error_type, error_message)
        use_fuzzy: bool = True,
        fuzzy_threshold: float = 0.6,
        max_concurrency: int = 10,
    ) -> list[list[Episode]]:
        """
        Match multiple error patterns concurrently.

        Args:
            error_patterns: List of (error_type, error_message) tuples
            use_fuzzy: Whether to use fuzzy matching
            fuzzy_threshold: Fuzzy matching threshold
            max_concurrency: Maximum concurrent searches

        Returns:
            List of matching episodes for each pattern
        """
        if not error_patterns:
            return []

        semaphore = asyncio.Semaphore(max_concurrency)

        async def search_pattern(pattern: tuple[str, str | None]) -> list[Episode]:
            async with semaphore:
                error_type, error_message = pattern
                return await self.find_by_error_pattern(
                    error_type=error_type,
                    error_message=error_message,
                    use_fuzzy=use_fuzzy,
                    fuzzy_threshold=fuzzy_threshold,
                )

        tasks = [search_pattern(p) for p in error_patterns]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed: list[list[Episode]] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("batch_error_match_failed", pattern_index=i, error=str(result))
                processed.append([])
            else:
                processed.append(result)

        logger.info(
            "batch_error_match_completed",
            pattern_count=len(error_patterns),
            total_matches=sum(len(r) for r in processed),
        )

        return processed

    # ============================================================
    # Cache Management
    # ============================================================

    def _get_from_cache(self, key: str) -> list[Episode] | None:
        """Get results from cache if not expired."""
        if key not in self._similarity_cache:
            return None

        results, timestamp = self._similarity_cache[key]
        current_time = datetime.now().timestamp()

        if current_time - timestamp > self._cache_ttl:
            # Expired, remove from cache
            del self._similarity_cache[key]
            record_counter("memory_cache_expired_total")
            return None

        return results

    def _put_in_cache(self, key: str, results: list[Episode]) -> None:
        """Put results in cache with current timestamp."""
        # Enforce cache size limit (LRU eviction)
        if len(self._similarity_cache) >= self._cache_size:
            # Remove oldest entry
            oldest_key = min(self._similarity_cache.keys(), key=lambda k: self._similarity_cache[k][1])
            del self._similarity_cache[oldest_key]
            record_counter("memory_cache_evictions_total")

        self._similarity_cache[key] = (results, datetime.now().timestamp())

    def invalidate_cache(self, pattern: str | None = None) -> int:
        """
        Invalidate cache entries.

        Args:
            pattern: Optional prefix pattern to match keys. If None, clears all cache.

        Returns:
            Number of entries invalidated
        """
        if pattern is None:
            count = len(self._similarity_cache)
            self._similarity_cache.clear()
            self._embedding_cache.clear()
            logger.info("cache_invalidated_all", count=count)
            return count

        # Pattern-based invalidation
        keys_to_remove = [k for k in self._similarity_cache if k.startswith(pattern)]
        for key in keys_to_remove:
            del self._similarity_cache[key]

        logger.info("cache_invalidated_pattern", pattern=pattern, count=len(keys_to_remove))
        return len(keys_to_remove)

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        current_time = datetime.now().timestamp()

        # Count expired entries
        expired_count = sum(1 for _, (_, ts) in self._similarity_cache.items() if current_time - ts > self._cache_ttl)

        return {
            "similarity_cache_size": len(self._similarity_cache),
            "embedding_cache_size": len(self._embedding_cache),
            "max_cache_size": self._cache_size,
            "cache_ttl_seconds": self._cache_ttl,
            "expired_entries": expired_count,
            "hit_rate": "tracked via metrics",
        }

    # ============================================================
    # Hybrid Search (Combines all methods)
    # ============================================================

    async def hybrid_search(
        self,
        query_text: str,
        error_type: str | None = None,
        error_message: str | None = None,
        task_type: TaskType | None = None,
        top_k: int = 10,
        semantic_weight: float = 0.4,
        fuzzy_weight: float = 0.3,
        keyword_weight: float = 0.3,
    ) -> list[tuple[Episode, float]]:
        """
        Hybrid search combining semantic, fuzzy, and keyword matching.

        Fuses multiple search signals for best results.

        Args:
            query_text: Query text for semantic/keyword matching
            error_type: Optional error type filter
            error_message: Optional error message for fuzzy matching
            task_type: Optional task type filter
            top_k: Maximum results
            semantic_weight: Weight for semantic similarity (0-1)
            fuzzy_weight: Weight for fuzzy matching (0-1)
            keyword_weight: Weight for keyword overlap (0-1)

        Returns:
            List of (Episode, combined_score) tuples
        """
        # Normalize weights
        total_weight = semantic_weight + fuzzy_weight + keyword_weight
        if total_weight == 0:
            return []
        semantic_weight /= total_weight
        fuzzy_weight /= total_weight
        keyword_weight /= total_weight

        # Start with all candidates
        candidates = list(self.storage.values())

        # Apply filters
        if error_type:
            error_ids = set(self.by_error_type.get(error_type, []))
            candidates = [e for e in candidates if e.id in error_ids]

        if task_type:
            type_ids = set(self.by_task_type.get(task_type, []))
            candidates = [e for e in candidates if e.id in type_ids]

        if not candidates:
            return []

        # Calculate scores for each candidate
        scored_candidates: list[tuple[Episode, float]] = []

        # Get query embedding once
        query_embedding = None
        if self.embedder and semantic_weight > 0:
            query_embedding = await self._get_cached_embedding(query_text)

        for episode in candidates:
            scores: list[float] = []
            weights: list[float] = []

            # 1. Semantic similarity (if embedder available)
            if query_embedding and episode.task_description_embedding:
                sim = self._cosine_similarity(query_embedding, episode.task_description_embedding)
                scores.append(sim)
                weights.append(semantic_weight)

            # 2. Fuzzy similarity
            if error_message:
                fuzzy_score = self._match_error_message(episode, error_message, use_fuzzy=True, fuzzy_threshold=0.0)
                scores.append(fuzzy_score)
                weights.append(fuzzy_weight)
            elif query_text:
                # Fuzzy match against task description
                episode_text = f"{episode.task_description} {episode.solution_pattern or ''}"
                fuzzy_score = self._fuzzy_similarity(query_text.lower(), episode_text.lower())
                scores.append(fuzzy_score)
                weights.append(fuzzy_weight)

            # 3. Keyword overlap
            episode_text = f"{episode.task_description} {episode.solution_pattern or ''}"
            keyword_score = self._keyword_overlap_score(query_text, episode_text)
            scores.append(keyword_score)
            weights.append(keyword_weight)

            # Calculate weighted average
            if scores:
                total_w = sum(weights)
                weighted_sum = sum(s * w for s, w in zip(scores, weights, strict=False))
                combined_score = weighted_sum / total_w if total_w > 0 else 0
                scored_candidates.append((episode, combined_score))

        # Sort by combined score
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        logger.info(
            "hybrid_search_completed",
            query_len=len(query_text),
            candidates=len(candidates),
            results=min(top_k, len(scored_candidates)),
            weights={"semantic": semantic_weight, "fuzzy": fuzzy_weight, "keyword": keyword_weight},
        )
        record_counter("memory_hybrid_searches_total")

        return scored_candidates[:top_k]
