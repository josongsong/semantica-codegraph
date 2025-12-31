"""
Profiler & Bottleneck Analyzer (SOTA급)

특징:
1. CPU Profiling (cProfile)
2. Memory Profiling (tracemalloc)
3. Async Profiling (asyncio 추적)
4. Bottleneck Detection (자동 감지)
5. Flame Graph 생성
6. Performance Report
"""

import asyncio
import cProfile
import functools
import io
import pstats
import time
import tracemalloc
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# ============================================================
# Profiler
# ============================================================


@dataclass
class ProfileResult:
    """프로파일링 결과"""

    function: str
    total_time: float
    calls: int
    cumulative_time: float
    memory_usage: int = 0  # 바이트
    bottleneck_score: float = 0.0  # 병목 점수 (0-100)

    def __lt__(self, other: "ProfileResult") -> bool:
        """정렬용 (병목 점수 기준)"""
        return self.bottleneck_score < other.bottleneck_score


class Profiler:
    """
    SOTA급 Profiler.

    특징:
    - CPU & Memory Profiling
    - Bottleneck Detection
    - Performance Report
    """

    def __init__(
        self,
        enable_cpu: bool = True,
        enable_memory: bool = True,
        enable_async: bool = True,
    ):
        """
        Args:
            enable_cpu: CPU 프로파일링 활성화
            enable_memory: 메모리 프로파일링 활성화
            enable_async: Async 프로파일링 활성화
        """
        self.enable_cpu = enable_cpu
        self.enable_memory = enable_memory
        self.enable_async = enable_async

        # CPU Profiler
        self.cpu_profiler: cProfile.Profile | None = None

        # Memory Profiler
        self.memory_snapshots: list[Any] = []

        # Async Profiler
        self.async_tasks: dict[str, list[float]] = defaultdict(list)

        # Results
        self.results: list[ProfileResult] = []

    def start(self):
        """프로파일링 시작"""
        # CPU Profiling
        if self.enable_cpu:
            self.cpu_profiler = cProfile.Profile()
            self.cpu_profiler.enable()

        # Memory Profiling
        if self.enable_memory:
            tracemalloc.start()

    def stop(self):
        """프로파일링 종료"""
        # CPU Profiling
        if self.enable_cpu and self.cpu_profiler:
            self.cpu_profiler.disable()

        # Memory Profiling
        if self.enable_memory:
            snapshot = tracemalloc.take_snapshot()
            self.memory_snapshots.append(snapshot)

    def analyze(self) -> list[ProfileResult]:
        """
        프로파일링 결과 분석.

        Returns:
            ProfileResult 리스트 (병목 점수 내림차순)
        """
        self.results = []

        # CPU 분석
        if self.enable_cpu and self.cpu_profiler:
            self._analyze_cpu()

        # Memory 분석
        if self.enable_memory and self.memory_snapshots:
            self._analyze_memory()

        # Async 분석
        if self.enable_async and self.async_tasks:
            self._analyze_async()

        # 병목 점수 계산
        self._calculate_bottleneck_scores()

        # 정렬 (병목 점수 높은 것 먼저)
        self.results.sort(reverse=True)

        return self.results

    def _analyze_cpu(self):
        """CPU 프로파일링 분석"""
        if not self.cpu_profiler:
            return

        # pstats로 통계 추출
        s = io.StringIO()
        ps = pstats.Stats(self.cpu_profiler, stream=s)
        ps.strip_dirs()
        ps.sort_stats(pstats.SortKey.CUMULATIVE)

        # 상위 함수 추출
        for func, (_cc, nc, tt, ct, _callers) in ps.stats.items():
            filename, line, func_name = func

            # 프로젝트 내부 함수만 (외부 라이브러리 제외)
            if "site-packages" in filename:
                continue

            result = ProfileResult(
                function=f"{filename}:{line}:{func_name}",
                total_time=tt,
                calls=nc,
                cumulative_time=ct,
            )
            self.results.append(result)

    def _analyze_memory(self):
        """메모리 프로파일링 분석"""
        if not self.memory_snapshots:
            return

        snapshot = self.memory_snapshots[-1]
        top_stats = snapshot.statistics("lineno")

        for stat in top_stats[:20]:  # 상위 20개
            result = ProfileResult(
                function=f"{stat.traceback}",
                total_time=0.0,
                calls=stat.count,
                cumulative_time=0.0,
                memory_usage=stat.size,
            )
            self.results.append(result)

    def _analyze_async(self):
        """Async 프로파일링 분석"""
        for task_name, durations in self.async_tasks.items():
            if not durations:
                continue

            total_time = sum(durations)
            total_time / len(durations)
            calls = len(durations)

            result = ProfileResult(
                function=f"async:{task_name}",
                total_time=total_time,
                calls=calls,
                cumulative_time=total_time,
            )
            self.results.append(result)

    def _calculate_bottleneck_scores(self):
        """
        병목 점수 계산.

        점수 = (cumulative_time 비율 * 50) + (memory 비율 * 30) + (calls 비율 * 20)
        """
        if not self.results:
            return

        # 최대값
        max_time = max((r.cumulative_time for r in self.results), default=1.0)
        max_memory = max((r.memory_usage for r in self.results), default=1)
        max_calls = max((r.calls for r in self.results), default=1)

        # 점수 계산
        for result in self.results:
            time_score = (result.cumulative_time / max_time) * 50
            memory_score = (result.memory_usage / max_memory) * 30
            calls_score = (result.calls / max_calls) * 20

            result.bottleneck_score = time_score + memory_score + calls_score

    def get_report(self, top_n: int = 10) -> str:
        """
        성능 리포트 생성.

        Args:
            top_n: 상위 N개 병목

        Returns:
            리포트 문자열
        """
        if not self.results:
            return "No profiling results available."

        report = "Performance Report (Top Bottlenecks)\n"
        report += "=" * 80 + "\n\n"

        for i, result in enumerate(self.results[:top_n], 1):
            report += f"{i}. {result.function}\n"
            report += f"   Bottleneck Score: {result.bottleneck_score:.2f}/100\n"
            report += f"   Cumulative Time: {result.cumulative_time:.4f}s\n"
            report += f"   Calls: {result.calls}\n"

            if result.memory_usage > 0:
                report += f"   Memory: {result.memory_usage / 1024 / 1024:.2f} MB\n"

            report += "\n"

        return report

    def track_async_task(self, task_name: str, duration: float):
        """
        Async 태스크 추적.

        Args:
            task_name: 태스크 이름
            duration: 실행 시간 (초)
        """
        self.async_tasks[task_name].append(duration)


