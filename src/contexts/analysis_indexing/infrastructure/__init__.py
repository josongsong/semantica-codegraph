"""
Indexing Orchestration

Orchestrates the complete indexing pipeline from parsing to indexing.
"""

from typing import TYPE_CHECKING

from src.contexts.analysis_indexing.infrastructure.change_detector import ChangeDetector, ChangeSet
from src.contexts.analysis_indexing.infrastructure.conflict_registry import ConflictRegistry, ConflictStrategy
from src.contexts.analysis_indexing.infrastructure.content_hash_checker import (
    ContentHashChecker,
    HashStore,
    InMemoryHashStore,
    RedisHashStore,
)
from src.contexts.analysis_indexing.infrastructure.file_discovery import FileDiscovery
from src.contexts.analysis_indexing.infrastructure.file_watcher import FileWatcher, MultiRepoFileWatcher
from src.contexts.analysis_indexing.infrastructure.git_helper import GitHelper
from src.contexts.analysis_indexing.infrastructure.models import (
    IndexingConfig,
    IndexingResult,
    IndexingStage,
    IndexingStatus,
    StageProgress,
)
from src.contexts.analysis_indexing.infrastructure.models.job import (
    IndexJob,
    IndexJobCheckpoint,
    JobProgress,
    JobStatus,
    TriggerType,
)
from src.contexts.analysis_indexing.infrastructure.scope_expander import ScopeExpander
from src.contexts.analysis_indexing.infrastructure.snapshot_gc import SnapshotGarbageCollector, SnapshotRetentionPolicy
from src.contexts.analysis_indexing.infrastructure.watcher_debouncer import EventDebouncer, FileEvent, FileEventType
from src.contexts.analysis_indexing.infrastructure.watcher_service import FileWatcherService, create_watcher_service

if TYPE_CHECKING:
    from src.contexts.analysis_indexing.infrastructure.job_orchestrator import IndexJobOrchestrator
    from src.contexts.analysis_indexing.infrastructure.orchestrator import IndexingOrchestrator


def __getattr__(name: str):
    """Lazy import for heavy orchestrator classes."""
    if name == "IndexingOrchestrator":
        from src.contexts.analysis_indexing.infrastructure.orchestrator import IndexingOrchestrator

        return IndexingOrchestrator
    if name == "IndexJobOrchestrator":
        from src.contexts.analysis_indexing.infrastructure.job_orchestrator import IndexJobOrchestrator

        return IndexJobOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Orchestrators (heavy - lazy import via TYPE_CHECKING)
    "IndexingOrchestrator",
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
