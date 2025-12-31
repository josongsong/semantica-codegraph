"""
Workspace Repository (RFC-SEM-022 SOTA)

Immutable Revision Snapshot 관리.

SOTA Features:
- PostgreSQL + SQLite 듀얼 모드 (RFC-018)
- 트랜잭션 보장
- Workspace 계층 구조 (parent/child 관계)
- A/B 실험 지원 (branching)
- Async/Sync 하이브리드

Architecture:
- Port/Adapter Pattern
- Repository Pattern (DDD)
- CQRS-ready (Read/Write 분리 가능)
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from codegraph_shared.common.observability import get_logger
from codegraph_shared.kernel.contracts import PatchSet, Workspace

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = get_logger(__name__)


class WorkspaceRepository(ABC):
    """Workspace 저장소 Port (RFC-SEM-022)."""

    @abstractmethod
    async def save(self, workspace: Workspace) -> None:
        """Workspace 저장."""
        raise NotImplementedError

    @abstractmethod
    async def get(self, workspace_id: str) -> Workspace | None:
        """Workspace 조회."""
        raise NotImplementedError

    @abstractmethod
    async def list(
        self,
        repo_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Workspace], int]:
        """Workspace 목록 조회."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, workspace_id: str) -> bool:
        """Workspace 삭제."""
        raise NotImplementedError

    @abstractmethod
    async def get_children(self, workspace_id: str) -> list[Workspace]:
        """자식 Workspace 조회."""
        raise NotImplementedError

    @abstractmethod
    async def get_by_revision(self, repo_id: str, revision: str) -> Workspace | None:
        """특정 revision의 Workspace 조회."""
        raise NotImplementedError

    # PatchSet 관련
    @abstractmethod
    async def save_patchset(self, patchset: PatchSet) -> None:
        """PatchSet 저장."""
        raise NotImplementedError

    @abstractmethod
    async def get_patchset(self, patchset_id: str) -> PatchSet | None:
        """PatchSet 조회."""
        raise NotImplementedError


