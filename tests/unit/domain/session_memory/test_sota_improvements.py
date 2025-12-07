"""
Session Memory SOTA Improvements Integration Tests

8개 핵심 컴포넌트 통합 테스트:
1. Config
2. Scoring
3. Reflection
4. Cache
5. Fallback
6. Metrics
7. Working Memory Auto-cleanup
8. Distributed Lock
"""

import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from src.contexts.session_memory.infrastructure.cache import (
    LRUCache,
    MemoryCacheManager,
    TieredCache,
)
from src.contexts.session_memory.infrastructure.config import (
    MemorySystemConfig,
    get_config,
    reset_config,
    set_config,
)
from src.contexts.session_memory.infrastructure.distributed_lock import (
    DistributedLock,
    DistributedLockManager,
)
from src.contexts.session_memory.infrastructure.embeddings import MockEmbeddingProvider
from src.contexts.session_memory.infrastructure.fallback import (
    CircuitBreaker,
    DegradationManager,
    FallbackStrategy,
)
from src.contexts.session_memory.infrastructure.metrics import get_metrics
from src.contexts.session_memory.infrastructure.models import Episode, TaskType
from src.contexts.session_memory.infrastructure.reflection import ReflectionEngine
from src.contexts.session_memory.infrastructure.scoring import (
    AdaptiveScoringEngine,
    MemoryScoringEngine,
)
from src.contexts.session_memory.infrastructure.working import WorkingMemoryManager


class TestConfig:
    """설정 관리 시스템 테스트"""

    def test_default_config(self):
        """기본 설정 로드"""
        reset_config()
        config = get_config()

        assert config.semantic.max_bug_patterns == 500
        assert config.working.max_steps == 1000
        assert config.retrieval.weight_similarity == 0.5
        assert config.cache.enable_l1_cache is True

    def test_development_config(self):
        """개발 환경 설정"""
        config = MemorySystemConfig.for_development()

        assert config.storage.storage_type == "file"
        assert config.cache.enable_l2_cache is False
        assert config.episodic.enable_embeddings is False

    def test_production_config(self):
        """프로덕션 환경 설정"""
        config = MemorySystemConfig.for_production()

        assert config.storage.storage_type == "postgres"
        assert config.cache.enable_l2_cache is True
        assert config.episodic.enable_embeddings is True
        assert config.reflection.enable_reflection is True

    def test_singleton_pattern(self):
        """Singleton 패턴 검증"""
        reset_config()
        config1 = get_config()
        config2 = get_config()

        assert config1 is config2


