"""
Git History Adapter

Enriches search hits with git history metrics (churn, recency, ownership).
"""

import time
from collections import defaultdict
from pathlib import Path

from codegraph_shared.common.observability import get_logger, record_histogram
from codegraph_engine.analysis_indexing.infrastructure.git_history.git_service import create_git_service
from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit
from codegraph_search.infrastructure.fusion.engine import FusedHit

logger = get_logger(__name__)


class GitHistoryAdapter:
    """
    Enriches search hits with git history metrics.

    Adds metadata:
    - churn_score: Code change frequency (0-1)
    - last_modified_days: Days since last modification
    - author_count: Number of distinct authors
    - is_hotspot: Whether code is a hotspot (high churn/many authors)
    - primary_author: Main contributor email
    """

    def __init__(self, repo_path: str | Path, cache_ttl_seconds: int = 3600):
        """
        Initialize Git history adapter.

        Args:
            repo_path: Path to git repository
            cache_ttl_seconds: Cache TTL for metrics (default: 1 hour)
        """
        self.repo_path = Path(repo_path)
        self.git_service = create_git_service(repo_path)
        self.cache_ttl = cache_ttl_seconds

        # Cache: {file_path: (metrics, timestamp)}
        self._metrics_cache: dict[str, tuple[dict, float]] = {}

        if self.git_service is None:
            logger.warning("Git service unavailable - git enrichment disabled")
            self.enabled = False
        else:
            self.enabled = True
            logger.info(f"Git enrichment enabled for {repo_path}")

    def enrich_hits(self, hits: list[SearchHit]) -> list[SearchHit]:
        """
        Enrich search hits with git metrics.

        Args:
            hits: Search hits to enrich

        Returns:
            Enriched hits (in-place modification + return)
        """
        if not self.enabled or not hits:
            return hits

        start_time = time.perf_counter()
        enriched_count = 0

        # Group hits by file for efficient batch processing
        file_chunks: dict[str, list[SearchHit]] = defaultdict(list)
        for hit in hits:
            if hit.file_path:
                file_chunks[hit.file_path].append(hit)

        # Enrich each file's hits
        for file_path, file_hits in file_chunks.items():
            metrics = self._get_file_metrics(file_path)
            if metrics:
                for hit in file_hits:
                    hit.metadata.update(metrics)
                    enriched_count += 1

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        record_histogram("retrieval_git_enrichment_latency_ms", elapsed_ms)

        logger.debug(f"Git enrichment: {enriched_count}/{len(hits)} hits enriched in {elapsed_ms:.1f}ms")

        return hits

    def enrich_fused_hits(self, hits: list[FusedHit]) -> list[FusedHit]:
        """
        Enrich fused hits with git metrics.

        Args:
            hits: Fused hits to enrich

        Returns:
            Enriched hits (in-place modification + return)
        """
        if not self.enabled or not hits:
            return hits

        start_time = time.perf_counter()
        enriched_count = 0

        for hit in hits:
            if hit.file_path:
                metrics = self._get_file_metrics(hit.file_path)
                if metrics:
                    hit.metadata.update(metrics)
                    enriched_count += 1

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        record_histogram("retrieval_git_enrichment_fused_latency_ms", elapsed_ms)

        logger.debug(f"Git enrichment (fused): {enriched_count}/{len(hits)} hits enriched in {elapsed_ms:.1f}ms")

        return hits

    def _get_file_metrics(self, file_path: str) -> dict | None:
        """
        Get git metrics for a file (with caching).

        Args:
            file_path: File path relative to repo root

        Returns:
            Dict of git metrics or None if unavailable
        """
        if not self.git_service:
            return None

        # Check cache
        current_time = time.time()
        if file_path in self._metrics_cache:
            metrics, cached_time = self._metrics_cache[file_path]
            if current_time - cached_time < self.cache_ttl:
                return metrics

        # Compute metrics
        try:
            metrics = self._compute_file_metrics(file_path)
            self._metrics_cache[file_path] = (metrics, current_time)
            return metrics
        except Exception as e:
            logger.debug(f"Failed to compute git metrics for {file_path}: {e}")
            return None

    def _compute_file_metrics(self, file_path: str) -> dict:
        """
        Compute git metrics for a file.

        Args:
            file_path: File path relative to repo root

        Returns:
            Dict with git metrics
        """
        # Get file authors
        authors = self.git_service.get_file_authors(file_path)
        author_count = len(authors)

        # Get primary author (most commits)
        primary_author = None
        if authors:
            primary_author = max(authors.values(), key=lambda a: a.commit_count).email

        # Get file history (last 50 commits)
        history = self.git_service.get_file_history(file_path, max_commits=50)

        # Calculate metrics
        if history:
            # Most recent commit
            latest_commit, _ = history[0]
            last_modified_date = latest_commit.commit_date
            from datetime import datetime

            days_since_last_change = (datetime.now() - last_modified_date.replace(tzinfo=None)).days

            # Churn score approximation (commits per month)
            # Simplified: normalize by total commits
            total_commits = len(history)
            if total_commits > 0:
                # Simple heuristic: more commits = higher churn
                # Normalize: 1 commit = 0.05, 20+ commits = 1.0
                churn_score = min(total_commits * 0.05, 1.0)
            else:
                churn_score = 0.0

            # Hotspot detection
            is_hotspot = churn_score > 0.7 or author_count >= 5
        else:
            days_since_last_change = 9999
            churn_score = 0.0
            is_hotspot = False

        return {
            "git_churn_score": round(churn_score, 3),
            "git_last_modified_days": days_since_last_change,
            "git_author_count": author_count,
            "git_is_hotspot": is_hotspot,
            "git_primary_author": primary_author,
        }

    def clear_cache(self):
        """Clear metrics cache."""
        self._metrics_cache.clear()
        logger.debug("Git metrics cache cleared")
