"""
LATS Domain Models (v9)

MCTS 기반 Tree Search를 위한 도메인 모델
"""

import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from ..tot.tot_models import CodeStrategy

# ============================================================================
# Enums
# ============================================================================


class LATSPhase(Enum):
    """LATS 실행 단계"""

    EXPANSION = "expansion"  # 확장 (다양성 필요)
    EVALUATION = "evaluation"  # 평가 (안정성 필요)
    SIMULATION = "simulation"  # 시뮬레이션 (정확성 필요)
    FINAL_GENERATION = "final"  # 최종 생성 (품질 필요)


class LATSEventType(Enum):
    """LATS 이벤트 타입 (Streaming용)"""

    SEARCH_START = "search_start"
    ITERATION_START = "iteration_start"
    SELECTION = "selection"
    EXPANSION = "expansion"
    SIMULATION_START = "simulation_start"
    SIMULATION_END = "simulation_end"
    BACKPROPAGATION = "backpropagation"
    BUDGET_CHECK = "budget_check"
    EARLY_STOP = "early_stop"
    EARLY_GIVEUP = "early_giveup"
    SEARCH_END = "search_end"


# ============================================================================
# Tree Node
# ============================================================================


@dataclass
class LATSNode:
    """
    LATS Tree Node (Domain Model)

    MCTS 기반 트리 탐색의 노드

    책임:
    - Tree 구조 관리 (Parent-Child)
    - MCTS 값 저장 (Q-value, Visit Count)
    - UCB 계산

    Memory Safety:
    - Python GC가 circular reference 처리
    - 명시적 cleanup 지원 (cleanup_tree)
    """

    # Identity
    node_id: str
    parent: Optional["LATSNode"] = None
    children: list["LATSNode"] = field(default_factory=list)
    depth: int = 0

    # State
    partial_thought: str = ""  # 중간 단계 (e.g., "1. 파일 X 읽기")
    thought_diff: str = ""  # 부모 대비 변화량 (Context 경량화)
    completed_strategy: CodeStrategy | None = None  # Leaf 노드만

    # MCTS Values
    visit_count: int = 0
    total_value: float = 0.0
    q_value: float = 0.0  # Q(s,a) = avg reward

    # Reflection
    thought_score: float = 0.0  # 중간 평가 점수
    is_promising: bool = True  # 유망한가?
    is_terminal: bool = False  # Leaf 노드인가?

    # Feedback (Reflexion)
    rejected_reasons: list[str] = field(default_factory=list)  # 실패 이유들

    def ucb(self, c: float = 1.4) -> float:
        """
        UCT (Upper Confidence Bound for Trees)

        UCB1 = Q(s,a) + c * sqrt(ln(N_parent) / N_child)

        Args:
            c: 탐험 계수 (default 1.4)

        Returns:
            UCB 값 (높을수록 선택됨)
        """
        if self.visit_count == 0:
            return float("inf")  # 미방문 노드 우선

        if not self.parent:
            return self.q_value

        exploitation = self.q_value
        exploration = c * math.sqrt(math.log(self.parent.visit_count) / self.visit_count)

        return exploitation + exploration

    def update_q_value(self, reward: float):
        """
        Q-value 업데이트

        Q(s,a) = (Q * N + reward) / (N + 1)
        """
        self.visit_count += 1
        self.total_value += reward
        self.q_value = self.total_value / self.visit_count

    def add_child(self, child: "LATSNode"):
        """자식 노드 추가"""
        child.parent = self
        child.depth = self.depth + 1
        self.children.append(child)

    def cleanup_tree(self):
        """
        Tree 메모리 정리 (Optional)

        Circular reference 명시적 해제
        대규모 탐색 후 메모리 정리용
        """
        for child in self.children:
            child.cleanup_tree()
            child.parent = None
        self.children.clear()

    def is_leaf(self) -> bool:
        """Leaf 노드인가?"""
        return len(self.children) == 0 or self.is_terminal

    def best_child(self) -> Optional["LATSNode"]:
        """가장 높은 Q-value를 가진 자식"""
        if not self.children:
            return None
        return max(self.children, key=lambda c: c.q_value)

    def most_visited_child(self) -> Optional["LATSNode"]:
        """가장 많이 방문된 자식 (최종 선택용)"""
        if not self.children:
            return None
        return max(self.children, key=lambda c: c.visit_count)

    def get_full_path(self) -> list[str]:
        """전체 경로 재구성 (Root → Current)"""
        path = []
        node = self

        while node:
            if node.thought_diff:
                path.append(node.thought_diff)
            elif node.partial_thought:
                path.append(node.partial_thought)
            node = node.parent

        return list(reversed(path))

    def get_summary(self, max_length: int = 200) -> str:
        """
        경로 요약 (Context Window 절약)

        Args:
            max_length: 최대 길이

        Returns:
            요약 문자열
        """
        full_path = self.get_full_path()

        if len(full_path) <= 3:
            return " → ".join(full_path)

        # 깊은 경로: 첫 2개 + ... + 마지막 1개
        summary = f"{full_path[0]} → {full_path[1]} → ... → {full_path[-1]}"

        if len(summary) > max_length:
            summary = summary[:max_length] + "..."

        return summary

    def add_rejection_reason(self, reason: str):
        """실패 이유 추가 (Reflexion)"""
        if reason and reason not in self.rejected_reasons:
            self.rejected_reasons.append(reason)


