"""
Memory System Metrics

프로덕션급 모니터링 메트릭 정의 및 추적
"""

from datetime import datetime
from typing import Any

from codegraph_shared.infra.observability import (
    get_logger,
    record_counter,
    record_gauge,
    record_histogram,
)

logger = get_logger(__name__)


class MemoryMetrics:
    """
    Memory System 메트릭 컬렉터

    Prometheus-compatible metrics
    """

    def __init__(self):
        """Initialize metrics collector"""
        self._start_time = datetime.now()

    # ============================================================
    # Working Memory Metrics
    # ============================================================

    def record_working_memory_size(
        self,
        session_id: str,
        steps: int,
        files: int,
        symbols: int,
        hypotheses: int,
    ) -> None:
        """Working memory 크기 기록"""
        record_gauge("memory_working_steps_total", steps, labels={"session_id": session_id})
        record_gauge("memory_working_files_total", files, labels={"session_id": session_id})
        record_gauge("memory_working_symbols_total", symbols, labels={"session_id": session_id})
        record_gauge("memory_working_hypotheses_total", hypotheses, labels={"session_id": session_id})

    def record_working_memory_operation(
        self,
        operation: str,
        duration_ms: float,
        success: bool = True,
    ) -> None:
        """Working memory 작업 기록"""
        record_counter(
            "memory_working_operations_total",
            labels={"operation": operation, "success": str(success)},
        )
        record_histogram(
            "memory_working_operation_duration_ms",
            duration_ms,
            labels={"operation": operation},
        )

    # ============================================================
    # Episodic Memory Metrics
    # ============================================================

    def record_episode_created(
        self,
        project_id: str,
        task_type: str,
        duration_ms: float,
        outcome: str,
    ) -> None:
        """에피소드 생성 기록"""
        record_counter(
            "memory_episodes_created_total",
            labels={
                "project_id": project_id,
                "task_type": task_type,
                "outcome": outcome,
            },
        )
        record_histogram(
            "memory_episode_duration_ms",
            duration_ms,
            labels={"task_type": task_type},
        )

    def record_episode_retrieval(
        self,
        query_type: str,
        results_count: int,
        duration_ms: float,
        hit: bool,
    ) -> None:
        """에피소드 검색 기록"""
        record_counter(
            "memory_episode_retrievals_total",
            labels={"query_type": query_type, "hit": str(hit)},
        )
        record_histogram(
            "memory_episode_retrieval_duration_ms",
            duration_ms,
            labels={"query_type": query_type},
        )
        record_gauge(
            "memory_episode_retrieval_results",
            results_count,
            labels={"query_type": query_type},
        )

    def record_episode_storage_size(
        self,
        total_episodes: int,
        total_size_bytes: int,
    ) -> None:
        """에피소드 저장소 크기 기록"""
        record_gauge("memory_episodes_total", total_episodes)
        record_gauge("memory_episodes_storage_bytes", total_size_bytes)

    # ============================================================
    # Semantic Memory Metrics
    # ============================================================

    def record_bug_pattern_match(
        self,
        error_type: str,
        matches_found: int,
        duration_ms: float,
        top_score: float,
    ) -> None:
        """버그 패턴 매칭 기록"""
        record_counter(
            "memory_bug_pattern_matches_total",
            labels={"error_type": error_type, "found": str(matches_found > 0)},
        )
        record_histogram(
            "memory_bug_pattern_match_duration_ms",
            duration_ms,
            labels={"error_type": error_type},
        )
        if matches_found > 0:
            record_gauge(
                "memory_bug_pattern_top_score",
                top_score,
                labels={"error_type": error_type},
            )

    def record_code_pattern_applied(
        self,
        language: str,
        pattern_type: str,
        success: bool,
    ) -> None:
        """코드 패턴 적용 기록"""
        record_counter(
            "memory_code_patterns_applied_total",
            labels={
                "language": language,
                "pattern_type": pattern_type,
                "success": str(success),
            },
        )

    def record_semantic_learning(
        self,
        learning_type: str,
        confidence: float,
        source_episodes: int,
    ) -> None:
        """Semantic learning 기록"""
        record_counter(
            "memory_semantic_learning_total",
            labels={"type": learning_type},
        )
        record_gauge(
            "memory_semantic_learning_confidence",
            confidence,
            labels={"type": learning_type},
        )
        record_gauge(
            "memory_semantic_learning_source_episodes",
            source_episodes,
            labels={"type": learning_type},
        )

    # ============================================================
    # Retrieval & Scoring Metrics
    # ============================================================

    def record_memory_scoring(
        self,
        similarity: float,
        recency: float,
        importance: float,
        composite: float,
    ) -> None:
        """메모리 스코어링 기록"""
        record_gauge("memory_score_similarity", similarity)
        record_gauge("memory_score_recency", recency)
        record_gauge("memory_score_importance", importance)
        record_gauge("memory_score_composite", composite)

    def record_retrieval_ranking(
        self,
        top_k: int,
        total_candidates: int,
        avg_score: float,
    ) -> None:
        """검색 랭킹 기록"""
        record_gauge("memory_retrieval_top_k", top_k)
        record_gauge("memory_retrieval_candidates", total_candidates)
        record_gauge("memory_retrieval_avg_score", avg_score)

    # ============================================================
    # Reflection Metrics
    # ============================================================

    def record_reflection_triggered(
        self,
        task_type: str,
        source_episodes: int,
        insights_generated: int,
        duration_ms: float,
    ) -> None:
        """Reflection 실행 기록"""
        record_counter(
            "memory_reflections_total",
            labels={"task_type": task_type},
        )
        record_gauge(
            "memory_reflection_source_episodes",
            source_episodes,
            labels={"task_type": task_type},
        )
        record_gauge(
            "memory_reflection_insights",
            insights_generated,
            labels={"task_type": task_type},
        )
        record_histogram(
            "memory_reflection_duration_ms",
            duration_ms,
            labels={"task_type": task_type},
        )

    # ============================================================
    # Cache Metrics
    # ============================================================

    def record_cache_operation(
        self,
        cache_tier: str,
        operation: str,
        hit: bool,
        duration_ms: float | None = None,
    ) -> None:
        """캐시 작업 기록"""
        record_counter(
            "memory_cache_operations_total",
            labels={
                "tier": cache_tier,
                "operation": operation,
                "hit": str(hit),
            },
        )

        if duration_ms is not None:
            record_histogram(
                "memory_cache_operation_duration_ms",
                duration_ms,
                labels={"tier": cache_tier, "operation": operation},
            )

    def record_cache_stats(
        self,
        cache_tier: str,
        size: int,
        hit_rate: float,
    ) -> None:
        """캐시 통계 기록"""
        record_gauge("memory_cache_size", size, labels={"tier": cache_tier})
        record_gauge("memory_cache_hit_rate", hit_rate, labels={"tier": cache_tier})

    # ============================================================
    # Storage Metrics
    # ============================================================

    def record_storage_operation(
        self,
        storage_type: str,
        operation: str,
        duration_ms: float,
        success: bool = True,
    ) -> None:
        """저장소 작업 기록"""
        record_counter(
            "memory_storage_operations_total",
            labels={
                "type": storage_type,
                "operation": operation,
                "success": str(success),
            },
        )
        record_histogram(
            "memory_storage_operation_duration_ms",
            duration_ms,
            labels={"type": storage_type, "operation": operation},
        )

    def record_storage_health(
        self,
        storage_type: str,
        healthy: bool,
        latency_ms: float | None = None,
    ) -> None:
        """저장소 건강 상태 기록"""
        record_gauge(
            "memory_storage_healthy",
            1.0 if healthy else 0.0,
            labels={"type": storage_type},
        )

        if latency_ms is not None:
            record_gauge(
                "memory_storage_latency_ms",
                latency_ms,
                labels={"type": storage_type},
            )

    # ============================================================
    # Fallback & Degradation Metrics
    # ============================================================

    def record_fallback_triggered(
        self,
        service: str,
        source: str,
    ) -> None:
        """Fallback 실행 기록"""
        record_counter(
            "memory_fallback_triggered_total",
            labels={"service": service, "source": source},
        )

    def record_circuit_breaker_state(
        self,
        service: str,
        state: str,
    ) -> None:
        """Circuit breaker 상태 기록"""
        states = {"healthy": 0, "degraded": 1, "unavailable": 2}
        record_gauge(
            "memory_circuit_breaker_state",
            states.get(state, 0),
            labels={"service": service},
        )

    def record_degradation_level(
        self,
        level: int,
        disabled_features: list[str],
    ) -> None:
        """Degradation level 기록"""
        record_gauge("memory_degradation_level", level)
        record_counter(
            "memory_degradation_triggered_total",
            labels={"level": str(level), "features": ",".join(disabled_features)},
        )

    # ============================================================
    # System Health Metrics
    # ============================================================

    def record_system_health(
        self,
        overall_health: str,
        error_rate: float,
        uptime_seconds: float,
    ) -> None:
        """전체 시스템 건강 상태 기록"""
        health_values = {"healthy": 1.0, "degraded": 0.5, "unavailable": 0.0}
        record_gauge("memory_system_health", health_values.get(overall_health, 0.0))
        record_gauge("memory_system_error_rate", error_rate)
        record_gauge("memory_system_uptime_seconds", uptime_seconds)

    def get_uptime_seconds(self) -> float:
        """시스템 가동 시간"""
        return (datetime.now() - self._start_time).total_seconds()


# Global instance
_metrics = MemoryMetrics()


def get_metrics() -> MemoryMetrics:
    """전역 메트릭 컬렉터 가져오기"""
    return _metrics


def record_memory_operation(
    operation: str,
    duration_ms: float,
    success: bool = True,
    **labels: Any,
) -> None:
    """
    메모리 작업 기록 (편의 함수)

    Args:
        operation: 작업 이름
        duration_ms: 소요 시간 (ms)
        success: 성공 여부
        **labels: 추가 라벨
    """
    record_counter(
        "memory_operations_total",
        labels={"operation": operation, "success": str(success), **labels},
    )
    record_histogram(
        "memory_operation_duration_ms",
        duration_ms,
        labels={"operation": operation, **labels},
    )


def export_metrics_summary() -> dict[str, Any]:
    """
    메트릭 요약 export (Prometheus 외)

    Returns:
        메트릭 요약 딕셔너리
    """
    metrics = get_metrics()

    return {
        "uptime_seconds": metrics.get_uptime_seconds(),
        "start_time": metrics._start_time.isoformat(),
        "current_time": datetime.now().isoformat(),
    }
