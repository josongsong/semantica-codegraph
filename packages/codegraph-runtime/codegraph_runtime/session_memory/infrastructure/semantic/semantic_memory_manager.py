"""
Semantic Memory Manager

Manages long-term semantic knowledge:
- Bug patterns and solutions
- Code patterns (refactoring, optimization)
- Project-specific knowledge
- User preferences
"""

import asyncio
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from codegraph_runtime.session_memory.infrastructure.models import (
    BugPattern,
    BugPatternMatch,
    CodePattern,
    CodeRule,
    Episode,
    ErrorObservation,
    InteractionProfile,
    ProjectKnowledge,
    Solution,
    StyleProfile,
    TaskType,
    UserPreferences,
)
from codegraph_runtime.session_memory.infrastructure.pattern_matcher import EmbeddingProvider, PatternMatcher
from codegraph_shared.infra.observability import get_logger, record_counter, record_histogram

logger = get_logger(__name__)


class SemanticMemoryManager:
    """
    Manages semantic memory - generalized knowledge extracted from episodes.

    This is the "learning" component that builds up reusable patterns
    and knowledge over time.
    """

    def __init__(
        self,
        llm: Any | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        """
        Initialize semantic memory manager.

        Args:
            llm: LLM for knowledge extraction (optional)
            embedding_provider: Provider for generating embeddings (optional)
        """
        self.llm = llm
        self.embedding_provider = embedding_provider

        # Memory limits to prevent unbounded growth
        self.max_bug_patterns = 500  # Maximum bug patterns to keep
        self.max_code_patterns = 200  # Maximum code patterns to keep
        self.max_projects = 100  # Maximum project knowledge entries

        # Knowledge stores
        self.bug_patterns: dict[str, BugPattern] = {}
        self.code_patterns: dict[str, CodePattern] = {}
        self.project_knowledge: dict[str, ProjectKnowledge] = {}
        self.user_preferences = UserPreferences()

        # Pattern matcher for semantic matching
        self._pattern_matcher = PatternMatcher(embedding_provider)

        # Locks for thread safety
        self._patterns_lock = asyncio.Lock()
        self._code_patterns_lock = asyncio.Lock()
        self._project_lock = asyncio.Lock()

        logger.info(
            "semantic_memory_initialized",
            max_bug_patterns=self.max_bug_patterns,
            max_code_patterns=self.max_code_patterns,
            max_projects=self.max_projects,
            has_embedding_provider=embedding_provider is not None,
        )
        record_counter("memory_semantic_initialized_total")

    # ============================================================
    # Bug Pattern Management
    # ============================================================

    async def add_bug_pattern(self, pattern: BugPattern) -> str:
        """
        Add or update bug pattern with memory limits and thread safety.

        Args:
            pattern: Bug pattern to add

        Returns:
            Pattern ID
        """
        async with self._patterns_lock:
            # Check memory limit
            if len(self.bug_patterns) >= self.max_bug_patterns:
                # Remove oldest pattern with lowest occurrence count
                sorted_patterns = sorted(
                    self.bug_patterns.items(), key=lambda x: (x[1].occurrence_count, x[1].last_seen)
                )
                removed_id = sorted_patterns[0][0]
                del self.bug_patterns[removed_id]
                logger.debug("bug_pattern_removed_for_space", removed_id=removed_id)
                record_counter("memory_bug_patterns_trimmed_total")

            self.bug_patterns[pattern.id] = pattern
            logger.info("bug_pattern_added", pattern_name=pattern.name, pattern_id=pattern.id)
            record_counter("memory_bug_patterns_total")
            return pattern.id

    async def match_bug_pattern(
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

        Uses PatternMatcher with:
        1. Hard filter (error_type, language, framework)
        2. Semantic similarity (embeddings)
        3. Regex boost (pattern matching)

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
        if not self.bug_patterns:
            return []

        # Create observation from inputs
        observation = ErrorObservation(
            error_type=error_type,
            error_message=error_message or "",
            language=language,
            framework=framework,
            stacktrace=stack_trace,
            code_context=code_context,
        )

        # Use pattern matcher for hybrid matching
        matches = await self._pattern_matcher.match(
            observation=observation,
            patterns=list(self.bug_patterns.values()),
            top_k=top_k,
        )

        logger.info(
            "bug_pattern_matches_found",
            match_count=len(matches),
            top_score=matches[0].score if matches else 0.0,
        )
        record_histogram("memory_bug_pattern_matches", len(matches))
        return matches

    def _get_matched_aspects(self, pattern: BugPattern, error_type: str) -> list[str]:
        """Get which aspects of the pattern matched (legacy, kept for compatibility)."""
        aspects = []
        if error_type in pattern.error_types:
            aspects.append(f"error_type: {error_type}")
        # TODO: Add other matched aspects
        return aspects

    def _select_best_solution(self, pattern: BugPattern) -> Solution | None:
        """Select best solution from pattern's solutions."""
        if not pattern.solutions:
            return None

        # Sort by success rate
        sorted_solutions = sorted(pattern.solutions, key=lambda s: s.success_rate, reverse=True)
        return sorted_solutions[0]

    # ============================================================
    # Code Pattern Management
    # ============================================================

    async def add_code_pattern(self, pattern: CodePattern) -> str:
        """
        Add or update code pattern with memory limits and thread safety.

        Args:
            pattern: Code pattern to add

        Returns:
            Pattern ID
        """
        async with self._code_patterns_lock:
            # Check memory limit
            if len(self.code_patterns) >= self.max_code_patterns:
                # Remove oldest pattern with lowest success rate and application count
                sorted_patterns = sorted(
                    self.code_patterns.items(), key=lambda x: (x[1].success_rate, x[1].application_count)
                )
                removed_id = sorted_patterns[0][0]
                del self.code_patterns[removed_id]
                logger.debug("code_pattern_removed_for_space", removed_id=removed_id)
                record_counter("memory_code_patterns_trimmed_total")

            self.code_patterns[pattern.id] = pattern
            logger.info(
                "code_pattern_added", pattern_name=pattern.name, category=pattern.category, pattern_id=pattern.id
            )
            record_counter("memory_code_patterns_total", labels={"category": pattern.category})
            return pattern.id

    def find_applicable_code_patterns(
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

        for pattern in self.code_patterns.values():
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

    # ============================================================
    # Project Knowledge Management
    # ============================================================

    def get_or_create_project_knowledge(self, project_id: str) -> ProjectKnowledge:
        """
        Get or create project knowledge with memory limits.

        Args:
            project_id: Project identifier

        Returns:
            Project knowledge
        """
        if project_id not in self.project_knowledge:
            # Check memory limit
            if len(self.project_knowledge) >= self.max_projects:
                # Remove least recently updated project
                sorted_projects = sorted(self.project_knowledge.items(), key=lambda x: x[1].last_updated)
                removed_id = sorted_projects[0][0]
                del self.project_knowledge[removed_id]
                logger.debug("project_knowledge_removed_for_space", removed_id=removed_id)
                record_counter("memory_project_knowledge_trimmed_total")

            self.project_knowledge[project_id] = ProjectKnowledge(project_id=project_id)
            logger.info("project_knowledge_created", project_id=project_id)
            record_counter("memory_project_knowledge_total")

        return self.project_knowledge[project_id]

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

    async def update_project_knowledge_from_episode(self, episode: Episode) -> None:
        """
        Update project knowledge from episode with thread safety.

        Args:
            episode: Episode to learn from
        """
        async with self._project_lock:
            knowledge = self.get_or_create_project_knowledge(episode.project_id)

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
                    # Keep only last 50 common issues
                    if len(knowledge.common_issues) > 50:
                        knowledge.common_issues = knowledge.common_issues[-50:]

            knowledge.last_updated = datetime.now()
            logger.debug(
                "project_knowledge_updated",
                project_id=episode.project_id,
                total_sessions=knowledge.total_sessions,
                success_rate=knowledge.success_rate,
            )
            record_counter("memory_project_updates_total", labels={"project_id": episode.project_id})

    # ============================================================
    # User Preferences Management
    # ============================================================

    def update_user_preferences_from_episode(self, episode: Episode) -> None:
        """
        Update user preferences from episode.

        Args:
            episode: Episode to learn from
        """
        # Track accepted/rejected decisions
        for decision in episode.key_decisions:
            pattern = self._extract_decision_pattern(decision)

            if decision.accepted:
                if pattern not in self.user_preferences.frequently_accepted:
                    self.user_preferences.frequently_accepted.append(pattern)
            else:
                if pattern not in self.user_preferences.frequently_rejected:
                    self.user_preferences.frequently_rejected.append(pattern)

        # Infer coding style preferences from patches
        self._infer_coding_style_preferences(episode)

        # Infer interaction preferences from session patterns
        self._infer_interaction_preferences(episode)

        logger.debug(
            "user_preferences_updated",
            accepted_count=len(self.user_preferences.frequently_accepted),
            rejected_count=len(self.user_preferences.frequently_rejected),
        )
        record_counter("memory_user_preference_updates_total")

    def _extract_decision_pattern(self, decision: Any) -> str:
        """Extract pattern from decision for preference learning."""
        # Simplified pattern extraction
        return decision.description[:50] if hasattr(decision, "description") else ""

    def _infer_coding_style_preferences(self, episode: Episode) -> None:
        """
        Infer coding style preferences from patches in episode.

        Extracts patterns like:
        - Naming conventions (camelCase vs snake_case)
        - Quotation style (single vs double)
        - Indentation (tabs vs spaces)
        - Line length preferences
        - Comment style

        Args:
            episode: Episode with patches to analyze
        """
        if not episode.patches:
            return

        # Analyze patches for style patterns
        for patch in episode.patches:
            # Extract style indicators from description and file path
            desc = patch.description.lower()

            # Naming convention inference
            if "snake_case" in desc or "_" in patch.file_path:
                if "naming:snake_case" not in self.user_preferences.frequently_accepted:
                    self.user_preferences.frequently_accepted.append("naming:snake_case")
            elif "camelCase" in desc or any(c.isupper() for c in patch.file_path if c.isalpha()):
                if "naming:camelCase" not in self.user_preferences.frequently_accepted:
                    self.user_preferences.frequently_accepted.append("naming:camelCase")

            # Comment style
            if "docstring" in desc or '"""' in desc:
                if "comment:docstring" not in self.user_preferences.frequently_accepted:
                    self.user_preferences.frequently_accepted.append("comment:docstring")

            # Type hints preference
            if "type hint" in desc or "typing" in desc:
                if "style:type_hints" not in self.user_preferences.frequently_accepted:
                    self.user_preferences.frequently_accepted.append("style:type_hints")

        logger.debug("coding_style_inferred", patch_count=len(episode.patches))

    def _infer_interaction_preferences(self, episode: Episode) -> None:
        """
        Infer interaction preferences from session patterns.

        Extracts patterns like:
        - Preferred tools (search vs grep vs codebase_search)
        - Step-by-step vs batch operations
        - Verbosity preference (detailed vs concise)
        - File organization preferences

        Args:
            episode: Episode with interaction history
        """
        if not episode.tools_used:
            return

        # Analyze tool usage patterns
        tool_names = [tool.tool_name for tool in episode.tools_used]

        # Search preference
        search_tools = [t for t in tool_names if "search" in t.lower()]
        if search_tools:
            most_used_search = max(set(search_tools), key=search_tools.count)
            pref = f"tool:{most_used_search}"
            if pref not in self.user_preferences.frequently_accepted:
                self.user_preferences.frequently_accepted.append(pref)

        # Batch vs incremental preference
        if episode.steps_count > 10:
            avg_tool_calls = len(tool_names) / max(episode.steps_count, 1)
            if avg_tool_calls > 3:
                if "interaction:batch" not in self.user_preferences.frequently_accepted:
                    self.user_preferences.frequently_accepted.append("interaction:batch")
            else:
                if "interaction:incremental" not in self.user_preferences.frequently_accepted:
                    self.user_preferences.frequently_accepted.append("interaction:incremental")

        # File organization preference (from files_involved)
        if len(episode.files_involved) > 5:
            if "organization:multi_file" not in self.user_preferences.frequently_accepted:
                self.user_preferences.frequently_accepted.append("organization:multi_file")

        logger.debug("interaction_preferences_inferred", tools_count=len(episode.tools_used))

    # ============================================================
    # Learning from Episodes
    # ============================================================

    async def learn_from_episode(self, episode: Episode) -> None:
        """
        Extract knowledge from episode and update semantic memory.

        Args:
            episode: Episode to learn from
        """
        logger.info(
            "learning_from_episode",
            episode_id=episode.id,
            task_type=episode.task_type.value,
            has_errors=bool(episode.error_types),
            outcome=episode.outcome_status.value,
        )
        record_counter("memory_episode_learning_total", labels={"task_type": episode.task_type.value})

        # Learn bug patterns
        if episode.error_types and episode.outcome_status.value == "success":
            await self._learn_bug_pattern(episode)

        # Learn code patterns
        if episode.task_type == TaskType.REFACTOR and episode.patches:
            await self._learn_code_pattern(episode)

        # Update project knowledge
        await self.update_project_knowledge_from_episode(episode)

        # Update user preferences
        self.update_user_preferences_from_episode(episode)

        logger.info(
            "learning_complete",
            episode_id=episode.id,
            bug_patterns=len(self.bug_patterns),
            code_patterns=len(self.code_patterns),
            projects=len(self.project_knowledge),
        )
        record_histogram("memory_total_bug_patterns", len(self.bug_patterns))
        record_histogram("memory_total_code_patterns", len(self.code_patterns))

    async def _learn_bug_pattern(self, episode: Episode) -> None:
        """Learn or reinforce bug pattern from episode with safe division."""
        for error_type in episode.error_types:
            # Check if pattern exists
            existing_pattern = self._find_pattern_by_error_type(error_type)

            if existing_pattern:
                async with self._patterns_lock:
                    # Reinforce existing pattern
                    existing_pattern.occurrence_count += 1
                    existing_pattern.resolution_count += 1
                    existing_pattern.last_seen = datetime.now()

                    # Update average resolution time (safe division)
                    n = existing_pattern.resolution_count
                    if n > 0:
                        existing_pattern.avg_resolution_time_ms = (
                            (existing_pattern.avg_resolution_time_ms * (n - 1)) + episode.duration_ms
                        ) / n

                    # Add new solution if different
                    if episode.solution_pattern:
                        self._add_or_update_solution(existing_pattern, episode)

                    logger.debug(
                        "bug_pattern_reinforced",
                        pattern_name=existing_pattern.name,
                        occurrence_count=existing_pattern.occurrence_count,
                        resolution_count=existing_pattern.resolution_count,
                    )
                    record_counter("memory_bug_pattern_reinforcements_total")

            else:
                # Create new pattern
                pattern_id = str(uuid4())
                new_pattern = BugPattern(
                    id=pattern_id,
                    name=f"Pattern for {error_type}",
                    error_types=[error_type],
                    languages=["python"],  # Default language for learned patterns
                    occurrence_count=1,
                    resolution_count=1,
                    avg_resolution_time_ms=episode.duration_ms,
                )

                # Add solution
                if episode.solution_pattern:
                    new_pattern.solutions.append(
                        Solution(
                            description=episode.solution_pattern,
                            approach=episode.plan_summary,
                            success_rate=1.0,
                        )
                    )

                await self.add_bug_pattern(new_pattern)
                logger.info("new_bug_pattern_learned", error_type=error_type, pattern_id=pattern_id)
                record_counter("memory_new_bug_patterns_learned_total", labels={"error_type": error_type})

    def _find_pattern_by_error_type(self, error_type: str) -> BugPattern | None:
        """Find existing pattern by error type."""
        for pattern in self.bug_patterns.values():
            if error_type in pattern.error_types:
                return pattern
        return None

    def _add_or_update_solution(self, pattern: BugPattern, episode: Episode) -> None:
        """Add or update solution in pattern with safe division."""
        solution_desc = episode.solution_pattern

        # Check if similar solution exists
        for solution in pattern.solutions:
            if self._is_similar_solution(solution.description, solution_desc):
                # Update success rate (safe division)
                n = pattern.resolution_count
                if n > 0:
                    solution.success_rate = ((solution.success_rate * (n - 1)) + 1.0) / n
                return

        # Add new solution (limit solutions per pattern)
        if len(pattern.solutions) < 10:  # Max 10 solutions per pattern
            pattern.solutions.append(
                Solution(
                    description=solution_desc,
                    approach=episode.plan_summary,
                    success_rate=1.0,
                )
            )
        else:
            # Replace lowest performing solution
            pattern.solutions.sort(key=lambda s: s.success_rate)
            pattern.solutions[0] = Solution(
                description=solution_desc,
                approach=episode.plan_summary,
                success_rate=1.0,
            )

    def _is_similar_solution(self, desc1: str, desc2: str) -> bool:
        """Check if two solution descriptions are similar."""
        # Simple similarity check (could use embeddings for better results)
        return desc1.lower() == desc2.lower()

    async def _learn_code_pattern(self, episode: Episode) -> None:
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
        pattern_info = self._analyze_patches_for_pattern(episode)

        if not pattern_info:
            logger.debug("no_pattern_extracted", episode_id=episode.id)
            record_counter("memory_code_pattern_learning_attempts_total", labels={"status": "no_pattern"})
            return

        # Check if similar pattern exists
        existing = self._find_similar_code_pattern(pattern_info)

        if existing:
            async with self._code_patterns_lock:
                # Reinforce existing pattern
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
        else:
            # Create new pattern
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

            await self.add_code_pattern(new_pattern)
            logger.info(
                "new_code_pattern_learned",
                pattern_id=new_pattern.id,
                category=new_pattern.category,
            )
            record_counter("memory_new_code_patterns_learned_total", labels={"category": new_pattern.category})

    def _analyze_patches_for_pattern(self, episode: Episode) -> dict[str, Any] | None:
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
        category = self._detect_pattern_category(episode, total_additions, total_deletions)

        if not category:
            return None

        # Build pattern info
        pattern_info: dict[str, Any] = {
            "name": self._generate_pattern_name(episode, category),
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

    def _detect_pattern_category(
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
        if any(kw in desc for kw in ["extract", "refactor out", "pull out"]):
            return "extract_method"
        if any(kw in desc for kw in ["rename", "change name"]):
            return "rename"
        if any(kw in desc for kw in ["simplify", "reduce", "clean up"]):
            return "simplify"
        if any(kw in desc for kw in ["type hint", "typing", "annotation"]):
            return "type_hints"
        if any(kw in desc for kw in ["constant", "magic number"]):
            return "extract_constant"
        if any(kw in desc for kw in ["move", "restructure", "reorganize"]):
            return "restructure"

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

    def _generate_pattern_name(self, episode: Episode, category: str) -> str:
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

    def _find_similar_code_pattern(self, pattern_info: dict[str, Any]) -> CodePattern | None:
        """Find existing code pattern similar to new pattern info."""
        category = pattern_info.get("category")
        name_lower = pattern_info.get("name", "").lower()

        for pattern in self.code_patterns.values():
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

    # ============================================================
    # Knowledge Retrieval
    # ============================================================

    def get_relevant_knowledge(
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
        knowledge: dict[str, Any] = {}

        # Project knowledge
        if project_id in self.project_knowledge:
            knowledge["project"] = self.project_knowledge[project_id]

        # Bug patterns if error
        if error_type:
            knowledge["bug_patterns"] = [p for p in self.bug_patterns.values() if error_type in p.error_types]

        # User preferences
        knowledge["user_preferences"] = self.user_preferences

        return knowledge

    # ============================================================
    # Statistics
    # ============================================================

    def get_statistics(self) -> dict[str, Any]:
        """Get semantic memory statistics."""
        return {
            "bug_patterns": len(self.bug_patterns),
            "code_patterns": len(self.code_patterns),
            "projects": len(self.project_knowledge),
            "top_bug_patterns": sorted(self.bug_patterns.values(), key=lambda p: p.occurrence_count, reverse=True)[:5],
            "user_preferences": {
                "accepted_patterns": len(self.user_preferences.frequently_accepted),
                "rejected_patterns": len(self.user_preferences.frequently_rejected),
            },
        }

    # ============================================================
    # Style Inference (RFC: Coding Style Preferences)
    # ============================================================

    def infer_style_from_code(self, code: str, language: str = "python") -> "StyleProfile":
        """
        Infer coding style from a code snippet.

        Uses AST analysis and regex patterns to detect:
        - Naming conventions (snake_case, camelCase, etc.)
        - Function length and style
        - Import patterns
        - Type hint usage
        - Docstring style

        Args:
            code: Source code to analyze
            language: Programming language

        Returns:
            StyleProfile with inferred style preferences
        """
        from .models import StyleProfile

        profile = StyleProfile()

        if language != "python":
            # Only Python supported for now
            return profile

        # Analyze naming conventions
        naming_stats = self._analyze_naming(code)
        profile.naming_snake_ratio = naming_stats.get("snake", 0.0)
        profile.naming_camel_ratio = naming_stats.get("camel", 0.0)
        profile.naming_pascal_ratio = naming_stats.get("pascal", 0.0)

        # Determine dominant convention
        max_ratio = max(profile.naming_snake_ratio, profile.naming_camel_ratio, profile.naming_pascal_ratio)
        if max_ratio < 0.5:
            profile.naming_convention = "mixed"
        elif profile.naming_snake_ratio == max_ratio:
            profile.naming_convention = "snake_case"
        elif profile.naming_camel_ratio == max_ratio:
            profile.naming_convention = "camelCase"
        else:
            profile.naming_convention = "PascalCase"

        # Analyze function style
        func_stats = self._analyze_functions(code)
        profile.function_length_mean = func_stats.get("avg_length", 15.0)
        profile.function_length_std = func_stats.get("std_length", 10.0)
        profile.early_return_ratio = func_stats.get("early_return_ratio", 0.0)
        profile.max_nesting_depth_mean = func_stats.get("avg_nesting", 2.0)

        # Analyze imports
        import_stats = self._analyze_imports(code)
        profile.import_sorted = import_stats.get("sorted", False)
        profile.import_grouped = import_stats.get("grouped", False)
        profile.import_alias_usage = import_stats.get("alias_ratio", 0.0)

        # Analyze type hints
        type_stats = self._analyze_type_hints(code)
        profile.type_hint_coverage = type_stats.get("coverage", 0.0)
        profile.return_type_coverage = type_stats.get("return_coverage", 0.0)

        # Analyze docstrings
        doc_stats = self._analyze_docstrings(code)
        profile.docstring_coverage = doc_stats.get("coverage", 0.0)
        profile.docstring_style = doc_stats.get("style", "none")

        # General patterns
        profile.prefer_comprehensions = self._detect_comprehension_preference(code)
        profile.prefer_f_strings = self._detect_fstring_preference(code)

        # Update metadata
        profile.samples_analyzed = 1
        profile.confidence = min(0.9, len(code) / 5000)  # More code = higher confidence
        profile.last_updated = datetime.now()

        logger.debug(
            "style_inferred",
            naming=profile.naming_convention,
            func_length=profile.function_length_mean,
            type_coverage=profile.type_hint_coverage,
        )

        return profile

    def _analyze_naming(self, code: str) -> dict[str, float]:
        """Analyze naming conventions in code."""
        import re

        # Find all identifiers (function names, variable names, class names)
        # Exclude keywords and builtins
        identifiers: list[str] = []

        # Function/method names
        func_pattern = r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        identifiers.extend(re.findall(func_pattern, code))

        # Variable assignments
        var_pattern = r"^[ \t]*([a-zA-Z_][a-zA-Z0-9_]*)\s*="
        identifiers.extend(re.findall(var_pattern, code, re.MULTILINE))

        # Class names
        class_pattern = r"class\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        identifiers.extend(re.findall(class_pattern, code))

        if not identifiers:
            return {"snake": 0.0, "camel": 0.0, "pascal": 0.0}

        # Classify each identifier
        snake_count = 0
        camel_count = 0
        pascal_count = 0

        for name in identifiers:
            if name.startswith("_"):
                name = name.lstrip("_")
            if not name:
                continue

            # Skip single character or all caps (constants)
            if len(name) <= 1 or name.isupper():
                continue

            if "_" in name:
                snake_count += 1
            elif name[0].isupper():
                pascal_count += 1
            elif any(c.isupper() for c in name[1:]):
                camel_count += 1
            else:
                snake_count += 1  # Default lowercase to snake

        total = snake_count + camel_count + pascal_count
        if total == 0:
            return {"snake": 0.0, "camel": 0.0, "pascal": 0.0}

        return {
            "snake": snake_count / total,
            "camel": camel_count / total,
            "pascal": pascal_count / total,
        }

    def _analyze_functions(self, code: str) -> dict[str, float]:
        """Analyze function style patterns."""
        import ast
        import statistics

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {}

        func_lengths: list[int] = []
        early_return_count = 0
        nesting_depths: list[int] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                # Function length (lines)
                if hasattr(node, "end_lineno") and node.end_lineno:
                    length = node.end_lineno - node.lineno + 1
                    func_lengths.append(length)

                # Check for early return pattern
                if self._has_early_return(node):
                    early_return_count += 1

                # Calculate max nesting depth
                depth = self._calculate_nesting_depth(node)
                nesting_depths.append(depth)

        if not func_lengths:
            return {}

        return {
            "avg_length": statistics.mean(func_lengths),
            "std_length": statistics.stdev(func_lengths) if len(func_lengths) > 1 else 0.0,
            "early_return_ratio": early_return_count / len(func_lengths),
            "avg_nesting": statistics.mean(nesting_depths) if nesting_depths else 2.0,
        }

    def _has_early_return(self, func_node: Any) -> bool:
        """Check if function uses early return pattern."""
        import ast

        for node in ast.walk(func_node):
            if isinstance(node, ast.If):
                # Check if first statement in if body is return
                if node.body and isinstance(node.body[0], ast.Return):
                    return True
        return False

    def _calculate_nesting_depth(self, node: Any, current_depth: int = 0) -> int:
        """Calculate maximum nesting depth in a node."""
        import ast

        max_depth = current_depth

        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.If | ast.For | ast.While | ast.With | ast.Try):
                child_depth = self._calculate_nesting_depth(child, current_depth + 1)
                max_depth = max(max_depth, child_depth)
            else:
                child_depth = self._calculate_nesting_depth(child, current_depth)
                max_depth = max(max_depth, child_depth)

        return max_depth

    def _analyze_imports(self, code: str) -> dict[str, Any]:
        """Analyze import style patterns."""
        import ast

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {}

        imports: list[tuple[int, str, bool]] = []  # (lineno, module, has_alias)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((node.lineno, alias.name, alias.asname is not None))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append((node.lineno, module, alias.asname is not None))

        if not imports:
            return {"sorted": False, "grouped": False, "alias_ratio": 0.0}

        # Check if imports are sorted (by line order matching alphabetical)
        import_names = [imp[1] for imp in sorted(imports, key=lambda x: x[0])]
        is_sorted = import_names == sorted(import_names)

        # Check if imports are grouped (stdlib, third-party, local)
        # Simplified: check if there are blank lines between import sections
        lines = code.split("\n")
        import_lines = [imp[0] for imp in imports]
        has_gaps = False
        for i in range(len(import_lines) - 1):
            if import_lines[i + 1] - import_lines[i] > 1:
                # Check if gap contains blank line
                for j in range(import_lines[i], import_lines[i + 1]):
                    if j <= len(lines) and not lines[j - 1].strip():
                        has_gaps = True
                        break

        # Alias ratio
        alias_count = sum(1 for imp in imports if imp[2])
        alias_ratio = alias_count / len(imports)

        return {
            "sorted": is_sorted,
            "grouped": has_gaps,
            "alias_ratio": alias_ratio,
        }

    def _analyze_type_hints(self, code: str) -> dict[str, float]:
        """Analyze type hint usage."""
        import ast

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {}

        total_funcs = 0
        funcs_with_hints = 0
        funcs_with_return = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                total_funcs += 1

                # Check for any parameter type hints
                has_param_hints = any(arg.annotation for arg in node.args.args)
                if has_param_hints:
                    funcs_with_hints += 1

                # Check for return type hint
                if node.returns:
                    funcs_with_return += 1

        if total_funcs == 0:
            return {"coverage": 0.0, "return_coverage": 0.0}

        return {
            "coverage": funcs_with_hints / total_funcs,
            "return_coverage": funcs_with_return / total_funcs,
        }

    def _analyze_docstrings(self, code: str) -> dict[str, Any]:
        """Analyze docstring patterns."""
        import ast

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {}

        total_funcs = 0
        funcs_with_docs = 0
        docstring_samples: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                total_funcs += 1
                docstring = ast.get_docstring(node)
                if docstring:
                    funcs_with_docs += 1
                    docstring_samples.append(docstring)

        if total_funcs == 0:
            return {"coverage": 0.0, "style": "none"}

        # Detect docstring style from samples
        style = "none"
        if docstring_samples:
            sample = docstring_samples[0]
            if "Args:" in sample or "Returns:" in sample:
                style = "google"
            elif "Parameters" in sample and "----------" in sample:
                style = "numpy"
            elif ":param" in sample or ":returns:" in sample:
                style = "sphinx"

        return {
            "coverage": funcs_with_docs / total_funcs,
            "style": style,
        }

    def _detect_comprehension_preference(self, code: str) -> bool:
        """Detect if code prefers comprehensions over loops."""
        import re

        # Count comprehensions
        list_comp = len(re.findall(r"\[.+\s+for\s+.+\s+in\s+.+\]", code))
        dict_comp = len(re.findall(r"\{.+:\s*.+\s+for\s+.+\s+in\s+.+\}", code))
        set_comp = len(re.findall(r"\{.+\s+for\s+.+\s+in\s+.+\}", code))
        gen_exp = len(re.findall(r"\(.+\s+for\s+.+\s+in\s+.+\)", code))

        total_comp = list_comp + dict_comp + set_comp + gen_exp

        # Count for loops
        for_loops = len(re.findall(r"^\s*for\s+.+\s+in\s+.+:", code, re.MULTILINE))

        # Prefer comprehensions if ratio > 0.3
        if for_loops + total_comp == 0:
            return False
        return total_comp / (for_loops + total_comp) > 0.3

    def _detect_fstring_preference(self, code: str) -> bool:
        """Detect if code prefers f-strings over .format()."""
        import re

        # Count f-strings
        fstrings = len(re.findall(r'f["\']', code))

        # Count .format() calls
        format_calls = len(re.findall(r"\.format\s*\(", code))

        # Count % formatting
        percent_format = len(re.findall(r"%\s*[(\[]", code))

        total = fstrings + format_calls + percent_format
        if total == 0:
            return False

        return fstrings / total > 0.5

    def merge_style_profiles(self, profiles: list["StyleProfile"]) -> "StyleProfile":
        """
        Merge multiple style profiles into one.

        Uses weighted averaging based on samples_analyzed.

        Args:
            profiles: List of StyleProfile to merge

        Returns:
            Merged StyleProfile
        """
        from .models import StyleProfile

        if not profiles:
            return StyleProfile()

        if len(profiles) == 1:
            return profiles[0]

        merged = StyleProfile()
        total_samples = sum(p.samples_analyzed for p in profiles)

        if total_samples == 0:
            return merged

        # Weighted average for numeric fields
        for field in [
            "naming_snake_ratio",
            "naming_camel_ratio",
            "naming_pascal_ratio",
            "function_length_mean",
            "function_length_std",
            "early_return_ratio",
            "max_nesting_depth_mean",
            "import_alias_usage",
            "type_hint_coverage",
            "return_type_coverage",
            "docstring_coverage",
        ]:
            weighted_sum = sum(getattr(p, field) * p.samples_analyzed for p in profiles)
            setattr(merged, field, weighted_sum / total_samples)

        # Majority vote for categorical fields
        from collections import Counter

        naming_votes = Counter(p.naming_convention for p in profiles)
        merged.naming_convention = naming_votes.most_common(1)[0][0]

        docstyle_votes = Counter(p.docstring_style for p in profiles)
        merged.docstring_style = docstyle_votes.most_common(1)[0][0]

        # OR for boolean fields (prefer True if any profile has it)
        merged.import_sorted = any(p.import_sorted for p in profiles)
        merged.import_grouped = any(p.import_grouped for p in profiles)
        merged.prefer_comprehensions = sum(p.prefer_comprehensions for p in profiles) > len(profiles) / 2
        merged.prefer_f_strings = sum(p.prefer_f_strings for p in profiles) > len(profiles) / 2

        merged.samples_analyzed = total_samples
        merged.confidence = sum(p.confidence * p.samples_analyzed for p in profiles) / total_samples
        merged.last_updated = datetime.now()

        return merged

    # ============================================================
    # Interaction Pattern Learning (RFC: User Interaction Preferences)
    # ============================================================

    def infer_interaction_from_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> InteractionProfile:
        """
        Infer user interaction preferences from conversation history.

        Analyzes patterns in:
        - Response length preferences
        - Detail level preferences
        - Format preferences (markdown, tables, code blocks)
        - Tone and style

        Args:
            messages: List of message dicts with 'role', 'content', and optionally 'tokens'

        Returns:
            InteractionProfile with inferred preferences
        """
        profile = InteractionProfile()

        if not messages:
            return profile

        # Separate user and assistant messages
        user_messages = [m for m in messages if m.get("role") == "user"]
        assistant_messages = [m for m in messages if m.get("role") == "assistant"]

        # Analyze response length preferences
        length_stats = self._analyze_response_lengths(assistant_messages)
        profile.avg_response_tokens = length_stats.get("avg_tokens", 500.0)
        profile.response_length_std = length_stats.get("std_tokens", 200.0)
        profile.preferred_response_length = length_stats.get("preference", "moderate")

        # Analyze detail preferences from user queries
        detail_stats = self._analyze_detail_preferences(user_messages)
        profile.detail_preference = detail_stats.get("preference", "balanced")
        profile.code_to_explanation_ratio = detail_stats.get("code_ratio", 0.5)

        # Analyze format preferences from assistant responses
        format_stats = self._analyze_format_preferences(assistant_messages)
        profile.preferred_format = format_stats.get("format", "markdown")
        profile.use_tables = format_stats.get("uses_tables", False)
        profile.use_code_blocks = format_stats.get("uses_code_blocks", True)

        # Analyze tone
        tone_stats = self._analyze_tone(user_messages, assistant_messages)
        profile.tone = tone_stats.get("tone", "technical")
        profile.use_emojis = tone_stats.get("uses_emojis", False)

        # Analyze interaction patterns
        interaction_stats = self._analyze_interaction_patterns(user_messages)
        profile.asks_clarifying_questions = interaction_stats.get("clarification_rate", 0.3)
        profile.requests_examples = interaction_stats.get("example_rate", 0.5)
        profile.iterates_on_solutions = interaction_stats.get("iteration_rate", 0.4)

        # Update metadata
        profile.interactions_analyzed = len(messages)
        profile.confidence = min(0.9, len(messages) / 50)  # More messages = higher confidence
        profile.last_updated = datetime.now()

        logger.debug(
            "interaction_inferred",
            response_length=profile.preferred_response_length,
            detail=profile.detail_preference,
            format=profile.preferred_format,
            tone=profile.tone,
        )

        return profile

    def _analyze_response_lengths(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze response length patterns."""
        import statistics

        if not messages:
            return {"avg_tokens": 500.0, "std_tokens": 200.0, "preference": "moderate"}

        # Calculate lengths (tokens if available, else estimate from content)
        lengths: list[int] = []
        for msg in messages:
            if "tokens" in msg:
                lengths.append(msg["tokens"])
            elif "content" in msg:
                # Rough estimate: ~4 chars per token
                lengths.append(len(msg["content"]) // 4)

        if not lengths:
            return {"avg_tokens": 500.0, "std_tokens": 200.0, "preference": "moderate"}

        avg = statistics.mean(lengths)
        std = statistics.stdev(lengths) if len(lengths) > 1 else 200.0

        # Categorize preference
        if avg < 200:
            pref = "brief"
        elif avg > 800:
            pref = "detailed"
        else:
            pref = "moderate"

        return {"avg_tokens": avg, "std_tokens": std, "preference": pref}

    def _analyze_detail_preferences(self, user_messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze user's detail level preferences."""
        if not user_messages:
            return {"preference": "balanced", "code_ratio": 0.5}

        summary_keywords = ["요약", "간단히", "짧게", "summary", "brief", "short", "tl;dr"]
        detail_keywords = ["자세히", "상세", "설명", "explain", "detail", "elaborate", "more"]
        code_keywords = ["코드", "code", "implement", "구현", "작성"]
        explain_keywords = ["왜", "why", "어떻게", "how", "설명"]

        summary_count = 0
        detail_count = 0
        code_count = 0
        explain_count = 0

        for msg in user_messages:
            content = msg.get("content", "").lower()

            if any(kw in content for kw in summary_keywords):
                summary_count += 1
            if any(kw in content for kw in detail_keywords):
                detail_count += 1
            if any(kw in content for kw in code_keywords):
                code_count += 1
            if any(kw in content for kw in explain_keywords):
                explain_count += 1

        # Determine preference
        if summary_count > detail_count:
            pref = "summary"
        elif detail_count > summary_count:
            pref = "thorough"
        else:
            pref = "balanced"

        # Code vs explanation ratio
        if code_count + explain_count == 0:
            code_ratio = 0.5
        else:
            code_ratio = code_count / (code_count + explain_count)

        return {"preference": pref, "code_ratio": code_ratio}

    def _analyze_format_preferences(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze format preferences from responses."""
        import re

        if not messages:
            return {"format": "markdown", "uses_tables": False, "uses_code_blocks": True}

        markdown_count = 0
        table_count = 0
        code_block_count = 0
        bullet_count = 0
        prose_count = 0

        for msg in messages:
            content = msg.get("content", "")

            # Check for markdown elements
            if re.search(r"^#+\s", content, re.MULTILINE):
                markdown_count += 1
            if "|" in content and re.search(r"\|.*\|.*\|", content):
                table_count += 1
            if "```" in content:
                code_block_count += 1
            if re.search(r"^[-*]\s", content, re.MULTILINE):
                bullet_count += 1
            if len(content) > 100 and not any(
                [
                    re.search(r"^#+\s", content, re.MULTILINE),
                    "```" in content,
                    re.search(r"^[-*]\s", content, re.MULTILINE),
                ]
            ):
                prose_count += 1

        total = len(messages)

        # Determine primary format
        if code_block_count > total * 0.5:
            fmt = "code_heavy"
        elif bullet_count > total * 0.4:
            fmt = "bullet_points"
        elif prose_count > total * 0.6:
            fmt = "prose"
        else:
            fmt = "markdown"

        return {
            "format": fmt,
            "uses_tables": table_count > 0,
            "uses_code_blocks": code_block_count > total * 0.3,
        }

    def _analyze_tone(
        self, user_messages: list[dict[str, Any]], assistant_messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze tone preferences."""
        import re

        all_messages = user_messages + assistant_messages

        if not all_messages:
            return {"tone": "technical", "uses_emojis": False}

        formal_indicators = 0
        casual_indicators = 0
        technical_indicators = 0
        emoji_count = 0

        emoji_pattern = re.compile(
            r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
            r"\U0001F1E0-\U0001F1FF\U00002702-\U000027B0]"
        )

        for msg in all_messages:
            content = msg.get("content", "")

            # Check for emojis
            if emoji_pattern.search(content):
                emoji_count += 1

            content_lower = content.lower()

            # Formal indicators
            if any(w in content_lower for w in ["please", "thank you", "kindly", "부탁", "감사"]):
                formal_indicators += 1

            # Casual indicators
            if any(w in content_lower for w in ["hey", "cool", "awesome", "ㅋㅋ", "ㅎㅎ", "lol"]):
                casual_indicators += 1

            # Technical indicators
            if any(w in content_lower for w in ["function", "class", "api", "함수", "클래스", "메서드"]):
                technical_indicators += 1

        total = len(all_messages)

        # Determine tone
        if technical_indicators > total * 0.3:
            tone = "technical"
        elif casual_indicators > formal_indicators:
            tone = "casual"
        else:
            tone = "formal"

        return {"tone": tone, "uses_emojis": emoji_count > total * 0.1}

    def _analyze_interaction_patterns(self, user_messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze user interaction patterns."""
        if not user_messages:
            return {"clarification_rate": 0.3, "example_rate": 0.5, "iteration_rate": 0.4}

        clarification_keywords = ["무슨 뜻", "뭐야", "what do you mean", "clarify", "?"]
        example_keywords = ["예시", "예를 들", "example", "show me", "샘플"]
        iteration_keywords = ["다시", "수정", "바꿔", "change", "modify", "update", "fix"]

        clarification_count = 0
        example_count = 0
        iteration_count = 0

        for msg in user_messages:
            content = msg.get("content", "").lower()

            if any(kw in content for kw in clarification_keywords):
                clarification_count += 1
            if any(kw in content for kw in example_keywords):
                example_count += 1
            if any(kw in content for kw in iteration_keywords):
                iteration_count += 1

        total = len(user_messages)

        return {
            "clarification_rate": clarification_count / total if total > 0 else 0.3,
            "example_rate": example_count / total if total > 0 else 0.5,
            "iteration_rate": iteration_count / total if total > 0 else 0.4,
        }

    def merge_interaction_profiles(self, profiles: list[InteractionProfile]) -> InteractionProfile:
        """
        Merge multiple interaction profiles into one.

        Args:
            profiles: List of InteractionProfile to merge

        Returns:
            Merged InteractionProfile
        """
        if not profiles:
            return InteractionProfile()

        if len(profiles) == 1:
            return profiles[0]

        merged = InteractionProfile()
        total_interactions = sum(p.interactions_analyzed for p in profiles)

        if total_interactions == 0:
            return merged

        # Weighted average for numeric fields
        for field in [
            "avg_response_tokens",
            "response_length_std",
            "code_to_explanation_ratio",
            "asks_clarifying_questions",
            "requests_examples",
            "iterates_on_solutions",
        ]:
            weighted_sum = sum(getattr(p, field) * p.interactions_analyzed for p in profiles)
            setattr(merged, field, weighted_sum / total_interactions)

        # Majority vote for categorical fields
        from collections import Counter

        length_votes = Counter(p.preferred_response_length for p in profiles)
        merged.preferred_response_length = length_votes.most_common(1)[0][0]

        detail_votes = Counter(p.detail_preference for p in profiles)
        merged.detail_preference = detail_votes.most_common(1)[0][0]

        format_votes = Counter(p.preferred_format for p in profiles)
        merged.preferred_format = format_votes.most_common(1)[0][0]

        tone_votes = Counter(p.tone for p in profiles)
        merged.tone = tone_votes.most_common(1)[0][0]

        confirm_votes = Counter(p.needs_confirmation for p in profiles)
        merged.needs_confirmation = confirm_votes.most_common(1)[0][0]

        # Boolean fields - majority vote
        merged.use_tables = sum(p.use_tables for p in profiles) > len(profiles) / 2
        merged.use_code_blocks = sum(p.use_code_blocks for p in profiles) > len(profiles) / 2
        merged.use_emojis = sum(p.use_emojis for p in profiles) > len(profiles) / 2

        merged.interactions_analyzed = total_interactions
        merged.confidence = sum(p.confidence * p.interactions_analyzed for p in profiles) / total_interactions
        merged.last_updated = datetime.now()

        return merged

    # ============================================================
    # Phase 4: Code Pattern Detection from Patches (RFC §3)
    # ============================================================

    def detect_code_rules_from_patch(
        self,
        before_code: str,
        after_code: str,
        language: str = "python",
        commit_message: str = "",
    ) -> list[CodeRule]:
        """
        Detect transformation rules from before/after code.

        Analyzes patches to learn common transformation patterns that can
        be applied to similar code in the future.

        Args:
            before_code: Code before the change
            after_code: Code after the change
            language: Programming language
            commit_message: Optional commit message for context

        Returns:
            List of detected CodeRule instances
        """
        rules: list[CodeRule] = []

        # 1. Null Safety Patterns
        null_rules = self._detect_null_safety_patterns(before_code, after_code)
        rules.extend(null_rules)

        # 2. Error Handling Patterns
        error_rules = self._detect_error_handling_patterns(before_code, after_code)
        rules.extend(error_rules)

        # 3. Style/Readability Patterns
        style_rules = self._detect_style_patterns(before_code, after_code)
        rules.extend(style_rules)

        # 4. Performance Patterns
        perf_rules = self._detect_performance_patterns(before_code, after_code)
        rules.extend(perf_rules)

        # 5. Security Patterns
        security_rules = self._detect_security_patterns(before_code, after_code)
        rules.extend(security_rules)

        # Set language for all rules
        for rule in rules:
            rule.languages = [language]

        logger.debug(
            "code_rules_detected",
            rule_count=len(rules),
            categories=[r.category for r in rules],
        )

        return rules

    def _detect_null_safety_patterns(self, before: str, after: str) -> list[CodeRule]:
        """Detect null/None safety transformation patterns."""
        from .models import CodeRule

        rules: list[CodeRule] = []

        # Pattern 1: Direct access -> Optional check
        # Before: x.attr / After: x.attr if x else None
        if "if " in after and " else " in after and " if " not in before:
            # Check for ternary optional access pattern
            if re.search(r"\w+\.\w+\s+if\s+\w+\s+else\s+(None|default)", after):
                rules.append(
                    CodeRule(
                        id=str(uuid4()),
                        name="add_optional_check",
                        description="Add optional/None check before attribute access",
                        category="null_safety",
                        before_pattern=r"(\w+)\.(\w+)",
                        after_pattern=r"\1.\2 if \1 else None",
                        pattern_type="regex",
                        confidence=0.6,
                    )
                )

        # Pattern 2: .get() usage
        if ".get(" in after and ".get(" not in before:
            if re.search(r"\[\s*[\'\"]\w+[\'\"]\s*\]", before):
                rules.append(
                    CodeRule(
                        id=str(uuid4()),
                        name="use_dict_get",
                        description="Use .get() for safe dictionary access",
                        category="null_safety",
                        before_pattern=r"(\w+)\[['\"](\w+)['\"]\]",
                        after_pattern=r"\1.get('\2')",
                        pattern_type="regex",
                        confidence=0.7,
                    )
                )

        # Pattern 3: or default value
        if " or " in after and " or " not in before:
            if re.search(r"\w+\s+or\s+[\'\"\[\{]", after):
                rules.append(
                    CodeRule(
                        id=str(uuid4()),
                        name="add_default_value",
                        description="Add default value with 'or' operator",
                        category="null_safety",
                        before_pattern=r"(\w+)",
                        after_pattern=r"\1 or default",
                        pattern_type="literal",
                        confidence=0.5,
                    )
                )

        return rules

    def _detect_error_handling_patterns(self, before: str, after: str) -> list[CodeRule]:
        """Detect error handling transformation patterns."""
        from .models import CodeRule

        rules: list[CodeRule] = []

        # Pattern 1: Add try-except
        if "try:" in after and "try:" not in before:
            rules.append(
                CodeRule(
                    id=str(uuid4()),
                    name="wrap_with_try_except",
                    description="Wrap code with try-except block",
                    category="error_handling",
                    pattern_type="literal",
                    confidence=0.6,
                )
            )

        # Pattern 2: Specific exception -> Generic exception
        before_exceptions = set(re.findall(r"except\s+(\w+)", before))
        after_exceptions = set(re.findall(r"except\s+(\w+)", after))
        new_exceptions = after_exceptions - before_exceptions

        if new_exceptions:
            for exc in new_exceptions:
                rules.append(
                    CodeRule(
                        id=str(uuid4()),
                        name=f"catch_{exc.lower()}",
                        description=f"Add {exc} exception handling",
                        category="error_handling",
                        before_pattern="",
                        after_pattern=f"except {exc}:",
                        pattern_type="literal",
                        confidence=0.5,
                    )
                )

        # Pattern 3: Add finally block
        if "finally:" in after and "finally:" not in before:
            rules.append(
                CodeRule(
                    id=str(uuid4()),
                    name="add_finally_block",
                    description="Add finally block for cleanup",
                    category="error_handling",
                    pattern_type="literal",
                    confidence=0.6,
                )
            )

        return rules

    def _detect_style_patterns(self, before: str, after: str) -> list[CodeRule]:
        """Detect style/readability transformation patterns."""
        from .models import CodeRule

        rules: list[CodeRule] = []

        # Pattern 1: f-string conversion
        if 'f"' in after or "f'" in after:
            if ".format(" in before or "% " in before:
                rules.append(
                    CodeRule(
                        id=str(uuid4()),
                        name="convert_to_fstring",
                        description="Convert .format() or % to f-string",
                        category="readability",
                        before_pattern=r'"[^"]*"\s*\.format\([^)]+\)',
                        after_pattern='f"..."',
                        pattern_type="regex",
                        confidence=0.8,
                    )
                )

        # Pattern 2: List comprehension
        comp_pattern = re.search(r"\[.+\s+for\s+.+\s+in\s+.+\]", after)
        loop_pattern = re.search(r"for\s+\w+\s+in\s+.+:\s*\n\s+\w+\.append", before)
        if comp_pattern and loop_pattern:
            rules.append(
                CodeRule(
                    id=str(uuid4()),
                    name="use_list_comprehension",
                    description="Convert for-loop append to list comprehension",
                    category="readability",
                    pattern_type="ast",
                    confidence=0.7,
                )
            )

        # Pattern 3: Early return
        # Check if nested if-else was flattened
        before_indent = max(len(line) - len(line.lstrip()) for line in before.split("\n") if line.strip())
        after_indent = max(len(line) - len(line.lstrip()) for line in after.split("\n") if line.strip())

        if before_indent > after_indent and "return" in after:
            if after.count("return") > before.count("return"):
                rules.append(
                    CodeRule(
                        id=str(uuid4()),
                        name="use_early_return",
                        description="Flatten nested conditionals with early return",
                        category="readability",
                        pattern_type="ast",
                        confidence=0.6,
                    )
                )

        # Pattern 4: Walrus operator
        if ":=" in after and ":=" not in before:
            rules.append(
                CodeRule(
                    id=str(uuid4()),
                    name="use_walrus_operator",
                    description="Use walrus operator for assignment in expression",
                    category="style",
                    pattern_type="literal",
                    confidence=0.5,
                )
            )

        # Pattern 5: Type hints added
        if re.search(r"def\s+\w+\([^)]*:\s*\w+", after):
            if not re.search(r"def\s+\w+\([^)]*:\s*\w+", before):
                rules.append(
                    CodeRule(
                        id=str(uuid4()),
                        name="add_type_hints",
                        description="Add type hints to function parameters",
                        category="style",
                        pattern_type="ast",
                        confidence=0.6,
                    )
                )

        return rules

    def _detect_performance_patterns(self, before: str, after: str) -> list[CodeRule]:
        """Detect performance optimization patterns."""
        from .models import CodeRule

        rules: list[CodeRule] = []

        # Pattern 1: Generator instead of list
        if "(" in after and "for" in after and ")" in after:
            if "[" in before and "for" in before and "]" in before:
                # Check if list comp was converted to generator
                if re.search(r"\(\s*\w+\s+for\s+\w+\s+in", after):
                    if re.search(r"\[\s*\w+\s+for\s+\w+\s+in", before):
                        rules.append(
                            CodeRule(
                                id=str(uuid4()),
                                name="use_generator_expression",
                                description="Use generator expression instead of list",
                                category="performance",
                                pattern_type="ast",
                                confidence=0.7,
                            )
                        )

        # Pattern 2: set() for membership
        if "set(" in after and "set(" not in before:
            if " in " in after:
                rules.append(
                    CodeRule(
                        id=str(uuid4()),
                        name="use_set_for_membership",
                        description="Use set for O(1) membership testing",
                        category="performance",
                        pattern_type="literal",
                        confidence=0.7,
                    )
                )

        # Pattern 3: str.join instead of concatenation
        if ".join(" in after and ".join(" not in before:
            if " + " in before or "+=" in before:
                rules.append(
                    CodeRule(
                        id=str(uuid4()),
                        name="use_str_join",
                        description="Use str.join() instead of string concatenation",
                        category="performance",
                        before_pattern=r"(\w+)\s*\+=\s*(\w+)",
                        after_pattern='"".join([...])',
                        pattern_type="regex",
                        confidence=0.6,
                    )
                )

        # Pattern 4: lru_cache / cache decorator
        if "@lru_cache" in after or "@cache" in after:
            if "@lru_cache" not in before and "@cache" not in before:
                rules.append(
                    CodeRule(
                        id=str(uuid4()),
                        name="add_memoization",
                        description="Add memoization with lru_cache",
                        category="performance",
                        pattern_type="literal",
                        confidence=0.6,
                    )
                )

        return rules

    def _detect_security_patterns(self, before: str, after: str) -> list[CodeRule]:
        """Detect security improvement patterns."""
        from .models import CodeRule

        rules: list[CodeRule] = []

        # Pattern 1: Parameterized queries
        if "?" in after or "%s" in after:
            if "f'" in before or 'f"' in before:
                # SQL injection prevention
                rules.append(
                    CodeRule(
                        id=str(uuid4()),
                        name="use_parameterized_query",
                        description="Use parameterized queries to prevent SQL injection",
                        category="security",
                        pattern_type="literal",
                        confidence=0.9,
                    )
                )

        # Pattern 2: secrets module usage
        if "secrets." in after and "secrets." not in before:
            if "random." in before:
                rules.append(
                    CodeRule(
                        id=str(uuid4()),
                        name="use_secrets_module",
                        description="Use secrets module for cryptographic randomness",
                        category="security",
                        pattern_type="literal",
                        confidence=0.8,
                    )
                )

        # Pattern 3: Input validation
        validation_keywords = ["validate", "sanitize", "escape", "clean"]
        if any(kw in after.lower() for kw in validation_keywords):
            if not any(kw in before.lower() for kw in validation_keywords):
                rules.append(
                    CodeRule(
                        id=str(uuid4()),
                        name="add_input_validation",
                        description="Add input validation/sanitization",
                        category="security",
                        pattern_type="literal",
                        confidence=0.6,
                    )
                )

        return rules

    # ============================================================
    # Phase 5: Confidence-based Rule Management (RFC §3.3)
    # ============================================================

    def reinforce_rule(
        self,
        rule: CodeRule,
        success: bool,
        ema_alpha: float = 0.2,
    ) -> CodeRule:
        """
        Reinforce or weaken a rule based on outcome.

        Uses EMA for confidence updates:
        - Success: confidence = α * 1.0 + (1-α) * confidence
        - Failure: confidence = α * 0.0 + (1-α) * confidence

        Args:
            rule: CodeRule to update
            success: Whether the rule application was successful
            ema_alpha: EMA smoothing factor (0.2 = slow adaptation)

        Returns:
            Updated CodeRule
        """
        rule.observation_count += 1

        if success:
            rule.success_count += 1
            new_confidence = ema_alpha * 1.0 + (1 - ema_alpha) * rule.confidence
        else:
            rule.failure_count += 1
            new_confidence = ema_alpha * 0.0 + (1 - ema_alpha) * rule.confidence

        old_confidence = rule.confidence
        rule.confidence = new_confidence

        logger.debug(
            "rule_reinforced",
            rule_id=rule.id,
            rule_name=rule.name,
            success=success,
            old_confidence=f"{old_confidence:.3f}",
            new_confidence=f"{new_confidence:.3f}",
        )

        return rule

    def should_apply_rule(self, rule: CodeRule) -> bool:
        """
        Determine if a rule should be applied based on confidence.

        Rules below min_confidence_threshold are not applied.
        Rules above promotion_threshold are always applied.

        Args:
            rule: CodeRule to check

        Returns:
            True if rule should be applied
        """
        return rule.confidence >= rule.min_confidence_threshold

    def is_trusted_rule(self, rule: CodeRule) -> bool:
        """
        Check if a rule has graduated to trusted status.

        A rule is trusted when:
        - confidence >= promotion_threshold (default 0.8)
        - observation_count >= 5

        Args:
            rule: CodeRule to check

        Returns:
            True if rule is trusted
        """
        return rule.confidence >= rule.promotion_threshold and rule.observation_count >= 5

    def cleanup_weak_rules(
        self,
        rules: dict[str, CodeRule],
        min_observations: int = 3,
    ) -> dict[str, CodeRule]:
        """
        Remove rules that have fallen below confidence threshold.

        Only removes rules with enough observations to be confident
        about their low performance.

        Args:
            rules: Dictionary of rule_id -> CodeRule
            min_observations: Minimum observations before removal

        Returns:
            Cleaned dictionary without weak rules
        """
        cleaned: dict[str, CodeRule] = {}
        removed_count = 0

        for rule_id, rule in rules.items():
            if rule.observation_count >= min_observations:
                if rule.confidence < rule.min_confidence_threshold:
                    logger.info(
                        "weak_rule_removed",
                        rule_id=rule_id,
                        rule_name=rule.name,
                        confidence=f"{rule.confidence:.3f}",
                        observations=rule.observation_count,
                    )
                    removed_count += 1
                    continue

            cleaned[rule_id] = rule

        if removed_count > 0:
            logger.info("weak_rules_cleanup_complete", removed=removed_count)

        return cleaned

    def merge_duplicate_rules(
        self,
        rules: dict[str, CodeRule],
        similarity_threshold: float = 0.9,
    ) -> dict[str, CodeRule]:
        """
        Merge duplicate or very similar rules.

        Rules with similar before/after patterns are merged,
        combining their confidence scores.

        Args:
            rules: Dictionary of rule_id -> CodeRule
            similarity_threshold: Pattern similarity threshold for merging

        Returns:
            Dictionary with merged rules
        """
        if len(rules) <= 1:
            return rules

        rules_list = list(rules.values())
        merged_indices: set[int] = set()
        result: dict[str, CodeRule] = {}

        for i, rule1 in enumerate(rules_list):
            if i in merged_indices:
                continue

            merged_rule = rule1
            for j, rule2 in enumerate(rules_list[i + 1 :], start=i + 1):
                if j in merged_indices:
                    continue

                # Check if rules are similar
                if self._are_rules_similar(rule1, rule2, similarity_threshold):
                    merged_rule = self._merge_rules(merged_rule, rule2)
                    merged_indices.add(j)
                    logger.debug(
                        "rules_merged",
                        rule1_id=rule1.id,
                        rule2_id=rule2.id,
                        merged_name=merged_rule.name,
                    )

            result[merged_rule.id] = merged_rule

        return result

    def _are_rules_similar(
        self,
        rule1: CodeRule,
        rule2: CodeRule,
        threshold: float,
    ) -> bool:
        """Check if two rules are similar enough to merge."""
        # Must be same category
        if rule1.category != rule2.category:
            return False

        # Check pattern similarity
        pattern1 = (rule1.before_pattern or "") + (rule1.after_pattern or "")
        pattern2 = (rule2.before_pattern or "") + (rule2.after_pattern or "")

        if not pattern1 or not pattern2:
            # If no patterns, compare names
            return rule1.name == rule2.name

        # Simple character-level similarity
        common = set(pattern1) & set(pattern2)
        total = set(pattern1) | set(pattern2)

        if not total:
            return False

        similarity = len(common) / len(total)
        return similarity >= threshold

    def _merge_rules(self, rule1: CodeRule, rule2: CodeRule) -> CodeRule:
        """Merge two similar rules into one."""
        from .models import CodeRule

        # Weighted average of confidence
        total_obs = rule1.observation_count + rule2.observation_count
        if total_obs == 0:
            merged_confidence = (rule1.confidence + rule2.confidence) / 2
        else:
            merged_confidence = (
                rule1.confidence * rule1.observation_count + rule2.confidence * rule2.observation_count
            ) / total_obs

        return CodeRule(
            id=rule1.id,  # Keep first rule's ID
            name=rule1.name,
            description=rule1.description or rule2.description,
            category=rule1.category,
            before_pattern=rule1.before_pattern or rule2.before_pattern,
            after_pattern=rule1.after_pattern or rule2.after_pattern,
            pattern_type=rule1.pattern_type,
            languages=list(set(rule1.languages + rule2.languages)),
            confidence=merged_confidence,
            observation_count=total_obs,
            success_count=rule1.success_count + rule2.success_count,
            failure_count=rule1.failure_count + rule2.failure_count,
        )

    def get_applicable_rules(
        self,
        code: str,
        language: str = "python",
        min_confidence: float | None = None,
    ) -> list[CodeRule]:
        """
        Find applicable rules for given code.

        Args:
            code: Source code to check
            language: Programming language
            min_confidence: Minimum confidence threshold (uses rule's default if None)

        Returns:
            List of applicable CodeRule instances, sorted by confidence
        """
        # This would typically query from stored rules
        # For now, we detect fresh rules and filter by confidence
        applicable: list[CodeRule] = []

        # In a real implementation, this would query stored rules
        # and match patterns against the code
        # Here we show the interface

        # Filter by confidence
        for rule in applicable:
            threshold = min_confidence or rule.min_confidence_threshold
            if rule.confidence >= threshold and language in rule.languages:
                applicable.append(rule)

        # Sort by confidence (highest first)
        applicable.sort(key=lambda r: r.confidence, reverse=True)

        return applicable

    # ============================================================
    # Phase 6: DB Persistence Integration (CodeRule Storage)
    # ============================================================

    async def save_rule_to_db(
        self,
        rule: CodeRule,
        db_store: Any,
        project_id: str = "global",
    ) -> str:
        """
        Save a CodeRule to the database.

        Args:
            rule: CodeRule instance to save
            db_store: PostgresMemoryStore instance
            project_id: Project scope (default 'global')

        Returns:
            Rule ID
        """
        rule_dict = {
            "id": rule.id,
            "name": rule.name,
            "description": rule.description,
            "category": rule.category,
            "before_pattern": rule.before_pattern,
            "after_pattern": rule.after_pattern,
            "pattern_type": rule.pattern_type,
            "languages": rule.languages,
            "confidence": rule.confidence,
            "observation_count": rule.observation_count,
            "success_count": rule.success_count,
            "failure_count": rule.failure_count,
            "min_confidence_threshold": rule.min_confidence_threshold,
            "promotion_threshold": rule.promotion_threshold,
        }

        rule_id = await db_store.save_code_rule(rule_dict, project_id)
        logger.info(
            "code_rule_saved_to_db",
            rule_id=rule_id,
            name=rule.name,
            category=rule.category,
            project_id=project_id,
        )
        record_counter("memory_code_rule_saved_total")
        return rule_id

    async def load_rule_from_db(
        self,
        rule_id: str,
        db_store: Any,
    ) -> CodeRule | None:
        """
        Load a CodeRule from the database.

        Args:
            rule_id: Rule ID to load
            db_store: PostgresMemoryStore instance

        Returns:
            CodeRule instance or None if not found
        """
        row = await db_store.get_code_rule(rule_id)
        if not row:
            return None

        return self._dict_to_code_rule(row)

    async def load_rules_from_db(
        self,
        db_store: Any,
        project_id: str | None = None,
        category: str | None = None,
        language: str = "python",
        min_confidence: float | None = None,
        trusted_only: bool = False,
        limit: int = 50,
    ) -> list[CodeRule]:
        """
        Load CodeRules from the database with filters.

        Args:
            db_store: PostgresMemoryStore instance
            project_id: Filter by project (None = include global)
            category: Filter by category (null_safety, error_handling, etc.)
            language: Filter by language
            min_confidence: Minimum confidence threshold
            trusted_only: Only return trusted rules
            limit: Maximum results

        Returns:
            List of CodeRule instances
        """
        rows = await db_store.find_code_rules(
            project_id=project_id,
            category=category,
            language=language,
            min_confidence=min_confidence,
            trusted_only=trusted_only,
            limit=limit,
        )

        rules = [self._dict_to_code_rule(row) for row in rows]
        logger.debug(
            "code_rules_loaded_from_db",
            count=len(rules),
            project_id=project_id,
            category=category,
        )
        return rules

    async def reinforce_rule_in_db(
        self,
        rule_id: str,
        success: bool,
        db_store: Any,
        ema_alpha: float = 0.2,
    ) -> CodeRule | None:
        """
        Update rule confidence in the database based on outcome.

        Args:
            rule_id: Rule ID to update
            success: Whether rule application was successful
            db_store: PostgresMemoryStore instance
            ema_alpha: EMA smoothing factor

        Returns:
            Updated CodeRule or None if not found
        """
        row = await db_store.update_code_rule_confidence(
            rule_id=rule_id,
            success=success,
            ema_alpha=ema_alpha,
        )

        if not row:
            logger.warning("code_rule_not_found_for_reinforcement", rule_id=rule_id)
            return None

        rule = self._dict_to_code_rule(row)
        logger.info(
            "code_rule_reinforced_in_db",
            rule_id=rule_id,
            success=success,
            new_confidence=rule.confidence,
            observation_count=rule.observation_count,
        )
        record_counter(
            "memory_code_rule_reinforced_total",
            {"success": str(success).lower()},
        )
        return rule

    async def sync_rules_to_db(
        self,
        rules: dict[str, CodeRule],
        db_store: Any,
        project_id: str = "global",
    ) -> int:
        """
        Sync in-memory rules to the database.

        Args:
            rules: Dictionary of rules to sync (id -> CodeRule)
            db_store: PostgresMemoryStore instance
            project_id: Project scope

        Returns:
            Number of rules synced
        """
        synced_count = 0
        for rule in rules.values():
            try:
                await self.save_rule_to_db(rule, db_store, project_id)
                synced_count += 1
            except Exception as e:
                logger.error(
                    "code_rule_sync_failed",
                    rule_id=rule.id,
                    error=str(e),
                )

        logger.info(
            "code_rules_synced_to_db",
            synced_count=synced_count,
            total_rules=len(rules),
            project_id=project_id,
        )
        return synced_count

    async def cleanup_weak_rules_in_db(
        self,
        db_store: Any,
        project_id: str | None = None,
        min_observations: int = 3,
    ) -> int:
        """
        Remove rules with low confidence from the database.

        Args:
            db_store: PostgresMemoryStore instance
            project_id: Optional project filter
            min_observations: Minimum observations before cleanup

        Returns:
            Number of rules deleted
        """
        deleted_count = await db_store.cleanup_weak_rules(
            project_id=project_id,
            min_observations=min_observations,
        )

        logger.info(
            "weak_rules_cleaned_from_db",
            deleted_count=deleted_count,
            project_id=project_id,
        )
        record_counter("memory_code_rule_cleanup_total", count=deleted_count)
        return deleted_count

    def _dict_to_code_rule(self, data: dict[str, Any]) -> CodeRule:
        """Convert dictionary to CodeRule instance."""
        return CodeRule(
            id=str(data.get("id", "")),
            name=data.get("name", ""),
            description=data.get("description", ""),
            category=data.get("category", "other"),
            before_pattern=data.get("before_pattern", ""),
            after_pattern=data.get("after_pattern", ""),
            pattern_type=data.get("pattern_type", "literal"),
            languages=data.get("languages", ["python"]),
            confidence=data.get("confidence", 0.5),
            observation_count=data.get("observation_count", 1),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            min_confidence_threshold=data.get("min_confidence_threshold", 0.3),
            promotion_threshold=data.get("promotion_threshold", 0.8),
        )
