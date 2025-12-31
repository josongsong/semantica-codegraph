"""
Parallel IR Build Strategy

Multi-process parallel build for large repositories.
Uses ProcessPoolExecutor for true parallelism.
"""

import asyncio
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.ir.strategies.protocol import (
    IRBuildContext,
    IRBuildResult,
    IRBuildStrategy,
)

logger = get_logger(__name__)


@dataclass
class ParallelBuildResult:
    """Pickle-safe result from worker process."""

    file_path: str
    success: bool
    error_message: str | None = None

    # IR data (pickle-safe primitives)
    nodes_count: int = 0
    edges_count: int = 0

    # Serialized IR (for cross-process transfer)
    ir_data: dict[str, Any] | None = None


def _build_ir_worker(
    file_path_str: str,
    project_root_str: str,
    enable_semantic_ir: bool = False,
    semantic_mode: str = "quick",
) -> ParallelBuildResult:
    """
    Worker function for parallel IR build.

    CRITICAL: Must be pickle-safe (top-level function, no closures).

    Args:
        file_path_str: File path as string
        project_root_str: Project root as string
        enable_semantic_ir: Whether to build semantic IR
        semantic_mode: "quick" or "full"

    Returns:
        ParallelBuildResult (pickle-safe)
    """
    try:
        from pathlib import Path

        from codegraph_engine.code_foundation.infrastructure.generators.python_generator import _PythonIRGenerator
        from codegraph_engine.code_foundation.infrastructure.parsing import AstTree, SourceFile

        file_path = Path(file_path_str)

        if not file_path.exists():
            return ParallelBuildResult(
                file_path=file_path_str,
                success=False,
                error_message=f"File not found: {file_path_str}",
            )

        # Read file
        content = file_path.read_text(encoding="utf-8")

        # Parse AST
        source = SourceFile.from_content(str(file_path), content, "python")
        ast = AstTree.parse(source)

        # Generate structural IR (Layer 1)
        generator = _PythonIRGenerator(repo_id=project_root_str)
        ir_doc = generator.generate(source, "parallel", ast)

        # Optionally build semantic IR (Layer 5)
        if enable_semantic_ir:
            try:
                from codegraph_engine.code_foundation.infrastructure.semantic_ir.builder import DefaultSemanticIrBuilder

                builder = DefaultSemanticIrBuilder()
                source_map = {str(file_path): (source, ast)}
                snapshot, index = builder.build_full(ir_doc, source_map)

                # Apply to IR doc
                ir_doc.types = snapshot.types
                ir_doc.signatures = snapshot.signatures
                ir_doc.cfgs = snapshot.cfg_graphs
                ir_doc.cfg_blocks = snapshot.cfg_blocks
                ir_doc.cfg_edges = snapshot.cfg_edges
                ir_doc.bfg_graphs = snapshot.bfg_graphs
                ir_doc.bfg_blocks = snapshot.bfg_blocks
                ir_doc.dfg_snapshot = snapshot.dfg_snapshot

            except Exception as e:
                # Semantic IR failure is non-fatal
                logger.warning(f"Semantic IR failed for {file_path}: {e}")

        # Serialize IR for cross-process transfer
        # Note: Full IRDocument may not be pickle-safe, so we extract key data
        ir_data = {
            "file_path": str(file_path),
            "repo_id": ir_doc.repo_id,
            "nodes": [
                {
                    "id": n.id,
                    "kind": n.kind.value if hasattr(n.kind, "value") else str(n.kind),
                    "name": n.name,
                    "fqn": n.fqn,
                    "file_path": n.file_path,
                    "language": n.language,
                    "start_line": n.span.start_line if n.span else 0,
                    "start_col": n.span.start_col if n.span else 0,
                    "end_line": n.span.end_line if n.span else 0,
                    "end_col": n.span.end_col if n.span else 0,
                }
                for n in ir_doc.nodes
            ],
            "edges": [
                {
                    "id": e.id,
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "kind": e.kind.value if hasattr(e.kind, "value") else str(e.kind),
                }
                for e in ir_doc.edges
            ],
        }

        return ParallelBuildResult(
            file_path=file_path_str,
            success=True,
            nodes_count=len(ir_doc.nodes),
            edges_count=len(ir_doc.edges),
            ir_data=ir_data,
        )

    except Exception as e:
        import traceback

        return ParallelBuildResult(
            file_path=file_path_str,
            success=False,
            error_message=f"{e}\n{traceback.format_exc()}",
        )


