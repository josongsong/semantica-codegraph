"""FSM to LangGraph Adapter.

Wraps existing FSM mode handlers as LangGraph nodes.
"""

from src.contexts.agent_automation.infrastructure.fsm import AgentFSM
from src.contexts.agent_automation.infrastructure.types import AgentMode, Task
from src.infra.observability import get_logger

from .state import AgentState

logger = get_logger(__name__)


class FSMNodeAdapter:
    """Adapts FSM mode handlers to LangGraph nodes.

    Allows reusing existing 23 FSM modes as LangGraph nodes
    without rewriting them.
    """

    def __init__(self, fsm: AgentFSM, mode: AgentMode):
        """Initialize adapter.

        Args:
            fsm: Agent FSM instance
            mode: Which mode to adapt
        """
        self.fsm = fsm
        self.mode = mode

    async def __call__(self, state: AgentState) -> dict:
        """Execute FSM mode as LangGraph node.

        Args:
            state: Current agent state

        Returns:
            Updated state with results
        """
        # Extract task from state
        task_desc = state.get("task", "")
        subtask = self._find_subtask_for_mode(state)

        if subtask:
            task_desc = subtask.get("description", task_desc)
            subtask_id = subtask.get("id", "default")
        else:
            subtask_id = "default"

        logger.info(
            "executing_fsm_mode",
            mode=self.mode.value,
            subtask_id=subtask_id,
        )

        # Execute FSM mode
        task = Task(query=task_desc)

        # Transition to mode if needed
        if self.fsm.current_mode != self.mode:
            await self.fsm.transition_to(self.mode)

        # Execute
        result = await self.fsm.execute(task)

        # Store result in agent_results
        agent_results = state.get("agent_results", {})
        agent_results[subtask_id] = {
            "mode": self.mode.value,
            "result": result.data,
            "patches": result.data.get("patches", []) if isinstance(result.data, dict) else [],
        }

        return {
            "agent_results": agent_results,
        }

    def _find_subtask_for_mode(self, state: AgentState) -> dict | None:
        """Find subtask matching this mode.

        Args:
            state: Agent state

        Returns:
            Subtask dict or None
        """
        plan = state.get("plan", [])

        for subtask in plan:
            if subtask.get("agent_mode") == self.mode.value:
                return subtask

        return None
