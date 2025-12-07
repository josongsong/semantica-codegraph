"""
SemanticaTask Daemon 어댑터.

SemanticaTask Engine과 통합하여 Job Queue 기능 제공.
로컬: SQLite, 프로덕션: PostgreSQL (Daemon 내부 설정)
"""

import asyncio
import os
import signal
import subprocess
from typing import Any

from semantica_task_engine import (
    CancelResponse,
    EnqueueRequest,
    EnqueueResponse,
    SemanticaTaskClient,
    TailLogsResponse,
)

from src.infra.jobs.handler import JobHandler, JobResult
from src.infra.jobs.models import Job, JobState
from src.infra.observability.logging import get_logger

logger = get_logger(__name__)


class SemanticaAdapter:
    """
    SemanticaTask Daemon 어댑터.

    Usage:
        # 자동 모드 (Daemon 자동 시작/종료)
        async with SemanticaAdapter.create(auto_start=True) as adapter:
            job = await adapter.enqueue(...)

        # 수동 모드 (Daemon 직접 관리)
        adapter = SemanticaAdapter(
            url="http://localhost:9527",
            handlers={"INDEX_FILE": IndexingJobHandler(...)},
        )
        job = await adapter.enqueue(...)
    """

    def __init__(
        self,
        url: str | None = None,
        handlers: dict[str, JobHandler] | None = None,
        auto_start_daemon: bool = False,
        daemon_path: str | None = None,
    ):
        """
        Args:
            url: Daemon RPC URL (기본: http://localhost:9527)
            handlers: job_type → Handler 매핑
            auto_start_daemon: Daemon 자동 시작 여부
            daemon_path: Daemon 바이너리 경로 (기본: cargo run)
        """
        self.url = url or os.getenv("SEMANTICA_RPC_URL", "http://localhost:9527")
        self.handlers = handlers or {}
        self.auto_start_daemon = auto_start_daemon
        self.daemon_path = daemon_path or os.getenv("SEMANTICA_DAEMON_PATH")
        self._daemon_process: subprocess.Popen | None = None

    @classmethod
    async def create(
        cls,
        url: str | None = None,
        handlers: dict[str, JobHandler] | None = None,
        auto_start: bool = True,
    ) -> "SemanticaAdapter":
        """
        Daemon 자동 시작과 함께 Adapter 생성.

        Usage:
            async with SemanticaAdapter.create(auto_start=True) as adapter:
                job = await adapter.enqueue(...)
        """
        adapter = cls(
            url=url,
            handlers=handlers,
            auto_start_daemon=auto_start,
        )

        if auto_start:
            await adapter._start_daemon()

        return adapter

    async def __aenter__(self):
        """Async context manager enter."""
        if self.auto_start_daemon and not self._daemon_process:
            await self._start_daemon()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._daemon_process:
            await self._stop_daemon()

    async def _start_daemon(self) -> None:
        """
        Daemon 자동 시작.

        1. Daemon 실행 중인지 체크 (포트 9527)
        2. 없으면 cargo run 또는 바이너리 실행
        3. 5초 대기 (시작 완료)
        """
        # 이미 실행 중인지 체크
        if await self._is_daemon_running():
            logger.info("daemon_already_running", url=self.url)
            return

        logger.info("starting_daemon", url=self.url)

        try:
            # Daemon 시작
            if self.daemon_path:
                # 바이너리 직접 실행
                cmd = [self.daemon_path]
            else:
                # cargo run (개발 모드)
                cmd = ["cargo", "run", "--bin", "semantica-task-engine"]

            # 환경변수 설정
            env = os.environ.copy()
            port = self.url.split(":")[-1]
            env["SEMANTICA_RPC_PORT"] = port

            # Daemon 프로세스 시작 (백그라운드)
            self._daemon_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                start_new_session=True,  # 독립 프로세스 그룹
            )

            logger.info(
                "daemon_process_started",
                pid=self._daemon_process.pid,
                cmd=" ".join(cmd),
            )

            # Daemon 시작 대기 (최대 10초)
            for i in range(20):
                await asyncio.sleep(0.5)
                if await self._is_daemon_running():
                    logger.info("daemon_ready", wait_seconds=i * 0.5)
                    return

            # 10초 내에 시작 안되면 에러
            raise RuntimeError("Daemon failed to start within 10 seconds")

        except Exception as e:
            logger.error("daemon_start_failed", error=str(e), exc_info=True)
            if self._daemon_process:
                self._daemon_process.kill()
                self._daemon_process = None
            raise

    async def _stop_daemon(self) -> None:
        """Daemon 종료."""
        if not self._daemon_process:
            return

        logger.info("stopping_daemon", pid=self._daemon_process.pid)

        try:
            # SIGTERM 전송 (graceful shutdown)
            os.killpg(os.getpgid(self._daemon_process.pid), signal.SIGTERM)

            # 5초 대기
            for _ in range(10):
                if self._daemon_process.poll() is not None:
                    logger.info("daemon_stopped_gracefully")
                    return
                await asyncio.sleep(0.5)

            # 강제 종료
            logger.warning("daemon_force_kill")
            os.killpg(os.getpgid(self._daemon_process.pid), signal.SIGKILL)

        except Exception as e:
            logger.error("daemon_stop_failed", error=str(e))
        finally:
            self._daemon_process = None

    async def _is_daemon_running(self) -> bool:
        """Daemon 실행 중인지 체크 (포트 확인)."""
        try:
            # HTTP 요청으로 확인 (간단한 stats 호출)
            async with SemanticaTaskClient(self.url):
                # 연결만 확인
                return True
        except Exception:
            return False

    async def enqueue(
        self,
        job_type: str,
        queue: str,
        subject_key: str,
        payload: dict[str, Any],
        priority: int = 0,
    ) -> Job:
        """
        Job 등록.

        Args:
            job_type: Job 타입 ("INDEX_FILE", "EMBED_CHUNK")
            queue: 큐 이름 ("code_intel", "default")
            subject_key: 중복 방지 키 ("repo::file")
            payload: Job 데이터 (JSON 직렬화 가능)
            priority: 우선순위 (기본값: 0)

        Returns:
            생성된 Job
        """
        async with SemanticaTaskClient(self.url) as client:
            response: EnqueueResponse = await client.enqueue(
                EnqueueRequest(
                    job_type=job_type,
                    queue=queue,
                    subject_key=subject_key,
                    payload=payload,
                    priority=priority,
                )
            )

        logger.info(
            "job_enqueued_via_semantica",
            job_id=response.job_id,
            job_type=job_type,
            queue=queue,
        )

        # SemanticaTask 응답 → Job 모델 변환
        return Job(
            job_id=response.job_id,
            job_type=job_type,
            queue=response.queue,
            subject_key=subject_key,
            payload=payload,
            state=JobState(response.state),
            priority=priority,
        )

    async def cancel_job(self, job_id: str) -> bool:
        """
        Job 취소.

        Args:
            job_id: Job UUID

        Returns:
            취소 성공 여부
        """
        async with SemanticaTaskClient(self.url) as client:
            response: CancelResponse = await client.cancel(job_id)

        logger.info("job_cancelled", job_id=job_id, cancelled=response.cancelled)
        return response.cancelled

    async def tail_logs(self, job_id: str, lines: int = 100) -> list[str]:
        """
        Job 로그 조회.

        Args:
            job_id: Job UUID
            lines: 조회할 라인 수

        Returns:
            로그 라인 배열
        """
        async with SemanticaTaskClient(self.url) as client:
            response: TailLogsResponse = await client.tail_logs(job_id, lines=lines)

        return response.lines

    async def execute_handler(self, job_id: str, job_type: str, payload: dict[str, Any]) -> JobResult:
        """
        Handler 실행 (Worker용).

        SemanticaTask Daemon이 HTTP callback으로 호출:
        POST /worker/execute
        {
            "job_id": "...",
            "job_type": "INDEX_FILE",
            "payload": {...}
        }

        Args:
            job_id: Job UUID
            job_type: Job 타입
            payload: Job 데이터

        Returns:
            실행 결과
        """
        handler = self.handlers.get(job_type)
        if not handler:
            logger.error("handler_not_found", job_type=job_type, available=list(self.handlers.keys()))
            return JobResult.fail(error=f"No handler for job_type: {job_type}")

        try:
            result = await handler.execute(payload)
            logger.info(
                "handler_executed",
                job_id=job_id,
                job_type=job_type,
                success=result.success,
            )
            return result

        except Exception as e:
            logger.error(
                "handler_execution_failed",
                job_id=job_id,
                job_type=job_type,
                error=str(e),
                exc_info=True,
            )
            return JobResult.fail(error=str(e))
