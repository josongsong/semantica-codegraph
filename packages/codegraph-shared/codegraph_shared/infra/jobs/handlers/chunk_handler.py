"""
Chunk Build Handler (L2).

IR 결과를 사용하여 청크 생성.
L1 (IR Build) 완료 후에만 실행 가능 - IR 결과 필요.
"""

from pathlib import Path
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


class ChunkBuildHandler(JobHandler):
    """
    Chunk Build Handler.

    Payload:
        {
            "repo_id": "repo-123",
            "snapshot_id": "main",
            "ir_cache_key": "ir:repo-123:main",  # L1에서 생성된 캐시 키
            "db_path": "data/codegraph.db",
        }

    Result:
        {
            "chunks_created": 500,
            "chunk_cache_key": "chunks:repo-123:main",  # L4 (Vector)가 사용할 키
        }

    Error Classification:
        - TRANSIENT: DB 잠금, 일시적 IO 오류
        - PERMANENT: IR 캐시 없음 (L1 실패), 잘못된 IR 형식
        - INFRASTRUCTURE: DB 연결 실패, 메모리 부족
    """

    def __init__(
        self,
        ir_cache: dict[str, Any] | None = None,
        chunk_cache: dict[str, Any] | None = None,
        config: IndexingConfig | None = None,
    ):
        """
        Args:
            ir_cache: L1에서 생성된 IR 캐시 (IRBuildHandler와 공유)
            chunk_cache: 생성된 청크를 저장할 캐시 (L4와 공유)
            config: 인덱싱 설정 (기본: DEFAULT_CONFIG)
        """
        self.ir_cache = ir_cache if ir_cache is not None else {}
        self.chunk_cache = chunk_cache if chunk_cache is not None else {}
        self.config = config or DEFAULT_CONFIG

    async def execute(self, payload: dict[str, Any]) -> JobResult:
        """청크 빌드 실행."""
        repo_id = payload.get("repo_id")
        snapshot_id = payload.get("snapshot_id", self.config.defaults.snapshot_id)
        ir_cache_key = payload.get("ir_cache_key")
        db_path = payload.get("db_path", self.config.defaults.db_path)

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
                error=f"IR cache not found: {ir_cache_key}. L1 (IR Build) may have failed.",
                data={"error_code": ErrorCode.IR_CACHE_MISS, "error_category": ErrorCategory.PERMANENT},
            )

        ir_documents = ir_data.get("ir_documents", {})
        repo_path = ir_data.get("repo_path")

        if not ir_documents:
            return JobResult.ok(
                data={
                    "chunks_created": 0,
                    "chunk_cache_key": None,
                    "warning": "No IR documents to process",
                }
            )

        logger.info(
            "chunk_build_started",
            repo_id=repo_id,
            ir_documents_count=len(ir_documents),
        )

        try:
            from codegraph_engine.code_foundation.infrastructure.chunk.builder import ChunkBuilder
            from codegraph_engine.code_foundation.infrastructure.chunk.id_generator import ChunkIdGenerator
            from codegraph_engine.code_foundation.infrastructure.chunk.store_auto import create_auto_chunk_store
            from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument
            from codegraph_shared.infra.storage.sqlite import SQLiteStore

            # Create chunk store
            db_store = SQLiteStore(db_path=db_path)
            chunk_store = create_auto_chunk_store(db_store)
            chunk_builder = ChunkBuilder(id_generator=ChunkIdGenerator())

            # Create minimal graph_doc
            graph_doc = GraphDocument(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                graph_nodes={},
                graph_edges=[],
            )

            all_chunks = []
            repo_config = {}

            for file_path_str, ir_doc in ir_documents.items():
                file_path = Path(file_path_str)

                try:
                    file_text = file_path.read_text().splitlines() if file_path.exists() else []

                    chunks, _, _ = chunk_builder.build(
                        repo_id=repo_id,
                        ir_doc=ir_doc,
                        graph_doc=graph_doc,
                        file_text=file_text,
                        repo_config=repo_config,
                        snapshot_id=snapshot_id,
                    )
                    all_chunks.extend(chunks)

                except Exception as e:
                    logger.warning(
                        "chunk_build_file_failed",
                        file_path=file_path_str,
                        error=str(e),
                    )

            # Save chunks to store
            if all_chunks:
                await chunk_store.save_chunks(all_chunks)

            # Cache chunks for L4 (Vector)
            chunk_cache_key = self.config.cache_keys.make_chunk_key(repo_id, snapshot_id)
            self.chunk_cache[chunk_cache_key] = {
                "chunks": all_chunks,
                "repo_id": repo_id,
                "snapshot_id": snapshot_id,
            }

            logger.info(
                "chunk_build_completed",
                repo_id=repo_id,
                chunks_created=len(all_chunks),
            )

            return JobResult.ok(
                data={
                    "chunks_created": len(all_chunks),
                    "chunk_cache_key": chunk_cache_key,
                }
            )

        except MemoryError as e:
            logger.error("chunk_build_memory_error", repo_id=repo_id, error=str(e))
            return JobResult.fail(
                error=f"Memory error during chunk build: {e}",
                data={"error_code": ErrorCode.OUT_OF_MEMORY, "error_category": ErrorCategory.INFRASTRUCTURE},
            )

        except Exception as e:
            logger.error("chunk_build_failed", repo_id=repo_id, error=str(e), exc_info=True)

            # Classify error
            error_str = str(e).lower()
            if "database" in error_str or "sqlite" in error_str:
                if "locked" in error_str:
                    error_category = ErrorCategory.TRANSIENT  # DB 잠금 → 재시도
                    error_code = ErrorCode.DB_LOCKED
                else:
                    error_category = ErrorCategory.INFRASTRUCTURE
                    error_code = ErrorCode.DB_ERROR
            else:
                error_category = ErrorCategory.TRANSIENT
                error_code = ErrorCode.CHUNK_BUILD_ERROR

            return JobResult.fail(
                error=f"Chunk build failed: {e}",
                data={"error_code": error_code, "error_category": error_category},
            )
