"""
Pattern Repository Implementations (SOTA)

Specialized repositories for BugPattern, CodePattern, CodeRule.
All extend BoundedInMemoryRepository with pattern-specific logic.

SOTA: Eliminates ~800 lines of duplicate code across the original
BugPatternManager, CodePatternManager, CodeRuleManager.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from codegraph_runtime.session_memory.domain.models import (
    BugPattern,
    CodePattern,
    CodeRule,
    PatternCategory,
    Solution,
)

from .base import BoundedInMemoryRepository


class BugPatternRepository(BoundedInMemoryRepository[BugPattern]):
    """
    Repository for BugPatterns with specialized matching logic.

    SOTA: Replaces the 400+ line BugPatternManager with clean,
    focused repository that only handles storage and retrieval.
    """

    def __init__(self, max_patterns: int = 500) -> None:
        """
        Initialize bug pattern repository.

        Uses occurrence_count for eviction priority (least seen = evicted first).
        """
        super().__init__(
            max_size=max_patterns,
            eviction_batch_size=10,
            sort_key=lambda p: (p.occurrence_count, p.updated_at),
        )

    async def add_or_update(
        self,
        error_type: str,
        solution_description: str,
        solution_approach: str = "",
        error_message_pattern: str | None = None,
        language: str = "python",
        framework: str | None = None,
        common_causes: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """
        Add or update a bug pattern.

        If pattern with same error_type exists, update it.
        Otherwise create new pattern.
        """
        # Find existing pattern with same error_type
        existing = await self.find_by_error_type(error_type)

        if existing:
            # Update existing pattern
            existing.occurrence_count += 1
            existing.last_seen = datetime.now()

            # Add solution if unique
            if solution_description:
                solution = Solution(
                    id=str(uuid4()),
                    description=solution_description,
                    approach=solution_approach,
                )
                if not any(s.description == solution_description for s in existing.solutions):
                    existing.solutions.append(solution)
                    # Keep only top 5 solutions by success rate
                    existing.solutions = sorted(
                        existing.solutions,
                        key=lambda s: s.success_rate,
                        reverse=True,
                    )[:5]

            # Update common causes
            if common_causes:
                for cause in common_causes:
                    if cause not in existing.common_causes:
                        existing.common_causes.append(cause)
                existing.common_causes = existing.common_causes[:10]

            return await self.save(existing)

        # Create new pattern
        pattern = BugPattern(
            id=str(uuid4()),
            name=f"Pattern for {error_type}",
            error_types=[error_type],
            error_message_patterns=[error_message_pattern] if error_message_pattern else [],
            languages=[language],
            frameworks=[framework] if framework else [],
            common_causes=common_causes or [],
            tags=tags or [],
            solutions=[
                Solution(
                    id=str(uuid4()),
                    description=solution_description,
                    approach=solution_approach,
                )
            ]
            if solution_description
            else [],
            occurrence_count=1,
            last_seen=datetime.now(),
        )

        return await self.save(pattern)

    async def find_by_error_type(
        self,
        error_type: str,
        language: str | None = None,
    ) -> BugPattern | None:
        """Find pattern by error type."""
        patterns = await self.find_by(
            lambda p: error_type in p.error_types and (language is None or language in p.languages)
        )
        return patterns[0] if patterns else None

    async def find_matching(
        self,
        error_type: str,
        language: str = "python",
        framework: str | None = None,
        limit: int = 5,
    ) -> list[BugPattern]:
        """Find patterns matching error context."""
        results = await self.find_by(
            lambda p: (
                error_type in p.error_types
                and language in p.languages
                and (framework is None or not p.frameworks or framework in p.frameworks)
            ),
            limit=limit,
        )

        # Sort by occurrence count (most common first)
        return sorted(results, key=lambda p: p.occurrence_count, reverse=True)

    async def reinforce_solution(
        self,
        pattern_id: str,
        solution_description: str,
        success: bool,
    ) -> None:
        """Reinforce or weaken a solution based on outcome."""
        pattern = await self.get(pattern_id)
        if not pattern:
            return

        for solution in pattern.solutions:
            if solution.description == solution_description:
                solution.application_count += 1
                # EMA update
                alpha = 0.1
                new_rate = 1.0 if success else 0.0
                solution.success_rate = alpha * new_rate + (1 - alpha) * solution.success_rate
                break

        await self.save(pattern)

    async def get_best_solution(
        self,
        error_type: str,
        language: str = "python",
    ) -> Solution | None:
        """Get the best solution for an error type."""
        pattern = await self.find_by_error_type(error_type, language)
        if not pattern or not pattern.solutions:
            return None

        # Return highest success rate solution
        return max(pattern.solutions, key=lambda s: s.success_rate)

    def get_statistics(self) -> dict[str, Any]:
        """Get repository statistics."""
        stats = super().get_statistics()

        total_solutions = sum(len(p.solutions) for p in self._storage.values())
        avg_solutions = total_solutions / len(self._storage) if self._storage else 0

        stats.update(
            {
                "total_solutions": total_solutions,
                "avg_solutions_per_pattern": avg_solutions,
                "unique_error_types": len({et for p in self._storage.values() for et in p.error_types}),
            }
        )
        return stats


class CodePatternRepository(BoundedInMemoryRepository[CodePattern]):
    """
    Repository for CodePatterns (refactoring, optimization patterns).

    SOTA: Replaces CodePatternManager with clean repository implementation.
    """

    def __init__(self, max_patterns: int = 200) -> None:
        """Initialize code pattern repository."""
        super().__init__(
            max_size=max_patterns,
            eviction_batch_size=5,
            sort_key=lambda p: (p.application_count, p.success_rate),
        )

    async def add(
        self,
        name: str,
        category: str,
        description: str,
        before_pattern: str | None = None,
        after_pattern: str | None = None,
        languages: list[str] | None = None,
    ) -> str:
        """Add a new code pattern."""
        pattern = CodePattern(
            id=str(uuid4()),
            name=name,
            category=category,
            description=description,
            before_pattern=before_pattern,
            after_pattern=after_pattern,
            applicable_languages=languages or ["python"],
        )
        return await self.save(pattern)

    async def find_by_category(
        self,
        category: str,
        language: str | None = None,
        limit: int = 10,
    ) -> list[CodePattern]:
        """Find patterns by category."""
        return await self.find_by(
            lambda p: (p.category == category and (language is None or language in p.applicable_languages)),
            limit=limit,
        )

    async def find_applicable(
        self,
        code: str,
        language: str = "python",
        limit: int = 5,
    ) -> list[CodePattern]:
        """Find patterns applicable to given code."""
        import re

        results = []

        for pattern in self._storage.values():
            if language not in pattern.applicable_languages:
                continue

            if pattern.before_pattern:
                try:
                    if re.search(pattern.before_pattern, code):
                        results.append(pattern)
                except re.error:
                    # Skip invalid regex patterns
                    pass

        # Sort by success rate
        results = sorted(results, key=lambda p: p.success_rate, reverse=True)
        return results[:limit]

    async def reinforce(
        self,
        pattern_id: str,
        success: bool,
        ema_alpha: float = 0.1,
    ) -> None:
        """Reinforce or weaken pattern based on application outcome."""
        pattern = await self.get(pattern_id)
        if not pattern:
            return

        pattern.application_count += 1
        new_rate = 1.0 if success else 0.0
        pattern.success_rate = ema_alpha * new_rate + (1 - ema_alpha) * pattern.success_rate

        await self.save(pattern)


class CodeRuleRepository(BoundedInMemoryRepository[CodeRule]):
    """
    Repository for CodeRules (learned transformation rules).

    SOTA: Replaces CodeRuleManager with clean repository that focuses
    on storage, retrieval, and confidence-based management.
    """

    def __init__(
        self,
        max_rules: int = 1000,
        min_confidence_threshold: float = 0.3,
        promotion_threshold: float = 0.8,
    ) -> None:
        """
        Initialize code rule repository.

        Args:
            max_rules: Maximum rules to store
            min_confidence_threshold: Rules below this are candidates for removal
            promotion_threshold: Rules above this are considered "trusted"
        """
        super().__init__(
            max_size=max_rules,
            eviction_batch_size=20,
            sort_key=lambda r: r.confidence,  # Lowest confidence evicted first
        )
        self._min_confidence = min_confidence_threshold
        self._promotion_threshold = promotion_threshold

    async def add_rule(
        self,
        name: str,
        description: str,
        category: PatternCategory,
        before_pattern: str = "",
        after_pattern: str = "",
        pattern_type: str = "literal",
        languages: list[str] | None = None,
        initial_confidence: float = 0.5,
    ) -> str:
        """Add a new code rule."""
        # Check for duplicate
        existing = await self.find_by_name(name)
        if existing:
            # Reinforce existing rule
            existing.observation_count += 1
            return await self.save(existing)

        rule = CodeRule(
            id=str(uuid4()),
            name=name,
            description=description,
            category=category,
            before_pattern=before_pattern,
            after_pattern=after_pattern,
            pattern_type=pattern_type,
            languages=languages or ["python"],
            confidence=initial_confidence,
            min_confidence_threshold=self._min_confidence,
            promotion_threshold=self._promotion_threshold,
        )
        return await self.save(rule)

    async def find_by_name(self, name: str) -> CodeRule | None:
        """Find rule by name."""
        rules = await self.find_by(lambda r: r.name == name)
        return rules[0] if rules else None

    async def find_by_category(
        self,
        category: PatternCategory,
        language: str | None = None,
        min_confidence: float | None = None,
        trusted_only: bool = False,
        limit: int = 20,
    ) -> list[CodeRule]:
        """Find rules by category and filters."""
        min_conf = min_confidence or self._min_confidence

        def matches(r: CodeRule) -> bool:
            if r.category != category:
                return False
            if language and language not in r.languages:
                return False
            if r.confidence < min_conf:
                return False
            if trusted_only and not r.is_trusted:
                return False
            return True

        results = await self.find_by(matches, limit=limit)
        return sorted(results, key=lambda r: r.confidence, reverse=True)

    async def find_applicable(
        self,
        code: str,
        language: str = "python",
        min_confidence: float | None = None,
    ) -> list[CodeRule]:
        """Find rules applicable to given code."""
        import re

        min_conf = min_confidence or self._min_confidence
        results = []

        for rule in self._storage.values():
            if language not in rule.languages:
                continue
            if rule.confidence < min_conf:
                continue

            if rule.pattern_type == "regex" and rule.before_pattern:
                try:
                    if re.search(rule.before_pattern, code):
                        results.append(rule)
                except re.error:
                    pass
            elif rule.pattern_type == "literal" and rule.before_pattern:
                if rule.before_pattern in code:
                    results.append(rule)

        return sorted(results, key=lambda r: r.confidence, reverse=True)

    async def reinforce(
        self,
        rule_id: str,
        success: bool,
        weight: float = 0.1,
    ) -> CodeRule | None:
        """Reinforce or weaken a rule based on outcome."""
        rule = await self.get(rule_id)
        if not rule:
            return None

        rule.reinforce(success, weight)
        await self.save(rule)
        return rule

    async def cleanup_weak_rules(self, min_observations: int = 3) -> int:
        """Remove rules with confidence below threshold."""
        return await self.evict_below_threshold(
            score_fn=lambda r: r.confidence,
            threshold=self._min_confidence,
            min_observations=min_observations,
        )

    async def get_trusted_rules(
        self,
        category: PatternCategory | None = None,
        language: str | None = None,
    ) -> list[CodeRule]:
        """Get only trusted (high confidence + enough observations) rules."""

        def is_trusted(r: CodeRule) -> bool:
            if not r.is_trusted:
                return False
            if category and r.category != category:
                return False
            if language and language not in r.languages:
                return False
            return True

        return await self.find_by(is_trusted)

    def get_statistics(self) -> dict[str, Any]:
        """Get repository statistics."""
        stats = super().get_statistics()

        if self._storage:
            confidences = [r.confidence for r in self._storage.values()]
            trusted = sum(1 for r in self._storage.values() if r.is_trusted)
            weak = sum(
                1 for r in self._storage.values() if r.confidence < self._min_confidence and r.observation_count >= 3
            )

            stats.update(
                {
                    "avg_confidence": sum(confidences) / len(confidences),
                    "min_confidence": min(confidences),
                    "max_confidence": max(confidences),
                    "trusted_rules": trusted,
                    "weak_rules_candidates": weak,
                    "by_category": {
                        cat.value: sum(1 for r in self._storage.values() if r.category == cat)
                        for cat in PatternCategory
                    },
                }
            )

        return stats
