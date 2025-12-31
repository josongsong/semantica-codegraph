"""TaintRuleExecutor - Runtime Execution Engine.

RFC-033 Section 7: CompiledRule Execution.

Pipeline:
    1. Build indices from entities
    2. For each rule:
        a. Generate candidates (via generators)
        b. Apply prefilters (cheap gates)
        c. Evaluate predicates (short-circuit)
        d. Calculate confidence
        e. Build match result
    3. Return matches
"""

import logging
import time
from typing import TYPE_CHECKING

from trcr.index.cache import MatchCache

if TYPE_CHECKING:
    from trcr.telemetry.collector import TelemetryCollector
from trcr.index.multi import MultiIndex
from trcr.ir.executable import TaintRuleExecutableIR
from trcr.ir.generators import (
    CallPrefixGenIR,
    ExactCallGenIR,
    ExactTypeCallGenIR,
    FallbackGenIR,
    PrefilterCallStartsWithIR,
    PrefilterHasArgIndexIR,
    PrefilterIR,
    PrefilterTypeEndsWithIR,
    TypeSuffixGenIR,
    TypeTrigramGenIR,
)
from trcr.runtime.evaluator import evaluate_predicate
from trcr.types.entity import Entity
from trcr.types.match import Match, MatchContext, TraceInfo

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    """Execution error."""


