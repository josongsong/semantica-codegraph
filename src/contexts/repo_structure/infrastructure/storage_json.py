"""
JSON File-based RepoMap Storage with In-Memory Cache

Provides persistent storage using JSON files with in-memory caching for performance.

Directory structure:
    {base_dir}/
        {repo_id}/
            {snapshot_id}.json
            .{snapshot_id}.json.lock  (temporary lock files)

Features:
- Fast in-memory reads with cache invalidation
- Persistent JSON storage
- No database dependencies
- Simple file-based backup/restore
- Atomic writes (temp file + rename) for data integrity
- Cross-platform file locking (fcntl on POSIX, msvcrt on Windows)
- Multi-process safe with mtime-based cache invalidation

Thread Safety:
- Multi-process safe: File locks prevent concurrent writes
- Cache invalidation: mtime tracking detects external updates
- Atomic operations: No partial/corrupted writes
"""

import json
import os
import tempfile
import warnings
from pathlib import Path

try:
    import fcntl  # POSIX systems

    HAVE_FCNTL = True
except ImportError:
    HAVE_FCNTL = False

try:
    import msvcrt  # Windows

    HAVE_MSVCRT = True
except ImportError:
    HAVE_MSVCRT = False

from src.contexts.repo_structure.infrastructure.models import RepoMapNode, RepoMapSnapshot


