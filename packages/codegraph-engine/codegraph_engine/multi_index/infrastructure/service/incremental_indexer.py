"""
Incremental Indexer

파일 단위 증분 인덱싱 담당 (Single Responsibility).

Responsibilities:
- 파일 필터링/정규화
- 단일 파일 인덱싱
- 큐 기반 배치 처리
- Idempotency 관리
"""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.multi_index.infrastructure.service.index_registry import IndexRegistry

logger = get_logger(__name__)


class IncrementalIndexer:
    """
    증분 인덱싱 서비스.

    Usage:
        indexer = IncrementalIndexer(registry, file_queue=queue)
        result = await indexer.index_files(repo_id, snapshot_id, file_paths)
    """

    def __init__(
        self,
        registry: "IndexRegistry",
        file_queue: Any | None = None,
        queue_threshold: int = 10,
        idempotency_store: Any | None = None,
        indexing_orchestrator: Any | None = None,
        file_filter: Any | None = None,  # 캐시된 FileFilter
    ):
        """
        Args:
            registry: 인덱스 레지스트리
            file_queue: 파일 큐 (대량 처리용)
            queue_threshold: 큐 사용 임계값
            idempotency_store: Idempotency 저장소
            indexing_orchestrator: 전체 파이프라인 오케스트레이터
            file_filter: 파일 필터 (재사용)
        """
        self._registry = registry
        self._file_queue = file_queue
        self._queue_threshold = queue_threshold
        self._idempotency_store = idempotency_store
        self._indexing_orchestrator = indexing_orchestrator
        self._file_filter = file_filter

    def _get_file_filter(self):
        """FileFilter 가져오기 (지연 초기화 + 캐싱)"""
        if self._file_filter is None:
            from codegraph_engine.multi_index.infrastructure.common.file_filter import FileFilter

            self._file_filter = FileFilter()
        return self._file_filter

    def set_indexing_orchestrator(self, orchestrator: Any) -> None:
        """IndexingOrchestrator 설정 (순환 참조 방지용 지연 주입)"""
        self._indexing_orchestrator = orchestrator
        logger.info("indexing_orchestrator_injected")

    async def index_files(
        self,
        repo_id: str,
        snapshot_id: str,
        file_paths: list[str],
        reason: str | None = None,
        priority: int = 0,
        head_sha: str | None = None,
    ):
        """
        증분 인덱싱.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            file_paths: 파일 경로 리스트
            reason: 트리거 이유 (로깅용)
            priority: 우선순위 (1 이상이면 즉시 실행)
            head_sha: Git HEAD SHA (idempotency용)

        Returns:
            IncrementalIndexingResult
        """
        # LEGACY: from src.contexts.agent_automation.domain.ports import IncrementalIndexingResult
        from codegraph_shared.infra.observability import record_counter

        # 1. 파일 필터링
        file_filter = self._get_file_filter()

        repo_root = self._resolve_repo_root(repo_id)
        normalized_paths = file_filter.normalize_and_filter(
            repo_id=repo_id,
            file_paths=file_paths,
            repo_root=repo_root,
        )

        if not normalized_paths:
            logger.info(
                "incremental_index_skipped_no_files",
                repo_id=repo_id,
                original_count=len(file_paths),
            )
            return IncrementalIndexingResult(
                status="not_triggered",
                indexed_count=0,
                total_files=0,
                errors=[],
            )

        # 2. Idempotency 체크
        already_indexed = []
        if head_sha and self._idempotency_store:
            normalized_paths, already_indexed = await self._idempotency_store.filter_already_indexed(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                file_paths=normalized_paths,
                head_sha=head_sha,
            )

            if not normalized_paths:
                return IncrementalIndexingResult(
                    status="not_triggered",
                    indexed_count=0,
                    total_files=0,
                    errors=[],
                )

        # 3. 메트릭
        record_counter(
            "incremental_indexing_triggered_total",
            labels={"repo_id": repo_id, "trigger_source": reason or "unknown"},
        )

        logger.info(
            "incremental_index_starting",
            repo_id=repo_id,
            file_count=len(normalized_paths),
            reason=reason,
        )

        # 4. 실행 전략: 큐 vs 즉시
        use_queue = len(normalized_paths) > self._queue_threshold and self._file_queue and priority < 1

        if use_queue:
            return await self._enqueue_files(repo_id, snapshot_id, normalized_paths, reason, priority)

        # 5. 즉시 인덱싱 (병렬)
        return await self._index_files_parallel(repo_id, snapshot_id, normalized_paths, head_sha)

    async def _enqueue_files(
        self,
        repo_id: str,
        snapshot_id: str,
        file_paths: list[str],
        reason: str | None,
        priority: int,
    ):
        """파일 큐에 등록"""
        # LEGACY: from src.contexts.agent_automation.domain.ports import IncrementalIndexingResult

        added_count = await self._file_queue.enqueue_batch(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            file_paths=file_paths,
            reason=reason,
            priority=priority,
        )

        logger.info(
            "files_enqueued",
            repo_id=repo_id,
            file_count=added_count,
        )

        return IncrementalIndexingResult(
            status="success",
            indexed_count=added_count,
            total_files=len(file_paths),
            errors=[],
        )

    async def _index_files_parallel(
        self,
        repo_id: str,
        snapshot_id: str,
        file_paths: list[str],
        head_sha: str | None,
    ):
        """파일 병렬 인덱싱"""
        # LEGACY: from src.contexts.agent_automation.domain.ports import IncrementalIndexingResult
        from codegraph_shared.infra.observability import record_counter

        # 병렬 실행 (동시 10개 제한)
        semaphore = asyncio.Semaphore(10)

        async def _index_one(file_path: str) -> tuple[str, Exception | None]:
            async with semaphore:
                try:
                    await self._index_single_file(repo_id, snapshot_id, file_path)
                    return (file_path, None)
                except Exception as e:
                    logger.error(
                        "incremental_index_file_failed",
                        repo_id=repo_id,
                        file_path=file_path,
                        error=str(e),
                    )
                    record_counter(
                        "incremental_indexing_errors_total",
                        labels={"repo_id": repo_id},
                    )
                    return (file_path, e)

        # 병렬 실행
        tasks = [_index_one(fp) for fp in file_paths]
        results: list[tuple[str, Exception | None]] = list(await asyncio.gather(*tasks))

        # 결과 집계
        indexed_count = sum(1 for _, e in results if e is None)
        errors = [{"file_path": fp, "error": str(e)} for fp, e in results if e is not None]

        # 상태 결정
        if indexed_count == len(file_paths):
            status = "success"
        elif indexed_count == 0:
            status = "failed"
        else:
            status = "partial_success"

        logger.info(
            "incremental_index_completed",
            repo_id=repo_id,
            status=status,
            indexed_count=indexed_count,
            total_files=len(file_paths),
        )

        # Idempotency 저장
        if head_sha and self._idempotency_store:
            await self._save_idempotency_records(repo_id, snapshot_id, file_paths, results, head_sha)

        return IncrementalIndexingResult(
            status=status,
            indexed_count=indexed_count,
            total_files=len(file_paths),
            errors=errors,
        )

    async def _index_single_file(
        self,
        repo_id: str,
        snapshot_id: str,
        file_path: str,
    ) -> None:
        """
        단일 파일 인덱싱.

        Strategy:
        1. IndexingOrchestrator 있으면: 전체 파이프라인
        2. 없으면: Lexical Delta만
        """
        logger.debug(
            "index_single_file_started",
            repo_id=repo_id,
            file_path=file_path,
        )

        # Strategy 1: 전체 파이프라인
        if self._indexing_orchestrator:
            repo_path = self._resolve_repo_root(repo_id)
            if repo_path:
                await self._index_via_orchestrator(repo_id, snapshot_id, file_path, repo_path)
                return

        # Strategy 2: Lexical Delta
        lexical = self._registry.get("lexical")
        if lexical and hasattr(lexical, "delta"):
            await self._index_via_delta(repo_id, file_path, lexical)
            return

        logger.warning("no_indexing_strategy_available", repo_id=repo_id)

    async def _index_via_orchestrator(
        self,
        repo_id: str,
        snapshot_id: str,
        file_path: str,
        repo_path: Path,
    ) -> None:
        """IndexingOrchestrator를 통한 전체 파이프라인 인덱싱"""
        from datetime import datetime

        # Hexagonal: Optional import to break circular dependency
        try:
            from codegraph_engine.analysis_indexing.infrastructure.models import (
                IndexingResult,
                IndexingStatus,
            )
        except ImportError:
            # Fallback: Create minimal result tracking
            logger.warning("analysis_indexing not available - using minimal result tracking")
            # Just proceed without detailed result tracking
            success = await self._indexing_orchestrator._index_single_file(
                repo_path=repo_path,
                file_path=file_path,
                repo_id=repo_id,
                snapshot_id=snapshot_id,
            )
            return

        temp_result = IndexingResult(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            status=IndexingStatus.IN_PROGRESS,
            start_time=datetime.now(),
        )

        success = await self._indexing_orchestrator._index_single_file(
            repo_path=repo_path,
            file_path=file_path,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            result=temp_result,
        )

        if success:
            logger.info(
                "index_single_file_completed_full_pipeline",
                repo_id=repo_id,
                file_path=file_path,
            )
        else:
            raise RuntimeError(f"Failed to index {file_path}")

    async def _index_via_delta(
        self,
        repo_id: str,
        file_path: str,
        lexical: Any,
    ) -> None:
        """Lexical Delta를 통한 인덱싱"""
        repo_path = lexical.repo_resolver.resolve_repo_path(repo_id)
        if not repo_path:
            logger.warning("repo_path_not_resolved", repo_id=repo_id)
            return

        full_path = Path(repo_path) / file_path
        if not full_path.exists():
            logger.warning("file_not_found", file_path=file_path)
            return

        # Non-blocking file read: avoid blocking event loop for large files
        def _read_file() -> str:
            return full_path.read_text(encoding="utf-8", errors="replace")

        content = await asyncio.to_thread(_read_file)

        await lexical.delta.index_file(
            repo_id=repo_id,
            file_path=file_path,
            content=content,
        )

        logger.debug(
            "index_single_file_completed_delta",
            repo_id=repo_id,
            file_path=file_path,
        )

    def _resolve_repo_root(self, repo_id: str) -> Path | None:
        """저장소 루트 경로 해결"""
        # Lexical index에서 시도
        lexical = self._registry.get("lexical")
        if lexical and hasattr(lexical, "repo_resolver"):
            try:
                repo_path = lexical.repo_resolver.resolve_repo_path(repo_id)
                if repo_path:
                    return Path(repo_path)
            except Exception as e:
                logger.debug(f"repo_resolver_failed: {repo_id}, error={e}")

        # Container에서 시도
        try:
            from src.container import container

            workspace = getattr(container._settings, "workspace_path", None)
            if workspace:
                return Path(workspace)
        except Exception as e:
            logger.debug(f"container_workspace_lookup_failed: {e}")

        return None

    async def _save_idempotency_records(
        self,
        repo_id: str,
        snapshot_id: str,
        file_paths: list[str],
        results: list[tuple[str, Exception | None]],
        head_sha: str,
    ) -> None:
        """Idempotency 레코드 저장 (성공한 파일만)"""
        for file_path, exc in results:
            if exc is None:
                try:
                    await self._idempotency_store.mark_indexed(
                        repo_id=repo_id,
                        snapshot_id=snapshot_id,
                        file_path=file_path,
                        head_sha=head_sha,
                    )
                except Exception as e:
                    logger.warning(
                        "idempotency_record_failed",
                        file_path=file_path,
                        error=str(e),
                    )

    async def wait_until_idle(
        self,
        repo_id: str,
        snapshot_id: str,
        timeout: float = 5.0,
    ) -> bool:
        """인덱싱 완료 대기"""
        import time

        start = time.time()
        delay = 0.1

        while time.time() - start < timeout:
            if self._file_queue:
                if await self._file_queue.is_idle(repo_id, snapshot_id):
                    return True
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, 1.0)
            else:
                return True

        logger.warning("wait_until_idle_timeout", repo_id=repo_id, timeout=timeout)
        return False
