"""
Fake Lexical Search for Unit Testing
"""

from typing import Any

from src.index.common.documents import SearchHit


class FakeLexicalSearch:
    """
    LexicalSearchPort Fake 구현.

    간단한 substring matching 기반.
    """

    def __init__(self):
        self.documents: dict[str, dict[str, Any]] = {}  # (repo_id, snapshot_id) -> {chunk_id -> SearchHit}
        self.hits: list[SearchHit] = []  # For storing pre-configured hits

    def add_hit(self, hit: SearchHit):
        """Add a pre-configured search hit for testing"""
        self.hits.append(hit)

    async def reindex_repo(self, repo_id: str, snapshot_id: str) -> None:
        """Full repository reindex (no-op in fake)"""
        pass

    async def reindex_paths(self, repo_id: str, snapshot_id: str, paths: list[str]) -> None:
        """Partial reindex for specific files/paths (no-op in fake)"""
        pass

    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> list[SearchHit]:
        """
        Substring matching 기반 검색.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: 검색 쿼리
            limit: 결과 수

        Returns:
            검색 결과 (SearchHit 리스트)
        """
        # Return pre-configured hits that match the query
        matching_hits = [
            hit
            for hit in self.hits
            if query.lower() in (hit.file_path or "").lower() or query.lower() in (hit.chunk_id or "").lower()
        ]

        # Sort by score descending
        matching_hits.sort(key=lambda h: h.score, reverse=True)
        return matching_hits[:limit]

    async def delete_repo(self, repo_id: str, snapshot_id: str) -> None:
        """Delete repository index"""
        key = (repo_id, snapshot_id)
        self.documents.pop(key, None)

    def clear(self):
        """모든 문서 삭제."""
        self.documents.clear()
        self.hits.clear()
