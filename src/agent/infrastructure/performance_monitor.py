"""
Performance Monitor (SOTA급)

특징:
1. Request Tracing (분산 추적)
2. Latency Histogram (P50, P95, P99)
3. Throughput Tracking (QPS)
4. Resource Monitoring (CPU, Memory)
5. Slow Query Detection
6. Performance Alerts
"""

import asyncio
import functools
import statistics
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ============================================================
# Trace Context
# ============================================================


@dataclass
class TraceContext:
    """분산 추적 컨텍스트"""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    operation: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    tags: dict[str, Any] = field(default_factory=dict)
    logs: list[dict[str, Any]] = field(default_factory=list)

    def finish(self):
        """Span 종료"""
        self.end_time = time.time()

    def duration(self) -> float:
        """실행 시간 (초)"""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    def add_tag(self, key: str, value: Any):
        """태그 추가"""
        self.tags[key] = value

    def add_log(self, event: str, **kwargs):
        """로그 추가"""
        self.logs.append({"event": event, "timestamp": time.time(), **kwargs})


# ============================================================
# Performance Monitor
# ============================================================


class PerformanceMonitor:
    """
    SOTA급 Performance Monitor.

    특징:
    - Request Tracing
    - Latency Histogram
    - Throughput Tracking
    - Slow Query Detection
    """

    def __init__(
        self,
        slow_threshold: float = 1.0,  # 1초 이상 느림
        histogram_window: int = 1000,  # 최근 1000개 요청
        alert_callback: Callable | None = None,
    ):
        """
        Args:
            slow_threshold: Slow query 임계값 (초)
            histogram_window: Latency histogram 윈도우 크기
            alert_callback: Alert 콜백 함수
        """
        self.slow_threshold = slow_threshold
        self.histogram_window = histogram_window
        self.alert_callback = alert_callback

        # Traces
        self.active_traces: dict[str, TraceContext] = {}
        self.completed_traces: deque[TraceContext] = deque(maxlen=10000)

        # Latency Histogram (operation별)
        self.latencies: defaultdict[str, deque] = defaultdict(lambda: deque(maxlen=histogram_window))

        # Throughput (operation별, 1초 단위)
        self.throughput: defaultdict[str, list[tuple[float, int]]] = defaultdict(list)
        self.last_throughput_reset = time.time()

        # Slow Queries
        self.slow_queries: deque[TraceContext] = deque(maxlen=100)

        # Metrics
        self.stats = defaultdict(int)

    def start_trace(self, operation: str, parent_span_id: str | None = None) -> TraceContext:
        """
        Trace 시작.

        Args:
            operation: 작업 이름
            parent_span_id: 부모 Span ID (선택)

        Returns:
            TraceContext
        """
        import uuid

        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())

        context = TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            operation=operation,
        )

        self.active_traces[span_id] = context
        return context

    def finish_trace(self, context: TraceContext):
        """
        Trace 종료.

        Args:
            context: TraceContext
        """
        context.finish()

        # Active에서 제거
        if context.span_id in self.active_traces:
            del self.active_traces[context.span_id]

        # Completed에 추가
        self.completed_traces.append(context)

        # Latency 기록
        duration = context.duration()
        self.latencies[context.operation].append(duration)

        # Throughput 업데이트
        now = time.time()
        self._update_throughput(context.operation, now)

        # Slow Query 감지
        if duration > self.slow_threshold:
            self.slow_queries.append(context)
            self.stats["slow_queries"] += 1

            # Alert
            if self.alert_callback:
                self.alert_callback(f"Slow query detected: {context.operation} ({duration:.2f}s)")

        # Stats
        self.stats["total_requests"] += 1
        self.stats[f"{context.operation}_requests"] += 1

    def _update_throughput(self, operation: str, now: float):
        """
        Throughput 업데이트 (1초 단위).

        Args:
            operation: 작업 이름
            now: 현재 시간
        """
        # 1초마다 리셋
        if now - self.last_throughput_reset >= 1.0:
            self.last_throughput_reset = now

        # 현재 초의 카운트 증가
        current_second = int(now)
        if self.throughput[operation] and self.throughput[operation][-1][0] == current_second:
            # 같은 초 → 카운트 증가
            timestamp, count = self.throughput[operation][-1]
            self.throughput[operation][-1] = (timestamp, count + 1)
        else:
            # 새로운 초
            self.throughput[operation].append((current_second, 1))

        # 오래된 데이터 제거 (최근 60초만 유지)
        cutoff = current_second - 60
        while self.throughput[operation] and self.throughput[operation][0][0] < cutoff:
            self.throughput[operation].pop(0)

    def get_latency_percentiles(self, operation: str) -> dict[str, float]:
        """
        Latency percentiles 조회.

        Args:
            operation: 작업 이름

        Returns:
            P50, P95, P99 딕셔너리
        """
        latencies = list(self.latencies[operation])
        if not latencies:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0, "max": 0.0}

        latencies.sort()

        p50 = statistics.median(latencies)
        p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0]
        p99 = latencies[int(len(latencies) * 0.99)] if len(latencies) > 1 else latencies[0]
        avg = statistics.mean(latencies)
        max_latency = max(latencies)

        return {
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "avg": avg,
            "max": max_latency,
        }

    def get_throughput(self, operation: str) -> dict[str, float]:
        """
        Throughput 조회 (QPS).

        Args:
            operation: 작업 이름

        Returns:
            현재, 평균, 최대 QPS
        """
        if not self.throughput[operation]:
            return {"current": 0.0, "avg": 0.0, "max": 0.0}

        # 현재 QPS (최근 1초)
        current_qps = self.throughput[operation][-1][1] if self.throughput[operation] else 0

        # 평균 QPS
        total_requests = sum(count for _, count in self.throughput[operation])
        duration = len(self.throughput[operation])  # 초 단위
        avg_qps = total_requests / duration if duration > 0 else 0.0

        # 최대 QPS
        max_qps = max((count for _, count in self.throughput[operation]), default=0)

        return {"current": float(current_qps), "avg": avg_qps, "max": float(max_qps)}

    def get_slow_queries(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Slow queries 조회.

        Args:
            limit: 최대 개수

        Returns:
            Slow query 리스트
        """
        queries = sorted(self.slow_queries, key=lambda ctx: ctx.duration(), reverse=True)[:limit]

        return [
            {
                "operation": ctx.operation,
                "duration": ctx.duration(),
                "trace_id": ctx.trace_id,
                "tags": ctx.tags,
            }
            for ctx in queries
        ]

    def get_stats(self) -> dict[str, Any]:
        """
        전체 통계 조회.

        Returns:
            통계 딕셔너리
        """
        # 모든 operation의 latency
        all_latencies = {}
        for operation, _latencies in self.latencies.items():
            all_latencies[operation] = self.get_latency_percentiles(operation)

        # 모든 operation의 throughput
        all_throughput = {}
        for operation in self.latencies.keys():
            all_throughput[operation] = self.get_throughput(operation)

        return {
            "active_traces": len(self.active_traces),
            "completed_traces": len(self.completed_traces),
            "latencies": all_latencies,
            "throughput": all_throughput,
            "slow_queries_count": len(self.slow_queries),
            **dict(self.stats),
        }


# ============================================================
# Trace Decorator
# ============================================================


def trace(operation: str = "", tags: dict | None = None):
    """
    함수 실행을 추적하는 데코레이터.

    Example:
        @trace(operation="fetch_user", tags={"service": "user-api"})
        async def fetch_user(user_id: int):
            ...
    """

    def decorator(func: Callable):
        op_name = operation or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Performance Monitor 인스턴스 필요 (글로벌 또는 주입)
            monitor = kwargs.pop("_monitor", None) or _global_monitor

            context = monitor.start_trace(op_name)
            if tags:
                for key, value in tags.items():
                    context.add_tag(key, value)

            try:
                result = await func(*args, **kwargs)
                context.add_tag("status", "success")
                return result

            except Exception as e:
                context.add_tag("status", "error")
                context.add_tag("error", str(e))
                raise

            finally:
                monitor.finish_trace(context)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            monitor = kwargs.pop("_monitor", None) or _global_monitor

            context = monitor.start_trace(op_name)
            if tags:
                for key, value in tags.items():
                    context.add_tag(key, value)

            try:
                result = func(*args, **kwargs)
                context.add_tag("status", "success")
                return result

            except Exception as e:
                context.add_tag("status", "error")
                context.add_tag("error", str(e))
                raise

            finally:
                monitor.finish_trace(context)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# Global Monitor (선택)
_global_monitor = PerformanceMonitor()
