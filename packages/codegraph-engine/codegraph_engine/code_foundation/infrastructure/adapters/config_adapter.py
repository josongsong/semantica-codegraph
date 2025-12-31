"""
Config Adapter

RFC-052: MCP Service Layer Architecture
Implements ConfigPort using MCPConfig.

Adapter Pattern:
- Port: ConfigPort (Domain)
- Adapter: ConfigAdapter (Infrastructure)
- Adaptee: MCPConfig (Infrastructure)
"""

from codegraph_engine.code_foundation.domain.ports.config_ports import ConfigPort
from codegraph_engine.code_foundation.infrastructure.config import get_mcp_config


class ConfigAdapter:
    """
    Config adapter for ConfigPort.

    Bridges Domain (ConfigPort) and Infrastructure (MCPConfig).
    """

    def __init__(self):
        """Initialize adapter with MCPConfig"""
        self._config = get_mcp_config()

    @property
    def evidence_ttl_days(self) -> int:
        return self._config.evidence_ttl_days

    @property
    def engine_version(self) -> str:
        return self._config.engine_version

    @property
    def ruleset_hash(self) -> str:
        return self._config.ruleset_hash

    @property
    def session_cleanup_days(self) -> int:
        return self._config.session_cleanup_days
