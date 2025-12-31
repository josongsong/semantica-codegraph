"""
RFC Adapter Versions (RFC-027 Section 9)

Centralized version management for RFC adapters.
Versions follow Semantic Versioning (MAJOR.MINOR.PATCH).

Version History:
- 3.0.0: RFC-028 integration (Taint + SCCP + Cost)
- 2.0.0: SCCP integration
- 1.0.0: Initial implementation
"""

# Adapter Versions (Semantic Versioning)
TAINT_VERSION = "3.0.0"  # RFC-028 integrated
SCCP_VERSION = "2.0.0"  # SCCP with dead code detection
COST_VERSION = "1.0.0"  # RFC-028 cost analysis
REASONING_VERSION = "1.0.0"  # Reasoning engine
RISK_VERSION = "1.0.0"  # Risk analysis
DIFF_VERSION = "1.0.0"  # Differential analysis
RACE_VERSION = "1.0.0"  # Race detection

# Version Registry (for dynamic lookup)
ADAPTER_VERSIONS = {
    "taint": TAINT_VERSION,
    "sccp": SCCP_VERSION,
    "cost": COST_VERSION,
    "reasoning": REASONING_VERSION,
    "risk": RISK_VERSION,
    "diff": DIFF_VERSION,
    "race": RACE_VERSION,
}


def get_adapter_version(adapter_name: str) -> str:
    """
    Get version for adapter.

    Args:
        adapter_name: Adapter name (taint, sccp, cost, etc.)

    Returns:
        Version string (e.g., "3.0.0")

    Raises:
        KeyError: If adapter not found
    """
    return ADAPTER_VERSIONS[adapter_name]


def get_all_versions() -> dict[str, str]:
    """
    Get all adapter versions.

    Returns:
        Dictionary of {adapter_name: version}
    """
    return ADAPTER_VERSIONS.copy()