class TestScoring:
    """3축 메모리 스코어링 테스트"""

    def test_similarity_score(self):
        """유사도 점수 계산"""
        engine = MemoryScoringEngine()

        episode = Episode(
            id="test-1",
            task_description="Fix bug in auth module",
            task_type=TaskType.IMPLEMENTATION,
            project_id="test",
            created_at=datetime.now(),
            task_description_embedding=[0.1] * 1536,
        )

        query_embedding = [0.1] * 1536

        score = engine.score_episode(episode, query_embedding)

        assert 0.0 <= score.similarity <= 1.0
        assert score.similarity > 0.5  # Should be high for identical vectors

    def test_recency_decay(self):
        """최근성 점수 (시간 감쇠)"""
        engine = MemoryScoringEngine()

        # Recent episode
        recent = Episode(
            id="recent",
            task_description="Recent task",
            task_type=TaskType.IMPLEMENTATION,
            project_id="test",
            created_at=datetime.now(),
        )

        # Old episode (90 days ago)
        old = Episode(
            id="old",
            task_description="Old task",
            task_type=TaskType.IMPLEMENTATION,
            project_id="test",
            created_at=datetime.now() - timedelta(days=90),
        )

        recent_score = engine.score_episode(recent)
        old_score = engine.score_episode(old)

        # Recent should have higher recency score
        assert recent_score.recency > old_score.recency
        assert recent_score.recency > 0.9
        assert old_score.recency < 0.2

    def test_importance_score(self):
        """중요도 점수 계산"""
        engine = MemoryScoringEngine()

        # High importance episode
        important = Episode(
            id="important",
            task_description="Critical task",
            task_type=TaskType.IMPLEMENTATION,
            project_id="test",
            created_at=datetime.now(),
            outcome_status="success",
            retrieval_count=10,
            usefulness_score=0.9,
            steps_count=50,
        )

        # Low importance episode
        trivial = Episode(
            id="trivial",
            task_description="Trivial task",
            task_type=TaskType.IMPLEMENTATION,
            project_id="test",
            created_at=datetime.now(),
            outcome_status="failure",
            retrieval_count=0,
            usefulness_score=0.1,
            steps_count=2,
        )

        important_score = engine.score_episode(important)
        trivial_score = engine.score_episode(trivial)

        assert important_score.importance > trivial_score.importance
        assert important_score.importance > 0.7

    def test_composite_score(self):
        """종합 점수 계산"""
        engine = MemoryScoringEngine()

        episode = Episode(
            id="test",
            task_description="Test task",
            task_type=TaskType.IMPLEMENTATION,
            project_id="test",
            created_at=datetime.now(),
            outcome_status="success",
        )

        score = engine.score_episode(episode)

        # Composite should be weighted sum
        expected = (
            score.similarity * score.w_similarity
            + score.recency * score.w_recency
            + score.importance * score.w_importance
        )

        assert abs(score.composite_score - expected) < 0.01

    def test_adaptive_scoring(self):
        """적응형 스코어링 (피드백 기반 가중치 조정)"""
        engine = AdaptiveScoringEngine()

        episode = Episode(
            id="test",
            task_description="Test task",
            task_type=TaskType.IMPLEMENTATION,
            project_id="test",
            created_at=datetime.now(),
        )

        score = engine.score_episode(episode)

        # Record positive feedback
        for _ in range(5):
            engine.record_feedback(episode, helpful=True, score=score)

        # Record negative feedback
        for _ in range(5):
            engine.record_feedback(episode, helpful=False, score=score)

        # Auto-tune should be triggered (>=10 feedbacks)
        assert len(engine.feedback_history) == 10


@pytest.mark.asyncio
class TestReflection:
    """Reflection 엔진 테스트"""

    async def test_should_reflect(self):
        """Reflection 트리거 조건"""
        engine = ReflectionEngine()

        # Should reflect every 10 episodes
        assert await engine.should_reflect(10) is True
        assert await engine.should_reflect(20) is True
        assert await engine.should_reflect(15) is False

    async def test_rule_based_reflection(self):
        """Rule-based Reflection (LLM 없이)"""
        engine = ReflectionEngine(llm=None)

        episodes = [
            Episode(
                id=f"ep-{i}",
                task_description=f"Fix auth bug {i}",
                task_type=TaskType.IMPLEMENTATION,
                project_id="test",
                created_at=datetime.now(),
                outcome_status="success",
                files_involved=["auth.py", "user.py"],
                error_types=["AttributeError"],
                duration_ms=30000,
            )
            for i in range(5)
        ]

        reflections = await engine.reflect_on_episodes(episodes, project_id="test")

        assert len(reflections) > 0
        reflection = reflections[0]
        assert reflection.confidence == 0.6  # Rule-based
        assert len(reflection.semantic_memory.key_insights) > 0
        assert "auth.py" in reflection.semantic_memory.summary.lower()


