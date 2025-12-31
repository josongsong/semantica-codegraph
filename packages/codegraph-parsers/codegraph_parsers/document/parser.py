"""
Document Parsers

Base parser interface and implementations for various document formats.
"""

import re
from abc import ABC, abstractmethod
from pathlib import Path

from codegraph_parsers.document.models import (
    CodeBlock,
    DocumentSection,
    DocumentType,
    ParsedDocument,
    SectionType,
)
from codegraph_parsers.document.profile import DocIndexProfile


class DocumentParser(ABC):
    """Base class for document parsers."""

    @abstractmethod
    def parse(self, file_path: Path, content: str) -> ParsedDocument:
        """
        Parse a document.

        Args:
            file_path: Path to document
            content: Document content

        Returns:
            Parsed document
        """
        pass

    @abstractmethod
    def can_parse(self, file_path: Path) -> bool:
        """
        Check if this parser can handle the file.

        Args:
            file_path: Path to file

        Returns:
            True if parser can handle this file type
        """
        pass


class MarkdownParser(DocumentParser):
    """
    Parser for Markdown documents.

    Uses regex-based parsing for simplicity and reliability.
    Supports CommonMark + GitHub Flavored Markdown.
    """

    def can_parse(self, file_path: Path) -> bool:
        """Check if file is a Markdown file."""
        return file_path.suffix.lower() in [".md", ".mdx", ".markdown"]

    def parse(self, file_path: Path, content: str) -> ParsedDocument:
        """
        Parse Markdown document.

        Extracts:
        - Headings (H1-H6)
        - Code blocks with language info
        - Paragraphs
        - Lists

        Args:
            file_path: Path to markdown file
            content: Markdown content

        Returns:
            Parsed document
        """
        doc = ParsedDocument(
            file_path=str(file_path),
            doc_type=DocumentType.MARKDOWN,
            raw_content=content,
        )

        lines = content.split("\n")
        current_line = 0

        while current_line < len(lines):
            line = lines[current_line]

            # Parse heading (ATX style: # Heading)
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2).strip()
                doc.sections.append(
                    DocumentSection(
                        section_type=SectionType.HEADING,
                        content=text,
                        level=level,
                        line_start=current_line + 1,
                        line_end=current_line + 1,
                    )
                )
                current_line += 1
                continue

            # Parse code block (fenced: ```language)
            code_fence_match = re.match(r"^```(\w*)$", line)
            if code_fence_match:
                language = code_fence_match.group(1) or None
                code_start = current_line
                current_line += 1
                code_lines = []

                # Collect code until closing fence
                while current_line < len(lines):
                    if re.match(r"^```\s*$", lines[current_line]):
                        break
                    code_lines.append(lines[current_line])
                    current_line += 1

                code = "\n".join(code_lines)
                doc.code_blocks.append(
                    CodeBlock(
                        language=language,
                        code=code,
                        line_start=code_start + 1,
                        line_end=current_line + 1,
                    )
                )

                # Also add as section for completeness
                doc.sections.append(
                    DocumentSection(
                        section_type=SectionType.CODE_BLOCK,
                        content=code,
                        line_start=code_start + 1,
                        line_end=current_line + 1,
                        metadata={"language": language},
                    )
                )

                current_line += 1
                continue

            # Parse list item
            list_match = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.+)$", line)
            if list_match:
                doc.sections.append(
                    DocumentSection(
                        section_type=SectionType.LIST,
                        content=list_match.group(3).strip(),
                        line_start=current_line + 1,
                        line_end=current_line + 1,
                    )
                )
                current_line += 1
                continue

            # Parse paragraph (non-empty line)
            if line.strip():
                # Collect consecutive lines as paragraph
                para_start = current_line
                para_lines = [line]
                current_line += 1

                while current_line < len(lines):
                    next_line = lines[current_line]
                    # Stop at empty line, heading, code fence, or list
                    if (
                        not next_line.strip()
                        or re.match(r"^#{1,6}\s+", next_line)
                        or re.match(r"^```", next_line)
                        or re.match(r"^(\s*)([-*+]|\d+\.)\s+", next_line)
                    ):
                        break
                    para_lines.append(next_line)
                    current_line += 1

                doc.sections.append(
                    DocumentSection(
                        section_type=SectionType.PARAGRAPH,
                        content=" ".join(para_lines),
                        line_start=para_start + 1,
                        line_end=current_line,
                    )
                )
                continue

            current_line += 1

        return doc


class TextParser(DocumentParser):
    """
    Parser for plain text documents.

    Uses heuristics to detect structure (sections separated by blank lines).
    """

    def can_parse(self, file_path: Path) -> bool:
        """Check if file is a text file."""
        return file_path.suffix.lower() in [".txt", ".text"]

    def parse(self, file_path: Path, content: str) -> ParsedDocument:
        """
        Parse plain text document.

        Splits into paragraphs by blank lines.

        Args:
            file_path: Path to text file
            content: Text content

        Returns:
            Parsed document
        """
        doc = ParsedDocument(
            file_path=str(file_path),
            doc_type=DocumentType.TEXT,
            raw_content=content,
        )

        # Split by double newlines (paragraphs)
        paragraphs = re.split(r"\n\s*\n", content)

        line_num = 1
        for para in paragraphs:
            if para.strip():
                lines_in_para = para.count("\n") + 1
                doc.sections.append(
                    DocumentSection(
                        section_type=SectionType.PARAGRAPH,
                        content=para.strip(),
                        line_start=line_num,
                        line_end=line_num + lines_in_para - 1,
                    )
                )
                line_num += lines_in_para + 1  # +1 for blank line

        return doc


