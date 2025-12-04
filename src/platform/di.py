"""
Platform Dependency Injection

플랫폼 레벨 컴포넌트 생성 및 주입.
"""

from functools import cached_property

from src.common.observability import get_logger
from src.platform.runtime import RuntimeManager

logger = get_logger(__name__)


class PlatformContainer:
    """
    플랫폼 레벨 컴포넌트 컨테이너.

    Domain Container(src/container.py)와 분리:
    - Domain: 비즈니스 로직, 서비스 (chunk_store, retriever 등)
    - Platform: 런타임 인프라 (스케줄러, 워커, 큐)
    """

    def __init__(self, domain_container):
        """
        Initialize platform container.

        Args:
            domain_container: Domain container (src/container.py의 container)
        """
        self._domain = domain_container
        self._runtime: RuntimeManager | None = None

    @cached_property
    def runtime(self) -> RuntimeManager:
        """RuntimeManager 싱글톤"""
        if self._runtime is None:
            self._runtime = RuntimeManager()
        return self._runtime

    # ============================================================
    # Scheduler Factories
    # ============================================================

    def create_compaction_scheduler(self):
        """Compaction scheduler 생성"""
        from src.contexts.multi_index.infrastructure.lexical.compaction.scheduler import CompactionScheduler

        compaction_manager = self._domain._index.compaction_manager

        return CompactionScheduler(
            compaction_manager=compaction_manager,
            check_interval_seconds=3600,  # 1 hour
        )

    def create_background_jobs_scheduler(self):
        """Background jobs scheduler 생성"""
        from src.contexts.analysis_indexing.infrastructure.jobs import EmbeddingRefreshJob, RepoMapRebuildJob
        from src.contexts.analysis_indexing.infrastructure.jobs.scheduler import BackgroundJobsScheduler

        # Embedding refresh job
        embedding_job = EmbeddingRefreshJob(
            postgres_store=self._domain._infra.postgres,
            embedding_queue=self._domain._index.embedding_queue,
            chunk_store=self._domain.chunk_store,
            stale_threshold_days=7,
        )

        # RepoMap rebuild job
        repomap_job = RepoMapRebuildJob(
            repomap_store=self._domain.repomap_store,
            chunk_store=self._domain.chunk_store,
            graph_store=self._domain._infra.memgraph,
        )

        return BackgroundJobsScheduler(
            embedding_refresh_job=embedding_job,
            repomap_rebuild_job=repomap_job,
            consistency_checker=None,  # TODO: Add if needed
        )

    # ============================================================
    # Worker Factories
    # ============================================================

    def create_background_cleanup_service(self):
        """Background cleanup service 생성"""
        from src.contexts.analysis_indexing.infrastructure.background_cleanup import BackgroundCleanupService

        orchestrator = self._domain.indexing_orchestrator

        return BackgroundCleanupService(
            edge_validator=orchestrator.edge_validator,
            cleanup_interval_seconds=3600,  # 1 hour
            graph_store=orchestrator.graph_store,
            snapshot_gc=self._domain.snapshot_gc,
        )

    def get_embedding_worker_pool(self):
        """Embedding worker pool 가져오기 (Container에 이미 존재)"""
        return self._domain._index.embedding_worker_pool

    # ============================================================
    # Setup Helper
    # ============================================================

    async def setup_runtime(self) -> RuntimeManager:
        """
        모든 플랫폼 컴포넌트 생성 및 등록.

        Returns:
            설정된 RuntimeManager
        """
        runtime = self.runtime

        # 모든 컴포넌트를 단순 등록
        components = {
            "compaction_scheduler": self.create_compaction_scheduler,
            "background_jobs": self.create_background_jobs_scheduler,
            "cleanup_service": self.create_background_cleanup_service,
            "embedding_pool": self.get_embedding_worker_pool,
        }

        for name, factory in components.items():
            try:
                component = factory()
                if component:
                    runtime.register(name, component)
            except Exception as e:
                logger.warning(f"Failed to create {name}: {e}")

        logger.info(f"Runtime setup completed: {len(runtime.components)} components")

        return runtime
