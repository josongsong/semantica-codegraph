"""
Indexing Triggers Module

This module provides various triggers for repository indexing:

1. **Watch Mode** - Real-time file change detection (P0 - Complete ✅)
2. **Git Hooks** - Post-commit indexing (P2 - Not implemented)
3. **Scheduler** - Periodic full reindexing (P2 - Partial)
4. **Manual Trigger** - API-triggered indexing (P1 - Not implemented)
5. **Cold Start** - Application startup indexing (P1 - Complete ✅)

# Usage

## Cold Start (Application Startup)

```python
from fastapi import FastAPI
from codegraph_engine.multi_index.infrastructure.triggers import setup_cold_start_indexing

app = FastAPI()
setup_cold_start_indexing(app, background=True)
```

## Watch Mode (File System Monitoring)

```python
from codegraph_engine.multi_index.infrastructure.triggers import FileWatcherManager

manager = FileWatcherManager()
await manager.watch_repository(repo_id="my_repo", repo_path="/path/to/repo")
```

# Implementation Status

- ✅ **Watch Mode**: Complete (FileWatcherManager, IntelligentDebouncer, RateLimiter)
- ✅ **Cold Start**: Complete (ColdStartIndexingManager, setup_cold_start_indexing)
- ⚠️ **Scheduler**: Partial (compaction only, needs full reindex scheduler)
- ❌ **Git Hooks**: Not implemented (needs post-commit script + API endpoint)
- ❌ **Manual Trigger**: Not implemented (needs API endpoints)

# References

- [INDEXING_STRATEGY.md](../../../../../../docs/INDEXING_STRATEGY.md) - Complete trigger specification
- [FILE_WATCHER_GUIDE.md](../../../../../../docs/FILE_WATCHER_GUIDE.md) - Watch Mode documentation
"""

# Cold Start trigger
from .cold_start import ColdStartIndexingManager, setup_cold_start_indexing

# Watch Mode trigger (already implemented)
from ..watch import (
    FileChangeEvent,
    FileWatcherManager,
    IncrementalIndexEventHandler,
    IntelligentDebouncer,
    RateLimiter,
    RepoWatcher,
    WatchConfig,
)

__all__ = [
    # Cold Start
    "ColdStartIndexingManager",
    "setup_cold_start_indexing",
    # Watch Mode
    "FileChangeEvent",
    "FileWatcherManager",
    "IncrementalIndexEventHandler",
    "IntelligentDebouncer",
    "RateLimiter",
    "RepoWatcher",
    "WatchConfig",
]
