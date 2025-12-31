"""
Debate Orchestrator

Multi-Agent 토론 오케스트레이션.
"""

import logging
import time
from collections.abc import Callable

from .agent_roles import DebateAgent
from .consensus_builder import ConsensusBuilder
from .debate_models import (
    AgentRole,
    DebateConfig,
    DebateResult,
    DebateRound,
    Position,
)

logger = logging.getLogger(__name__)


class DebateOrchestrator:
    """토론 오케스트레이터"""

    def __init__(self, config: DebateConfig | None = None):
        self.config = config or DebateConfig()
        self.consensus_builder = ConsensusBuilder(self.config)

    async def debate_async(
        self,
        problem: str,
        generate_fn: Callable[[str, int, list], str],
    ) -> DebateResult:
        """
        Async debate execution with v8 integration

        Args:
            problem: Problem to solve
            generate_fn: Async function to generate positions (agent_id, round, prev) -> str

        Returns:
            DebateResult
        """
        import time

        start_time = time.time()

        # Create agents with adapted generate_fn
        agents = []
        for i in range(self.config.num_proposers):
            agent_id = f"proposer_{i}"

            async def agent_generate_fn(prob, prev_positions):
                # Call v8's generate_fn
                return await generate_fn(agent_id, 0, prev_positions)

            from .agent_roles import AgentRole, DebateAgent

            agent = DebateAgent(agent_id=agent_id, role=AgentRole.PROPOSER, generate_fn=agent_generate_fn)
            agents.append(agent)

        # Run debate rounds
        all_positions = []
        rounds = []

        for round_num in range(self.config.max_rounds):
            round_positions = []

            for agent in agents:
                try:
                    position = await agent.generate_position(problem, all_positions)
                    round_positions.append(position)
                    all_positions.append(position)
                except Exception as e:
                    logger.error(f"Agent {agent.agent_id} failed: {e}")

            from .debate_models import DebateRound

            round_obj = DebateRound(
                round_number=round_num + 1,
                positions=round_positions,
                consensus_reached=False,
                agreement_score=0.5,
            )
            rounds.append(round_obj)

        # Build result
        from .debate_models import DebateResult

        result = DebateResult(
            final_decision="Debate complete",
            final_position=all_positions[0] if all_positions else None,
            rounds=rounds,
            consensus_reached=False,
            final_agreement_score=0.5,
            total_rounds=len(rounds),
            total_positions=len(all_positions),
            debate_time=time.time() - start_time,
        )

        return result

    async def orchestrate_debate(
        self,
        problem: str,
        generate_fn: Callable[[str], str],
    ) -> DebateResult:
        """
        토론 실행

        Args:
            problem: 문제
            generate_fn: 텍스트 생성 함수 (LLM)

        Returns:
            토론 결과
        """
        start_time = time.time()
        logger.info(f"Starting debate for: {problem[:100]}...")

        # 1. 에이전트 생성
        agents = self._create_agents(generate_fn)

        # 2. 토론 라운드
        rounds: list[DebateRound] = []
        all_positions: list[Position] = []

        for round_num in range(1, self.config.max_rounds + 1):
            logger.info(f"Debate round {round_num}/{self.config.max_rounds}")

            # 2.1 각 에이전트가 포지션 생성
            round_positions = []

            for agent in agents:
                position = await agent.generate_position(problem, all_positions)
                round_positions.append(position)
                all_positions.append(position)

            # 2.2 합의 확인
            consensus_reached, agreement_score, consensus_content = self.consensus_builder.build_consensus(
                round_positions
            )

            # 2.3 라운드 기록
            debate_round = DebateRound(
                round_number=round_num,
                positions=round_positions,
                consensus_reached=consensus_reached,
                agreement_score=agreement_score,
            )
            rounds.append(debate_round)

            # 2.4 합의 도달 시 종료
            if consensus_reached:
                logger.info(f"Consensus reached at round {round_num}")
                break

        # 3. 최종 결정 (Judge)
        judge = DebateAgent(AgentRole.JUDGE, "judge", generate_fn)
        final_position = await judge.generate_position(problem, all_positions)

        # 4. 결과 생성
        debate_time = time.time() - start_time

        result = DebateResult(
            final_decision=final_position.content,
            final_position=final_position,
            rounds=rounds,
            consensus_reached=rounds[-1].consensus_reached if rounds else False,
            final_agreement_score=rounds[-1].agreement_score if rounds else 0.0,
            total_rounds=len(rounds),
            total_positions=len(all_positions),
            debate_time=debate_time,
        )

        logger.info(
            f"Debate completed in {debate_time:.2f}s: {len(rounds)} rounds, consensus={result.consensus_reached}"
        )

        return result

    def _create_agents(self, generate_fn: Callable[[str], str]) -> list[DebateAgent]:
        """
        에이전트 생성

        Args:
            generate_fn: 생성 함수

        Returns:
            에이전트 리스트
        """
        agents: list[DebateAgent] = []

        # Proposers
        for i in range(self.config.num_proposers):
            agent = DebateAgent(AgentRole.PROPOSER, f"proposer_{i}", generate_fn)
            agents.append(agent)

        # Critics
        for i in range(self.config.num_critics):
            agent = DebateAgent(AgentRole.CRITIC, f"critic_{i}", generate_fn)
            agents.append(agent)

        logger.info(
            f"Created {len(agents)} debate agents: "
            f"{self.config.num_proposers} proposers, {self.config.num_critics} critics"
        )

        return agents

    def orchestrate_debate_sync(
        self,
        problem: str,
        generate_fn: Callable[[str], str],
    ) -> DebateResult:
        """동기 버전"""
        import asyncio

        return asyncio.run(self.orchestrate_debate(problem, generate_fn))
