"""
IR Stage - Intermediate Representation Building

Stage 4: Build IR from AST results
Stage 5: Build Semantic IR (CFG, DFG, types)
"""

from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from typing import Any

from codegraph_engine.analysis_indexing.infrastructure.models import IndexingStage
from codegraph_engine.code_foundation.infrastructure.profiling import Profiler
from codegraph_shared.infra.observability import get_logger, record_counter

from .base import BaseStage, StageContext

logger = get_logger(__name__)


class IRStage(BaseStage):
    """IR Building Stage"""

    stage_name = IndexingStage.IR_BUILDING

    def __init__(self, components: Any = None):
        super().__init__(components)
        self.ir_builder = getattr(components, "ir_builder", None)
        self.config = getattr(components, "config", None)
        self.project_root = getattr(components, "project_root", None)
        self._profiler = getattr(components, "profiler", None)

    async def execute(self, ctx: StageContext) -> None:
        """Execute IR building stage using LayeredIRBuilder."""
        stage_start = datetime.now()
        profiler = ctx.profiler or self._profiler

        logger.info("ir_building_started")

        # Use LayeredIRBuilder for SOTA 9-layer IR
        if self.ir_builder and hasattr(self.ir_builder, "build"):
            await self._build_ir_layered(ctx, profiler)
        else:
            # Fallback to legacy _build_ir
            with profiler.phase("ir_building") if profiler else nullcontext():
                ir_doc, ast_map = await self._build_ir(
                    ctx.ast_results,
                    ctx.repo_id,
                    ctx.snapshot_id,
                    repo_path=ctx.repo_path,
                    profiler=profiler,
                )

            if ir_doc:
                ctx.result.ir_nodes_created = len(getattr(ir_doc, "nodes", []))
                logger.info("ir_nodes_created", count=ctx.result.ir_nodes_created)
                record_counter("ir_nodes_created_total", value=ctx.result.ir_nodes_created)
                await self._save_ir_document(ir_doc, ctx)

            ctx.ir_doc = ir_doc
            ctx._ast_map = ast_map

        self._record_duration(ctx, stage_start)

    async def _build_ir_layered(self, ctx: StageContext, profiler: Profiler | None) -> None:
        """Build IR using LayeredIRBuilder (SOTA 9-layer)."""
        from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig, SemanticTier

        # Extract file list from ast_results
        files = [Path(file_path) for file_path in ctx.ast_results.keys()]

        logger.info(f"Building IR with LayeredIRBuilder for {len(files)} files...")

        # Configure layers (using defaults for now)
        config = BuildConfig(
            semantic_tier=SemanticTier.FULL,
            occurrences=True,
            cross_file=True,
            retrieval_index=True,
            parallel_workers=4,
        )

        # Build IR
        with profiler.phase("layered_ir_build") if profiler else nullcontext():
            result = await self.ir_builder.build(files=files, config=config)

        # Extract results
        ir_documents = result.ir_documents

        # Aggregate stats
        total_nodes = sum(len(doc.nodes) for doc in ir_documents.values())
        total_edges = sum(len(doc.edges) for doc in ir_documents.values())

        ctx.result.ir_nodes_created = total_nodes
        logger.info("ir_nodes_created", count=total_nodes, files=len(ir_documents))
        record_counter("ir_nodes_created_total", value=total_nodes)

        # Store first document as ir_doc (for backward compatibility)
        ctx.ir_doc = next(iter(ir_documents.values())) if ir_documents else None
        ctx.ir_documents = ir_documents  # Store all documents
        ctx._ast_map = {}  # Not needed with LayeredIRBuilder

    async def _save_ir_document(self, ir_doc, ctx) -> None:
        """
        Save IR Document to store (RFC-027 Integration).

        SOTA 원칙:
        - Lazy DI (container 나중에 로드)
        - Error handling (실패해도 파이프라인 계속)
        - Performance (비동기 저장)
        """
        try:
            # Lazy import (circular dependency 방지)
            if not hasattr(self, "_ir_document_store"):
                from src.container import container

                # IndexingContainer → ir_document_store
                self._ir_document_store = container._indexing.ir_document_store

            # 비동기 저장
            saved = await self._ir_document_store.save(ir_doc)

            if saved:
                logger.info(
                    "ir_document_stored",
                    repo_id=ir_doc.repo_id,
                    snapshot_id=ir_doc.snapshot_id,
                    node_count=len(ir_doc.nodes),
                )
            else:
                logger.warning("ir_document_save_failed", repo_id=ir_doc.repo_id)

        except Exception as e:
            # Never fail the pipeline
            logger.error(
                "ir_document_save_error",
                repo_id=ir_doc.repo_id,
                error=str(e),
                exc_info=True,
            )

    async def _build_ir(
        self,
        ast_results: dict,
        repo_id: str,
        snapshot_id: str,
        repo_path: Path | None = None,
        profiler: Profiler | None = None,
    ):
        """Build IR from AST results."""
        from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.error_handling import (
            ErrorCategory,
            PipelineErrorHandler,
            create_ir_error_context,
        )
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.source_map import (
            FullSourceMap,
            create_source_map_from_results,
        )
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.validation import IRValidator

        error_handler = PipelineErrorHandler()

        # Create type-safe source map
        source_map: FullSourceMap = create_source_map_from_results(
            ast_results=ast_results,
            repo_root=self.project_root or repo_path,
            language="python",
        )

        logger.info(f"Building IR for {len(source_map)} files...")

        all_nodes = []
        all_edges = []
        failed_files = []

        for file_path, (source_file, ast_tree) in source_map.items():
            try:
                with profiler.phase(f"ir_gen:{file_path.name}") if profiler else nullcontext():
                    ir_doc = self.ir_builder.generate(
                        source=source_file,
                        snapshot_id=snapshot_id,
                        ast=ast_tree,
                    )

                if ir_doc:
                    all_nodes.extend(ir_doc.nodes)
                    all_edges.extend(ir_doc.edges)
                    if profiler:
                        profiler.increment("ir_nodes_total", len(ir_doc.nodes))
                        profiler.increment("ir_edges_total", len(ir_doc.edges))

            except Exception as e:
                context = create_ir_error_context(file_path, "generate_ir", e)
                error_handler.handle(e, ErrorCategory.IR_GENERATION, context, logger)
                failed_files.append(file_path)

                if self.config and not self.config.continue_on_error:
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


