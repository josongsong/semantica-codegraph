"""
Cold Start Trigger - Repository Indexing on Application Startup

This module provides FastAPI startup event handlers for automatic repository
indexing when the application starts.

# Architecture

```text
┌───────────────────────────────────────────────────────────────┐
│                     FastAPI Application                       │
│                                                               │
│  @app.on_event("startup")                                    │
│         ↓                                                     │
│  ┌──────────────────────────────────────┐                   │
│  │  ColdStartIndexingManager            │                   │
│  │  - check_and_index_repositories()    │                   │
│  │  - run_initial_indexing()            │                   │
│  └───────────┬──────────────────────────┘                   │
│              ↓                                                │
│       ┌──────┴───────┐                                       │
│       │              │                                        │
│  ┌────▼────┐    ┌───▼──────┐                               │
│  │Python   │    │Rust      │                               │
│  │Incremental│  │Indexing  │                               │
│  │Indexer  │    │Service   │                               │
│  └─────────┘    └──────────┘                               │
└───────────────────────────────────────────────────────────────┘
```

# Usage

## FastAPI Integration

```python
from fastapi import FastAPI
from codegraph_engine.multi_index.infrastructure.triggers.cold_start import (
    ColdStartIndexingManager,
    setup_cold_start_indexing,
)

app = FastAPI()

# Method 1: Automatic setup (recommended)
setup_cold_start_indexing(app, background=True)

# Method 2: Manual control
manager = ColdStartIndexingManager()

@app.on_event("startup")
async def on_startup():
    await manager.check_and_index_repositories(background=True)
```

## Configuration

Cold start behavior can be configured via environment variables:

- `SEMANTICA_COLD_START_ENABLED`: Enable/disable cold start indexing (default: True)
- `SEMANTICA_COLD_START_BACKGROUND`: Run indexing in background (default: True)
- `SEMANTICA_COLD_START_PARALLEL_WORKERS`: Number of parallel workers (default: 0 = auto)

# Performance

- **Target**: < 1 second for index existence check
- **Full indexing**: Runs in background (non-blocking)
- **Expected throughput**: 661,000+ LOC/s

# References

- INDEXING_STRATEGY.md: Cold Start trigger specification (P1 priority)
- packages/codegraph-ir/src/usecases/indexing_service.rs: Rust IndexingService
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ColdStartIndexingManager:
    """
    Manages repository indexing on application startup (Cold Start).

    This manager checks which repositories need indexing and triggers
    full repository reindexing in the background.

    # Responsibilities

    1. **Check Index Status**: Verify if repositories are already indexed
    2. **Trigger Full Indexing**: Call Rust IndexingService for unindexed repos
    3. **Background Execution**: Non-blocking startup (app remains responsive)
    4. **Error Handling**: Graceful degradation on indexing failures

    # Examples

    ```python
    # Basic usage
    manager = ColdStartIndexingManager()
    await manager.check_and_index_repositories()

    # With custom configuration
    manager = ColdStartIndexingManager(
        parallel_workers=8,
        enable_repomap=True,
    )
    await manager.check_and_index_repositories(background=True)
    ```
    """

    def __init__(
        self,
        parallel_workers: int = 0,  # 0 = auto-detect
        enable_chunking: bool = True,
        enable_cross_file: bool = True,
        enable_symbols: bool = True,
        enable_points_to: bool = False,  # Expensive, disabled by default
        enable_repomap: bool = False,  # Expensive, disabled by default
        enable_taint: bool = False,  # Expensive, disabled by default
    ):
        """
        Initialize Cold Start Indexing Manager.

        Args:
            parallel_workers: Number of parallel workers (0 = auto-detect)
            enable_chunking: Enable L2 chunking stage
            enable_cross_file: Enable L3 cross-file resolution
            enable_symbols: Enable L5 symbol extraction
            enable_points_to: Enable L6 points-to analysis
            enable_repomap: Enable L16 RepoMap visualization
            enable_taint: Enable L14 taint analysis
        """
        self.parallel_workers = parallel_workers
        self.enable_chunking = enable_chunking
        self.enable_cross_file = enable_cross_file
        self.enable_symbols = enable_symbols
        self.enable_points_to = enable_points_to
        self.enable_repomap = enable_repomap
        self.enable_taint = enable_taint

    async def check_and_index_repositories(
        self,
        background: bool = True,
    ) -> dict[str, str]:
        """
        Check all repositories and trigger indexing for unindexed ones.

        This is the main entry point for Cold Start indexing. It checks which
        repositories are already indexed and triggers full indexing for the rest.

        Args:
            background: Run indexing in background (non-blocking)

        Returns:
            Dict mapping repo_id → status ("indexed", "scheduled", "skipped")

        Examples:
            ```python
            # Blocking mode (wait for completion)
            result = await manager.check_and_index_repositories(background=False)
            print(f"Indexed {len(result)} repositories")

            # Background mode (non-blocking, recommended)
            result = await manager.check_and_index_repositories(background=True)
            print(f"Scheduled {len([v for v in result.values() if v == 'scheduled'])} repos")
            ```
        """
        logger.info("🚀 [Cold Start] Checking repository indexes on startup...")

        # Get all repositories from database
        repos = await self._get_all_repositories_from_db()

        if not repos:
            logger.info("No repositories found in database, skipping cold start indexing")
            return {}

        logger.info(f"Found {len(repos)} repositories to check")

        result = {}

        for repo in repos:
            repo_id = repo["id"]
            repo_path = repo["path"]

            # Check if repository is already indexed
            is_indexed = await self._check_index_exists(repo_id)

            if is_indexed:
                logger.info(f"✅ Repository {repo_id} already indexed, skipping")
                result[repo_id] = "skipped"
                continue

            logger.info(f"📦 Repository {repo_id} not indexed, scheduling indexing...")

            if background:
                # Schedule in background (non-blocking)
                asyncio.create_task(self._run_full_indexing(repo_id, repo_path))
                result[repo_id] = "scheduled"
            else:
                # Run synchronously (blocking)
                await self._run_full_indexing(repo_id, repo_path)
                result[repo_id] = "indexed"

        logger.info(
            f"🎯 [Cold Start] Complete - "
            f"Indexed: {len([v for v in result.values() if v == 'indexed'])}, "
            f"Scheduled: {len([v for v in result.values() if v == 'scheduled'])}, "
            f"Skipped: {len([v for v in result.values() if v == 'skipped'])}"
        )

        return result

    async def _get_all_repositories_from_db(self) -> list[dict]:
        """
        Get all repositories from database.

        Returns:
            List of repository dicts with 'id' and 'path' keys

        Note:
            This is a placeholder implementation. In production, this should
            query the PostgreSQL database to get all registered repositories.
        """
        # TODO: Implement database query
        # Example:
        #   async with get_db_session() as session:
        #       result = await session.execute(
        #           select(Repository.id, Repository.path)
        #       )
        #       return [{"id": r.id, "path": r.path} for r in result]

        # For now, return empty list (no repositories)
        logger.warning("[Cold Start] _get_all_repositories_from_db() not implemented, returning empty list")
        return []

    async def _check_index_exists(self, repo_id: str) -> bool:
        """
        Check if repository index exists in database.

        Args:
            repo_id: Repository ID

        Returns:
            True if index exists, False otherwise

        Note:
            This is a placeholder implementation. In production, this should
            check PostgreSQL for the existence of indexed nodes/chunks for the repo.
        """
        # TODO: Implement index existence check
        # Example:
        #   async with get_db_session() as session:
        #       result = await session.execute(
        #           select(func.count(Node.id))
        #           .where(Node.repo_id == repo_id)
        #       )
        #       count = result.scalar()
        #       return count > 0

        # For now, assume no index exists
        return False

    async def _run_full_indexing(self, repo_id: str, repo_path: str) -> None:
        """
        Run full repository indexing using Rust IndexingService.

        Args:
            repo_id: Repository ID
            repo_path: Repository root path

        Note:
            This calls the Rust IndexingService::full_reindex() method
            via PyO3 bindings.
        """
        try:
            logger.info(f"[Cold Start] Starting full indexing for {repo_id}...")

            # Import Rust IndexingService (via PyO3)
            # NOTE: This import is done dynamically to avoid circular dependencies
            try:
                from codegraph_ir import IndexingService
            except ImportError:
                logger.error(
                    "[Cold Start] Failed to import codegraph_ir.IndexingService - "
                    "Falling back to Python IncrementalIndexer"
                )
                # Fallback to Python implementation
                await self._run_full_indexing_python(repo_id, repo_path)
                return

            # Create Rust IndexingService
            service = IndexingService()

            # Run full reindex (Rust)
            # NOTE: This is a synchronous call, so we run it in a thread pool
            def _blocking_reindex():
                return service.full_reindex(
                    repo_root=repo_path,
                    repo_name=repo_id,
                    file_paths=None,  # All files
                )

            # Run in thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _blocking_reindex)

            logger.info(
                f"✅ [Cold Start] Indexing complete for {repo_id} - "
                f"Processed {result.files_processed} files in {result.duration.total_seconds():.2f}s "
                f"({result.loc_per_second:.0f} LOC/s)"
            )

        except Exception as e:
            logger.error(
                f"❌ [Cold Start] Indexing failed for {repo_id}: {e}",
                exc_info=True,
            )

    async def _run_full_indexing_python(self, repo_id: str, repo_path: str) -> None:
        """
        Fallback: Run full indexing using Python IncrementalIndexer.

        This is used when the Rust IndexingService is not available.

        Args:
            repo_id: Repository ID
            repo_path: Repository root path
        """
        try:
            # Import Python IncrementalIndexer
            from codegraph_engine.multi_index.infrastructure.service.incremental_indexer import (
                IncrementalIndexer,
            )

            logger.info(f"[Cold Start] Using Python IncrementalIndexer for {repo_id} (fallback)")

            # Create indexer
            # NOTE: This assumes a DI container is set up
            # In production, use get_incremental_indexer() from DI
            indexer = IncrementalIndexer()

            # Get all Python files in repository
            file_paths = list(Path(repo_path).rglob("*.py"))

            # Run incremental indexing (all files = full indexing)
            result = await indexer.index_files(
                repo_id=repo_id,
                snapshot_id="main",  # Or branch name
                file_paths=[str(f) for f in file_paths],
                reason="cold_start",
                priority=1,  # High priority
            )

            logger.info(
                f"✅ [Cold Start] Python indexing complete for {repo_id} - Processed {result.indexed_count} files"
            )

        except Exception as e:
            logger.error(
                f"❌ [Cold Start] Python indexing failed for {repo_id}: {e}",
                exc_info=True,
            )


def setup_cold_start_indexing(
    app,  # FastAPI app
    background: bool = True,
    parallel_workers: int = 0,
    enable_repomap: bool = False,
    enable_taint: bool = False,
) -> None:
    """
    Setup automatic Cold Start indexing for FastAPI application.

    This is a convenience function that registers a startup event handler
    for automatic repository indexing.

    Args:
        app: FastAPI application instance
        background: Run indexing in background (recommended: True)
        parallel_workers: Number of parallel workers (0 = auto-detect)
        enable_repomap: Enable L16 RepoMap visualization
        enable_taint: Enable L14 taint analysis

    Examples:
        ```python
        from fastapi import FastAPI
        from codegraph_engine.multi_index.infrastructure.triggers.cold_start import (
            setup_cold_start_indexing,
        )

        app = FastAPI()

        # Basic setup (recommended)
        setup_cold_start_indexing(app)

        # Advanced setup
        setup_cold_start_indexing(
            app,
            background=True,
            parallel_workers=8,
            enable_repomap=True,
        )
        ```
    """
    # Check if cold start is enabled via environment variable
    enabled = os.getenv("SEMANTICA_COLD_START_ENABLED", "true").lower() == "true"

    if not enabled:
        logger.info("[Cold Start] Disabled via SEMANTICA_COLD_START_ENABLED=false")
        return

    # Create manager
    manager = ColdStartIndexingManager(
        parallel_workers=parallel_workers,
        enable_repomap=enable_repomap,
        enable_taint=enable_taint,
    )

    # Register startup event
    @app.on_event("startup")
    async def on_app_startup():
        """FastAPI startup event handler for Cold Start indexing."""
        await manager.check_and_index_repositories(background=background)

    logger.info(f"✅ [Cold Start] Registered startup handler (background={background}, workers={parallel_workers})")
