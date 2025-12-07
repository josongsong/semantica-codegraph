"""
Reflection Engine

Generative Agents (Stanford 2023) 스타일 고차원 요약 생성
여러 에피소드에서 일반화된 패턴 추출
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from src.infra.observability import get_logger, record_counter

from .config import get_config
from .models import Episode, ReflectionResult, SemanticMemory, TaskType

logger = get_logger(__name__)


class ReflectionEngine:
    """
    Reflection 엔진

    N개의 에피소드를 분석하여 고차원 패턴 생성
    """

    def __init__(
        self,
        llm: Any | None = None,
        config: Any | None = None,
    ):
        """
        Initialize reflection engine

        Args:
            llm: LLM provider (OpenAI, LiteLLM 등)
            config: ReflectionConfig
        """
        self.llm = llm
        self.config = config or get_config().reflection
        self._reflection_count = 0

    async def should_reflect(self, episode_count: int) -> bool:
        """
        Reflection을 수행해야 하는지 판단

        Args:
            episode_count: 현재까지 저장된 에피소드 수

        Returns:
            True if reflection should be triggered
        """
        if not self.config.enable_reflection:
            return False

        # N개마다 reflection
        return episode_count % self.config.reflection_interval_episodes == 0

    async def reflect_on_episodes(
        self,
        episodes: list[Episode],
        project_id: str = "default",
    ) -> list[ReflectionResult]:
        """
        여러 에피소드에서 고차원 패턴 추출

        Args:
            episodes: 반영할 에피소드 목록
            project_id: 프로젝트 ID

        Returns:
            추출된 SemanticMemory 리스트
        """
        if not episodes:
            return []

        # 중요도 필터링
        important_episodes = [
            ep for ep in episodes if self._calculate_episode_importance(ep) >= self.config.reflection_min_importance
        ]

        if not important_episodes:
            logger.debug("no_important_episodes_for_reflection", total=len(episodes))
            return []

        # 태스크 타입별로 그룹화
        grouped = self._group_by_task_type(important_episodes)

        reflections: list[ReflectionResult] = []

        for task_type, eps in grouped.items():
            if len(eps) < 3:  # 최소 3개 이상
                continue

            reflection = await self._reflect_on_group(eps, task_type, project_id)
            if reflection:
                reflections.append(reflection)
                record_counter("memory_reflections_created_total", labels={"task_type": task_type.value})

        self._reflection_count += len(reflections)

        logger.info(
            "reflection_complete",
            total_episodes=len(episodes),
            important=len(important_episodes),
            reflections=len(reflections),
        )

        return reflections

    async def _reflect_on_group(
        self,
        episodes: list[Episode],
        task_type: TaskType,
        project_id: str,
    ) -> ReflectionResult | None:
        """
        같은 타입의 에피소드 그룹에서 패턴 추출

        Args:
            episodes: 에피소드 그룹
            task_type: 태스크 타입
            project_id: 프로젝트 ID

        Returns:
            ReflectionResult 또는 None
        """
        # LLM이 없으면 rule-based fallback
        if self.llm is None:
            return self._rule_based_reflection(episodes, task_type, project_id)

        # LLM 기반 reflection
        return await self._llm_based_reflection(episodes, task_type, project_id)

    async def _llm_based_reflection(
        self,
        episodes: list[Episode],
        task_type: TaskType,
        project_id: str,
    ) -> ReflectionResult | None:
        """
        LLM 기반 고차원 요약 생성

        Args:
            episodes: 에피소드 그룹
            task_type: 태스크 타입
            project_id: 프로젝트 ID

        Returns:
            ReflectionResult
        """
        # Prepare context
        context = self._prepare_reflection_context(episodes)

        # Reflection prompt
        prompt = (
            f"Given the following {len(episodes)} successful "
            f"{task_type.value} episodes, extract key insights and patterns:"
        )
        prompt = f"""{prompt}

{context}

Generate a concise summary (max 3 sentences) that captures:
1. Common patterns or approaches
2. Key lessons learned
3. Best practices

