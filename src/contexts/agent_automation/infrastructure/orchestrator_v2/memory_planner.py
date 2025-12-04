"""
Memory-aware Planner - 과거 경험 기반 Planning

Memory 시스템에서 유사한 과거 작업을 조회하여 planning에 활용합니다.
"""

from typing import TYPE_CHECKING, Any

from src.contexts.agent_automation.infrastructure.orchestrator_v2.state import SubTask
from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.contexts.session_memory.infrastructure.service import MemoryService

logger = get_logger(__name__)


class MemoryAwarePlanner:
    """
    Memory-aware Task Planner.

    과거 실행 기록에서 유사한 작업을 찾아:
    1. 성공한 패턴 재사용
    2. 실패한 접근법 회피
    3. 예상 시간/난이도 추정
    """

    def __init__(
        self,
        memory_service: "MemoryService | None" = None,
        similarity_threshold: float = 0.7,
    ):
        """
        Args:
            memory_service: Memory service
            similarity_threshold: 유사도 임계값 (0.0~1.0)
        """
        self.memory_service = memory_service
        self.similarity_threshold = similarity_threshold

    async def enhance_plan(
        self,
        tasks: list[SubTask],
        user_request: str,
        repo_id: str,
        session_id: str | None = None,
    ) -> list[SubTask]:
        """
        Memory 기반 planning 개선.

        Args:
            tasks: 기본 planning 결과
            user_request: 사용자 요청
            repo_id: 저장소 ID
            session_id: 세션 ID (optional)

        Returns:
            개선된 SubTask 리스트
        """
        if not self.memory_service:
            logger.info("Memory service not available, skipping memory enhancement")
            return tasks

        logger.info(f"Enhancing plan with memory for: {user_request[:100]}")

        # 1. 유사한 과거 작업 조회
        similar_episodes = await self._recall_similar_tasks(user_request, repo_id, session_id)

        if not similar_episodes:
            logger.info("No similar past tasks found")
            return tasks

        logger.info(f"Found {len(similar_episodes)} similar past tasks")

        # 2. 과거 패턴 분석
        patterns = self._analyze_patterns(similar_episodes)

        # 3. Task 개선
        enhanced_tasks = self._apply_patterns(tasks, patterns)

        # 4. 메타데이터 추가
        for task in enhanced_tasks:
            task["metadata"]["memory_enhanced"] = True
            task["metadata"]["similar_episodes"] = len(similar_episodes)
            if patterns.get("estimated_duration"):
                task["metadata"]["estimated_duration"] = patterns["estimated_duration"]

        return enhanced_tasks

    async def _recall_similar_tasks(
        self,
        user_request: str,
        repo_id: str,
        session_id: str | None,
    ) -> list[dict[str, Any]]:
        """
        유사한 과거 작업 조회.

        Args:
            user_request: 사용자 요청
            repo_id: 저장소 ID
            session_id: 세션 ID

        Returns:
            유사한 에피소드 리스트
        """
        if not self.memory_service:
            return []

        try:
            # Memory service에서 유사한 에피소드 조회
            episodes = await self.memory_service.recall_similar_episodes(
                query=user_request,
                repo_id=repo_id,
                limit=5,
                min_similarity=self.similarity_threshold,
            )

            return episodes

        except Exception as e:
            logger.warning(f"Failed to recall similar tasks: {e}")
            return []

    def _analyze_patterns(self, episodes: list[dict[str, Any]]) -> dict[str, Any]:
        """
        과거 에피소드에서 패턴 분석.

        Args:
            episodes: 과거 에피소드 리스트

        Returns:
            분석된 패턴
        """
        patterns: dict[str, Any] = {
            "successful_approaches": [],
            "failed_approaches": [],
            "common_pitfalls": [],
            "estimated_duration": None,
            "recommended_order": [],
        }

        successful_episodes = [e for e in episodes if e.get("outcome") == "success"]
        failed_episodes = [e for e in episodes if e.get("outcome") == "failure"]

        # 1. 성공한 접근법 추출
        for episode in successful_episodes:
            if approach := episode.get("approach"):
                patterns["successful_approaches"].append(approach)

        # 2. 실패한 접근법 추출
        for episode in failed_episodes:
            if approach := episode.get("approach"):
                patterns["failed_approaches"].append(approach)
            if error := episode.get("error"):
                patterns["common_pitfalls"].append(error)

        # 3. 평균 소요 시간 추정
        if successful_episodes:
            durations = [e.get("duration", 0) for e in successful_episodes if e.get("duration")]
            if durations:
                patterns["estimated_duration"] = sum(durations) / len(durations)

        # 4. 권장 순서 (가장 성공적인 에피소드 기준)
        if successful_episodes:
            best_episode = max(successful_episodes, key=lambda e: e.get("quality_score", 0))
            if task_order := best_episode.get("task_order"):
                patterns["recommended_order"] = task_order

        return patterns

    def _apply_patterns(
        self,
        tasks: list[SubTask],
        patterns: dict[str, Any],
    ) -> list[SubTask]:
        """
        패턴을 tasks에 적용.

        Args:
            tasks: 기본 tasks
            patterns: 분석된 패턴

        Returns:
            개선된 tasks
        """
        enhanced_tasks = list(tasks)

        # 1. Task 순서 조정 (권장 순서가 있으면)
        if patterns.get("recommended_order"):
            enhanced_tasks = self._reorder_by_pattern(enhanced_tasks, patterns["recommended_order"])

        # 2. 주의사항 추가
        if patterns.get("common_pitfalls"):
            for task in enhanced_tasks:
                task["metadata"]["warnings"] = patterns["common_pitfalls"][:3]

        # 3. 권장 접근법 추가
        if patterns.get("successful_approaches"):
            for task in enhanced_tasks:
                task["metadata"]["recommended_approach"] = patterns["successful_approaches"][0]

        return enhanced_tasks

    def _reorder_by_pattern(
        self,
        tasks: list[SubTask],
        recommended_order: list[str],
    ) -> list[SubTask]:
        """
        권장 순서에 따라 task 재정렬.

        Args:
            tasks: 원본 tasks
            recommended_order: 권장 task 타입 순서 (예: ["implementation", "test", "doc"])

        Returns:
            재정렬된 tasks
        """
        # Task type별로 그룹화
        task_by_type: dict[str, list[SubTask]] = {}
        for task in tasks:
            task_type = task.get("metadata", {}).get("type", "generic")
            if task_type not in task_by_type:
                task_by_type[task_type] = []
            task_by_type[task_type].append(task)

        # 권장 순서대로 재구성
        reordered = []
        for task_type in recommended_order:
            if task_type in task_by_type:
                reordered.extend(task_by_type[task_type])
                del task_by_type[task_type]

        # 남은 tasks 추가
        for remaining_tasks in task_by_type.values():
            reordered.extend(remaining_tasks)

        return reordered

    async def record_execution(
        self,
        user_request: str,
        tasks: list[SubTask],
        outcome: str,
        duration: float,
        quality_score: float,
        repo_id: str,
        session_id: str | None = None,
    ) -> None:
        """
        실행 결과를 Memory에 기록.

        Args:
            user_request: 사용자 요청
            tasks: 실행한 tasks
            outcome: 결과 ("success" or "failure")
            duration: 소요 시간 (초)
            quality_score: 품질 점수 (0.0~1.0)
            repo_id: 저장소 ID
            session_id: 세션 ID
        """
        if not self.memory_service:
            return

        try:
            # Episodic Memory에 기록
            episode = {
                "task": user_request,
                "repo_id": repo_id,
                "session_id": session_id,
                "task_count": len(tasks),
                "task_order": [t.get("metadata", {}).get("type") for t in tasks],
                "outcome": outcome,
                "duration": duration,
                "quality_score": quality_score,
            }

            await self.memory_service.store_episode(episode)
            logger.info(f"Recorded execution to memory: outcome={outcome}, duration={duration:.1f}s")

        except Exception as e:
            logger.warning(f"Failed to record execution to memory: {e}")
