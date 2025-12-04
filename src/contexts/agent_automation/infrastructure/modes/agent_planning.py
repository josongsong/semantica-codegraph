"""
Agent Planning Mode

High-level task planning and decomposition for complex multi-step tasks.

Features:
- Task decomposition into subtasks
- Dependency analysis between subtasks
- Execution order planning
- Resource estimation
- Risk assessment for complex plans
"""

from typing import Any

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)


@mode_registry.register(AgentMode.AGENT_PLANNING)
class AgentPlanningMode(BaseModeHandler):
    """
    Agent Planning mode for complex task planning.

    Flow:
    1. Analyze task complexity
    2. Decompose into subtasks
    3. Identify dependencies
    4. Determine execution order
    5. Estimate resources/time
    6. Assess risks

    Transitions:
    - plan_ready → IMPLEMENTATION (simple plan)
    - complex_plan → MULTI_FILE_EDITING (multi-file changes)
    - migration_plan → MIGRATION (database/schema migration)
    """

    def __init__(self, llm_client=None):
        """
        Initialize Agent Planning mode.

        Args:
            llm_client: Optional LLM client for intelligent planning
        """
        super().__init__(AgentMode.AGENT_PLANNING)
        self.llm = llm_client

    async def enter(self, context: ModeContext) -> None:
        """Enter agent planning mode."""
        await super().enter(context)
        self.logger.info(f"📋 Agent Planning mode: {context.current_task}")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute agent planning.

        Args:
            task: Planning task with requirements
            context: Shared mode context

        Returns:
            Result with plan, subtasks, and execution order
        """
        self.logger.info(f"Planning: {task.query}")

        # 1. Analyze task complexity
        complexity = self._analyze_complexity(task)

        # 2. Decompose into subtasks
        subtasks = await self._decompose_task(task, context)

        # 3. Identify dependencies
        dependencies = self._identify_dependencies(subtasks)

        # 4. Determine execution order
        execution_order = self._determine_execution_order(subtasks, dependencies)

        # 5. Estimate resources
        estimates = self._estimate_resources(subtasks)

        # 6. Assess risks
        risks = self._assess_risks(subtasks, complexity)

        # 7. Create plan document
        plan = {
            "task": task.query,
            "complexity": complexity,
            "subtasks": subtasks,
            "dependencies": dependencies,
            "execution_order": execution_order,
            "estimates": estimates,
            "risks": risks,
        }

        # 8. Update context
        context.current_task = task.query

        # 9. Determine trigger based on plan type
        trigger = self._determine_trigger(subtasks, complexity)

        return self._create_result(
            data=plan,
            trigger=trigger,
            explanation=f"Plan created: {len(subtasks)} subtasks, complexity: {complexity}",
            requires_approval=True,
        )

    def _analyze_complexity(self, task: Task) -> str:
        """
        Analyze task complexity.

        Args:
            task: Planning task

        Returns:
            "low", "medium", or "high"
        """
        query_lower = task.query.lower()

        # High complexity indicators
        high_indicators = [
            "migration",
            "refactor entire",
            "redesign",
            "rewrite",
            "architecture",
            "전체",
            "마이그레이션",
            "아키텍처",
        ]

        # Medium complexity indicators
        medium_indicators = [
            "multiple",
            "several",
            "integrate",
            "connect",
            "여러",
            "통합",
        ]

        if any(ind in query_lower for ind in high_indicators):
            return "high"
        elif any(ind in query_lower for ind in medium_indicators):
            return "medium"
        else:
            return "low"

    async def _decompose_task(self, task: Task, context: ModeContext) -> list[dict]:
        """
        Decompose task into subtasks.

        Args:
            task: Planning task
            context: Mode context

        Returns:
            List of subtasks
        """
        if self.llm:
            try:
                return await self._decompose_with_llm(task, context)
            except Exception as e:
                self.logger.warning(f"LLM decomposition failed: {e}, using template")

        # Fallback: Template-based decomposition
        return self._decompose_template(task)

    async def _decompose_with_llm(self, task: Task, context: ModeContext) -> list[dict]:
        """Decompose task using LLM."""
        if self.llm is None:
            return []

        prompt = f"""Decompose this task into subtasks:

Task: {task.query}

Context files: {", ".join(context.current_files[:5]) if context.current_files else "None"}

Provide 3-7 subtasks in this format:
1. [Type] Description (estimated lines: N)
2. [Type] Description (estimated lines: N)
...

