"""
Code Rule Manager

Manages code transformation rules detection, reinforcement, and persistence.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from codegraph_runtime.session_memory.infrastructure.models import CodeRule
from codegraph_shared.infra.observability import get_logger, record_counter

logger = get_logger(__name__)


class CodeRuleManager:
    """
    Manages code transformation rules.

    Responsibilities:
    - Detect transformation rules from patches
    - Reinforce/weaken rules based on outcomes
    - Manage rule confidence and cleanup
    - DB persistence for rules
    """

    def detect_from_patch(
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
        rules: list[CodeRule] = []

        # Pattern 1: Direct access -> Optional check
        if "if " in after and " else " in after and " if " not in before:
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
        before_indent = max((len(line) - len(line.lstrip()) for line in before.split("\n") if line.strip()), default=0)
        after_indent = max((len(line) - len(line.lstrip()) for line in after.split("\n") if line.strip()), default=0)

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
        rules: list[CodeRule] = []

        # Pattern 1: Generator instead of list
        if "(" in after and "for" in after and ")" in after:
            if "[" in before and "for" in before and "]" in before:
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
        rules: list[CodeRule] = []

        # Pattern 1: Parameterized queries
        if "?" in after or "%s" in after:
            if "f'" in before or 'f"' in before:
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
    # Confidence-based Rule Management
    # ============================================================

    def reinforce(
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

    def should_apply(self, rule: CodeRule) -> bool:
        """
        Determine if a rule should be applied based on confidence.

        Rules below min_confidence_threshold are not applied.

        Args:
            rule: CodeRule to check

        Returns:
            True if rule should be applied
        """
        return rule.confidence >= rule.min_confidence_threshold

    def is_trusted(self, rule: CodeRule) -> bool:
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

    def get_applicable(
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
        applicable: list[CodeRule] = []

        # Filter by confidence and sort
        applicable.sort(key=lambda r: r.confidence, reverse=True)

        return applicable

    # ============================================================
    # DB Persistence
    # ============================================================

    async def save_to_db(
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

    async def load_from_db(
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
            category: Filter by category
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

    async def reinforce_in_db(
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

    async def sync_to_db(
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
                await self.save_to_db(rule, db_store, project_id)
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

    async def cleanup_weak_in_db(
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
