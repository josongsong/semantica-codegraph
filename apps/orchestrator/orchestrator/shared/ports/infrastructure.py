"""
Infrastructure Abstraction Ports (DEPRECATED)

⚠️  MIGRATION NOTICE:
This module is DEPRECATED. Please use:
    from codegraph_agent.ports.infrastructure import (
        CommandStatus,
        InfraCommandResult,
        IInfraCommandExecutor,
        IFileSystem,
        ...
    )

레거시 호환성을 위해 codegraph-agent에서 re-export합니다.
"""

import warnings
from typing import TYPE_CHECKING

warnings.warn(
    "apps.orchestrator.orchestrator.shared.ports.infrastructure is deprecated. "
    "Use codegraph_agent.ports.infrastructure instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from codegraph-agent (SSOT)
from codegraph_agent.ports.infrastructure import (  # noqa: E402, F401
    CommandStatus,
    FileSystemEntry,
    IFileSystem,
    IInfraCommandExecutor,
    IProcessMonitor,
    InfraCommandResult,
    SystemProcess,
)

# Backward compatibility aliases (deprecated names)
# 레거시 코드에서 CommandResult, ICommandExecutor 사용 가능
CommandResult = InfraCommandResult
ICommandExecutor = IInfraCommandExecutor

__all__ = [
    # Current names (from codegraph-agent)
    "CommandStatus",
    "InfraCommandResult",
    "SystemProcess",
    "FileSystemEntry",
    "IInfraCommandExecutor",
    "IProcessMonitor",
    "IFileSystem",
    # Backward compatibility (deprecated)
    "CommandResult",
    "ICommandExecutor",
]

if TYPE_CHECKING:
    # Static type checkers see the proper types
    pass
