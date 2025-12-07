"""
Chunk Incremental Refresher

Handles incremental updates to chunks based on file changes.

Phase A (MVP): ✅ COMPLETE (2024-11-24)
- Added/deleted/modified file handling
- content_hash based skip optimization
- ChunkRefreshResult tracking
- Version & commit tracking

Phase B: ✅ COMPLETE (2024-11-24)
- Span drift tracking ✅
- Chunk-level rename detection ✅
- LLM Summary/Importance hooks ✅

Phase C: 🔄 IN PROGRESS (2024-11-24)
- Diff-based partial updates (Current)
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from src.common.observability import get_logger, record_counter, record_histogram
from src.contexts.code_foundation.infrastructure.chunk.builder import ChunkBuilder
from src.contexts.code_foundation.infrastructure.chunk.git_loader import GitFileLoader
from src.contexts.code_foundation.infrastructure.chunk.models import Chunk, ChunkDiffType, ChunkRefreshResult
from src.contexts.code_foundation.infrastructure.chunk.store import ChunkStore

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument
    from src.contexts.code_foundation.infrastructure.ir.models import IRDocument

logger = get_logger(__name__)

# ============================================================
# GAP #7: Language-aware Span Drift Thresholds
# ============================================================

# Default threshold (lines)
DEFAULT_SPAN_DRIFT_THRESHOLD = 10

# Language-specific thresholds
# Higher for languages with verbose docstrings/comments
SPAN_DRIFT_THRESHOLDS: dict[str, int] = {
    "python": 15,  # Account for docstrings
    "typescript": 10,
    "javascript": 10,
    "java": 20,  # Verbose Javadoc
    "kotlin": 15,
    "go": 10,
    "rust": 12,
    "c": 10,
    "cpp": 12,
    "csharp": 15,
    "ruby": 12,
    "php": 12,
}

# Chunk-type specific adjustments
# Functions are more sensitive to drift than classes
CHUNK_TYPE_DRIFT_MULTIPLIER: dict[str, float] = {
    "function": 1.0,  # Base threshold
    "class": 1.5,  # Classes can drift more before recalc needed
    "file": 2.0,  # Files are least sensitive
    "module": 2.0,
}


def get_span_drift_threshold(language: str | None = None, chunk_kind: str | None = None) -> int:
    """
    Get language and chunk-type aware span drift threshold (GAP #7).

    Args:
        language: Programming language (e.g., "python", "typescript")
        chunk_kind: Chunk type (e.g., "function", "class")

    Returns:
        Threshold in lines
    """
    # Get base threshold for language
    base = SPAN_DRIFT_THRESHOLDS.get(language or "", DEFAULT_SPAN_DRIFT_THRESHOLD)

    # Apply chunk type multiplier
    multiplier = CHUNK_TYPE_DRIFT_MULTIPLIER.get(chunk_kind or "function", 1.0)

    return int(base * multiplier)


# ============================================================
# Phase C: Diff-based Partial Updates
# ============================================================


@dataclass
class DiffHunk:
    """
    Represents a single hunk in a git diff (Phase C).

    A hunk is a contiguous block of changes in a file.

    Example unified diff hunk:
        @@ -10,5 +12,7 @@ def function():
        (old_start=10, old_count=5, new_start=12, new_count=7)
    """

    old_start: int  # Starting line in old version
    old_count: int  # Number of lines in old version
    new_start: int  # Starting line in new version
    new_count: int  # Number of lines in new version
    lines: list[str]  # Actual diff lines (with +/- prefix)

    def affected_old_range(self) -> tuple[int, int]:
        """Get affected line range in old version"""
        return (self.old_start, self.old_start + self.old_count - 1)

    def affected_new_range(self) -> tuple[int, int]:
        """Get affected line range in new version"""
        return (self.new_start, self.new_start + self.new_count - 1)


class DiffParser:
    """
    Parses git unified diff format (Phase C).

    Extracts hunks from diff output to identify changed regions.

    Usage:
        parser = DiffParser()
        hunks = parser.parse_diff(diff_text)

        for hunk in hunks:
            start, end = hunk.affected_new_range()
            print(f"Changed lines: {start}-{end}")
    """

    # Unified diff hunk header: @@ -old_start,old_count +new_start,new_count @@
    HUNK_HEADER_PATTERN = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    def parse_diff(self, diff_text: str) -> list[DiffHunk]:
        """
        Parse unified diff format and extract hunks.

        Args:
            diff_text: Git diff output (unified format)

        Returns:
            List of DiffHunk objects
        """
        hunks: list[DiffHunk] = []
        current_hunk: DiffHunk | None = None
        current_lines: list[str] = []

        for line in diff_text.splitlines():
            # Check for hunk header
            match = self.HUNK_HEADER_PATTERN.match(line)
            if match:
                # Save previous hunk if exists
                if current_hunk and current_lines:
                    current_hunk.lines = current_lines
                    hunks.append(current_hunk)

                # Parse hunk header
                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_count = int(match.group(4)) if match.group(4) else 1

                # Create new hunk
                current_hunk = DiffHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=[],
                )
                current_lines = []

            elif current_hunk and (line.startswith("+") or line.startswith("-") or line.startswith(" ")):
                # Collect hunk lines
                current_lines.append(line)

        # Save last hunk
        if current_hunk and current_lines:
            current_hunk.lines = current_lines
            hunks.append(current_hunk)

        return hunks


class IRGenerator(Protocol):
    """Protocol for IR generation"""

    def generate_for_file(self, repo_id: str, file_path: str, commit: str) -> "IRDocument":
        """Generate IR for a file at a specific commit"""
        ...


class GraphGenerator(Protocol):
    """Protocol for graph generation"""

    def build_for_file(self, ir_doc: "IRDocument", snapshot_id: str) -> "GraphDocument":
        """Build graph from IR document"""
        ...


class ChunkUpdateHook(Protocol):
    """
    Protocol for chunk update hooks (Phase B).

    Allows external systems (LLM summarizer, importance ranker, etc.)
    to react to chunk changes without coupling ChunkIncrementalRefresher
    to specific implementations.

    Usage:
        class MyChunkHook:
            def on_chunk_drifted(self, chunk: Chunk) -> None:
                # Recalculate summary/importance for drifted chunk
                pass

            def on_chunk_renamed(self, old_id: str, new_id: str, chunk: Chunk) -> None:
                # Update references, reuse embeddings
                pass

            def on_chunk_modified(self, chunk: Chunk) -> None:
                # Regenerate summary/importance
                pass

        refresher = ChunkIncrementalRefresher(..., update_hook=MyChunkHook())
    """

    def on_chunk_drifted(self, chunk: Chunk) -> None:
        """
        Called when a chunk has drifted beyond threshold.

        Args:
            chunk: The drifted chunk (with updated position)
        """
        ...

    def on_chunk_renamed(self, old_id: str, new_id: str, chunk: Chunk) -> None:
        """
        Called when a chunk was renamed (same content, different FQN).

        Args:
            old_id: Old chunk ID
            new_id: New chunk ID
            chunk: The renamed chunk (with new FQN)
        """
        ...

    def on_chunk_modified(self, chunk: Chunk) -> None:
        """
        Called when a chunk's content was modified.

        Args:
            chunk: The modified chunk
        """
        ...


class ChunkIncrementalRefresher:
    """
    Incremental chunk refresher (Phase A - MVP).

    Handles file-level incremental updates with content_hash optimization.

    Usage:
        refresher = ChunkIncrementalRefresher(
            chunk_builder=builder,
            chunk_store=store,
            ir_generator=ir_gen,
            graph_generator=graph_gen,
        )

        result = refresher.refresh_files(
            repo_id="myrepo",
            old_commit="abc123",
            new_commit="def456",
            added_files=["new.py"],
            deleted_files=["old.py"],
            modified_files=["changed.py"],
            renamed_files={},  # Phase B
        )

        print(f"Changes: {result.total_changes()}")
    """

    def __init__(
        self,
        chunk_builder: ChunkBuilder,
        chunk_store: ChunkStore,
        ir_generator: IRGenerator,
        graph_generator: GraphGenerator,
        update_hook: ChunkUpdateHook | None = None,
        use_partial_updates: bool = False,  # Phase C: Enable diff-based partial updates
        repo_path: str | None = None,  # Repository path for Git operations
    ):
        self.chunk_builder = chunk_builder
        self.chunk_store = chunk_store
        self.ir_generator = ir_generator
        self.graph_generator = graph_generator
        self.update_hook = update_hook
        self.use_partial_updates = use_partial_updates
        self.diff_parser = DiffParser()
        # Cache for repeated chunk queries within a single refresh cycle
        self._chunk_cache: dict[tuple[str, str, str], list[Chunk]] = {}
        # Git file loader for loading file contents at specific commits
        self.git_loader = GitFileLoader(repo_path) if repo_path else None

    async def refresh_files(
        self,
        repo_id: str,
        old_commit: str,
        new_commit: str,
        added_files: list[str],
        deleted_files: list[str],
        modified_files: list[str],
        renamed_files: dict[str, str] | None = None,  # 🔥 IMPLEMENTED: old → new
        repo_config: dict | None = None,
        file_diffs: dict[str, str] | None = None,  # Phase C: file_path → diff_text
    ) -> ChunkRefreshResult:
        """
        Incrementally refresh chunks based on file changes.

        Optimizations:
        - Batch chunk queries for modified files (reduce DB round-trips)
        - Content hash based skip optimization
        - Diff-based partial updates (if enabled)
        """
        """
        Refresh chunks for changed files.

        Args:
            repo_id: Repository identifier
            old_commit: Previous commit hash
            new_commit: New commit hash
            added_files: List of newly added file paths
            deleted_files: List of deleted file paths
            modified_files: List of modified file paths
            renamed_files: Dict of renamed files (old → new) [Phase B]
            repo_config: Repository configuration
            file_diffs: Dict of file_path → diff_text for partial updates [Phase C]

        Returns:
            ChunkRefreshResult with all changes
        """
        # Clear cache at the start of each refresh cycle
        self._chunk_cache.clear()

        result = ChunkRefreshResult()
        repo_config = repo_config or {}

        logger.info(
            "chunk_refresh_start",
            repo_id=repo_id,
            old_commit=old_commit[:8],
            new_commit=new_commit[:8],
            added_files_count=len(added_files),
            modified_files_count=len(modified_files),
            deleted_files_count=len(deleted_files),
        )
        record_counter("chunk_refresh_total")
        record_histogram("chunk_refresh_added_files", len(added_files))
        record_histogram("chunk_refresh_modified_files", len(modified_files))
        record_histogram("chunk_refresh_deleted_files", len(deleted_files))

        # 1. Handle added files (full chunking)
        for file_path in added_files:
            try:
                new_chunks = await self._handle_added_file(repo_id, file_path, new_commit, repo_config)
                result.added_chunks.extend(new_chunks)
                logger.debug(
                    "chunk_added_file_processed",
                    file_path=file_path,
                    chunks_count=len(new_chunks),
                )
                record_counter("chunk_file_processed_total", labels={"operation": "added", "status": "success"})
                record_histogram("chunk_added_file_chunks_count", len(new_chunks))
            except Exception as e:
                logger.error(
                    "chunk_added_file_failed",
                    file_path=file_path,
                    error=str(e),
                )
                record_counter("chunk_file_processed_total", labels={"operation": "added", "status": "error"})

        # 2. Handle deleted files (soft delete)
        for file_path in deleted_files:
            try:
                deleted_ids = await self._handle_deleted_file(repo_id, file_path, old_commit, new_commit)
                result.deleted_chunks.extend(deleted_ids)
                logger.debug(
                    "chunk_deleted_file_processed",
                    file_path=file_path,
                    chunks_count=len(deleted_ids),
                )
                record_counter("chunk_file_processed_total", labels={"operation": "deleted", "status": "success"})
                record_histogram("chunk_deleted_file_chunks_count", len(deleted_ids))
            except Exception as e:
                logger.error(
                    "chunk_deleted_file_failed",
                    file_path=file_path,
                    error=str(e),
                )
                record_counter("chunk_file_processed_total", labels={"operation": "deleted", "status": "error"})

        # 3. 🔥 NEW: Handle renamed files (update file_path in chunks)
        if renamed_files:
            logger.info(
                "chunk_renamed_files_start",
                renamed_count=len(renamed_files),
            )
            for old_path, new_path in renamed_files.items():
                try:
                    renamed_chunks = await self._handle_renamed_file(
                        repo_id, old_path, new_path, old_commit, new_commit
                    )
                    result.renamed_chunks.extend(renamed_chunks)
                    logger.debug(
                        "chunk_renamed_file_processed",
                        old_path=old_path,
                        new_path=new_path,
                        chunks_count=len(renamed_chunks),
                    )
                    record_counter("chunk_file_processed_total", labels={"operation": "renamed", "status": "success"})
                except Exception as e:
                    logger.error(
                        "chunk_renamed_file_failed",
                        old_path=old_path,
                        new_path=new_path,
                        error=str(e),
                    )
                    record_counter("chunk_file_processed_total", labels={"operation": "renamed", "status": "error"})

        # 4. Handle modified files (diff + content_hash skip) - OPTIMIZED with batch loading
        # Pre-load all chunks for modified files in one batch query (reduce DB round-trips)
        if modified_files:
            logger.debug(
                "chunk_batch_load_start",
                file_count=len(modified_files),
            )
            chunks_by_file = await self.chunk_store.get_chunks_by_files_batch(repo_id, modified_files, old_commit)
            # Pre-populate cache
            for file_path, chunks in chunks_by_file.items():
                cache_key = (repo_id, file_path, old_commit)
                self._chunk_cache[cache_key] = chunks

            record_counter("chunk_batch_load_total")
            record_histogram("chunk_batch_load_files_count", len(modified_files))

        for file_path in modified_files:
            try:
                # Phase C: Use partial update if diff provided and enabled
                diff_text = file_diffs.get(file_path) if file_diffs else None
                if self.use_partial_updates and diff_text:
                    file_result = await self._handle_modified_file_partial(
                        repo_id, file_path, old_commit, new_commit, repo_config, diff_text
                    )
                else:
                    file_result = await self._handle_modified_file(
                        repo_id, file_path, old_commit, new_commit, repo_config
                    )

                result.added_chunks.extend(file_result.added_chunks)
                result.updated_chunks.extend(file_result.updated_chunks)
                result.deleted_chunks.extend(file_result.deleted_chunks)
                logger.debug(
                    "chunk_modified_file_processed",
                    file_path=file_path,
                    added_count=len(file_result.added_chunks),
                    updated_count=len(file_result.updated_chunks),
                    deleted_count=len(file_result.deleted_chunks),
                )
                record_counter("chunk_file_processed_total", labels={"operation": "modified", "status": "success"})
                record_histogram("chunk_modified_file_added_count", len(file_result.added_chunks))
                record_histogram("chunk_modified_file_updated_count", len(file_result.updated_chunks))
                record_histogram("chunk_modified_file_deleted_count", len(file_result.deleted_chunks))
            except Exception as e:
                logger.error(
                    "chunk_modified_file_failed",
                    file_path=file_path,
                    error=str(e),
                )
                record_counter("chunk_file_processed_total", labels={"operation": "modified", "status": "error"})

        logger.info(
            "chunk_refresh_complete",
            repo_id=repo_id,
            total_changes=result.total_changes(),
            added=len(result.added_chunks),
            updated=len(result.updated_chunks),
            deleted=len(result.deleted_chunks),
            renamed=len(result.renamed_chunks),
            drifted=len(result.drifted_chunks),
        )
        record_histogram("chunk_refresh_total_changes", result.total_changes())
        record_histogram("chunk_refresh_added_chunks", len(result.added_chunks))
        record_histogram("chunk_refresh_updated_chunks", len(result.updated_chunks))
        record_histogram("chunk_refresh_deleted_chunks", len(result.deleted_chunks))
        record_histogram("chunk_refresh_renamed_chunks", len(result.renamed_chunks))
        record_histogram("chunk_refresh_drifted_chunks", len(result.drifted_chunks))
        return result

    async def _get_chunks_by_file_cached(self, repo_id: str, file_path: str, commit: str) -> list[Chunk]:
        """
        Get chunks by file with caching (prevents redundant DB queries).

        Cache key: (repo_id, file_path, commit)
        """
        cache_key = (repo_id, file_path, commit)
        if cache_key not in self._chunk_cache:
            self._chunk_cache[cache_key] = await self.chunk_store.get_chunks_by_file(repo_id, file_path, commit)
        return self._chunk_cache[cache_key]

    async def _handle_added_file(self, repo_id: str, file_path: str, commit: str, repo_config: dict) -> list[Chunk]:
        """
        Handle newly added file.

        Strategy: Full chunking with version=1

        Args:
            repo_id: Repository identifier
            file_path: File path
            commit: Commit hash
            repo_config: Repository configuration

        Returns:
            List of new chunks
        """
        # Generate IR + Graph
        ir_doc = self.ir_generator.generate_for_file(repo_id, file_path, commit)
        graph_doc = self.graph_generator.build_for_file(ir_doc, commit)

        # Load file text from Git at specific commit
        file_text = self._load_file_text(file_path, commit)

        # Build chunks
        chunks, _, _ = self.chunk_builder.build(
            repo_id=repo_id,
            ir_doc=ir_doc,
            graph_doc=graph_doc,
            file_text=file_text,
            repo_config=repo_config,
        )

        # Set versioning fields
        for chunk in chunks:
            chunk.version = 1
            chunk.last_indexed_commit = commit
            chunk.is_deleted = False

        return chunks

    async def _handle_renamed_file(
        self,
        repo_id: str,
        old_path: str,
        new_path: str,
        old_commit: str,
        new_commit: str,
    ) -> list["Chunk"]:
        """
        🔥 NEW: Handle renamed file (update file_path in chunks).

        Strategy:
        1. Load chunks from old_path
        2. Update file_path to new_path
        3. Increment version
        4. Update last_indexed_commit

        Args:
            repo_id: Repository identifier
            old_path: Old file path
            new_path: New file path
            old_commit: Previous commit hash
            new_commit: New commit hash

        Returns:
            List of renamed chunks
        """
        # Get existing chunks from old path
        old_chunks = await self._get_chunks_by_file_cached(repo_id, old_path, old_commit)

        if not old_chunks:
            logger.warning(
                "renamed_file_no_chunks_found",
                repo_id=repo_id,
                old_path=old_path,
                new_path=new_path,
            )
            return []

        # Update file_path and metadata
        renamed_chunks = []
        for chunk in old_chunks:
            # Create updated chunk (immutable if frozen dataclass)
            updated_chunk = chunk
            updated_chunk.file_path = new_path
            updated_chunk.version = chunk.version + 1
            updated_chunk.last_indexed_commit = new_commit
            renamed_chunks.append(updated_chunk)

        # Save updated chunks
        await self.chunk_store.save_chunks(renamed_chunks)

        logger.info(
            "renamed_file_chunks_updated",
            repo_id=repo_id,
            old_path=old_path,
            new_path=new_path,
            chunks_count=len(renamed_chunks),
        )

        return renamed_chunks

    async def _handle_deleted_file(self, repo_id: str, file_path: str, old_commit: str, new_commit: str) -> list[str]:
        """
        Handle deleted file.

        Strategy: Soft delete (is_deleted=True, version++)

        Args:
            repo_id: Repository identifier
            file_path: File path
            old_commit: Previous commit hash
            new_commit: New commit hash

        Returns:
            List of deleted chunk IDs
        """
        # Get existing chunks (cached)
        old_chunks = await self._get_chunks_by_file_cached(repo_id, file_path, old_commit)

        # Mark as deleted
        deleted_ids = []
        for chunk in old_chunks:
            chunk.is_deleted = True
            chunk.version += 1
            chunk.last_indexed_commit = new_commit
            deleted_ids.append(chunk.chunk_id)

        # Save updated chunks
        await self.chunk_store.save_chunks(old_chunks)

        return deleted_ids

    async def _handle_modified_file(
        self,
        repo_id: str,
        file_path: str,
        old_commit: str,
        new_commit: str,
        repo_config: dict,
    ) -> ChunkRefreshResult:
        """
        Handle modified file.

        Refactored to use helper methods for better maintainability.
        Reduced from 167 lines → ~50 lines (70% reduction).

        Strategy:
        1. Get old chunks (cached)
        2. Generate new chunks
        3. Process chunk updates (UNCHANGED/MODIFIED/MOVED)
        4. Detect and handle renames
        5. Handle remaining unmatched chunks (deleted and truly new)

        Args:
            repo_id: Repository identifier
            file_path: File path
            old_commit: Previous commit hash
            new_commit: New commit hash
            repo_config: Repository configuration

        Returns:
            ChunkRefreshResult for this file
        """
        result = ChunkRefreshResult()

        # Step 1: Get old chunks (cached)
        old_chunks = await self._get_chunks_by_file_cached(repo_id, file_path, old_commit)
        old_by_fqn = {c.fqn: c for c in old_chunks}

        # Step 2: Generate new chunks
        new_chunks = self._generate_new_chunks_for_file(repo_id, file_path, new_commit, repo_config)
        new_by_fqn = {c.fqn: c for c in new_chunks}

        # Step 3: Process chunk updates (UNCHANGED/MODIFIED/MOVED)
        self._process_chunk_updates(old_by_fqn, new_by_fqn, new_commit, result)

        # Step 4: Detect and handle renames
        unmatched_old = {fqn: c for fqn, c in old_by_fqn.items() if fqn not in new_by_fqn}
        unmatched_new = {fqn: c for fqn, c in new_by_fqn.items() if fqn not in old_by_fqn}

        unmatched_old, unmatched_new = self._detect_and_handle_renames(unmatched_old, unmatched_new, new_commit, result)

        # Step 5: Handle remaining unmatched chunks (deleted and truly new)
        self._handle_unmatched_chunks(unmatched_old, unmatched_new, new_commit, result)

        return result

    # ============================================================
    # Helper methods (refactored from _handle_modified_file)
    # ============================================================

    def _load_file_text(self, file_path: str, commit: str) -> list[str]:
        """
        Load file text from Git at specific commit.

        Args:
            file_path: File path relative to repo root
            commit: Git commit hash

        Returns:
            List of file lines (empty list if Git loader unavailable or error)
        """
        if not self.git_loader:
            return []

        try:
            return self.git_loader.get_file_at_commit(file_path, commit)
        except Exception as e:
            logger.debug(
                "git_file_load_failed",
                file_path=file_path,
                commit=commit,
                error=str(e),
            )
            return []

    def _generate_new_chunks_for_file(
        self, repo_id: str, file_path: str, new_commit: str, repo_config: dict
    ) -> list[Chunk]:
        """
        Generate new chunks for a file.

        Args:
            repo_id: Repository identifier
            file_path: File path
            new_commit: New commit hash
            repo_config: Repository configuration

        Returns:
            List of new chunks
        """
        ir_doc = self.ir_generator.generate_for_file(repo_id, file_path, new_commit)
        graph_doc = self.graph_generator.build_for_file(ir_doc, new_commit)

        # Load file text from Git at specific commit
        file_text = self._load_file_text(file_path, new_commit)

        new_chunks, _, _ = self.chunk_builder.build(
            repo_id=repo_id,
            ir_doc=ir_doc,
            graph_doc=graph_doc,
            file_text=file_text,
            repo_config=repo_config,
        )
        return new_chunks

    def _process_chunk_updates(
        self,
        old_by_fqn: dict[str, Chunk],
        new_by_fqn: dict[str, Chunk],
        new_commit: str,
        result: ChunkRefreshResult,
    ) -> None:
        """
        Process chunk updates by comparing old and new chunks.

        Handles: UNCHANGED, MODIFIED, MOVED (with span drift detection)

        Args:
            old_by_fqn: Old chunks by FQN
            new_by_fqn: New chunks by FQN
            new_commit: New commit hash
            result: ChunkRefreshResult to update (mutated)
        """
        for fqn, new_chunk in new_by_fqn.items():
            old_chunk = old_by_fqn.get(fqn)

            if old_chunk is None:
                # New chunk (will be handled in _handle_unmatched_chunks)
                continue

            # Compare content_hash
            diff_type = self._compare_chunks(old_chunk, new_chunk)

            if diff_type == ChunkDiffType.UNCHANGED:
                # Skip - no changes
                continue
            elif diff_type == ChunkDiffType.MODIFIED:
                # Update chunk
                new_chunk.version = old_chunk.version + 1
                new_chunk.last_indexed_commit = new_commit
                result.updated_chunks.append(new_chunk)

                # Hook: content modified
                if self.update_hook:
                    self.update_hook.on_chunk_modified(new_chunk)
            elif diff_type == ChunkDiffType.MOVED:
                # Position changed only (Phase B: span drift tracking)
                new_chunk.version = old_chunk.version + 1
                new_chunk.last_indexed_commit = new_commit

                # Preserve original_start_line for drift tracking
                if old_chunk.original_start_line is not None:
                    new_chunk.original_start_line = old_chunk.original_start_line
                    new_chunk.original_end_line = old_chunk.original_end_line
                else:
                    # First move - set original from old chunk
                    new_chunk.original_start_line = old_chunk.start_line
                    new_chunk.original_end_line = old_chunk.end_line

                # Detect span drift
                if self._detect_span_drift(old_chunk, new_chunk):
                    result.drifted_chunks.append(new_chunk.chunk_id)
                    old_start = old_chunk.original_start_line or old_chunk.start_line or 0
                    new_start = new_chunk.start_line or 0
                    logger.debug(
                        "chunk_span_drift_detected",
                        chunk_id=new_chunk.chunk_id,
                        fqn=new_chunk.fqn,
                        old_start_line=old_start,
                        new_start_line=new_start,
                        drift_distance=abs(new_start - old_start),
                    )
                    record_counter("chunk_span_drift_total")
                    record_histogram(
                        "chunk_span_drift_distance",
                        abs(new_start - old_start),
                    )

                    # Hook: chunk drifted
                    if self.update_hook:
                        self.update_hook.on_chunk_drifted(new_chunk)

                result.updated_chunks.append(new_chunk)

    def _detect_and_handle_renames(
        self,
        old_by_fqn: dict[str, Chunk],
        new_by_fqn: dict[str, Chunk],
        new_commit: str,
        result: ChunkRefreshResult,
    ) -> tuple[dict[str, Chunk], dict[str, Chunk]]:
        """
        Detect and handle chunk renames (same content, different FQN).

        Args:
            old_by_fqn: Old chunks by FQN
            new_by_fqn: New chunks by FQN
            new_commit: New commit hash
            result: ChunkRefreshResult to update (mutated)

        Returns:
            Tuple of (unmatched_old, unmatched_new) after removing renamed chunks
        """
        # Find unmatched chunks
        unmatched_old = {fqn: c for fqn, c in old_by_fqn.items() if fqn not in new_by_fqn}
        unmatched_new = {fqn: c for fqn, c in new_by_fqn.items() if fqn not in old_by_fqn}

        # Build hash map for old chunks by content_hash
        old_by_hash: dict[str, Chunk] = {}
        for old_chunk in unmatched_old.values():
            if old_chunk.content_hash:
                old_by_hash[old_chunk.content_hash] = old_chunk

        # Match new chunks with old chunks by content_hash
        matched_old_fqns: set[str] = set()
        matched_new_fqns: set[str] = set()

        for new_fqn, new_chunk in unmatched_new.items():
            if not new_chunk.content_hash:
                continue

            # Find old chunk with same content_hash
            old_chunk = old_by_hash.get(new_chunk.content_hash)
            if old_chunk and self._detect_rename(old_chunk, new_chunk):
                # Found rename: old_chunk → new_chunk
                result.renamed_chunks[old_chunk.chunk_id] = new_chunk.chunk_id

                # Update new_chunk with old version info
                new_chunk.version = old_chunk.version + 1
                new_chunk.last_indexed_commit = new_commit
                new_chunk.original_start_line = old_chunk.original_start_line or old_chunk.start_line
                new_chunk.original_end_line = old_chunk.original_end_line or old_chunk.end_line
                result.updated_chunks.append(new_chunk)

                # Mark for removal
                matched_old_fqns.add(old_chunk.fqn)
                matched_new_fqns.add(new_fqn)

                logger.debug(
                    "chunk_rename_detected",
                    old_fqn=old_chunk.fqn,
                    new_fqn=new_chunk.fqn,
                    old_chunk_id=old_chunk.chunk_id,
                    new_chunk_id=new_chunk.chunk_id,
                    content_hash=old_chunk.content_hash,
                )
                record_counter("chunk_rename_total")

                # Hook: chunk renamed
                if self.update_hook:
                    self.update_hook.on_chunk_renamed(old_chunk.chunk_id, new_chunk.chunk_id, new_chunk)

        # Remove matched chunks from unmatched sets
        for fqn in matched_old_fqns:
            unmatched_old.pop(fqn, None)
        for fqn in matched_new_fqns:
            unmatched_new.pop(fqn, None)

        return unmatched_old, unmatched_new

    def _handle_unmatched_chunks(
        self,
        unmatched_old: dict[str, Chunk],
        unmatched_new: dict[str, Chunk],
        new_commit: str,
        result: ChunkRefreshResult,
    ) -> None:
        """
        Handle unmatched chunks (deleted and truly new).

        Args:
            unmatched_old: Unmatched old chunks (to be marked as deleted)
            unmatched_new: Unmatched new chunks (to be added)
            new_commit: New commit hash
            result: ChunkRefreshResult to update (mutated)
        """
        # Remaining unmatched_old are truly deleted
        for old_chunk in unmatched_old.values():
            old_chunk.is_deleted = True
            old_chunk.version += 1
            old_chunk.last_indexed_commit = new_commit
            result.deleted_chunks.append(old_chunk.chunk_id)

        # Remaining unmatched_new are truly new
        for new_chunk in unmatched_new.values():
            new_chunk.version = 1
            new_chunk.last_indexed_commit = new_commit
            result.added_chunks.append(new_chunk)

    def _compare_chunks(self, old: Chunk, new: Chunk) -> ChunkDiffType:
        """
        Compare old and new chunks.

        Strategy (Phase B):
        - content_hash identical → UNCHANGED or MOVED
        - content_hash different → MODIFIED
        - Span drift tracked when MOVED beyond threshold

        Args:
            old: Old chunk
            new: New chunk

        Returns:
            ChunkDiffType
        """
        if old.content_hash == new.content_hash:
            # Content identical
            if old.start_line == new.start_line:
                return ChunkDiffType.UNCHANGED
            else:
                # Position changed
                return ChunkDiffType.MOVED
        else:
            # Content changed
            return ChunkDiffType.MODIFIED

    def _detect_span_drift(self, old: Chunk, new: Chunk) -> bool:
        """
        Detect if chunk has drifted beyond threshold (Phase B + GAP #7).

        Span drift occurs when a chunk moves significantly from its
        original position, indicating structural changes that may
        warrant re-summarization or importance recalculation.

        GAP #7: Uses language-aware and chunk-type-aware thresholds.

        Args:
            old: Old chunk
            new: New chunk

        Returns:
            True if drift exceeds threshold
        """
        # Only detect drift if content unchanged
        if old.content_hash != new.content_hash:
            return False

        # Use original_start_line if available, otherwise use start_line
        old_baseline = old.original_start_line or old.start_line
        new_line = new.start_line

        if old_baseline is None or new_line is None:
            return False

        # Calculate drift distance
        drift = abs(new_line - old_baseline)

        # GAP #7: Use language and chunk-type aware threshold
        threshold = get_span_drift_threshold(new.language, new.kind)
        return drift > threshold

    def _detect_rename(self, old: Chunk, new: Chunk, allow_cross_file: bool = False) -> bool:
        """
        Detect if chunk was renamed (Phase B + GAP #8).

        Rename occurs when:
        - Content is identical (same content_hash)
        - FQN is different
        - Same file (default) or same module (if allow_cross_file=True)

        GAP #8: Cross-file rename detection for refactoring tracking.

        This allows reusing embeddings/summaries instead of recreating them.

        Args:
            old: Old chunk
            new: New chunk
            allow_cross_file: Allow rename detection across files (GAP #8)

        Returns:
            True if chunk was renamed
        """
        # Must have matching content
        if old.content_hash != new.content_hash or old.content_hash is None:
            return False

        # FQN must be different
        if old.fqn == new.fqn:
            return False

        # Check file/module matching
        if allow_cross_file:
            # GAP #8: Allow cross-file if same module
            return old.module_path == new.module_path
        else:
            # Default: Same file only
            return old.file_path == new.file_path

    def _detect_cross_file_move(self, old: Chunk, new: Chunk) -> bool:
        """
        Detect if chunk was moved to a different file (GAP #8).

        Cross-file move occurs when:
        - Content is identical (same content_hash)
        - File path is different
        - Module path is the same (refactoring within module)

        This is a special case of rename that tracks refactoring.

        Args:
            old: Old chunk
            new: New chunk

        Returns:
            True if chunk was moved to different file
        """
        return (
            old.content_hash == new.content_hash
            and old.content_hash is not None
            and old.file_path != new.file_path
            and old.module_path == new.module_path
        )

    async def _handle_modified_file_partial(
        self,
        repo_id: str,
        file_path: str,
        old_commit: str,
        new_commit: str,
        repo_config: dict,
        diff_text: str,
    ) -> ChunkRefreshResult:
        """
        Handle modified file with partial update (Phase C).

        Strategy:
        1. Parse diff to get changed line ranges
        2. Identify affected chunks (chunks overlapping with changed lines)
        3. Only regenerate affected chunks
        4. Reuse unchanged chunks (performance optimization)

        Args:
            repo_id: Repository identifier
            file_path: File path
            old_commit: Previous commit hash
            new_commit: New commit hash
            repo_config: Repository configuration
            diff_text: Git diff output (unified format)

        Returns:
            ChunkRefreshResult for this file
        """
        result = ChunkRefreshResult()

        # 1. Parse diff to get changed hunks
        hunks = self.diff_parser.parse_diff(diff_text)
        if not hunks:
            # No hunks found - fallback to full processing
            logger.debug(
                "chunk_partial_update_no_hunks",
                file_path=file_path,
                fallback="full_processing",
            )
            record_counter("chunk_partial_update_fallback_total", labels={"reason": "no_hunks"})
            return await self._handle_modified_file(repo_id, file_path, old_commit, new_commit, repo_config)

        # 2. Get old chunks (cached)
        old_chunks = await self._get_chunks_by_file_cached(repo_id, file_path, old_commit)
        old_by_fqn = {c.fqn: c for c in old_chunks}

        # 3. Identify affected chunks (chunks overlapping with changed lines)
        affected_fqns = self._identify_affected_chunks(old_chunks, hunks)

        if not affected_fqns:
            # No affected chunks - all changes are outside function/class boundaries
            # Fallback to full processing
            logger.debug(
                "chunk_partial_update_no_affected",
                file_path=file_path,
                fallback="full_processing",
            )
            record_counter("chunk_partial_update_fallback_total", labels={"reason": "no_affected_chunks"})
            return await self._handle_modified_file(repo_id, file_path, old_commit, new_commit, repo_config)

        logger.info(
            "chunk_partial_update_processing",
            file_path=file_path,
            affected_chunks=len(affected_fqns),
            total_chunks=len(old_chunks),
            efficiency_pct=round(100 * (1 - len(affected_fqns) / len(old_chunks)), 1) if old_chunks else 0,
        )
        record_counter("chunk_partial_update_total")
        record_histogram("chunk_partial_update_affected_count", len(affected_fqns))
        record_histogram("chunk_partial_update_total_count", len(old_chunks))

        # 4. Generate new chunks (full file processing - we still need full AST)
        # TODO: In future, support partial AST parsing
        ir_doc = self.ir_generator.generate_for_file(repo_id, file_path, new_commit)
        graph_doc = self.graph_generator.build_for_file(ir_doc, new_commit)

        # Load file text from Git at specific commit
        file_text = self._load_file_text(file_path, new_commit)

        new_chunks, _, _ = self.chunk_builder.build(
            repo_id=repo_id,
            ir_doc=ir_doc,
            graph_doc=graph_doc,
            file_text=file_text,
            repo_config=repo_config,
        )
        new_by_fqn = {c.fqn: c for c in new_chunks}

        # 5. Process only affected chunks
        for fqn in affected_fqns:
            old_chunk = old_by_fqn.get(fqn)
            new_chunk = new_by_fqn.get(fqn)

            if old_chunk and new_chunk:
                # Chunk exists in both versions - compare
                diff_type = self._compare_chunks(old_chunk, new_chunk)

                if diff_type == ChunkDiffType.UNCHANGED:
                    continue  # Skip
                elif diff_type in (ChunkDiffType.MODIFIED, ChunkDiffType.MOVED):
                    new_chunk.version = old_chunk.version + 1
                    new_chunk.last_indexed_commit = new_commit

                    if diff_type == ChunkDiffType.MOVED:
                        self._handle_moved_chunk(old_chunk, new_chunk, result)

                    result.updated_chunks.append(new_chunk)

                    if diff_type == ChunkDiffType.MODIFIED and self.update_hook:
                        self.update_hook.on_chunk_modified(new_chunk)

            elif old_chunk and not new_chunk:
                # Chunk deleted
                old_chunk.is_deleted = True
                old_chunk.version += 1
                old_chunk.last_indexed_commit = new_commit
                result.deleted_chunks.append(old_chunk.chunk_id)

            elif new_chunk and not old_chunk:
                # Chunk added
                new_chunk.version = 1
                new_chunk.last_indexed_commit = new_commit
                result.added_chunks.append(new_chunk)

        # 6. Unaffected chunks are skipped (performance win!)
        # They keep their old version and don't need reprocessing

        return result

    def _identify_affected_chunks(self, chunks: list[Chunk], hunks: list[DiffHunk]) -> set[str]:
        """
        Identify chunks affected by diff hunks (Phase C).

        A chunk is "affected" if its line range overlaps with any hunk's
        changed line range.

        Args:
            chunks: List of chunks from old version
            hunks: List of diff hunks

        Returns:
            Set of affected chunk FQNs
        """
        affected_fqns: set[str] = set()

        for chunk in chunks:
            if chunk.start_line is None or chunk.end_line is None:
                # Skip chunks without line ranges (repo/project/module level)
                continue

            chunk_range = (chunk.start_line, chunk.end_line)

            # Check if chunk overlaps with any hunk
            for hunk in hunks:
                hunk_start, hunk_end = hunk.affected_old_range()

                # Check for range overlap
                if self._ranges_overlap(chunk_range, (hunk_start, hunk_end)):
                    affected_fqns.add(chunk.fqn)
                    logger.debug(
                        "chunk_affected_by_hunk",
                        chunk_fqn=chunk.fqn,
                        chunk_start=chunk_range[0],
                        chunk_end=chunk_range[1],
                        hunk_start=hunk_start,
                        hunk_end=hunk_end,
                    )
                    break  # Already marked as affected

        return affected_fqns

    def _ranges_overlap(self, range1: tuple[int, int], range2: tuple[int, int]) -> bool:
        """
        Check if two line ranges overlap.

        Args:
            range1: (start, end) tuple
            range2: (start, end) tuple

        Returns:
            True if ranges overlap
        """
        start1, end1 = range1
        start2, end2 = range2
        return start1 <= end2 and start2 <= end1

    def _handle_moved_chunk(self, old_chunk: Chunk, new_chunk: Chunk, result: ChunkRefreshResult) -> None:
        """
        Handle a chunk that has been moved (line numbers changed).

        Preserves original line numbers and detects drift.
        Uses early return pattern to reduce nesting.

        Args:
            old_chunk: Old version of the chunk
            new_chunk: New version of the chunk (already updated with version/commit)
            result: Result object to update with drifted chunks
        """
        # Preserve original line numbers
        new_chunk.original_start_line = old_chunk.original_start_line or old_chunk.start_line
        new_chunk.original_end_line = old_chunk.original_end_line or old_chunk.end_line

        # Early return: no drift detected
        if not self._detect_span_drift(old_chunk, new_chunk):
            return

        # Handle drift
        result.drifted_chunks.append(new_chunk.chunk_id)
        if self.update_hook:
            self.update_hook.on_chunk_drifted(new_chunk)
