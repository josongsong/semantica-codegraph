"""
Self-RAG (Self-Reflective Retrieval-Augmented Generation)

LLM decides when retrieval is needed and validates retrieved results.

References:
- Self-RAG (Asai et al., 2023)
- https://arxiv.org/abs/2310.11511

Key Insight:
Not all queries need retrieval. LLM can self-assess:
1. Whether retrieval is needed
2. Whether retrieved docs are relevant
3. Whether final answer is supported

This saves cost, latency, and improves precision.
"""

from enum import Enum
from typing import Any, Protocol

from src.common.observability import get_logger

logger = get_logger(__name__)


class RetrievalDecision(Enum):
    """Decision on whether to retrieve."""

    RETRIEVE = "retrieve"  # Retrieval needed
    SKIP = "skip"  # No retrieval needed (LLM can answer directly)
    UNCERTAIN = "uncertain"  # Unclear, default to retrieve


class RelevanceAssessment(Enum):
    """Assessment of retrieved document relevance."""

    RELEVANT = "relevant"  # Documents are relevant
    PARTIALLY_RELEVANT = "partial"  # Some relevance
    IRRELEVANT = "irrelevant"  # Not relevant


class SupportAssessment(Enum):
    """Assessment of whether answer is supported by docs."""

    FULLY_SUPPORTED = "full"
    PARTIALLY_SUPPORTED = "partial"
    NOT_SUPPORTED = "not_supported"


class LLMPort(Protocol):
    """LLM interface for self-reflection."""

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text from prompt."""
        ...


# Retrieval Decision Prompt
RETRIEVAL_DECISION_PROMPT = """You are assessing whether retrieval from a codebase is needed to answer this query.

Query: "{query}"

Consider:
- Can you answer this confidently without looking at code?
- Does this require specific implementation details?
- Is this a factual question about code structure/behavior?

Respond with ONE word:
- RETRIEVE: Need to search codebase
- SKIP: Can answer without retrieval (general knowledge)
- UNCERTAIN: Not sure (default to retrieve)

Decision:"""

# Relevance Assessment Prompt
RELEVANCE_ASSESSMENT_PROMPT = """You are assessing whether retrieved code is relevant to the query.

Query: "{query}"

Retrieved Code Summary:
{doc_summary}

Is this code relevant to answering the query?

Respond with ONE word:
- RELEVANT: Yes, this code helps answer the query
- PARTIAL: Somewhat relevant but incomplete
- IRRELEVANT: Not relevant to the query

Assessment:"""

# Support Assessment Prompt
SUPPORT_ASSESSMENT_PROMPT = """You are checking if an answer is supported by the retrieved code.

Query: "{query}"

Retrieved Code: {doc_summary}

Proposed Answer: {answer}

Is the answer fully supported by the retrieved code?

Respond with ONE word:
- FULL: Answer is fully supported
- PARTIAL: Answer is partially supported
- NOT_SUPPORTED: Answer is not supported by code

