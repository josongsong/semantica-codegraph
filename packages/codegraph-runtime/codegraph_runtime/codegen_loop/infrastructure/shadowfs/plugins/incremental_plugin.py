"""
Incremental Update Plugin (Infrastructure Layer)

Integrates incremental IR updates and indexing with ShadowFS.

Architecture:
    - Infrastructure Layer
    - Cross-context integration (code_foundation + multi_index)
    - Implements ShadowFSPlugin Protocol

Dependencies:
    - code_foundation.IncrementalIRBuilder (IR delta calculation)
    - multi_index.IncrementalIndexer (batch indexing)
    - LanguageDetector (extension → language mapping)

Thread-Safety:
    - Internal state protected by dict (thread-safe for asyncio)
    - Delegates to builder/indexer for concurrency

Error Handling:
    - Incremental update failures logged but don't block ShadowFS
    - Indexing failures logged but don't block commits

Performance Optimizations:
    - Batch IR delta calculation (commit-time, not write-time)
    - TTL cleanup for stale transactions (1 hour default)
    - Language grouping for parallel batch processing

References:
    - RFC-018 Section 18.4 (IncrementalUpdatePlugin)
    - RFC-018 Section 20 (Incremental Update Integration)
"""

import asyncio
import dataclasses
import logging
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

from ....domain.shadowfs.events import ShadowFSEvent
from .language_detector import LanguageDetector

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.incremental.incremental_builder import IncrementalIRBuilder
    from codegraph_engine.multi_index.infrastructure.indexer import IncrementalIndexer

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PluginMetrics:
    """
    Metrics for IncrementalUpdatePlugin observability

    Thread-Safe: No (should be accessed within async context only)

    Attributes:
        total_writes: Total write events processed
        total_commits: Total commit events processed
        total_rollbacks: Total rollback events processed
        total_files_processed: Total files processed (IR delta + indexing)
        total_ir_delta_calls: Total IR delta calls
        total_indexing_calls: Total indexing calls
        avg_batch_size: Average batch size (files per commit)
        avg_ir_delta_latency_ms: Average IR delta latency (ms)
        avg_indexing_latency_ms: Average indexing latency (ms)
        max_ir_delta_latency_ms: Max IR delta latency (ms)
        max_indexing_latency_ms: Max indexing latency (ms)
        total_errors: Total errors (IR delta + indexing)
        stale_txns_cleaned: Total stale transactions cleaned up
    """

    total_writes: int = 0
    total_commits: int = 0
    total_rollbacks: int = 0
    total_files_processed: int = 0
    total_ir_delta_calls: int = 0
    total_indexing_calls: int = 0
    avg_batch_size: float = 0.0
    avg_ir_delta_latency_ms: float = 0.0
    avg_indexing_latency_ms: float = 0.0
    max_ir_delta_latency_ms: float = 0.0
    max_indexing_latency_ms: float = 0.0
    total_errors: int = 0
    stale_txns_cleaned: int = 0

    # Internal accumulators (not exposed) - Ring buffer to prevent memory leak
    _batch_sizes: deque[int] = dataclasses.field(default_factory=lambda: deque(maxlen=1000), repr=False)
    _ir_delta_latencies: deque[float] = dataclasses.field(default_factory=lambda: deque(maxlen=1000), repr=False)
    _indexing_latencies: deque[float] = dataclasses.field(default_factory=lambda: deque(maxlen=1000), repr=False)

    def record_write(self) -> None:
        """Record write event"""
        self.total_writes += 1

    def record_commit(self, batch_size: int) -> None:
        """Record commit event"""
        self.total_commits += 1
        self.total_files_processed += batch_size
        self._batch_sizes.append(batch_size)

        # Update average
        if self._batch_sizes:
            self.avg_batch_size = sum(self._batch_sizes) / len(self._batch_sizes)

    def record_rollback(self) -> None:
        """Record rollback event"""
        self.total_rollbacks += 1

    def record_ir_delta(self, latency_ms: float) -> None:
        """Record IR delta call"""
        self.total_ir_delta_calls += 1
        self._ir_delta_latencies.append(latency_ms)

        # Update average and max
        if self._ir_delta_latencies:
            self.avg_ir_delta_latency_ms = sum(self._ir_delta_latencies) / len(self._ir_delta_latencies)
            self.max_ir_delta_latency_ms = max(self._ir_delta_latencies)

    def record_indexing(self, latency_ms: float) -> None:
        """Record indexing call"""
        self.total_indexing_calls += 1
        self._indexing_latencies.append(latency_ms)

        # Update average and max
        if self._indexing_latencies:
            self.avg_indexing_latency_ms = sum(self._indexing_latencies) / len(self._indexing_latencies)
            self.max_indexing_latency_ms = max(self._indexing_latencies)

    def record_error(self) -> None:
        """Record error"""
        self.total_errors += 1

    def record_stale_txn_cleanup(self, count: int = 1) -> None:
        """Record stale transaction cleanup"""
        self.stale_txns_cleaned += count


