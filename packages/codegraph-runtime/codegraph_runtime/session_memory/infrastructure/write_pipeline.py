"""
SOTA Memory Write Pipeline

Implements the write pipeline for memory storage:
1. Event → Classification (type + importance)
2. Filtering (discard low-value)
3. Routing (profile/preference/episodic/semantic/fact)

Based on patterns from:
- MemGPT: LLM-driven classification
- Generative Agents: Importance scoring
- Mem0: Fact extraction and deduplication

Usage with LiteLLM:
    from codegraph_shared.infra.llm import LiteLLMAdapter
    from src.memory import create_write_pipeline, MemoryEvent

    # Create LLM-enabled pipeline
    llm = LiteLLMAdapter(model="gpt-4o-mini")
    pipeline = create_write_pipeline(llm_client=llm)

    # Process event
    event = MemoryEvent(
        user_id="user-1",
        project_id="project-1",
        text="I prefer using async/await patterns",
        source="user_input",
    )
    result = await pipeline.process(event)
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from codegraph_shared.common.observability import get_logger

from .models import (
    ImportanceLevel,
    MemoryEvent,
    MemoryType,
    MemoryUnit,
)

logger = get_logger(__name__)
# ============================================================
# LLM Provider Protocol
# ============================================================


class LLMProvider(Protocol):
    """
    Protocol for LLM providers.

    Compatible implementations:
    - LiteLLMAdapter (recommended)
    - OpenAIAdapter
    - Any class with an async complete() method
    """

    async def complete(self, prompt: str) -> str:
        """Generate completion from prompt."""
        ...


# ============================================================
# Classification Strategies
# ============================================================


class ClassificationStrategy(Protocol):
    """Protocol for memory classification strategies."""

    async def classify_type(self, event: MemoryEvent) -> MemoryType:
        """Classify memory type."""
        ...

    async def classify_importance(self, event: MemoryEvent) -> tuple[float, ImportanceLevel]:
        """Classify importance (score, level)."""
        ...


class RuleBasedClassifier:
    """
    Rule-based memory classifier.

    Fast, deterministic classification without LLM calls.
    Good for filtering obvious cases before LLM refinement.
    """

    # Profile keywords - static user/project attributes (identity/role)
    PROFILE_KEYWORDS = [
        "my name is",
        "i am a",
        "i'm a",
        "i work at",
        "my role is",
        "i specialize in",
        "my expertise",
        "my timezone",
        "i live in",
        "years of experience",
    ]

    # Preference keywords - behavioral patterns (likes/dislikes/style)
    PREFERENCE_KEYWORDS = [
        "i like",
        "i don't like",
        "i hate",
        "i prefer",
        "please always",
        "please never",
        "don't suggest",
        "i want you to",
        "remember that i",
        "i usually",
        "my style is",
        "i tend to",
        "i favor",
        "over ",  # "prefer X over Y" pattern
        "when possible",
        "functional programming",
        "oop",
        "coding style",
    ]

    # Episodic keywords - task execution
    EPISODIC_KEYWORDS = [
        "i did",
        "i fixed",
        "i implemented",
        "i changed",
        "we debugged",
        "the error was",
        "the solution was",
        "successfully",
        "failed to",
        "completed",
    ]

    # Semantic keywords - knowledge/insights
    SEMANTIC_KEYWORDS = [
        "the pattern is",
        "generally",
        "typically",
        "best practice",
        "important to note",
        "lesson learned",
        "insight:",
        "key finding",
        "conclusion",
    ]

    # Fact keywords - individual knowledge units
    FACT_KEYWORDS = [
        "the function",
        "the class",
        "the file",
        "api endpoint",
        "database",
        "config",
        "located at",
        "defined in",
        "returns",
        "uses",  # "X uses Y" pattern for technical facts
        "protocol",
        "version",
        "port",
        "library",
        "framework",
        "rabbitmq",
        "kafka",
        "redis",
        "postgres",
    ]

    # High importance indicators
    HIGH_IMPORTANCE_KEYWORDS = [
        "critical",
        "important",
        "must",
        "always",
        "never",
        "security",
        "production",
        "breaking",
        "urgent",
        "remember this",
        "don't forget",
        "key point",
    ]

    # Low importance indicators
    LOW_IMPORTANCE_KEYWORDS = [
        "maybe",
        "might",
        "just",
        "small",
        "minor",
        "trivial",
        "not important",
        "fyi",
        "btw",
    ]

    async def classify_type(self, event: MemoryEvent) -> MemoryType:
        """Classify memory type using rule-based approach."""
        text_lower = event.text.lower()

        # Check source for hints
        if event.source == "user_profile":
            return MemoryType.PROFILE
        if event.source == "user_preference":
            return MemoryType.PREFERENCE

        # Check keywords
        scores = {
            MemoryType.PROFILE: self._keyword_score(text_lower, self.PROFILE_KEYWORDS),
            MemoryType.PREFERENCE: self._keyword_score(text_lower, self.PREFERENCE_KEYWORDS),
            MemoryType.EPISODIC: self._keyword_score(text_lower, self.EPISODIC_KEYWORDS),
            MemoryType.SEMANTIC: self._keyword_score(text_lower, self.SEMANTIC_KEYWORDS),
            MemoryType.FACT: self._keyword_score(text_lower, self.FACT_KEYWORDS),
        }

        # Get best match
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        # If no clear match, classify based on context
        if best_score < 0.1:
            # Check for negation patterns that indicate low importance
            negation_patterns = ["not important", "trivial", "not a big deal", "doesn't matter"]
            is_negated = any(p in text_lower for p in negation_patterns)

            # High importance content should be stored as semantic knowledge
            high_importance_indicators = [
                "critical",
                "security",
                "never",
                "always",
                "must",
                "rule",
                "best practice",
                "don't",
                "do not",
            ]
            # Only match if "important" is not negated
            if not is_negated and any(kw in text_lower for kw in high_importance_indicators):
                return MemoryType.SEMANTIC
            # Special case: "important" keyword only if not negated
            if not is_negated and "important" in text_lower:
                return MemoryType.SEMANTIC

            # Short statements about code are usually facts
            if len(event.text) < 100 and any(kw in text_lower for kw in ["function", "class", "file", "variable"]):
                return MemoryType.FACT

            # Default to episodic for task-related content
            if event.source in ["tool_result", "observation"]:
                return MemoryType.EPISODIC

            # User input defaults to fact if contains technical terms
            if event.source == "user_input" and len(event.text) > 20:
                return MemoryType.FACT

            return MemoryType.NONE

        return best_type

    async def classify_importance(self, event: MemoryEvent) -> tuple[float, ImportanceLevel]:
        """Classify importance using rule-based approach."""
        text_lower = event.text.lower()

        # Base score
        score = 0.5

        # Adjust based on keywords
        high_matches = self._keyword_score(text_lower, self.HIGH_IMPORTANCE_KEYWORDS)
        low_matches = self._keyword_score(text_lower, self.LOW_IMPORTANCE_KEYWORDS)

        score += high_matches * 0.3
        score -= low_matches * 0.2

        # Source-based adjustments
        if event.source == "user_input":
            score += 0.1  # User explicitly stated
        if event.source == "observation":
            score -= 0.1  # System observation

        # Context-based adjustments
        if event.context.get("explicit_remember"):
            score += 0.2  # User explicitly asked to remember
        if event.context.get("error_resolution"):
            score += 0.15  # Error resolution knowledge is valuable

        # Clamp to [0, 1]
        score = max(0.0, min(1.0, score))

        # Map to level
        level = self._score_to_level(score)

        return score, level

    def _keyword_score(self, text: str, keywords: list[str]) -> float:
        """Calculate keyword match score."""
        matches = sum(1 for kw in keywords if kw in text)
        return min(1.0, matches / max(len(keywords) * 0.3, 1))

    def _score_to_level(self, score: float) -> ImportanceLevel:
        """Convert numeric score to importance level."""
        if score >= 0.8:
            return ImportanceLevel.CRITICAL
        if score >= 0.6:
            return ImportanceLevel.HIGH
        if score >= 0.4:
            return ImportanceLevel.MEDIUM
        if score >= 0.2:
            return ImportanceLevel.LOW
        return ImportanceLevel.TRIVIAL


class LLMClassifier:
    """
    LLM-based memory classifier.

    Uses LLM for nuanced classification. More accurate but slower.
    Should be used selectively after rule-based filtering.

    Example:
        from codegraph_shared.infra.llm import LiteLLMAdapter

        llm = LiteLLMAdapter(model="gpt-4o-mini")
        classifier = LLMClassifier(llm)
        memory_type = await classifier.classify_type(event)
    """

    def __init__(self, llm_client: LLMProvider):
        """
        Initialize LLM classifier.

        Args:
            llm_client: LLM provider with async complete() method.
                        Use LiteLLMAdapter for multi-provider support.
        """
        self.llm = llm_client

    async def classify_type(self, event: MemoryEvent) -> MemoryType:
        """Classify memory type using LLM."""
        prompt = f"""Classify this memory into exactly one category:

