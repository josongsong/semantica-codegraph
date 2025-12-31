"""
Bug Pattern Manager

Manages bug pattern storage, matching, and learning.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from codegraph_runtime.session_memory.infrastructure.models import (
    BugPattern,
    BugPatternMatch,
    Episode,
    ErrorObservation,
    Solution,
)
from codegraph_shared.infra.observability import get_logger, record_counter, record_histogram

if TYPE_CHECKING:
    from codegraph_runtime.session_memory.infrastructure.pattern_matcher import PatternMatcher

logger = get_logger(__name__)


class BugPatternManager:
    """
    Manages bug patterns and solutions.

    Responsibilities:
    - Add/update bug patterns
    - Match errors to known patterns
    - Learn patterns from episodes
    """

    def __init__(
        self,
        pattern_matcher: PatternMatcher,
        max_patterns: int = 500,
    ):
        """
        Initialize bug pattern manager.

        Args:
            pattern_matcher: PatternMatcher for semantic matching
            max_patterns: Maximum patterns to keep in memory
        """
        self.max_patterns = max_patterns
        self._pattern_matcher = pattern_matcher
        self.patterns: dict[str, BugPattern] = {}
        self._lock = asyncio.Lock()

    async def add_pattern(self, pattern: BugPattern) -> str:
        """
        Add or update bug pattern with memory limits.

        Args:
            pattern: Bug pattern to add

        Returns:
            Pattern ID
        """
        async with self._lock:
            # Check memory limit
            if len(self.patterns) >= self.max_patterns:
                # Remove oldest pattern with lowest occurrence count
                sorted_patterns = sorted(
                    self.patterns.items(),
                    key=lambda x: (x[1].occurrence_count, x[1].last_seen),
                )
                removed_id = sorted_patterns[0][0]
                del self.patterns[removed_id]
                logger.debug("bug_pattern_removed_for_space", removed_id=removed_id)
                record_counter("memory_bug_patterns_trimmed_total")

            self.patterns[pattern.id] = pattern
            logger.info("bug_pattern_added", pattern_name=pattern.name, pattern_id=pattern.id)
            record_counter("memory_bug_patterns_total")
            return pattern.id

    async def match_pattern(
        self,
        error_type: str,
        error_message: str | None = None,
        stack_trace: str | None = None,
        code_context: str | None = None,
        language: str = "python",
        framework: str | None = None,
        top_k: int = 5,
    ) -> list[BugPatternMatch]:
        """
        Match bug patterns against an error using hybrid matching.

        Args:
            error_type: Error type/class name
            error_message: Error message
            stack_trace: Stack trace
            code_context: Code context where error occurred
            language: Programming language
            framework: Framework name (optional)
            top_k: Number of top matches to return

        Returns:
            List of matching patterns with scores
        """
        if not self.patterns:
            return []

        observation = ErrorObservation(
            error_type=error_type,
            error_message=error_message or "",
            language=language,
            framework=framework,
            stacktrace=stack_trace,
            code_context=code_context,
        )

        matches = await self._pattern_matcher.match(
            observation=observation,
            patterns=list(self.patterns.values()),
            top_k=top_k,
        )

        logger.info(
            "bug_pattern_matches_found",
            match_count=len(matches),
            top_score=matches[0].score if matches else 0.0,
        )
        record_histogram("memory_bug_pattern_matches", len(matches))
        return matches

    def find_by_error_type(self, error_type: str) -> BugPattern | None:
        """Find pattern by error type."""
        for pattern in self.patterns.values():
            if error_type in pattern.error_types:
                return pattern
        return None

    def select_best_solution(self, pattern: BugPattern) -> Solution | None:
        """Select best solution from pattern's solutions."""
        if not pattern.solutions:
            return None

        sorted_solutions = sorted(pattern.solutions, key=lambda s: s.success_rate, reverse=True)
        return sorted_solutions[0]

    async def learn_from_episode(self, episode: Episode) -> None:
        """
        Learn bug pattern from episode.

        Args:
            episode: Episode with error observations
        """
        if not episode.error_observations:
            return

        for error in episode.error_observations:
            existing = self.find_by_error_type(error.error_type)

            if existing:
                # Update existing pattern
                self._update_pattern(existing, episode)
            else:
                # Create new pattern
                new_pattern = self._create_pattern_from_error(error, episode)
                await self.add_pattern(new_pattern)

    def _update_pattern(self, pattern: BugPattern, episode: Episode) -> None:
        """Update existing pattern with episode data."""
        from datetime import datetime

        pattern.occurrence_count += 1
        pattern.last_seen = datetime.now()

        # Add solution if task was successful
        if episode.outcome and episode.outcome.success:
            self._add_or_update_solution(pattern, episode)

    def _create_pattern_from_error(self, error: ErrorObservation, episode: Episode) -> BugPattern:
        """Create new bug pattern from error observation."""
        from datetime import datetime
        from uuid import uuid4

        pattern = BugPattern(
            id=str(uuid4()),
            name=f"Pattern: {error.error_type}",
            error_types=[error.error_type],
            error_message_patterns=[error.error_message] if error.error_message else [],
            common_causes=[],
            solutions=[],
            occurrence_count=1,
            last_seen=datetime.now(),
        )

        # Add solution if successful
        if episode.outcome and episode.outcome.success:
            self._add_or_update_solution(pattern, episode)

        return pattern

    def _add_or_update_solution(self, pattern: BugPattern, episode: Episode) -> None:
        """Add or update solution from successful episode."""
        from uuid import uuid4

        # Extract solution description
        description = self._extract_solution_description(episode)
        if not description:
            return

        # Check for similar existing solution
        for solution in pattern.solutions:
            if self._is_similar_solution(solution.description, description):
                solution.application_count += 1
                solution.success_rate = min(1.0, solution.success_rate + 0.1)
                return

        # Add new solution
        new_solution = Solution(
            id=str(uuid4()),
            description=description,
            steps=episode.interaction.key_decisions if episode.interaction else [],
            success_rate=0.7,
            application_count=1,
        )
        pattern.solutions.append(new_solution)
        pattern.resolution_count += 1

    def _extract_solution_description(self, episode: Episode) -> str | None:
        """Extract solution description from episode."""
        if episode.interaction and episode.interaction.key_decisions:
            return "; ".join(str(d) for d in episode.interaction.key_decisions[:3])
        if episode.outcome and episode.outcome.patches:
            return f"Applied {len(episode.outcome.patches)} patches"
        return None

    def _is_similar_solution(self, desc1: str, desc2: str) -> bool:
        """Check if two solution descriptions are similar."""
        # Simple similarity check based on common words
        words1 = set(desc1.lower().split())
        words2 = set(desc2.lower().split())
        if not words1 or not words2:
            return False
        overlap = len(words1 & words2) / max(len(words1), len(words2))
        return overlap > 0.7

    def get_statistics(self) -> dict[str, Any]:
        """Get bug pattern statistics."""
        total_solutions = sum(len(p.solutions) for p in self.patterns.values())
        return {
            "total_patterns": len(self.patterns),
            "total_solutions": total_solutions,
            "max_patterns": self.max_patterns,
        }
