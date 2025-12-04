"""
Document Models

Data structures for parsed documents and their components.
"""

from dataclasses import dataclass, field
from enum import Enum


class DocumentType(str, Enum):
    """Type of document."""

    MARKDOWN = "markdown"
    TEXT = "text"
    PDF = "pdf"
    NOTEBOOK = "notebook"
    ASCIIDOC = "asciidoc"
    RST = "rst"


class SectionType(str, Enum):
    """Type of document section."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    CODE_BLOCK = "code_block"
    LIST = "list"
    TABLE = "table"
    IMAGE = "image"
    QUOTE = "quote"
    RAW = "raw"


@dataclass
class CodeBlock:
    """
    Represents a code block in a document.

    Attributes:
        language: Programming language (e.g., 'python', 'typescript')
        code: Source code content
        line_start: Starting line number in document
        line_end: Ending line number in document
    """

    language: str | None
    code: str
    line_start: int
    line_end: int

    def is_executable(self) -> bool:
        """Check if code block is in an executable language."""
        executable_langs = {
            "python",
            "py",
            "javascript",
            "js",
            "typescript",
            "ts",
            "java",
            "go",
            "rust",
            "c",
            "cpp",
        }
        return self.language is not None and self.language.lower() in executable_langs


@dataclass
class DocumentSection:
    """
    Represents a section in a document.

    Attributes:
        section_type: Type of section
        content: Text content
        level: Heading level (for HEADING type, 1-6)
        line_start: Starting line number
        line_end: Ending line number
        metadata: Additional metadata
    """

    section_type: SectionType
    content: str
    level: int = 0
    line_start: int = 0
    line_end: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """
    Result of parsing a document.

    Attributes:
        file_path: Path to source document
        doc_type: Type of document
        sections: List of document sections
        code_blocks: List of code blocks extracted
        metadata: Document metadata (title, author, etc.)
        raw_content: Original document content
    """

    file_path: str
    doc_type: DocumentType
    sections: list[DocumentSection] = field(default_factory=list)
    code_blocks: list[CodeBlock] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    raw_content: str = ""

    def get_title(self) -> str | None:
        """Get document title (first H1 heading)."""
        for section in self.sections:
            if section.section_type == SectionType.HEADING and section.level == 1:
                return section.content
        return None

    def get_all_headings(self) -> list[tuple[int, str]]:
        """
        Get all headings with their levels.

        Returns:
            List of (level, content) tuples
        """
        return [(s.level, s.content) for s in self.sections if s.section_type == SectionType.HEADING]

    def get_executable_code_blocks(self) -> list[CodeBlock]:
        """Get only executable code blocks (Python, TS, etc.)."""
        return [cb for cb in self.code_blocks if cb.is_executable()]