Text: "{event.text}"
Source: {event.source}
Context: {event.context}

Categories:
- PROFILE: Static user/project attributes (name, role, expertise, timezone)
- PREFERENCE: Behavioral patterns and preferences (coding style, likes/dislikes)
- EPISODIC: Specific task execution records (what happened, solutions found)
- SEMANTIC: General knowledge and insights (patterns, best practices)
- FACT: Individual facts about code/system (function does X, file is at Y)
- NONE: Not worth storing (greetings, fillers, already known)

Respond with ONLY the category name (e.g., "FACT")."""

        try:
            response = await self.llm.complete(prompt)
            result = response.strip().upper()

            type_map = {
                "PROFILE": MemoryType.PROFILE,
                "PREFERENCE": MemoryType.PREFERENCE,
                "EPISODIC": MemoryType.EPISODIC,
                "SEMANTIC": MemoryType.SEMANTIC,
                "FACT": MemoryType.FACT,
                "NONE": MemoryType.NONE,
            }

            return type_map.get(result, MemoryType.NONE)

        except Exception as e:
            logger.warning(f"LLM classification failed: {e}")
            return MemoryType.NONE

    async def classify_importance(self, event: MemoryEvent) -> tuple[float, ImportanceLevel]:
        """Classify importance using LLM (Generative Agents style)."""
        prompt = f"""Rate the importance of remembering this on a scale of 1-10.