@pytest.mark.asyncio
class TestCache:
    """캐싱 레이어 테스트"""

    def test_lru_cache_basic(self):
        """LRU 캐시 기본 동작"""
        cache = LRUCache[str](capacity=3)

        cache.put("a", "value_a")
        cache.put("b", "value_b")
        cache.put("c", "value_c")

        assert cache.get("a") == "value_a"
        assert cache.get("b") == "value_b"
        assert cache.size == 3

        # Evict LRU (c, since a and b were accessed)
        cache.put("d", "value_d")

        assert cache.get("c") is None  # Evicted
        assert cache.get("d") == "value_d"

    def test_lru_cache_hit_rate(self):
        """LRU 캐시 적중률"""
        cache = LRUCache[int](capacity=10)

        for i in range(10):
            cache.put(f"key{i}", i)

        # 5 hits
        for i in range(5):
            assert cache.get(f"key{i}") == i

        # 2 misses
        assert cache.get("nonexistent1") is None
        assert cache.get("nonexistent2") is None

        assert cache.hit_rate == 5 / 7  # 5 hits, 2 misses

    async def test_tiered_cache(self):
        """L1+L2 2-tier 캐시"""
        l1 = LRUCache[str](capacity=2)
        cache = TieredCache(l1_cache=l1, l2_cache=None)

        await cache.put("key1", "value1")
        await cache.put("key2", "value2")

        # L1 hit
        assert await cache.get("key1") == "value1"
        assert cache.l1_hit_rate > 0

    async def test_cache_manager(self):
        """Cache Manager (프로젝트별 캐싱)"""
        manager = MemoryCacheManager()
        await manager.initialize()

        # Project knowledge caching
        await manager.put_project_knowledge("proj1", {"info": "data"})
        result = await manager.get_project_knowledge("proj1")

        assert result == {"info": "data"}

        # Invalidation
        await manager.invalidate_project("proj1")
        result = await manager.get_project_knowledge("proj1")

        assert result is None


@pytest.mark.asyncio
class TestFallback:
    """장애 복구 메커니즘 테스트"""

    async def test_circuit_breaker_basic(self):
        """Circuit Breaker 기본 동작"""
        breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=1)

        async def failing_func():
            raise Exception("Failure")

        # Accumulate failures
        for _ in range(3):
            result, success = await breaker.call(failing_func)
            assert success is False

        # Circuit should be open now
        assert breaker.state.value == "unavailable"

    async def test_circuit_breaker_recovery(self):
        """Circuit Breaker 복구"""
        breaker = CircuitBreaker(failure_threshold=2, timeout_seconds=1)

        call_count = 0

        async def sometimes_failing():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Fail")
            return "success"

        # Fail twice (open circuit)
        await breaker.call(sometimes_failing)
        await breaker.call(sometimes_failing)

        assert breaker.state.value == "unavailable"

        # Wait for timeout
        await asyncio.sleep(1.1)

        # Should transition to degraded (half-open)
        assert breaker.state.value == "degraded"

        # Success should recover
        result, success = await breaker.call(sometimes_failing)

        assert success is True
        assert breaker.state.value == "healthy"

    async def test_fallback_strategy(self):
        """Fallback 전략 (Primary → Fallback)"""
        strategy = FallbackStrategy()

        async def primary():
            raise Exception("Primary failed")

        async def fallback():
            return "fallback_result"

        result, source = await strategy.try_with_fallback(primary, fallback, "test_service")

        assert result == "fallback_result"
        assert source == "fallback"

    def test_degradation_manager(self):
        """Degradation Manager (기능 제한)"""
        manager = DegradationManager()

        # Initially all enabled
        assert manager.is_enabled("reflection") is True
        assert manager.is_enabled("embeddings") is True

        # Degrade to level 2
        manager.degrade(2)

        assert manager.is_enabled("reflection") is False
        assert manager.is_enabled("embeddings") is False
        assert manager.is_enabled("working_memory") is True  # Core

    def test_auto_degrade_on_error(self):
        """에러율 기반 자동 degradation"""
        manager = DegradationManager()

        # High error rate (>50%)
        manager.auto_degrade_on_error(0.6)

        assert manager.current_level == 4  # Minimal mode
        assert manager.is_enabled("reflection") is False


class TestMetrics:
    """모니터링 메트릭 테스트"""

    def test_metrics_recording(self):
        """메트릭 기록"""
        metrics = get_metrics()

        # Working memory metrics
        metrics.record_working_memory_size(session_id="test", steps=10, files=5, symbols=20, hypotheses=3)

        # Episode creation
        metrics.record_episode_created(
            project_id="test", task_type="implementation", duration_ms=5000, outcome="success"
        )

        # No exceptions should occur
        assert True

    def test_uptime(self):
        """시스템 가동 시간"""
        metrics = get_metrics()
        uptime = metrics.get_uptime_seconds()

        assert uptime >= 0


