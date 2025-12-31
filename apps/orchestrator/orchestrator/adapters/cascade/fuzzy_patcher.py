"""
Smart Fuzzy Patcher Adapter (DEPRECATED)

⚠️  MIGRATION NOTICE:
This module is DEPRECATED. Please use:
    from codegraph_agent.shared.fuzzy_patcher import FuzzyPatcherAdapter

레거시 호환성을 위해 codegraph-agent에서 re-export합니다.
"""

import warnings

warnings.warn(
    "apps.orchestrator.orchestrator.adapters.cascade.fuzzy_patcher is deprecated. "
    "Use codegraph_agent.shared.fuzzy_patcher instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from codegraph-agent (SSOT)
from codegraph_agent.shared.fuzzy_patcher import FuzzyPatcherAdapter  # noqa: E402, F401

__all__ = ["FuzzyPatcherAdapter"]