class _FileLock:
    """
    Cross-platform file lock context manager.

    Uses fcntl on POSIX systems, msvcrt on Windows.
    """

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.lock_path = file_path.parent / f".{file_path.name}.lock"
        self.lock_file = None

    def __enter__(self):
        """Acquire exclusive lock."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file = open(self.lock_path, "w")

        if HAVE_FCNTL:
            # POSIX: fcntl advisory lock
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX)
        elif HAVE_MSVCRT:
            # Windows: msvcrt lock
            msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            # Fallback: no locking (single-process only)
            warnings.warn("File locking not available on this platform", stacklevel=2)

        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        """Release lock."""
        if self.lock_file:
            if HAVE_FCNTL:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
            elif HAVE_MSVCRT:
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)

            self.lock_file.close()

            # Clean up lock file
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass


class JsonFileRepoMapStore:
    """
    JSON file-based RepoMap storage with in-memory cache.

    Advantages:
    - No database setup required
    - Fast in-memory access
    - Easy backup (just copy files)
    - Human-readable format
    - No external dependencies

    Usage:
        store = JsonFileRepoMapStore(base_dir="./data/repomap")
        store.save_snapshot(snapshot)
        snapshot = store.get_snapshot(repo_id, snapshot_id)
    """

    def __init__(self, base_dir: str | Path = "./data/repomap", enable_mtime_check: bool = False):
        """
        Initialize JSON file-based store with in-memory cache.

        Args:
            base_dir: Base directory for storing JSON files
            enable_mtime_check: Enable file modification time checking for cache invalidation.
                              Set to True for multi-process environments.
                              Set to False (default) for single-process for better performance.
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.enable_mtime_check = enable_mtime_check

        # In-memory cache: {(repo_id, snapshot_id): RepoMapSnapshot}
        self._cache: dict[tuple[str, str], RepoMapSnapshot] = {}

        # Node index: {node_id: RepoMapNode}
        self._node_index: dict[str, RepoMapNode] = {}

        # Cache timestamps for invalidation: {(repo_id, snapshot_id): mtime}
        # Only used if enable_mtime_check is True
        self._cache_timestamps: dict[tuple[str, str], float] = {}

    def _get_snapshot_path(self, repo_id: str, snapshot_id: str) -> Path:
        """Get file path for a snapshot."""
        repo_dir = self.base_dir / repo_id
        repo_dir.mkdir(parents=True, exist_ok=True)
        return repo_dir / f"{snapshot_id}.json"

    def save_snapshot(self, snapshot: RepoMapSnapshot) -> None:
        """
        Save a complete RepoMap snapshot to JSON file and cache.

        Uses atomic write pattern (temp file + rename) with file locking
        to prevent data corruption in multi-process environments.

        Args:
            snapshot: RepoMap snapshot to save
        """
        path = self._get_snapshot_path(snapshot.repo_id, snapshot.snapshot_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Acquire lock for atomic write
        with _FileLock(path):
            # Write to temporary file first
            fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(snapshot.model_dump(), f, indent=2, ensure_ascii=False)

                # Atomic rename (POSIX guarantees atomicity)
                os.replace(tmp_path, path)
            except Exception:
                # Clean up temp file on error
                try:
                    os.unlink(tmp_path)
                except FileNotFoundError:
                    pass
                raise

        # Update cache and timestamp
        key = (snapshot.repo_id, snapshot.snapshot_id)
        self._cache[key] = snapshot
        self._cache_timestamps[key] = path.stat().st_mtime

        # Update node index
        for node in snapshot.nodes:
            self._node_index[node.id] = node

    def get_snapshot(self, repo_id: str, snapshot_id: str) -> RepoMapSnapshot | None:
        """
        Get a snapshot by repo_id and snapshot_id.

        Checks cache first, then loads from file if needed.
        If enable_mtime_check is True, validates cache by file modification time
        to handle multi-process updates.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier

        Returns:
            RepoMapSnapshot or None if not found
        """
        key = (repo_id, snapshot_id)
        path = self._get_snapshot_path(repo_id, snapshot_id)

        # Check cache first (fast path)
        if key in self._cache:
            if not self.enable_mtime_check:
                # Fast path: Trust cache without mtime check
                return self._cache[key]

            # Slow path: Validate cache with mtime check (multi-process safe)
            if not path.exists():
                # File was deleted externally
                self._cache.pop(key, None)
                self._cache_timestamps.pop(key, None)
                return None

            file_mtime = path.stat().st_mtime
            cached_mtime = self._cache_timestamps.get(key, 0)

            if file_mtime <= cached_mtime:
                # Cache is still valid
                return self._cache[key]
            else:
                # File was modified by another process - invalidate cache
                self._cache.pop(key, None)
                self._cache_timestamps.pop(key, None)

        # Cache miss or invalidated - load from file
        if not path.exists():
            return None

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                snapshot = RepoMapSnapshot.model_validate(data)

                # Update cache
                self._cache[key] = snapshot

                # Update timestamp only if mtime check is enabled
                if self.enable_mtime_check:
                    self._cache_timestamps[key] = path.stat().st_mtime

                # Update node index
                for node in snapshot.nodes:
                    self._node_index[node.id] = node

                return snapshot
        except (json.JSONDecodeError, ValueError) as e:
            warnings.warn(f"Failed to load snapshot {repo_id}:{snapshot_id}: {e}", stacklevel=2)
            return None

    def list_snapshots(self, repo_id: str) -> list[str]:
        """
        List all snapshot IDs for a repo.

        Args:
            repo_id: Repository identifier

        Returns:
            List of snapshot IDs
        """
        repo_dir = self.base_dir / repo_id
        if not repo_dir.exists():
            return []

        return [p.stem for p in repo_dir.glob("*.json")]

    def delete_snapshot(self, repo_id: str, snapshot_id: str) -> None:
        """
        Delete a snapshot from file and cache.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
        """
        # Remove from cache
        key = (repo_id, snapshot_id)
        snapshot = self._cache.pop(key, None)

        # Remove nodes from index
        if snapshot:
            for node in snapshot.nodes:
                self._node_index.pop(node.id, None)

        # Delete file
        path = self._get_snapshot_path(repo_id, snapshot_id)
        if path.exists():
            path.unlink()

    def get_node(self, node_id: str) -> RepoMapNode | None:
        """
        Get a single node by ID.

        Args:
            node_id: Node identifier

        Returns:
            RepoMapNode or None if not found
        """
        return self._node_index.get(node_id)

    def get_nodes_by_path(self, repo_id: str, snapshot_id: str, path: str) -> list[RepoMapNode]:
        """
        Get all nodes matching a path.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            path: File/directory path

        Returns:
            List of matching nodes
        """
        snapshot = self.get_snapshot(repo_id, snapshot_id)
        if not snapshot:
            return []

        return [node for node in snapshot.nodes if node.path == path]

    def get_nodes_by_fqn(self, repo_id: str, snapshot_id: str, fqn: str) -> list[RepoMapNode]:
        """
        Get all nodes matching an FQN.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            fqn: Fully qualified name

        Returns:
            List of matching nodes
        """
        snapshot = self.get_snapshot(repo_id, snapshot_id)
        if not snapshot:
            return []

        return [node for node in snapshot.nodes if node.fqn == fqn]

    def get_subtree(self, node_id: str) -> list[RepoMapNode]:
        """
        Get node and all descendants.

        Args:
            node_id: Node identifier

        Returns:
            List of nodes in subtree (root-first order)
        """
        node = self.get_node(node_id)
        if not node:
            return []

        # Find snapshot containing this node
        snapshot = None
        for s in self._cache.values():
            if any(n.id == node_id for n in s.nodes):
                snapshot = s
                break

        if not snapshot:
            # Try to load all snapshots for this repo
            # Extract repo_id from node_id (format: repomap:{repo_id}:...)
            parts = node_id.split(":")
            if len(parts) >= 2:
                repo_id = parts[1]
                for snapshot_id in self.list_snapshots(repo_id):
                    snapshot = self.get_snapshot(repo_id, snapshot_id)
                    if snapshot and any(n.id == node_id for n in snapshot.nodes):
                        break

        if not snapshot:
            return [node]

        return snapshot.get_subtree(node_id)

    def get_topk_by_importance(self, repo_id: str, snapshot_id: str, k: int = 100) -> list[RepoMapNode]:
        """
        Get top K nodes sorted by importance score.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            k: Number of top nodes to return

        Returns:
            List of RepoMapNode sorted by importance (descending)
        """
        snapshot = self.get_snapshot(repo_id, snapshot_id)
        if not snapshot:
            return []

        # Sort by importance descending
        nodes = sorted(
            snapshot.nodes,
            key=lambda n: n.metrics.importance,
            reverse=True,
        )
        return nodes[:k]

    def clear_cache(self) -> None:
        """Clear in-memory cache. Files remain on disk."""
        self._cache.clear()
        self._node_index.clear()
        self._cache_timestamps.clear()

    def preload_repo(self, repo_id: str) -> None:
        """
        Preload all snapshots for a repo into cache.

        Args:
            repo_id: Repository identifier
        """
        for snapshot_id in self.list_snapshots(repo_id):
            self.get_snapshot(repo_id, snapshot_id)

    def get_cache_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with cache size information
        """
        return {
            "cached_snapshots": len(self._cache),
            "indexed_nodes": len(self._node_index),
            "repos": len({repo_id for repo_id, _ in self._cache.keys()}),
        }
