"""
LATS Search Engine (v9)

MCTS 기반 Tree Search
"""

import asyncio
import json
import logging
import random
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..tot.tot_models import ToTResult
from .lats_models import (
    LATSEvent,
    LATSEventType,
    LATSNode,
    LATSSearchMetrics,
    MCTSConfig,
    WinningPath,
)

if TYPE_CHECKING:
    from codegraph_agent.ports.reasoning import ILATSExecutor

logger = logging.getLogger(__name__)


class LATSSearchEngine:
    """
    LATS Search Engine (Domain Service)

    책임:
    1. MCTS 4단계 실행 (Selection, Expansion, Simulation, Backpropagation)
    2. Tree 구조 관리
    3. 최종 전략 선택

    SOTA:
    - MCTS (Monte Carlo Tree Search)
    - UCT (Upper Confidence Bound for Trees)
    - Reflection 기반 Thought Evaluation
    """

    def __init__(
        self,
        executor: "ILATSExecutor",
        config: MCTSConfig | None = None,
        on_event: Callable[[LATSEvent], None] | None = None,
        save_winning_paths: bool = True,
        enable_reflexion: bool = True,
        experience_repository=None,
    ):
        """
        Args:
            executor: LATS Executor (Adapter)
            config: MCTS 설정
            on_event: Event Callback (Streaming용)
            save_winning_paths: Winning Path 저장 여부
            enable_reflexion: Reflexion 활성화 (P2 Advanced)
            experience_repository: Experience Store (Optional, P2)
        """
        self.executor = executor
        self.config = config or MCTSConfig()
        self.on_event = on_event
        self.save_winning_paths = save_winning_paths
        self.enable_reflexion = enable_reflexion
        self.experience_repo = experience_repository

        # Metrics
        self.metrics = LATSSearchMetrics()

        # Reflexion (P2)
        if enable_reflexion:
            from .lats_reflexion import LATSReflexion

            self.reflexion = LATSReflexion()
        else:
            self.reflexion = None

        # Winning Path 저장 경로
        self.winning_path_dir = Path("data/lats/winning_paths")
        if save_winning_paths:
            self.winning_path_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"LATSSearchEngine initialized: "
            f"max_iter={self.config.max_iterations}, "
            f"max_depth={self.config.max_depth}, "
            f"reflexion={enable_reflexion}, "
            f"experience_store={experience_repository is not None}"
        )

    async def search(
        self,
        problem: str,
        context: dict,
        cancellation_token: asyncio.Event | None = None,
    ) -> ToTResult:
        """
        LATS Tree Search 실행

        Args:
            problem: 문제 설명
            context: 컨텍스트
            cancellation_token: 취소 Token (Optional)

        Returns:
            ToTResult (기존 인터페이스 호환)
        """
        logger.info(f"Starting LATS search: {problem[:50]}...")

        # Seed 설정 (Determinism)
        if self.config.seed is not None:
            random.seed(self.config.seed)
            logger.info(f"LATS search with seed={self.config.seed} (deterministic mode)")

        # Event: Search Start
        self._emit_event(
            LATSEvent(
                type=LATSEventType.SEARCH_START,
                iteration=0,
                message=f"Starting LATS search: {problem[:50]}...",
            )
        )

        # Root 노드 생성
        root = LATSNode(
            node_id="root",
            partial_thought=f"Problem: {problem}",
            depth=0,
        )

        # MCTS 반복
        for iteration in range(self.config.max_iterations):
            # Cancellation Check
            if cancellation_token and cancellation_token.is_set():
                logger.warning(f"LATS search cancelled at iteration {iteration}")
                break

            logger.debug(f"MCTS Iteration {iteration + 1}/{self.config.max_iterations}")

            # Event: Iteration Start
            self._emit_event(
                LATSEvent(
                    type=LATSEventType.ITERATION_START,
                    iteration=iteration + 1,
                    message=f"Iteration {iteration + 1}/{self.config.max_iterations}",
                )
            )

            # 1. Selection (UCT)
            node = self._selection(root)

            # Event: Selection
            self._emit_event(
                LATSEvent(
                    type=LATSEventType.SELECTION,
                    iteration=iteration + 1,
                    node_id=node.node_id,
                    message=f"Selected node: {node.node_id}",
                    metadata={"q_value": node.q_value, "visit_count": node.visit_count},
                )
            )

            # 2. Expansion (LLM)
            if not node.is_terminal:
                # Event: Expansion
                self._emit_event(
                    LATSEvent(
                        type=LATSEventType.EXPANSION,
                        iteration=iteration + 1,
                        node_id=node.node_id,
                        message="Expanding node (generating thoughts)...",
                    )
                )

                node, tokens_used = await self._expansion_with_tracking(node, problem, context)

                # Budget Tracking
                self.metrics.add_tokens(
                    phase="expansion", tokens=tokens_used, cost_per_1k=self.config.cost_per_1k_tokens
                )

            # 3. Simulation (Rollout)
            # Event: Simulation Start
            self._emit_event(
                LATSEvent(
                    type=LATSEventType.SIMULATION_START,
                    iteration=iteration + 1,
                    node_id=node.node_id,
                    message="Simulating node...",
                )
            )

            value, tokens_used = await self._simulation_with_tracking(node, problem, context)

            # Budget Tracking
            self.metrics.add_tokens(phase="simulation", tokens=tokens_used, cost_per_1k=self.config.cost_per_1k_tokens)

            # Event: Simulation End
            self._emit_event(
                LATSEvent(
                    type=LATSEventType.SIMULATION_END,
                    iteration=iteration + 1,
                    node_id=node.node_id,
                    message=f"Simulation complete: value={value:.2f}",
                    metadata={"value": value},
                )
            )

            # 4. Backpropagation (Q-value 업데이트)
            # Event: Backpropagation
            self._emit_event(
                LATSEvent(
                    type=LATSEventType.BACKPROPAGATION,
                    iteration=iteration + 1,
                    node_id=node.node_id,
                    message="Updating Q-values...",
                )
            )

            self._backpropagation(node, value)

            self.metrics.iterations_completed = iteration + 1

            # Budget Circuit Breaker
            if self.metrics.exceeds_budget(self.config):
                logger.warning(
                    f"Budget exceeded! "
                    f"Tokens: {self.metrics.total_tokens_used}/{self.config.max_total_tokens}, "
                    f"Cost: ${self.metrics.total_cost_usd:.2f}/${self.config.max_cost_usd:.2f}"
                )

                # Event: Budget Check
                self._emit_event(
                    LATSEvent(
                        type=LATSEventType.BUDGET_CHECK,
                        iteration=iteration + 1,
                        message=f"Budget exceeded (${self.metrics.total_cost_usd:.2f})",
                        metadata={
                            "tokens": self.metrics.total_tokens_used,
                            "cost": self.metrics.total_cost_usd,
                        },
                    )
                )

                break

            # Early Give-up (정답 없는 문제)
            if self._should_give_up(root, iteration):
                logger.warning(f"Early give-up at iteration {iteration + 1}")

                # Event: Early Giveup
                self._emit_event(
                    LATSEvent(
                        type=LATSEventType.EARLY_GIVEUP,
                        iteration=iteration + 1,
                        message="Low confidence, giving up",
                    )
                )

                break

            # Early Stop (충분히 좋은 솔루션)
            if self._has_good_solution(root):
                logger.info(f"Early stop at iteration {iteration + 1}")

                # Event: Early Stop
                self._emit_event(
                    LATSEvent(
                        type=LATSEventType.EARLY_STOP,
                        iteration=iteration + 1,
                        message="Early stop (good solution found)",
                    )
                )

                break

        # Metrics 종료
        self.metrics.end_time = self.metrics.start_time + self.metrics.get_duration()

        # Log 최종 통계
        logger.info(
            f"LATS completed: "
            f"{self.metrics.iterations_completed} iterations, "
            f"{self.metrics.total_tokens_used} tokens, "
            f"${self.metrics.total_cost_usd:.2f} cost, "
            f"{self.metrics.get_duration():.1f}s"
        )

        # Tree → ToTResult 변환
        tot_result = self._to_tot_result(root)

        # Metrics 첨부
        tot_result.lats_metrics = self.metrics.to_dict()

        # Winning Path 저장
        if self.save_winning_paths and tot_result.best_strategy_id:
            winning_path = self._extract_winning_path(root, tot_result, problem, context)
            if winning_path:
                self._save_winning_path(winning_path)

        # Tree Dump (디버깅)
        if logger.isEnabledFor(logging.DEBUG):
            self._dump_tree_json(root, "/tmp/lats_tree.json")

        # Event: Search End
        self._emit_event(
            LATSEvent(
                type=LATSEventType.SEARCH_END,
                iteration=self.metrics.iterations_completed,
                message="LATS search completed",
                metadata={
                    "total_tokens": self.metrics.total_tokens_used,
                    "total_cost": self.metrics.total_cost_usd,
                    "best_q_value": root.best_child().q_value if root.children else 0.0,
                },
            )
        )

        return tot_result

    # ========================================================================
    # MCTS 4 Stages
    # ========================================================================

    def _selection(self, root: LATSNode) -> LATSNode:
        """
        Selection Phase (MCTS)

        UCT를 사용하여 가장 유망한 노드 선택

        Args:
            root: Root 노드

        Returns:
            선택된 노드 (Leaf 또는 확장 가능)
        """
        node = root

        while not node.is_leaf() and node.depth < self.config.max_depth:
            # UCB1이 가장 높은 자식 선택
            node = max(node.children, key=lambda c: c.ucb(self.config.exploration_constant))

        logger.debug(
            f"Selected node: {node.node_id} (depth={node.depth}, visits={node.visit_count}, q={node.q_value:.2f})"
        )

        return node

    async def _expansion_with_tracking(self, node: LATSNode, problem: str, context: dict) -> tuple[LATSNode, int]:
        """
        Expansion Phase + Token Tracking

        Args:
            node: 확장할 노드
            problem: 문제
            context: 컨텍스트

        Returns:
            (새 자식 노드, 사용 토큰)
        """
        # LLM으로 다음 step 생성
        next_thoughts = await self.executor.generate_next_thoughts(
            current_state=node.get_summary(),  # Context 경량화!
            problem=problem,
            context=context,
            k=self.config.strategies_per_expansion,
        )

        logger.debug(f"Expanded {len(next_thoughts)} children from {node.node_id}")

        # 자식 노드 생성
        for i, thought in enumerate(next_thoughts):
            child = LATSNode(
                node_id=f"{node.node_id}-{i}",
                partial_thought=thought,
                thought_diff=thought,  # Incremental State
            )
            node.add_child(child)
            self.metrics.nodes_created += 1

        # 토큰 추정 (TODO: LLM Response에서 실제 usage 추출)
        estimated_tokens = len(problem.split()) * 2 + 200

        # 첫 번째 자식 반환 (Simulation으로)
        return node.children[0] if node.children else node, estimated_tokens

    async def _simulation_with_tracking(self, node: LATSNode, problem: str, context: dict) -> tuple[float, int]:
        """
        Simulation Phase + Token Tracking

        Args:
            node: 시뮬레이션 노드
            problem: 문제
            context: 컨텍스트

        Returns:
            (보상, 사용 토큰)
        """
        # Leaf 노드: 실제 코드 생성 및 실행
        if node.depth >= self.config.max_depth - 1:
            return await self._simulate_leaf_with_tracking(node, problem, context)

        # 중간 노드: Thought Evaluation
        else:
            return await self._simulate_intermediate_with_tracking(node)

    async def _simulate_leaf_with_tracking(self, node: LATSNode, problem: str, context: dict) -> tuple[float, int]:
        """
        Leaf 노드 시뮬레이션 (실제 코드 생성 및 실행)

        Returns:
            (실행 결과 점수, 사용 토큰)
        """
        # 1. 완전한 전략 생성
        strategy = await self.executor.generate_complete_strategy(
            thought_path=node.get_full_path(), problem=problem, context=context
        )

        node.completed_strategy = strategy
        node.is_terminal = True

        # 2. Sandbox 실행
        try:
            execution_result = await self.executor.execute_strategy(strategy)
        except Exception as e:
            # ✅ Reflexion: 실행 실패 시 이유 전파
            if self.reflexion:
                failure_reason = self.reflexion.extract_failure_reason(node, str(e))
                self.reflexion.propagate_to_parent(node, failure_reason)

            logger.warning(f"Execution failed: {e}")

            # 실패 점수 반환
            return 0.0, 500

        # 3. 점수 계산 (ToT Scorer 재사용)
        from ..tot.tot_scorer import ToTScoringEngine

        scorer = ToTScoringEngine()
        score = scorer.score_strategy(strategy, execution_result)

        # ✅ Reflexion: 낮은 점수 시 이유 전파
        if self.reflexion and score.total_score < 0.5:
            weakness = score.weaknesses[:100] if score.weaknesses else "unknown"
            reason = f"Low score ({score.total_score:.2f}): {weakness}"
            self.reflexion.propagate_to_parent(node, reason)

        logger.debug(f"Leaf simulation: {node.node_id} → {score.total_score:.2f}")

        # 토큰 추정
        estimated_tokens = 500  # Leaf는 큼

        return score.total_score, estimated_tokens

    async def _simulate_intermediate_with_tracking(self, node: LATSNode) -> tuple[float, int]:
        """
        중간 노드 시뮬레이션 (Thought Evaluator)

        Returns:
            (Thought 평가 점수, 사용 토큰)
        """
        # Thought Evaluator로 중간 평가
        thought_score = await self.executor.evaluate_thought(partial_thought=node.partial_thought)

        node.thought_score = thought_score
        node.is_promising = thought_score >= self.config.thought_eval_threshold

        logger.debug(
            f"Thought eval: {node.node_id} → {thought_score:.2f} "
            f"({'promising' if node.is_promising else 'unpromising'})"
        )

        # 토큰 추정
        estimated_tokens = 50  # 평가는 작음

        return thought_score, estimated_tokens

    def _backpropagation(self, node: LATSNode, value: float):
        """
        Backpropagation Phase (MCTS)

        Q-value 업데이트 (역전파)

        Args:
            node: 시작 노드
            value: 보상
        """
        updates = []

        while node:
            old_q = node.q_value
            node.update_q_value(value)

            updates.append(f"{node.node_id}: {old_q:.2f} → {node.q_value:.2f}")

            node = node.parent

        logger.debug(f"Backpropagation: {' <- '.join(updates)}")

    # ========================================================================
    # Termination Conditions
    # ========================================================================

    def _has_good_solution(self, root: LATSNode) -> bool:
        """
        충분히 좋은 솔루션이 있는가?

        Args:
            root: Root 노드

        Returns:
            조기 종료 여부
        """
        # BFS로 모든 Leaf 탐색
        leaves = self._get_all_leaves(root)

        for leaf in leaves:
            if leaf.q_value >= self.config.early_stop_threshold:
                return True

        return False

    def _should_give_up(self, root: LATSNode, iteration: int) -> bool:
        """
        조기 포기 여부 (정답 없는 문제)

        Args:
            root: Root 노드
            iteration: 현재 반복 횟수

        Returns:
            포기 여부
        """
        if not self.config.enable_early_giveup:
            return False

        if iteration < self.config.early_giveup_iterations:
            return False

        # 현재 최고 점수
        leaves = self._get_all_leaves(root)
        if not leaves:
            return False

        best_leaf = max(leaves, key=lambda leaf: leaf.q_value, default=None)

        if best_leaf and best_leaf.q_value < self.config.early_giveup_threshold:
            logger.warning(
                f"Early give-up: best_q_value={best_leaf.q_value:.2f} < {self.config.early_giveup_threshold}"
            )
            return True

        return False

    # ========================================================================
    # Tree Utilities
    # ========================================================================

    def _get_all_leaves(self, node: LATSNode) -> list[LATSNode]:
        """
        모든 Leaf 노드 수집 (BFS)

        Args:
            node: 시작 노드

        Returns:
            Leaf 노드 리스트
        """
        leaves = []
        queue = [node]

        while queue:
            current = queue.pop(0)

            if current.is_leaf():
                leaves.append(current)
            else:
                queue.extend(current.children)

        return leaves

    def _count_nodes(self, node: LATSNode) -> int:
        """
        전체 노드 수

        Args:
            node: 시작 노드

        Returns:
            노드 개수
        """
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count

    def _get_max_depth(self, node: LATSNode) -> int:
        """
        최대 깊이

        Args:
            node: 시작 노드

        Returns:
            최대 깊이
        """
        if not node.children:
            return node.depth
        return max(self._get_max_depth(c) for c in node.children)

    # ========================================================================
    # Result Conversion
    # ========================================================================

    def _to_tot_result(self, root: LATSNode) -> ToTResult:
        """
        LATS Tree → ToTResult 변환 (기존 인터페이스 호환)

        Args:
            root: Root 노드

        Returns:
            ToTResult
        """
        from ..tot.tot_models import StrategyScore

        # 모든 Leaf 노드 수집
        leaves = self._get_all_leaves(root)

        # CodeStrategy 추출
        strategies = [leaf.completed_strategy for leaf in leaves if leaf.completed_strategy]

        # 점수 계산 (Q-value 기반)
        scores = {}
        for leaf in leaves:
            if leaf.completed_strategy:
                score = StrategyScore(
                    strategy_id=leaf.completed_strategy.strategy_id,
                    total_score=leaf.q_value,
                    confidence=leaf.visit_count / root.visit_count if root.visit_count > 0 else 0,
                    recommendation="LATS selected" if leaf.q_value >= 0.7 else "Consider alternatives",
                )
                scores[leaf.completed_strategy.strategy_id] = score

        # Best 선택 (가장 많이 방문된 Leaf)
        best_leaf = max(leaves, key=lambda leaf: leaf.visit_count, default=None)

        result = ToTResult(
            all_strategies=strategies,
            executed_strategies=[s for s in strategies if s.is_completed()],
            scores=scores,
            best_strategy_id=best_leaf.completed_strategy.strategy_id
            if best_leaf and best_leaf.completed_strategy
            else None,
            best_score=best_leaf.q_value if best_leaf else 0.0,
            total_generated=len(strategies),
            total_executed=len([s for s in strategies if s.is_completed()]),
            total_passed=len(
                [s for s in strategies if scores.get(s.strategy_id, None) and scores[s.strategy_id].total_score >= 0.6]
            ),
        )

        return result

    # ========================================================================
    # Winning Path (Data Flywheel)
    # ========================================================================

    def _extract_winning_path(
        self, root: LATSNode, tot_result: ToTResult, problem: str, context: dict
    ) -> WinningPath | None:
        """
        Best Leaf로 이어지는 경로 추출

        Args:
            root: Root 노드
            tot_result: ToT 결과
            problem: 문제
            context: 컨텍스트

        Returns:
            WinningPath (성공 시)
        """
        if not tot_result.best_strategy_id:
            return None

        # Best Leaf 찾기
        best_leaf = self._find_best_leaf(root, tot_result.best_strategy_id)

        if not best_leaf or not best_leaf.completed_strategy:
            return None

        # Root → Leaf 경로
        thought_sequence = best_leaf.get_full_path()

        # WinningPath 생성
        winning_path = WinningPath(
            problem_description=problem,
            problem_type=context.get("problem_type", "unknown"),
            thought_sequence=thought_sequence,
            final_strategy_id=best_leaf.completed_strategy.strategy_id,
            final_code_changes=best_leaf.completed_strategy.file_changes,
            final_q_value=best_leaf.q_value,
            total_iterations=self.metrics.iterations_completed,
            total_nodes_explored=self.metrics.nodes_created,
            execution_result={},  # TODO: ExecutionResult 직렬화
            reflection_verdict="ACCEPT",  # TODO: 실제 Reflection 결과
            llm_model=self.config.generator_model,
            lats_config={
                "max_iterations": self.config.max_iterations,
                "max_depth": self.config.max_depth,
                "exploration_constant": self.config.exploration_constant,
            },
        )

        return winning_path

    def _find_best_leaf(self, root: LATSNode, best_strategy_id: str) -> LATSNode | None:
        """Best Strategy를 가진 Leaf 찾기"""
        leaves = self._get_all_leaves(root)

        for leaf in leaves:
            if leaf.completed_strategy and leaf.completed_strategy.strategy_id == best_strategy_id:
                return leaf

        return None

    def _save_winning_path(self, winning_path: WinningPath):
        """Winning Path를 JSONL + Experience Store에 저장"""
        if not winning_path:
            return

        # 1. 파일 저장 (JSONL)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        problem_hash = hash(winning_path.problem_description) % 10000
        filename = f"{timestamp}_{problem_hash:04d}.jsonl"

        filepath = self.winning_path_dir / filename

        # JSONL 저장
        filepath.write_text(winning_path.to_jsonl())

        logger.info(f"Winning path saved to file: {filepath}")

        # 2. Experience Store 저장 (Optional)
        if self.experience_repo:
            try:
                from apps.orchestrator.orchestrator.domain.experience import (
                    AgentExperience,
                    ProblemType,
                )

                # ProblemType Enum 매칭
                try:
                    problem_type_enum = ProblemType(winning_path.problem_type)
                except ValueError:
                    problem_type_enum = ProblemType.OTHER

                experience = AgentExperience(
                    problem_description=winning_path.problem_description,
                    problem_type=problem_type_enum,
                    strategy_id=winning_path.final_strategy_id,
                    strategy_type="LATS",  # LATS로 고정
                    code_chunk_ids=[],
                    file_paths=list(winning_path.final_code_changes.keys()),
                    success=winning_path.reflection_verdict == "ACCEPT",
                    tot_score=winning_path.final_q_value,
                    reflection_verdict=winning_path.reflection_verdict,
                    test_pass_rate=winning_path.execution_result.get("test_pass_rate"),
                    graph_impact=None,
                    execution_time=None,
                    similar_to_ids=[],
                    tags=["lats", "v9", f"iterations_{winning_path.total_iterations}"],
                )

                self.experience_repo.save(experience)
                logger.info("Winning path saved to Experience Store")

            except Exception as e:
                logger.warning(f"Failed to save to Experience Store: {e}")

    # ========================================================================
    # Debugging & Visualization
    # ========================================================================

    def _dump_tree_json(self, root: LATSNode, output_path: str):
        """JSON 형태로 Tree 덤프 (디버깅)"""

        def node_to_dict(node: LATSNode) -> dict:
            return {
                "id": node.node_id,
                "thought": node.partial_thought[:50] + "..."
                if len(node.partial_thought) > 50
                else node.partial_thought,
                "q_value": round(node.q_value, 3),
                "visit_count": node.visit_count,
                "thought_score": round(node.thought_score, 3),
                "is_promising": node.is_promising,
                "is_terminal": node.is_terminal,
                "depth": node.depth,
                "children": [node_to_dict(c) for c in node.children],
            }

        tree_data = {
            "problem": root.partial_thought[:100],
            "total_nodes": self._count_nodes(root),
            "max_depth": self._get_max_depth(root),
            "metrics": self.metrics.to_dict(),
            "tree": node_to_dict(root),
        }

        Path(output_path).write_text(json.dumps(tree_data, indent=2, ensure_ascii=False))
        logger.info(f"Tree dumped to {output_path}")

    # ========================================================================
    # Event Streaming
    # ========================================================================

    def _emit_event(self, event: LATSEvent):
        """이벤트 발행"""
        if self.on_event:
            try:
                self.on_event(event)
            except Exception as e:
                logger.error(f"Event callback failed: {e}")