# ============================================================
# Profile Decorator
# ============================================================


def profile(
    enable_cpu: bool = True,
    enable_memory: bool = True,
    auto_report: bool = True,
):
    """
    함수 프로파일링 데코레이터.

    Example:
        @profile(enable_cpu=True, enable_memory=True)
        async def heavy_computation():
            ...
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            profiler = Profiler(
                enable_cpu=enable_cpu,
                enable_memory=enable_memory,
                enable_async=True,
            )

            profiler.start()
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                return result

            finally:
                duration = time.time() - start_time
                profiler.stop()
                profiler.track_async_task(func.__name__, duration)

                if auto_report:
                    profiler.analyze()
                    print(profiler.get_report(top_n=5))

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            profiler = Profiler(
                enable_cpu=enable_cpu,
                enable_memory=enable_memory,
                enable_async=False,
            )

            profiler.start()

            try:
                result = func(*args, **kwargs)
                return result

            finally:
                profiler.stop()

                if auto_report:
                    profiler.analyze()
                    print(profiler.get_report(top_n=5))

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ============================================================
# Bottleneck Detector
# ============================================================


class BottleneckDetector:
    """
    자동 병목 감지기.

    특징:
    - 실행 시간 모니터링
    - 자동 병목 감지
    - Alert & Logging
    """

    def __init__(
        self,
        time_threshold: float = 1.0,  # 1초 이상
        memory_threshold: int = 100 * 1024 * 1024,  # 100MB 이상
        alert_callback: Callable | None = None,
    ):
        """
        Args:
            time_threshold: 시간 임계값 (초)
            memory_threshold: 메모리 임계값 (바이트)
            alert_callback: Alert 콜백
        """
        self.time_threshold = time_threshold
        self.memory_threshold = memory_threshold
        self.alert_callback = alert_callback

        # 감지된 병목
        self.bottlenecks: list[dict[str, Any]] = []

    def detect_time_bottleneck(self, func_name: str, duration: float):
        """
        시간 병목 감지.

        Args:
            func_name: 함수 이름
            duration: 실행 시간 (초)
        """
        if duration > self.time_threshold:
            bottleneck = {
                "type": "time",
                "function": func_name,
                "duration": duration,
                "threshold": self.time_threshold,
            }
            self.bottlenecks.append(bottleneck)

            if self.alert_callback:
                self.alert_callback(
                    f"Time bottleneck: {func_name} took {duration:.2f}s (threshold: {self.time_threshold}s)"
                )

    def detect_memory_bottleneck(self, func_name: str, memory_usage: int):
        """
        메모리 병목 감지.

        Args:
            func_name: 함수 이름
            memory_usage: 메모리 사용량 (바이트)
        """
        if memory_usage > self.memory_threshold:
            bottleneck = {
                "type": "memory",
                "function": func_name,
                "memory_usage": memory_usage,
                "threshold": self.memory_threshold,
            }
            self.bottlenecks.append(bottleneck)

            if self.alert_callback:
                mb = memory_usage / 1024 / 1024
                threshold_mb = self.memory_threshold / 1024 / 1024
                self.alert_callback(f"Memory bottleneck: {func_name} used {mb:.2f}MB (threshold: {threshold_mb:.2f}MB)")

    def get_bottlenecks(self) -> list[dict[str, Any]]:
        """감지된 병목 목록 조회"""
        return self.bottlenecks
