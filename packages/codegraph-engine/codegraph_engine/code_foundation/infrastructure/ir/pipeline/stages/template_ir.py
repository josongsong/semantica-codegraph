"""L5.5: Template IR Stage (JSX/TSX/Vue)

Parses JSX/TSX/Vue templates and links them to CodeIR.

SOTA Features:
- Reuses existing Python implementation (jsx_template_parser, vue_sfc_parser)
- Template → Code linking (BINDS, RENDERS, ESCAPES edges)
- Support for React JSX/TSX and Vue SFC

Performance: ~5ms/file (only JSX/TSX/Vue files)
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from codegraph_shared.infra.logging import get_logger

from ..protocol import PipelineStage, StageContext

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models.ir_document import IRDocument

logger = get_logger(__name__)


class TemplateIRStage(PipelineStage[dict[str, "IRDocument"]]):
    """L5.5: Template IR Stage

    Parses JSX/TSX/Vue templates and links them to CodeIR.

    Features:
    - JSX/TSX template parsing (React)
    - Vue SFC template parsing (Vue.js)
    - Template → Code linking with edges:
        - BINDS: Template slots → Code variables
        - RENDERS: Code → Template elements
        - ESCAPES: User input → Template output (XSS detection)

    Example:
        ```python
        stage = TemplateIRStage(enabled=True)
        ctx = await stage.execute(ctx)
        # ctx.ir_documents now have template nodes/edges
        ```

    Performance:
    - Only processes JSX/TSX/Vue files (~5-10% of total files)
    - ~5ms/file (tree-sitter parsing + linking)
    """

    def __init__(self, enabled: bool = True):
        """Initialize template IR stage.

        Args:
            enabled: Enable template IR processing
        """
        self.enabled = enabled
        self._jsx_parser = None
        self._vue_parser = None
        self._template_linker = None

    async def execute(self, ctx: StageContext) -> StageContext:
        """Parse and link templates to CodeIR.

        Strategy:
        1. Identify JSX/TSX/Vue files
        2. Parse templates with tree-sitter
        3. Link templates to CodeIR (BINDS, RENDERS, ESCAPES)
        4. Update IR documents with template nodes/edges

        Performance: ~5ms/file (only JSX/TSX/Vue files)
        """
        if not self.enabled:
            return ctx

        if not ctx.ir_documents:
            logger.warning("No IR documents for template processing")
            return ctx

        logger.info("Building Template IR for JSX/TSX/Vue files...")

        # Lazy init parsers
        jsx_parser = self._get_jsx_parser()
        vue_parser = self._get_vue_parser()
        template_linker = self._get_template_linker()

        # Process files
        template_count = 0
        slot_count = 0
        jsx_file_count = 0
        vue_file_count = 0

        updated_irs = {}

        for file_path, ir_doc in ctx.ir_documents.items():
            file_path_obj = Path(file_path) if isinstance(file_path, str) else file_path

            # Identify file type
            if file_path_obj.suffix in [".tsx", ".jsx"]:
                parser = jsx_parser
                file_type = "JSX"
                jsx_file_count += 1
            elif file_path_obj.suffix == ".vue":
                parser = vue_parser
                file_type = "Vue"
                vue_file_count += 1
            else:
                # Not a template file, keep as-is
                updated_irs[file_path] = ir_doc
                continue

            try:
                logger.debug(f"Processing {file_type} file: {file_path}")

                # Step 1: Parse template (tree-sitter)
                # Get source code (from file or cache)
                source_code = self._get_source_code(file_path_obj)
                if not source_code:
                    logger.warning(f"Could not read source for {file_path}")
                    updated_irs[file_path] = ir_doc
                    continue

                template_ir = parser.parse(source_code, str(file_path_obj))

                if not template_ir:
                    logger.debug(f"No templates found in {file_path}")
                    updated_irs[file_path] = ir_doc
                    continue

                # Step 2: Link template to CodeIR
                binds_edges, renders_edges, escapes_edges = template_linker.link(ir_doc, template_ir)

                # Step 3: Update IR document
                # Add template nodes
                ir_doc.nodes.extend(template_ir.nodes)

                # Add linking edges
                ir_doc.edges.extend(binds_edges)
                ir_doc.edges.extend(renders_edges)
                ir_doc.edges.extend(escapes_edges)

                # Track stats
                template_count += len(template_ir.templates)
                slot_count += len(template_ir.slots)

                updated_irs[file_path] = ir_doc

            except Exception as e:
                logger.warning(f"Template IR failed for {file_path}: {e}")
                # Keep original IR on error
                updated_irs[file_path] = ir_doc

        logger.info(
            f"Template IR complete: {template_count} templates "
            f"({jsx_file_count} JSX, {vue_file_count} Vue), "
            f"{slot_count} slots extracted"
        )

        return replace(ctx, ir_documents=updated_irs)

    def should_skip(self, ctx: StageContext) -> tuple[bool, str | None]:
        """Skip if disabled or no IR documents."""
        if not self.enabled:
            return True, "Template IR disabled"

        if not ctx.ir_documents:
            return True, "No IR documents to process"

        # Check if any JSX/TSX/Vue files
        has_template_files = any(Path(fp).suffix in [".tsx", ".jsx", ".vue"] for fp in ctx.ir_documents.keys())

        if not has_template_files:
            return True, "No JSX/TSX/Vue files to process"

        return False, None

    def _get_jsx_parser(self):
        """Get or create JSX parser (lazy init)."""
        if self._jsx_parser is None:
            try:
                from codegraph_engine.code_foundation.infrastructure.parsers.jsx_template_parser import (
                    create_jsx_parser,
                )

                self._jsx_parser = create_jsx_parser()
            except ImportError as e:
                raise RuntimeError(f"Failed to import jsx_template_parser: {e}") from e

        return self._jsx_parser

    def _get_vue_parser(self):
        """Get or create Vue parser (lazy init)."""
        if self._vue_parser is None:
            try:
                from codegraph_engine.code_foundation.infrastructure.parsers.vue_sfc_parser import (
                    create_vue_parser,
                )

                self._vue_parser = create_vue_parser()
            except ImportError as e:
                raise RuntimeError(f"Failed to import vue_sfc_parser: {e}") from e

        return self._vue_parser

    def _get_template_linker(self):
        """Get or create template linker (lazy init)."""
        if self._template_linker is None:
            try:
                from codegraph_engine.code_foundation.infrastructure.linkers.template_linker import (
                    create_template_linker,
                )

                self._template_linker = create_template_linker()
            except ImportError as e:
                raise RuntimeError(f"Failed to import template_linker: {e}") from e

        return self._template_linker

    def _get_source_code(self, file_path: Path) -> str | None:
        """Read source code from file.

        TODO: Reuse from ctx.source_cache if available.
        """
        try:
            if not file_path.exists():
                return None

            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            return None
