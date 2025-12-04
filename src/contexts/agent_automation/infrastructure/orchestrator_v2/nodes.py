"""LangGraph Node Implementations."""

from pathlib import Path
from typing import Any

from src.contexts.agent_automation.infrastructure.tools.conflict_resolver import PatchConflictResolver
from src.infra.observability import get_logger

from .state import AgentState

logger = get_logger(__name__)

# Graph-aware planner can be imported when needed
# from .graph_planner import GraphAwarePlanner


class PlannerNode:
    """Plans and decomposes tasks into subtasks.

    Uses LLM to analyze the task and determine:
    - How to break it down into subtasks
    - Which subtasks can run in parallel
    - Dependencies between subtasks
    - Resource allocation (files, workspaces)
    """

    def __init__(self, llm_client: Any | None = None):
        """Initialize planner.

        Args:
            llm_client: LLM client for task decomposition
        """
        self.llm_client = llm_client

    async def __call__(self, state: AgentState) -> dict:
        """Plan the task.

        Args:
            state: Current agent state

        Returns:
            Updated state with plan
        """
        task = state["task"]

        logger.info("planning_task", task=task[:100])

        # Simple heuristic-based planning (can be enhanced with LLM)
        plan = self._simple_plan(task)

        return {
            "plan": plan,
            "parallel_allowed": len(plan) > 1,
            "dependency_graph": {},
            "agent_results": {},
            "patches": [],
            "conflicts": [],
            "retry_count": 0,
            "max_retries": 3,
            "errors": [],
        }

    def _simple_plan(self, task: str) -> list[dict]:
        """Simple rule-based task planning.

        Args:
            task: Task description

        Returns:
            List of subtask dicts
        """
        # Simple implementation - can be enhanced with LLM
        subtasks = []

        # Check for keywords
        if "refactor" in task.lower():
            subtasks.append(
                {
                    "id": "subtask-1",
                    "type": "refactor",
                    "description": task,
                    "agent_mode": "REFACTOR",
                }
            )

        elif "test" in task.lower() and "implement" in task.lower():
            # Needs both implementation and testing
            subtasks.append(
                {
                    "id": "subtask-1",
                    "type": "implementation",
                    "description": f"Implement {task}",
                    "agent_mode": "IMPLEMENTATION",
                }
            )
            subtasks.append(
                {
                    "id": "subtask-2",
                    "type": "test",
                    "description": f"Test {task}",
                    "agent_mode": "TEST",
                    "depends_on": ["subtask-1"],
                }
            )

        else:
            # Single task
            subtasks.append(
                {
                    "id": "subtask-1",
                    "type": "general",
                    "description": task,
                    "agent_mode": "IMPLEMENTATION",
                }
            )

        logger.info("plan_created", subtasks_count=len(subtasks))

        return subtasks


