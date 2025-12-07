"""
HyDE (Hypothetical Document Embeddings)

Generates hypothetical answer documents to improve retrieval for conceptual queries.

References:
- Precise Zero-Shot Dense Retrieval without Relevance Labels (Gao et al., 2022)
- https://arxiv.org/abs/2212.10496

Key Insight:
Instead of embedding the query directly, generate a hypothetical "ideal answer"
and use that for retrieval. Works better for abstract/conceptual queries.
"""

from typing import Any, Protocol

from src.common.observability import get_logger

logger = get_logger(__name__)


class LLMPort(Protocol):
    """LLM interface for generating hypothetical documents."""

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text from prompt."""
        ...


class EmbeddingPort(Protocol):
    """Embedding interface for vectorizing documents."""

    async def embed(self, text: str) -> list[float]:
        """Embed text to vector."""
        ...


# Prompt templates optimized for code search
CODE_HYDE_PROMPT = """You are an expert code documentation writer.

Given this question about a codebase:
"{query}"

Write a concise, technical answer (2-3 sentences) that would appear in good documentation.
Focus on:
- What the code does (functionality)
- How it works (mechanism)
- Key components involved

Answer:"""

CONCEPT_HYDE_PROMPT = """You are a technical architect explaining code concepts.

Question: "{query}"

Write a brief explanation (2-3 sentences) that captures:
- The core concept or pattern
- Why it's used
- Common implementation approach

Explanation:"""

TROUBLESHOOTING_HYDE_PROMPT = """You are helping debug a codebase issue.

Problem: "{query}"

Describe what the relevant code section would look like (2-3 sentences):
- What components are involved
- What the fix or solution entails
- Key code patterns to look for

