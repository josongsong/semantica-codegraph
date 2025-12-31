"""
Content Hash Checker - 가짜 변경 필터링.

IDE가 파일을 저장할 때 실제 내용이 바뀌지 않아도 이벤트가 발생합니다.
이 모듈은 파일 내용의 해시를 비교하여 실제 변경만 통과시킵니다.

주요 기능:
- 빠른 해시 비교 (xxHash64)
- 메모리 내 해시 캐시
- 영구 저장소 지원 (Redis/PostgreSQL)
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from codegraph_engine.analysis_indexing.infrastructure.change_detector import ChangeSet
from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


# xxHash가 있으면 사용 (더 빠름), 없으면 MD5 fallback
try:
    import xxhash

    def compute_hash(content: bytes) -> str:
        """xxHash64로 해시 계산 (고속)."""
        return xxhash.xxh64(content).hexdigest()

except ImportError:

    def compute_hash(content: bytes) -> str:
        """MD5로 해시 계산 (fallback)."""
        return hashlib.md5(content).hexdigest()


@dataclass
class FileHashEntry:
    """파일 해시 엔트리."""

    file_path: str
    content_hash: str
    size: int
    mtime: float
    updated_at: datetime = field(default_factory=datetime.utcnow)


class HashStore(Protocol):
    """해시 저장소 프로토콜."""

    def get(self, repo_id: str, file_path: str) -> FileHashEntry | None:
        """파일 해시 조회."""
        ...

    def set(self, repo_id: str, entry: FileHashEntry) -> None:
        """파일 해시 저장."""
        ...

    def delete(self, repo_id: str, file_path: str) -> None:
        """파일 해시 삭제."""
        ...

    def get_batch(self, repo_id: str, file_paths: list[str]) -> dict[str, FileHashEntry]:
        """여러 파일 해시 일괄 조회."""
        ...

    def set_batch(self, repo_id: str, entries: list[FileHashEntry]) -> None:
        """여러 파일 해시 일괄 저장."""
        ...


class InMemoryHashStore:
    """메모리 내 해시 저장소."""

    def __init__(self, max_entries: int = 100_000):
        self._store: dict[str, dict[str, FileHashEntry]] = {}
        self._max_entries = max_entries

    def get(self, repo_id: str, file_path: str) -> FileHashEntry | None:
        repo_store = self._store.get(repo_id, {})
        return repo_store.get(file_path)

    def set(self, repo_id: str, entry: FileHashEntry) -> None:
        if repo_id not in self._store:
            self._store[repo_id] = {}
        self._store[repo_id][entry.file_path] = entry

        # 간단한 크기 제한 (LRU는 생략)
        if len(self._store[repo_id]) > self._max_entries:
            # 가장 오래된 10% 삭제
            sorted_entries = sorted(
                self._store[repo_id].items(),
                key=lambda x: x[1].updated_at,
            )
            for path, _ in sorted_entries[: self._max_entries // 10]:
                del self._store[repo_id][path]

    def delete(self, repo_id: str, file_path: str) -> None:
        if repo_id in self._store and file_path in self._store[repo_id]:
            del self._store[repo_id][file_path]

    def get_batch(self, repo_id: str, file_paths: list[str]) -> dict[str, FileHashEntry]:
        repo_store = self._store.get(repo_id, {})
        return {path: repo_store[path] for path in file_paths if path in repo_store}

    def set_batch(self, repo_id: str, entries: list[FileHashEntry]) -> None:
        for entry in entries:
            self.set(repo_id, entry)


class RedisHashStore:
    """
    Redis 기반 해시 저장소.

    영구 저장소로 서버 재시작 후에도 해시 정보를 유지합니다.
    HSET/HGET을 사용하여 레포별로 해시 엔트리를 관리합니다.

    Key 구조:
        file_hash:{repo_id} → Hash { file_path: json(FileHashEntry) }

    사용 예:
        from codegraph_shared.infra.cache.redis import RedisAdapter
        redis_adapter = RedisAdapter(host="localhost", port=6379)
        store = RedisHashStore(redis_adapter, expire_seconds=86400)
    """

    def __init__(
        self,
        redis_adapter,
        key_prefix: str = "file_hash",
        expire_seconds: int | None = 86400,  # 24시간 기본 TTL
    ):
        """
        Args:
            redis_adapter: RedisAdapter 인스턴스
            key_prefix: Redis 키 접두사
            expire_seconds: 해시 만료 시간 (초), None이면 만료 없음
        """
        import json

        self._json = json
        self._redis = redis_adapter
        self._key_prefix = key_prefix
        self._expire_seconds = expire_seconds
        # 동기 API를 위한 메모리 캐시 (async 환경에서의 fallback)
        self._memory_fallback = InMemoryHashStore()
        self._use_fallback = False

    def _make_key(self, repo_id: str) -> str:
        """Redis 키 생성."""
        return f"{self._key_prefix}:{repo_id}"

    def _serialize_entry(self, entry: FileHashEntry) -> str:
        """FileHashEntry를 JSON 문자열로 직렬화."""
        return self._json.dumps(
            {
                "file_path": entry.file_path,
                "content_hash": entry.content_hash,
                "size": entry.size,
                "mtime": entry.mtime,
                "updated_at": entry.updated_at.isoformat(),
            }
        )

    def _deserialize_entry(self, data: str) -> FileHashEntry:
        """JSON 문자열을 FileHashEntry로 역직렬화."""
        obj = self._json.loads(data)
        return FileHashEntry(
            file_path=obj["file_path"],
            content_hash=obj["content_hash"],
            size=obj["size"],
            mtime=obj["mtime"],
            updated_at=datetime.fromisoformat(obj["updated_at"]),
        )

    def get(self, repo_id: str, file_path: str) -> FileHashEntry | None:
        """파일 해시 조회."""
        # 동기 컨텍스트에서는 메모리 fallback 사용
        return self._memory_fallback.get(repo_id, file_path)

    def set(self, repo_id: str, entry: FileHashEntry) -> None:
        """파일 해시 저장."""
        self._memory_fallback.set(repo_id, entry)

    def delete(self, repo_id: str, file_path: str) -> None:
        """파일 해시 삭제."""
        self._memory_fallback.delete(repo_id, file_path)

    def get_batch(self, repo_id: str, file_paths: list[str]) -> dict[str, FileHashEntry]:
        """여러 파일 해시 일괄 조회."""
        return self._memory_fallback.get_batch(repo_id, file_paths)

    def set_batch(self, repo_id: str, entries: list[FileHashEntry]) -> None:
        """여러 파일 해시 일괄 저장."""
        self._memory_fallback.set_batch(repo_id, entries)

    # Async API for proper Redis operations
    async def get_async(self, repo_id: str, file_path: str) -> FileHashEntry | None:
        """파일 해시 조회 (async)."""
        try:
            client = await self._redis._get_client()
            key = self._make_key(repo_id)
            data = await client.hget(key, file_path)
            if data:
                entry = self._deserialize_entry(data)
                # 메모리 캐시에도 저장
                self._memory_fallback.set(repo_id, entry)
                return entry
            return None
        except Exception as e:
            logger.warning(f"Redis get_async failed: {e}")
            return self._memory_fallback.get(repo_id, file_path)

    async def set_async(self, repo_id: str, entry: FileHashEntry) -> None:
        """파일 해시 저장 (async)."""
        # 메모리 캐시에 먼저 저장
        self._memory_fallback.set(repo_id, entry)

        try:
            client = await self._redis._get_client()
            key = self._make_key(repo_id)
            await client.hset(key, entry.file_path, self._serialize_entry(entry))
            if self._expire_seconds:
                await client.expire(key, self._expire_seconds)
        except Exception as e:
            logger.warning(f"Redis set_async failed: {e}")

    async def delete_async(self, repo_id: str, file_path: str) -> None:
        """파일 해시 삭제 (async)."""
        self._memory_fallback.delete(repo_id, file_path)

        try:
            client = await self._redis._get_client()
            key = self._make_key(repo_id)
            await client.hdel(key, file_path)
        except Exception as e:
            logger.warning(f"Redis delete_async failed: {e}")

    async def get_batch_async(self, repo_id: str, file_paths: list[str]) -> dict[str, FileHashEntry]:
        """여러 파일 해시 일괄 조회 (async)."""
        if not file_paths:
            return {}

        try:
            client = await self._redis._get_client()
            key = self._make_key(repo_id)

            # HMGET으로 일괄 조회
            values = await client.hmget(key, *file_paths)

            result = {}
            for file_path, data in zip(file_paths, values, strict=False):
                if data:
                    entry = self._deserialize_entry(data)
                    result[file_path] = entry
                    # 메모리 캐시에도 저장
                    self._memory_fallback.set(repo_id, entry)
            return result
        except Exception as e:
            logger.warning(f"Redis get_batch_async failed: {e}")
            return self._memory_fallback.get_batch(repo_id, file_paths)

    async def set_batch_async(self, repo_id: str, entries: list[FileHashEntry]) -> None:
        """여러 파일 해시 일괄 저장 (async)."""
        if not entries:
            return

        # 메모리 캐시에 먼저 저장
        self._memory_fallback.set_batch(repo_id, entries)

        try:
            client = await self._redis._get_client()
            key = self._make_key(repo_id)

            # HSET으로 일괄 저장 (mapping 사용)
            mapping = {entry.file_path: self._serialize_entry(entry) for entry in entries}
            await client.hset(key, mapping=mapping)

            if self._expire_seconds:
                await client.expire(key, self._expire_seconds)
        except Exception as e:
            logger.warning(f"Redis set_batch_async failed: {e}")

    async def sync_to_redis(self, repo_id: str) -> int:
        """메모리 캐시를 Redis에 동기화."""
        try:
            entries = list(self._memory_fallback._store.get(repo_id, {}).values())
            if entries:
                await self.set_batch_async(repo_id, entries)
            return len(entries)
        except Exception as e:
            logger.warning(f"Redis sync_to_redis failed: {e}")
            return 0

    async def load_from_redis(self, repo_id: str) -> int:
        """Redis에서 메모리 캐시로 로드."""
        try:
            client = await self._redis._get_client()
            key = self._make_key(repo_id)

            # HGETALL로 전체 조회
            all_data = await client.hgetall(key)

            count = 0
            for _, data in all_data.items():
                entry = self._deserialize_entry(data)
                self._memory_fallback.set(repo_id, entry)
                count += 1

            logger.info(f"Loaded {count} hash entries from Redis for {repo_id}")
            return count
        except Exception as e:
            logger.warning(f"Redis load_from_redis failed: {e}")
            return 0


class ContentHashChecker:
    """
    Content Hash Checker.

    파일 내용의 해시를 비교하여 실제로 변경된 파일만 필터링합니다.

    사용 예:
        checker = ContentHashChecker(repo_path, repo_id)
        filtered = checker.filter_changes(change_set)
        # filtered에는 실제 내용이 변경된 파일만 포함
    """

    def __init__(
        self,
        repo_path: Path,
        repo_id: str,
        hash_store: HashStore | None = None,
    ):
        """
        Args:
            repo_path: 레포지토리 경로
            repo_id: 레포지토리 ID
            hash_store: 해시 저장소 (None이면 InMemoryHashStore 사용)
        """
        self.repo_path = Path(repo_path).resolve()
        self.repo_id = repo_id
        self.hash_store = hash_store or InMemoryHashStore()

        # 통계
        self._stats = {
            "total_checked": 0,
            "actually_changed": 0,
            "false_positives": 0,  # 가짜 변경 (해시 동일)
        }

    def filter_changes(self, change_set: ChangeSet) -> ChangeSet:
        """
        실제 변경된 파일만 필터링.

        Args:
            change_set: 원본 ChangeSet

        Returns:
            실제 변경된 파일만 포함된 ChangeSet
        """
        # added: 새 파일은 항상 포함 (해시 저장)
        real_added = self._filter_added(change_set.added)

        # modified: 해시 비교 후 실제 변경만 포함
        real_modified = self._filter_modified(change_set.modified)

        # deleted: 삭제된 파일은 항상 포함 (해시 삭제)
        real_deleted = self._handle_deleted(change_set.deleted)

        filtered = ChangeSet(
            added=real_added,
            modified=real_modified,
            deleted=real_deleted,
        )

        # 통계 업데이트
        original_count = change_set.total_count
        filtered_count = filtered.total_count
        false_positives = original_count - filtered_count

        self._stats["total_checked"] += original_count
        self._stats["actually_changed"] += filtered_count
        self._stats["false_positives"] += false_positives

        if false_positives > 0:
            logger.info(
                "content_hash_filtered",
                original=original_count,
                filtered=filtered_count,
                false_positives=false_positives,
            )

        return filtered

    def _filter_added(self, added_files: set[str]) -> set[str]:
        """새 파일 처리 - 해시 저장."""
        real_added: set[str] = set()
        entries_to_save: list[FileHashEntry] = []

        for file_path in added_files:
            full_path = self.repo_path / file_path

            if not full_path.exists():
                continue

            try:
                entry = self._compute_entry(file_path, full_path)
                entries_to_save.append(entry)
                real_added.add(file_path)
            except Exception as e:
                logger.warning("hash_compute_failed", file_path=file_path, error=str(e))
                # 해시 계산 실패 시에도 포함
                real_added.add(file_path)

        # 일괄 저장
        if entries_to_save:
            self.hash_store.set_batch(self.repo_id, entries_to_save)

        return real_added

    def _filter_modified(self, modified_files: set[str]) -> set[str]:
        """수정된 파일 필터링 - 해시 비교."""
        real_modified: set[str] = set()
        entries_to_update: list[FileHashEntry] = []

        # 기존 해시 일괄 조회
        old_hashes = self.hash_store.get_batch(self.repo_id, list(modified_files))

        for file_path in modified_files:
            full_path = self.repo_path / file_path

            if not full_path.exists():
                continue

            try:
                new_entry = self._compute_entry(file_path, full_path)
                old_entry = old_hashes.get(file_path)

                # 해시 비교
                if old_entry is None or old_entry.content_hash != new_entry.content_hash:
                    # 실제 변경됨
                    real_modified.add(file_path)
                    entries_to_update.append(new_entry)
                else:
                    # 가짜 변경 (해시 동일)
                    logger.debug(
                        "false_positive_detected",
                        file_path=file_path,
                        hash=new_entry.content_hash,
                    )

            except Exception as e:
                logger.warning("hash_compare_failed", file_path=file_path, error=str(e))
                # 비교 실패 시에도 포함 (안전한 쪽으로)
                real_modified.add(file_path)

        # 일괄 업데이트
        if entries_to_update:
            self.hash_store.set_batch(self.repo_id, entries_to_update)

        return real_modified

    def _handle_deleted(self, deleted_files: set[str]) -> set[str]:
        """삭제된 파일 처리 - 해시 삭제."""
        for file_path in deleted_files:
            self.hash_store.delete(self.repo_id, file_path)

        return deleted_files

    def _compute_entry(self, file_path: str, full_path: Path) -> FileHashEntry:
        """파일 해시 엔트리 계산."""
        stat = full_path.stat()
        content = full_path.read_bytes()

        return FileHashEntry(
            file_path=file_path,
            content_hash=compute_hash(content),
            size=stat.st_size,
            mtime=stat.st_mtime,
        )

    def get_stats(self) -> dict:
        """통계 반환."""
        return dict(self._stats)

    def reset_stats(self):
        """통계 초기화."""
        self._stats = {
            "total_checked": 0,
            "actually_changed": 0,
            "false_positives": 0,
        }
