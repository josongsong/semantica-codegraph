"""
ShadowFS Core Implementation (SOTA-Level Production-Ready)

File-level overlay filesystem with:
    - In-memory overlay (zero disk writes)
    - Tombstone deletion
    - Unified diff generation
    - External tool materialization
    - Thread-safe operations

References:
    - Union Filesystems (Pendry & McKusick, 1995)
    - Copy-on-Write (Rosenblum & Ousterhout, 1992)
    - Git Index (Torvalds, 2005)

Architecture:
    Infrastructure Layer implementing Application Port (Hexagonal)
"""

import difflib
import shutil
import tempfile
import threading
from pathlib import Path

from ...application.shadowfs.shadowfs_port import ShadowFSPort
from ...domain.shadowfs.models import ChangeType, FilePatch, Hunk
from .path_canonicalizer import PathCanonicalizer


class ShadowFSCore(ShadowFSPort):
    """
    File-level overlay filesystem (SOTA-Level Thread-Safe)

    Design Pattern:
        - Copy-on-Write: Read from disk, write to overlay
        - Tombstone: Mark deletions without disk modification
        - Materialization: Temporary filesystem for external tools

    Attributes:
        workspace_root: Project root directory
        overlay: In-memory file modifications (path → content)
        deleted: Tombstone set of deleted file paths
        _lock: Thread lock for all mutations
        path_canonicalizer: Path normalization utility

    Thread-Safety:
        - RLock protects overlay and deleted mutations
        - Read operations are thread-safe (immutable disk)

    Performance:
        - O(1) read/write/delete
        - O(N) list_files where N = total files
        - O(M) materialize where M = modified files

    Examples:
        >>> fs = ShadowFSCore(Path("/project"))
        >>> fs.write_file("src/main.py", "print('hello')")
        >>> content = fs.read_file("src/main.py")
        >>> fs.delete_file("old.py")
        >>> patches = fs.get_diff()
    """

    def __init__(self, workspace_root: Path):
        """
        Initialize ShadowFS

        Args:
            workspace_root: Project root directory

        Raises:
            ValueError: If workspace_root doesn't exist or isn't directory
        """
        if not workspace_root.exists():
            raise ValueError(f"Workspace root doesn't exist: {workspace_root}")

        if not workspace_root.is_dir():
            raise ValueError(f"Workspace root isn't directory: {workspace_root}")

        self.workspace_root = workspace_root.resolve()

        # State: In-memory overlay
        self.overlay: dict[str, str] = {}

        # State: Tombstone set
        self.deleted: set[str] = set()

        # Thread safety
        self._lock = threading.RLock()

        # Utilities
        self.path_canonicalizer = PathCanonicalizer(self.workspace_root)

    # ========== Read Operations ==========

    def read_file(self, path: str) -> str:
        """
        Read file content (Thread-Safe)

        Strategy:
            1. Check deleted (tombstone)
            2. Check overlay (modified/new)
            3. Fallback to disk

        Args:
            path: Relative file path

        Returns:
            File content

        Raises:
            FileNotFoundError: File deleted or doesn't exist
            PermissionError: No read permission
            UnicodeDecodeError: File encoding issue

        Thread-Safety: Protected by RLock

        Performance: O(1)
        """
        with self._lock:
            # Step 1: Check tombstone
            if path in self.deleted:
                raise FileNotFoundError(f"File deleted (tombstone): {path}")

            # Step 2: Check overlay
            if path in self.overlay:
                return self.overlay[path]

            # Step 3: Fallback to disk
            disk_path = self.workspace_root / path

            if not disk_path.exists():
                raise FileNotFoundError(f"File not found on disk: {path}")

            try:
                return disk_path.read_text(encoding="utf-8")
            except PermissionError as e:
                raise PermissionError(f"No read permission for {path}") from e
            except UnicodeDecodeError as e:
                raise UnicodeDecodeError(
                    e.encoding, e.object, e.start, e.end, f"File encoding error for {path}: {e.reason}"
                )

    def exists(self, path: str) -> bool:
        """
        Check if file exists (Thread-Safe)

        Strategy:
            1. Check deleted → False
            2. Check overlay → True
            3. Check disk → disk.exists()

        Thread-Safety: Protected by RLock

        Performance: O(1)
        """
        with self._lock:
            if path in self.deleted:
                return False

            if path in self.overlay:
                return True

            return (self.workspace_root / path).exists()

    # ========== Write Operations ==========

    def write_file(self, path: str, content: str) -> None:
        """
        Write file to overlay (Thread-Safe, Zero Disk I/O)

        Args:
            path: Relative file path
            content: File content

        Raises:
            ValueError: Empty path or invalid content type

        Side Effects:
            - Adds to overlay
            - Removes from deleted (if was tombstone)

        Thread-Safety: Protected by RLock

        Performance: O(1)
        """
        with self._lock:
            if not path:
                raise ValueError("path must be non-empty")

            if not isinstance(content, str):
                raise TypeError(f"content must be str, got {type(content)}")

            # Add to overlay
            self.overlay[path] = content

            # Remove from deleted (resurrection)
            self.deleted.discard(path)

    def delete_file(self, path: str) -> None:
        """
        Delete file (Tombstone, Thread-Safe, Zero Disk I/O)

        Args:
            path: Relative file path

        Side Effects:
            - Adds to deleted set
            - Removes from overlay

        Thread-Safety: Protected by RLock

        Performance: O(1)
        """
        with self._lock:
            if not path:
                raise ValueError("path must be non-empty")

            # Add tombstone
            self.deleted.add(path)

            # Remove from overlay (if exists)
            self.overlay.pop(path, None)

    # ========== List Operations ==========

    def list_files(self, prefix: str | None = None, suffix: str | None = None) -> list[str]:
        """
        List all visible files (Thread-Safe)

        Strategy:
            1. Scan disk files
            2. Add overlay files
            3. Remove deleted files
            4. Apply filters

        Args:
            prefix: Filter by prefix (e.g., "src/")
            suffix: Filter by suffix (e.g., ".py")

        Returns:
            Sorted list of visible file paths

        Thread-Safety: Protected by RLock

        Performance: O(N) where N = total files
        """
        with self._lock:
            # Step 1: Disk files
            disk_files = set()
            try:
                for file_path in self.workspace_root.rglob("*"):
                    if file_path.is_file():
                        rel_path = str(file_path.relative_to(self.workspace_root))
                        disk_files.add(rel_path)
            except PermissionError:
                # Skip inaccessible directories
                pass

            # Step 2: Overlay files
            overlay_files = set(self.overlay.keys())

            # Step 3: Combine and remove deleted
            all_files = (disk_files | overlay_files) - self.deleted

            # Step 4: Apply filters
            if prefix:
                all_files = {f for f in all_files if f.startswith(prefix)}

            if suffix:
                all_files = {f for f in all_files if f.endswith(suffix)}

            return sorted(all_files)

    # ========== State Management ==========

    def rollback(self) -> None:
        """
        Clear all changes (Thread-Safe)

        Side Effects:
            - Clears overlay
            - Clears deleted set

        Thread-Safety: Protected by RLock

        Performance: O(1)
        """
        with self._lock:
            self.overlay.clear()
            self.deleted.clear()

    def get_modified_files(self) -> list[str]:
        """
        Get list of modified/added files (Thread-Safe)

        Thread-Safety: Protected by RLock

        Performance: O(M log M) where M = modified files
        """
        with self._lock:
            return sorted(self.overlay.keys())

    def get_deleted_files(self) -> list[str]:
        """
        Get list of deleted files (Thread-Safe)

        Thread-Safety: Protected by RLock

        Performance: O(D log D) where D = deleted files
        """
        with self._lock:
            return sorted(self.deleted)

    def is_modified(self) -> bool:
        """
        Check if any changes exist (Thread-Safe)

        Thread-Safety: Protected by RLock

        Performance: O(1)
        """
        with self._lock:
            return len(self.overlay) > 0 or len(self.deleted) > 0

    # ========== Diff Generation ==========

    def get_diff(self) -> list[FilePatch]:
        """
        Generate patches for all changes (Thread-Safe)

        Returns:
            List of FilePatch objects (Git-compatible)

        Thread-Safety: Protected by RLock

        Performance: O(M * L) where M = modified files, L = avg lines
        """
        with self._lock:
            patches = []

            # Modified/Added files
            for path, new_content in self.overlay.items():
                disk_path = self.workspace_root / path

                if disk_path.exists():
                    # MODIFY
                    try:
                        original_content = disk_path.read_text(encoding="utf-8")
                    except (PermissionError, UnicodeDecodeError):
                        # Treat as new file if can't read original
                        original_content = ""

                    if original_content != new_content:
                        patch = self._compute_patch(path, original_content, new_content)
                        patches.append(patch)
                else:
                    # ADD
                    hunks = self._create_add_hunks(new_content)
                    patches.append(
                        FilePatch(
                            path=path,
                            change_type=ChangeType.ADD,
                            original_content=None,
                            new_content=new_content,
                            hunks=hunks,
                        )
                    )

            # Deleted files
            for path in self.deleted:
                disk_path = self.workspace_root / path

                if disk_path.exists():
                    try:
                        original_content = disk_path.read_text(encoding="utf-8")
                        hunks = self._create_delete_hunks(original_content)
                        patches.append(
                            FilePatch(
                                path=path,
                                change_type=ChangeType.DELETE,
                                original_content=original_content,
                                new_content=None,
                                hunks=hunks,
                            )
                        )
                    except (PermissionError, UnicodeDecodeError):
                        # Skip if can't read
                        pass

            return patches

    def _compute_patch(self, path: str, original: str, new: str) -> FilePatch:
        """
        Compute unified diff patch

        Algorithm:
            Uses difflib.unified_diff for line-based diff

        Args:
            path: File path
            original: Original content
            new: New content

        Returns:
            FilePatch with MODIFY type and hunks

        Performance: O(L) where L = lines
        """
        original_lines = original.splitlines(keepends=False)
        new_lines = new.splitlines(keepends=False)

        # Generate unified diff
        diff_lines = list(
            difflib.unified_diff(original_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="")
        )

        # Parse into hunks
        hunks = self._parse_unified_diff(diff_lines)

        return FilePatch(
            path=path, change_type=ChangeType.MODIFY, original_content=original, new_content=new, hunks=hunks
        )

    def _parse_unified_diff(self, diff_lines: list[str]) -> tuple:
        """
        Parse unified diff into Hunk objects (FIXED: Empty file handling)

        Args:
            diff_lines: Output from difflib.unified_diff

        Returns:
            Tuple of Hunk objects

        Algorithm:
            Parse @@ headers and +/- lines

        Special Cases:
            - Empty file (start_line=0) → use start_line=1
        """
        hunks = []
        current_hunk_data = None

        for line in diff_lines:
            if line.startswith("@@"):
                # Save previous hunk
                if current_hunk_data:
                    hunk = self._create_hunk_from_data(current_hunk_data)
                    hunks.append(hunk)

                # Parse @@ -start,count +start,count @@
                parts = line.split("@@")[1].strip().split()
                if len(parts) >= 2:
                    original_info = parts[0]  # -start,count
                    start_line = int(original_info.split(",")[0][1:])  # Remove '-'

                    # CRITICAL FIX: Empty file has start_line=0, but Hunk requires > 0
                    if start_line == 0:
                        start_line = 1

                    current_hunk_data = {"start_line": start_line, "original_lines": [], "new_lines": []}

            elif line.startswith("-") and not line.startswith("---"):
                # Removed line
                if current_hunk_data:
                    current_hunk_data["original_lines"].append(line[1:])

            elif line.startswith("+") and not line.startswith("+++"):
                # Added line
                if current_hunk_data:
                    current_hunk_data["new_lines"].append(line[1:])

            elif line.startswith(" "):
                # Context line (both sides)
                if current_hunk_data:
                    current_hunk_data["original_lines"].append(line[1:])
                    current_hunk_data["new_lines"].append(line[1:])

        # Save last hunk
        if current_hunk_data:
            hunk = self._create_hunk_from_data(current_hunk_data)
            hunks.append(hunk)

        return tuple(hunks)

    def _create_hunk_from_data(self, data: dict) -> Hunk:
        """
        Create Hunk from parsed data

        Args:
            data: Dict with start_line, original_lines, new_lines

        Returns:
            Hunk object
        """
        start_line = data["start_line"]
        original_lines = tuple(data["original_lines"])
        new_lines = tuple(data["new_lines"])

        # Compute end_line
        if original_lines:
            end_line = start_line + len(original_lines) - 1
        else:
            # No original lines (pure addition)
            end_line = start_line

        return Hunk(start_line=start_line, end_line=end_line, original_lines=original_lines, new_lines=new_lines)

    def _create_add_hunks(self, content: str) -> tuple:
        """Create hunks for added file"""
        lines = tuple(content.splitlines(keepends=False))

        if not lines:
            # Empty file
            return ()

        return (Hunk(start_line=1, end_line=1, original_lines=(), new_lines=lines),)  # No original lines

    def _create_delete_hunks(self, content: str) -> tuple:
        """Create hunks for deleted file"""
        lines = tuple(content.splitlines(keepends=False))

        if not lines:
            # Empty file
            return ()

        return (Hunk(start_line=1, end_line=len(lines), original_lines=lines, new_lines=()),)

    # ========== External Tool Integration ==========

    def prepare_for_external_tool(self) -> Path:
        """
        Materialize overlay to temporary directory (FIXED: Snapshot Pattern)

        Use Case:
            External tools (pytest, mypy, docker) need real filesystem

        Strategy:
            1. Snapshot state (under lock) - O(M) where M = modified
            2. Create temp directory (without lock)
            3. Copy workspace structure (without lock)
            4. Apply overlay from snapshot (without lock)
            5. Apply deletions from snapshot (without lock)

        Returns:
            Path to materialized temporary directory

        Raises:
            OSError: Failed to create temp directory or symlinks
            IOError: Failed to write files

        Thread-Safety:
            - Phase 1 (snapshot): Protected by RLock
            - Phase 2 (materialize): No lock (uses snapshot)

        Performance:
            - Snapshot: O(M) where M = modified files
            - Materialization: O(N) where N = workspace files
            - Non-blocking: Other threads can read/write during materialize
            - Typical: ~100ms for 1000 files, 10 changes

        Cleanup:
            Caller MUST call cleanup_temp() after use
        """
        # Phase 1: Snapshot state (CRITICAL FIX: Minimal lock time)
        with self._lock:
            overlay_snapshot = self.overlay.copy()
            deleted_snapshot = self.deleted.copy()

        # Phase 2: Materialize (WITHOUT lock, non-blocking)
        temp_dir = Path(tempfile.mkdtemp(prefix="shadowfs_"))

        try:
            # Collect affected paths from snapshot
            affected_files = set(overlay_snapshot.keys()) | deleted_snapshot
            affected_dirs = self._get_affected_dirs(affected_files)

            # Copy workspace structure
            self._copy_workspace_optimized(temp_dir, affected_dirs)

            # Apply overlay from snapshot
            for file_path, content in overlay_snapshot.items():
                dest_file = temp_dir / file_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                dest_file.write_text(content, encoding="utf-8")

            # Apply deletions from snapshot
            for file_path in deleted_snapshot:
                dest_file = temp_dir / file_path
                dest_file.unlink(missing_ok=True)

            return temp_dir

        except Exception as e:
            # Cleanup on error
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise OSError(f"Failed to materialize to temp directory: {e}") from e

    def cleanup_temp(self, temp_dir: Path) -> None:
        """
        Cleanup materialized temp directory

        Args:
            temp_dir: Path returned by prepare_for_external_tool()

        Side Effects:
            - Removes entire temp directory tree

        Thread-Safety: Thread-safe (no shared state)

        Performance: O(N) where N = files in temp_dir
        """
        if not temp_dir or not temp_dir.exists():
            return

        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            # Best effort cleanup, don't raise
            pass

    def _get_affected_dirs(self, affected_files: set[str]) -> set[str]:
        """
        Get all directories containing affected files (OPTIMIZED: Simpler logic)

        Args:
            affected_files: Set of file paths

        Returns:
            Set of directory paths (all parent directories)

        Algorithm:
            For each file, walk up all parent directories

        Examples:
            >>> fs._get_affected_dirs({"a/b/c.py"})
            {"a", "a/b"}

        Performance: O(F * D) where F = files, D = avg depth
        """
        affected_dirs = set()

        for file_path in affected_files:
            # Walk up all parent directories
            current = Path(file_path).parent

            while current != Path("."):
                dir_str = str(current)
                if dir_str:  # Avoid empty string
                    affected_dirs.add(dir_str)
                current = current.parent

        return affected_dirs

    def _copy_workspace_optimized(self, temp_dir: Path, affected_dirs: set[str]) -> None:
        """
        Copy workspace with optimization (FIXED: Symlink jail check)

        Strategy:
            - Affected directories: Deep copy
            - Unaffected directories: Symlink (with security validation)

        Security:
            - Validate symlink targets within workspace
            - Skip external symlinks

        Args:
            temp_dir: Destination directory
            affected_dirs: Set of directories with modifications

        Performance:
            - Symlink: O(1) per directory
            - Deep copy: O(N) where N = files in directory
        """
        for item in self.workspace_root.iterdir():
            dest = temp_dir / item.name

            try:
                # SECURITY: Skip symlinks pointing outside workspace
                if item.is_symlink():
                    target = item.resolve(strict=False)
                    try:
                        target.relative_to(self.workspace_root)
                    except ValueError:
                        # Symlink points outside workspace, skip
                        continue

                if item.is_dir():
                    rel_path = str(item.relative_to(self.workspace_root))

                    # Check if any affected files in this dir
                    has_modifications = any(d.startswith(rel_path) for d in affected_dirs)

                    if has_modifications:
                        # Deep copy (has modifications)
                        shutil.copytree(item, dest, dirs_exist_ok=True)
                    else:
                        # Symlink (no modifications)
                        try:
                            # SECURITY: Final validation before symlink
                            resolved = item.resolve(strict=True)
                            resolved.relative_to(self.workspace_root)

                            dest.symlink_to(item, target_is_directory=True)
                        except (OSError, NotImplementedError, ValueError):
                            # Fallback: Copy if symlink fails or security issue
                            shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    # File: Copy
                    shutil.copy2(item, dest)

            except (OSError, PermissionError):
                # Skip inaccessible items
                continue