# ============================================================================
# MCTS Configuration
# ============================================================================


@dataclass
class MCTSConfig:
    """MCTS 설정"""

    # MCTS Parameters
    max_iterations: int = 100  # MCTS 반복 횟수
    max_depth: int = 5  # 최대 깊이
    exploration_constant: float = 1.4  # UCT c 값
    min_visit_threshold: int = 3  # 최소 방문 횟수
    early_stop_threshold: float = 0.9  # 조기 종료 점수

    # Expansion
    strategies_per_expansion: int = 3  # 확장 시 생성할 자식 수

    # Thought Evaluator
    thought_eval_threshold: float = 0.3  # 중간 평가 최소 점수

    # Dynamic Temperature
    temperature_expansion: float = 0.8  # 확장 (다양성)
    temperature_evaluation: float = 0.2  # 평가 (안정성)
    temperature_simulation: float = 0.0  # 시뮬레이션 (결정론)
    temperature_final: float = 0.3  # 최종 생성 (품질)

    # Budget Limits
    max_total_tokens: int = 50_000  # 토큰 제한
    max_cost_usd: float = 5.0  # 비용 제한 ($5)
    cost_per_1k_tokens: float = 0.03  # GPT-4 기준
    enable_budget_limit: bool = True

    # Early Give-up
    early_giveup_iterations: int = 10  # 초반 N번 체크
    early_giveup_threshold: float = 0.3  # 최고 점수 임계값
    enable_early_giveup: bool = True

    # Multi-Model Strategy
    generator_model: str = "gpt-4o"  # 생성: GPT-4
    verifier_model: str = "claude-3.5-sonnet"  # 검증: Claude
    final_model: str = "gpt-4o"  # 최종: GPT-4
    enable_cross_model: bool = True  # Cross-Model 활성화

    # Determinism
    seed: int | None = None  # Random Seed (테스트용)

    # Optimization
    enable_prompt_caching: bool = True  # Prompt Caching
    enable_semantic_dedup: bool = True  # 의미론적 중복 제거
    parallel_evaluation: bool = True  # 병렬 평가

    # Context Management
    context_length_limit: int = 1000  # Context 길이 제한 (토큰)

    def get_temperature(self, phase: LATSPhase) -> float:
        """
        단계별 Temperature 반환

        Args:
            phase: LATS 실행 단계

        Returns:
            Temperature 값
        """
        if phase == LATSPhase.EXPANSION:
            return self.temperature_expansion
        elif phase == LATSPhase.EVALUATION:
            return self.temperature_evaluation
        elif phase == LATSPhase.SIMULATION:
            return self.temperature_simulation
        elif phase == LATSPhase.FINAL_GENERATION:
            return self.temperature_final
        else:
            return 0.7  # Fallback


# ============================================================================
# Metrics & Monitoring
# ============================================================================


