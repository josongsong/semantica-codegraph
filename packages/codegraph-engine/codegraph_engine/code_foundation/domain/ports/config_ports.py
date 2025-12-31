"""
Configuration Ports

RFC-052: MCP Service Layer Architecture
Domain-defined interface for configuration access.

Why Port?
- Config is Infrastructure concern
- Application needs config values
- Port abstracts implementation (env vars, files, etc.)
"""

from typing import Protocol


class ConfigPort(Protocol):
    """
    Configuration provider port.

    Domain-defined interface for accessing configuration.
    """

    @property
    def evidence_ttl_days(self) -> int:
        """Evidence TTL in days"""
        ...

    @property
    def engine_version(self) -> str:
        """QueryEngine version"""
        ...

    @property
    def ruleset_hash(self) -> str:
        """Taint/security ruleset hash"""
        ...

    @property
    def session_cleanup_days(self) -> int:
        """Session cleanup threshold in days"""
        ...