class TaintRuleExecutor:
    """Rule execution engine.

    RFC-033 Section 7: Execute compiled rules against entities.

    Architecture:
        1. Build indices from entities (one-time setup)
        2. Execute rules in specificity order
        3. Short-circuit on first predicate failure
        4. Collect matches

    Performance:
        - O(1) for exact matches (hash lookup)
        - O(log N) for prefix/suffix matches (trie)
        - O(T) for trigram matches
        - O(N) for fallback (linear scan)

    Usage:
        >>> executor = TaintRuleExecutor(compiled_rules)
        >>> matches = executor.execute(entities)
        >>> matches[0].rule_id
        'sink.sql.sqlite3'
    """

    def __init__(
        self,
        rules: list[TaintRuleExecutableIR],
        enable_cache: bool = True,
        cache_size: int = 10000,
        telemetry: "TelemetryCollector | None" = None,
    ) -> None:
        """Initialize executor.

        SOTA: Optional result caching for repeated executions.

        Args:
            rules: Compiled executable rules (sorted by specificity)
            enable_cache: Enable result caching (default: True)
            cache_size: Maximum cache entries (default: 10000)
            telemetry: Optional telemetry collector for metrics (RFC-036)
        """
        self.rules = sorted(rules)  # Sort by specificity
        self.enable_cache = enable_cache
        self._telemetry = telemetry

        # SOTA: Result cache
        self._cache = MatchCache(max_size=cache_size) if enable_cache else None

        self.stats = {
            "total_rules": len(rules),
            "total_entities": 0,
            "total_matches": 0,
            "execution_time_ms": 0.0,
            "candidates_generated": 0,
            "predicates_evaluated": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

    def execute(
        self,
        entities: list[Entity],
        enable_trace: bool = False,
    ) -> list[Match]:
        """Execute rules against entities.

        RFC-033: Main execution loop.

        Steps:
            1. Build indices from entities
            2. Create match context
            3. For each rule (in specificity order):
                - Generate candidates
                - Evaluate predicates
                - Collect matches
            4. Return matches

        Args:
            entities: Entities to match against
            enable_trace: Enable trace info for debugging

        Returns:
            List of matches (sorted by specificity)

        Example:
            >>> executor = TaintRuleExecutor(rules)
            >>> entities = [MockEntity(id="e1", kind="call", call="execute", ...)]
            >>> matches = executor.execute(entities)
            >>> len(matches)
            3
        """
        start_time = time.time()

        # 1. Build indices
        context, multi_index = self._build_context(entities)

        # 2. Execute rules
        matches: list[Match] = []

        for rule in self.rules:
            rule_matches = self._execute_rule(rule, entities, context, multi_index, enable_trace)
            matches.extend(rule_matches)

        # Update stats
        elapsed_ms = (time.time() - start_time) * 1000
        self.stats["total_entities"] = len(entities)
        self.stats["total_matches"] = len(matches)
        self.stats["execution_time_ms"] = elapsed_ms

        logger.info(
            "Executed %d rules against %d entities: %d matches in %.2fms",
            len(self.rules),
            len(entities),
            len(matches),
            elapsed_ms,
        )

        return matches

    def _build_context(self, entities: list[Entity]) -> tuple[MatchContext, MultiIndex]:
        """Build match context with indices.

        RFC-034: Build indices for fast lookup.

        Args:
            entities: Entities to index

        Returns:
            Tuple of (MatchContext, MultiIndex)
        """
        context = MatchContext()

        # Build multi-index (includes all index types)
        multi_index = MultiIndex()
        multi_index.build(entities)

        # Populate context (for backward compatibility)
        context.exact_type_call_index = multi_index.exact_type_call_index
        context.exact_call_index = multi_index.exact_call_index
        context.total_entities = len(entities)

        stats = multi_index.stats()
        logger.debug(
            "Built indices: %d type+call, %d call, %d types, %d calls",
            stats.exact_type_call_size,
            stats.exact_call_size,
            stats.type_index_size,
            stats.call_index_size,
        )

        return context, multi_index

    def _execute_rule(
        self,
        rule: TaintRuleExecutableIR,
        entities: list[Entity],
        context: MatchContext,
        multi_index: MultiIndex,
        enable_trace: bool,
    ) -> list[Match]:
        """Execute single rule against entities.

        RFC-033: Rule execution with candidate generation + predicate evaluation.

        Args:
            rule: Rule to execute
            entities: All entities
            context: Match context
            multi_index: MultiIndex for lookups
            enable_trace: Enable trace

        Returns:
            List of matches from this rule
        """
        matches: list[Match] = []

        # 1. Generate candidates
        candidates = self._generate_candidates(rule, entities, context, multi_index)
        self.stats["candidates_generated"] += len(candidates)

        # 2. Apply prefilters
        candidates = self._apply_prefilters(rule, candidates)

        # 3. Evaluate predicates for each candidate
        for candidate in candidates:
            match = self._evaluate_candidate(rule, candidate, context, enable_trace)
            if match:
                matches.append(match)

        return matches

    def _generate_candidates(
        self,
        rule: TaintRuleExecutableIR,
        entities: list[Entity],
        context: MatchContext,
        multi_index: MultiIndex,
    ) -> list[Entity]:
        """Generate candidate entities using generators.

        RFC-033 Section 4: Candidate generation.
        RFC-034: Uses MultiIndex for all lookups.

        Args:
            rule: Rule with generators
            entities: All entities
            context: Match context with indices
            multi_index: MultiIndex for lookups

        Returns:
            List of candidate entities
        """
        candidates: list[Entity] = []

        for generator in rule.generator_exec.candidate_plan.generators:
            if isinstance(generator, ExactTypeCallGenIR):
                # O(1) hash lookup
                base_type, call = generator.key
                candidates.extend(multi_index.query_exact_type_call(base_type, call))
                context.record_hit("exact_type_call")

            elif isinstance(generator, ExactCallGenIR):
                # O(1) hash lookup
                candidates.extend(multi_index.query_exact_call(generator.key))
                context.record_hit("exact_call")

            elif isinstance(generator, CallPrefixGenIR):
                # O(L) prefix trie lookup
                candidates.extend(multi_index.query_call_prefix(generator.prefix))
                context.record_hit("call_prefix")

            elif isinstance(generator, TypeSuffixGenIR):
                # O(L) suffix trie lookup
                candidates.extend(multi_index.query_type_suffix(generator.suffix))
                context.record_hit("type_suffix")

            elif isinstance(generator, TypeTrigramGenIR):
                # O(T) trigram lookup
                trigrams_raw = generator.key.get("trigrams", [])
                trigrams: list[str] = list(trigrams_raw) if isinstance(trigrams_raw, list) else []
                if trigrams:
                    # Use trigrams to construct substring for contains search
                    # E.g., ["mon", "ong", "ngo"] → "mongo" (reconstruct original)
                    literal = trigrams[0] + "".join(t[-1] for t in trigrams[1:]) if trigrams else ""
                    candidates.extend(multi_index.query_type_contains(literal))
                context.record_hit("type_trigram")

            elif isinstance(generator, FallbackGenIR):
                # O(N) linear scan (last resort)
                candidates.extend(multi_index.query_fallback())
                context.record_hit("fallback")

        return candidates

    def _apply_prefilters(
        self,
        rule: TaintRuleExecutableIR,
        candidates: list[Entity],
    ) -> list[Entity]:
        """Apply prefilters to candidates.

        RFC-033: Cheap gates before expensive predicate evaluation.

        Args:
            rule: Rule with prefilters
            candidates: Candidate entities

        Returns:
            Filtered candidates
        """
        prefilters = rule.generator_exec.candidate_plan.prefilters

        if not prefilters:
            return candidates

        filtered: list[Entity] = []

        for candidate in candidates:
            if self._check_prefilters(prefilters, candidate):
                filtered.append(candidate)

        return filtered

    def _check_prefilters(
        self,
        prefilters: list[PrefilterIR],
        entity: Entity,
    ) -> bool:
        """Check if entity passes all prefilters.

        Args:
            prefilters: List of prefilters
            entity: Entity to check

        Returns:
            True if all prefilters pass
        """
        for prefilter in prefilters:
            if isinstance(prefilter, PrefilterCallStartsWithIR):
                if not entity.call or not entity.call.startswith(prefilter.value):
                    return False

            elif isinstance(prefilter, PrefilterTypeEndsWithIR):
                if not entity.base_type or not entity.base_type.endswith(prefilter.value):
                    return False

            elif isinstance(prefilter, PrefilterHasArgIndexIR):
                if len(entity.args) <= prefilter.value:
                    return False

        return True

    def _evaluate_candidate(
        self,
        rule: TaintRuleExecutableIR,
        entity: Entity,
        context: MatchContext,
        enable_trace: bool,
    ) -> Match | None:
        """Evaluate predicates for candidate.

        RFC-033: Short-circuit predicate evaluation + confidence calculation.

        SOTA: Result caching for repeated (entity, rule) pairs.

        Args:
            rule: Rule to execute
            entity: Candidate entity
            context: Match context
            enable_trace: Enable trace

        Returns:
            Match if all predicates pass, None otherwise
        """
        # SOTA: Check cache first
        if self._cache:
            cached = self._cache.get(entity.id, rule.compiled_id)
            if cached is not None:
                self.stats["cache_hits"] += 1
                return cached if isinstance(cached, Match) else None
            self.stats["cache_misses"] += 1

        confidence = rule.confidence.base_confidence
        confidence_adjustments: list[tuple[str, float]] = []
        predicate_results: list[tuple[str, bool, float]] = []

        # Evaluate predicates (short-circuit on failure)
        for predicate in rule.predicate_exec.predicates:
            self.stats["predicates_evaluated"] += 1

            passed, conf_adj = evaluate_predicate(predicate, entity, context)

            predicate_results.append((predicate.kind, passed, conf_adj))

            if not passed:
                # Short-circuit: stop on first failure
                return None

            # Accumulate confidence adjustments
            if conf_adj != 0.0:
                confidence += conf_adj
                confidence_adjustments.append((predicate.kind, conf_adj))

        # All predicates passed!

        # Calculate final confidence (clamp to [0, 1])
        final_confidence = max(0.0, min(1.0, confidence))

        # Check reporting threshold
        if not rule.confidence.should_report():
            return None

        # Build trace (if enabled)
        trace = None
        if enable_trace:
            trace = TraceInfo(
                rule_id=rule.rule_id,
                atom_id=rule.atom_id,
                tier=rule.tier,
                generator_kind=rule.generator_exec.candidate_plan.generators[0].kind,
                index_used=rule.generator_exec.candidate_plan.generators[0].index,
                candidates_generated=1,  # This candidate
                predicates_evaluated=len(predicate_results),
                predicates_passed=len([r for r in predicate_results if r[1]]),
                predicate_results=predicate_results,
                base_confidence=rule.confidence.base_confidence,
                confidence_adjustments=confidence_adjustments,
                final_confidence=final_confidence,
                specificity_score=rule.specificity.final_score,
            )

        # Build match
        match = Match(
            rule_id=rule.rule_id,
            atom_id=rule.atom_id,
            entity=entity,
            confidence=final_confidence,
            specificity=rule.specificity.final_score,
            effect_kind=rule.effect.kind,
            taint_positions=rule.effect.arg_positions,
            tier=rule.tier,
            severity=rule.effect.vulnerability.severity if rule.effect.vulnerability else None,
            tags=rule.tags,
            trace=trace,
        )

        # SOTA: Cache result
        if self._cache:
            self._cache.set(entity.id, rule.compiled_id, match)

        # RFC-036: Log to telemetry
        if self._telemetry:
            self._telemetry.log_match(match, context)

        return match

    def get_stats(self) -> dict[str, float | int]:
        """Get execution statistics.

        Returns:
            Dict with execution stats
        """
        return self.stats.copy()
