"""
Git History Analysis

Provides git history analysis for code intelligence:
- Git blame (authorship tracking)
- Code churn metrics (change frequency)
- Co-change patterns (files that change together)
- Evolution tracking (how code evolves over time)
- GitService: Main service for git operations
- GitHistoryEnrichmentHook: Chunk update hook for automatic enrichment
"""

from .blame import BlameInfo, GitBlameAnalyzer
from .churn import ChurnAnalyzer, ChurnMetrics
from .cochange import CoChangeAnalyzer, CoChangePattern
from .enrichment import GitHistoryEnrichmentHook, create_enrichment_hook
from .evolution import EvolutionSnapshot, EvolutionTracker
from .git_service import GitService, create_git_service
from .models import (
    AuthorContribution,
    ChangeType,
    ChunkChurnMetrics,
    ChunkEvolutionSnapshot,
    ChunkHistory,
    FileHistory,
    GitBlame,
    GitCommit,
    HotspotAnalysis,
    HotspotReason,
)

__all__ = [
    # Services
    "GitService",
    "create_git_service",
    "GitHistoryEnrichmentHook",
    "create_enrichment_hook",
    # Analyzers
    "GitBlameAnalyzer",
    "BlameInfo",
    "ChurnAnalyzer",
    "ChurnMetrics",
    "CoChangeAnalyzer",
    "CoChangePattern",
    "EvolutionTracker",
    "EvolutionSnapshot",
    # Models
    "GitCommit",
    "FileHistory",
    "ChunkHistory",
    "GitBlame",
    "ChunkChurnMetrics",
    "AuthorContribution",
    "ChunkEvolutionSnapshot",
    "HotspotAnalysis",
    # Enums
    "ChangeType",
    "HotspotReason",
]
