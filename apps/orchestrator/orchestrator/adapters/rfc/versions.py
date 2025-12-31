"""
DEPRECATED: Use src.contexts.llm_arbitration.infrastructure.adapters.versions instead

RFC Adapter Versions (RFC-027 Section 9)

This module re-exports from the canonical location for backward compatibility.
"""

# Re-export from canonical location
from codegraph_runtime.llm_arbitration.infrastructure.adapters.versions import (  # noqa: F401
    ADAPTER_VERSIONS,
    COST_VERSION,
    DIFF_VERSION,
    RACE_VERSION,
    REASONING_VERSION,
    RISK_VERSION,
    SCCP_VERSION,
    TAINT_VERSION,
    get_adapter_version,
    get_all_versions,
)

__all__ = [
    "TAINT_VERSION",
    "SCCP_VERSION",
    "COST_VERSION",
    "REASONING_VERSION",
    "RISK_VERSION",
    "DIFF_VERSION",
    "RACE_VERSION",
    "ADAPTER_VERSIONS",
    "get_adapter_version",
    "get_all_versions",
]