class RstParser(DocumentParser):
    """
    Parser for reStructuredText documents.

    Basic support for headings and code blocks.
    """

    def can_parse(self, file_path: Path) -> bool:
        """Check if file is an RST file."""
        return file_path.suffix.lower() in [".rst", ".rest"]

    def parse(self, file_path: Path, content: str) -> ParsedDocument:
        """
        Parse RST document.

        Supports:
        - Setext-style headings (underlined)
        - Code blocks (.. code-block:: language)

        Args:
            file_path: Path to RST file
            content: RST content

        Returns:
            Parsed document
        """
        doc = ParsedDocument(
            file_path=str(file_path),
            doc_type=DocumentType.RST,
            raw_content=content,
        )

        lines = content.split("\n")
        current_line = 0

        while current_line < len(lines):
            line = lines[current_line]

            # Parse heading (Setext: text followed by ==== or ----)
            if current_line + 1 < len(lines):
                next_line = lines[current_line + 1]
                if re.match(r"^[=\-~`]{3,}$", next_line):
                    level = {"=": 1, "-": 2, "~": 3, "`": 4}.get(next_line[0], 1)
                    doc.sections.append(
                        DocumentSection(
                            section_type=SectionType.HEADING,
                            content=line.strip(),
                            level=level,
                            line_start=current_line + 1,
                            line_end=current_line + 2,
                        )
                    )
                    current_line += 2
                    continue

            # Parse code block (.. code-block:: language)
            code_match = re.match(r"^\.\.\s+code-block::\s*(\w*)$", line)
            if code_match:
                language = code_match.group(1) or None
                code_start = current_line
                current_line += 1

                # Skip blank line after directive
                if current_line < len(lines) and not lines[current_line].strip():
                    current_line += 1

                code_lines = []
                # Collect indented code
                while current_line < len(lines):
                    code_line = lines[current_line]
                    if code_line and not code_line.startswith(("   ", "\t")):
                        break
                    code_lines.append(code_line.lstrip())
                    current_line += 1

                code = "\n".join(code_lines).rstrip()
                if code:
                    doc.code_blocks.append(
                        CodeBlock(
                            language=language,
                            code=code,
                            line_start=code_start + 1,
                            line_end=current_line,
                        )
                    )
                continue

            # Parse paragraph
            if line.strip():
                para_start = current_line
                para_lines = [line]
                current_line += 1

                while current_line < len(lines):
                    next_line = lines[current_line]
                    if not next_line.strip():
                        break
                    para_lines.append(next_line)
                    current_line += 1

                doc.sections.append(
                    DocumentSection(
                        section_type=SectionType.PARAGRAPH,
                        content=" ".join(para_lines),
                        line_start=para_start + 1,
                        line_end=current_line,
                    )
                )
                continue

            current_line += 1

        return doc


class DocumentParserRegistry:
    """Registry for document parsers."""

    def __init__(self, profile: DocIndexProfile = DocIndexProfile.BASIC):
        """
        Initialize registry with built-in parsers.

        Args:
            profile: Document indexing profile (affects parser behavior)
        """
        self.profile = profile
        self.parsers: list[DocumentParser] = [
            MarkdownParser(),
            TextParser(),
            RstParser(),
        ]

        # Add optional parsers if dependencies are available
        try:
            from codegraph_parsers.document.parsers.notebook_parser import NotebookParser

            include_outputs = profile == DocIndexProfile.SOTA
            self.parsers.append(NotebookParser(include_outputs=include_outputs))
        except ImportError:
            pass  # nbformat not available

        try:
            from codegraph_parsers.document.parsers.pdf_parser import PDFParser

            self.parsers.append(PDFParser(profile=profile))
        except ImportError:
            pass  # PyMuPDF not available

    def add_parser(self, parser: DocumentParser):
        """Add a custom parser."""
        self.parsers.append(parser)

    def get_parser(self, file_path: Path) -> DocumentParser | None:
        """
        Get appropriate parser for file.

        Args:
            file_path: Path to file

        Returns:
            Parser instance or None if no parser available
        """
        for parser in self.parsers:
            if parser.can_parse(file_path):
                return parser
        return None

    def parse_file(self, file_path: Path) -> ParsedDocument | None:
        """
        Parse a document file.

        Args:
            file_path: Path to document

        Returns:
            Parsed document or None if no parser available
        """
        parser = self.get_parser(file_path)
        if not parser:
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
            return parser.parse(file_path, content)
        except Exception:
            return None


# Global registry instance
_registry = DocumentParserRegistry()


def get_document_parser_registry() -> DocumentParserRegistry:
    """Get global document parser registry."""
    return _registry
