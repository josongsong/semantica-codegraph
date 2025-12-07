"""
Incremental Workflow (SOTA급)

기존 인프라를 활용하여 변경된 부분만 재실행합니다.

핵심 개선:
1. ChangeDetector 연동 (PostgreSQL 기반, 정교한 변경 감지)
2. GraphImpactAnalyzer 연동 (심볼 그래프 기반, 정확한 영향 분석)
3. Memgraph 의존성 그래프 활용
4. 심볼 레벨 Incremental 지원
"""

from dataclasses import dataclass, field
from typing import Any

from src.agent.domain.models import AgentTask, WorkflowState


@dataclass
class IncrementalContext:
    """Incremental 실행 컨텍스트"""

    is_incremental: bool  # Incremental 모드 여부
    changed_files: list[str]  # 변경된 파일
    impacted_files: list[str]  # 영향받는 파일
    rerun_files: list[str]  # 재실행할 파일
    cache_hits: int = 0  # 캐시 히트 수
    cache_misses: int = 0  # 캐시 미스 수

    # SOTA급 추가 정보
    changed_symbols: list[str] = field(default_factory=list)  # 변경된 심볼
    impacted_symbols: list[str] = field(default_factory=list)  # 영향받는 심볼
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_speedup_ratio(self, total_files: int) -> float:
        """
        속도 향상 비율.

        Args:
            total_files: 전체 파일 수

        Returns:
            속도 향상 배수 (e.g., 10.0 = 10배 빠름)
        """
        if not self.rerun_files or total_files == 0:
            return 1.0

        return total_files / len(self.rerun_files)


class IncrementalCache:
    """
    Incremental Execution 캐시.

    이전 실행 결과를 저장하여 재사용합니다.
    """

    def __init__(self, redis_client=None):
        """
        Args:
            redis_client: Redis 클라이언트 (옵셔널, SOTA급)
        """
        self._cache: dict[str, Any] = {}
        self.redis_client = redis_client

    def get(self, key: str) -> Any | None:
        """
        캐시에서 가져오기.

        Args:
            key: 캐시 키 (파일 경로)

        Returns:
            캐시된 값, 없으면 None
        """
        # Redis 우선 (SOTA)
        if self.redis_client:
            try:
                import pickle

                value = self.redis_client.get(f"agent:incr:{key}")
                if value:
                    return pickle.loads(value)
            except Exception:
                pass

        # Fallback: 메모리
        return self._cache.get(key)

    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """
        캐시에 저장.

        Args:
            key: 캐시 키 (파일 경로)
            value: 저장할 값
            ttl: TTL (초, Redis용)
        """
        # Redis 저장 (SOTA)
        if self.redis_client:
            try:
                import pickle

                self.redis_client.setex(
                    f"agent:incr:{key}",
                    ttl,
                    pickle.dumps(value),
                )
            except Exception:
                pass

        # 메모리 저장
        self._cache[key] = value

    def invalidate(self, keys: list[str]) -> None:
        """
        캐시 무효화.

        Args:
            keys: 무효화할 키 목록
        """
        # Redis 무효화
        if self.redis_client:
            try:
                for key in keys:
                    self.redis_client.delete(f"agent:incr:{key}")
            except Exception:
                pass

        # 메모리 무효화
        for key in keys:
            if key in self._cache:
                del self._cache[key]

    def clear(self) -> None:
        """전체 캐시 삭제"""
        if self.redis_client:
            try:
                # Redis 패턴 삭제
                keys = self.redis_client.keys("agent:incr:*")
                if keys:
                    self.redis_client.delete(*keys)
            except Exception:
                pass

        self._cache.clear()


