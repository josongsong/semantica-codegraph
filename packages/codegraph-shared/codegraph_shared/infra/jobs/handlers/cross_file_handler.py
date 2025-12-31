"""
Cross-File Resolution Handler (L3).

**Note**: This handler is being phased out in favor of Rust L3 pipeline.

As of v2.1.0, cross-file resolution is integrated into the Rust engine's
L3 stage (IRIndexingOrchestrator). This standalone handler is kept for
backward compatibility only.

**Recommended**: Use IRIndexingOrchestrator with enable_cross_file=True instead.

Legacy behavior:
- Receives IR from L1 (IR Build) and creates GlobalContext
- Rust implementation (12x faster): DashMap, Rayon, petgraph
- Fallback to Python implementation if Rust unavailable

Migration:
    # Before (separate L1 + L3 handlers)
    ir_result = await ir_handler.execute(payload)
    cross_file_result = await cross_file_handler.execute(payload)

    # After (integrated Rust pipeline)
    import codegraph_ir
    config = codegraph_ir.E2EPipelineConfig(
        root_path=repo_path,
        enable_cross_file=True,  # L3 included
    )
    result = orchestrator.execute()
    # result.global_context contains cross-file data

See: docs/adr/ADR-072-clean-rust-python-architecture.md
"""

import time
from typing import Any

from codegraph_shared.infra.jobs.handler import JobHandler, JobResult
from codegraph_shared.infra.jobs.handlers.config import (
    DEFAULT_CONFIG,
    ErrorCategory,
    ErrorCode,
    IndexingConfig,
)
from codegraph_shared.infra.observability.logging import get_logger

logger = get_logger(__name__)

# RFC-062: Try to import Rust accelerated implementation
try:
    import codegraph_ir.codegraph_ir as codegraph_ir_native

    RUST_AVAILABLE = hasattr(codegraph_ir_native, "build_global_context_py")
except ImportError:
    codegraph_ir_native = None
    RUST_AVAILABLE = False


