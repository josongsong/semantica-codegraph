"""
Agent Automation Domain Ports

에이전트 자동화 도메인의 포트 인터페이스
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from .models import AgentResult, AgentSession


@dataclass
class IncrementalIndexingResult:
    """
    증분 인덱싱 결과.

    Note: Non-blocking 모드에서는 indexed_count=0 (Job만 제출)
    실제 인덱싱은 background worker가 처리.
    """

    status: Literal["not_triggered", "success", "partial_success", "failed"]
    indexed_count: int  # Job 즉시 제출 모드에서는 0
    total_files: int
    errors: list[dict]

    @property
    def success(self) -> bool:
        """완전 성공 여부 (Job 제출 성공)."""
        return self.status == "success"

    @property
    def partial_success(self) -> bool:
        """부분 성공 여부."""
        return self.status == "partial_success"


class IncrementalIndexingPort(Protocol):
    """증분 인덱싱 포트."""

    async def index_files(
        self,
        repo_id: str,
        snapshot_id: str,
        file_paths: list[str],
        reason: str | None = None,
        priority: int = 0,
        head_sha: str | None = None,
    ) -> IncrementalIndexingResult:
        """파일 목록 증분 인덱싱."""
        ...

    async def wait_until_idle(
        self,
        repo_id: str,
        snapshot_id: str,
        timeout: float = 5.0,
    ) -> bool:
        """인덱싱 완료 대기."""
        ...


class AgentOrchestratorPort(Protocol):
    """에이전트 오케스트레이터 포트"""

    async def run_session(
        self,
        repo_id: str,
        prompt: str,
        mode: str,
        step_callback: Callable[[str], None] | None = None,
    ) -> AgentResult:
        """에이전트 세션 실행"""
        ...


class SessionStorePort(Protocol):
    """세션 저장소 포트"""

    async def save_session(self, session: AgentSession) -> None:
        """세션 저장"""
        ...

    async def get_session(self, session_id: str) -> AgentSession | None:
        """세션 조회"""
        ...
