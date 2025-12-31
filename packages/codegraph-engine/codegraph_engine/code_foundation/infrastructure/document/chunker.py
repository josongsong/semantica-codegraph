"""
Document Chunker

Profile-aware chunking strategies for documents.
"""

from dataclasses import dataclass
from typing import Protocol

from codegraph_engine.code_foundation.infrastructure.document.models import ParsedDocument, SectionType
from codegraph_engine.code_foundation.infrastructure.document.profile import DocIndexConfig, DocIndexProfile


@dataclass
class DocumentChunk:
    """
    A chunk of document content.

    Attributes:
        content: Text content
        chunk_type: Type of chunk (heading, paragraph, code_block, etc.)
        file_path: Source file path
        line_start: Starting line number
        line_end: Ending line number
        heading_context: Parent heading hierarchy (e.g., ["Setup", "Installation"])
        metadata: Additional metadata
        code_language: Language if chunk is code block
    """

    content: str
    chunk_type: str
    file_path: str
    line_start: int
    line_end: int
    heading_context: list[str] | None = None
    metadata: dict | None = None
    code_language: str | None = None

    def get_context_string(self) -> str:
        """Get heading context as string (e.g., 'Setup > Installation')."""
        if not self.heading_context:
            return ""
        return " > ".join(self.heading_context)

    def is_code_block(self) -> bool:
        """Check if chunk is a code block."""
        return self.chunk_type == "code_block"


class ChunkingStrategy(Protocol):
    """Protocol for chunking strategies."""

    def chunk(self, doc: ParsedDocument) -> list[DocumentChunk]:
        """
        Chunk a parsed document.

        Args:
            doc: Parsed document

        Returns:
            List of document chunks
        """
        ...


class BasicChunkingStrategy:
    """
    Basic chunking strategy for BASIC profile.

    - Simple heading-based chunking (H1/H2 boundaries)
    - Code blocks included in same section (not separate)
    - Minimal metadata
    """

    def __init__(self, max_tokens: int = 1024):
        """
        Initialize basic chunking strategy.

        Args:
            max_tokens: Maximum tokens per chunk (approximate)
        """
        self.max_tokens = max_tokens

    def chunk(self, doc: ParsedDocument) -> list[DocumentChunk]:
        """Chunk document using basic strategy."""
        chunks: list[DocumentChunk] = []
        current_section: list[str] = []
        current_heading: list[str] = []
        section_start_line = 1

        for section in doc.sections:
            # Start new chunk at H1/H2
            if section.section_type == SectionType.HEADING and section.level <= 2:
                # Flush previous section
                if current_section:
                    chunks.append(
                        DocumentChunk(
                            content="\n".join(current_section),
                            chunk_type="section",
                            file_path=doc.file_path,
                            line_start=section_start_line,
                            line_end=section.line_start - 1,
                            heading_context=current_heading.copy() if current_heading else None,
                        )
                    )
                    current_section = []

                # Update heading
                if section.level == 1:
                    current_heading = [section.content]
                else:  # level == 2
                    if current_heading:
                        current_heading = [current_heading[0], section.content]
                    else:
                        current_heading = [section.content]

                section_start_line = section.line_start

            # Add content to current section
            current_section.append(section.content)

        # Flush last section
        if current_section:
            chunks.append(
                DocumentChunk(
                    content="\n".join(current_section),
                    chunk_type="section",
                    file_path=doc.file_path,
                    line_start=section_start_line,
                    line_end=len(doc.raw_content.split("\n")),
                    heading_context=current_heading.copy() if current_heading else None,
                )
            )

        return chunks


class AdvancedChunkingStrategy:
    """
    Advanced chunking strategy for ADVANCED profile.

    - Hierarchical heading-based chunking (H1/H2 root, H3+ merged)
    - Code blocks as separate chunks (for code-centric retrieval)
    - Heading hierarchy context preserved
    """

    def __init__(self, max_tokens: int = 1024):
        """
        Initialize advanced chunking strategy.

        Args:
            max_tokens: Maximum tokens per chunk
        """
        self.max_tokens = max_tokens

    def chunk(self, doc: ParsedDocument) -> list[DocumentChunk]:
        """Chunk document using advanced strategy."""
        chunks: list[DocumentChunk] = []
        current_section: list[str] = []
        heading_stack: list[tuple[int, str]] = []  # (level, content)
        section_start_line = 1

        for section in doc.sections:
            # Handle headings
            if section.section_type == SectionType.HEADING:
                # Flush previous section
                if current_section:
                    chunks.append(
                        DocumentChunk(
                            content="\n".join(current_section),
                            chunk_type="section",
                            file_path=doc.file_path,
                            line_start=section_start_line,
                            line_end=section.line_start - 1,
                            heading_context=self._get_heading_context(heading_stack),
                        )
                    )
                    current_section = []

                # Update heading stack
                # Remove headings at same or lower level
                while heading_stack and heading_stack[-1][0] >= section.level:
                    heading_stack.pop()

                # Add new heading
                heading_stack.append((section.level, section.content))
                section_start_line = section.line_start

            # Handle code blocks separately
            elif section.section_type == SectionType.CODE_BLOCK:
                # Flush previous section
                if current_section:
                    chunks.append(
                        DocumentChunk(
                            content="\n".join(current_section),
                            chunk_type="section",
                            file_path=doc.file_path,
                            line_start=section_start_line,
                            line_end=section.line_start - 1,
                            heading_context=self._get_heading_context(heading_stack),
                        )
                    )
                    current_section = []

                # Create separate code chunk
                chunks.append(
                    DocumentChunk(
                        content=section.content,
                        chunk_type="code_block",
                        file_path=doc.file_path,
                        line_start=section.line_start,
                        line_end=section.line_end,
                        heading_context=self._get_heading_context(heading_stack),
                        code_language=section.metadata.get("language"),
                    )
                )
                section_start_line = section.line_end + 1

            # Handle other content
            else:
                current_section.append(section.content)

        # Flush last section
        if current_section:
            chunks.append(
                DocumentChunk(
                    content="\n".join(current_section),
                    chunk_type="section",
                    file_path=doc.file_path,
                    line_start=section_start_line,
                    line_end=len(doc.raw_content.split("\n")),
                    heading_context=self._get_heading_context(heading_stack),
                )
            )

        return chunks

    def _get_heading_context(self, heading_stack: list[tuple[int, str]]) -> list[str] | None:
        """Extract heading context from stack."""
        if not heading_stack:
            return None
        return [h[1] for h in heading_stack]


