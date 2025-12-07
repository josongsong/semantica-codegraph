"""
Index Adapters

렉시컬/벡터 인덱스 어댑터
"""


class LexicalIndexAdapter:
    """렉시컬 인덱스 어댑터"""

    def __init__(self, lexical_index):
        """
        초기화

        Args:
            lexical_index: Lexical Index
        """
        self.lexical_index = lexical_index

    async def index_chunks(self, repo_id: str, chunks: list) -> None:
        """청크 인덱싱"""
        await self.lexical_index.index_chunks(repo_id, chunks)

    async def delete_chunks(self, repo_id: str, chunk_ids: list[str]) -> None:
        """청크 삭제"""
        await self.lexical_index.delete_chunks(repo_id, chunk_ids)


class VectorIndexAdapter:
    """벡터 인덱스 어댑터"""

    def __init__(self, vector_index):
        """
        초기화

        Args:
            vector_index: Vector Index
        """
        self.vector_index = vector_index

    async def index_chunks(self, repo_id: str, chunks: list) -> None:
        """청크 인덱싱"""
        await self.vector_index.index_chunks(repo_id, chunks)

    async def delete_chunks(self, repo_id: str, chunk_ids: list[str]) -> None:
        """청크 삭제"""
        await self.vector_index.delete_chunks(repo_id, chunk_ids)
