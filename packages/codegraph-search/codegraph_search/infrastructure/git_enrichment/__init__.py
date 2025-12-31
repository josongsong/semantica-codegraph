"""
Git History Enrichment for Retrieval

Integrates git history metrics into search results for better ranking.
"""

from codegraph_search.infrastructure.git_enrichment.adapter import GitHistoryAdapter
from codegraph_search.infrastructure.git_enrichment.ranker import GitAwareRanker

__all__ = ["GitHistoryAdapter", "GitAwareRanker"]
