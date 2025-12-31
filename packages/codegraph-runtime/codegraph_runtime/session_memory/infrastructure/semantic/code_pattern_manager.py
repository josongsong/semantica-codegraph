"""
Code Pattern Manager

Manages code pattern storage, learning, and matching.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from codegraph_runtime.session_memory.infrastructure.models import CodePattern, Episode
from codegraph_shared.infra.observability import get_logger, record_counter, record_histogram

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class CodePatternManager:
    """
    Manages code patterns (refactoring, optimization).

    Responsibilities:
    - Add/update code patterns
    - Find applicable patterns for context
    - Learn patterns from episodes
    """

    def __init__(self, max_patterns: int = 200):
        """
        Initialize code pattern manager.

        Args:
            max_patterns: Maximum patterns to keep in memory
        """
        self.max_patterns = max_patterns
        self.patterns: dict[str, CodePattern] = {}
        self._lock = asyncio.Lock()

    async def add_pattern(self, pattern: CodePattern) -> str:
        """
        Add or update code pattern with memory limits.

        Args:
            pattern: Code pattern to add

        Returns:
            Pattern ID
        """
        async with self._lock:
            # Check memory limit
            if len(self.patterns) >= self.max_patterns:
                # Remove oldest pattern with lowest success rate and application count
                sorted_patterns = sorted(
                    self.patterns.items(),
                    key=lambda x: (x[1].success_rate, x[1].application_count),
                )
                removed_id = sorted_patterns[0][0]
                del self.patterns[removed_id]
                logger.debug("code_pattern_removed_for_space", removed_id=removed_id)
                record_counter("memory_code_patterns_trimmed_total")

            self.patterns[pattern.id] = pattern
            logger.info(
                "code_pattern_added",
                pattern_name=pattern.name,
                category=pattern.category,
                pattern_id=pattern.id,
            )
            record_counter("memory_code_patterns_total", labels={"category": pattern.category})
            return pattern.id

    def find_applicable(
        self,
        language: str,
        code_context: str | None = None,
    ) -> list[CodePattern]:
        """
        Find applicable code patterns for given context.

        Args:
            language: Programming language
            code_context: Optional code context for pattern detection

        Returns:
            List of applicable patterns
        """
        applicable = []

        for pattern in self.patterns.values():
            if language in pattern.applicable_languages:
                # TODO: Check pattern detection rules
                applicable.append(pattern)

        # Sort by success rate and impact
        applicable.sort(
            key=lambda p: (
                p.success_rate,
                p.readability_impact + p.maintainability_impact,
            ),
            reverse=True,
        )

        logger.info("applicable_code_patterns_found", pattern_count=len(applicable), language=language)
        record_histogram("memory_applicable_code_patterns", len(applicable))
        return applicable

    async def learn_from_episode(self, episode: Episode) -> None:
        """
        Learn code pattern from refactoring episode.

        Analyzes patches to extract:
        - Code transformation patterns (before/after)
        - Refactoring categories (extract method, rename, etc.)
        - Impact metrics

        Args:
            episode: Refactoring episode with patches
        """
        if not episode.patches:
            logger.debug("no_patches_for_code_pattern", episode_id=episode.id)
            return

        # Analyze patches to extract pattern info
        pattern_info = self._analyze_patches(episode)

        if not pattern_info:
            logger.debug("no_pattern_extracted", episode_id=episode.id)
            record_counter("memory_code_pattern_learning_attempts_total", labels={"status": "no_pattern"})
            return

        # Check if similar pattern exists
        existing = self._find_similar(pattern_info)

        if existing:
            await self._reinforce_existing(existing, episode)
        else:
            await self._create_new_pattern(pattern_info, episode)

    async def _reinforce_existing(self, existing: CodePattern, episode: Episode) -> None:
        """Reinforce existing pattern."""
        async with self._lock:
            existing.application_count += 1

            # Update success rate based on episode outcome
            success = 1.0 if episode.outcome_status.value == "success" else 0.0
            n = existing.application_count
            existing.success_rate = ((existing.success_rate * (n - 1)) + success) / n

            logger.debug(
                "code_pattern_reinforced",
                pattern_id=existing.id,
                application_count=existing.application_count,
            )
            record_counter("memory_code_pattern_reinforcements_total")

    async def _create_new_pattern(self, pattern_info: dict[str, Any], episode: Episode) -> None:
        """Create new pattern from episode."""
        new_pattern = CodePattern(
            id=str(uuid4()),
            name=pattern_info["name"],
            category=pattern_info["category"],
            description=pattern_info.get("description", ""),
            applicable_languages=pattern_info.get("languages", ["python"]),
            before_pattern=pattern_info.get("before_pattern"),
            after_pattern=pattern_info.get("after_pattern"),
            detection_rules=pattern_info.get("detection_rules", []),
            success_rate=1.0 if episode.outcome_status.value == "success" else 0.5,
            application_count=1,
            readability_impact=pattern_info.get("readability_impact", 0.0),
            maintainability_impact=pattern_info.get("maintainability_impact", 0.0),
        )

        await self.add_pattern(new_pattern)
        logger.info(
            "new_code_pattern_learned",
            pattern_id=new_pattern.id,
            category=new_pattern.category,
        )
        record_counter("memory_new_code_patterns_learned_total", labels={"category": new_pattern.category})

    def _analyze_patches(self, episode: Episode) -> dict[str, Any] | None:
        """
        Analyze patches to extract code pattern information.

        Detects common refactoring patterns:
        - Extract method/function
        - Rename variable/function/class
        - Move to module
        - Simplify conditionals
        - Extract constant
        - Add type hints

        Args:
            episode: Episode with patches

        Returns:
            Pattern info dict or None if no pattern detected
        """
        if not episode.patches:
            return None

        # Aggregate patch statistics
        total_additions = 0
        total_deletions = 0
        files_changed: list[str] = []
        languages: set[str] = set()

        for patch in episode.patches:
            # Count additions/deletions
            additions, deletions = self._count_patch_lines(patch)
            total_additions += additions
            total_deletions += deletions

            # Track files
            if hasattr(patch, "file_path") and patch.file_path:
                files_changed.append(patch.file_path)
                lang = self._detect_language(patch.file_path)
                if lang:
                    languages.add(lang)

        # Detect pattern category based on task description and patch characteristics
        category = self._detect_category(episode, total_additions, total_deletions)

        if not category:
            return None

        # Build pattern info
        pattern_info: dict[str, Any] = {
            "name": self._generate_name(episode, category),
            "category": category,
            "description": episode.plan_summary or episode.task_description,
            "languages": list(languages) if languages else ["python"],
            "files_affected": len(files_changed),
            "lines_added": total_additions,
            "lines_removed": total_deletions,
        }

        # Extract before/after patterns if available
        before_after = self._extract_before_after(episode.patches)
        if before_after:
            pattern_info["before_pattern"] = before_after.get("before")
            pattern_info["after_pattern"] = before_after.get("after")

        # Calculate impact metrics
        pattern_info["readability_impact"] = self._estimate_readability_impact(
            category, total_additions, total_deletions
        )
        pattern_info["maintainability_impact"] = self._estimate_maintainability_impact(category, files_changed)

        return pattern_info

    def _count_patch_lines(self, patch: Any) -> tuple[int, int]:
        """Count additions and deletions in a patch."""
        additions = 0
        deletions = 0

        # Handle different patch formats
        content = ""
        if hasattr(patch, "diff"):
            content = patch.diff
        elif hasattr(patch, "content"):
            content = patch.content
        elif isinstance(patch, str):
            content = patch

        for line in content.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

        return additions, deletions

    def _detect_language(self, file_path: str) -> str | None:
        """Detect programming language from file path."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".cpp": "cpp",
            ".c": "c",
            ".cs": "csharp",
        }

        for ext, lang in ext_map.items():
            if file_path.endswith(ext):
                return lang
        return None

    def _detect_category(
        self,
        episode: Episode,
        additions: int,
        deletions: int,
    ) -> str | None:
        """
        Detect refactoring pattern category.

        Categories:
        - extract_method: Large addition with moderate deletion
        - rename: Similar additions and deletions
        - simplify: More deletions than additions
        - type_hints: Additions with type annotations
        - extract_constant: Small additions
        - restructure: Large changes across files
        """
        desc = (episode.task_description + " " + (episode.plan_summary or "")).lower()

        # Keyword-based detection
        keyword_categories = [
            (["extract", "refactor out", "pull out"], "extract_method"),
            (["rename", "change name"], "rename"),
            (["simplify", "reduce", "clean up"], "simplify"),
            (["type hint", "typing", "annotation"], "type_hints"),
            (["constant", "magic number"], "extract_constant"),
            (["move", "restructure", "reorganize"], "restructure"),
        ]

        for keywords, category in keyword_categories:
            if any(kw in desc for kw in keywords):
                return category

        # Heuristic detection based on patch stats
        if additions > 0 and deletions > 0:
            ratio = additions / deletions if deletions > 0 else float("inf")

            if 0.8 <= ratio <= 1.2 and additions < 20:
                return "rename"
            if ratio > 2.0:
                return "extract_method"
            if ratio < 0.5:
                return "simplify"

        # Default for refactoring episodes
        if additions > 0 or deletions > 0:
            return "refactoring"

        return None

    def _generate_name(self, episode: Episode, category: str) -> str:
        """Generate descriptive pattern name."""
        # Clean up task description for name
        desc = episode.task_description[:50] if episode.task_description else ""
        desc = desc.replace("\n", " ").strip()

        category_prefix = {
            "extract_method": "Extract:",
            "rename": "Rename:",
            "simplify": "Simplify:",
            "type_hints": "Add Types:",
            "extract_constant": "Extract Const:",
            "restructure": "Restructure:",
            "refactoring": "Refactor:",
        }

        prefix = category_prefix.get(category, "Pattern:")
        return f"{prefix} {desc}" if desc else f"{prefix} {category}"

    def _extract_before_after(self, patches: list[Any]) -> dict[str, str] | None:
        """Extract before/after code snippets from patches."""
        if not patches:
            return None

        before_lines: list[str] = []
        after_lines: list[str] = []

        for patch in patches[:1]:  # Use first patch only
            content = ""
            if hasattr(patch, "diff"):
                content = patch.diff
            elif hasattr(patch, "content"):
                content = patch.content
            elif isinstance(patch, str):
                content = patch

            for line in content.split("\n")[:50]:  # Limit to 50 lines
                if line.startswith("-") and not line.startswith("---"):
                    before_lines.append(line[1:])
                elif line.startswith("+") and not line.startswith("+++"):
                    after_lines.append(line[1:])

        if before_lines or after_lines:
            return {
                "before": "\n".join(before_lines[:20]),  # Max 20 lines
                "after": "\n".join(after_lines[:20]),
            }
        return None

    def _estimate_readability_impact(self, category: str, additions: int, deletions: int) -> float:
        """Estimate readability impact of pattern (0.0-1.0)."""
        # Positive impact patterns
        positive_categories = {"extract_method", "simplify", "type_hints", "extract_constant"}

        if category in positive_categories:
            # More deletions = better readability (removing complexity)
            if deletions > additions:
                return min(0.8, 0.5 + (deletions - additions) * 0.02)
            return 0.5

        # Neutral or context-dependent
        return 0.3

    def _estimate_maintainability_impact(self, category: str, files_changed: list[str]) -> float:
        """Estimate maintainability impact of pattern (0.0-1.0)."""
        # Fewer files = better maintainability
        base_impact = 0.5

        if category in {"extract_method", "restructure"}:
            base_impact = 0.7

        # Penalty for many files changed
        if len(files_changed) > 5:
            base_impact -= 0.2
        elif len(files_changed) == 1:
            base_impact += 0.1

        return max(0.0, min(1.0, base_impact))

    def _find_similar(self, pattern_info: dict[str, Any]) -> CodePattern | None:
        """Find existing code pattern similar to new pattern info."""
        category = pattern_info.get("category")
        name_lower = pattern_info.get("name", "").lower()

        for pattern in self.patterns.values():
            # Same category
            if pattern.category != category:
                continue

            # Similar name (simple check)
            if pattern.name.lower() in name_lower or name_lower in pattern.name.lower():
                return pattern

            # Same before/after patterns
            if pattern_info.get("before_pattern") and pattern.before_pattern:
                if pattern_info["before_pattern"] == pattern.before_pattern:
                    return pattern

        return None

    def get_statistics(self) -> dict[str, Any]:
        """Get code pattern statistics."""
        category_counts: dict[str, int] = {}
        for pattern in self.patterns.values():
            category_counts[pattern.category] = category_counts.get(pattern.category, 0) + 1

        return {
            "total_patterns": len(self.patterns),
            "max_patterns": self.max_patterns,
            "by_category": category_counts,
            "top_patterns": sorted(
                self.patterns.values(),
                key=lambda p: p.application_count,
                reverse=True,
            )[:5],
        }