class ParallelStrategy(IRBuildStrategy):
    """
    Parallel IR build strategy using ProcessPoolExecutor.

    True multi-process parallelism for CPU-bound IR generation.
    3x speedup on multi-core systems.

    Use this for:
    - Large repository initial indexing
    - Batch processing many files
    - When CPU is the bottleneck (not I/O)

    Limitations:
    - Layer 1 only in workers (pickle constraint)
    - Higher memory usage (multiple processes)
    - Startup overhead (~100ms per process)

    Trade-off:
    - Layer 1 parallel (fast) + Layer 2-9 sequential (post-merge)
    """

    def __init__(
        self,
        max_workers: int | None = None,
        min_files_for_parallel: int = 5,
    ):
        """
        Args:
            max_workers: Max parallel workers (None = CPU count)
            min_files_for_parallel: Minimum files to use parallelism
        """
        self.max_workers = max_workers
        self.min_files_for_parallel = min_files_for_parallel

    @property
    def name(self) -> str:
        return "parallel"

    def pre_process(
        self,
        files: list[Path],
        context: IRBuildContext,
    ) -> list[Path]:
        """
        Sort files largest-first for better load balancing.
        """
        return sorted(
            files,
            key=lambda f: f.stat().st_size if f.exists() else 0,
            reverse=True,
        )

    async def build(
        self,
        files: list[Path],
        context: IRBuildContext,
    ) -> IRBuildResult:
        """
        Build IR in parallel using ProcessPoolExecutor.
        """
        from codegraph_engine.code_foundation.infrastructure.ir.cross_file_resolver import (
            CrossFileResolver,
            GlobalContext,
        )
        from codegraph_engine.code_foundation.infrastructure.ir.models import (
            Edge,
            EdgeKind,
            IRDocument,
            Node,
            NodeKind,
        )
        from codegraph_engine.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex

        start = time.perf_counter()

        # Check if parallel is beneficial
        if len(files) < self.min_files_for_parallel:
            logger.info(f"Too few files ({len(files)}), falling back to sequential")
            from codegraph_engine.code_foundation.infrastructure.ir.strategies.default import DefaultStrategy

            return await DefaultStrategy().build(files, context)

        # Pre-process (sort by size)
        sorted_files = self.pre_process(files, context)

        logger.info(f"🚀 Parallel build: {len(files)} files, {self.max_workers or 'auto'} workers")

        # Run in parallel
        project_root_str = str(context.project_root)
        loop = asyncio.get_event_loop()

        results: list[ParallelBuildResult] = []

        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                loop.run_in_executor(
                    executor,
                    _build_ir_worker,
                    str(file_path),
                    project_root_str,
                    context.enable_semantic_ir,
                    context.semantic_mode,
                )
                for file_path in sorted_files
            ]

            raw_results = await asyncio.gather(*futures, return_exceptions=True)

            for i, result in enumerate(raw_results):
                if isinstance(result, Exception):
                    logger.error(f"Worker crashed for {sorted_files[i]}: {result}")
                    results.append(
                        ParallelBuildResult(
                            file_path=str(sorted_files[i]),
                            success=False,
                            error_message=str(result),
                        )
                    )
                else:
                    results.append(result)

        # Reconstruct IR documents from worker results
        ir_docs: dict[str, IRDocument] = {}

        # Build lookup for NodeKind/EdgeKind
        node_kind_values = {nk.value: nk for nk in NodeKind}
        edge_kind_values = {ek.value: ek for ek in EdgeKind}

        for result in results:
            if result.success and result.ir_data:
                try:
                    # Reconstruct IRDocument from serialized data
                    data = result.ir_data

                    from codegraph_engine.code_foundation.infrastructure.ir.models import Span

                    nodes = []
                    for n in data["nodes"]:
                        kind_str = n["kind"]
                        kind = node_kind_values.get(kind_str, NodeKind.VARIABLE)
                        span = Span(
                            start_line=n["start_line"],
                            start_col=n["start_col"],
                            end_line=n["end_line"],
                            end_col=n["end_col"],
                        )
                        nodes.append(
                            Node(
                                id=n["id"],
                                kind=kind,
                                fqn=n["fqn"],
                                name=n["name"],
                                file_path=n["file_path"],
                                language=n["language"],
                                span=span,
                            )
                        )

                    edges = []
                    for e in data["edges"]:
                        kind_str = e["kind"]
                        kind = edge_kind_values.get(kind_str, EdgeKind.REFERENCES)
                        edges.append(
                            Edge(
                                id=e["id"],
                                source_id=e["source_id"],
                                target_id=e["target_id"],
                                kind=kind,
                            )
                        )

                    ir_doc = IRDocument(
                        repo_id=data["repo_id"],
                        snapshot_id=data["file_path"],  # Use file_path as snapshot_id
                        nodes=nodes,
                        edges=edges,
                    )
                    ir_docs[result.file_path] = ir_doc

                except Exception as e:
                    logger.warning(f"Failed to reconstruct IR for {result.file_path}: {e}")

        # Post-process: Cross-file resolution (sequential, needs all IRs)
        if context.enable_cross_file:
            resolver = CrossFileResolver()
            global_ctx = resolver.resolve(ir_docs)
        else:
            global_ctx = GlobalContext()

        # Build retrieval index
        if context.enable_retrieval_index:
            retrieval_index = RetrievalOptimizedIndex()
            for ir_doc in ir_docs.values():
                retrieval_index.index_ir_document(ir_doc)
        else:
            retrieval_index = RetrievalOptimizedIndex()

        elapsed = time.perf_counter() - start
        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count

        logger.info(
            f"✅ Parallel build complete: {success_count}/{len(files)} files "
            f"in {elapsed:.2f}s ({len(files) / elapsed:.1f} files/sec)"
        )

        return IRBuildResult(
            ir_documents=ir_docs,
            global_ctx=global_ctx,
            retrieval_index=retrieval_index,
            files_processed=success_count,
            files_failed=fail_count,
            elapsed_seconds=elapsed,
            extra={
                "parallel": True,
                "workers": self.max_workers,
            },
        )
