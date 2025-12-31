"""Freeze Buffer - Compaction 중 write 임시 저장."""

from typing import TYPE_CHECKING

from codegraph_shared.infra.observability import get_logger

if TYPE_CHECKING:
    from codegraph_shared.infra.cache.redis import RedisAdapter

logger = get_logger(__name__)


class FreezeBuffer:
    """Freeze Buffer.

    Compaction 중 Delta write를 임시 저장하는 버퍼.
    Redis Streams 기반.
    """

    def __init__(self, redis: "RedisAdapter"):
        """
        Args:
            redis: RedisAdapter 인스턴스
        """
        self.redis = redis
        self.stream_key_prefix = "freeze_buffer:"

    def _get_stream_key(self, repo_id: str) -> str:
        """Stream key 생성."""
        return f"{self.stream_key_prefix}{repo_id}"

    async def append(
        self,
        repo_id: str,
        operation: str,
        file_path: str,
        content: str | None = None,
    ) -> None:
        """Write 이벤트 추가.

        Args:
            repo_id: 저장소 ID
            operation: 작업 타입 (index, delete)
            file_path: 파일 경로
            content: 파일 내용 (index 시)
        """
        stream_key = self._get_stream_key(repo_id)

        # Redis Streams에 추가
        event: dict[str, str | int | float] = {
            "operation": operation,
            "file_path": file_path,
            "content": content or "",
        }

        # RedisAdapter를 통해 추가
        client = await self.redis._get_client()
        await client.xadd(stream_key, event)

        logger.debug(
            f"Appended to freeze buffer: {operation} {file_path}",
            extra={"repo_id": repo_id, "operation": operation},
        )

    async def replay(self, repo_id: str) -> list[dict]:
        """Freeze buffer replay (Compaction Phase 3).

        Args:
            repo_id: 저장소 ID

        Returns:
            이벤트 리스트
        """
        stream_key = self._get_stream_key(repo_id)

        try:
            # Redis Streams에서 모든 이벤트 읽기
            client = await self.redis._get_client()
            events = await client.xrange(stream_key)

            replayed = []
            for _event_id, event_data in events:
                replayed.append(event_data)

            logger.info(
                f"Replayed {len(replayed)} events from freeze buffer",
                extra={"repo_id": repo_id, "count": len(replayed)},
            )

            return replayed

        except Exception as e:
            logger.error(f"Freeze buffer replay error: {e}")
            return []

    async def clear(self, repo_id: str) -> None:
        """Freeze buffer 초기화.

        Args:
            repo_id: 저장소 ID
        """
        stream_key = self._get_stream_key(repo_id)

        try:
            await self.redis.delete(stream_key)
            logger.info(f"Cleared freeze buffer: {repo_id}")
        except Exception as e:
            logger.error(f"Freeze buffer clear error: {e}")

    async def is_frozen(self, repo_id: str) -> bool:
        """Freeze 상태 확인.

        Args:
            repo_id: 저장소 ID

        Returns:
            Freeze 여부
        """
        stream_key = self._get_stream_key(repo_id)
        exists = await self.redis.get(f"{stream_key}:frozen")
        return exists is not None

    async def set_frozen(self, repo_id: str, frozen: bool) -> None:
        """Freeze 상태 설정.

        Args:
            repo_id: 저장소 ID
            frozen: Freeze 여부
        """
        stream_key = self._get_stream_key(repo_id)
        freeze_key = f"{stream_key}:frozen"

        if frozen:
            await self.redis.set(freeze_key, "1")  # TTL은 RedisAdapter 내부 처리
        else:
            await self.redis.delete(freeze_key)
