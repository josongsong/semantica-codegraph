"""
Retriever Layer Exceptions

Custom exceptions for the Retriever Layer.
"""


class RetrieverError(Exception):
    """Base exception for Retriever layer."""

    pass


class SnapshotNotFoundError(RetrieverError):
    """Snapshot does not exist in index."""

    def __init__(self, repo_id: str, snapshot_id: str, index_name: str):
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id
        self.index_name = index_name
        super().__init__(f"Snapshot not found: repo={repo_id}, snapshot={snapshot_id}, index={index_name}")


class IndexNotReadyError(RetrieverError):
    """Index is not ready for querying."""

    def __init__(self, repo_id: str, snapshot_id: str, index_name: str, reason: str = ""):
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id
        self.index_name = index_name
        self.reason = reason
        msg = f"Index not ready: repo={repo_id}, snapshot={snapshot_id}, index={index_name}"
        if reason:
            msg += f" (reason: {reason})"
        super().__init__(msg)


class RepoMapStaleError(RetrieverError):
    """RepoMap is stale or outdated."""

    def __init__(self, repo_id: str, snapshot_id: str, repomap_snapshot_id: str):
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id
        self.repomap_snapshot_id = repomap_snapshot_id
        super().__init__(
            f"RepoMap is stale: requested snapshot={snapshot_id}, " f"repomap snapshot={repomap_snapshot_id}"
        )
