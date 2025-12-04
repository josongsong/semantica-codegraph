"""Parallel Orchestrator using LangGraph."""

from typing import Literal

from langgraph.graph import END, StateGraph

from src.infra.observability import get_logger

from .nodes import MergerNode, PlannerNode, ValidatorNode
from .state import AgentState

logger = get_logger(__name__)


class ParallelOrchestrator:
    """LangGraph-based parallel multi-agent orchestrator.

    Workflow:
    1. Planner decomposes task into subtasks
    2. Agents execute subtasks in parallel (if allowed)
    3. Merger collects and resolves conflicts
    4. Validator checks results
    5. Retry if needed or finish
    """

    def __init__(
        self,
        planner: PlannerNode | None = None,
        merger: MergerNode | None = None,
        validator: ValidatorNode | None = None,
    ):
        """Initialize orchestrator.

        Args:
            planner: Planner node (default: creates new)
            merger: Merger node (default: creates new)
            validator: Validator node (default: creates new)
        """
        self.planner = planner or PlannerNode()
        self.merger = merger or MergerNode()
        self.validator = validator or ValidatorNode()

        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow graph.

        Returns:
            Compiled StateGraph
        """
        # Create graph
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("planner", self.planner)
        workflow.add_node("execute", self._execute_agents)
        workflow.add_node("merger", self.merger)
        workflow.add_node("validator", self.validator)

        # Define flow
        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "execute")
        workflow.add_edge("execute", "merger")
        workflow.add_edge("merger", "validator")

        # Conditional retry or finish
        workflow.add_conditional_edges(
            "validator",
            self._should_retry,
            {
                "retry": "planner",
                "done": END,
            },
        )

        return workflow.compile(checkpointer=None, debug=False)

    async def _execute_agents(self, state: AgentState) -> dict:
        """Execute agent subtasks.

        For now, sequential execution. Can be enhanced with
        parallel execution using asyncio.gather.

        Args:
            state: Current state

        Returns:
            Updated state
        """
        plan = state.get("plan", [])

        logger.info("executing_agents", subtask_count=len(plan))

        # Placeholder: Execute each subtask
        # In real implementation, would use FSMNodeAdapter
        agent_results = {}

        for subtask in plan:
            subtask_id = subtask["id"]
            # Simulate execution
            agent_results[subtask_id] = {
                "mode": subtask.get("agent_mode", "IMPLEMENTATION"),
                "result": {"success": True},
                "patches": [],
            }

        return {"agent_results": agent_results}

    def _should_retry(self, state: AgentState) -> Literal["retry", "done"]:
        """Determine if workflow should retry.

        Args:
            state: Current state

        Returns:
            "retry" or "done"
        """
        should_retry = state.get("should_retry", False)

        if should_retry:
            logger.info("retry_triggered", retry_count=state.get("retry_count", 0))
            return "retry"
        else:
            logger.info("workflow_completed")
            return "done"

    async def execute(self, task: str, repo_id: str, repo_path: str) -> dict:
        """Execute the multi-agent workflow.

        Args:
            task: User task
            repo_id: Repository ID
            repo_path: Repository path

        Returns:
            Final state dict
        """
        initial_state: AgentState = {
            "task": task,
            "repo_id": repo_id,
            "repo_path": repo_path,
            "current_commit": "HEAD",
        }

        logger.info(
            "orchestrator_started",
            task=task[:100],
            repo_id=repo_id,
        )

        # Execute graph with recursion limit
        config = {"recursion_limit": 10}  # Prevent infinite loops
        final_state = await self.graph.ainvoke(initial_state, config=config)

        logger.info(
            "orchestrator_completed",
            validation_passed=final_state.get("validation_passed", False),
            patch_count=len(final_state.get("merged_patches", [])),
        )

        return final_state
