"""
Analysis Indexing DI Container

분석 인덱싱 컨텍스트의 의존성 주입 컨테이너
"""

import os
from functools import cached_property

from .infrastructure.fake_metadata_store import FakeIndexingMetadataStore
from .infrastructure.pg_metadata_store import PgIndexingMetadataStore
from .usecase.get_indexing_status import GetIndexingStatusUseCase
from .usecase.index_repository_full import IndexRepositoryFullUseCase
from .usecase.index_repository_incremental import IndexRepositoryIncrementalUseCase


class AnalysisIndexingContainer:
    """Analysis Indexing BC의 DI Container"""

    def __init__(self, indexing_orchestrator=None, use_fake: bool = False):
        """
        초기화

        Args:
            indexing_orchestrator: IndexingOrchestrator (None이면 기존 container에서 가져옴)
            use_fake: Fake 구현 사용 여부 (기본값: 환경 변수로 결정)
        """
        self._indexing_orchestrator = indexing_orchestrator
        self._use_fake = use_fake or os.getenv("USE_FAKE_STORES", "false").lower() == "true"

    @cached_property
    def metadata_store(self):
        """메타데이터 저장소"""
        if self._use_fake:
            return FakeIndexingMetadataStore()

        # 실제 PostgreSQL 사용
        from src.container import container

        return PgIndexingMetadataStore(postgres_adapter=container.postgres)

    @property
    def indexing_orchestrator(self):
        """실제 IndexingOrchestrator"""
        if self._indexing_orchestrator is None:
            # 기존 container에서 가져옴
            from src.container import container

            return container.indexing_orchestrator
        return self._indexing_orchestrator

    @cached_property
    def get_status_usecase(self) -> GetIndexingStatusUseCase:
        """인덱싱 상태 조회 UseCase"""
        return GetIndexingStatusUseCase(
            metadata_store=self.metadata_store,
        )

    @cached_property
    def index_full_usecase(self) -> IndexRepositoryFullUseCase:
        """전체 인덱싱 UseCase"""
        return IndexRepositoryFullUseCase(
            orchestrator=self.indexing_orchestrator,
        )

    @cached_property
    def index_incremental_usecase(self) -> IndexRepositoryIncrementalUseCase:
        """증분 인덱싱 UseCase"""
        return IndexRepositoryIncrementalUseCase(
            orchestrator=self.indexing_orchestrator,
        )


# 전역 싱글톤
analysis_indexing_container = AnalysisIndexingContainer()
