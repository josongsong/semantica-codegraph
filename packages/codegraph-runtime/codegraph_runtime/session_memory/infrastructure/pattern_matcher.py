"""
Pattern Matcher for Bug Pattern Matching

Implements hybrid matching strategy:
1. Hard filter (error_type, language, framework)
2. Semantic similarity (embeddings)
3. Regex boost (optional patterns)
"""

import math
import re
from typing import Protocol

from codegraph_shared.infra.observability import get_logger, record_counter, record_histogram

from .models import BugPattern, BugPatternMatch, ErrorObservation, Solution

logger = get_logger(__name__)


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""

    async def embed(self, text: str) -> list[float]: ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


class StackTraceNormalizer:
    """Normalizes stack traces for consistent matching."""

    # Patterns to remove/normalize
    LINE_NUMBER_PATTERN = re.compile(r":\d+")
    ABS_PATH_PATTERN = re.compile(r"/[^\s:]+/")
    MEMORY_ADDR_PATTERN = re.compile(r"0x[0-9a-fA-F]+")

    @classmethod
    def normalize(cls, stacktrace: str) -> str:
        """
        Normalize stacktrace by removing volatile parts.

        - Remove absolute paths
        - Mask line numbers
        - Remove memory addresses
        """
        if not stacktrace:
            return ""

        normalized = stacktrace

        # Replace absolute paths with relative
        normalized = cls.ABS_PATH_PATTERN.sub("/.../", normalized)

        # Mask line numbers
        normalized = cls.LINE_NUMBER_PATTERN.sub(":N", normalized)

        # Remove memory addresses
        normalized = cls.MEMORY_ADDR_PATTERN.sub("0xXXXX", normalized)

        return normalized

    @classmethod
    def extract_frame_signatures(cls, stacktrace: str) -> list[str]:
        """Extract function/method names from stacktrace."""
        if not stacktrace:
            return []

        # Common patterns for function names in stack traces
        # Python: "in function_name"
        # JS/TS: "at functionName" or "at Object.functionName"
        patterns = [
            re.compile(r"in (\w+)"),  # Python
            re.compile(r"at (?:Object\.)?(\w+)"),  # JS/TS
            re.compile(r"(\w+)\("),  # Generic function call
        ]

        signatures = []
        for line in stacktrace.split("\n"):
            for pattern in patterns:
                match = pattern.search(line)
                if match:
                    signatures.append(match.group(1))
                    break

        return signatures


