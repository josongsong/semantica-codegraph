"""
IR Building Handler for Indexing Pipeline

Stage 4: Build Intermediate Representation (IR) from AST
Stage 5: Build Semantic IR (CFG, DFG, types, signatures)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.contexts.analysis_indexing.infrastructure.handlers.base import BaseHandler, HandlerContext
from src.contexts.analysis_indexing.infrastructure.models import IndexingResult, IndexingStage
from src.infra.observability import get_logger, record_counter
from src.pipeline.decorators import stage_execution

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.builder import IRBuilder
    from src.contexts.code_foundation.infrastructure.semantic_ir.builder import SemanticIrBuilder

logger = get_logger(__name__)


class IRBuildingHandler(BaseHandler):
    """
    Stage 4-5: Build IR and Semantic IR.

    Stage 4: IR Building
    - Converts AST to language-neutral Intermediate Representation
    - Creates IRDocument with nodes and edges

    Stage 5: Semantic IR Building
    - Builds CFG, DFG, types, signatures
    - Optionally uses Pyright for external type analysis (RFC-023)
    """

    stage = IndexingStage.IR_BUILDING

    def __init__(
        self,
        ir_builder: IRBuilder,
        semantic_ir_builder: SemanticIrBuilder,
        config: Any,
        container: Any = None,
    ):
        """
        Initialize IR building handler.

        Args:
            ir_builder: IR builder for AST->IR conversion
            semantic_ir_builder: Semantic IR builder for CFG/DFG/types
            config: IndexingConfig
            container: Optional DI container for Pyright integration
        """
        super().__init__()
        self.ir_builder = ir_builder
        self.semantic_ir_builder = semantic_ir_builder
        self.config = config
        self.container = container

        # Temporary storage for AST map (between stages)
        self._temp_ast_map: dict = {}

    @stage_execution(IndexingStage.IR_BUILDING)
    async def execute_ir_building(
        self,
        ctx: HandlerContext,
        result: IndexingResult,
        ast_results: dict[str, Any],
    ) -> tuple[Any, dict]:
        """
        Execute Stage 4: IR Building.

        Args:
            ctx: Handler context
            result: Indexing result to update
            ast_results: Dictionary mapping file paths to AST trees

        Returns:
            Tuple of (IRDocument, source_map)
        """
        logger.info("ir_building_started")

        ir_doc, source_map = await self._build_ir(
            ast_results,
            ctx.repo_id,
            ctx.snapshot_id,
            ctx.project_root,
        )

        if ir_doc:
            result.ir_nodes_created = len(getattr(ir_doc, "nodes", []))
            logger.info("ir_nodes_created", count=result.ir_nodes_created)
            record_counter("ir_nodes_created_total", value=result.ir_nodes_created)

        # Store AST map for semantic IR stage
        self._temp_ast_map = source_map

        return ir_doc, source_map

    @stage_execution(IndexingStage.SEMANTIC_IR_BUILDING)
    async def execute_semantic_ir_building(
        self,
        ctx: HandlerContext,
        result: IndexingResult,
        ir_doc: Any,
    ) -> dict[str, Any] | None:
        """
        Execute Stage 5: Semantic IR Building.

        Args:
            ctx: Handler context
            result: Indexing result to update
            ir_doc: IRDocument from Stage 4

        Returns:
            Dictionary with "snapshot" and "index" keys
        """
        logger.info("semantic_ir_building_started")

        semantic_ir = await self._build_semantic_ir(
            ir_doc,
            ctx.project_root,
            incremental=result.incremental,
        )

        logger.info("semantic_ir_building_completed")

        return semantic_ir

    async def _build_ir(
        self,
        ast_results: dict[str, Any],
        repo_id: str,
        snapshot_id: str,
        project_root: Path | None,
    ) -> tuple[Any, dict]:
        """
        Build IR from AST results.

        Uses type-safe FullSourceMap with integrated error handling.
        """
        from src.contexts.code_foundation.infrastructure.ir.models import IRDocument
        from src.contexts.code_foundation.infrastructure.semantic_ir.error_handling import (
            ErrorCategory,
            PipelineErrorHandler,
            create_ir_error_context,
        )
        from src.contexts.code_foundation.infrastructure.semantic_ir.source_map import (
            FullSourceMap,
            create_source_map_from_results,
        )
        from src.contexts.code_foundation.infrastructure.semantic_ir.validation import IRValidator

        error_handler = PipelineErrorHandler()

        # Create type-safe source map
        source_map: FullSourceMap = create_source_map_from_results(
            ast_results=ast_results,
            repo_root=project_root,
            language="python",
        )

        logger.info(f"Building IR for {len(source_map)} files...")

        all_nodes = []
        all_edges = []
        failed_files = []

        for file_path, (source_file, ast_tree) in source_map.items():
            try:
                ir_doc = self.ir_builder.generate(
                    source=source_file,
                    snapshot_id=snapshot_id,
                    ast=ast_tree,
                )

                if ir_doc:
                    all_nodes.extend(ir_doc.nodes)
                    all_edges.extend(ir_doc.edges)

            except Exception as e:
                context = create_ir_error_context(file_path, "generate_ir", e)
                error_handler.handle(e, ErrorCategory.IR_GENERATION, context, logger)
                failed_files.append(file_path)

                if not self.config.continue_on_error:
                    raise

        if all_nodes:
            ir_document = IRDocument(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                schema_version="4.1.0",
                nodes=all_nodes,
                edges=all_edges,
            )

            validation_result = IRValidator.validate(ir_document)
            if validation_result.has_errors:
                logger.error(f"IR validation failed: {validation_result}")

            logger.info(f"IR built: {len(all_nodes)} nodes, {len(all_edges)} edges ({len(failed_files)} failed files)")

            return ir_document, source_map

        logger.warning("No IR nodes generated")
        return None, {}

    async def _build_semantic_ir(
        self,
        ir_doc: Any,
        project_root: Path | None,
        incremental: bool = False,
    ) -> dict[str, Any] | None:
        """
        Build semantic IR.

        Uses Pyright for external type analysis if enabled (RFC-023).
        Falls back to internal type inference otherwise.
        """
        from src.config import settings

        ast_map = self._temp_ast_map

        if settings.enable_pyright and self.container and project_root:
            logger.info("Using Pyright for semantic analysis")
            try:
                pyright_builder = self.container.create_semantic_ir_builder_with_pyright(project_root)
                semantic_snapshot, semantic_index = pyright_builder.build_full(ir_doc, source_map=ast_map)

                logger.info("   Pyright semantic analysis complete")

                await self._persist_pyright_snapshot(
                    ir_doc,
                    pyright_builder.external_analyzer,
                    incremental=incremental,
                )

            except Exception as e:
                logger.warning(f"Pyright failed ({e}), falling back to internal types")
                semantic_snapshot, semantic_index = self.semantic_ir_builder.build_full(ir_doc, source_map=ast_map)
        else:
            semantic_snapshot, semantic_index = self.semantic_ir_builder.build_full(ir_doc, source_map=ast_map)

        # Clear temp AST map
        self._temp_ast_map = {}

        return {"snapshot": semantic_snapshot, "index": semantic_index}

    async def _persist_pyright_snapshot(
        self,
        ir_doc: Any,
        pyright_analyzer: Any,
        incremental: bool = False,
    ) -> None:
        """
        Persist Pyright semantic snapshot to PostgreSQL.

        RFC-023 M1: Save PyrightSemanticSnapshot for future incremental updates.
        RFC-023 M2: Support incremental updates using ChangeDetector.
        """
        try:
            snapshot_store = self.container.semantic_snapshot_store
            file_locations = self._extract_ir_locations(ir_doc)

            if not file_locations:
                logger.warning("No IR locations found, skipping snapshot persist")
                return

            if incremental:
                pyright_snapshot = await self._persist_incremental_snapshot(
                    ir_doc, pyright_analyzer, file_locations, snapshot_store
                )
            else:
                logger.info("Full Pyright snapshot export...")
                pyright_snapshot = pyright_analyzer.export_semantic_for_files(file_locations)

            if pyright_snapshot:
                await snapshot_store.save_snapshot(pyright_snapshot)
                logger.info(
                    f"Saved Pyright snapshot: {pyright_snapshot.snapshot_id} "
                    f"({len(pyright_snapshot.files)} files, "
                    f"{len(pyright_snapshot.typing_info)} types)"
                )

        except Exception as e:
            logger.warning(f"Failed to persist Pyright snapshot: {e}")

    async def _persist_incremental_snapshot(
        self,
        ir_doc: Any,
        pyright_analyzer: Any,
        file_locations: dict,
        snapshot_store: Any,
    ) -> Any:
        """Handle incremental Pyright snapshot update."""
        logger.info("Incremental Pyright snapshot update...")

        try:
            # This would need project_root from context
            # For now, fall back to full export
            logger.info("Incremental update - falling back to full export")
            return pyright_analyzer.export_semantic_for_files(file_locations)

        except Exception as e:
            logger.warning(f"Incremental update failed: {e}")
            return pyright_analyzer.export_semantic_for_files(file_locations)

    def _extract_ir_locations(self, ir_doc: Any) -> dict[Path, list[tuple[int, int]]]:
        """
        Extract file locations from IR document for Pyright analysis.

        Returns:
            Dict mapping file paths to list of (line, col) tuples
        """
        file_locations_sets: dict[Path, set[tuple[int, int]]] = {}

        for node in ir_doc.nodes:
            if not hasattr(node, "span") or not node.span or not node.span.file_path:
                continue

            file_path = Path(node.span.file_path)
            line = node.span.start_line
            col = node.span.start_column

            if file_path not in file_locations_sets:
                file_locations_sets[file_path] = set()

            file_locations_sets[file_path].add((line, col))

        return {path: sorted(locations) for path, locations in file_locations_sets.items()}