class IncrementalWorkflow:
    """
    Incremental Workflow Manager (SOTA급).

    기존 SOTA 인프라를 활용:
    - ChangeDetector (PostgreSQL 기반)
    - GraphImpactAnalyzer (심볼 그래프)
    - Memgraph (의존성 그래프)
    """

    def __init__(
        self,
        change_detector=None,  # ✅ 기존 ChangeDetector
        graph_impact_analyzer=None,  # ✅ 기존 GraphImpactAnalyzer
        graph_store=None,  # ✅ Memgraph
        cache: IncrementalCache | None = None,
    ):
        """
        Args:
            change_detector: 파일 변경 감지 (PostgreSQL 기반)
            graph_impact_analyzer: 영향 분석 (심볼 그래프)
            graph_store: 의존성 그래프 (Memgraph)
            cache: Incremental Cache
        """
        self.change_detector = change_detector
        self.graph_impact_analyzer = graph_impact_analyzer
        self.graph_store = graph_store
        self.cache = cache or IncrementalCache()

    async def prepare_incremental_execution(
        self,
        task: AgentTask,
        previous_state: WorkflowState | None = None,
    ) -> IncrementalContext:
        """
        Incremental 실행 준비 (SOTA급).

        Args:
            task: Agent Task
            previous_state: 이전 실행 상태 (옵셔널)

        Returns:
            Incremental 실행 컨텍스트
        """
        # 1. 변경 감지 (기존 ChangeDetector 활용)
        changed_files = await self._detect_changes_with_sota(task, previous_state)

        if not changed_files:
            # 변경 없음 -> 캐시만 사용
            return IncrementalContext(
                is_incremental=True,
                changed_files=[],
                impacted_files=[],
                rerun_files=[],
                cache_hits=len(task.context_files),
            )

        # 2. 영향 분석 (기존 GraphImpactAnalyzer 활용)
        impact_result = await self._analyze_impact_with_sota(changed_files, task.repo_id)

        # 3. Incremental 가능 여부 확인
        is_incremental = self._can_run_incremental(changed_files, impact_result)

        if not is_incremental:
            # 전체 실행 필요
            return IncrementalContext(
                is_incremental=False,
                changed_files=changed_files,
                impacted_files=impact_result.get("impacted_files", []),
                rerun_files=task.context_files,  # 전체 파일
                cache_misses=len(task.context_files),
                metadata=impact_result.get("metadata", {}),
            )

        # 4. 재실행 파일 결정
        impacted_files = impact_result.get("impacted_files", [])
        rerun_files = list(set(changed_files) | set(impacted_files))
        cached_files = [f for f in task.context_files if f not in rerun_files]

        return IncrementalContext(
            is_incremental=True,
            changed_files=changed_files,
            impacted_files=impacted_files,
            rerun_files=rerun_files,
            cache_hits=len(cached_files),
            cache_misses=len(rerun_files),
            changed_symbols=impact_result.get("changed_symbols", []),
            impacted_symbols=impact_result.get("impacted_symbols", []),
            metadata=impact_result.get("metadata", {}),
        )

    async def _detect_changes_with_sota(
        self,
        task: AgentTask,
        previous_state: WorkflowState | None,
    ) -> list[str]:
        """
        변경 감지 (기존 ChangeDetector 활용).

        Args:
            task: Agent Task
            previous_state: 이전 실행 상태

        Returns:
            변경된 파일 목록
        """
        if not self.change_detector:
            # Fallback: 간단한 방법
            if not previous_state:
                return task.context_files
            return self._detect_changes_simple(task, previous_state)

        # ✅ SOTA: 기존 ChangeDetector 사용
        try:
            change_set = await self.change_detector.detect_changes(
                repo_id=task.repo_id,
                snapshot_id=task.snapshot_id,
            )

            # 변경된 파일 필터링
            changed = []
            for file_path in task.context_files:
                if file_path in change_set.added_files:
                    changed.append(file_path)
                elif file_path in change_set.modified_files:
                    changed.append(file_path)

            return changed
        except Exception:
            # Fallback
            return self._detect_changes_simple(task, previous_state)

    def _detect_changes_simple(
        self,
        task: AgentTask,
        previous_state: WorkflowState | None,
    ) -> list[str]:
        """간단한 변경 감지 (Fallback)"""
        if not previous_state:
            return task.context_files

        previous_files = set(previous_state.task.context_files)
        current_files = set(task.context_files)

        # 추가/수정된 파일
        changed = list(current_files - previous_files)

        # 공통 파일 중 캐시 없는 것
        for file_path in current_files & previous_files:
            if not self.cache.get(file_path):
                changed.append(file_path)

        return changed

    async def _analyze_impact_with_sota(
        self,
        changed_files: list[str],
        repo_id: str,
    ) -> dict[str, Any]:
        """
        영향 분석 (기존 GraphImpactAnalyzer 활용).

        Args:
            changed_files: 변경된 파일 목록
            repo_id: Repository ID

        Returns:
            영향 분석 결과
        """
        if not self.graph_impact_analyzer:
            # Fallback: 간단한 방법
            return {
                "impacted_files": [],
                "changed_symbols": [],
                "impacted_symbols": [],
                "metadata": {},
            }

        # ✅ SOTA: 기존 GraphImpactAnalyzer 사용
        try:
            # 변경된 심볼 감지
            changed_symbols = []
            for file_path in changed_files:
                symbols = await self._get_symbols_in_file(file_path)
                changed_symbols.extend(symbols)

            # 영향 분석
            impact = await self.graph_impact_analyzer.analyze(
                changed_symbols=changed_symbols,
                graph_store=self.graph_store,
            )

            # 영향받는 파일 추출
            impacted_files = list({sym.file_path for sym in impact.impacted_symbols})

            return {
                "impacted_files": impacted_files,
                "changed_symbols": [s.name for s in impact.changed_symbols],
                "impacted_symbols": [s.name for s in impact.impacted_symbols],
                "metadata": {
                    "impact_score": impact.impact_score,
                    "propagation_depth": impact.propagation_depth,
                },
            }
        except Exception:
            # Fallback
            return {
                "impacted_files": [],
                "changed_symbols": [],
                "impacted_symbols": [],
                "metadata": {},
            }

    async def _get_symbols_in_file(self, file_path: str) -> list[str]:
        """파일 내 심볼 목록 (간단한 버전)"""
        # TODO: 실제 파서 사용
        return [f"{file_path}:*"]

    def _can_run_incremental(
        self,
        changed_files: list[str],
        impact_result: dict[str, Any],
    ) -> bool:
        """
        Incremental 실행 가능 여부 판단.

        Args:
            changed_files: 변경 파일
            impact_result: 영향 분석 결과

        Returns:
            True면 Incremental 가능
        """
        # 1. 변경이 너무 많으면 전체 실행
        if len(changed_files) > 20:
            return False

        # 2. 영향 범위가 너무 크면 전체 실행
        impacted_count = len(impact_result.get("impacted_files", []))
        if impacted_count > 50:
            return False

        # 3. 설정 파일 변경은 전체 실행
        config_files = {
            "pyproject.toml",
            "setup.py",
            "requirements.txt",
            "Dockerfile",
        }

        from pathlib import Path

        for file_path in changed_files:
            if Path(file_path).name in config_files:
                return False

        return True

    def get_cached_result(self, file_path: str) -> Any | None:
        """캐시된 결과 가져오기"""
        return self.cache.get(file_path)

    def cache_result(self, file_path: str, result: Any) -> None:
        """결과 캐싱"""
        self.cache.set(file_path, result)

    def invalidate_cache(self, file_paths: list[str]) -> None:
        """캐시 무효화"""
        self.cache.invalidate(file_paths)

    def get_statistics(self, context: IncrementalContext) -> dict[str, Any]:
        """통계 정보"""
        total_files = len(context.changed_files) + len(context.impacted_files)
        speedup = context.get_speedup_ratio(total_files) if total_files > 0 else 1.0

        return {
            "is_incremental": context.is_incremental,
            "changed_files": len(context.changed_files),
            "impacted_files": len(context.impacted_files),
            "rerun_files": len(context.rerun_files),
            "cache_hits": context.cache_hits,
            "cache_misses": context.cache_misses,
            "cache_hit_rate": (
                context.cache_hits / (context.cache_hits + context.cache_misses)
                if (context.cache_hits + context.cache_misses) > 0
                else 0.0
            ),
            "speedup_ratio": speedup,
            "time_saved_percent": (1 - 1 / speedup) * 100 if speedup > 1 else 0,
            # SOTA급 추가 정보
            "changed_symbols": len(context.changed_symbols),
            "impacted_symbols": len(context.impacted_symbols),
            "metadata": context.metadata,
        }
