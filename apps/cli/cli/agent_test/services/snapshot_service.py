"""Snapshot 생성 서비스 (Production-Ready)."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from codegraph_engine.analysis_indexing.domain.aggregates.indexing_session import (
    IndexingSession,
    SessionStatus,
)
from codegraph_engine.analysis_indexing.domain.value_objects.snapshot_id import SnapshotId


class SnapshotService:
    """Snapshot 생성 및 관리."""

    @staticmethod
    def get_git_sha(repo_path: Path) -> str:
        """Git commit SHA 가져오기."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()[:8]
        except subprocess.CalledProcessError:
            return "no-git"

    @staticmethod
    async def create_snapshot(repo_path: Path, name: str | None = None) -> SnapshotId:
        """
        스냅샷 생성 (실제 저장).

        Args:
            repo_path: 저장소 경로
            name: 스냅샷 이름 (선택)

        Returns:
            SnapshotId

        Raises:
            ValueError: 저장소 경로가 유효하지 않을 때
            NotImplementedError: Container 미설정 시
        """
        if not repo_path.exists():
            raise ValueError(f"Repository does not exist: {repo_path}")

        # Git SHA 가져오기
        SnapshotService.get_git_sha(repo_path)

        # SnapshotId 생성
        snapshot_id = SnapshotId.generate()

        # 실제 저장소에 저장 (Production)
        try:
            from codegraph_shared.container import container

            session_repo = container.session_repository
            if session_repo is None:
                raise NotImplementedError(
                    "Session repository not configured. Initialize container.session_repository first."
                )

            session = IndexingSession(
                session_id=snapshot_id.value,
                repo_id=str(repo_path.absolute()),
                snapshot_id=snapshot_id,
                mode="full",
                status=SessionStatus.PENDING,
                started_at=datetime.now(UTC),
            )

            await session_repo.save(session)

            # 저장 검증 (Critical!)
            saved = await session_repo.find_by_id(snapshot_id.value)
            if saved is None:
                raise RuntimeError(
                    f"Failed to save snapshot: {snapshot_id.value}\nRepository save succeeded but verification failed"
                )

            if saved.repo_id != str(repo_path.absolute()):
                raise RuntimeError(
                    f"Data corruption detected:\nExpected: {repo_path.absolute()}\nSaved: {saved.repo_id}"
                )

        except AttributeError as e:
            raise NotImplementedError(
                f"Container integration incomplete: {e}\nRequired: container.session_repository"
            ) from e

        return snapshot_id

    @staticmethod
    async def list_snapshots(repo_path: Path) -> list[dict]:
        """
        스냅샷 목록 조회 (실제 데이터).

        Args:
            repo_path: 저장소 경로

        Returns:
            스냅샷 목록

        Raises:
            NotImplementedError: Container 미설정 시
        """
        try:
            from codegraph_shared.container import container

            session_repo = container.session_repository
            if session_repo is None:
                raise NotImplementedError("Session repository not configured")

            sessions = await session_repo.find_by_repo(str(repo_path.absolute()))

            return [
                {
                    "id": session.session_id,
                    "created_at": session.started_at or datetime.now(UTC),
                    "commit_sha": SnapshotService.get_git_sha(repo_path),
                    "status": session.status.value,
                }
                for session in sessions
            ]

        except AttributeError as e:
            raise NotImplementedError(
                f"Container integration incomplete: {e}\nRequired: container.session_repository"
            ) from e

    @staticmethod
    async def get_snapshot_info(snapshot_id: str) -> dict:
        """
        스냅샷 정보 조회 (실제 데이터).

        Args:
            snapshot_id: 스냅샷 ID

        Returns:
            스냅샷 정보

        Raises:
            ValueError: 스냅샷을 찾을 수 없을 때
            NotImplementedError: Container 미설정 시
        """
        try:
            from codegraph_shared.container import container

            session_repo = container.session_repository
            if session_repo is None:
                raise NotImplementedError("Session repository not configured")

            session = await session_repo.find_by_id(snapshot_id)

            if session is None:
                raise ValueError(f"Snapshot not found: {snapshot_id}")

            return {
                "id": session.session_id,
                "created_at": session.started_at or datetime.now(UTC),
                "completed_at": session.completed_at,
                "status": session.status.value,
                "indexed": session.status == SessionStatus.COMPLETED,
                "index_stats": {
                    "files": len(session.indexed_files),
                    "symbols": sum(f.ir_nodes_count for f in session.indexed_files.values()),
                },
            }

        except AttributeError as e:
            raise NotImplementedError(
                f"Container integration incomplete: {e}\nRequired: container.session_repository"
            ) from e
