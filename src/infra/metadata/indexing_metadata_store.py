"""인덱싱 메타데이터 저장소 구현."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from src.contexts.analysis_indexing.infrastructure.models import IndexingMode
from src.infra.metadata.schema_version import MetadataStore, VersionInfo
from src.infra.observability import get_logger

if TYPE_CHECKING:
    from src.infra.storage.postgres import PostgresStore

logger = get_logger(__name__)


class PostgresIndexingMetadataStore(MetadataStore):
    """PostgreSQL 기반 인덱싱 메타데이터 저장소.

    PostgresStore를 사용하여 비동기 DB 연결을 지원합니다.
    동기 메서드는 내부적으로 asyncio.run()을 사용합니다.

    Note: 이 클래스는 동기/비동기 하이브리드로 설계되었습니다.
    - async 메서드: _async suffix 사용
    - sync 메서드: asyncio.run() 사용 (비동기 컨텍스트 외에서만)
    """

    def __init__(self, db_pool: "PostgresStore"):
        """
        Args:
            db_pool: PostgresStore 인스턴스 (lazy pool 초기화 지원)
        """
        self._store = db_pool

    async def _get_pool(self):
        """Get pool with lazy initialization."""
        return await self._store._ensure_pool()

    async def _execute(self, query: str, *args) -> None:
        """Execute a query without returning results."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(query, *args)

    async def _fetchrow(self, query: str, *args) -> Any:
        """Execute a query and return a single row."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def _fetchval(self, query: str, *args) -> Any:
        """Execute a query and return a single value."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def get_version_info_async(self, repo_id: str) -> VersionInfo | None:
        """버전 정보 조회 (async)."""
        row = await self._fetchrow(
            """
            SELECT schema_version, index_version, last_migration_at, last_repair_at
            FROM indexing_metadata
            WHERE repo_id = $1
            """,
            repo_id,
        )
        if not row:
            return None
        return VersionInfo(
            schema_version=row["schema_version"],
            index_version=row["index_version"],
            last_migration_at=row["last_migration_at"],
            last_repair_at=row["last_repair_at"],
        )

    def get_version_info(self, repo_id: str) -> VersionInfo | None:
        """버전 정보 조회 (sync wrapper - 비권장)."""
        import asyncio

        try:
            asyncio.get_running_loop()
            # Already in async context - can't use run()
            logger.warning("get_version_info called in async context, use get_version_info_async instead")
            return None
        except RuntimeError:
            # No running loop - safe to use asyncio.run()
            return asyncio.run(self.get_version_info_async(repo_id))

    async def save_version_info_async(self, repo_id: str, version_info: VersionInfo) -> None:
        """버전 정보 저장 (async)."""
        await self._execute(
            """
            INSERT INTO indexing_metadata (
                repo_id, schema_version, index_version,
                last_migration_at, last_repair_at, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
            ON CONFLICT (repo_id) DO UPDATE SET
                schema_version = EXCLUDED.schema_version,
                index_version = EXCLUDED.index_version,
                last_migration_at = EXCLUDED.last_migration_at,
                last_repair_at = EXCLUDED.last_repair_at,
                updated_at = NOW()
            """,
            repo_id,
            version_info.schema_version,
            version_info.index_version,
            version_info.last_migration_at,
            version_info.last_repair_at,
        )
        logger.debug(f"Version info saved for {repo_id}")

    def save_version_info(self, repo_id: str, version_info: VersionInfo) -> None:
        """버전 정보 저장 (sync wrapper)."""
        import asyncio

        try:
            asyncio.get_running_loop()
            logger.warning("save_version_info called in async context, use save_version_info_async instead")
        except RuntimeError:
            asyncio.run(self.save_version_info_async(repo_id, version_info))

    async def update_repair_time_async(self, repo_id: str, timestamp: datetime) -> None:
        """Repair 시간 기록 (async)."""
        await self._execute(
            """
            UPDATE indexing_metadata
            SET last_repair_at = $2, updated_at = NOW()
            WHERE repo_id = $1
            """,
            repo_id,
            timestamp,
        )
        logger.debug(f"Repair time updated for {repo_id}")

    def update_repair_time(self, repo_id: str, timestamp: datetime) -> None:
        """Repair 시간 기록 (sync wrapper)."""
        import asyncio

        try:
            asyncio.get_running_loop()
            logger.warning("update_repair_time called in async context")
        except RuntimeError:
            asyncio.run(self.update_repair_time_async(repo_id, timestamp))

    async def get_last_indexed_time_async(self, repo_id: str) -> datetime | None:
        """마지막 인덱싱 시간 (async)."""
        return await self._fetchval(
            "SELECT last_indexed_at FROM indexing_metadata WHERE repo_id = $1",
            repo_id,
        )

    def get_last_indexed_time(self, repo_id: str) -> datetime | None:
        """마지막 인덱싱 시간 (sync wrapper)."""
        import asyncio

        try:
            asyncio.get_running_loop()
            return None
        except RuntimeError:
            return asyncio.run(self.get_last_indexed_time_async(repo_id))

    async def get_last_mode_time_async(self, repo_id: str, mode: IndexingMode) -> datetime | None:
        """특정 모드의 마지막 실행 시간 (async)."""
        return await self._fetchval(
            """
            SELECT executed_at FROM indexing_mode_history
            WHERE repo_id = $1 AND mode = $2 AND success = TRUE
            ORDER BY executed_at DESC
            LIMIT 1
            """,
            repo_id,
            mode.value,
        )

    def get_last_mode_time(self, repo_id: str, mode: IndexingMode) -> datetime | None:
        """특정 모드의 마지막 실행 시간 (sync wrapper)."""
        import asyncio

        try:
            asyncio.get_running_loop()
            return None
        except RuntimeError:
            return asyncio.run(self.get_last_mode_time_async(repo_id, mode))

    async def save_mode_execution_async(
        self,
        repo_id: str,
        mode: IndexingMode,
        timestamp: datetime,
        duration_seconds: float,
        files_processed: int,
        success: bool,
    ) -> None:
        """모드 실행 기록 (async)."""
        await self._execute(
            """
            INSERT INTO indexing_mode_history (repo_id, mode, executed_at, duration_seconds, files_processed, success)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            repo_id,
            mode.value,
            timestamp,
            duration_seconds,
            files_processed,
            success,
        )

        # Update last_indexed_at if success
        if success:
            await self._execute(
                """
                UPDATE indexing_metadata
                SET last_indexed_at = $2, updated_at = NOW()
                WHERE repo_id = $1
                """,
                repo_id,
                timestamp,
            )

        logger.debug(f"Mode execution recorded: {repo_id} / {mode.value}")

    def save_mode_execution(
        self,
        repo_id: str,
        mode: IndexingMode,
        timestamp: datetime,
        duration_seconds: float,
        files_processed: int,
        success: bool,
    ) -> None:
        """모드 실행 기록 (sync wrapper)."""
        import asyncio

        try:
            asyncio.get_running_loop()
            logger.warning("save_mode_execution called in async context")
        except RuntimeError:
            asyncio.run(
                self.save_mode_execution_async(repo_id, mode, timestamp, duration_seconds, files_processed, success)
            )

    async def get_last_commit_async(self, repo_id: str) -> str | None:
        """마지막 인덱싱된 커밋 해시 (async)."""
        return await self._fetchval(
            "SELECT last_commit FROM indexing_metadata WHERE repo_id = $1",
            repo_id,
        )

    def get_last_commit(self, repo_id: str) -> str | None:
        """마지막 인덱싱된 커밋 해시 (sync wrapper)."""
        import asyncio

        try:
            asyncio.get_running_loop()
            return None
        except RuntimeError:
            return asyncio.run(self.get_last_commit_async(repo_id))

    async def save_last_commit_async(self, repo_id: str, commit_hash: str) -> None:
        """마지막 인덱싱된 커밋 해시 저장 (async)."""
        await self._execute(
            """
            UPDATE indexing_metadata
            SET last_commit = $2, updated_at = NOW()
            WHERE repo_id = $1
            """,
            repo_id,
            commit_hash,
        )
        logger.debug(f"Last commit saved for {repo_id}: {commit_hash[:8]}")

    def save_last_commit(self, repo_id: str, commit_hash: str) -> None:
        """마지막 인덱싱된 커밋 해시 저장 (sync wrapper)."""
        import asyncio

        try:
            asyncio.get_running_loop()
            logger.warning("save_last_commit called in async context")
        except RuntimeError:
            asyncio.run(self.save_last_commit_async(repo_id, commit_hash))


class InMemoryIndexingMetadataStore(MetadataStore):
    """인메모리 인덱싱 메타데이터 저장소 (개발/테스트용).

    PostgresIndexingMetadataStore와 동일한 인터페이스를 제공하지만
    메모리에만 저장합니다. 서버 재시작 시 데이터가 사라집니다.
    """

    def __init__(self):
        self._metadata: dict[str, dict] = {}  # {repo_id: {version_info}}
        self._mode_history: list[dict] = []  # [{repo_id, mode, executed_at, ...}]
        self._last_commits: dict[str, str] = {}  # {repo_id: commit_hash}

    def get_version_info(self, repo_id: str) -> VersionInfo | None:
        """버전 정보 조회."""
        data = self._metadata.get(repo_id)
        if not data:
            return None
        return VersionInfo(
            schema_version=data.get("schema_version", "1.0.0"),
            index_version=data.get("index_version", "1.0.0"),
            last_migration_at=data.get("last_migration_at"),
            last_repair_at=data.get("last_repair_at"),
        )

    def save_version_info(self, repo_id: str, version_info: VersionInfo) -> None:
        """버전 정보 저장."""
        self._metadata[repo_id] = {
            "schema_version": version_info.schema_version,
            "index_version": version_info.index_version,
            "last_migration_at": version_info.last_migration_at,
            "last_repair_at": version_info.last_repair_at,
            "updated_at": datetime.now(),
        }
        logger.debug(f"Version info saved for {repo_id}")

    def update_repair_time(self, repo_id: str, timestamp: datetime) -> None:
        """Repair 시간 기록."""
        if repo_id not in self._metadata:
            self._metadata[repo_id] = {}
        self._metadata[repo_id]["last_repair_at"] = timestamp
        self._metadata[repo_id]["updated_at"] = datetime.now()
        logger.debug(f"Repair time updated for {repo_id}")

    def get_last_indexed_time(self, repo_id: str) -> datetime | None:
        """마지막 인덱싱 시간."""
        data = self._metadata.get(repo_id)
        if not data:
            return None
        return data.get("last_indexed_at")

    def get_last_mode_time(self, repo_id: str, mode: IndexingMode) -> datetime | None:
        """특정 모드의 마지막 실행 시간."""
        for entry in reversed(self._mode_history):
            if entry["repo_id"] == repo_id and entry["mode"] == mode.value and entry.get("success"):
                return entry["executed_at"]
        return None

    def save_mode_execution(
        self,
        repo_id: str,
        mode: IndexingMode,
        timestamp: datetime,
        duration_seconds: float,
        files_processed: int,
        success: bool,
    ) -> None:
        """모드 실행 기록."""
        self._mode_history.append(
            {
                "repo_id": repo_id,
                "mode": mode.value,
                "executed_at": timestamp,
                "duration_seconds": duration_seconds,
                "files_processed": files_processed,
                "success": success,
            }
        )

        # Update last_indexed_at
        if success:
            if repo_id not in self._metadata:
                self._metadata[repo_id] = {}
            self._metadata[repo_id]["last_indexed_at"] = timestamp

        logger.debug(f"Mode execution recorded: {repo_id} / {mode.value}")

    def get_last_commit(self, repo_id: str) -> str | None:
        """마지막 인덱싱된 커밋 해시."""
        return self._last_commits.get(repo_id)

    def save_last_commit(self, repo_id: str, commit_hash: str) -> None:
        """마지막 인덱싱된 커밋 해시 저장."""
        self._last_commits[repo_id] = commit_hash
        logger.debug(f"Last commit saved for {repo_id}: {commit_hash[:8]}")


class InMemoryFileHashStore:
    """인메모리 파일 해시 저장소 (개발/테스트용)."""

    def __init__(self):
        self._state: dict[str, dict[str, dict]] = {}  # {repo_id: {file_path: {mtime, hash}}}

    def get_repo_state(self, repo_id: str) -> dict[str, dict]:
        """레포지토리 파일 상태 조회."""
        return self._state.get(repo_id, {})

    def save_repo_state(self, repo_id: str, state: dict[str, dict]) -> None:
        """레포지토리 파일 상태 저장."""
        self._state[repo_id] = state
        logger.debug(f"File state saved for {repo_id}: {len(state)} files")

    def update_file(self, repo_id: str, file_path: str, mtime: float, file_hash: str):
        """단일 파일 상태 업데이트."""
        if repo_id not in self._state:
            self._state[repo_id] = {}
        self._state[repo_id][file_path] = {"mtime": mtime, "hash": file_hash}


class PostgresFileHashStore:
    """PostgreSQL 기반 파일 해시 저장소.

    file_hash_state 테이블을 사용하여 파일 변경 감지 상태를 영속화합니다.
    InMemoryFileHashStore와 동일한 인터페이스를 제공합니다.
    """

    def __init__(self, db_store: "PostgresStore"):
        """
        Args:
            db_store: PostgresStore 인스턴스
        """
        self._store = db_store

    async def _get_pool(self):
        """Get pool with lazy initialization."""
        return await self._store._ensure_pool()

    # ========== Async Methods ==========

    async def get_repo_state_async(self, repo_id: str) -> dict[str, dict]:
        """레포지토리 파일 상태 조회 (async)."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT file_path, mtime, content_hash
                FROM file_hash_state
                WHERE repo_id = $1
                """,
                repo_id,
            )
        return {row["file_path"]: {"mtime": row["mtime"], "hash": row["content_hash"]} for row in rows}

    async def save_repo_state_async(self, repo_id: str, state: dict[str, dict]) -> None:
        """레포지토리 파일 상태 저장 (async).

        기존 상태를 삭제하고 새 상태로 교체합니다.
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # 기존 상태 삭제
                await conn.execute("DELETE FROM file_hash_state WHERE repo_id = $1", repo_id)

                # 새 상태 삽입
                if state:
                    await conn.executemany(
                        """
                        INSERT INTO file_hash_state (repo_id, file_path, mtime, content_hash, last_checked_at)
                        VALUES ($1, $2, $3, $4, NOW())
                        """,
                        [(repo_id, path, data["mtime"], data["hash"]) for path, data in state.items()],
                    )

        logger.debug(f"File state saved for {repo_id}: {len(state)} files")

    async def update_file_async(self, repo_id: str, file_path: str, mtime: float, file_hash: str) -> None:
        """단일 파일 상태 업데이트 (async)."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO file_hash_state (repo_id, file_path, mtime, content_hash, last_checked_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (repo_id, file_path) DO UPDATE SET
                    mtime = EXCLUDED.mtime,
                    content_hash = EXCLUDED.content_hash,
                    last_checked_at = NOW()
                """,
                repo_id,
                file_path,
                mtime,
                file_hash,
            )

    async def delete_file_async(self, repo_id: str, file_path: str) -> None:
        """파일 상태 삭제 (async)."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM file_hash_state WHERE repo_id = $1 AND file_path = $2",
                repo_id,
                file_path,
            )

    async def delete_repo_async(self, repo_id: str) -> None:
        """레포지토리 전체 상태 삭제 (async)."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM file_hash_state WHERE repo_id = $1", repo_id)
        logger.debug(f"File state deleted for {repo_id}")

    # ========== Sync Methods (asyncio.run wrapper) ==========

    def get_repo_state(self, repo_id: str) -> dict[str, dict]:
        """레포지토리 파일 상태 조회 (sync wrapper)."""
        import asyncio

        try:
            asyncio.get_running_loop()
            logger.warning("get_repo_state called in async context, use get_repo_state_async")
            return {}
        except RuntimeError:
            return asyncio.run(self.get_repo_state_async(repo_id))

    def save_repo_state(self, repo_id: str, state: dict[str, dict]) -> None:
        """레포지토리 파일 상태 저장 (sync wrapper)."""
        import asyncio

        try:
            asyncio.get_running_loop()
            logger.warning("save_repo_state called in async context, use save_repo_state_async")
        except RuntimeError:
            asyncio.run(self.save_repo_state_async(repo_id, state))

    def update_file(self, repo_id: str, file_path: str, mtime: float, file_hash: str) -> None:
        """단일 파일 상태 업데이트 (sync wrapper)."""
        import asyncio

        try:
            asyncio.get_running_loop()
            logger.warning("update_file called in async context, use update_file_async")
        except RuntimeError:
            asyncio.run(self.update_file_async(repo_id, file_path, mtime, file_hash))
