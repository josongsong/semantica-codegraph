"""
Indexing Service Components (SOTA Refactored)

Single Responsibility 원칙에 따라 분리된 서비스 컴포넌트:

- IndexOrchestrator: 인덱싱 조정 (full, incremental, two-phase)
- SearchFusion: 검색 + 결과 퓨전
- IncrementalIndexer: 증분 인덱싱 (파일 단위)
- IndexingService: Facade (하위 호환성)
- IndexRegistry: 인덱스 레지스트리 (OCP)
- ConsistencyChecker: 인덱스 간 일관성 검증

Usage:
    from codegraph_engine.multi_index.infrastructure.service import IndexingService
"""

from codegraph_engine.multi_index.infrastructure.service.consistency_checker import (
    ConsistencyChecker,
    ConsistencyReport,
    IndexSnapshot,
)
from codegraph_engine.multi_index.infrastructure.service.incremental_indexer import IncrementalIndexer
from codegraph_engine.multi_index.infrastructure.service.index_orchestrator import (
    IndexingPhaseResult,
    IndexOrchestrator,
)
from codegraph_engine.multi_index.infrastructure.service.index_registry import IndexEntry, IndexRegistry
from codegraph_engine.multi_index.infrastructure.service.indexing_service import IndexingService
from codegraph_engine.multi_index.infrastructure.service.search_fusion import SearchFusion

__all__ = [
    "IndexingService",
    "IndexOrchestrator",
    "SearchFusion",
    "IncrementalIndexer",
    "IndexRegistry",
    "IndexEntry",
    "IndexingPhaseResult",
    "ConsistencyChecker",
    "ConsistencyReport",
    "IndexSnapshot",
]