Types: setup, implement, test, refactor, document, deploy
"""

        response = await self.llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1000,
        )

        # Parse response
        subtasks = []
        content = response.get("content", "")

        for line in content.strip().split("\n"):
            line = line.strip()
            if line and line[0].isdigit():
                # Parse: "1. [Type] Description (estimated lines: N)"
                parts = line.split("]", 1)
                if len(parts) == 2:
                    task_type = parts[0].split("[")[-1].strip().lower()
                    description = parts[1].strip()

                    # Extract estimated lines
                    estimated_lines = 50  # default
                    if "lines:" in description.lower():
                        try:
                            lines_part = description.lower().split("lines:")[-1]
                            estimated_lines = int("".join(filter(str.isdigit, lines_part.split(")")[0])))
                        except (ValueError, IndexError):
                            pass

                    subtasks.append(
                        {
                            "id": len(subtasks) + 1,
                            "type": task_type,
                            "description": description.split("(")[0].strip(),
                            "estimated_lines": estimated_lines,
                            "status": "pending",
                        }
                    )

        return subtasks if subtasks else self._decompose_template(task)

    def _decompose_template(self, task: Task) -> list[dict]:
        """Template-based task decomposition."""
        query_lower = task.query.lower()

        subtasks = []

        # Standard subtasks based on keywords
        if any(kw in query_lower for kw in ["add", "create", "implement", "구현"]):
            subtasks = [
                {
                    "id": 1,
                    "type": "setup",
                    "description": "Setup project structure",
                    "estimated_lines": 20,
                    "status": "pending",
                },
                {
                    "id": 2,
                    "type": "implement",
                    "description": "Implement core functionality",
                    "estimated_lines": 100,
                    "status": "pending",
                },
                {
                    "id": 3,
                    "type": "test",
                    "description": "Write unit tests",
                    "estimated_lines": 50,
                    "status": "pending",
                },
                {
                    "id": 4,
                    "type": "document",
                    "description": "Add documentation",
                    "estimated_lines": 30,
                    "status": "pending",
                },
            ]
        elif any(kw in query_lower for kw in ["fix", "bug", "error", "버그"]):
            subtasks = [
                {
                    "id": 1,
                    "type": "analyze",
                    "description": "Analyze error and find root cause",
                    "estimated_lines": 0,
                    "status": "pending",
                },
                {
                    "id": 2,
                    "type": "implement",
                    "description": "Implement fix",
                    "estimated_lines": 30,
                    "status": "pending",
                },
                {
                    "id": 3,
                    "type": "test",
                    "description": "Add regression test",
                    "estimated_lines": 20,
                    "status": "pending",
                },
            ]
        elif any(kw in query_lower for kw in ["refactor", "리팩토링"]):
            subtasks = [
                {
                    "id": 1,
                    "type": "analyze",
                    "description": "Identify refactoring targets",
                    "estimated_lines": 0,
                    "status": "pending",
                },
                {
                    "id": 2,
                    "type": "refactor",
                    "description": "Apply refactoring",
                    "estimated_lines": 100,
                    "status": "pending",
                },
                {
                    "id": 3,
                    "type": "test",
                    "description": "Run existing tests",
                    "estimated_lines": 0,
                    "status": "pending",
                },
                {
                    "id": 4,
                    "type": "test",
                    "description": "Add missing tests",
                    "estimated_lines": 50,
                    "status": "pending",
                },
            ]
        elif any(kw in query_lower for kw in ["migration", "마이그레이션"]):
            subtasks = [
                {
                    "id": 1,
                    "type": "analyze",
                    "description": "Analyze migration scope",
                    "estimated_lines": 0,
                    "status": "pending",
                },
                {
                    "id": 2,
                    "type": "setup",
                    "description": "Create migration scripts",
                    "estimated_lines": 50,
                    "status": "pending",
                },
                {
                    "id": 3,
                    "type": "implement",
                    "description": "Update code for new schema",
                    "estimated_lines": 100,
                    "status": "pending",
                },
                {"id": 4, "type": "test", "description": "Test migration", "estimated_lines": 30, "status": "pending"},
                {
                    "id": 5,
                    "type": "deploy",
                    "description": "Deploy migration",
                    "estimated_lines": 10,
                    "status": "pending",
                },
            ]
        else:
            # Generic subtasks
            subtasks = [
                {
                    "id": 1,
                    "type": "analyze",
                    "description": "Analyze requirements",
                    "estimated_lines": 0,
                    "status": "pending",
                },
                {
                    "id": 2,
                    "type": "implement",
                    "description": "Implement changes",
                    "estimated_lines": 50,
                    "status": "pending",
                },
                {"id": 3, "type": "test", "description": "Test changes", "estimated_lines": 20, "status": "pending"},
            ]

        return subtasks

    def _identify_dependencies(self, subtasks: list[dict]) -> list[dict]:
        """
        Identify dependencies between subtasks.

        Args:
            subtasks: List of subtasks

        Returns:
            List of dependency relationships
        """
        dependencies = []

        # Simple rule: each task depends on previous tasks of certain types
        for i, task in enumerate(subtasks):
            task_type = task.get("type", "")

            # Test depends on implement
            if task_type == "test":
                for j in range(i):
                    if subtasks[j].get("type") in ["implement", "refactor"]:
                        dependencies.append({"from": subtasks[j]["id"], "to": task["id"], "type": "requires"})

            # Document depends on implement
            if task_type == "document":
                for j in range(i):
                    if subtasks[j].get("type") == "implement":
                        dependencies.append({"from": subtasks[j]["id"], "to": task["id"], "type": "requires"})

            # Deploy depends on test
            if task_type == "deploy":
                for j in range(i):
                    if subtasks[j].get("type") == "test":
                        dependencies.append({"from": subtasks[j]["id"], "to": task["id"], "type": "requires"})

        return dependencies

    def _determine_execution_order(self, subtasks: list[dict], dependencies: list[dict]) -> list[int]:
        """
        Determine execution order based on dependencies (topological sort).

        Args:
            subtasks: List of subtasks
            dependencies: List of dependencies

        Returns:
            List of subtask IDs in execution order
        """
        if not subtasks:
            return []

        # Build adjacency list
        graph: dict[int, list[int]] = {task["id"]: [] for task in subtasks}
        in_degree: dict[int, int] = {task["id"]: 0 for task in subtasks}

        for dep in dependencies:
            from_id = dep["from"]
            to_id = dep["to"]
            if from_id in graph and to_id in in_degree:
                graph[from_id].append(to_id)
                in_degree[to_id] += 1

        # Kahn's algorithm for topological sort
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        order = []

        while queue:
            current = queue.pop(0)
            order.append(current)

            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # If not all tasks are in order, there might be a cycle - just return original order
        if len(order) != len(subtasks):
            return [task["id"] for task in subtasks]

        return order

    def _estimate_resources(self, subtasks: list[dict]) -> dict[str, Any]:
        """
        Estimate resources for the plan.

        Args:
            subtasks: List of subtasks

        Returns:
            Resource estimates
        """
        total_lines = sum(task.get("estimated_lines", 0) for task in subtasks)

        return {
            "total_subtasks": len(subtasks),
            "total_estimated_lines": total_lines,
            "files_affected": max(1, total_lines // 100),  # rough estimate
        }

    def _assess_risks(self, subtasks: list[dict], complexity: str) -> list[dict]:
        """
        Assess risks for the plan.

        Args:
            subtasks: List of subtasks
            complexity: Task complexity

        Returns:
            List of identified risks
        """
        risks = []

        # Complexity-based risks
        if complexity == "high":
            risks.append(
                {
                    "risk": "High complexity may lead to unforeseen issues",
                    "mitigation": "Break down into smaller PRs, review incrementally",
                    "severity": "medium",
                }
            )

        # Task count risks
        if len(subtasks) > 5:
            risks.append(
                {
                    "risk": "Many subtasks increase coordination overhead",
                    "mitigation": "Consider parallel execution where possible",
                    "severity": "low",
                }
            )

        # Migration-specific risks
        has_migration = any(task.get("type") == "deploy" for task in subtasks)
        if has_migration:
            risks.append(
                {
                    "risk": "Migration may cause downtime",
                    "mitigation": "Plan for rollback, test in staging first",
                    "severity": "high",
                }
            )

        return risks

    def _determine_trigger(self, subtasks: list[dict], complexity: str) -> str:
        """
        Determine appropriate trigger based on plan.

        Args:
            subtasks: List of subtasks
            complexity: Task complexity

        Returns:
            Trigger string for FSM
        """
        # Check for migration tasks
        has_migration = any(
            task.get("type") == "deploy" or "migration" in task.get("description", "").lower() for task in subtasks
        )
        if has_migration:
            return "migration_plan"

        # Check for complex multi-file changes
        if complexity == "high" or len(subtasks) > 4:
            return "complex_plan"

        # Simple plan
        return "plan_ready"

    async def exit(self, context: ModeContext) -> None:
        """Exit agent planning mode."""
        self.logger.info("Agent planning complete")
        await super().exit(context)