@dataclass
class LATSSearchMetrics:
    """LATS Search 실행 메트릭"""

    # Tokens
    total_tokens_used: int = 0
    tokens_by_phase: dict[str, int] = field(default_factory=dict)

    # Cost
    total_cost_usd: float = 0.0

    # Iterations
    iterations_completed: int = 0
    nodes_created: int = 0
    nodes_pruned: int = 0

    # Time
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0

    # Deduplication
    duplicates_removed: int = 0

    def add_tokens(self, phase: str, tokens: int, cost_per_1k: float):
        """
        토큰 사용 기록

        Args:
            phase: 실행 단계
            tokens: 사용 토큰 수
            cost_per_1k: 1K 토큰당 비용
        """
        self.total_tokens_used += tokens

        if phase not in self.tokens_by_phase:
            self.tokens_by_phase[phase] = 0
        self.tokens_by_phase[phase] += tokens

        # 비용 계산
        self.total_cost_usd += (tokens / 1000) * cost_per_1k

    def exceeds_budget(self, config: MCTSConfig) -> bool:
        """
        예산 초과 여부

        Args:
            config: MCTS 설정

        Returns:
            초과 여부
        """
        if not config.enable_budget_limit:
            return False

        if self.total_tokens_used > config.max_total_tokens:
            return True

        if self.total_cost_usd > config.max_cost_usd:
            return True

        return False

    def get_duration(self) -> float:
        """실행 시간 (초)"""
        if self.end_time > 0:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "total_tokens": self.total_tokens_used,
            "tokens_by_phase": self.tokens_by_phase,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "iterations": self.iterations_completed,
            "nodes_created": self.nodes_created,
            "nodes_pruned": self.nodes_pruned,
            "duplicates_removed": self.duplicates_removed,
            "duration_seconds": round(self.get_duration(), 2),
        }


# ============================================================================
# Event Streaming
# ============================================================================


@dataclass
class LATSEvent:
    """LATS 실행 이벤트 (Streaming)"""

    type: LATSEventType
    iteration: int
    node_id: str | None = None
    message: str = ""
    metadata: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """딕셔너리로 변환 (SSE용)"""
        return {
            "type": self.type.value,
            "iteration": self.iteration,
            "node_id": self.node_id,
            "message": self.message,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


# ============================================================================
# Winning Path (Data Flywheel)
# ============================================================================


@dataclass
class WinningPath:
    """
    성공적인 LATS 사고 경로

    Fine-tuning 및 Distillation용 데이터
    """

    # Problem
    problem_description: str
    problem_type: str

    # Trajectory (Root → Leaf)
    thought_sequence: list[str]  # ["1. 파일 읽기", "1.1 경로 확인", ...]

    # Final Strategy
    final_strategy_id: str
    final_code_changes: dict[str, str]

    # Metrics
    final_q_value: float
    total_iterations: int
    total_nodes_explored: int

    # Outcome
    execution_result: dict  # ExecutionResult 직렬화
    reflection_verdict: str  # ACCEPT/REVISE/ROLLBACK

    # Meta
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    llm_model: str = "gpt-4o"
    lats_config: dict = field(default_factory=dict)  # MCTSConfig 직렬화

    def to_jsonl(self) -> str:
        """
        JSONL 형태로 직렬화 (Fine-tuning용)

        Returns:
            JSONL 문자열
        """
        import json

        data = {
            "problem": self.problem_description,
            "problem_type": self.problem_type,
            "thoughts": self.thought_sequence,
            "solution": self.final_code_changes,
            "q_value": self.final_q_value,
            "verdict": self.reflection_verdict,
            "timestamp": self.timestamp,
            "model": self.llm_model,
        }

        return json.dumps(data, ensure_ascii=False)

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "problem_description": self.problem_description,
            "problem_type": self.problem_type,
            "thought_sequence": self.thought_sequence,
            "final_strategy_id": self.final_strategy_id,
            "final_code_changes": self.final_code_changes,
            "final_q_value": self.final_q_value,
            "total_iterations": self.total_iterations,
            "total_nodes_explored": self.total_nodes_explored,
            "execution_result": self.execution_result,
            "reflection_verdict": self.reflection_verdict,
            "timestamp": self.timestamp,
            "llm_model": self.llm_model,
            "lats_config": self.lats_config,
        }


# ============================================================================
# Compute Allocation (Market-Based)
# ============================================================================


@dataclass
class ComputeBid:
    """노드의 계산 자원 입찰"""

    node_id: str
    confidence: float  # 성공 확률 (0.0 ~ 1.0)
    budget: float  # 예산 (가상 화폐)
    requested_time: float  # 요청 시간 (초)

    def utility(self) -> float:
        """
        효용 함수 (높을수록 우선)

        Returns:
            효용 값
        """
        return self.confidence * self.budget