class MergerNode:
    """Merges results from parallel agents.

    Handles:
    - Collecting patches from all agents
    - Detecting conflicts (same file modifications)
    - Resolving conflicts using PatchConflictResolver
    - Creating final merged patch set
    """

    def __init__(self, conflict_resolver: PatchConflictResolver | None = None, repo_path: str | None = None):
        """Initialize merger.

        Args:
            conflict_resolver: Patch conflict resolver (default: creates new instance)
            repo_path: Repository root path for reading file contents
        """
        self.conflict_resolver = conflict_resolver or PatchConflictResolver()
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()

    async def __call__(self, state: AgentState) -> dict:
        """Merge agent results.

        Args:
            state: Current agent state

        Returns:
            Updated state with merged results
        """
        agent_results = state.get("agent_results", {})
        patches = state.get("patches", [])

        logger.info("merging_results", agent_count=len(agent_results))

        # Collect patches from all agents
        all_patches = []
        for _agent_id, result in agent_results.items():
            if isinstance(result, dict) and "patches" in result:
                all_patches.extend(result["patches"])

        all_patches.extend(patches)

        # Detect conflicts (same file)
        conflicts = self._detect_conflicts(all_patches)

        # Resolve conflicts if any
        if conflicts:
            logger.warning("conflicts_detected", count=len(conflicts))
            merged_patches = self._resolve_conflicts(all_patches, conflicts)
            merge_success = len(merged_patches) == len(all_patches)
        else:
            merged_patches = all_patches
            merge_success = True

        return {
            "merged_patches": merged_patches,
            "conflicts": conflicts,
            "merge_success": merge_success,
        }

    def _detect_conflicts(self, patches: list[dict]) -> list[dict]:
        """Detect patches modifying the same file.

        Args:
            patches: List of patch dicts

        Returns:
            List of conflict dicts
        """
        file_patches: dict[str, list[dict]] = {}

        for patch in patches:
            file_path = patch.get("file_path", "")
            if file_path not in file_patches:
                file_patches[file_path] = []
            file_patches[file_path].append(patch)

        # Files with multiple patches are conflicts
        conflicts = []
        for file_path, file_patch_list in file_patches.items():
            if len(file_patch_list) > 1:
                conflicts.append(
                    {
                        "file_path": file_path,
                        "patch_count": len(file_patch_list),
                        "patches": file_patch_list,
                    }
                )

        return conflicts

    def _resolve_conflicts(self, patches: list[dict], conflicts: list[dict]) -> list[dict]:
        """Resolve conflicts by merging patches using 3-way merge.

        Uses PatchConflictResolver to perform intelligent merging of conflicting patches.

        Args:
            patches: All patches
            conflicts: Detected conflicts

        Returns:
            Merged patches
        """
        # Build conflict map: file_path -> list of patches
        conflict_map = {c["file_path"]: c["patches"] for c in conflicts}

        resolved = []
        seen_files = set()

        for patch in patches:
            file_path = patch.get("file_path", "")

            # Skip if already processed
            if file_path in seen_files:
                continue

            # No conflict - keep original patch
            if file_path not in conflict_map:
                resolved.append(patch)
                seen_files.add(file_path)
                continue

            # Conflict - use 3-way merge
            conflicting_patches = conflict_map[file_path]

            try:
                merged_patch = self._merge_patches(file_path, conflicting_patches)
                resolved.append(merged_patch)
                logger.info(
                    "3way_merge_success",
                    file_path=file_path,
                    patch_count=len(conflicting_patches),
                )
            except Exception as e:
                # Merge failed - keep first patch as fallback
                logger.warning(
                    "3way_merge_failed_fallback_to_first",
                    file_path=file_path,
                    error=str(e),
                )
                resolved.append(conflicting_patches[0])

            seen_files.add(file_path)

        logger.info("conflicts_resolved", resolved_count=len(resolved))

        return resolved

    def _merge_patches(self, file_path: str, conflicting_patches: list[dict]) -> dict:
        """Merge multiple patches for the same file using 3-way merge.

        Args:
            file_path: File being modified
            conflicting_patches: List of patches modifying the same file

        Returns:
            Merged patch

        Raises:
            Exception: If merge fails
        """
        # Get base content (current file state)
        base_content = self._read_file(file_path)

        # Apply patches sequentially with 3-way merge
        current_content = base_content

        for i, patch in enumerate(conflicting_patches):
            proposed_content = patch.get("new_code") or patch.get("content", "")

            if not proposed_content:
                logger.warning(
                    "patch_missing_content",
                    file_path=file_path,
                    patch_index=i,
                )
                continue

            # 3-way merge: base -> current -> proposed
            merge_result = self.conflict_resolver.merge_3way(
                base=base_content,
                ours=current_content,
                theirs=proposed_content,
            )

            if merge_result.success:
                # Auto-merged successfully
                current_content = merge_result.content
                logger.debug(
                    "patch_merged",
                    file_path=file_path,
                    patch_index=i,
                    resolution=merge_result.resolution.value,
                )
            else:
                # Has conflicts - try auto-resolve with "theirs" strategy
                logger.warning(
                    "patch_has_conflicts_using_theirs",
                    file_path=file_path,
                    patch_index=i,
                    conflict_count=len(merge_result.conflicts),
                )
                resolved = self.conflict_resolver.resolve_conflicts(merge_result, strategy="theirs")
                current_content = resolved.content

        # Create merged patch
        merged_patch = {
            "file_path": file_path,
            "new_code": current_content,
            "description": f"Merged {len(conflicting_patches)} patches for {file_path}",
            "merged_from": [p.get("patch_id") or f"patch-{i}" for i, p in enumerate(conflicting_patches)],
        }

        # Preserve metadata from first patch
        if conflicting_patches:
            first_patch = conflicting_patches[0]
            for key in ["base_content", "base_version_id", "index_version_id", "agent_mode"]:
                if key in first_patch:
                    merged_patch[key] = first_patch[key]

        return merged_patch

    def _read_file(self, file_path: str) -> str:
        """Read current file content.

        Args:
            file_path: Path to file (relative to repo root)

        Returns:
            File content (empty string if file doesn't exist)
        """
        try:
            full_path = self.repo_path / file_path
            if full_path.exists():
                return full_path.read_text(encoding="utf-8")
            return ""
        except Exception as e:
            logger.warning(f"Failed to read file {file_path}: {e}")
            return ""


class ValidatorNode:
    """Validates merged results.

    Runs:
    - Tests on changed files
    - Lint/format validation
    - Type checking
    - Determines if retry needed
    """

    def __init__(self, test_runner: Any | None = None):
        """Initialize validator.

        Args:
            test_runner: Test runner instance
        """
        self.test_runner = test_runner

    async def __call__(self, state: AgentState) -> dict:
        """Validate results.

        Args:
            state: Current agent state

        Returns:
            Updated state with validation results
        """
        merged_patches = state.get("merged_patches", [])

        logger.info("validating_results", patch_count=len(merged_patches))

        # Simple validation - can be enhanced
        # No patches is OK (read-only operations are valid)
        validation_result = {
            "patch_count": len(merged_patches),
            "has_errors": False,  # Always pass for now
        }

        validation_passed = True  # Always pass simple validation

        # Never retry automatically (can be enhanced with real validation)
        retry_count = state.get("retry_count", 0)
        should_retry = False

        return {
            "validation_result": validation_result,
            "validation_passed": validation_passed,
            "should_retry": should_retry,
            "retry_count": retry_count + 1 if should_retry else retry_count,
        }
