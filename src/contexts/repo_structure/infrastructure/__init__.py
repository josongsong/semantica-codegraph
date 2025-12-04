"""
RepoMap Layer

Project structure map with importance metrics and summaries.

RepoMap extends Chunk hierarchy with:
- Tree structure visualization
- Importance metrics (PageRank, LOC, change frequency)
- LLM summaries for navigation
- Query interface for exploration

Usage:
    # Build RepoMap
    builder = RepoMapBuilder(store, config)
    snapshot = builder.build(repo_id, snapshot_id, chunks)

    # Query RepoMap
    query = RepoMapQuery(store)
    top_nodes = query.get_top_nodes(repo_id, snapshot_id, top_n=20)
"""

from typing import TYPE_CHECKING

from src.contexts.repo_structure.infrastructure.git_history import GitHistoryAnalyzer
from src.contexts.repo_structure.infrastructure.id_strategy import RepoMapIdGenerator
from src.contexts.repo_structure.infrastructure.incremental import RepoMapIncrementalUpdater
from src.contexts.repo_structure.infrastructure.models import (
    RepoMapBuildConfig,
    RepoMapMetrics,
    RepoMapNode,
    RepoMapSnapshot,
)
from src.contexts.repo_structure.infrastructure.pagerank import (
    AggregationStrategy,
    GraphAdapter,
)
from src.contexts.repo_structure.infrastructure.storage import (
    InMemoryRepoMapStore,
    JsonFileRepoMapStore,
    RepoMapStore,
)
from src.contexts.repo_structure.infrastructure.summarizer import (
    CostController,
    InMemorySummaryCache,
    SummaryCache,
    SummaryCostConfig,
    SummaryPromptTemplate,
)
from src.contexts.repo_structure.infrastructure.tree import (
    EntrypointDetector,
    HeuristicMetricsCalculator,
    TestDetector,
)

if TYPE_CHECKING:
    from src.contexts.repo_structure.infrastructure.builder import RepoMapBuilder, RepoMapQuery
    from src.contexts.repo_structure.infrastructure.pagerank import PageRankAggregator, PageRankEngine
    from src.contexts.repo_structure.infrastructure.storage import PostgresRepoMapStore
    from src.contexts.repo_structure.infrastructure.summarizer import LLMSummarizer
    from src.contexts.repo_structure.infrastructure.tree import RepoMapTreeBuilder


def __getattr__(name: str):
    """Lazy import for heavy classes."""
    if name == "RepoMapBuilder":
        from src.contexts.repo_structure.infrastructure.builder import RepoMapBuilder

        return RepoMapBuilder
    if name == "RepoMapQuery":
        from src.contexts.repo_structure.infrastructure.builder import RepoMapQuery

        return RepoMapQuery
    if name == "PageRankEngine":
        from src.contexts.repo_structure.infrastructure.pagerank import PageRankEngine

        return PageRankEngine
    if name == "PageRankAggregator":
        from src.contexts.repo_structure.infrastructure.pagerank import PageRankAggregator

        return PageRankAggregator
    if name == "PostgresRepoMapStore":
        from src.contexts.repo_structure.infrastructure.storage import PostgresRepoMapStore

        return PostgresRepoMapStore
    if name == "LLMSummarizer":
        from src.contexts.repo_structure.infrastructure.summarizer import LLMSummarizer

        return LLMSummarizer
    if name == "RepoMapTreeBuilder":
        from src.contexts.repo_structure.infrastructure.tree import RepoMapTreeBuilder

        return RepoMapTreeBuilder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Models (lightweight)
    "RepoMapNode",
    "RepoMapSnapshot",
    "RepoMapMetrics",
    "RepoMapBuildConfig",
    # Builder (heavy - lazy import via TYPE_CHECKING)
    "RepoMapBuilder",
    "RepoMapQuery",
    "RepoMapIncrementalUpdater",
    "GitHistoryAnalyzer",
    # Tree (heavy - lazy import via TYPE_CHECKING)
    "RepoMapTreeBuilder",
    "HeuristicMetricsCalculator",
    "EntrypointDetector",
    "TestDetector",
    # PageRank (heavy - lazy import via TYPE_CHECKING)
    "PageRankEngine",
    "PageRankAggregator",
    "GraphAdapter",
    "AggregationStrategy",
    # Summarizer (heavy - lazy import via TYPE_CHECKING)
    "LLMSummarizer",
    "SummaryCache",
    "InMemorySummaryCache",
    "CostController",
    "SummaryCostConfig",
    "SummaryPromptTemplate",
    # Storage (PostgreSQL heavy - lazy import via TYPE_CHECKING)
    "RepoMapStore",
    "InMemoryRepoMapStore",
    "JsonFileRepoMapStore",
    "PostgresRepoMapStore",  # DEPRECATED
    # Utils (lightweight)
    "RepoMapIdGenerator",
]
