"""
Chunk Builder Adapter

청크 빌드 어댑터
"""


class ChunkBuilderAdapter:
    """청크 빌더 어댑터"""

    def __init__(self, chunk_builder):
        """
        초기화

        Args:
            chunk_builder: ChunkBuilder
        """
        self.chunk_builder = chunk_builder

    def build_chunks(self, ir, graph, file_content: str):
        """
        청크 빌드

        Args:
            ir: IRDocument
            graph: GraphDocument
            file_content: 파일 내용

        Returns:
            청크 리스트
        """
        file_lines = file_content.splitlines()

        chunks, _, _ = self.chunk_builder.build(
            repo_id=ir.repo_id if hasattr(ir, "repo_id") else "default",
            ir_doc=ir,
            graph_doc=graph,
            file_text=file_lines,
            repo_config={"project_roots": ["."]},
            snapshot_id=ir.snapshot_id if hasattr(ir, "snapshot_id") else "default",
        )

        return chunks