class SemanticIRStage(BaseStage):
    """Semantic IR Building Stage (CFG, DFG, types)"""

    stage_name = IndexingStage.SEMANTIC_IR_BUILDING

    def __init__(self, components: Any = None):
        super().__init__(components)
        self.ir_builder = getattr(components, "ir_builder", None)
        self.semantic_ir_builder = getattr(components, "semantic_ir_builder", None)
        self.pyright_daemon_factory = getattr(components, "pyright_daemon_factory", None)
        self.project_root = getattr(components, "project_root", None)

        # RFC-028: Cost Analyzer (DI, optional)
        self.cost_analyzer = getattr(components, "cost_analyzer", None)

    async def execute(self, ctx: StageContext) -> None:
        """Execute semantic IR building stage."""
        stage_start = datetime.now()

        logger.info("semantic_ir_building_started")

        semantic_ir = await self._build_semantic_ir(
            ctx.ir_doc,
            ast_map=getattr(ctx, "_ast_map", {}),
            incremental=ctx.is_incremental,
        )

        ctx.semantic_ir = semantic_ir

        # Clear temp ast_map
        if hasattr(ctx, "_ast_map"):
            delattr(ctx, "_ast_map")

        # RFC-028: Real-time Cost Analysis (optional)
        if self.cost_analyzer and ctx.config and getattr(ctx.config, "enable_realtime_analysis", False):
            await self._run_cost_analysis(ctx)

        logger.info("semantic_ir_building_completed")
        self._record_duration(ctx, stage_start)

    async def _build_semantic_ir(self, ir_doc, ast_map=None, incremental=False):
        """Build semantic IR with optional Pyright integration."""
        from codegraph_shared.config import settings

        ast_map = ast_map or {}

        if settings.enable_pyright and self.pyright_daemon_factory and self.project_root:
            logger.info("Using Pyright for semantic analysis")
            try:
                pyright_daemon = self.pyright_daemon_factory(self.project_root)

                from codegraph_engine.code_foundation.infrastructure.semantic_ir.semantic_ir_builder import (
                    SemanticIRBuilder,
                )

                pyright_builder = SemanticIRBuilder(
                    ir_generator=self.ir_builder,
                    pyright_daemon=pyright_daemon,
                )

                semantic_snapshot, semantic_index = pyright_builder.build_full(ir_doc, source_map=ast_map)
                logger.info("Pyright semantic analysis complete")

                return {"snapshot": semantic_snapshot, "index": semantic_index}

            except Exception as e:
                logger.warning(f"Pyright failed ({e}), falling back to internal types")
                semantic_snapshot, semantic_index = self.semantic_ir_builder.build_full(ir_doc, source_map=ast_map)
        else:
            semantic_snapshot, semantic_index = self.semantic_ir_builder.build_full(ir_doc, source_map=ast_map)

        return {"snapshot": semantic_snapshot, "index": semantic_index}

    async def _run_cost_analysis(self, ctx: StageContext) -> None:
        """
        Run real-time cost analysis (RFC-028 Point 1)

        Target: <100ms per function (incremental only)

        Args:
            ctx: Stage context
        """
        if not ctx.ir_doc:
            return

        logger.info("cost_analysis_realtime_started")

        try:
            # Get changed functions (incremental only)
            if ctx.is_incremental and ctx.change_set:
                # Incremental: analyze changed functions only
                changed_functions = getattr(ctx.change_set, "changed_functions", [])
                if not changed_functions:
                    logger.debug("No changed functions, skipping cost analysis")
                    return
            else:
                # Full indexing: Skip (too slow)
                logger.debug("Full indexing mode, skipping real-time cost analysis")
                return

            # Analyze each changed function
            cost_results = {}
            for func_fqn in changed_functions[:10]:  # Limit to 10 (performance)
                try:
                    result = self.cost_analyzer.analyze_function(ctx.ir_doc, func_fqn, request_id=ctx.snapshot_id)
                    cost_results[func_fqn] = result

                    # Log slow functions
                    if result.is_slow():
                        logger.warning(
                            f"Performance issue detected: {func_fqn} → {result.complexity.value}",
                            function=func_fqn,
                            complexity=result.complexity.value,
                            verdict=result.verdict,
                        )

                except Exception as e:
                    logger.warning(f"Cost analysis failed for {func_fqn}: {e}")
                    continue

            # Store results in context
            if not hasattr(ctx, "analysis_results"):
                ctx.analysis_results = {}
            ctx.analysis_results["cost"] = cost_results

            logger.info(
                "cost_analysis_realtime_completed",
                functions_analyzed=len(cost_results),
                slow_functions=sum(1 for r in cost_results.values() if r.is_slow()),
            )

        except Exception as e:
            # Non-blocking: Cost analysis failure should not break indexing
            logger.error(f"Cost analysis failed: {e}", exc_info=True)
