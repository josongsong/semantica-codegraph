"""
Debate Models

Multi-Agent 토론을 위한 데이터 모델.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AgentRole(str, Enum):
    """에이전트 역할"""

    PROPOSER = "proposer"  # 제안자
    CRITIC = "critic"  # 비평가
    JUDGE = "judge"  # 판사 (최종 결정)


@dataclass
class Position:
    """토론 포지션"""

    agent_role: AgentRole
    content: str
    reasoning: str
    confidence: float  # 0.0 ~ 1.0

    # 지지/반대
    supporting_points: list[str] = field(default_factory=list)
    opposing_points: list[str] = field(default_factory=list)


@dataclass
class DebateRound:
    """토론 라운드"""

    round_number: int
    positions: list[Position] = field(default_factory=list)
    consensus_reached: bool = False
    agreement_score: float = 0.0  # 합의 점수 (0.0 ~ 1.0)


@dataclass
class DebateConfig:
    """토론 설정"""

    max_rounds: int = 3  # 최대 라운드
    num_proposers: int = 2  # 제안자 수
    num_critics: int = 1  # 비평가 수

    # 합의
    consensus_threshold: float = 0.8  # 합의 임계값
    min_agreement_score: float = 0.6


@dataclass
class DebateResult:
    """토론 결과"""

    # Final decision
    final_decision: str = ""
    final_position: Position | None = None

    # Rounds
    rounds: list[DebateRound] = field(default_factory=list)

    # Consensus
    consensus_reached: bool = False
    final_agreement_score: float = 0.0

    # Metrics
    total_rounds: int = 0
    total_positions: int = 0
    debate_time: float = 0.0

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)

    def get_winning_position(self) -> Position | None:
        """
        최종 승리 포지션 반환

        Returns:
            승리 포지션
        """
        return self.final_position