class PatternMatcher:
    """
    Hybrid pattern matcher for bug patterns.

    Combines:
    1. Hard filter (fast candidate reduction)
    2. Semantic similarity (embedding-based)
    3. Regex boost (precision tuning)
    """

    # Score weights
    WEIGHT_TYPE = 0.25  # error_type exact match
    WEIGHT_LANG = 0.10  # language match
    WEIGHT_MSG = 0.35  # message embedding similarity
    WEIGHT_STACK = 0.20  # stacktrace embedding similarity
    WEIGHT_CODE = 0.10  # code context embedding similarity
    REGEX_BOOST_MAX = 0.10  # max boost from regex matches

    # Thresholds
    MIN_SCORE_THRESHOLD = 0.3  # minimum score to be considered a match
    HARD_FILTER_MAX_CANDIDATES = 50  # max candidates after hard filter

    def __init__(self, embedding_provider: EmbeddingProvider | None = None):
        """
        Initialize pattern matcher.

        Args:
            embedding_provider: Provider for generating embeddings (optional)
        """
        self.embedding_provider = embedding_provider
        self.normalizer = StackTraceNormalizer()

    async def match(
        self,
        observation: ErrorObservation,
        patterns: list[BugPattern],
        top_k: int = 5,
    ) -> list[BugPatternMatch]:
        """
        Match error observation against bug patterns.

        Args:
            observation: Observed error
            patterns: Available bug patterns
            top_k: Number of top matches to return

        Returns:
            List of matches sorted by score
        """
        if not patterns:
            return []

        logger.debug(
            "pattern_matching_start",
            error_type=observation.error_type,
            pattern_count=len(patterns),
        )
        record_counter("memory_pattern_match_attempts_total")

        # Stage 1: Hard filter
        candidates = self._hard_filter(observation, patterns)
        logger.debug("hard_filter_complete", candidates=len(candidates))

        if not candidates:
            return []

        # Stage 2: Ensure embeddings
        await self._ensure_embeddings(observation)

        # Stage 3: Score each candidate
        matches: list[BugPatternMatch] = []
        for pattern in candidates:
            match = self._score_pattern(observation, pattern)
            if match.score >= self.MIN_SCORE_THRESHOLD:
                matches.append(match)

        # Sort by score and take top_k
        matches.sort(key=lambda m: m.score, reverse=True)
        matches = matches[:top_k]

        logger.info(
            "pattern_matching_complete",
            candidates=len(candidates),
            matches=len(matches),
            top_score=matches[0].score if matches else 0.0,
        )
        record_histogram("memory_pattern_matches", len(matches))

        return matches

    def _hard_filter(
        self,
        observation: ErrorObservation,
        patterns: list[BugPattern],
    ) -> list[BugPattern]:
        """
        Filter patterns using hard matching criteria.

        Patterns must match at least one of:
        - error_type
        - language (if specified)
        """
        candidates = []

        for pattern in patterns:
            # Error type filter (most important)
            type_match = not pattern.error_types or observation.error_type in pattern.error_types  # no filter

            # Language filter
            lang_match = not pattern.languages or observation.language in pattern.languages  # no filter

            # Framework filter (if observation has framework)
            framework_match = (
                not observation.framework
                or not pattern.typical_frameworks
                or observation.framework in pattern.typical_frameworks
            )

            # Must match type OR (language AND framework)
            if type_match or (lang_match and framework_match):
                candidates.append(pattern)

        # Limit candidates
        if len(candidates) > self.HARD_FILTER_MAX_CANDIDATES:
            # Prioritize by error_type match
            type_matched = [p for p in candidates if observation.error_type in p.error_types]
            others = [p for p in candidates if observation.error_type not in p.error_types]
            candidates = type_matched + others[: self.HARD_FILTER_MAX_CANDIDATES - len(type_matched)]

        return candidates

    async def _ensure_embeddings(self, observation: ErrorObservation) -> None:
        """Generate embeddings for observation if not already present."""
        if not self.embedding_provider:
            return

        texts_to_embed = []
        fields = []

        # Message embedding
        if observation.message_embedding is None and observation.error_message:
            texts_to_embed.append(observation.error_message)
            fields.append("message")

        # Stack embedding
        if observation.stack_embedding is None and observation.stacktrace:
            normalized = self.normalizer.normalize(observation.stacktrace)
            texts_to_embed.append(normalized)
            fields.append("stack")

        # Code embedding
        if observation.code_embedding is None and observation.code_context:
            texts_to_embed.append(observation.code_context)
            fields.append("code")

        if not texts_to_embed:
            return

        # Batch embed
        embeddings = await self.embedding_provider.embed_batch(texts_to_embed)

        # Assign back
        for field, embedding in zip(fields, embeddings, strict=False):
            if field == "message":
                observation.message_embedding = embedding
            elif field == "stack":
                observation.stack_embedding = embedding
            elif field == "code":
                observation.code_embedding = embedding

    def _score_pattern(
        self,
        observation: ErrorObservation,
        pattern: BugPattern,
    ) -> BugPatternMatch:
        """Calculate match score for a single pattern."""
        matched_aspects: list[str] = []

        # 1. Type score
        type_score = 0.0
        if observation.error_type in pattern.error_types:
            type_score = 1.0
            matched_aspects.append(f"error_type:{observation.error_type}")

        # 2. Language score
        lang_score = 0.0
        if observation.language in pattern.languages:
            lang_score = 1.0
            matched_aspects.append(f"language:{observation.language}")

        # 3. Message similarity
        message_score = 0.0
        if observation.message_embedding and pattern.message_embedding:
            message_score = cosine_similarity(observation.message_embedding, pattern.message_embedding)
            if message_score > 0.5:
                matched_aspects.append(f"message_sim:{message_score:.2f}")

        # 4. Stack similarity
        stack_score = 0.0
        if observation.stack_embedding and pattern.stack_embedding:
            stack_score = cosine_similarity(observation.stack_embedding, pattern.stack_embedding)
            if stack_score > 0.5:
                matched_aspects.append(f"stack_sim:{stack_score:.2f}")

        # 5. Code similarity
        code_score = 0.0
        if observation.code_embedding and pattern.code_embedding:
            code_score = cosine_similarity(observation.code_embedding, pattern.code_embedding)
            if code_score > 0.5:
                matched_aspects.append(f"code_sim:{code_score:.2f}")

        # 6. Regex boost
        regex_boost = 0.0
        if observation.error_message and pattern.error_message_patterns:
            for regex in pattern.error_message_patterns:
                try:
                    if re.search(regex, observation.error_message, re.IGNORECASE):
                        regex_boost = min(regex_boost + 0.05, self.REGEX_BOOST_MAX)
                        matched_aspects.append(f"regex:{regex[:20]}...")
                except re.error:
                    pass  # Invalid regex, skip

        # Calculate weighted score
        score = (
            self.WEIGHT_TYPE * type_score
            + self.WEIGHT_LANG * lang_score
            + self.WEIGHT_MSG * message_score
            + self.WEIGHT_STACK * stack_score
            + self.WEIGHT_CODE * code_score
            + regex_boost
        )

        # Normalize to 0-1 range (max possible is 1.0 + REGEX_BOOST_MAX)
        score = min(score, 1.0)

        # Select best solution
        best_solution = self._select_best_solution(pattern)

        return BugPatternMatch(
            pattern=pattern,
            score=score,
            matched_aspects=matched_aspects,
            recommended_solution=best_solution,
            type_score=type_score,
            message_score=message_score,
            stack_score=stack_score,
            code_score=code_score,
            regex_boost=regex_boost,
        )

    def _select_best_solution(self, pattern: BugPattern) -> Solution | None:
        """Select best solution from pattern based on success rate."""
        if not pattern.solutions:
            return None

        return max(pattern.solutions, key=lambda s: s.success_rate)
