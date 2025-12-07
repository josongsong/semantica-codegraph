"""
Retriever Module

Provides unified interface for code retrieval across multiple implementations.

Usage:
    from src.contexts.retrieval_search.infrastructure import (
        RetrieverFactory, RetrieverType, RetrieverConfig
    )

    # Create factory with DI container
    factory = RetrieverFactory(container)

    # Get default retriever (V3)
    retriever = factory.create()

    # With custom config
    config = RetrieverConfig(token_budget=8000, enable_cache=True)
    retriever = factory.create(RetrieverType.V3, config)

    # Execute retrieval
    result = await retriever.retrieve(
        repo_id="my-repo",
        snapshot_id="abc123",
        query="How does authentication work?"
    )

    # Access results
    print(f"Found {result.total_results} chunks")
    print(f"Intent: {result.intent} (confidence: {result.confidence})")
    for chunk in result.chunks:
        print(f"  - {chunk['file_path']}: {chunk['score']:.3f}")

Available Retriever Types:
    - BASIC: Simple multi-index fusion
    - OPTIMIZED: With caching, reranking, contextual expansion
    - V3: Latest with intent-aware fusion, consensus scoring
    - MULTI_HOP: Follows relationships across code
    - REASONING: Test-time compute, self-verification
"""

from src.contexts.retrieval_search.infrastructure.factory import (
    OptimizationLevel,
    RetrieverConfig,
    RetrieverFactory,
    RetrieverProtocol,
    RetrieverType,
    UnifiedRetrievalResult,
)

__all__ = [
    # Main factory
    "RetrieverFactory",
    # Types and config
    "RetrieverType",
    "RetrieverConfig",
    "OptimizationLevel",
    # Protocol and result
    "RetrieverProtocol",
    "UnifiedRetrievalResult",
]