class SQLiteWorkspaceRepository(WorkspaceRepository):
    """
    SQLite 기반 Workspace 저장소 (RFC-SEM-022 SOTA).

    RFC-018: SQLite First Strategy
    - 로컬 개발 환경에서 외부 의존성 없이 동작
    - 파일 기반 영속성
    - WAL 모드로 동시성 지원
    """

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_dir = Path.home() / ".semantica"
            db_dir.mkdir(exist_ok=True)
            db_path = str(db_dir / "workspaces.db")

        self.db_path = db_path
        self._init_db()
        logger.debug(f"SQLite workspace repository initialized: {db_path}")

    def _init_db(self) -> None:
        """테이블 생성."""
        with sqlite3.connect(self.db_path) as conn:
            # WAL 모드 활성화
            conn.execute("PRAGMA journal_mode=WAL")

            # Workspaces 테이블
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workspaces (
                    workspace_id TEXT PRIMARY KEY,
                    repo_id TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    parent_workspace_id TEXT,
                    patchset_id TEXT,
                    metadata TEXT,
                    FOREIGN KEY (parent_workspace_id) REFERENCES workspaces(workspace_id)
                )
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ws_repo
                ON workspaces(repo_id)
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ws_parent
                ON workspaces(parent_workspace_id)
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ws_revision
                ON workspaces(repo_id, revision)
            """
            )

            # PatchSets 테이블
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS patchsets (
                    patchset_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    files TEXT,
                    patches TEXT,
                    verified INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    compile_verified INTEGER DEFAULT 0,
                    finding_resolved INTEGER DEFAULT 0,
                    no_regression INTEGER DEFAULT 0,
                    FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
                )
            """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ps_workspace
                ON patchsets(workspace_id)
            """
            )

    async def save(self, workspace: Workspace) -> None:
        """Workspace 저장."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO workspaces
                (workspace_id, repo_id, revision, created_at,
                 parent_workspace_id, patchset_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workspace.workspace_id,
                    workspace.repo_id,
                    workspace.revision,
                    workspace.created_at.isoformat(),
                    workspace.parent_workspace_id,
                    workspace.patchset_id,
                    json.dumps(workspace.metadata),
                ),
            )
        logger.debug(f"Workspace saved: {workspace.workspace_id}")

    async def get(self, workspace_id: str) -> Workspace | None:
        """Workspace 조회."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM workspaces WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()

            if not row:
                return None

            return self._row_to_workspace(row)

    async def list(
        self,
        repo_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Workspace], int]:
        """Workspace 목록 조회."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Count
            if repo_id:
                count_row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM workspaces WHERE repo_id = ?",
                    (repo_id,),
                ).fetchone()
                rows = conn.execute(
                    """
                    SELECT * FROM workspaces
                    WHERE repo_id = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (repo_id, limit, offset),
                ).fetchall()
            else:
                count_row = conn.execute("SELECT COUNT(*) as cnt FROM workspaces").fetchone()
                rows = conn.execute(
                    """
                    SELECT * FROM workspaces
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()

            total = count_row["cnt"]
            workspaces = [self._row_to_workspace(row) for row in rows]

            return workspaces, total

    async def delete(self, workspace_id: str) -> bool:
        """Workspace 삭제."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM workspaces WHERE workspace_id = ?",
                (workspace_id,),
            )
            deleted = cursor.rowcount > 0

        if deleted:
            logger.info(f"Workspace deleted: {workspace_id}")

        return deleted

    async def get_children(self, workspace_id: str) -> list[Workspace]:
        """자식 Workspace 조회."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM workspaces
                WHERE parent_workspace_id = ?
                ORDER BY created_at DESC
                """,
                (workspace_id,),
            ).fetchall()

            return [self._row_to_workspace(row) for row in rows]

    async def get_by_revision(self, repo_id: str, revision: str) -> Workspace | None:
        """특정 revision의 Workspace 조회."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM workspaces
                WHERE repo_id = ? AND revision = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (repo_id, revision),
            ).fetchone()

            if not row:
                return None

            return self._row_to_workspace(row)

    async def save_patchset(self, patchset: PatchSet) -> None:
        """PatchSet 저장."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO patchsets
                (patchset_id, workspace_id, files, patches, verified,
                 created_at, compile_verified, finding_resolved, no_regression)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    patchset.patchset_id,
                    patchset.workspace_id,
                    json.dumps(patchset.files),
                    json.dumps(patchset.patches),
                    1 if patchset.verified else 0,
                    patchset.created_at.isoformat(),
                    1 if patchset.compile_verified else 0,
                    1 if patchset.finding_resolved else 0,
                    1 if patchset.no_regression else 0,
                ),
            )
        logger.debug(f"PatchSet saved: {patchset.patchset_id}")

    async def get_patchset(self, patchset_id: str) -> PatchSet | None:
        """PatchSet 조회."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM patchsets WHERE patchset_id = ?",
                (patchset_id,),
            ).fetchone()

            if not row:
                return None

            return PatchSet(
                patchset_id=row["patchset_id"],
                workspace_id=row["workspace_id"],
                files=json.loads(row["files"]) if row["files"] else [],
                patches=json.loads(row["patches"]) if row["patches"] else {},
                verified=bool(row["verified"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                compile_verified=bool(row["compile_verified"]),
                finding_resolved=bool(row["finding_resolved"]),
                no_regression=bool(row["no_regression"]),
            )

    def _row_to_workspace(self, row: sqlite3.Row) -> Workspace:
        """Row → Workspace 변환."""
        return Workspace(
            workspace_id=row["workspace_id"],
            repo_id=row["repo_id"],
            revision=row["revision"],
            created_at=datetime.fromisoformat(row["created_at"]),
            parent_workspace_id=row["parent_workspace_id"],
            patchset_id=row["patchset_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )


class PostgresWorkspaceRepository(WorkspaceRepository):
    """
    PostgreSQL 기반 Workspace 저장소 (Production).

    SOTA Features:
    - 트랜잭션 보장 (ACID)
    - Connection Pooling (asyncpg)
    - Full-text Search 지원
    - 대규모 데이터 처리
    """

    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        logger.info("PostgreSQL workspace repository initialized")

    async def save(self, workspace: Workspace) -> None:
        """Workspace 저장."""
        from sqlalchemy import text

        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO workspaces
                    (workspace_id, repo_id, revision, created_at,
                     parent_workspace_id, patchset_id, metadata)
                    VALUES (:workspace_id, :repo_id, :revision, :created_at,
                            :parent_workspace_id, :patchset_id, :metadata)
                    ON CONFLICT (workspace_id) DO UPDATE SET
                        repo_id = EXCLUDED.repo_id,
                        revision = EXCLUDED.revision,
                        parent_workspace_id = EXCLUDED.parent_workspace_id,
                        patchset_id = EXCLUDED.patchset_id,
                        metadata = EXCLUDED.metadata
                """
                ),
                {
                    "workspace_id": workspace.workspace_id,
                    "repo_id": workspace.repo_id,
                    "revision": workspace.revision,
                    "created_at": workspace.created_at,
                    "parent_workspace_id": workspace.parent_workspace_id,
                    "patchset_id": workspace.patchset_id,
                    "metadata": json.dumps(workspace.metadata),
                },
            )

    async def get(self, workspace_id: str) -> Workspace | None:
        """Workspace 조회."""
        from sqlalchemy import text

        async with self.engine.connect() as conn:
            result = await conn.execute(
                text("SELECT * FROM workspaces WHERE workspace_id = :id"),
                {"id": workspace_id},
            )
            row = result.fetchone()

            if not row:
                return None

            return Workspace(
                workspace_id=row.workspace_id,
                repo_id=row.repo_id,
                revision=row.revision,
                created_at=row.created_at,
                parent_workspace_id=row.parent_workspace_id,
                patchset_id=row.patchset_id,
                metadata=json.loads(row.metadata) if row.metadata else {},
            )

    async def list(
        self,
        repo_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Workspace], int]:
        """Workspace 목록 조회."""
        from sqlalchemy import text

        async with self.engine.connect() as conn:
            if repo_id:
                count_result = await conn.execute(
                    text("SELECT COUNT(*) FROM workspaces WHERE repo_id = :repo_id"),
                    {"repo_id": repo_id},
                )
                result = await conn.execute(
                    text(
                        """
                        SELECT * FROM workspaces
                        WHERE repo_id = :repo_id
                        ORDER BY created_at DESC
                        LIMIT :limit OFFSET :offset
                    """
                    ),
                    {"repo_id": repo_id, "limit": limit, "offset": offset},
                )
            else:
                count_result = await conn.execute(text("SELECT COUNT(*) FROM workspaces"))
                result = await conn.execute(
                    text(
                        """
                        SELECT * FROM workspaces
                        ORDER BY created_at DESC
                        LIMIT :limit OFFSET :offset
                    """
                    ),
                    {"limit": limit, "offset": offset},
                )

            total = count_result.scalar() or 0
            rows = result.fetchall()

            workspaces = [
                Workspace(
                    workspace_id=row.workspace_id,
                    repo_id=row.repo_id,
                    revision=row.revision,
                    created_at=row.created_at,
                    parent_workspace_id=row.parent_workspace_id,
                    patchset_id=row.patchset_id,
                    metadata=json.loads(row.metadata) if row.metadata else {},
                )
                for row in rows
            ]

            return workspaces, total

    async def delete(self, workspace_id: str) -> bool:
        """Workspace 삭제."""
        from sqlalchemy import text

        async with self.engine.begin() as conn:
            result = await conn.execute(
                text("DELETE FROM workspaces WHERE workspace_id = :id"),
                {"id": workspace_id},
            )
            return result.rowcount > 0

    async def get_children(self, workspace_id: str) -> list[Workspace]:
        """자식 Workspace 조회."""
        from sqlalchemy import text

        async with self.engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT * FROM workspaces
                    WHERE parent_workspace_id = :id
                    ORDER BY created_at DESC
                """
                ),
                {"id": workspace_id},
            )
            rows = result.fetchall()

            return [
                Workspace(
                    workspace_id=row.workspace_id,
                    repo_id=row.repo_id,
                    revision=row.revision,
                    created_at=row.created_at,
                    parent_workspace_id=row.parent_workspace_id,
                    patchset_id=row.patchset_id,
                    metadata=json.loads(row.metadata) if row.metadata else {},
                )
                for row in rows
            ]

    async def get_by_revision(self, repo_id: str, revision: str) -> Workspace | None:
        """특정 revision의 Workspace 조회."""
        from sqlalchemy import text

        async with self.engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT * FROM workspaces
                    WHERE repo_id = :repo_id AND revision = :revision
                    ORDER BY created_at DESC
                    LIMIT 1
                """
                ),
                {"repo_id": repo_id, "revision": revision},
            )
            row = result.fetchone()

            if not row:
                return None

            return Workspace(
                workspace_id=row.workspace_id,
                repo_id=row.repo_id,
                revision=row.revision,
                created_at=row.created_at,
                parent_workspace_id=row.parent_workspace_id,
                patchset_id=row.patchset_id,
                metadata=json.loads(row.metadata) if row.metadata else {},
            )

    async def save_patchset(self, patchset: PatchSet) -> None:
        """PatchSet 저장."""
        from sqlalchemy import text

        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO patchsets
                    (patchset_id, workspace_id, files, patches, verified,
                     created_at, compile_verified, finding_resolved, no_regression)
                    VALUES (:patchset_id, :workspace_id, :files, :patches, :verified,
                            :created_at, :compile_verified, :finding_resolved, :no_regression)
                    ON CONFLICT (patchset_id) DO UPDATE SET
                        files = EXCLUDED.files,
                        patches = EXCLUDED.patches,
                        verified = EXCLUDED.verified,
                        compile_verified = EXCLUDED.compile_verified,
                        finding_resolved = EXCLUDED.finding_resolved,
                        no_regression = EXCLUDED.no_regression
                """
                ),
                {
                    "patchset_id": patchset.patchset_id,
                    "workspace_id": patchset.workspace_id,
                    "files": json.dumps(patchset.files),
                    "patches": json.dumps(patchset.patches),
                    "verified": patchset.verified,
                    "created_at": patchset.created_at,
                    "compile_verified": patchset.compile_verified,
                    "finding_resolved": patchset.finding_resolved,
                    "no_regression": patchset.no_regression,
                },
            )

    async def get_patchset(self, patchset_id: str) -> PatchSet | None:
        """PatchSet 조회."""
        from sqlalchemy import text

        async with self.engine.connect() as conn:
            result = await conn.execute(
                text("SELECT * FROM patchsets WHERE patchset_id = :id"),
                {"id": patchset_id},
            )
            row = result.fetchone()

            if not row:
                return None

            return PatchSet(
                patchset_id=row.patchset_id,
                workspace_id=row.workspace_id,
                files=json.loads(row.files) if row.files else [],
                patches=json.loads(row.patches) if row.patches else {},
                verified=row.verified,
                created_at=row.created_at,
                compile_verified=row.compile_verified,
                finding_resolved=row.finding_resolved,
                no_regression=row.no_regression,
            )


