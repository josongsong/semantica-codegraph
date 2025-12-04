"""
Pyright Semantic Daemon

RFC-023 M0: Minimal implementation

Provides:
- Single file or multi-file analysis
- Export semantic info for specific locations (IR-provided)
- In-memory snapshot only (no persistence)

Key principle: Only query locations provided by IR (no blind scanning)
"""

import time
from pathlib import Path

from src.contexts.code_foundation.infrastructure.ir.external_analyzers.pyright_lsp import PyrightLSPClient
from src.contexts.code_foundation.infrastructure.ir.external_analyzers.snapshot import PyrightSemanticSnapshot, Span


class PyrightSemanticDaemon:
    """
    RFC-023 M0: Minimal Semantic Daemon

    Constraints:
    - In-memory snapshot only (no PostgreSQL)
    - IR-provided locations only (no blind scan)
    - Reuses PyrightLSPClient for LSP communication

    Usage:
        daemon = PyrightSemanticDaemon(Path("/project/root"))
        daemon.open_file(Path("main.py"), code)
        locations = [(10, 5), (15, 10), (20, 0)]  # From IR
        snapshot = daemon.export_semantic_for_locations(Path("main.py"), locations)
        daemon.shutdown()
    """

    def __init__(self, project_root: Path):
        """
        Initialize Pyright Semantic Daemon.

        Args:
            project_root: Root directory of the project

        Raises:
            RuntimeError: If pyright-langserver not found
        """
        self._lsp_client = PyrightLSPClient(project_root)
        self._current_snapshot: PyrightSemanticSnapshot | None = None

    def open_file(self, file_path: Path, content: str) -> None:
        """
        Open a single file in Pyright LSP.

        Args:
            file_path: File path (absolute or relative to project_root)
            content: File content

        Note:
            This reuses PyrightLSPClient._ensure_document_opened()
        """
        # Write file to disk temporarily (Pyright needs actual file)
        if not file_path.is_absolute():
            file_path = self._lsp_client.project_root / file_path

        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        file_path.write_text(content)

        # Open in LSP
        self._lsp_client._ensure_document_opened(file_path)

    def open_files(self, files: list[tuple[Path, str]]) -> None:
        """
        Open multiple files in Pyright LSP.

        Args:
            files: List of (file_path, content) tuples

        Note:
            M1 feature - opens multiple files at once
        """
        for file_path, content in files:
            self.open_file(file_path, content)

    def export_semantic_for_locations(
        self,
        file_path: Path,
        locations: list[tuple[int, int]],
    ) -> PyrightSemanticSnapshot:
        """
        Export semantic information for specific locations.

        ⚠️ IMPORTANT: Only queries IR-provided locations (no blind scan)

        Args:
            file_path: File path
            locations: List of (line, col) tuples from IR
                      line: 1-indexed
                      col: 0-indexed

        Returns:
            PyrightSemanticSnapshot with typing info

        Performance:
            O(N) where N = len(locations)
            NOT O(N^2) (no blind scanning)

        Example:
            # IR provides these locations (functions/classes/variables)
            locations = [(10, 0), (15, 4), (20, 8)]
            snapshot = daemon.export_semantic_for_locations(
                Path("main.py"),
                locations
            )
        """
        # Normalize file path
        if not file_path.is_absolute():
            file_path = self._lsp_client.project_root / file_path

        # Create snapshot
        snapshot = PyrightSemanticSnapshot(
            snapshot_id=f"snapshot-{int(time.time())}",
            project_id=self._lsp_client.project_root.name,
            files=[str(file_path)],
        )

        # Query each location (N queries, not N^2)
        for line, col in locations:
            hover_result = self._lsp_client.hover(file_path, line, col)

            if hover_result and hover_result.get("type"):
                # Create simple point span
                span = Span(line, col, line, col)

                # Add to snapshot
                snapshot.add_type_info(
                    str(file_path),
                    span,
                    hover_result["type"],
                )

        self._current_snapshot = snapshot
        return snapshot

    def export_semantic_for_files(
        self,
        file_locations: dict[Path, list[tuple[int, int]]],
    ) -> PyrightSemanticSnapshot:
        """
        Export semantic information for multiple files.

        Args:
            file_locations: Dictionary mapping file paths to location lists
                           {Path("main.py"): [(10, 0), (15, 4)], ...}

        Returns:
            PyrightSemanticSnapshot with typing info for all files

        Note:
            M1 feature - handles multiple files
        """
        # Create snapshot
        snapshot = PyrightSemanticSnapshot(
            snapshot_id=f"snapshot-{int(time.time())}",
            project_id=self._lsp_client.project_root.name,
            files=[str(fp) for fp in file_locations.keys()],
        )

        # Query each file
        for file_path, locations in file_locations.items():
            # Normalize path
            if not file_path.is_absolute():
                file_path = self._lsp_client.project_root / file_path

            # Query each location in this file
            for line, col in locations:
                hover_result = self._lsp_client.hover(file_path, line, col)

                if hover_result and hover_result.get("type"):
                    span = Span(line, col, line, col)
                    snapshot.add_type_info(
                        str(file_path),
                        span,
                        hover_result["type"],
                    )

        self._current_snapshot = snapshot
        return snapshot

    def shutdown(self):
        """
        Shutdown LSP client and clean up resources.

        Always call this when done to properly terminate pyright-langserver.
        """
        self._lsp_client.shutdown()
        self._current_snapshot = None

    def health_check(self) -> dict:
        """
        Get daemon health status.

        Returns:
            Dictionary with status information

        Note:
            M3 feature
        """
        return {
            "status": "healthy" if self._lsp_client._initialized else "unhealthy",
            "files_opened": len(self._lsp_client._opened_documents),
            "cache_size": len(self._lsp_client._hover_cache),
        }

    # M2: Incremental Updates

    def export_semantic_incremental(
        self,
        changed_files: dict[Path, list[tuple[int, int]]],
        previous_snapshot: PyrightSemanticSnapshot | None = None,
        deleted_files: list[Path] | None = None,
    ) -> PyrightSemanticSnapshot:
        """
        Export semantic information for changed files only (M2).

        This is the core incremental update method. It:
        1. Analyzes only changed files (not entire project)
        2. Merges with previous snapshot
        3. Handles deleted files

        Args:
            changed_files: Dict mapping changed file paths to IR-provided locations
            previous_snapshot: Previous snapshot to merge with (None = fresh start)
            deleted_files: List of deleted files to remove from snapshot

        Returns:
            New snapshot (previous + delta)

        Performance:
            O(N) where N = sum of locations in changed_files
            NOT O(total project size)

        Usage:
            # Detect changes
            detector = ChangeDetector(project_root)
            changed, deleted = detector.detect_changed_files()

            # Extract IR locations for changed files only
            changed_locations = {}
            for file_path in changed:
                ir_doc = generate_ir(file_path)
                locations = extract_ir_locations(ir_doc)
                changed_locations[file_path] = locations

            # Incremental update
            new_snapshot = daemon.export_semantic_incremental(
                changed_files=changed_locations,
                previous_snapshot=old_snapshot,
                deleted_files=deleted,
            )

        Example:
            # 1 file changed out of 100 files
            # M1 (Full): ~50 seconds (all 100 files)
            # M2 (Incremental): ~500ms (1 file only) → 100x faster!
        """
        if deleted_files is None:
            deleted_files = []

        # Step 1: Analyze changed files only
        changed_snapshot = self.export_semantic_for_files(changed_files)

        # Step 2: Handle previous snapshot
        if previous_snapshot is None:
            # No previous snapshot → just return changed snapshot
            return changed_snapshot

        # Step 3: Build new snapshot by merging
        # Start with previous snapshot's typing_info
        import time

        new_typing_info = dict(previous_snapshot.typing_info)

        # Get list of changed file paths (as strings for comparison)
        changed_file_strs = [str(f) for f in changed_files.keys()]

        # Remove old typing info for changed files (we'll replace with new)
        keys_to_remove = [key for key in new_typing_info.keys() if key[0] in changed_file_strs]
        for key in keys_to_remove:
            del new_typing_info[key]

        # Add new typing info from changed files
        new_typing_info.update(changed_snapshot.typing_info)

        # Handle deleted files
        if deleted_files:
            deleted_file_strs = [str(f) for f in deleted_files]
            keys_to_remove = [key for key in new_typing_info.keys() if key[0] in deleted_file_strs]
            for key in keys_to_remove:
                del new_typing_info[key]

        # Build list of all files (previous + changed - deleted)
        all_files = set(previous_snapshot.files)
        all_files.update(changed_file_strs)
        if deleted_files:
            deleted_file_strs_set = {str(f) for f in deleted_files}
            all_files = all_files - deleted_file_strs_set

        # Create new snapshot
        new_snapshot = PyrightSemanticSnapshot(
            snapshot_id=f"snapshot-{int(time.time())}",
            project_id=previous_snapshot.project_id,
            files=list(all_files),
            typing_info=new_typing_info,
        )

        return new_snapshot

    # M2.3: Parallel Hover Optimization

    async def export_semantic_for_locations_async(
        self, file_path: Path, locations: list[tuple[int, int]]
    ) -> PyrightSemanticSnapshot:
        """
        Export semantic information for specific locations (async, parallel).

        This is the async version of export_semantic_for_locations().
        Uses concurrent hover queries for ~10x speedup.

        Args:
            file_path: Path to file
            locations: List of (line, col) tuples from IR

        Returns:
            PyrightSemanticSnapshot with type information

        Performance:
            - Sequential: N × 50ms = 5000ms (100 locations)
            - Parallel (10 concurrent): N / 10 × 50ms = 500ms (100 locations)
            - Expected speedup: ~10x

        Usage:
            # Same as sync version, but async
            locations = [(1, 4), (5, 0), (10, 8)]
            snapshot = await daemon.export_semantic_for_locations_async(
                file_path, locations
            )

        Note:
            Uses asyncio.to_thread() to run synchronous hover() calls
            in parallel with concurrency limit.
        """

        # Normalize file path
        if not file_path.is_absolute():
            file_path = self._lsp_client.project_root / file_path

        # Create snapshot
        snapshot = PyrightSemanticSnapshot(
            snapshot_id=f"snapshot-{int(time.time())}",
            project_id=self._lsp_client.project_root.name,
            files=[str(file_path)],
        )

        # Parallel hover queries
        hover_results = await self._batch_hover_queries_async(file_path, locations)

        # Add to snapshot
        for span, type_str in hover_results.items():
            snapshot.add_type_info(str(file_path), span, type_str)

        self._current_snapshot = snapshot
        return snapshot

    async def _batch_hover_queries_async(
        self, file_path: Path, locations: list[tuple[int, int]], max_concurrent: int = 10
    ) -> dict[Span, str]:
        """
        Execute multiple hover queries in parallel (M2.3).

        Args:
            file_path: File to query
            locations: List of (line, col) positions
            max_concurrent: Maximum concurrent requests (default: 10)

        Returns:
            Dict mapping Span -> type string

        Performance:
            With max_concurrent=10:
            - 100 locations: ~500ms (vs 5000ms sequential)
            - ~10x speedup

        Implementation:
            Uses asyncio.to_thread() to run synchronous hover() calls
            in thread pool with concurrency limit (Semaphore).
        """
        import asyncio

        # Semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _hover_with_limit(line: int, col: int) -> tuple[Span, str | None]:
            """Execute single hover with concurrency limit."""
            async with semaphore:
                # Run sync hover() in thread pool
                try:
                    result = await asyncio.to_thread(self._lsp_client.hover, file_path, line, col)
                    span = Span(line, col, line, col)
                    if result and result.get("type"):
                        return (span, result["type"])
                    return (span, None)
                except Exception as e:
                    # Log error but continue
                    print(f"Warning: Hover failed at {file_path}:{line}:{col}: {e}")
                    return (Span(line, col, line, col), None)

        # Create tasks for all locations
        tasks = [_hover_with_limit(line, col) for line, col in locations]

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks)

        # Filter out None results
        hover_results = {}
        for span, type_str in results:
            if type_str is not None:
                hover_results[span] = type_str

        return hover_results

    async def export_semantic_for_files_async(
        self, file_locations: dict[Path, list[tuple[int, int]]]
    ) -> PyrightSemanticSnapshot:
        """
        Export semantic information for multiple files (async, parallel).

        This is the async version of export_semantic_for_files().
        Parallelizes hover queries across all files.

        Args:
            file_locations: Dict mapping file paths to IR-provided locations

        Returns:
            Single snapshot containing all files

        Performance:
            - Sequential: N_files × N_locs × 50ms
            - Parallel: (N_files × N_locs) / 10 × 50ms
            - Expected speedup: ~10x

        Usage:
            file_locations = {
                Path("main.py"): [(10, 5), (20, 0)],
                Path("utils.py"): [(5, 0)],
            }
            snapshot = await daemon.export_semantic_for_files_async(file_locations)
        """
        import asyncio

        # Create snapshot
        snapshot = PyrightSemanticSnapshot(
            snapshot_id=f"snapshot-{int(time.time())}",
            project_id=self._lsp_client.project_root.name,
            files=[str(fp) for fp in file_locations.keys()],
        )

        # Collect all hover tasks across all files
        all_tasks = []

        for file_path, locations in file_locations.items():
            # Normalize path
            if not file_path.is_absolute():
                file_path = self._lsp_client.project_root / file_path

            # Create tasks for this file
            for line, col in locations:
                all_tasks.append((file_path, line, col))

        # Execute all hover queries in parallel
        semaphore = asyncio.Semaphore(10)  # Limit concurrent requests

        async def _hover_single(file_path: Path, line: int, col: int) -> tuple[str, Span, str | None]:
            """Execute single hover with concurrency limit."""
            async with semaphore:
                try:
                    result = await asyncio.to_thread(self._lsp_client.hover, file_path, line, col)
                    span = Span(line, col, line, col)
                    if result and result.get("type"):
                        return (str(file_path), span, result["type"])
                    return (str(file_path), span, None)
                except Exception as e:
                    print(f"Warning: Hover failed at {file_path}:{line}:{col}: {e}")
                    return (str(file_path), Span(line, col, line, col), None)

        # Create tasks
        tasks = [_hover_single(fp, line, col) for fp, line, col in all_tasks]

        # Execute all
        results = await asyncio.gather(*tasks)

        # Add to snapshot
        for file_path_str, span, type_str in results:
            if type_str is not None:
                snapshot.add_type_info(file_path_str, span, type_str)

        self._current_snapshot = snapshot
        return snapshot