@pytest.mark.asyncio
class TestWorkingMemoryAutoCleanup:
    """Working Memory Auto-cleanup 테스트"""

    def test_auto_cleanup_trigger(self):
        """Auto-cleanup 트리거 조건"""
        config = MemorySystemConfig.for_development()
        config.working.max_steps = 10
        config.working.max_files = 5
        config.working.cleanup_threshold_ratio = 0.8

        working = WorkingMemoryManager(config=config.working)

        # Fill beyond threshold
        for i in range(9):  # 9 > 10 * 0.8
            from src.contexts.session_memory.infrastructure.models import StepRecord

            working.steps_completed.append(
                StepRecord(
                    step_number=i,
                    action="test",
                    result="ok",
                    timestamp=datetime.now(),
                )
            )

        assert working._should_auto_cleanup() is True

    def test_auto_cleanup_execution(self):
        """Auto-cleanup 실행"""
        config = MemorySystemConfig.for_development()
        config.working.max_steps = 10

        working = WorkingMemoryManager(config=config.working)

        # Add 20 steps
        for i in range(20):
            from src.contexts.session_memory.infrastructure.models import StepRecord

            working.steps_completed.append(
                StepRecord(
                    step_number=i,
                    action="test",
                    result="ok",
                    timestamp=datetime.now(),
                )
            )

        stats = working.auto_cleanup()

        # Should keep only 80% (8 steps)
        assert len(working.steps_completed) == 8
        assert stats["steps"] > 0


@pytest.mark.asyncio
class TestDistributedLock:
    """분산 락 테스트 (Redis 없이 fallback 모드)"""

    async def test_lock_acquisition(self):
        """락 획득 (fallback mode)"""
        lock = DistributedLock(
            redis_url="redis://localhost:6379",
            lock_key="test_lock",
            ttl_seconds=10,
        )

        # Redis 없어도 fallback으로 동작
        acquired = await lock.acquire(blocking=False)

        assert acquired is True
        assert lock.is_acquired is True

        await lock.release()
        assert lock.is_acquired is False

    async def test_lock_context_manager(self):
        """락 context manager"""
        lock = DistributedLock(
            redis_url="redis://localhost:6379",
            lock_key="test_lock_cm",
        )

        async with lock.lock() as acquired:
            assert acquired is True
            # Critical section
            await asyncio.sleep(0.01)

        # Should auto-release
        assert lock.is_acquired is False

    async def test_lock_manager(self):
        """Lock Manager"""
        manager = DistributedLockManager(redis_url="redis://localhost:6379")

        async with manager.acquire_lock("resource_1") as acquired:
            assert acquired is True


@pytest.mark.asyncio
class TestFullIntegration:
    """전체 통합 테스트"""

    async def test_end_to_end_workflow(self):
        """End-to-end 워크플로우"""
        # 1. Config
        config = MemorySystemConfig.for_development()
        set_config(config)

        # 2. Working Memory with auto-cleanup
        working = WorkingMemoryManager(config=config.working)
        working.start_task({"description": "Test task"})

        # 3. Episode creation
        episode = Episode(
            id=str(uuid4()),
            task_description="Implement feature X",
            task_type=TaskType.IMPLEMENTATION,
            project_id="test",
            created_at=datetime.now(),
            outcome_status="success",
            retrieval_count=0,
        )

        # 4. Scoring
        engine = MemoryScoringEngine(config=config.retrieval)
        score = engine.score_episode(episode)

        assert 0.0 <= score.composite_score <= 1.0

        # 5. Cache
        cache_manager = MemoryCacheManager(config=config.cache)
        await cache_manager.initialize()

        # 6. Metrics
        metrics = get_metrics()
        metrics.record_episode_created(
            project_id="test",
            task_type="implementation",
            duration_ms=1000,
            outcome="success",
        )

        # 7. Fallback (circuit breaker)
        strategy = FallbackStrategy()

        async def primary():
            return "primary_result"

        async def fallback():
            return "fallback_result"

        result, source = await strategy.try_with_fallback(primary, fallback)

        assert result == "primary_result"
        assert source == "primary"

        # All components working together!
        assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
