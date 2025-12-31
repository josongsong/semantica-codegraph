"""
Smart Filtering Integration

Integrates coverage and error-prone filtering into retrieval pipeline.

Usage:
    filter_service = SmartFilterService(
        coverage_storage=coverage_storage,
        git_service=git_service,
    )

    # Filter results
    filtered = await filter_service.apply_filters(
        results=fused_results,
        config=FilterConfig(min_coverage=0.5, exclude_error_prone=True)
    )

    # Or just enrich with metadata
    enriched = await filter_service.enrich_with_metrics(fused_results)
"""

from typing import Any

from codegraph_shared.common.observability import get_logger

from .error_prone import ErrorProneScorer
from .models import FilterConfig

logger = get_logger(__name__)


class SmartFilterService:
    """
    Service for applying smart filters to retrieval results.

    Integrates:
    - Test coverage filtering
    - Error-prone detection
    - Recency scoring
    - Quality-based filtering
    """

    def __init__(
        self,
        coverage_storage: Any,
        git_service: Any | None = None,
        enable_error_prone: bool = True,
    ):
        """
        Initialize filter service.

        Args:
            coverage_storage: CoverageStorage instance
            git_service: GitService for history metrics (optional)
            enable_error_prone: Enable error-prone detection
        """
        self.coverage_storage = coverage_storage
        self.git_service = git_service
        self.enable_error_prone = enable_error_prone

        if enable_error_prone:
            self.error_prone_scorer = ErrorProneScorer()
        else:
            self.error_prone_scorer = None

    async def apply_filters(
        self,
        results: list[Any],
        config: FilterConfig,
    ) -> list[Any]:
        """
        Apply smart filters to retrieval results.

        Args:
            results: List of retrieval results (FusedResultV3, etc.)
            config: Filter configuration

        Returns:
            Filtered and optionally re-ranked results
        """
        if not results:
            return []

        # Enrich with metrics
        enriched = await self.enrich_with_metrics(results)

        # Apply filters
        filtered = []

        for result in enriched:
            # Coverage filter
            if config.min_coverage > 0:
                coverage = result.metadata.get("coverage_metrics", {}).get("line_coverage", 0.0)
                if coverage < config.min_coverage:
                    logger.debug(f"Filtered {result.chunk_id[:8]}: low coverage {coverage:.2f}")
                    continue

            # Require tests filter
            if config.require_tests:
                has_tests = result.metadata.get("coverage_metrics", {}).get("has_tests", False)
                if not has_tests:
                    logger.debug(f"Filtered {result.chunk_id[:8]}: no tests")
                    continue

            # Error-prone filter
            if config.exclude_error_prone:
                error_score = result.metadata.get("error_prone_score", 0.0)
                if error_score > config.max_error_prone_score:
                    logger.debug(f"Filtered {result.chunk_id[:8]}: error-prone {error_score:.2f}")
                    continue

            # Quality filter
            if config.min_quality_level != "none":
                quality = result.metadata.get("coverage_metrics", {}).get("coverage_quality", "none")
                if not self._meets_quality_level(quality, config.min_quality_level):
                    logger.debug(f"Filtered {result.chunk_id[:8]}: quality {quality}")
                    continue

            filtered.append(result)

        # Re-rank if recency preferred
        if config.prefer_recent and self.git_service:
            filtered = self._apply_recency_boost(filtered, config.recency_weight)

        logger.info(f"Smart filtering: {len(results)} → {len(filtered)} results")
        return filtered

    async def enrich_with_metrics(
        self,
        results: list[Any],
    ) -> list[Any]:
        """
        Enrich results with coverage and error-prone metrics.

        Adds to result.metadata:
        - coverage_metrics: CoverageMetrics dict
        - error_prone_score: float (0-1)
        - error_prone_metrics: ErrorProneMetrics dict

        Args:
            results: List of retrieval results

        Returns:
            Results with enriched metadata
        """
        chunk_ids = [r.chunk_id for r in results]

        # Batch fetch coverage
        coverage_map = {}
        for chunk_id in chunk_ids:
            coverage = await self.coverage_storage.get_chunk_coverage(chunk_id)
            if coverage:
                coverage_map[chunk_id] = coverage

        # Batch fetch git metrics (if available)
        git_map = {}
        if self.git_service:
            # Assume git_service has batch method
            try:
                git_map = await self._fetch_git_metrics_batch(chunk_ids)
            except Exception as e:
                logger.warning(f"Failed to fetch git metrics: {e}")

        # Enrich each result
        for result in results:
            chunk_id = result.chunk_id

            # Add coverage metrics
            coverage = coverage_map.get(chunk_id)
            if coverage:
                result.metadata["coverage_metrics"] = {
                    "line_coverage": coverage.line_coverage,
                    "has_tests": coverage.has_tests,
                    "test_count": coverage.test_count,
                    "coverage_quality": coverage.coverage_quality,
                }
            else:
                result.metadata["coverage_metrics"] = {
                    "line_coverage": 0.0,
                    "has_tests": False,
                    "test_count": 0,
                    "coverage_quality": "none",
                }

            # Calculate error-prone score
            if self.error_prone_scorer:
                git_metrics = git_map.get(chunk_id, {})
                coverage_metrics = result.metadata["coverage_metrics"]

                error_prone = self.error_prone_scorer.calculate(
                    chunk_id=chunk_id,
                    git_metrics=git_metrics,
                    coverage_metrics=coverage_metrics,
                    complexity_metrics={},  # TODO: Add complexity
                )

                result.metadata["error_prone_score"] = error_prone.error_prone_score
                result.metadata["error_prone_metrics"] = {
                    "risk_level": error_prone.risk_level,
                    "primary_reason": error_prone.primary_reason.value if error_prone.primary_reason else None,
                    "churn_risk": error_prone.churn_risk,
                    "author_risk": error_prone.author_risk,
                    "coverage_risk": error_prone.coverage_risk,
                }

        return results

    async def _fetch_git_metrics_batch(self, chunk_ids: list[str]) -> dict[str, dict]:
        """Fetch git metrics for multiple chunks."""
        # Placeholder - implement based on git_service interface
        # Should return dict mapping chunk_id to git metrics
        return {}

    def _meets_quality_level(self, actual: str, required: str) -> bool:
        """Check if actual quality meets required level."""
        levels = ["none", "low", "medium", "high", "excellent"]
        try:
            actual_idx = levels.index(actual)
            required_idx = levels.index(required)
            return actual_idx >= required_idx
        except ValueError:
            return False

    def _apply_recency_boost(self, results: list[Any], weight: float) -> list[Any]:
        """
        Boost scores for recently modified code.

        Args:
            results: Results to boost
            weight: Boost weight (0.0-1.0)

        Returns:
            Re-ranked results
        """
        for result in results:
            git_metrics = result.metadata.get("git_metrics", {})
            days_since = git_metrics.get("days_since_last_change", 999)

            # Recency boost: decay over 90 days
            if days_since < 90:
                recency_factor = 1.0 - (days_since / 90.0)
                boost = recency_factor * weight
                result.final_score *= 1.0 + boost

        # Re-sort
        results.sort(key=lambda r: r.final_score, reverse=True)
        return results


# Convenience factory
def create_filter_service(
    coverage_storage: Any,
    git_service: Any | None = None,
    enable_error_prone: bool = True,
) -> SmartFilterService:
    """
    Factory for SmartFilterService.

    Args:
        coverage_storage: CoverageStorage instance
        git_service: Optional GitService
        enable_error_prone: Enable error-prone detection

    Returns:
        Configured filter service
    """
    return SmartFilterService(
        coverage_storage=coverage_storage,
        git_service=git_service,
        enable_error_prone=enable_error_prone,
    )
