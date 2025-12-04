"""Prompt Cache - 프롬프트 캐싱 관리."""

from typing import TYPE_CHECKING, Any

from src.contexts.agent_automation.infrastructure.cache.hasher import PromptHasher
from src.infra.observability import get_logger, record_counter

if TYPE_CHECKING:
    from src.contexts.agent_automation.infrastructure.cache.store import RedisCacheStore

logger = get_logger(__name__)


class PromptCache:
    """프롬프트 캐시.

    LLM 프롬프트와 응답을 캐싱하여
    동일한 요청에 대해 재사용합니다.
    """

    def __init__(
        self,
        store: "RedisCacheStore",
        enable_cache: bool = True,
    ):
        """
        Args:
            store: RedisCacheStore 인스턴스
            enable_cache: 캐시 활성화 여부
        """
        self.store = store
        self.enable_cache = enable_cache
        self.hasher = PromptHasher()

    async def get_cached_response(
        self,
        prompt: str,
        model: str,
        **kwargs,
    ) -> Any | None:
        """캐시된 응답 조회.

        Args:
            prompt: 프롬프트
            model: 모델 이름
            **kwargs: 추가 파라미터

        Returns:
            캐시된 응답 또는 None
        """
        if not self.enable_cache:
            return None

        # 해시 생성
        cache_key = self.hasher.hash_prompt(prompt, model, **kwargs)

        # 캐시 조회
        cached = await self.store.get(cache_key)

        if cached:
            record_counter("prompt_cache_hit_total", labels={"model": model})
            logger.info(
                f"Prompt cache hit: model={model}",
                extra={"model": model, "cache_key": cache_key[:16]},
            )
        else:
            record_counter("prompt_cache_miss_total", labels={"model": model})

        return cached

    async def cache_response(
        self,
        prompt: str,
        model: str,
        response: Any,
        **kwargs,
    ) -> bool:
        """응답 캐싱.

        Args:
            prompt: 프롬프트
            model: 모델 이름
            response: 응답 (LLM 응답 객체)
            **kwargs: 추가 파라미터

        Returns:
            성공 여부
        """
        if not self.enable_cache:
            return False

        # 해시 생성
        cache_key = self.hasher.hash_prompt(prompt, model, **kwargs)

        # 캐시 저장
        success = await self.store.set(cache_key, response)

        if success:
            logger.info(
                f"Prompt cached: model={model}",
                extra={"model": model, "cache_key": cache_key[:16]},
            )

        return success

    async def invalidate_context(self, context: str) -> int:
        """특정 컨텍스트와 관련된 캐시 무효화.

        Args:
            context: 컨텍스트 문자열

        Returns:
            무효화된 캐시 개수
        """
        # 간단한 구현: 컨텍스트 해시 기반 키 삭제
        context_hash = self.hasher.hash_context(context)

        # TODO: 컨텍스트와 연관된 모든 캐시 키를 추적하는 메커니즘 필요
        # 지금은 스킵
        logger.info(f"Context invalidation not fully implemented: hash={context_hash[:16]}")
        return 0

    async def clear_all(self) -> int:
        """모든 캐시 삭제.

        Returns:
            삭제된 캐시 개수
        """
        return await self.store.clear_all()

    def get_stats(self) -> dict[str, Any]:
        """캐시 통계.

        Returns:
            통계 딕셔너리
        """
        # TODO: Redis INFO 명령으로 통계 수집
        return {
            "enabled": self.enable_cache,
        }
