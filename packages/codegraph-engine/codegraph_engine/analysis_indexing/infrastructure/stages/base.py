"""
Base Stage for Indexing Pipeline

모든 Stage의 기본 클래스와 공통 컨텍스트를 정의합니다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from codegraph_engine.analysis_indexing.infrastructure.models import IndexingResult, IndexingStage
from codegraph_engine.code_foundation.infrastructure.profiling import Profiler, get_noop_profiler
from codegraph_shared.infra.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.chunk.store import ChunkStore

logger = get_logger(__name__)


@dataclass
class StageContext:
    """Stage 실행에 필요한 공통 컨텍스트"""

    repo_path: Path
    repo_id: str
    snapshot_id: str
    result: IndexingResult
    config: Any = None  # IndexingConfig

    # Optional runtime data (stages can populate these)
    files: list[Path] = field(default_factory=list)
    ast_results: dict = field(default_factory=dict)
    ir_doc: Any = None
    semantic_ir: Any = None
    graph_doc: Any = None
    chunks: list = field(default_factory=list)
    chunk_ids: list[str] = field(default_factory=list)

    # Change tracking (for incremental)
    change_set: Any = None
    is_incremental: bool = False

    # Profiler (for benchmarking - optional)
    profiler: Profiler = field(default_factory=get_noop_profiler)


class BaseStage(ABC):
    """Stage 기본 클래스"""

    stage_name: IndexingStage

    def __init__(self, components: Any = None):
        """
        Args:
            components: OrchestratorComponents 또는 개별 컴포넌트들
        """
        self.components = components
        self._chunk_store: ChunkStore | None = getattr(components, "chunk_store", None)

    @abstractmethod
    async def execute(self, ctx: StageContext) -> None:
        """
        Stage 실행

        Args:
            ctx: StageContext (입력/출력 공유)
        """
        pass

    def _record_duration(self, ctx: StageContext, start_time: datetime) -> float:
        """Stage 실행 시간 기록"""
        duration = (datetime.now() - start_time).total_seconds()
        ctx.result.stage_durations[self.stage_name.value] = duration
        return duration

    async def _load_chunks_by_ids(self, chunk_ids: list[str], batch_size: int = 100) -> list:
        """
        Load chunks from store by IDs with batching.

        공통 유틸리티 메서드 - ChunkStage, RepoMapStage, IndexingStage에서 사용.

        Args:
            chunk_ids: 로드할 청크 ID 목록
            batch_size: 배치 크기 (기본값 100)

        Returns:
            청크 객체 목록
        """
        if not chunk_ids:
            return []

        if not self._chunk_store:
            logger.warning("chunk_store not available for loading chunks")
            return []

        all_chunks = []

        for i in range(0, len(chunk_ids), batch_size):
            batch_ids = chunk_ids[i : i + batch_size]
            batch_result = await self._chunk_store.get_chunks_batch(batch_ids)

            for chunk_id in batch_ids:
                if chunk_id in batch_result:
                    all_chunks.append(batch_result[chunk_id])

        logger.debug(f"Loaded {len(all_chunks)}/{len(chunk_ids)} chunks from store")
        return all_chunks
