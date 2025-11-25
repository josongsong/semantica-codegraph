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

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from .builder import ChunkBuilder
from .models import Chunk, ChunkDiffType, ChunkRefreshResult
from .store import ChunkStore

if TYPE_CHECKING:
    from ..graph.models import GraphDocument
    from ..ir.models import IRDocument

logger = logging.getLogger(__name__)

# Span drift threshold (lines)
# If a chunk moves more than this many lines, it's considered "drifted"
# and may need summary/importance recalculation
SPAN_DRIFT_THRESHOLD = 10


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

    def refresh_files(
        self,
        repo_id: str,
        old_commit: str,
        new_commit: str,
        added_files: list[str],
        deleted_files: list[str],
        modified_files: list[str],
        renamed_files: dict[str, str] | None = None,  # old → new (Phase B)
        repo_config: dict | None = None,
        file_diffs: dict[str, str] | None = None,  # Phase C: file_path → diff_text
    ) -> ChunkRefreshResult:
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
            f"Refreshing chunks: {len(added_files)} added, "
            f"{len(modified_files)} modified, {len(deleted_files)} deleted"
        )

        # 1. Handle added files (full chunking)
        for file_path in added_files:
            try:
                new_chunks = self._handle_added_file(repo_id, file_path, new_commit, repo_config)
                result.added_chunks.extend(new_chunks)
                logger.debug(f"Added {len(new_chunks)} chunks from {file_path}")
            except Exception as e:
                logger.error(f"Failed to process added file {file_path}: {e}")

        # 2. Handle deleted files (soft delete)
        for file_path in deleted_files:
            try:
                deleted_ids = self._handle_deleted_file(repo_id, file_path, old_commit, new_commit)
                result.deleted_chunks.extend(deleted_ids)
                logger.debug(f"Deleted {len(deleted_ids)} chunks from {file_path}")
            except Exception as e:
                logger.error(f"Failed to process deleted file {file_path}: {e}")

        # 3. Handle modified files (diff + content_hash skip)
        for file_path in modified_files:
            try:
                # Phase C: Use partial update if diff provided and enabled
                diff_text = file_diffs.get(file_path) if file_diffs else None
                if self.use_partial_updates and diff_text:
                    file_result = self._handle_modified_file_partial(
                        repo_id, file_path, old_commit, new_commit, repo_config, diff_text
                    )
                else:
                    file_result = self._handle_modified_file(repo_id, file_path, old_commit, new_commit, repo_config)

                result.added_chunks.extend(file_result.added_chunks)
                result.updated_chunks.extend(file_result.updated_chunks)
                result.deleted_chunks.extend(file_result.deleted_chunks)
                logger.debug(
                    f"Modified {file_path}: "
                    f"{len(file_result.added_chunks)} added, "
                    f"{len(file_result.updated_chunks)} updated, "
                    f"{len(file_result.deleted_chunks)} deleted"
                )
            except Exception as e:
                logger.error(f"Failed to process modified file {file_path}: {e}")

        logger.info(f"Chunk refresh complete: {result.total_changes()} total changes")
        return result

    def _get_chunks_by_file_cached(
        self, repo_id: str, file_path: str, commit: str
    ) -> list[Chunk]:
        """
        Get chunks by file with caching (prevents redundant DB queries).

        Cache key: (repo_id, file_path, commit)
        """
        cache_key = (repo_id, file_path, commit)
        if cache_key not in self._chunk_cache:
            self._chunk_cache[cache_key] = self.chunk_store.get_chunks_by_file(
                repo_id, file_path, commit
            )
        return self._chunk_cache[cache_key]

    def _handle_added_file(self, repo_id: str, file_path: str, commit: str, repo_config: dict) -> list[Chunk]:
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

        # Get file text (simplified - in real impl, get from git)
        file_text = []  # TODO: Load from git at commit

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

    def _handle_deleted_file(self, repo_id: str, file_path: str, old_commit: str, new_commit: str) -> list[str]:
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
        old_chunks = self._get_chunks_by_file_cached(repo_id, file_path, old_commit)

        # Mark as deleted
        deleted_ids = []
        for chunk in old_chunks:
            chunk.is_deleted = True
            chunk.version += 1
            chunk.last_indexed_commit = new_commit
            deleted_ids.append(chunk.chunk_id)

        # Save updated chunks
        self.chunk_store.save_chunks(old_chunks)

        return deleted_ids

    def _handle_modified_file(
        self,
        repo_id: str,
        file_path: str,
        old_commit: str,
        new_commit: str,
        repo_config: dict,
    ) -> ChunkRefreshResult:
        """
        Handle modified file.

        Strategy:
        1. Get old chunks
        2. Generate new chunks
        3. Compare by content_hash
        4. Only update changed chunks

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

        # Get old chunks (cached)
        old_chunks = self._get_chunks_by_file_cached(repo_id, file_path, old_commit)
        old_by_fqn = {c.fqn: c for c in old_chunks}

        # Generate new chunks
        ir_doc = self.ir_generator.generate_for_file(repo_id, file_path, new_commit)
        graph_doc = self.graph_generator.build_for_file(ir_doc, new_commit)
        file_text = []  # TODO: Load from git

        new_chunks, _, _ = self.chunk_builder.build(
            repo_id=repo_id,
            ir_doc=ir_doc,
            graph_doc=graph_doc,
            file_text=file_text,
            repo_config=repo_config,
        )
        new_by_fqn = {c.fqn: c for c in new_chunks}

        # Compare old vs new
        for fqn, new_chunk in new_by_fqn.items():
            old_chunk = old_by_fqn.get(fqn)

            if old_chunk is None:
                # New chunk
                new_chunk.version = 1
                new_chunk.last_indexed_commit = new_commit
                result.added_chunks.append(new_chunk)
            else:
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
                        logger.debug(
                            f"Span drift detected for {new_chunk.chunk_id}: "
                            f"moved from line {old_chunk.original_start_line or old_chunk.start_line} "
                            f"to {new_chunk.start_line}"
                        )

                        # Hook: chunk drifted
                        if self.update_hook:
                            self.update_hook.on_chunk_drifted(new_chunk)

                    result.updated_chunks.append(new_chunk)

        # Find deleted chunks (Phase B: check for renames first)
        unmatched_old = {fqn: c for fqn, c in old_by_fqn.items() if fqn not in new_by_fqn}
        unmatched_new = {fqn: c for fqn, c in new_by_fqn.items() if fqn not in old_by_fqn}

        # Detect renames (same content, different FQN) - Optimized O(n)
        # Build hash map for old chunks by content_hash
        old_by_hash: dict[str, Chunk] = {}
        for old_chunk in unmatched_old.values():
            if old_chunk.content_hash:
                old_by_hash[old_chunk.content_hash] = old_chunk

        # Match new chunks with old chunks by content_hash
        renamed_pairs: list[tuple[Chunk, Chunk]] = []
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
                renamed_pairs.append((old_chunk, new_chunk))

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
                    f"Rename detected: {old_chunk.fqn} → {new_chunk.fqn} " f"(content_hash: {old_chunk.content_hash})"
                )

                # Hook: chunk renamed
                if self.update_hook:
                    self.update_hook.on_chunk_renamed(old_chunk.chunk_id, new_chunk.chunk_id, new_chunk)

        # Remove matched chunks from unmatched sets
        for fqn in matched_old_fqns:
            unmatched_old.pop(fqn, None)
        for fqn in matched_new_fqns:
            unmatched_new.pop(fqn, None)

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

        return result

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
        Detect if chunk has drifted beyond threshold (Phase B).

        Span drift occurs when a chunk moves significantly from its
        original position, indicating structural changes that may
        warrant re-summarization or importance recalculation.

        Args:
            old: Old chunk
            new: New chunk

        Returns:
            True if drift exceeds SPAN_DRIFT_THRESHOLD
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
        return drift > SPAN_DRIFT_THRESHOLD

    def _detect_rename(self, old: Chunk, new: Chunk) -> bool:
        """
        Detect if chunk was renamed (Phase B).

        Rename occurs when:
        - Content is identical (same content_hash)
        - FQN is different
        - Same file (file-level rename only)

        This allows reusing embeddings/summaries instead of recreating them.

        Args:
            old: Old chunk
            new: New chunk

        Returns:
            True if chunk was renamed
        """
        return (
            old.content_hash == new.content_hash
            and old.content_hash is not None  # Must have content_hash
            and old.fqn != new.fqn
            and old.file_path == new.file_path  # Same file only
        )

    def _handle_modified_file_partial(
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
            logger.debug(f"No hunks found in diff for {file_path}, using full processing")
            return self._handle_modified_file(repo_id, file_path, old_commit, new_commit, repo_config)

        # 2. Get old chunks
        old_chunks = self.chunk_store.get_chunks_by_file(repo_id, file_path, old_commit)
        old_by_fqn = {c.fqn: c for c in old_chunks}

        # 3. Identify affected chunks (chunks overlapping with changed lines)
        affected_fqns = self._identify_affected_chunks(old_chunks, hunks)

        if not affected_fqns:
            # No affected chunks - all changes are outside function/class boundaries
            # Fallback to full processing
            logger.debug(f"No affected chunks for {file_path}, using full processing")
            return self._handle_modified_file(repo_id, file_path, old_commit, new_commit, repo_config)

        logger.info(f"Partial update: {len(affected_fqns)}/{len(old_chunks)} chunks affected in {file_path}")

        # 4. Generate new chunks (full file processing - we still need full AST)
        # TODO: In future, support partial AST parsing
        ir_doc = self.ir_generator.generate_for_file(repo_id, file_path, new_commit)
        graph_doc = self.graph_generator.build_for_file(ir_doc, new_commit)
        file_text = []  # TODO: Load from git

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
                        # Preserve original line
                        new_chunk.original_start_line = old_chunk.original_start_line or old_chunk.start_line
                        new_chunk.original_end_line = old_chunk.original_end_line or old_chunk.end_line

                        # Check drift
                        if self._detect_span_drift(old_chunk, new_chunk):
                            result.drifted_chunks.append(new_chunk.chunk_id)
                            if self.update_hook:
                                self.update_hook.on_chunk_drifted(new_chunk)

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
                        f"Chunk {chunk.fqn} (lines {chunk_range[0]}-{chunk_range[1]}) "
                        f"affected by hunk (lines {hunk_start}-{hunk_end})"
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
