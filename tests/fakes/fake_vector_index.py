"""
Fake Vector Index for Testing

Implements VectorIndexPort with in-memory storage.
"""

from src.index.common.documents import IndexDocument, SearchHit


class FakeVectorIndex:
    """
    VectorIndexPort Fake implementation.

    Simple in-memory storage without actual embeddings.
    """

    def __init__(self):
        self.documents: dict[str, IndexDocument] = {}  # chunk_id -> IndexDocument
        self.doc_count: int = 0

    async def index(self, repo_id: str, snapshot_id: str, docs: list[IndexDocument]) -> None:
        """
        Full index creation.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            docs: List of IndexDocument instances
        """
        self.doc_count = len(docs)
        for doc in docs:
            self.documents[doc.chunk_id] = doc

    async def upsert(self, repo_id: str, snapshot_id: str, docs: list[IndexDocument]) -> None:
        """
        Incremental upsert.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            docs: List of IndexDocument instances to upsert
        """
        for doc in docs:
            self.documents[doc.chunk_id] = doc
        self.doc_count = len(self.documents)

    async def delete(self, repo_id: str, snapshot_id: str, doc_ids: list[str]) -> None:
        """
        Delete documents by ID.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            doc_ids: List of chunk_ids to delete
        """
        for doc_id in doc_ids:
            self.documents.pop(doc_id, None)
        self.doc_count = len(self.documents)

    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> list[SearchHit]:
        """
        Semantic search (simple substring matching for testing).

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Search query text
            limit: Maximum results

        Returns:
            List of SearchHit with source="vector"
        """
        results = []

        for chunk_id, doc in self.documents.items():
            # Simple substring match on content
            if query.lower() in doc.content.lower():
                score = doc.content.lower().count(query.lower()) / len(doc.content)
                hit = SearchHit(
                    chunk_id=chunk_id,
                    file_path=doc.file_path,
                    symbol_id=doc.symbol_id,
                    score=min(score, 1.0),  # Normalize to 0-1
                    source="vector",
                    metadata={
                        "symbol_name": doc.symbol_name,
                        "language": doc.language,
                    },
                )
                results.append(hit)

        # Sort by score descending
        results.sort(key=lambda h: h.score, reverse=True)
        return results[:limit]

    def clear(self):
        """Clear all documents"""
        self.documents.clear()
        self.doc_count = 0
