"""
Shared Components (Autonomous + Assistant 공통)

두 모드가 공유하는 인프라:
- Static Analysis Gate
- Git Adapter
- Local Command Executor
- Fuzzy Patcher
"""

from codegraph_agent.shared.fuzzy_patcher import FuzzyPatcherAdapter
from codegraph_agent.shared.git_adapter import GitAdapter
from codegraph_agent.shared.local_command_adapter import (
    DangerousCommandError,
    LocalCommandAdapter,
    console_approval_callback,
)
from codegraph_agent.shared.static_gate_adapter import (
    ISelfCorrector,
    StaticAnalysisGateAdapter,
)

__all__ = [
    # Adapters
    "FuzzyPatcherAdapter",
    "GitAdapter",
    "LocalCommandAdapter",
    "StaticAnalysisGateAdapter",
    # Helpers
    "console_approval_callback",
    "DangerousCommandError",
    # Protocols
    "ISelfCorrector",
]
