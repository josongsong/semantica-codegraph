"""
PDF Parser

Uses PyMuPDF (fitz) for high-quality PDF text extraction.
Supports tables, images, and OCR for SOTA profiles.
"""

from pathlib import Path

try:
    import fitz  # PyMuPDF

    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    import pdfplumber  # noqa: F401

    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

from codegraph_engine.code_foundation.infrastructure.document.models import (
    CodeBlock,
    DocumentSection,
    DocumentType,
    ParsedDocument,
    SectionType,
)
from codegraph_engine.code_foundation.infrastructure.document.parser import DocumentParser
from codegraph_engine.code_foundation.infrastructure.document.profile import DocIndexProfile


class PDFParser(DocumentParser):
    """
    Parser for PDF documents.

    Uses PyMuPDF (fitz) library for robust PDF parsing.

    Features by profile:
    - BASIC: Plain text extraction
    - ADVANCED: Text + table detection
    - SOTA: Text + tables + image metadata + OCR for images
    """

    def __init__(self, profile: DocIndexProfile = DocIndexProfile.BASIC):
        """
        Initialize PDF parser.

        Args:
            profile: Document indexing profile
        """
        if not PYMUPDF_AVAILABLE:
            raise ImportError("PyMuPDF not installed. Install with: pip install pymupdf")
        self.profile = profile
        self.extract_tables = profile in [DocIndexProfile.ADVANCED, DocIndexProfile.SOTA]
        self.extract_images = profile == DocIndexProfile.SOTA

    def can_parse(self, file_path: Path) -> bool:
        """Check if file is a PDF."""
        return file_path.suffix.lower() == ".pdf"

    def parse(self, file_path: Path, content: str | None = None) -> ParsedDocument:
        """
        Parse PDF document.

        Args:
            file_path: Path to PDF file
            content: Not used (PDF requires file path)

        Returns:
            Parsed document
        """
        doc = ParsedDocument(
            file_path=str(file_path),
            doc_type=DocumentType.PDF,
            raw_content="",  # PDFs stored as binary
        )

        pdf = None
        try:
            # Open PDF
            pdf = fitz.open(str(file_path))

            # Extract metadata
            metadata = pdf.metadata
            doc.metadata.update(
                {
                    "title": metadata.get("title", ""),
                    "author": metadata.get("author", ""),
                    "subject": metadata.get("subject", ""),
                    "creator": metadata.get("creator", ""),
                    "producer": metadata.get("producer", ""),
                    "page_count": len(pdf),
                }
            )

            # Process pages
            current_line = 1
            for page_num, page in enumerate(pdf):
                page_sections, page_code_blocks = self._parse_page(page, page_num + 1, current_line)

                doc.sections.extend(page_sections)
                doc.code_blocks.extend(page_code_blocks)

                # Update line counter
                for section in page_sections:
                    current_line = max(current_line, section.line_end + 1)

        except Exception as e:
            # If parsing fails, return empty doc with error
            doc.metadata["parse_error"] = str(e)
        finally:
            # Always close PDF to prevent resource leak
            if pdf is not None:
                pdf.close()

        return doc

    def _parse_page(
        self, page: "fitz.Page", page_num: int, start_line: int
    ) -> tuple[list[DocumentSection], list[CodeBlock]]:
        """
        Parse a single PDF page.

        Args:
            page: PyMuPDF page object
            page_num: Page number (1-indexed)
            start_line: Starting line number

        Returns:
            Tuple of (sections, code_blocks)
        """
        sections: list[DocumentSection] = []
        code_blocks: list[CodeBlock] = []

        current_line = start_line

        # 1. Extract text blocks
        text_sections = self._extract_text_blocks(page, page_num, current_line)
        sections.extend(text_sections)

        # Update line counter
        if text_sections:
            current_line = text_sections[-1].line_end + 1

        # 2. Extract tables (ADVANCED/SOTA)
        if self.extract_tables:
            table_sections = self._extract_tables(page, page_num, current_line)
            sections.extend(table_sections)
            if table_sections:
                current_line = table_sections[-1].line_end + 1

        # 3. Extract images (SOTA)
        if self.extract_images:
            image_sections = self._extract_images(page, page_num, current_line)
            sections.extend(image_sections)

        return sections, code_blocks

    def _extract_text_blocks(self, page: "fitz.Page", page_num: int, start_line: int) -> list[DocumentSection]:
        """
        Extract text blocks from page.

        Uses PyMuPDF's text extraction with layout preservation.
        """
        sections: list[DocumentSection] = []

        # Get text blocks with position info
        blocks = page.get_text("blocks")  # Returns list of (x0, y0, x1, y1, text, block_no, block_type)

        current_line = start_line

        for block in blocks:
            if len(block) < 5:
                continue

            x0, y0, x1, y1, text, block_no, block_type = block[:7]

            # Skip empty blocks
            text = text.strip()
            if not text:
                continue

            # Detect headings (larger font, bold, etc.)
            # Simple heuristic: if line is short and all caps or title case, treat as heading
            is_heading = self._is_heading(text)

            if is_heading:
                section_type = SectionType.HEADING
                # Estimate heading level based on font size (we'd need more analysis)
                level = 2  # Default
            else:
                section_type = SectionType.PARAGRAPH

            line_count = len(text.split("\n"))

            sections.append(
                DocumentSection(
                    section_type=section_type,
                    content=text,
                    level=level if is_heading else None,
                    line_start=current_line,
                    line_end=current_line + line_count - 1,
                    metadata={
                        "page": page_num,
                        "block_no": block_no,
                        "bbox": (x0, y0, x1, y1),
                    },
                )
            )

            current_line += line_count

        return sections

    def _extract_tables(self, page: "fitz.Page", page_num: int, start_line: int) -> list[DocumentSection]:
        """
        Extract tables from page using pdfplumber.

        Falls back to simple heuristics if pdfplumber is not available.
        """
        sections: list[DocumentSection] = []

        if not PDFPLUMBER_AVAILABLE:
            # Fallback to simple heuristic
            return self._extract_tables_fallback(page, page_num, start_line)

        current_line = start_line

        try:
            # Use pdfplumber for accurate table extraction
            import pdfplumber

            # Open the PDF page with pdfplumber
            pdf_path = page.parent.name
            with pdfplumber.open(pdf_path) as pdf:
                if page_num - 1 < len(pdf.pages):
                    plumber_page = pdf.pages[page_num - 1]

                    # Extract tables
                    tables = plumber_page.extract_tables()

                    for table_idx, table in enumerate(tables):
                        if not table:
                            continue

                        # Convert table to markdown format
                        table_text = self._format_table_as_markdown(table)

                        if table_text.strip():
                            line_count = len(table_text.split("\n"))

                            sections.append(
                                DocumentSection(
                                    section_type=SectionType.RAW,
                                    content=table_text,
                                    line_start=current_line,
                                    line_end=current_line + line_count - 1,
                                    metadata={
                                        "page": page_num,
                                        "type": "table",
                                        "table_index": table_idx,
                                        "rows": len(table),
                                        "cols": len(table[0]) if table else 0,
                                    },
                                )
                            )
                            current_line += line_count

        except Exception:
            # Table extraction failed, try fallback
            return self._extract_tables_fallback(page, page_num, start_line)

        return sections

    def _extract_tables_fallback(self, page: "fitz.Page", page_num: int, start_line: int) -> list[DocumentSection]:
        """
        Fallback table extraction using PyMuPDF text positioning.
        """
        sections: list[DocumentSection] = []
        current_line = start_line

        try:
            text_dict = page.get_text("dict")
            blocks = text_dict.get("blocks", [])

            for block in blocks:
                if block.get("type") == 0:  # Text block
                    lines = block.get("lines", [])

                    if len(lines) > 3:
                        table_text = "\n".join(
                            " ".join(span["text"] for span in line.get("spans", [])) for line in lines
                        )

                        if table_text.strip():
                            line_count = len(table_text.split("\n"))

                            sections.append(
                                DocumentSection(
                                    section_type=SectionType.RAW,
                                    content=table_text,
                                    line_start=current_line,
                                    line_end=current_line + line_count - 1,
                                    metadata={
                                        "page": page_num,
                                        "type": "table_candidate",
                                    },
                                )
                            )
                            current_line += line_count

        except Exception:
            pass

        return sections

    def _format_table_as_markdown(self, table: list[list[str]]) -> str:
        """
        Format extracted table as Markdown.

        Args:
            table: List of rows, each row is a list of cell values

        Returns:
            Markdown formatted table
        """
        if not table:
            return ""

        lines = []

        # Header row
        header = table[0]
        header_line = "| " + " | ".join(str(cell or "") for cell in header) + " |"
        lines.append(header_line)

        # Separator
        separator = "| " + " | ".join("---" for _ in header) + " |"
        lines.append(separator)

        # Data rows
        for row in table[1:]:
            row_line = "| " + " | ".join(str(cell or "") for cell in row) + " |"
            lines.append(row_line)

        return "\n".join(lines)

    def _extract_images(self, page: "fitz.Page", page_num: int, start_line: int) -> list[DocumentSection]:
        """
        Extract image metadata from page.

        For SOTA profile, we extract image info and can optionally run OCR.
        """
        sections: list[DocumentSection] = []

        current_line = start_line

        try:
            # Get list of images on page
            image_list = page.get_images(full=True)

            for img_index, img_info in enumerate(image_list):
                xref = img_info[0]  # Image reference number

                # Get image metadata
                base_image = page.parent.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                width = base_image.get("width", 0)
                height = base_image.get("height", 0)

                # Create section for image metadata
                content = f"[IMAGE: {image_ext.upper()} {width}x{height}px]"
                line_count = 1

                # Run OCR on image for SOTA profile
                if self.extract_images and image_bytes:
                    ocr_text = self._run_ocr(image_bytes)
                    if ocr_text:
                        content += f"\n[OCR_TEXT]\n{ocr_text}"
                        # Update line count for OCR text
                        line_count += 2 + len(ocr_text.split("\n"))

                sections.append(
                    DocumentSection(
                        section_type=SectionType.RAW,
                        content=content,
                        line_start=current_line,
                        line_end=current_line + line_count - 1,
                        metadata={
                            "page": page_num,
                            "type": "image",
                            "image_index": img_index,
                            "xref": xref,
                            "format": image_ext,
                            "width": width,
                            "height": height,
                        },
                    )
                )

                current_line += line_count

        except Exception:
            # Image extraction failed, skip
            pass

        return sections

    def _is_heading(self, text: str) -> bool:
        """
        Heuristic to detect if text is a heading.

        Checks:
        - Short length (< 100 chars)
        - Title case or all caps
        - No ending punctuation
        """
        if len(text) > 100:
            return False

        # Remove whitespace
        text = text.strip()

        # Check for title case or all caps
        is_title_case = text.istitle()
        is_upper = text.isupper() and len(text.split()) <= 6

        # Check no ending punctuation (except :)
        ends_with_period = text.endswith(".")

        return (is_title_case or is_upper) and not ends_with_period

    def _run_ocr(self, image_bytes: bytes) -> str:
        """
        Run OCR on image bytes.

        Requires pytesseract for SOTA profile.
        """
        try:
            import io

            import pytesseract
            from PIL import Image

            # Convert bytes to PIL Image
            image = Image.open(io.BytesIO(image_bytes))

            # Run OCR
            text = pytesseract.image_to_string(image)

            return text.strip()

        except ImportError:
            # pytesseract not available
            return ""
        except Exception:
            # OCR failed
            return ""