Text: "{event.text}"
Source: {event.source}

Scoring guide:
1-2: Trivial (greetings, fillers, obvious facts)
3-4: Low (minor observations, common knowledge)
5-6: Medium (useful context, standard task info)
7-8: High (valuable insights, important decisions)
9-10: Critical (security issues, breaking changes, explicit requests to remember)

Respond with ONLY a number (e.g., "7")."""

        try:
            response = await self.llm.complete(prompt)
            score_raw = int(response.strip())
            score = score_raw / 10.0

            level = self._score_to_level(score)
            return score, level

        except Exception as e:
            logger.warning(f"LLM importance scoring failed: {e}")
            return 0.5, ImportanceLevel.MEDIUM

    def _score_to_level(self, score: float) -> ImportanceLevel:
        """Convert numeric score to importance level."""
        if score >= 0.8:
            return ImportanceLevel.CRITICAL
        if score >= 0.6:
            return ImportanceLevel.HIGH
        if score >= 0.4:
            return ImportanceLevel.MEDIUM
        if score >= 0.2:
            return ImportanceLevel.LOW
        return ImportanceLevel.TRIVIAL


class HybridClassifier:
    """
    Hybrid classifier combining rule-based and LLM approaches.

    Uses rules for fast filtering, LLM for ambiguous cases.

    Example:
        from codegraph_shared.infra.llm import LiteLLMAdapter

        llm = LiteLLMAdapter(model="gpt-4o-mini")
        classifier = HybridClassifier(llm_client=llm)
    """

    def __init__(
        self,
        llm_client: LLMProvider | None = None,
        llm_threshold: float = 0.3,
    ):
        """
        Initialize hybrid classifier.

        Args:
            llm_client: Optional LLM provider for refinement.
                        Use LiteLLMAdapter for multi-provider support.
            llm_threshold: Confidence threshold below which to use LLM
        """
        self.rule_classifier = RuleBasedClassifier()
        self.llm_classifier = LLMClassifier(llm_client) if llm_client else None
        self.llm_threshold = llm_threshold

    async def classify_type(self, event: MemoryEvent) -> MemoryType:
        """Classify with hybrid approach."""
        # First, try rule-based
        rule_type = await self.rule_classifier.classify_type(event)

        # If confident or no LLM available, return rule result
        if rule_type != MemoryType.NONE or not self.llm_classifier:
            return rule_type

        # Use LLM for ambiguous cases
        return await self.llm_classifier.classify_type(event)

    async def classify_importance(self, event: MemoryEvent) -> tuple[float, ImportanceLevel]:
        """Classify importance with hybrid approach."""
        # Rule-based first
        score, level = await self.rule_classifier.classify_importance(event)

        # If score is in middle range and LLM available, refine
        if self.llm_classifier and 0.3 < score < 0.7:
            llm_score, llm_level = await self.llm_classifier.classify_importance(event)
            # Average the scores
            score = (score + llm_score) / 2
            level = self.rule_classifier._score_to_level(score)

        return score, level


# ============================================================
# Write Pipeline
# ============================================================


@dataclass
class PipelineConfig:
    """Configuration for write pipeline."""

    # Filtering thresholds
    min_importance_score: float = 0.2  # Discard below this
    min_text_length: int = 10  # Discard shorter than this

    # Deduplication
    enable_dedup: bool = True
    dedup_similarity_threshold: float = 0.9

    # Rate limiting
    max_memories_per_minute: int = 100

    # Bucket limits
    max_profile_items: int = 100
    max_preference_items: int = 500
    max_facts_per_project: int = 10000


@dataclass
class PipelineResult:
    """Result of write pipeline processing."""

    accepted: bool
    memory_type: MemoryType
    importance: float
    importance_level: ImportanceLevel
    memory_unit: MemoryUnit | None = None
    rejection_reason: str | None = None


class MemoryWritePipeline:
    """
    SOTA Memory Write Pipeline.

    Processes raw events into stored memories:
    1. Pre-filtering (length, rate limit)
    2. Classification (type + importance)
    3. Filtering (importance threshold)
    4. Deduplication
    5. Routing to appropriate bucket
    """

    def __init__(
        self,
        classifier: ClassificationStrategy | None = None,
        config: PipelineConfig | None = None,
        storage: Any | None = None,
        embedder: Any | None = None,
    ):
        """
        Initialize write pipeline.

        Args:
            classifier: Classification strategy (default: RuleBasedClassifier)
            config: Pipeline configuration
            storage: Storage backend for dedup checking
            embedder: Embedding provider for similarity-based dedup
        """
        self.classifier = classifier or RuleBasedClassifier()
        self.config = config or PipelineConfig()
        self.storage = storage
        self.embedder = embedder

        # Rate limiting state
        self._recent_writes: list[datetime] = []

    async def process(self, event: MemoryEvent) -> PipelineResult:
        """
        Process a memory event through the pipeline.

        Args:
            event: Raw memory event

        Returns:
            PipelineResult with processing outcome
        """
        # Step 1: Pre-filtering
        rejection = self._pre_filter(event)
        if rejection:
            return PipelineResult(
                accepted=False,
                memory_type=MemoryType.NONE,
                importance=0.0,
                importance_level=ImportanceLevel.TRIVIAL,
                rejection_reason=rejection,
            )

        # Step 2: Classification
        memory_type = await self.classifier.classify_type(event)
        importance, importance_level = await self.classifier.classify_importance(event)

        # Update event with classification
        event.memory_type = memory_type
        event.importance = importance
        event.importance_level = importance_level

        # Step 3: Importance filtering
        if memory_type == MemoryType.NONE:
            return PipelineResult(
                accepted=False,
                memory_type=memory_type,
                importance=importance,
                importance_level=importance_level,
                rejection_reason="Classified as NONE type",
            )

        if importance < self.config.min_importance_score:
            return PipelineResult(
                accepted=False,
                memory_type=memory_type,
                importance=importance,
                importance_level=importance_level,
                rejection_reason=f"Importance {importance:.2f} below threshold {self.config.min_importance_score}",
            )

        # Step 4: Deduplication (if storage available)
        if self.config.enable_dedup and self.storage:
            is_dup = await self._check_duplicate(event)
            if is_dup:
                return PipelineResult(
                    accepted=False,
                    memory_type=memory_type,
                    importance=importance,
                    importance_level=importance_level,
                    rejection_reason="Duplicate memory",
                )

        # Step 5: Create memory unit
        memory_unit = self._create_memory_unit(event)

        # Step 6: Update rate limit state
        self._recent_writes.append(datetime.now())

        return PipelineResult(
            accepted=True,
            memory_type=memory_type,
            importance=importance,
            importance_level=importance_level,
            memory_unit=memory_unit,
        )

    async def process_batch(self, events: list[MemoryEvent]) -> list[PipelineResult]:
        """Process multiple events."""
        results = []
        for event in events:
            result = await self.process(event)
            results.append(result)
        return results

    def _pre_filter(self, event: MemoryEvent) -> str | None:
        """
        Pre-filter event before classification.

        Returns rejection reason or None if passed.
        """
        # Length check
        if len(event.text.strip()) < self.config.min_text_length:
            return f"Text too short ({len(event.text)} < {self.config.min_text_length})"

        # Rate limit check
        now = datetime.now()

        # Clean old entries
        self._recent_writes = [t for t in self._recent_writes if (now - t).total_seconds() < 60]

        if len(self._recent_writes) >= self.config.max_memories_per_minute:
            return f"Rate limit exceeded ({self.config.max_memories_per_minute}/min)"

        return None

    async def _check_duplicate(self, event: MemoryEvent) -> bool:
        """
        Check if event is duplicate of existing memory.

        Uses embedding-based similarity if embedder is available,
        otherwise falls back to text-based search.
        """
        if not self.storage:
            return False

        try:
            # Try embedding-based similarity check first
            if self.embedder:
                event_embedding = await self.embedder.embed(event.text)
                existing = await self.storage.find_by_embedding(
                    embedding=event_embedding,
                    threshold=self.config.dedup_similarity_threshold,
                    limit=1,
                )
                if existing:
                    logger.debug(
                        "duplicate_found_by_embedding",
                        text_preview=event.text[:50],
                        similarity=existing[0].get("similarity", 0) if isinstance(existing[0], dict) else 0,
                    )
                    return True

            # Fallback to text-based search
            existing = await self.storage.find_similar(
                text=event.text,
                threshold=self.config.dedup_similarity_threshold,
                limit=1,
            )
            return len(existing) > 0
        except AttributeError:
            # Storage doesn't support find_by_embedding, use text-based only
            try:
                existing = await self.storage.find_similar(
                    text=event.text,
                    threshold=self.config.dedup_similarity_threshold,
                    limit=1,
                )
                return len(existing) > 0
            except Exception:
                return False
        except Exception as e:
            logger.warning("dedup_check_failed", error=str(e))
            return False

    def _create_memory_unit(self, event: MemoryEvent) -> MemoryUnit:
        """Create memory unit from classified event."""
        import uuid

        return MemoryUnit(
            id=str(uuid.uuid4()),
            content=event.text,
            memory_type=event.memory_type,
            source=event.source,
            source_id=event.context.get("source_id"),
            user_id=event.user_id,
            project_id=event.project_id,
            importance=event.importance,
            recency_score=1.0,  # New memory = max recency
            created_at=event.timestamp,
            last_used=event.timestamp,
            use_count=0,
        )


# ============================================================
# Fact Extractor (Mem0-style)
# ============================================================


class FactExtractor:
    """
    Extract individual facts from text (Mem0-style).

    Breaks down complex statements into atomic facts.

    Example:
        from codegraph_shared.infra.llm import LiteLLMAdapter

        llm = LiteLLMAdapter(model="gpt-4o-mini")
        extractor = FactExtractor(llm_client=llm)
        facts = await extractor.extract_facts("The auth module uses JWT tokens.")
    """

    def __init__(self, llm_client: LLMProvider | None = None):
        """
        Initialize fact extractor.

        Args:
            llm_client: Optional LLM provider for complex extraction.
                        Use LiteLLMAdapter for multi-provider support.
        """
        self.llm = llm_client

    async def extract_facts(self, text: str) -> list[str]:
        """
        Extract atomic facts from text.

        Args:
            text: Input text

        Returns:
            List of atomic facts
        """
        # Try rule-based extraction first
        facts = self._rule_based_extract(text)

        # Use LLM for complex cases
        if not facts and self.llm and len(text) > 50:
            facts = await self._llm_extract(text)

        return facts

    def _rule_based_extract(self, text: str) -> list[str]:
        """Extract facts using rules."""
        facts = []

        # Split on common delimiters
        sentences = re.split(r"[.!?]\s+", text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Check if it's a fact-like statement
            if self._is_fact_like(sentence):
                # Clean and normalize
                fact = self._normalize_fact(sentence)
                if fact and len(fact) >= 10:
                    facts.append(fact)

        return facts

    def _is_fact_like(self, sentence: str) -> bool:
        """Check if sentence looks like a fact."""
        lower = sentence.lower()

        # Patterns that indicate facts
        fact_patterns = [
            r"^the \w+ (is|are|has|does)",  # The X is/are/has...
            r"^this (function|class|file|module)",  # This function...
            r"(located|defined|stored) (at|in)",  # Located at...
            r"(returns|accepts|takes|requires)",  # Returns...
            r"(uses|calls|imports|depends)",  # Uses...
            r"^(when|if) .+ (then|,)",  # When X, then Y
        ]

        for pattern in fact_patterns:
            if re.search(pattern, lower):
                return True

        return False

    def _normalize_fact(self, sentence: str) -> str:
        """Normalize fact text."""
        # Remove leading articles
        fact = re.sub(r"^(the|a|an)\s+", "", sentence, flags=re.IGNORECASE)

        # Capitalize first letter
        if fact:
            fact = fact[0].upper() + fact[1:]

        # Ensure ends with period
        if fact and not fact.endswith("."):
            fact += "."

        return fact

    async def _llm_extract(self, text: str) -> list[str]:
        """Extract facts using LLM."""
        prompt = f"""Extract atomic facts from this text.