class CrossFileHandler(JobHandler):
    """
    Cross-File Resolution Handler (Legacy).

    .. deprecated:: v2.1.0
        Use IRIndexingOrchestrator with enable_cross_file=True instead.
        This handler is kept for backward compatibility only.

    Payload:
        {
            "repo_id": "repo-123",
            "snapshot_id": "main",
            "ir_cache_key": "ir:repo-123:main",  # L1에서 생성된 IR 캐시 키
        }

    Result:
        {
            "total_symbols": 5000,
            "total_files": 100,
            "dependencies_resolved": 250,
            "global_ctx_key": "ctx:repo-123:main",
            "used_rust": true,  # Whether Rust implementation was used
        }

    Error Classification:
        - TRANSIENT: 일시적 메모리 부족
        - PERMANENT: IR 캐시 없음

    Migration:
        See module docstring for migration to Rust L3 pipeline.
    """

    def __init__(
        self,
        ir_cache: dict[str, Any] | None = None,
        global_ctx_cache: dict[str, Any] | None = None,
        config: IndexingConfig | None = None,
    ):
        """
        Args:
            ir_cache: IR 캐시 (L1에서 생성)
            global_ctx_cache: GlobalContext 결과 저장 캐시
            config: 인덱싱 설정
        """
        self.ir_cache = ir_cache if ir_cache is not None else {}
        self.global_ctx_cache = global_ctx_cache if global_ctx_cache is not None else {}
        self.config = config or DEFAULT_CONFIG

    async def execute(self, payload: dict[str, Any]) -> JobResult:
        """Cross-file resolution 실행."""
        repo_id = payload.get("repo_id")
        snapshot_id = payload.get("snapshot_id", self.config.defaults.snapshot_id)
        ir_cache_key = payload.get("ir_cache_key")

        # Validation
        if not repo_id:
            return JobResult.fail(
                error="Missing required field: repo_id",
                data={"error_code": ErrorCode.INVALID_PAYLOAD, "error_category": ErrorCategory.PERMANENT},
            )

        if not ir_cache_key:
            return JobResult.fail(
                error="Missing required field: ir_cache_key",
                data={"error_code": ErrorCode.INVALID_PAYLOAD, "error_category": ErrorCategory.PERMANENT},
            )

        # Get IR from cache
        ir_data = self.ir_cache.get(ir_cache_key)
        if not ir_data:
            return JobResult.fail(
                error=f"IR cache not found: {ir_cache_key}",
                data={"error_code": ErrorCode.CACHE_MISS, "error_category": ErrorCategory.PERMANENT},
            )

        logger.info(
            "cross_file_started",
            repo_id=repo_id,
            ir_cache_key=ir_cache_key,
        )

        try:
            ir_documents = ir_data["ir_documents"]
            start_time = time.perf_counter()

            # RFC-062: Try Rust accelerated implementation first
            if RUST_AVAILABLE:
                try:
                    result = self._resolve_with_rust(ir_documents)
                    duration = time.perf_counter() - start_time

                    # Cache GlobalContext
                    cache_key = self.config.cache_keys.make_global_ctx_key(repo_id, snapshot_id)
                    self.global_ctx_cache[cache_key] = {
                        "global_ctx": result,  # Rust result dict
                        "ir_documents": ir_documents,
                        "repo_id": repo_id,
                        "snapshot_id": snapshot_id,
                        "used_rust": True,
                    }

                    logger.info(
                        "cross_file_completed",
                        repo_id=repo_id,
                        total_symbols=result["total_symbols"],
                        total_files=result["total_files"],
                        dependencies=result["total_dependencies"],
                        duration_seconds=round(duration, 3),
                        used_rust=True,
                        rust_duration_ms=result.get("build_duration_ms", 0),
                    )

                    return JobResult.ok(
                        data={
                            "total_symbols": result["total_symbols"],
                            "total_files": result["total_files"],
                            "dependencies_resolved": result["total_dependencies"],
                            "global_ctx_key": cache_key,
                            "used_rust": True,
                            "duration_ms": result.get("build_duration_ms", 0),
                        }
                    )

                except Exception as e:
                    logger.warning(
                        "rust_cross_file_failed",
                        error=str(e),
                        message="Falling back to Python implementation",
                    )

            # Fallback: Python implementation
            from codegraph_engine.code_foundation.infrastructure.ir.cross_file_resolver import CrossFileResolver

            resolver = CrossFileResolver()
            global_ctx = resolver.resolve(ir_documents)
            duration = time.perf_counter() - start_time

            stats = global_ctx.get_stats()

            # Cache GlobalContext
            cache_key = self.config.cache_keys.make_global_ctx_key(repo_id, snapshot_id)
            self.global_ctx_cache[cache_key] = {
                "global_ctx": global_ctx,
                "ir_documents": ir_documents,  # Pass through for next stage
                "repo_id": repo_id,
                "snapshot_id": snapshot_id,
                "used_rust": False,
            }

            logger.info(
                "cross_file_completed",
                repo_id=repo_id,
                total_symbols=global_ctx.total_symbols,
                total_files=global_ctx.total_files,
                dependencies=stats.get("total_dependencies", 0),
                duration_seconds=round(duration, 3),
                used_rust=False,
            )

            return JobResult.ok(
                data={
                    "total_symbols": global_ctx.total_symbols,
                    "total_files": global_ctx.total_files,
                    "dependencies_resolved": stats.get("total_dependencies", 0),
                    "global_ctx_key": cache_key,
                    "used_rust": False,
                }
            )

        except ImportError as e:
            logger.warning(
                "cross_file_resolver_not_available",
                error=str(e),
                message="Skipping cross-file resolution",
            )
            # Graceful degradation - return success with empty context
            cache_key = self.config.cache_keys.make_global_ctx_key(repo_id, snapshot_id)
            self.global_ctx_cache[cache_key] = ir_data  # Pass through without GlobalContext

            return JobResult.ok(
                data={
                    "total_symbols": 0,
                    "total_files": 0,
                    "dependencies_resolved": 0,
                    "global_ctx_key": cache_key,
                    "warning": "CrossFileResolver not available",
                }
            )

        except Exception as e:
            logger.error("cross_file_failed", repo_id=repo_id, error=str(e), exc_info=True)

            error_str = str(e).lower()
            if "memory" in error_str:
                error_category = ErrorCategory.INFRASTRUCTURE
                error_code = ErrorCode.OUT_OF_MEMORY
            else:
                error_category = ErrorCategory.TRANSIENT
                error_code = ErrorCode.CROSS_FILE_ERROR

            return JobResult.fail(
                error=f"Cross-file resolution failed: {e}",
                data={"error_code": error_code, "error_category": error_category},
            )

    def _resolve_with_rust(self, ir_documents: dict[str, Any]) -> dict[str, Any]:
        """
        RFC-062: Rust accelerated cross-file resolution.

        Converts IRDocument to Rust-compatible format and calls
        codegraph_ir.build_global_context_py().

        Args:
            ir_documents: dict of file_path → IRDocument

        Returns:
            dict with symbol_table, file_dependencies, etc.
        """
        # Convert IRDocument to list of dicts for Rust
        ir_docs_list = []

        for file_path, ir_doc in ir_documents.items():
            # Convert nodes to dicts
            nodes = []
            for node in ir_doc.nodes:
                node_dict = {
                    "id": node.id,
                    "kind": node.kind.value if hasattr(node.kind, "value") else str(node.kind),
                    "fqn": node.fqn or "",
                    "file_path": node.file_path,
                    "span": {
                        "start_line": node.span.start_line if node.span else 1,
                        "start_col": node.span.start_col if node.span else 0,
                        "end_line": node.span.end_line if node.span else 1,
                        "end_col": node.span.end_col if node.span else 0,
                    },
                    "name": node.name,
                }
                nodes.append(node_dict)

            # Convert edges to dicts
            edges = []
            for edge in ir_doc.edges:
                edge_dict = {
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "kind": edge.kind.value if hasattr(edge.kind, "value") else str(edge.kind),
                }
                edges.append(edge_dict)

            ir_docs_list.append(
                {
                    "file_path": file_path,
                    "nodes": nodes,
                    "edges": edges,
                }
            )

        # Call Rust implementation
        result = codegraph_ir_native.build_global_context_py(ir_docs_list)

        return result