class InMemoryWorkspaceRepository(WorkspaceRepository):
    """
    In-Memory Workspace 저장소 (테스트용).

    RFC-SEM-022 완전 호환.
    """

    def __init__(self):
        self._workspaces: dict[str, Workspace] = {}
        self._patchsets: dict[str, PatchSet] = {}

    async def save(self, workspace: Workspace) -> None:
        self._workspaces[workspace.workspace_id] = workspace

    async def get(self, workspace_id: str) -> Workspace | None:
        return self._workspaces.get(workspace_id)

    async def list(
        self,
        repo_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Workspace], int]:
        workspaces = list(self._workspaces.values())
        if repo_id:
            workspaces = [w for w in workspaces if w.repo_id == repo_id]
        workspaces.sort(key=lambda w: w.created_at, reverse=True)
        total = len(workspaces)
        return workspaces[offset : offset + limit], total

    async def delete(self, workspace_id: str) -> bool:
        if workspace_id in self._workspaces:
            del self._workspaces[workspace_id]
            return True
        return False

    async def get_children(self, workspace_id: str) -> list[Workspace]:
        return [w for w in self._workspaces.values() if w.parent_workspace_id == workspace_id]

    async def get_by_revision(self, repo_id: str, revision: str) -> Workspace | None:
        for w in self._workspaces.values():
            if w.repo_id == repo_id and w.revision == revision:
                return w
        return None

    async def save_patchset(self, patchset: PatchSet) -> None:
        self._patchsets[patchset.patchset_id] = patchset

    async def get_patchset(self, patchset_id: str) -> PatchSet | None:
        return self._patchsets.get(patchset_id)