Each fact should be:
- Self-contained (understandable without context)
- Specific (about concrete things, not opinions)
- Concise (one sentence)

Text: "{text}"

Return facts as a JSON array of strings. If no facts found, return [].
Example: ["The authenticate function is in auth.py.", "Redis cache expires after 1 hour."]"""

        try:
            response = await self.llm.complete(prompt)

            # Parse JSON response
            import json

            facts = json.loads(response)

            if isinstance(facts, list):
                return [f for f in facts if isinstance(f, str)]

        except Exception as e:
            logger.warning(f"LLM fact extraction failed: {e}")

        return []


# ============================================================
# Factory Functions
# ============================================================


def create_write_pipeline(
    llm_client: LLMProvider | None = None,
    storage: Any | None = None,
    config: PipelineConfig | None = None,
    embedder: Any | None = None,
) -> MemoryWritePipeline:
    """
    Create configured write pipeline.

    Args:
        llm_client: Optional LLM provider for classification.
                    Use LiteLLMAdapter for multi-provider support.
        storage: Optional storage backend for deduplication
        config: Pipeline configuration
        embedder: Optional embedding provider for similarity-based dedup

    Returns:
        Configured MemoryWritePipeline

    Example:
        from codegraph_shared.infra.llm import LiteLLMAdapter

        llm = LiteLLMAdapter(model="gpt-4o-mini")
        pipeline = create_write_pipeline(llm_client=llm)
    """
    classifier = HybridClassifier(llm_client=llm_client) if llm_client else RuleBasedClassifier()

    return MemoryWritePipeline(
        classifier=classifier,
        config=config or PipelineConfig(),
        storage=storage,
        embedder=embedder,
    )