class SOTAChunkingStrategy:
    """
    SOTA chunking strategy for SOTA profile.

    - Layout-based logical section chunking
    - Code blocks, tables, images as separate chunks
    - Noise chunk merging
    - Minimum token threshold
    """

    def __init__(self, max_tokens: int = 1024, min_tokens: int = 50):
        """
        Initialize SOTA chunking strategy.

        Args:
            max_tokens: Maximum tokens per chunk
            min_tokens: Minimum tokens per chunk (merge smaller chunks)
        """
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens

    def chunk(self, doc: ParsedDocument) -> list[DocumentChunk]:
        """Chunk document using SOTA strategy."""
        # For now, use advanced strategy
        # TODO: Implement layout-based chunking, noise detection
        advanced = AdvancedChunkingStrategy(self.max_tokens)
        chunks = advanced.chunk(doc)

        # Merge small chunks
        merged_chunks: list[DocumentChunk] = []
        pending_chunk: DocumentChunk | None = None

        for chunk in chunks:
            # Skip code blocks from merging
            if chunk.is_code_block():
                if pending_chunk:
                    merged_chunks.append(pending_chunk)
                    pending_chunk = None
                merged_chunks.append(chunk)
                continue

            # Estimate tokens (rough: words * 1.3)
            estimated_tokens = len(chunk.content.split()) * 1.3

            if estimated_tokens < self.min_tokens:
                # Accumulate small chunk
                if pending_chunk:
                    pending_chunk.content += "\n\n" + chunk.content
                    pending_chunk.line_end = chunk.line_end
                else:
                    pending_chunk = chunk
            else:
                # Large enough chunk
                if pending_chunk:
                    merged_chunks.append(pending_chunk)
                    pending_chunk = None
                merged_chunks.append(chunk)

        # Flush pending
        if pending_chunk:
            merged_chunks.append(pending_chunk)

        return merged_chunks


class DocumentChunker:
    """
    Profile-aware document chunker.

    Selects appropriate chunking strategy based on DocIndexProfile.
    """

    def __init__(self, config: DocIndexConfig):
        """
        Initialize document chunker.

        Args:
            config: Document indexing configuration
        """
        self.config = config
        self.strategy = self._create_strategy()

    def _create_strategy(self) -> ChunkingStrategy:
        """Create chunking strategy based on profile."""
        max_tokens = self.config.max_doc_tokens_per_chunk

        if self.config.profile == DocIndexProfile.OFF:
            # Should not be called, but return basic as fallback
            return BasicChunkingStrategy(max_tokens)

        if self.config.profile == DocIndexProfile.BASIC:
            return BasicChunkingStrategy(max_tokens)

        if self.config.profile == DocIndexProfile.ADVANCED:
            return AdvancedChunkingStrategy(max_tokens)

        if self.config.profile == DocIndexProfile.SOTA:
            return SOTAChunkingStrategy(max_tokens)

        return BasicChunkingStrategy(max_tokens)

    def chunk(self, doc: ParsedDocument) -> list[DocumentChunk]:
        """
        Chunk a parsed document.

        Args:
            doc: Parsed document

        Returns:
            List of document chunks
        """
        return self.strategy.chunk(doc)

    def chunk_documents(self, docs: list[ParsedDocument]) -> list[DocumentChunk]:
        """
        Chunk multiple documents.

        Args:
            docs: List of parsed documents

        Returns:
            Flattened list of all chunks
        """
        all_chunks: list[DocumentChunk] = []
        for doc in docs:
            chunks = self.chunk(doc)
            all_chunks.extend(chunks)
        return all_chunks
