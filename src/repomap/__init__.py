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

from .builder import RepoMapBuilder, RepoMapQuery
from .git_history import GitHistoryAnalyzer
from .id_strategy import RepoMapIdGenerator
from .incremental import RepoMapIncrementalUpdater
from .models import (
    RepoMapBuildConfig,
    RepoMapMetrics,
    RepoMapNode,
    RepoMapSnapshot,
)
from .pagerank import (
    AggregationStrategy,
    GraphAdapter,
    PageRankAggregator,
    PageRankEngine,
)
from .storage import InMemoryRepoMapStore, PostgresRepoMapStore, RepoMapStore
from .summarizer import (
    CostController,
    InMemorySummaryCache,
    LLMSummarizer,
    SummaryCache,
    SummaryCostConfig,
    SummaryPromptTemplate,
)
from .tree import (
    EntrypointDetector,
    HeuristicMetricsCalculator,
    RepoMapTreeBuilder,
    TestDetector,
)

__all__ = [
    # Models
    "RepoMapNode",
    "RepoMapSnapshot",
    "RepoMapMetrics",
    "RepoMapBuildConfig",
    # Builder
    "RepoMapBuilder",
    "RepoMapQuery",
    "RepoMapIncrementalUpdater",
    "GitHistoryAnalyzer",
    # Tree
    "RepoMapTreeBuilder",
    "HeuristicMetricsCalculator",
    "EntrypointDetector",
    "TestDetector",
    # PageRank
    "PageRankEngine",
    "PageRankAggregator",
    "GraphAdapter",
    "AggregationStrategy",
    # Summarizer
    "LLMSummarizer",
    "SummaryCache",
    "InMemorySummaryCache",
    "CostController",
    "SummaryCostConfig",
    "SummaryPromptTemplate",
    # Storage
    "RepoMapStore",
    "InMemoryRepoMapStore",
    "PostgresRepoMapStore",
    # Utils
    "RepoMapIdGenerator",
]
