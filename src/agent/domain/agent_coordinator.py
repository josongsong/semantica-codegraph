"""
Agent Coordinator (SOTA급)

여러 Agent를 조율하고 관리합니다.

핵심 기능:
1. Agent 생성 및 관리
2. Task 분배
3. 상태 동기화
4. 충돌 감지 및 해결
"""

import logging
from datetime import datetime
from typing import Any

from src.agent.domain.conflict_resolver import ConflictResolver
from src.agent.domain.multi_agent_models import (
    AgentSession,
    AgentStateType,
    AgentType,
    Conflict,
)
from src.agent.domain.soft_lock_manager import SoftLockManager

logger = logging.getLogger(__name__)


class AgentCoordinator:
    """
    Agent Coordinator (SOTA급).

    여러 Agent의 동시 실행을 조율합니다.
    """

    def __init__(
        self,
        lock_manager: SoftLockManager | None = None,
        conflict_resolver: ConflictResolver | None = None,
        orchestrator_factory=None,
    ):
        """
        Args:
            lock_manager: Soft Lock Manager
            conflict_resolver: Conflict Resolver
            orchestrator_factory: Agent Orchestrator 팩토리
        """
        self.lock_manager = lock_manager or SoftLockManager()
        self.conflict_resolver = conflict_resolver or ConflictResolver()
        self.orchestrator_factory = orchestrator_factory

        # Agent 세션 저장 (메모리)
        self._sessions: dict[str, AgentSession] = {}

    async def spawn_agent(
        self,
        agent_id: str,
        agent_type: AgentType = AgentType.AI,
        task_id: str | None = None,
    ) -> AgentSession:
        """
        새 Agent 생성.

        Args:
            agent_id: Agent ID
            agent_type: Agent 타입
            task_id: Task ID

        Returns:
            AgentSession
        """
        logger.info(f"Spawning agent: {agent_id} (type={agent_type.value})")

        # 세션 생성
        session = AgentSession(
            session_id=f"session-{agent_id}-{datetime.now().timestamp()}",
            agent_id=agent_id,
            agent_type=agent_type,
            task_id=task_id,
            state=AgentStateType.IDLE,
        )

        # 저장
        self._sessions[agent_id] = session

        logger.debug(f"Agent spawned: {session.session_id}")

        return session

    async def distribute_tasks(
        self,
        tasks: list[Any],
        num_agents: int = 2,
    ) -> dict[str, AgentSession]:
        """
        Task를 여러 Agent에게 분배.

        Args:
            tasks: Task 리스트
            num_agents: Agent 수

        Returns:
            Agent ID → AgentSession
        """
        logger.info(f"Distributing {len(tasks)} tasks to {num_agents} agents")

        agents = {}

        # Agent 생성
        for i in range(num_agents):
            agent_id = f"agent-{i}"
            session = await self.spawn_agent(agent_id, AgentType.AI)
            agents[agent_id] = session

        # Task 분배 (Round-robin)
        for i, task in enumerate(tasks):
            agent_id = f"agent-{i % num_agents}"
            agent = agents[agent_id]

            # Task ID 저장
            agent.task_id = str(task)
            agent.update_state(AgentStateType.RUNNING)

            logger.debug(f"Task {task} → {agent_id}")

        logger.info(f"Tasks distributed to {num_agents} agents")

        return agents

    async def synchronize_state(self) -> None:
        """
        모든 Agent 상태 동기화.

        - Lock 확인
        - 상태 업데이트
        """
        logger.debug(f"Synchronizing {len(self._sessions)} agents")

        for agent_id, session in self._sessions.items():
            # Lock 확인
            locks = []
            for file_path in list(session.locked_files):
                lock_exists = await self.lock_manager.check_lock(file_path)

                if not lock_exists:
                    # Lock이 만료됨
                    session.remove_lock(file_path)
                else:
                    locks.append(file_path)

            logger.debug(f"Agent {agent_id}: {len(locks)} active locks")

    async def detect_conflicts(self) -> list[Conflict]:
        """
        모든 Agent 간 충돌 감지.

        Returns:
            Conflict 리스트
        """
        logger.info("Detecting conflicts...")

        conflicts = []

        # 모든 Lock 조회
        all_locks = await self.lock_manager.list_locks()

        # 파일별 Lock 그룹화
        file_locks: dict[str, list] = {}
        for lock in all_locks:
            if lock.file_path not in file_locks:
                file_locks[lock.file_path] = []
            file_locks[lock.file_path].append(lock)

        # 충돌 감지 (동일 파일에 2개 이상 Lock)
        for file_path, locks in file_locks.items():
            if len(locks) > 1:
                logger.warning(f"Conflict: {file_path} locked by {len(locks)} agents")

                # 첫 2개 Agent 충돌로 기록
                lock_a = locks[0]
                lock_b = locks[1]

                conflict = Conflict(
                    conflict_id=f"conflict-{datetime.now().timestamp()}",
                    file_path=file_path,
                    agent_a_id=lock_a.agent_id,
                    agent_b_id=lock_b.agent_id,
                )

                conflicts.append(conflict)

        logger.info(f"Detected {len(conflicts)} conflicts")

        return conflicts

    async def resolve_all_conflicts(
        self,
        conflicts: list[Conflict],
    ) -> dict[str, Any]:
        """
        모든 충돌 해결.

        Args:
            conflicts: Conflict 리스트

        Returns:
            해결 결과
        """
        logger.info(f"Resolving {len(conflicts)} conflicts...")

        results = {
            "total": len(conflicts),
            "auto_resolved": 0,
            "manual_needed": 0,
            "failed": 0,
        }

        for conflict in conflicts:
            try:
                # 3-way merge 시도
                merge_result = await self.conflict_resolver.resolve_3way_merge(conflict)

                if merge_result.success:
                    results["auto_resolved"] += 1
                    logger.info(f"Auto-resolved: {conflict.file_path}")
                else:
                    results["manual_needed"] += 1
                    logger.warning(f"Manual needed: {conflict.file_path}")

            except Exception as e:
                results["failed"] += 1
                logger.error(f"Failed to resolve {conflict.file_path}: {e}")

        logger.info(f"Conflicts resolved: {results}")

        return results

    async def get_agent_session(self, agent_id: str) -> AgentSession | None:
        """Agent 세션 조회"""
        return self._sessions.get(agent_id)

    async def list_agents(self) -> list[AgentSession]:
        """모든 Agent 조회"""
        return list(self._sessions.values())

    async def shutdown_agent(self, agent_id: str) -> bool:
        """
        Agent 종료.

        Args:
            agent_id: Agent ID

        Returns:
            성공 여부
        """
        logger.info(f"Shutting down agent: {agent_id}")

        session = self._sessions.get(agent_id)

        if not session:
            logger.warning(f"Agent not found: {agent_id}")
            return False

        # 모든 Lock 해제
        for file_path in list(session.locked_files):
            await self.lock_manager.release_lock(agent_id, file_path)

        # 상태 업데이트
        session.update_state(AgentStateType.COMPLETED)

        # 삭제
        del self._sessions[agent_id]

        logger.info(f"Agent shutdown: {agent_id}")

        return True

    async def get_statistics(self) -> dict[str, Any]:
        """
        통계 조회.

        Returns:
            통계 정보
        """
        active_agents = sum(1 for session in self._sessions.values() if session.is_active())

        total_locks = len(await self.lock_manager.list_locks())

        conflicts = await self.detect_conflicts()

        return {
            "total_agents": len(self._sessions),
            "active_agents": active_agents,
            "total_locks": total_locks,
            "conflicts": len(conflicts),
        }
