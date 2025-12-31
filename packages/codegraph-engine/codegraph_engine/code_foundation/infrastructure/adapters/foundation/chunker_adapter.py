"""
Chunker Adapter

IR-based chunking for ChunkerPort.
"""

from codegraph_engine.code_foundation.domain.models import Chunk, IRDocument, Language
from codegraph_engine.code_foundation.domain.ports import ChunkerPort


class IRBasedChunkerAdapter:
    """
    ChunkerPort adapter using IR-based chunking.

    Creates chunks from IR nodes (functions, classes, etc.).
    """

    def __init__(self, max_chunk_size: int = 1024):
        """
        Initialize adapter.

        Args:
            max_chunk_size: Maximum tokens per chunk
        """
        self._max_chunk_size = max_chunk_size

    def chunk(self, ir_doc: IRDocument, source_code: str) -> list[Chunk]:
        """
        Create chunks from IR.

        Args:
            ir_doc: IR document
            source_code: Source code

        Returns:
            List of chunks

        Strategy:
        - Top-level symbols (classes, functions) → individual chunks
        - Small symbols → merged into single chunk
        """
        chunks: list[Chunk] = []

        # Get file path from metadata or use default
        file_path = ir_doc.metadata.get("file_path", "<inline>") if hasattr(ir_doc, "metadata") else "<inline>"

        # Extract top-level nodes
        for node in ir_doc.nodes:
            # Skip non-top-level nodes
            if hasattr(node, "parent_id") and node.parent_id:
                continue

            # Get node file path if available
            node_file_path = getattr(node, "file_path", file_path)

            # Extract source code for this node
            if hasattr(node, "span") and node.span:
                span = node.span
                lines = source_code.split("\n")
                chunk_code = "\n".join(lines[span.start_line - 1 : span.end_line])

                # Infer language from IR doc metadata
                language_str = ir_doc.metadata.get("language", "unknown") if hasattr(ir_doc, "metadata") else "unknown"
                try:
                    language = Language(language_str)
                except ValueError:
                    language = Language.UNKNOWN

                chunk = Chunk(
                    id=f"{node_file_path}:{node.id}",
                    content=chunk_code,
                    file_path=node_file_path,
                    start_line=span.start_line,
                    end_line=span.end_line,
                    chunk_type=node.kind,  # Use node kind as chunk type
                    language=language,
                    metadata={
                        "node_id": node.id,
                        "node_kind": node.kind,
                        "node_name": getattr(node, "name", ""),
                    },
                )
                chunks.append(chunk)

        return chunks


def create_chunker_adapter(max_chunk_size: int = 1024) -> ChunkerPort:
    """Create production-grade ChunkerPort adapter."""
    return IRBasedChunkerAdapter(max_chunk_size)
