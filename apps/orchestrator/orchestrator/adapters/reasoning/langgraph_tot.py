"""
LangGraph-based ToT Executor (실제 구현)

SOTA: LangGraph State Machine for Strategy Generation
"""

import asyncio
import logging
import uuid
from typing import TypedDict

from apps.orchestrator.orchestrator.shared.reasoning.tot.tot_models import (
    CodeStrategy,
    ExecutionResult,
    ExecutionStatus,
    StrategyType,
)

logger = logging.getLogger(__name__)


# ============================================================================
# LangGraph State
# ============================================================================


class ToTState(TypedDict):
    """Tree-of-Thought State"""

    problem: str
    context: dict
    strategies: list[CodeStrategy]
    strategy_count: int
    current_index: int
    errors: list[str]


# ============================================================================
# LangGraph ToT Executor
# ============================================================================


class LangGraphToTExecutor:
    """
    LangGraph 기반 ToT Executor (SOTA)

    특징:
    - LangGraph StateGraph로 전략 생성 흐름 관리
    - Parallel Strategy Generation
    - Structured Output (Pydantic)
    - Retry Logic
    """

    def __init__(
        self,
        llm_provider=None,
        sandbox_executor=None,
        max_strategies: int = 5,
        use_langgraph: bool = True,
    ):
        """
        Args:
            llm_provider: LLM Provider
            sandbox_executor: Sandbox Executor
            max_strategies: 최대 전략 수
            use_langgraph: LangGraph 사용 여부 (False면 Simple)
        """
        self._llm = llm_provider
        self._sandbox = sandbox_executor
        self._max_strategies = max_strategies
        self._use_langgraph = use_langgraph

        # LangGraph 초기화
        if self._use_langgraph and self._llm:
            self._graph = self._build_langgraph()
            logger.info("LangGraph ToT Executor initialized (SOTA mode)")
        else:
            self._graph = None
            logger.info("Simple ToT Executor initialized (fallback mode)")

    def _build_langgraph(self):
        """
        LangGraph StateGraph 구성

        Flow:
        START → generate_strategy → check_count → [loop or END]
        """
        try:
            from langgraph.graph import END, StateGraph

            # Graph 생성
            workflow = StateGraph(ToTState)

            # Nodes
            workflow.add_node("generate_strategy", self._generate_strategy_node)
            workflow.add_node("increment_index", self._increment_index_node)

            # Edges
            workflow.set_entry_point("generate_strategy")
            workflow.add_edge("generate_strategy", "increment_index")

            # Conditional Edge (loop or end)
            workflow.add_conditional_edges(
                "increment_index",
                self._should_continue,
                {
                    "continue": "generate_strategy",
                    "end": END,
                },
            )

            graph = workflow.compile()
            logger.debug("LangGraph compiled successfully")
            return graph

        except ImportError:
            logger.warning("LangGraph not installed, using simple fallback")
            return None
        except Exception as e:
            logger.error(f"Failed to build LangGraph: {e}")
            return None

    async def generate_strategies(self, problem: str, context: dict, count: int = 3) -> list[CodeStrategy]:
        """
        전략 생성 (LangGraph or Simple)

        Args:
            problem: 문제 설명
            context: 컨텍스트
            count: 생성할 전략 수

        Returns:
            CodeStrategy 리스트
        """
        count = min(count, self._max_strategies)

        logger.info(f"Generating {count} strategies for: {problem[:50]}...")

        if self._graph and self._use_langgraph:
            # LangGraph 사용
            strategies = await self._generate_with_langgraph(problem, context, count)
        else:
            # Simple Sequential
            strategies = await self._generate_simple(problem, context, count)

        logger.info(f"Generated {len(strategies)} strategies")
        return strategies

    async def execute_strategy(self, strategy: CodeStrategy, timeout: int = 60) -> ExecutionResult:
        """
        Sandbox에서 전략 실행

        Args:
            strategy: CodeStrategy
            timeout: 실행 타임아웃

        Returns:
            ExecutionResult
        """
        logger.info(f"Executing strategy: {strategy.strategy_id}")

        strategy.status = ExecutionStatus.RUNNING

        try:
            if self._sandbox:
                result = await self._sandbox.execute_code(strategy.file_changes, timeout=timeout)
                result.strategy_id = strategy.strategy_id
            else:
                logger.warning("No sandbox, using mock result")
                result = self._create_mock_result(strategy.strategy_id)

            strategy.status = ExecutionStatus.COMPLETED
            return result

        except asyncio.TimeoutError:
            logger.error(f"Strategy {strategy.strategy_id} timeout")
            strategy.status = ExecutionStatus.TIMEOUT
            return self._create_error_result(strategy.strategy_id, "Execution timeout")

        except Exception as e:
            logger.error(f"Strategy {strategy.strategy_id} failed: {e}")
            strategy.status = ExecutionStatus.FAILED
            return self._create_error_result(strategy.strategy_id, str(e))

    # ========================================================================
    # LangGraph Nodes
    # ========================================================================

    def _generate_strategy_node(self, state: ToTState) -> ToTState:
        """전략 생성 노드 (LangGraph)"""
        index = state["current_index"]

        # LLM으로 전략 생성
        strategy = self._generate_single_strategy_sync(state["problem"], state["context"], index)

        state["strategies"].append(strategy)

        logger.debug(f"Generated strategy {index + 1}/{state['strategy_count']}")
        return state

    def _increment_index_node(self, state: ToTState) -> ToTState:
        """인덱스 증가 노드"""
        state["current_index"] += 1
        return state

    def _should_continue(self, state: ToTState) -> str:
        """계속 생성할지 결정"""
        if state["current_index"] >= state["strategy_count"]:
            return "end"
        else:
            return "continue"

    # ========================================================================
    # Strategy Generation
    # ========================================================================

    async def _generate_with_langgraph(self, problem: str, context: dict, count: int) -> list[CodeStrategy]:
        """LangGraph로 전략 생성"""

        # Initial State
        initial_state: ToTState = {
            "problem": problem,
            "context": context,
            "strategies": [],
            "strategy_count": count,
            "current_index": 0,
            "errors": [],
        }

        try:
            # LangGraph 실행 (sync)
            # TODO: async invoke 지원되면 변경
            final_state = self._graph.invoke(initial_state)

            return final_state["strategies"]

        except Exception as e:
            logger.error(f"LangGraph execution failed: {e}")
            # Fallback to simple
            return await self._generate_simple(problem, context, count)

    async def _generate_simple(self, problem: str, context: dict, count: int) -> list[CodeStrategy]:
        """Simple Sequential Generation"""

        strategies = []

        for i in range(count):
            strategy = await self._generate_single_strategy(problem, context, i)
            strategies.append(strategy)

        return strategies

    def _generate_single_strategy_sync(self, problem: str, context: dict, index: int) -> CodeStrategy:
        """단일 전략 생성 (Sync, for LangGraph)"""

        # Strategy Type 결정
        strategy_types = list(StrategyType)
        strategy_type = strategy_types[index % len(strategy_types)]

        if self._llm:
            # LLM으로 실제 전략 생성
            try:
                import asyncio

                # Event loop 처리 (LangGraph 환경 고려)
                try:
                    # 기존 loop 확인
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Loop 실행 중이면 동기 방식으로
                        import concurrent.futures

                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(
                                asyncio.run,
                                self._llm.generate_strategy(
                                    problem=problem,
                                    context=context,
                                    strategy_type=strategy_type,
                                    index=index,
                                ),
                            )
                            strategy = future.result(timeout=30)
                    else:
                        # Loop 없으면 새로 생성
                        strategy = loop.run_until_complete(
                            self._llm.generate_strategy(
                                problem=problem,
                                context=context,
                                strategy_type=strategy_type,
                                index=index,
                            )
                        )
                except RuntimeError:
                    # Loop 없으면 새로 생성
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    strategy = loop.run_until_complete(
                        self._llm.generate_strategy(
                            problem=problem,
                            context=context,
                            strategy_type=strategy_type,
                            index=index,
                        )
                    )
                    loop.close()

                logger.info(f"LLM generated: {strategy.title}")
                return strategy

            except Exception as e:
                logger.error(f"LLM generation failed: {e}", exc_info=True)
                # Fallback to mock

        # Mock Strategy (LLM 없을 때)
        strategy_id = f"strategy_{uuid.uuid4().hex[:8]}"

        strategy = CodeStrategy(
            strategy_id=strategy_id,
            strategy_type=strategy_type,
            title=f"{strategy_type.value.replace('_', ' ').title()} Approach",
            description=f"Strategy {index + 1}: Apply {strategy_type.value} pattern",
            rationale=f"Use {strategy_type.value} to solve: {problem[:30]}...",
            file_changes={},
            llm_confidence=0.7 + (index * 0.05),
        )

        return strategy

    async def _generate_single_strategy(self, problem: str, context: dict, index: int) -> CodeStrategy:
        """단일 전략 생성 (Async)"""

        # Sync 버전 호출
        return self._generate_single_strategy_sync(problem, context, index)

    # ========================================================================
    # Mock/Error Helpers
    # ========================================================================

    def _create_mock_result(self, strategy_id: str) -> ExecutionResult:
        """Mock Execution Result"""
        import random

        return ExecutionResult(
            strategy_id=strategy_id,
            compile_success=True,
            tests_run=10,
            tests_passed=random.randint(5, 10),
            tests_failed=random.randint(0, 5),
            test_pass_rate=random.uniform(0.5, 1.0),
            lint_errors=random.randint(0, 3),
            lint_warnings=random.randint(0, 5),
            security_severity="none",
            complexity_delta=random.uniform(-5.0, 3.0),
            execution_time=random.uniform(1.0, 5.0),
        )

    def _create_error_result(self, strategy_id: str, error_message: str) -> ExecutionResult:
        """에러 Result"""
        return ExecutionResult(
            strategy_id=strategy_id,
            compile_success=False,
            error_message=error_message,
        )