Focus on generalizable insights that can help with future similar tasks."""

        try:
            # Call LLM
            response = await self.llm.complete(
                prompt=prompt,
                model=self.config.reflection_model,
                max_tokens=self.config.reflection_max_tokens,
            )

            summary = response.strip()

            # Extract key insights
            insights = self._extract_insights_from_summary(summary)

            # Create semantic memory
            semantic_memory = SemanticMemory(
                id=str(uuid4()),
                project_id=project_id,
                title=f"{task_type.value} patterns",
                summary=summary,
                key_insights=insights,
                source_episode_ids=[ep.id for ep in episodes],
                source_count=len(episodes),
                category=f"{task_type.value}_pattern",
                tags=[task_type.value, "reflection", "pattern"],
                importance=self._calculate_group_importance(episodes),
                created_at=datetime.now(),
            )

            return ReflectionResult(
                semantic_memory=semantic_memory,
                source_episodes=[ep.id for ep in episodes],
                reflection_prompt=prompt,
                llm_response=summary,
                confidence=0.8,  # LLM-based = high confidence
                created_at=datetime.now(),
            )

        except Exception as e:
            logger.error("llm_reflection_failed", error=str(e))
            # Fallback to rule-based
            return self._rule_based_reflection(episodes, task_type, project_id)

    def _rule_based_reflection(
        self,
        episodes: list[Episode],
        task_type: TaskType,
        project_id: str,
    ) -> ReflectionResult:
        """
        Rule-based 패턴 추출 (LLM 없이)

        Args:
            episodes: 에피소드 그룹
            task_type: 태스크 타입
            project_id: 프로젝트 ID

        Returns:
            ReflectionResult
        """
        # 공통 파일 추출
        all_files = []
        for ep in episodes:
            all_files.extend(ep.files_involved)

        from collections import Counter

        file_counts = Counter(all_files)
        common_files = [f for f, c in file_counts.most_common(5) if c >= 2]

        # 공통 에러 타입
        all_errors = []
        for ep in episodes:
            all_errors.extend(ep.error_types)

        error_counts = Counter(all_errors)
        common_errors = [e for e, c in error_counts.most_common(3)]

        # 성공률 계산
        success_count = sum(1 for ep in episodes if ep.outcome_status.value == "success")
        success_rate = success_count / len(episodes) if episodes else 0.0

        # 평균 해결 시간
        avg_duration = sum(ep.duration_ms for ep in episodes) / len(episodes)

        # Summary 생성
        summary = f"Analyzed {len(episodes)} {task_type.value} tasks. "
        summary += f"Success rate: {success_rate:.1%}. "
        if common_files:
            summary += f"Frequently modified files: {', '.join(common_files[:3])}. "
        if common_errors:
            summary += f"Common errors: {', '.join(common_errors)}. "
        summary += f"Avg resolution time: {avg_duration / 1000:.1f}s."

        # Insights
        insights = []
        if success_rate > 0.8:
            insights.append(f"High success rate ({success_rate:.0%}) indicates well-understood pattern")
        if common_files:
            insights.append(f"Focus area: {common_files[0]}")
        if avg_duration < 60000:  # < 1 min
            insights.append("Quick resolution pattern - likely simple fix")

        semantic_memory = SemanticMemory(
            id=str(uuid4()),
            project_id=project_id,
            title=f"{task_type.value} patterns (rule-based)",
            summary=summary,
            key_insights=insights,
            source_episode_ids=[ep.id for ep in episodes],
            source_count=len(episodes),
            category=f"{task_type.value}_pattern",
            tags=[task_type.value, "reflection", "rule_based"],
            importance=self._calculate_group_importance(episodes),
            created_at=datetime.now(),
        )

        return ReflectionResult(
            semantic_memory=semantic_memory,
            source_episodes=[ep.id for ep in episodes],
            reflection_prompt="Rule-based reflection (no LLM)",
            llm_response=summary,
            confidence=0.6,  # Rule-based = medium confidence
            created_at=datetime.now(),
        )

    def _prepare_reflection_context(self, episodes: list[Episode]) -> str:
        """
        Reflection을 위한 컨텍스트 준비

        Args:
            episodes: 에피소드 목록

        Returns:
            Context string for LLM
        """
        context_parts = []

        for i, ep in enumerate(episodes[:10], 1):  # 최대 10개
            context_parts.append(f"{i}. {ep.task_description}")
            if ep.solution_pattern:
                context_parts.append(f"   Solution: {ep.solution_pattern}")
            if ep.tips:
                context_parts.append(f"   Tips: {', '.join(ep.tips[:2])}")

        return "\n".join(context_parts)

    def _extract_insights_from_summary(self, summary: str) -> list[str]:
        """
        요약에서 핵심 인사이트 추출

        Args:
            summary: LLM 생성 요약

        Returns:
            Insight 리스트
        """
        # Simple extraction: 문장 단위 분할
        sentences = [s.strip() for s in summary.split(".") if s.strip()]
        return sentences[:5]  # 최대 5개

    def _calculate_episode_importance(self, episode: Episode) -> float:
        """
        에피소드 중요도 계산

        Args:
            episode: 에피소드

        Returns:
            Importance score (0.0-1.0)
        """
        importance = 0.0

        # Success = important
        if episode.outcome_status.value == "success":
            importance += 0.4

        # High retrieval count = important
        if episode.retrieval_count > 5:
            importance += 0.3

        # User feedback = important
        if episode.user_feedback == "positive":
            importance += 0.2

        # Complexity = important
        if episode.steps_count > 20:
            importance += 0.1

        return min(1.0, importance)

    def _calculate_group_importance(self, episodes: list[Episode]) -> float:
        """
        그룹 중요도 계산

        Args:
            episodes: 에피소드 그룹

        Returns:
            Group importance (0.0-1.0)
        """
        if not episodes:
            return 0.0

        avg_importance = sum(self._calculate_episode_importance(ep) for ep in episodes) / len(episodes)

        # 에피소드 수 보너스
        count_bonus = min(0.2, len(episodes) * 0.02)

        return min(1.0, avg_importance + count_bonus)

    def _group_by_task_type(self, episodes: list[Episode]) -> dict[TaskType, list[Episode]]:
        """
        태스크 타입별로 에피소드 그룹화

        Args:
            episodes: 에피소드 목록

        Returns:
            TaskType -> Episodes 딕셔너리
        """
        grouped: dict[TaskType, list[Episode]] = {}

        for ep in episodes:
            if ep.task_type not in grouped:
                grouped[ep.task_type] = []
            grouped[ep.task_type].append(ep)

        return grouped

    def get_statistics(self) -> dict[str, Any]:
        """Reflection 통계"""
        return {
            "total_reflections": self._reflection_count,
            "enabled": self.config.enable_reflection,
            "interval": self.config.reflection_interval_episodes,
        }
