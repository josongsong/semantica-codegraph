"""
Search Log Models

검색 쿼리 실행 로그 수집 for AutoRRF weight tuning.

로그 수집 항목:
- 입력: query, intent, weights
- 출력: fused results, rankings
- 피드백: 클릭, dwell time, 해결 여부
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SearchLog:
    """
    단일 검색 실행 로그.

    온라인 단계에서 수집하여 오프라인 튜닝의 재료로 사용.
    """

    # Input
    query: str
    """검색 쿼리"""

    intent: str
    """QueryIntent (IDENTIFIER, NATURAL_QUESTION, ERROR_LOG, etc.)"""

    repo_id: str
    """레포지토리 ID"""

    snapshot_id: str = "main"
    """스냅샷 ID"""

    # Weights used
    weights: dict[str, float] = field(default_factory=dict)
    """사용된 인덱스별 weight (lexical, vector, symbol, fuzzy, domain)"""

    # Results
    result_ids: list[str] = field(default_factory=list)
    """Fused 결과 chunk/hit ID 리스트 (rank 순)"""

    result_scores: list[float] = field(default_factory=list)
    """각 결과의 최종 RRF score"""

    result_sources: list[dict[str, float]] = field(default_factory=list)
    """각 결과의 source별 기여도 (예: {"vector": 0.8, "symbol": 0.2})"""

    # User feedback (optional, collected after interaction)
    clicked_hit_id: str | None = None
    """클릭된 결과 ID"""

    clicked_rank: int | None = None
    """클릭된 결과의 순위 (1-based)"""

    dwell_time_ms: int | None = None
    """결과 페이지 체류 시간 (밀리초)"""

    resolved: bool | None = None
    """사용자가 문제를 해결했는지 (True/False/None)"""

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    """로그 생성 시각"""

    session_id: str | None = None
    """검색 세션 ID (연속 검색 추적용)"""

    execution_time_ms: float = 0.0
    """검색 실행 시간 (밀리초)"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """추가 메타데이터"""

    def to_dict(self) -> dict:
        """로그를 dict로 변환 (저장/전송용)."""
        return {
            "query": self.query,
            "intent": self.intent,
            "repo_id": self.repo_id,
            "snapshot_id": self.snapshot_id,
            "weights": self.weights,
            "result_ids": self.result_ids,
            "result_scores": self.result_scores,
            "result_sources": self.result_sources,
            "clicked_hit_id": self.clicked_hit_id,
            "clicked_rank": self.clicked_rank,
            "dwell_time_ms": self.dwell_time_ms,
            "resolved": self.resolved,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata,
        }


@dataclass
class FeedbackEvent:
    """
    사용자 피드백 이벤트.

    검색 후 사용자 행동 추적.
    """

    log_id: str
    """연결된 SearchLog ID"""

    event_type: str
    """이벤트 타입: click, dwell, resolve, reject"""

    hit_id: str | None = None
    """관련 결과 ID"""

    hit_rank: int | None = None
    """결과 순위"""

    value: Any = None
    """이벤트 값 (dwell_time_ms, resolved bool 등)"""

    timestamp: datetime = field(default_factory=datetime.now)
    """이벤트 발생 시각"""


class SearchLogCollector:
    """
    검색 로그 수집기.

    온라인 검색 실행 시 로그 수집하여 저장.
    """

    def __init__(self, storage_backend=None):
        """
        Initialize log collector.

        Args:
            storage_backend: 로그 저장소 (DB, 파일, etc.)
        """
        self.storage = storage_backend
        self._buffer: list[SearchLog] = []
        self._buffer_size = 100

    def log_search(
        self,
        query: str,
        intent: str,
        repo_id: str,
        weights: dict[str, float],
        results: list,
        execution_time_ms: float = 0.0,
        session_id: str | None = None,
    ) -> str:
        """
        검색 실행 로그 기록.

        Args:
            query: 검색 쿼리
            intent: 의도
            repo_id: 레포 ID
            weights: 사용된 weights
            results: 검색 결과 리스트
            execution_time_ms: 실행 시간
            session_id: 세션 ID

        Returns:
            로그 ID
        """
        # 결과 추출
        result_ids = [r.chunk_id if hasattr(r, "chunk_id") else str(r) for r in results]
        result_scores = [r.score if hasattr(r, "score") else 0.0 for r in results]

        # 로그 생성
        log = SearchLog(
            query=query,
            intent=intent,
            repo_id=repo_id,
            weights=weights,
            result_ids=result_ids,
            result_scores=result_scores,
            execution_time_ms=execution_time_ms,
            session_id=session_id,
        )

        # 버퍼에 추가
        self._buffer.append(log)

        # 버퍼 플러시
        if len(self._buffer) >= self._buffer_size:
            self._flush_buffer()

        # 로그 ID 반환 (피드백 연결용)
        return f"log:{log.timestamp.isoformat()}"

    def log_feedback(
        self,
        log_id: str,
        event_type: str,
        hit_id: str | None = None,
        hit_rank: int | None = None,
        value: Any = None,
    ) -> None:
        """
        피드백 이벤트 기록.

        Args:
            log_id: SearchLog ID
            event_type: click, dwell, resolve, reject
            hit_id: 결과 ID
            hit_rank: 결과 순위
            value: 이벤트 값
        """
        event = FeedbackEvent(
            log_id=log_id,
            event_type=event_type,
            hit_id=hit_id,
            hit_rank=hit_rank,
            value=value,
        )

        if self.storage:
            self.storage.save_feedback(event)

    def _flush_buffer(self) -> None:
        """버퍼 플러시 (storage에 저장)."""
        if not self.storage or not self._buffer:
            return

        self.storage.save_logs(self._buffer)
        self._buffer.clear()


# Global collector instance
_log_collector: SearchLogCollector | None = None


def get_log_collector() -> SearchLogCollector | None:
    """Get global log collector."""
    return _log_collector


def init_log_collector(storage_backend=None) -> SearchLogCollector:
    """Initialize global log collector."""
    global _log_collector
    _log_collector = SearchLogCollector(storage_backend)
    return _log_collector
