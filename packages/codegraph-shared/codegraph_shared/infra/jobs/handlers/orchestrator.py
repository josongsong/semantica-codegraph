"""
Parallel Indexing Pipeline Orchestrator.

SemanticaTaskEngine을 사용하여 병렬 인덱싱 파이프라인 실행:

Pipeline Architecture:
    ┌───────────┐     ┌─────────────┐
    │ L1: IR    │     │ L3: Lexical │  ← 병렬 실행 (파일 경로만 필요)
    └─────┬─────┘     └─────────────┘
          │
    ┌─────┴─────┐
    │ L2: Chunk │  ← L1 완료 후 실행 (IR 필요)
    └─────┬─────┘
          │
    ┌─────┴─────┐
    │ L4: Vector│  ← L2 완료 후 실행 (Chunk 필요)
    └───────────┘

Usage:
    # Remote mode (Task Engine server)
    orchestrator = ParallelIndexingOrchestrator(adapter)
    result = await orchestrator.index_repository(...)

    # Local mode (no server, direct handler execution)
    orchestrator = ParallelIndexingOrchestrator.create_local()
    result = await orchestrator.index_repository(...)
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codegraph_shared.infra.jobs.handlers.config import (
    DEFAULT_CONFIG,
    IndexingConfig,
    JobState,
    JobType,
)
from codegraph_shared.infra.jobs.semantica_adapter import SemanticaAdapter
from codegraph_shared.infra.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PipelineResult:
    """파이프라인 실행 결과."""

    success: bool
    files_processed: int
    nodes_created: int
    edges_created: int
    chunks_created: int
    vectors_indexed: int
    lexical_files_indexed: int
    duration_seconds: float
    errors: list[str]

    @classmethod
    def empty(cls) -> "PipelineResult":
        return cls(
            success=True,
            files_processed=0,
            nodes_created=0,
            edges_created=0,
            chunks_created=0,
            vectors_indexed=0,
            lexical_files_indexed=0,
            duration_seconds=0.0,
            errors=[],
        )

    def merge(self, other: "PipelineResult") -> "PipelineResult":
        """두 결과 병합."""
        return PipelineResult(
            success=self.success and other.success,
            files_processed=self.files_processed + other.files_processed,
            nodes_created=self.nodes_created + other.nodes_created,
            edges_created=self.edges_created + other.edges_created,
            chunks_created=self.chunks_created + other.chunks_created,
            vectors_indexed=self.vectors_indexed + other.vectors_indexed,
            lexical_files_indexed=self.lexical_files_indexed + other.lexical_files_indexed,
            duration_seconds=max(self.duration_seconds, other.duration_seconds),
            errors=self.errors + other.errors,
        )


class ParallelIndexingOrchestrator:
    """
    병렬 인덱싱 파이프라인 오케스트레이터.

    SemanticaTaskEngine을 사용하여 Job 스케줄링 및 의존성 관리.
    """

    # Job Types (using Enum)
    JOB_TYPE_IR = JobType.BUILD_IR
    JOB_TYPE_LEXICAL = JobType.LEXICAL_INDEX
    JOB_TYPE_CHUNK = JobType.BUILD_CHUNK
    JOB_TYPE_VECTOR = JobType.VECTOR_INDEX

    def __init__(
        self,
        adapter: SemanticaAdapter,
        ir_cache: dict[str, Any] | None = None,
        chunk_cache: dict[str, Any] | None = None,
        config: IndexingConfig | None = None,
    ):
        """
        Args:
            adapter: SemanticaAdapter 인스턴스
            ir_cache: IR 결과 공유 캐시
            chunk_cache: 청크 결과 공유 캐시
            config: 인덱싱 설정 (기본: DEFAULT_CONFIG)
        """
        self.adapter = adapter
        self.ir_cache = ir_cache if ir_cache is not None else {}
        self.chunk_cache = chunk_cache if chunk_cache is not None else {}
        self.config = config or DEFAULT_CONFIG

    async def index_repository(
        self,
        repo_path: str | Path,
        repo_id: str,
        snapshot_id: str | None = None,
        semantic_tier: str | None = None,
        parallel_workers: int | None = None,
        skip_vector: bool = False,
        timeout_seconds: int | None = None,
    ) -> PipelineResult:
        """
        레포지토리 인덱싱 실행 (병렬 파이프라인).

        Phase 1: L1 (IR) ∥ L3 (Lexical) 병렬 실행
        Phase 2: L2 (Chunk) 실행 (L1 완료 후)
        Phase 3: L4 (Vector) 실행 (L2 완료 후, optional)

        Args:
            repo_path: 레포지토리 경로
            repo_id: 레포지토리 ID
            snapshot_id: 스냅샷 ID
            semantic_tier: IR 빌드 티어 ("BASE", "FULL")
            parallel_workers: IR 빌드 워커 수
            skip_vector: 벡터 인덱싱 스킵 여부
            timeout_seconds: 전체 타임아웃

        Returns:
            PipelineResult
        """
        from datetime import datetime

        # 기본값 적용 (config에서)
        snapshot_id = snapshot_id or self.config.defaults.snapshot_id
        semantic_tier = semantic_tier or self.config.defaults.semantic_tier
        parallel_workers = parallel_workers or self.config.defaults.parallel_workers
        timeout_seconds = timeout_seconds or self.config.timeouts.pipeline
        timeout_ms = timeout_seconds * 1000

        start_time = datetime.now()
        repo_path = Path(repo_path).resolve()

        logger.info(
            "pipeline_started",
            repo_id=repo_id,
            repo_path=str(repo_path),
            semantic_tier=semantic_tier,
        )

        result = PipelineResult.empty()
        subject_key_base = f"{repo_id}:{snapshot_id}"

        try:
            # ================================================
            # Phase 1: L1 (IR) ∥ L3 (Lexical) 병렬 실행
            # ================================================
            logger.info("phase1_parallel_started", jobs=["IR", "Lexical"])

            # L1: IR Build Job
            ir_job = await self.adapter.enqueue(
                job_type=self.JOB_TYPE_IR,
                queue=self.config.queue.default_queue,
                subject_key=f"{subject_key_base}:ir",
                payload={
                    "repo_path": str(repo_path),
                    "repo_id": repo_id,
                    "snapshot_id": snapshot_id,
                    "semantic_tier": semantic_tier,
                    "parallel_workers": parallel_workers,
                },
                priority=self.config.priority.ir_build,
            )

            # L3: Lexical Index Job
            lexical_job = await self.adapter.enqueue(
                job_type=self.JOB_TYPE_LEXICAL,
                queue=self.config.queue.default_queue,
                subject_key=f"{subject_key_base}:lexical",
                payload={
                    "repo_path": str(repo_path),
                    "repo_id": repo_id,
                },
                priority=self.config.priority.lexical_index,
            )

            # 병렬 대기 (Phase 7: wait_for_job 사용)
            from semantica_task_engine import SemanticaTaskClient

            ir_snapshot = None
            lexical_snapshot = None

            async with SemanticaTaskClient(self.adapter.url) as client:
                # 동시 대기 (return_exceptions=True로 예외 처리)
                ir_result_task = asyncio.create_task(client.wait_for_job(ir_job.job_id, timeout_ms=timeout_ms))
                lexical_result_task = asyncio.create_task(
                    client.wait_for_job(lexical_job.job_id, timeout_ms=timeout_ms)
                )

                results = await asyncio.gather(ir_result_task, lexical_result_task, return_exceptions=True)

                # 예외 확인 및 처리 (TimeoutError 우선)
                for res in results:
                    if isinstance(res, asyncio.TimeoutError):
                        raise res
                for res in results:
                    if isinstance(res, Exception):
                        raise res

                ir_snapshot, lexical_snapshot = results

            # L3 (Lexical) 결과 처리
            if lexical_snapshot.state == JobState.DONE:
                result.lexical_files_indexed = lexical_snapshot.progress or 0
                logger.info("lexical_completed", files_indexed=result.lexical_files_indexed)
            else:
                result.errors.append(f"Lexical indexing failed: {lexical_snapshot.error_message}")
                logger.warning("lexical_failed", error=lexical_snapshot.error_message)

            # L1 (IR) 결과 확인 - L2, L4의 필수 선행 조건
            if ir_snapshot.state != JobState.DONE:
                result.success = False
                result.errors.append(f"IR build failed: {ir_snapshot.error_message}")
                logger.error("ir_failed", error=ir_snapshot.error_message)
                result.duration_seconds = (datetime.now() - start_time).total_seconds()
                return result

            # IR 캐시 키 가져오기 (실제로는 Job 결과에서 추출)
            ir_cache_key = self.config.cache_keys.make_ir_key(repo_id, snapshot_id)
            logger.info("phase1_completed", ir_cache_key=ir_cache_key)

            # ================================================
            # Phase 2: L2 (Chunk) 실행
            # ================================================
            logger.info("phase2_chunk_started")

            chunk_job = await self.adapter.enqueue(
                job_type=self.JOB_TYPE_CHUNK,
                queue=self.config.queue.default_queue,
                subject_key=f"{subject_key_base}:chunk",
                payload={
                    "repo_id": repo_id,
                    "snapshot_id": snapshot_id,
                    "ir_cache_key": ir_cache_key,
                },
                priority=self.config.priority.chunk_build,
            )

            async with SemanticaTaskClient(self.adapter.url) as client:
                chunk_snapshot = await client.wait_for_job(chunk_job.job_id, timeout_ms=timeout_ms)

            if chunk_snapshot.state != JobState.DONE:
                result.success = False
                result.errors.append(f"Chunk build failed: {chunk_snapshot.error_message}")
                logger.error("chunk_failed", error=chunk_snapshot.error_message)
                result.duration_seconds = (datetime.now() - start_time).total_seconds()
                return result

            result.chunks_created = chunk_snapshot.progress or 0
            chunk_cache_key = self.config.cache_keys.make_chunk_key(repo_id, snapshot_id)
            logger.info("phase2_completed", chunks_created=result.chunks_created)

            # ================================================
            # Phase 3: L4 (Vector) 실행 (optional)
            # ================================================
            if not skip_vector:
                logger.info("phase3_vector_started")

                vector_job = await self.adapter.enqueue(
                    job_type=self.JOB_TYPE_VECTOR,
                    queue=self.config.queue.default_queue,
                    subject_key=f"{subject_key_base}:vector",
                    payload={
                        "repo_id": repo_id,
                        "snapshot_id": snapshot_id,
                        "chunk_cache_key": chunk_cache_key,
                    },
                    priority=self.config.priority.vector_index,
                )

                async with SemanticaTaskClient(self.adapter.url) as client:
                    vector_snapshot = await client.wait_for_job(vector_job.job_id, timeout_ms=timeout_ms)

                if vector_snapshot.state == JobState.DONE:
                    result.vectors_indexed = vector_snapshot.progress or 0
                    logger.info("phase3_completed", vectors_indexed=result.vectors_indexed)
                else:
                    result.errors.append(f"Vector indexing failed: {vector_snapshot.error_message}")
                    logger.warning("vector_failed", error=vector_snapshot.error_message)

            # ================================================
            # 완료
            # ================================================
            result.duration_seconds = (datetime.now() - start_time).total_seconds()

            logger.info(
                "pipeline_completed",
                repo_id=repo_id,
                duration_seconds=result.duration_seconds,
                chunks_created=result.chunks_created,
                vectors_indexed=result.vectors_indexed,
                lexical_files_indexed=result.lexical_files_indexed,
            )

            return result

        except asyncio.TimeoutError:
            result.success = False
            result.errors.append(f"Pipeline timeout after {timeout_seconds}s")
            result.duration_seconds = (datetime.now() - start_time).total_seconds()
            logger.error("pipeline_timeout", timeout_seconds=timeout_seconds)
            return result

        except Exception as e:
            result.success = False
            result.errors.append(f"Pipeline error: {e}")
            result.duration_seconds = (datetime.now() - start_time).total_seconds()
            logger.error("pipeline_error", error=str(e), exc_info=True)
            return result

    async def register_handlers(self) -> None:
        """
        Handler를 Adapter에 등록.

        Worker 모드에서 호출하여 Handler를 등록합니다.
        """
        from codegraph_shared.infra.jobs.handlers.ir_handler import IRBuildHandler
        from codegraph_shared.infra.jobs.handlers.lexical_handler import LexicalIndexHandler
        from codegraph_shared.infra.jobs.handlers.chunk_handler import ChunkBuildHandler
        from codegraph_shared.infra.jobs.handlers.vector_handler import VectorIndexHandler

        self.adapter.handlers[self.JOB_TYPE_IR] = IRBuildHandler(ir_cache=self.ir_cache)
        self.adapter.handlers[self.JOB_TYPE_LEXICAL] = LexicalIndexHandler()
        self.adapter.handlers[self.JOB_TYPE_CHUNK] = ChunkBuildHandler(
            ir_cache=self.ir_cache,
            chunk_cache=self.chunk_cache,
        )
        self.adapter.handlers[self.JOB_TYPE_VECTOR] = VectorIndexHandler(chunk_cache=self.chunk_cache)

        logger.info(
            "handlers_registered",
            handlers=list(self.adapter.handlers.keys()),
        )