Assessment:"""


class SelfRAGDecider:
    """
    Self-RAG decision engine.

    Makes intelligent decisions about retrieval necessity.

    Features:
    - LLM-based retrieval gating
    - Confidence-based fallback
    - Cost optimization (skip unnecessary retrievals)
    """

    def __init__(
        self,
        llm: LLMPort,
        temperature: float = 0.0,
        max_tokens: int = 10,
        default_decision: RetrievalDecision = RetrievalDecision.RETRIEVE,
    ):
        """
        Initialize Self-RAG decider.

        Args:
            llm: LLM for decision-making
            temperature: Generation temperature (0.0 for deterministic)
            max_tokens: Max tokens for decision
            default_decision: Fallback decision on error
        """
        self.llm = llm
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.default_decision = default_decision

    async def should_retrieve(self, query: str) -> tuple[RetrievalDecision, float]:
        """
        Decide whether retrieval is needed.

        Args:
            query: User query

        Returns:
            Tuple of (decision, confidence)
        """
        try:
            prompt = RETRIEVAL_DECISION_PROMPT.format(query=query)

            response = await self.llm.generate(
                prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            # Parse decision
            response_clean = response.strip().upper()

            if "RETRIEVE" in response_clean:
                decision = RetrievalDecision.RETRIEVE
                confidence = 0.9
            elif "SKIP" in response_clean:
                decision = RetrievalDecision.SKIP
                confidence = 0.8
            elif "UNCERTAIN" in response_clean:
                decision = RetrievalDecision.UNCERTAIN
                confidence = 0.5
            else:
                logger.warning(
                    "self_rag_decision_parse_failed",
                    response=response,
                )
                decision = self.default_decision
                confidence = 0.3

            logger.info(
                "self_rag_decision",
                query=query[:50],
                decision=decision.value,
                confidence=confidence,
            )

            return decision, confidence

        except Exception as e:
            logger.warning(
                "self_rag_decision_failed",
                error=str(e),
                query=query[:100],
            )
            return self.default_decision, 0.5

    async def assess_relevance(
        self,
        query: str,
        doc_summary: str,
    ) -> tuple[RelevanceAssessment, float]:
        """
        Assess relevance of retrieved documents.

        Args:
            query: User query
            doc_summary: Summary of retrieved docs

        Returns:
            Tuple of (assessment, confidence)
        """
        try:
            prompt = RELEVANCE_ASSESSMENT_PROMPT.format(
                query=query,
                doc_summary=doc_summary[:500],  # Limit summary length
            )

            response = await self.llm.generate(
                prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            response_clean = response.strip().upper()

            if "RELEVANT" in response_clean and "PARTIAL" not in response_clean:
                assessment = RelevanceAssessment.RELEVANT
                confidence = 0.9
            elif "PARTIAL" in response_clean:
                assessment = RelevanceAssessment.PARTIALLY_RELEVANT
                confidence = 0.6
            elif "IRRELEVANT" in response_clean:
                assessment = RelevanceAssessment.IRRELEVANT
                confidence = 0.8
            else:
                logger.warning(
                    "self_rag_relevance_parse_failed",
                    response=response,
                )
                assessment = RelevanceAssessment.PARTIALLY_RELEVANT
                confidence = 0.5

            logger.info(
                "self_rag_relevance",
                assessment=assessment.value,
                confidence=confidence,
            )

            return assessment, confidence

        except Exception as e:
            logger.warning(
                "self_rag_relevance_failed",
                error=str(e),
            )
            return RelevanceAssessment.PARTIALLY_RELEVANT, 0.5

    async def verify_answer_support(
        self,
        query: str,
        doc_summary: str,
        answer: str,
    ) -> tuple[SupportAssessment, float]:
        """
        Verify if answer is supported by retrieved docs.

        Args:
            query: User query
            doc_summary: Summary of retrieved docs
            answer: Proposed answer

        Returns:
            Tuple of (assessment, confidence)
        """
        try:
            prompt = SUPPORT_ASSESSMENT_PROMPT.format(
                query=query,
                doc_summary=doc_summary[:500],
                answer=answer[:500],
            )

            response = await self.llm.generate(
                prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            response_clean = response.strip().upper()

            if "FULL" in response_clean:
                assessment = SupportAssessment.FULLY_SUPPORTED
                confidence = 0.9
            elif "PARTIAL" in response_clean:
                assessment = SupportAssessment.PARTIALLY_SUPPORTED
                confidence = 0.6
            elif "NOT" in response_clean:
                assessment = SupportAssessment.NOT_SUPPORTED
                confidence = 0.8
            else:
                logger.warning(
                    "self_rag_support_parse_failed",
                    response=response,
                )
                assessment = SupportAssessment.PARTIALLY_SUPPORTED
                confidence = 0.5

            logger.info(
                "self_rag_support",
                assessment=assessment.value,
                confidence=confidence,
            )

            return assessment, confidence

        except Exception as e:
            logger.warning(
                "self_rag_support_failed",
                error=str(e),
            )
            return SupportAssessment.PARTIALLY_SUPPORTED, 0.5


class SelfRAGRetriever:
    """
    Retriever with Self-RAG intelligence.

    Wraps any retriever with self-reflective capabilities.
    """

    def __init__(
        self,
        decider: SelfRAGDecider,
        skip_retrieval_threshold: float = 0.7,
        relevance_threshold: float = 0.6,
        enable_self_rag: bool = True,
    ):
        """
        Initialize Self-RAG retriever.

        Args:
            decider: Self-RAG decision engine
            skip_retrieval_threshold: Confidence to skip retrieval
            relevance_threshold: Confidence to accept retrieved docs
            enable_self_rag: Enable/disable Self-RAG (for A/B testing)
        """
        self.decider = decider
        self.skip_threshold = skip_retrieval_threshold
        self.relevance_threshold = relevance_threshold
        self.enable = enable_self_rag

        # Metrics
        self.retrieval_skipped = 0
        self.retrieval_performed = 0
        self.irrelevant_filtered = 0

    async def should_retrieve_for_query(self, query: str) -> bool:
        """
        Decide if retrieval should be performed.

        Args:
            query: User query

        Returns:
            True if retrieval needed, False to skip
        """
        if not self.enable:
            return True  # Always retrieve when Self-RAG disabled

        decision, confidence = await self.decider.should_retrieve(query)

        # Skip only if confident about skipping
        should_skip = decision == RetrievalDecision.SKIP and confidence >= self.skip_threshold

        if should_skip:
            self.retrieval_skipped += 1
            logger.info(
                "self_rag_skipping_retrieval",
                query=query[:50],
                confidence=confidence,
                total_skipped=self.retrieval_skipped,
            )
            return False
        else:
            self.retrieval_performed += 1
            return True

    async def filter_relevant_docs(
        self,
        query: str,
        docs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Filter retrieved docs by relevance assessment.

        Args:
            query: User query
            docs: Retrieved documents

        Returns:
            Filtered relevant documents
        """
        if not self.enable or not docs:
            return docs

        # Create summary of docs
        doc_summary = "\n".join([doc.get("content", "")[:200] for doc in docs[:3]])

        assessment, confidence = await self.decider.assess_relevance(query, doc_summary)

        if assessment == RelevanceAssessment.IRRELEVANT and confidence >= self.relevance_threshold:
            # Docs are irrelevant, return empty
            self.irrelevant_filtered += 1
            logger.warning(
                "self_rag_filtering_irrelevant",
                query=query[:50],
                num_docs=len(docs),
                confidence=confidence,
            )
            return []

        # Keep docs (either relevant or uncertain)
        return docs

    def get_metrics(self) -> dict[str, Any]:
        """
        Get Self-RAG metrics.

        Returns:
            Dict with metrics
        """
        total = self.retrieval_skipped + self.retrieval_performed
        skip_rate = self.retrieval_skipped / total if total > 0 else 0

        return {
            "retrieval_skipped": self.retrieval_skipped,
            "retrieval_performed": self.retrieval_performed,
            "skip_rate": skip_rate,
            "irrelevant_filtered": self.irrelevant_filtered,
            "cost_savings": skip_rate,  # Direct correlation
        }
