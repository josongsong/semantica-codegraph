"""Agent-specific exceptions.

Custom exception hierarchy for agent operations.
"""


class AgentError(Exception):
    """Base exception for all agent-related errors."""

    pass


class PatchError(AgentError):
    """Base exception for patch-related errors."""

    pass


class PatchConflictError(PatchError):
    """Raised when patch has unresolvable conflict.

    Attributes:
        patch_id: ID of the conflicting patch
        conflict_details: Details about the conflict
    """

    def __init__(self, message: str, patch_id: str | None = None, conflict_details: dict | None = None):
        """Initialize conflict error.

        Args:
            message: Error message
            patch_id: Optional patch ID
            conflict_details: Optional conflict details
        """
        super().__init__(message)
        self.patch_id = patch_id
        self.conflict_details = conflict_details or {}


class PatchApplyError(PatchError):
    """Raised when patch application fails."""

    pass


class PatchNotFoundError(PatchError):
    """Raised when patch is not found in store."""

    def __init__(self, patch_id: str):
        """Initialize not found error.

        Args:
            patch_id: Missing patch ID
        """
        super().__init__(f"Patch not found: {patch_id}")
        self.patch_id = patch_id


class WorkspaceError(AgentError):
    """Base exception for workspace-related errors."""

    pass


class WorkspacePoolExhaustedError(WorkspaceError):
    """Raised when workspace pool is full and cannot allocate new workspace.

    Attributes:
        max_workspaces: Maximum pool size
        current_size: Current pool size
    """

    def __init__(self, max_workspaces: int, current_size: int):
        """Initialize pool exhausted error.

        Args:
            max_workspaces: Maximum pool capacity
            current_size: Current pool usage
        """
        super().__init__(f"Workspace pool exhausted: {current_size}/{max_workspaces} workspaces in use")
        self.max_workspaces = max_workspaces
        self.current_size = current_size


class WorkspaceCreationError(WorkspaceError):
    """Raised when workspace creation fails."""

    pass


class GitWorktreeError(WorkspaceError):
    """Raised when git worktree operation fails."""

    pass


class TestRunError(AgentError):
    """Raised when test execution fails."""

    pass


class IndexVersionError(AgentError):
    """Raised when index version is stale or invalid.

    Attributes:
        expected_version: Expected index version
        actual_version: Actual/current index version
    """

    def __init__(self, message: str, expected_version: int | None = None, actual_version: int | None = None):
        """Initialize index version error.

        Args:
            message: Error message
            expected_version: Expected version
            actual_version: Actual version
        """
        super().__init__(message)
        self.expected_version = expected_version
        self.actual_version = actual_version


class StaleIndexError(IndexVersionError):
    """Raised when agent tries to use stale index."""

    pass


class ToolExecutionError(AgentError):
    """Raised when tool execution fails.

    Attributes:
        tool_name: Name of the tool that failed
    """

    def __init__(self, message: str, tool_name: str | None = None):
        """Initialize tool execution error.

        Args:
            message: Error message
            tool_name: Optional tool name
        """
        super().__init__(message)
        self.tool_name = tool_name


class ValidationError(AgentError):
    """Raised when validation fails."""

    pass


class ApprovalRequiredError(AgentError):
    """Raised when human approval is required but not obtained.

    Attributes:
        proposal_id: ID of the proposal requiring approval
        risk_level: Risk level of the proposal
    """

    def __init__(self, message: str, proposal_id: str | None = None, risk_level: str | None = None):
        """Initialize approval required error.

        Args:
            message: Error message
            proposal_id: Optional proposal ID
            risk_level: Optional risk level
        """
        super().__init__(message)
        self.proposal_id = proposal_id
        self.risk_level = risk_level
