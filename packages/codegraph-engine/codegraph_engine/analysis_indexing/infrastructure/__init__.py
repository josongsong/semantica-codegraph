"""
Indexing Orchestration

Orchestrates the complete indexing pipeline from parsing to indexing.
"""

from typing import TYPE_CHECKING

from codegraph_engine.analysis_indexing.infrastructure.change_detector import ChangeDetector, ChangeSet
from codegraph_engine.analysis_indexing.infrastructure.conflict_registry import ConflictRegistry, ConflictStrategy
from codegraph_engine.analysis_indexing.infrastructure.content_hash_checker import (
    ContentHashChecker,
    HashStore,
    InMemoryHashStore,
    RedisHashStore,
)
from codegraph_engine.analysis_indexing.infrastructure.file_discovery import FileDiscovery
from codegraph_engine.analysis_indexing.infrastructure.file_watcher import FileWatcher, MultiRepoFileWatcher
from codegraph_engine.analysis_indexing.infrastructure.git_helper import GitHelper
from codegraph_engine.analysis_indexing.infrastructure.models import (
    IndexingConfig,
    IndexingResult,
    IndexingStage,
    IndexingStatus,
    StageProgress,
)
from codegraph_engine.analysis_indexing.infrastructure.models.job import (
    IndexJob,
    IndexJobCheckpoint,
    JobProgress,
    JobStatus,
    TriggerType,
)
from codegraph_engine.analysis_indexing.infrastructure.scope_expander import ScopeExpander
from codegraph_engine.analysis_indexing.infrastructure.snapshot_gc import (
    SnapshotGarbageCollector,
    SnapshotRetentionPolicy,
)
from codegraph_engine.analysis_indexing.infrastructure.watcher_debouncer import EventDebouncer, FileEvent, FileEventType
from codegraph_engine.analysis_indexing.infrastructure.watcher_service import FileWatcherService, create_watcher_service

if TYPE_CHECKING:
    from codegraph_engine.analysis_indexing.infrastructure.job_orchestrator import IndexJobOrchestrator
    from codegraph_engine.analysis_indexing.infrastructure.orchestrator import IndexingOrchestrator
    from codegraph_engine.analysis_indexing.infrastructure.orchestrator_slim import IndexingOrchestratorSlim


def __getattr__(name: str):
    """Lazy import for heavy orchestrator classes."""
    if name == "IndexingOrchestrator":
        from codegraph_engine.analysis_indexing.infrastructure.orchestrator import IndexingOrchestrator

        return IndexingOrchestrator
    if name == "IndexingOrchestratorSlim":
        from codegraph_engine.analysis_indexing.infrastructure.orchestrator_slim import IndexingOrchestratorSlim

        return IndexingOrchestratorSlim
    if name == "IndexJobOrchestrator":
        from codegraph_engine.analysis_indexing.infrastructure.job_orchestrator import IndexJobOrchestrator

        return IndexJobOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Orchestrators (heavy - lazy import via TYPE_CHECKING)
    "IndexingOrchestrator",
    "IndexingOrchestratorSlim",  # SOTA Slim version
    "IndexJobOrchestrator",
    # Conflict Resolution (lightweight)
    "ConflictRegistry",
    "ConflictStrategy",
    # Models (lightweight)
    "IndexingConfig",
    "IndexingResult",
    "IndexingStatus",
    "IndexingStage",
    "StageProgress",
    # Job Models (lightweight)
    "IndexJob",
    "JobStatus",
    "TriggerType",
    "IndexJobCheckpoint",
    "JobProgress",
    # Change Detection
    "ChangeDetector",
    "ChangeSet",
    # File Watcher (Watchdog)
    "FileWatcher",
    "MultiRepoFileWatcher",
    "FileWatcherService",
    "create_watcher_service",
    # Event Debouncing
    "EventDebouncer",
    "FileEvent",
    "FileEventType",
    # Content Hash Checking
    "ContentHashChecker",
    "HashStore",
    "InMemoryHashStore",
    "RedisHashStore",
    # Scope Expansion
    "ScopeExpander",
    # Snapshot GC (NEW)
    "SnapshotGarbageCollector",
    "SnapshotRetentionPolicy",
    # Utilities (lightweight)
    "FileDiscovery",
    "GitHelper",
]