# ============================================================
# Factory Functions (RFC-SEM-022)
# ============================================================


_workspace_repository: WorkspaceRepository | None = None


def get_workspace_repository(
    mode: str = "auto",
    db_path: str | None = None,
    engine: AsyncEngine | None = None,
) -> WorkspaceRepository:
    """
    WorkspaceRepository 싱글톤 획득.

    Args:
        mode: "auto" | "sqlite" | "postgres" | "memory"
        db_path: SQLite 경로 (mode=sqlite)
        engine: SQLAlchemy AsyncEngine (mode=postgres)

    Returns:
        WorkspaceRepository
    """
    global _workspace_repository

    if _workspace_repository is not None:
        return _workspace_repository

    if mode == "memory":
        _workspace_repository = InMemoryWorkspaceRepository()
    elif mode == "postgres" and engine is not None:
        _workspace_repository = PostgresWorkspaceRepository(engine)
    else:
        _workspace_repository = SQLiteWorkspaceRepository(db_path)

    return _workspace_repository


def reset_workspace_repository() -> None:
    """Repository 싱글톤 리셋 (테스트용)."""
    global _workspace_repository
    _workspace_repository = None


async def create_workspace(
    repo_id: str,
    revision: str,
    parent_workspace_id: str | None = None,
    patchset_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    repository: WorkspaceRepository | None = None,
) -> Workspace:
    """
    새 Workspace 생성 헬퍼.

    Usage:
        workspace = await create_workspace(
            repo_id="my-repo",
            revision="abc123",
        )
    """
    workspace_id = f"ws_{uuid4().hex[:12]}"

    workspace = Workspace(
        workspace_id=workspace_id,
        repo_id=repo_id,
        revision=revision,
        parent_workspace_id=parent_workspace_id,
        patchset_id=patchset_id,
        metadata=metadata or {},
    )

    repo = repository if repository else get_workspace_repository()
    await repo.save(workspace)

    return workspace


async def branch_workspace(
    base_workspace_id: str,
    patchset_id: str,
    metadata: dict[str, Any] | None = None,
    repository: WorkspaceRepository | None = None,
) -> Workspace:
    """
    Workspace 분기 (A/B 실험) 헬퍼.

    Usage:
        trial_ws = await branch_workspace(
            base_workspace_id="ws_base",
            patchset_id="ps_001",
        )
    """
    repo = repository if repository else get_workspace_repository()
    base = await repo.get(base_workspace_id)

    if not base:
        raise ValueError(f"Base workspace not found: {base_workspace_id}")

    workspace_id = f"ws_{uuid4().hex[:12]}"

    workspace = Workspace(
        workspace_id=workspace_id,
        repo_id=base.repo_id,
        revision=base.revision,
        parent_workspace_id=base_workspace_id,
        patchset_id=patchset_id,
        metadata={**base.metadata, **(metadata or {})},
    )

    await repo.save(workspace)

    return workspace