Description:"""


class HyDEGenerator:
    """
    HyDE (Hypothetical Document Embeddings) generator.

    Generates hypothetical documents for better retrieval on abstract queries.

    Features:
    - Query-type adaptive prompts (code/concept/troubleshooting)
    - Temperature=0 for consistency
    - Fallback to original query on failure
    - Configurable multi-hypothesis generation
    """

    def __init__(
        self,
        llm: LLMPort,
        embedding_provider: EmbeddingPort,
        temperature: float = 0.0,
        max_tokens: int = 150,
        num_hypotheses: int = 1,
    ):
        """
        Initialize HyDE generator.

        Args:
            llm: LLM for generating hypothetical documents
            embedding_provider: Embedding provider for vectorization
            temperature: Generation temperature (0.0 = deterministic)
            max_tokens: Max tokens for hypothetical doc
            num_hypotheses: Number of hypotheses to generate (1-3 recommended)
        """
        self.llm = llm
        self.embedding = embedding_provider
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.num_hypotheses = num_hypotheses

    async def generate_hypothetical_document(
        self,
        query: str,
        query_type: str = "code",
    ) -> str:
        """
        Generate a single hypothetical document for the query.

        Args:
            query: User query
            query_type: Query type (code/concept/troubleshooting)

        Returns:
            Hypothetical document text
        """
        # Select prompt based on query type
        prompt_map = {
            "code": CODE_HYDE_PROMPT,
            "concept": CONCEPT_HYDE_PROMPT,
            "troubleshooting": TROUBLESHOOTING_HYDE_PROMPT,
        }

        prompt_template = prompt_map.get(query_type, CODE_HYDE_PROMPT)
        prompt = prompt_template.format(query=query)

        try:
            # Generate hypothetical document
            hypothetical_doc = await self.llm.generate(
                prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            logger.info(
                "hyde_generation_success",
                query_len=len(query),
                doc_len=len(hypothetical_doc),
                query_type=query_type,
            )

            return hypothetical_doc.strip()

        except Exception as e:
            logger.warning(
                "hyde_generation_failed",
                error=str(e),
                query=query[:100],
            )
            # Fallback: return original query
            return query

    async def generate_multiple_hypotheses(
        self,
        query: str,
        query_type: str = "code",
    ) -> list[str]:
        """
        Generate multiple hypothetical documents.

        Args:
            query: User query
            query_type: Query type

        Returns:
            List of hypothetical documents
        """
        hypotheses = []

        for _i in range(self.num_hypotheses):
            doc = await self.generate_hypothetical_document(query, query_type)
            hypotheses.append(doc)

        logger.info(
            "hyde_multi_generation",
            num_hypotheses=len(hypotheses),
            avg_length=sum(len(h) for h in hypotheses) / len(hypotheses),
        )

        return hypotheses

    async def get_hyde_embeddings(
        self,
        query: str,
        query_type: str = "code",
    ) -> list[list[float]]:
        """
        Generate HyDE embeddings for retrieval.

        Args:
            query: User query
            query_type: Query type

        Returns:
            List of embedding vectors (one per hypothesis)
        """
        hypotheses = await self.generate_multiple_hypotheses(query, query_type)

        embeddings = []
        for hyp in hypotheses:
            try:
                emb = await self.embedding.embed(hyp)
                embeddings.append(emb)
            except Exception as e:
                logger.warning(
                    "hyde_embedding_failed",
                    error=str(e),
                    hypothesis_len=len(hyp),
                )
                # Skip failed embeddings
                continue

        if not embeddings:
            # Fallback: embed original query
            logger.warning("hyde_all_failed_fallback_to_query")
            original_emb = await self.embedding.embed(query)
            embeddings.append(original_emb)

        return embeddings


class HyDEQueryProcessor:
    """
    Query processor that uses HyDE for enhanced retrieval.

    Wraps vector search to use HyDE embeddings instead of direct query embedding.
    """

    def __init__(
        self,
        hyde_generator: HyDEGenerator,
        enable_hyde: bool = True,
        hyde_threshold: float = 0.7,
    ):
        """
        Initialize HyDE query processor.

        Args:
            hyde_generator: HyDE generator instance
            enable_hyde: Enable/disable HyDE (for A/B testing)
            hyde_threshold: Confidence threshold for using HyDE (0-1)
        """
        self.hyde = hyde_generator
        self.enable_hyde = enable_hyde
        self.hyde_threshold = hyde_threshold

    def should_use_hyde(self, query: str, query_complexity: float = 0.5) -> bool:
        """
        Determine if HyDE should be used for this query.

        HyDE works best for:
        - Abstract/conceptual queries
        - "How does X work?" questions
        - Troubleshooting scenarios

        Less useful for:
        - Exact keyword searches
        - Symbol/function name lookups
        - Very specific technical terms

        Args:
            query: User query
            query_complexity: Estimated query complexity (0-1)

        Returns:
            Whether to use HyDE
        """
        if not self.enable_hyde:
            return False

        # Simple heuristic: use HyDE for complex queries
        # TODO: Use intent classifier for better decision
        is_complex = query_complexity >= self.hyde_threshold

        # Heuristics for code search
        is_question = any(q in query.lower() for q in ["how", "what", "why", "when", "where"])
        has_quotes = '"' in query or "'" in query  # Exact match - skip HyDE
        is_short = len(query.split()) < 3  # Too short - skip HyDE

        use_hyde = is_complex or (is_question and not has_quotes and not is_short)

        logger.debug(
            "hyde_decision",
            use_hyde=use_hyde,
            complexity=query_complexity,
            is_question=is_question,
            query_len=len(query),
        )

        return use_hyde

    async def process_query(
        self,
        query: str,
        query_type: str = "code",
        query_complexity: float = 0.5,
    ) -> dict[str, Any]:
        """
        Process query with optional HyDE.

        Args:
            query: User query
            query_type: Query type (code/concept/troubleshooting)
            query_complexity: Estimated complexity (0-1)

        Returns:
            Dict with:
                - use_hyde: bool
                - embeddings: list[list[float]]
                - hypotheses: list[str] (if HyDE used)
        """
        use_hyde = self.should_use_hyde(query, query_complexity)

        if use_hyde:
            # Generate HyDE embeddings
            embeddings = await self.hyde.get_hyde_embeddings(query, query_type)
            hypotheses = await self.hyde.generate_multiple_hypotheses(query, query_type)

            return {
                "use_hyde": True,
                "embeddings": embeddings,
                "hypotheses": hypotheses,
                "original_query": query,
            }
        else:
            # Use original query embedding
            original_emb = await self.hyde.embedding.embed(query)

            return {
                "use_hyde": False,
                "embeddings": [original_emb],
                "hypotheses": [],
                "original_query": query,
            }
