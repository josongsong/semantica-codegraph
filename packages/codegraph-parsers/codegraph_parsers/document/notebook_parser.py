"""
Jupyter Notebook Parser

Uses nbformat (official Jupyter library) to parse .ipynb files.
"""

from pathlib import Path

try:
    import nbformat

    NBFORMAT_AVAILABLE = True
except ImportError:
    NBFORMAT_AVAILABLE = False

from codegraph_parsers.document.models import (
    CodeBlock,
    DocumentSection,
    DocumentType,
    ParsedDocument,
    SectionType,
)
from codegraph_parsers.document.parser import DocumentParser


class NotebookParser(DocumentParser):
    """
    Parser for Jupyter Notebook files (.ipynb).

    Uses nbformat library to parse notebook structure and extract:
    - Markdown cells → sections
    - Code cells → code blocks
    - Cell outputs (optional based on profile)
    """

    def __init__(self, include_outputs: bool = False):
        """
        Initialize notebook parser.

        Args:
            include_outputs: Whether to include cell outputs in parsing
        """
        if not NBFORMAT_AVAILABLE:
            raise ImportError("nbformat not installed. Install with: pip install nbformat")
        self.include_outputs = include_outputs

    def can_parse(self, file_path: Path) -> bool:
        """Check if file is a Jupyter Notebook."""
        return file_path.suffix.lower() in [".ipynb"]

    def parse(self, file_path: Path, content: str) -> ParsedDocument:
        """
        Parse Jupyter Notebook.

        Args:
            file_path: Path to notebook file
            content: Notebook JSON content

        Returns:
            Parsed document
        """
        doc = ParsedDocument(
            file_path=str(file_path),
            doc_type=DocumentType.NOTEBOOK,
            raw_content=content,
        )

        try:
            # Parse notebook JSON
            nb = nbformat.reads(content, as_version=4)

            # Extract metadata
            doc.metadata["notebook_format"] = nb.nbformat
            doc.metadata["kernel"] = nb.metadata.get("kernelspec", {}).get("name")

            # Process cells
            current_line = 1
            for cell_idx, cell in enumerate(nb.cells):
                cell_type = cell.cell_type

                if cell_type == "markdown":
                    # Parse markdown cell as sections
                    sections = self._parse_markdown_cell(cell, current_line, cell_idx)
                    doc.sections.extend(sections)
                    md_line_count = len(cell.source.split("\n"))
                    current_line += max(1, md_line_count)

                elif cell_type == "code":
                    # Parse code cell
                    code_block = self._parse_code_cell(cell, current_line, cell_idx)
                    doc.code_blocks.append(code_block)

                    # Add as section for completeness
                    line_count = len(cell.source.split("\n"))
                    doc.sections.append(
                        DocumentSection(
                            section_type=SectionType.CODE_BLOCK,
                            content=cell.source,
                            line_start=current_line,
                            line_end=current_line + line_count - 1,
                            metadata={
                                "cell_type": "code",
                                "cell_index": cell_idx,
                                "execution_count": cell.execution_count,
                            },
                        )
                    )

                    current_line += max(1, line_count)  # 빈 셀도 최소 1줄 차지

                    # Include outputs if enabled
                    if self.include_outputs and cell.outputs:
                        output_text = self._extract_outputs(cell.outputs)
                        if output_text:
                            output_line_count = len(output_text.split("\n"))
                            doc.sections.append(
                                DocumentSection(
                                    section_type=SectionType.RAW,
                                    content=output_text,
                                    line_start=current_line,
                                    line_end=current_line + output_line_count - 1,
                                    metadata={
                                        "cell_type": "output",
                                        "cell_index": cell_idx,
                                    },
                                )
                            )
                            current_line += max(1, output_line_count)

                elif cell_type == "raw":
                    # Raw cells
                    raw_line_count = len(cell.source.split("\n"))
                    doc.sections.append(
                        DocumentSection(
                            section_type=SectionType.RAW,
                            content=cell.source,
                            line_start=current_line,
                            line_end=current_line + raw_line_count - 1,
                            metadata={"cell_type": "raw", "cell_index": cell_idx},
                        )
                    )
                    current_line += max(1, raw_line_count)

        except Exception as e:
            # If parsing fails, return empty doc with error
            doc.metadata["parse_error"] = str(e)

        return doc

    def _parse_markdown_cell(self, cell, start_line: int, cell_idx: int) -> list[DocumentSection]:
        """Parse markdown cell into sections."""
        sections = []
        lines = cell.source.split("\n")

        # Simple paragraph grouping (more advanced parsing can use markdown-it-py)
        current_section = []
        section_start = start_line

        for line_idx, line in enumerate(lines):
            # Check for heading
            if line.strip().startswith("#"):
                # Flush previous section
                if current_section:
                    sections.append(
                        DocumentSection(
                            section_type=SectionType.PARAGRAPH,
                            content="\n".join(current_section),
                            line_start=section_start,
                            line_end=start_line + line_idx - 1,
                            metadata={"cell_type": "markdown", "cell_index": cell_idx},
                        )
                    )
                    current_section = []

                # Add heading
                # Count # characters at the beginning
                stripped = line.lstrip()
                level = 0
                for char in stripped:
                    if char == "#":
                        level += 1
                    else:
                        break
                text = stripped.lstrip("#").strip()
                sections.append(
                    DocumentSection(
                        section_type=SectionType.HEADING,
                        content=text,
                        level=level,
                        line_start=start_line + line_idx,
                        line_end=start_line + line_idx,
                        metadata={"cell_type": "markdown", "cell_index": cell_idx},
                    )
                )
                section_start = start_line + line_idx + 1
            else:
                current_section.append(line)

        # Flush last section
        if current_section:
            sections.append(
                DocumentSection(
                    section_type=SectionType.PARAGRAPH,
                    content="\n".join(current_section),
                    line_start=section_start,
                    line_end=start_line + len(lines) - 1,
                    metadata={"cell_type": "markdown", "cell_index": cell_idx},
                )
            )

        return sections

    def _parse_code_cell(self, cell, start_line: int, cell_idx: int) -> CodeBlock:
        """Parse code cell into code block."""
        # Determine language from kernel
        language = "python"  # Default
        if hasattr(cell, "metadata") and "language" in cell.metadata:
            language = cell.metadata["language"]

        line_count = len(cell.source.split("\n"))
        return CodeBlock(
            language=language,
            code=cell.source,
            line_start=start_line,
            line_end=start_line + line_count - 1,
        )

    def _extract_outputs(self, outputs: list) -> str:
        """Extract text from cell outputs."""
        output_texts = []

        for output in outputs:
            output_type = output.output_type

            # Text output
            if output_type in ["stream", "display_data", "execute_result"]:
                if hasattr(output, "text"):
                    output_texts.append(output.text)
                elif "text/plain" in output.get("data", {}):
                    output_texts.append(output.data["text/plain"])

            # Error output
            elif output_type == "error":
                error_text = f"Error: {output.ename}: {output.evalue}"
                output_texts.append(error_text)

        return "\n".join(output_texts) if output_texts else ""