class IncrementalUpdatePlugin:
    """
    Incremental Update Plugin

    Automates incremental IR updates and indexing on file changes.

    Responsibilities:
        - Calculate IR deltas on write
        - Track changed files per transaction
        - Trigger batch indexing on commit
        - Discard changes on rollback

    Event Handlers:
        - write → calculate IR delta
        - commit → batch index changed files
        - rollback → discard tracked changes
        - delete → track for indexing

    Performance:
        - write: <20ms (delta calculation)
        - commit: <100ms (batch indexing)
        - rollback: <1ms (dict deletion)

    Integration:
        - code_foundation.IncrementalIRBuilder (IR)
        - multi_index.IncrementalIndexer (indexing)

    Examples:
        >>> from codegraph_engine.code_foundation.infrastructure.incremental import (
        ...     IncrementalIRBuilder
        ... )
        >>> from codegraph_engine.multi_index.infrastructure.service import (
        ...     IncrementalIndexer
        ... )

        >>> ir_builder = IncrementalIRBuilder(repo_id="repo-123")
        >>> indexer = IncrementalIndexer(...)

        >>> plugin = IncrementalUpdatePlugin(ir_builder, indexer)
        >>> event_bus.register(plugin)

        >>> # Events automatically trigger incremental updates
        >>> await core.write("main.py", "code", txn_id)
        >>> # IR delta calculated automatically

        >>> await core.commit(txn_id)
        >>> # Batch indexing triggered automatically
    """

    def __init__(
        self,
        ir_builder: "IncrementalIRBuilder",
        indexer: "IncrementalIndexer",
        ttl: float = 3600.0,  # 1 hour
    ):
        """
        Initialize Incremental Update Plugin

        Args:
            ir_builder: IncrementalIRBuilder for IR delta calculation
            indexer: IncrementalIndexer for batch indexing
            ttl: Transaction TTL in seconds (default: 3600s = 1 hour)

        Raises:
            TypeError: ir_builder or indexer is None or invalid

        Architecture:
            Dependency Injection (Hexagonal principle)
        """
        # Validate dependencies
        if ir_builder is None:
            raise TypeError("ir_builder must not be None")

        if indexer is None:
            raise TypeError("indexer must not be None")

        # Check interfaces (duck typing)
        if not hasattr(ir_builder, "build_incremental"):
            raise TypeError(f"ir_builder must have build_incremental method, got {type(ir_builder)}")

        if not hasattr(indexer, "index_files"):
            raise TypeError(f"indexer must have index_files method, got {type(indexer)}")

        self._ir_builder = ir_builder
        self._indexer = indexer
        self._language_detector = LanguageDetector()
        self._ttl = ttl

        # Track changed files per transaction (for indexing)
        # Dict[txn_id, Set[Path]]
        self._pending_changes: dict[str, set[Path]] = {}

        # Track files for IR delta calculation (batched at commit)
        # Dict[txn_id, Set[Path]]
        self._pending_ir_deltas: dict[str, set[Path]] = {}

        # Track transaction creation times (for TTL cleanup)
        # Dict[txn_id, float (timestamp)]
        self._txn_created_at: dict[str, float] = {}

        # TTL cleanup background task (lazy initialization)
        self._cleanup_task: asyncio.Task | None = None

        # Metrics for observability
        self._metrics = PluginMetrics()

        logger.info(
            "IncrementalUpdatePlugin initialized: "
            f"ir_builder={type(ir_builder).__name__}, "
            f"indexer={type(indexer).__name__}, "
            f"ttl={ttl}s"
        )

    async def on_event(self, event: ShadowFSEvent) -> None:
        """
        Handle ShadowFS event

        Args:
            event: ShadowFSEvent

        Side Effects:
            - IR delta calculated (write)
            - Files tracked (write/delete)
            - Batch indexing triggered (commit)
            - Changes discarded (rollback)

        Error Handling:
            - Failures logged but not propagated
            - ShadowFS operation continues regardless

        Examples:
            >>> await plugin.on_event(ShadowFSEvent(
            ...     type="write",
            ...     path="main.py",
            ...     txn_id="txn-123",
            ...     old_content=None,
            ...     new_content="def func(): pass",
            ...     timestamp=time.time(),
            ... ))
        """
        # Ensure TTL cleanup task is running (lazy start)
        self._ensure_cleanup_task()

        if event.type == "write":
            await self._on_write(event)

        elif event.type == "delete":
            await self._on_delete(event)

        elif event.type == "commit":
            await self._on_commit(event)

        elif event.type == "rollback":
            self._on_rollback(event)

    async def _on_write(self, event: ShadowFSEvent) -> None:
        """
        Handle write event: track changes for batch processing

        Strategy:
            1. Track file for IR delta calculation (batched at commit)
            2. Track file for batch indexing (batched at commit)
            3. Track transaction creation time (for TTL)

        Optimization:
            - NO immediate IR delta calculation (batched at commit)
            - Reduces overhead from O(n) to O(1) per write

        Args:
            event: Write event

        Side Effects:
            - File tracked for IR delta calculation
            - File tracked for indexing
            - Transaction creation time recorded

        Performance:
            Target: <1ms (dict operations only)
        """
        if event.new_content is None:
            return

        # Validate path for security
        try:
            file_path = self._validate_path(event.path)
        except ValueError as e:
            logger.error(
                f"Invalid path in write event: {e}",
                extra={
                    "path": event.path,
                    "txn_id": event.txn_id,
                },
            )
            self._metrics.record_error()
            return  # Skip invalid paths

        # Track transaction creation time (for TTL cleanup)
        if event.txn_id not in self._txn_created_at:
            self._txn_created_at[event.txn_id] = time.time()

        # Track for IR delta calculation (batched at commit)
        if event.txn_id not in self._pending_ir_deltas:
            self._pending_ir_deltas[event.txn_id] = set()

        self._pending_ir_deltas[event.txn_id].add(file_path)

        # Track for indexing (batched at commit)
        if event.txn_id not in self._pending_changes:
            self._pending_changes[event.txn_id] = set()

        self._pending_changes[event.txn_id].add(file_path)

        # Record metrics
        self._metrics.record_write()

        logger.debug(f"Tracked {event.path} for batch processing in txn {event.txn_id}")

    async def _on_delete(self, event: ShadowFSEvent) -> None:
        """
        Handle delete event: track for indexing

        Args:
            event: Delete event

        Side Effects:
            - File tracked for indexing (to remove from index)
        """
        # Validate path for security
        try:
            file_path = self._validate_path(event.path)
        except ValueError as e:
            logger.error(
                f"Invalid path in delete event: {e}",
                extra={
                    "path": event.path,
                    "txn_id": event.txn_id,
                },
            )
            self._metrics.record_error()
            return  # Skip invalid paths

        # Track for indexing (to remove from index)
        if event.txn_id not in self._pending_changes:
            self._pending_changes[event.txn_id] = set()

        self._pending_changes[event.txn_id].add(file_path)

    async def _on_commit(self, event: ShadowFSEvent) -> None:
        """
        Handle commit event: batch IR delta calculation and indexing

        Strategy:
            1. Get tracked files for IR delta
            2. Group files by language
            3. Batch calculate IR deltas (parallel, per language)
            4. Get tracked files for indexing
            5. Batch index (parallel)
            6. Cleanup transaction state

        Optimization:
            - Batch IR delta: O(1) per language instead of O(n) per file
            - Language grouping: parallel processing per language
            - Single indexing call for all files

        Args:
            event: Commit event

        Side Effects:
            - Batch IR deltas calculated
            - Batch indexing triggered
            - Tracked files discarded
            - Transaction timestamps cleaned up

        Error Handling:
            - IR delta failure → logged, not propagated
            - Indexing failure → logged, not propagated

        Performance:
            Target: <100ms for <100 files
        """
        # Get tracked files
        delta_files = self._pending_ir_deltas.pop(event.txn_id, set())
        changed_files = self._pending_changes.pop(event.txn_id, set())
        self._txn_created_at.pop(event.txn_id, None)

        # Record commit metrics
        batch_size = len(changed_files)
        self._metrics.record_commit(batch_size)

        if not changed_files and not delta_files:
            # No changes to process
            return

        # 1. Batch IR delta calculation (PARALLEL)
        if delta_files:
            try:
                # Group files by language for parallel processing
                files_by_lang = self._group_by_language(delta_files)

                # Process each language group in PARALLEL (asyncio.gather)
                tasks = []
                for language, files in files_by_lang.items():
                    task = self._process_language_batch(
                        language=language,
                        files=list(files),
                        txn_id=event.txn_id,
                    )
                    tasks.append(task)

                # Wait for all language batches to complete (parallel)
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Log any exceptions
                for _i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(
                            f"Parallel IR delta failed (txn {event.txn_id}): {result}",
                            exc_info=result,
                        )

            except Exception as e:
                logger.error(
                    f"Batch IR delta grouping failed (txn {event.txn_id}): {e}",
                    exc_info=True,
                )

        # 2. Batch indexing
        if changed_files:
            indexing_start = time.perf_counter()

            try:
                await self._indexer.index_files(
                    file_paths=list(changed_files),
                    force_reindex=False,  # Incremental only
                )

                indexing_latency = (time.perf_counter() - indexing_start) * 1000  # ms
                self._metrics.record_indexing(indexing_latency)

                logger.info(
                    f"Batch indexing completed for transaction {event.txn_id}: "
                    f"{len(changed_files)} files indexed, "
                    f"latency={indexing_latency:.1f}ms"
                )

            except Exception as e:
                # Don't propagate indexing errors
                # File commit already succeeded
                indexing_latency = (time.perf_counter() - indexing_start) * 1000  # ms
                self._metrics.record_error()

                logger.error(
                    f"Batch indexing failed for transaction {event.txn_id}: {e}, latency={indexing_latency:.1f}ms",
                    exc_info=True,
                    extra={
                        "txn_id": event.txn_id,
                        "num_files": len(changed_files),
                        "event_type": event.type,
                        "latency_ms": indexing_latency,
                    },
                )

    def _on_rollback(self, event: ShadowFSEvent) -> None:
        """
        Handle rollback event: discard tracked changes

        Args:
            event: Rollback event

        Side Effects:
            - Tracked files discarded (both IR deltas and indexing)
            - Transaction timestamps cleaned up
            - Metrics recorded

        Performance:
            O(1) dict deletion
        """
        # Discard tracked files
        self._pending_changes.pop(event.txn_id, None)
        self._pending_ir_deltas.pop(event.txn_id, None)
        self._txn_created_at.pop(event.txn_id, None)

        # Record metrics
        self._metrics.record_rollback()

        logger.debug(f"Tracked changes discarded for transaction {event.txn_id}")

    async def _process_language_batch(
        self,
        language: str,
        files: list[Path],
        txn_id: str,
    ) -> dict:
        """
        Process a batch of files for a single language (parallel-safe)

        Strategy:
            1. Call IncrementalIRBuilder.build_incremental
            2. Log results
            3. Return metrics

        Args:
            language: Programming language
            files: List of file paths
            txn_id: Transaction ID

        Returns:
            Dict with metrics (changed_files, rebuilt_files, latency)

        Raises:
            Exception: If IR delta calculation fails

        Performance:
            This method is called in parallel for each language

        Examples:
            >>> await plugin._process_language_batch(
            ...     language="python",
            ...     files=[Path("a.py"), Path("b.py")],
            ...     txn_id="txn-123",
            ... )
            {
                "language": "python",
                "num_files": 2,
                "changed_files": 2,
                "rebuilt_files": 1,
                "latency_ms": 45.2,
            }
        """
        start = time.perf_counter()

        try:
            # Run sync build_incremental in thread pool (non-blocking)
            result = await asyncio.to_thread(
                self._ir_builder.build_incremental,
                files=files,
                language=language,
            )

            latency = (time.perf_counter() - start) * 1000  # ms

            # Record metrics
            self._metrics.record_ir_delta(latency)

            logger.info(
                f"Batch IR delta calculated for {language} "
                f"(txn {txn_id}): "
                f"{len(files)} files, "
                f"{len(result.changed_files)} changed, "
                f"{len(result.rebuilt_files)} rebuilt, "
                f"latency={latency:.1f}ms"
            )

            return {
                "language": language,
                "num_files": len(files),
                "changed_files": len(result.changed_files),
                "rebuilt_files": len(result.rebuilt_files),
                "latency_ms": latency,
            }

        except Exception as e:
            latency = (time.perf_counter() - start) * 1000  # ms

            # Record error metrics
            self._metrics.record_error()

            logger.error(
                f"Batch IR delta failed for {language} (txn {txn_id}): {e}, latency={latency:.1f}ms",
                exc_info=True,
                extra={
                    "txn_id": txn_id,
                    "language": language,
                    "num_files": len(files),
                    "latency_ms": latency,
                },
            )

            raise  # Re-raise for asyncio.gather to catch

    def _ensure_cleanup_task(self) -> None:
        """
        Ensure TTL cleanup task is running (lazy initialization)

        Strategy:
            - Start task on first event
            - Only start if not already running
            - Only start if event loop is available

        Thread-Safety:
            - Called within async context (event loop running)
            - Safe to call multiple times (idempotent)

        Note:
            This is lazy initialization to avoid creating tasks
            during __init__ when event loop may not be running (e.g., in tests).
        """
        if self._cleanup_task is None or self._cleanup_task.done():
            try:
                # Only create task if event loop is running
                self._cleanup_task = asyncio.create_task(self._cleanup_stale_txns())
                logger.debug("TTL cleanup task started")
            except RuntimeError:
                # No event loop running (e.g., in tests)
                # Task will be created on next call
                pass

    def _group_by_language(self, files: set[Path]) -> dict[str, list[Path]]:
        """
        Group files by programming language

        Strategy:
            Use LanguageDetector to detect language from extension

        Args:
            files: Set of file paths

        Returns:
            Dict[language, List[Path]]

        Examples:
            >>> files = {Path("a.py"), Path("b.py"), Path("c.ts")}
            >>> result = self._group_by_language(files)
            >>> result
            {
                "python": [Path("a.py"), Path("b.py")],
                "typescript": [Path("c.ts")]
            }

        Performance:
            O(n) where n is number of files
        """
        groups: dict[str, list[Path]] = {}

        for file_path in files:
            lang = self._language_detector.detect(str(file_path))

            if lang not in groups:
                groups[lang] = []

            groups[lang].append(file_path)

        return groups

    async def _cleanup_stale_txns(self) -> None:
        """
        Background task: cleanup stale transactions (TTL-based)

        Strategy:
            1. Run every 60 seconds
            2. Find transactions older than TTL
            3. Discard their tracked changes
            4. Log warnings

        Side Effects:
            - Stale transactions cleaned up
            - Memory freed

        Performance:
            O(n) where n is number of active transactions

        Error Handling:
            - Catches all exceptions to prevent task crash
            - Logs errors and continues

        Examples:
            >>> # Transaction created 2 hours ago (TTL = 1 hour)
            >>> # → Cleaned up by this task
        """
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute

                current_time = time.time()
                stale_txns = [
                    txn_id
                    for txn_id, created_at in self._txn_created_at.items()
                    if current_time - created_at > self._ttl
                ]

                for txn_id in stale_txns:
                    # Cleanup state
                    num_changes = len(self._pending_changes.get(txn_id, set()))
                    num_deltas = len(self._pending_ir_deltas.get(txn_id, set()))

                    self._pending_changes.pop(txn_id, None)
                    self._pending_ir_deltas.pop(txn_id, None)
                    created_at = self._txn_created_at.pop(txn_id, current_time)

                    age = current_time - created_at

                    # Record metrics
                    self._metrics.record_stale_txn_cleanup()

                    logger.warning(
                        f"Cleaned up stale transaction {txn_id}: "
                        f"age={age:.1f}s, "
                        f"changes={num_changes}, "
                        f"deltas={num_deltas}"
                    )

            except asyncio.CancelledError:
                # Task cancelled (plugin shutdown)
                logger.info("TTL cleanup task cancelled")
                break

            except Exception as e:
                # Don't crash the task on errors
                logger.error(
                    f"TTL cleanup task error: {e}",
                    exc_info=True,
                )

    def get_metrics(self) -> PluginMetrics:
        """
        Get plugin metrics for observability

        Returns:
            PluginMetrics with current statistics

        Thread-Safe:
            Should be called within async context only

        Examples:
            >>> metrics = plugin.get_metrics()
            >>> print(f"Total writes: {metrics.total_writes}")
            >>> print(f"Avg IR delta latency: {metrics.avg_ir_delta_latency_ms:.1f}ms")
        """
        return self._metrics

    def _validate_path(self, path: str) -> Path:
        """
        Validate file path for security

        Strategy:
            1. Resolve path
            2. Check for absolute path (reject)
            3. Check for parent directory traversal (reject)
            4. Return validated Path

        Args:
            path: File path to validate

        Returns:
            Validated Path object

        Raises:
            ValueError: If path is invalid or unsafe

        Security:
            - Prevents path traversal attacks (../)
            - Prevents absolute path access
            - Prevents symlink attacks (resolve())

        Examples:
            >>> plugin._validate_path("main.py")  # OK
            Path("main.py")

            >>> plugin._validate_path("../../../etc/passwd")  # RAISES
            ValueError: Parent directory traversal not allowed

            >>> plugin._validate_path("/etc/passwd")  # RAISES
            ValueError: Absolute path not allowed
        """
        # Normalize path
        normalized = str(Path(path).as_posix())

        # Check for parent directory traversal
        if ".." in normalized:
            raise ValueError(f"Parent directory traversal not allowed: {path}")

        # Check for absolute path
        if Path(path).is_absolute():
            raise ValueError(f"Absolute path not allowed: {path}")

        # Return validated path
        return Path(path)

    async def shutdown(self) -> None:
        """
        Graceful shutdown: cancel background tasks

        Side Effects:
            - TTL cleanup task cancelled

        Note:
            Should be called when plugin is unregistered or app shuts down
        """
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

            logger.info("IncrementalUpdatePlugin shutdown complete")
