"""
Taint Analysis Configuration (NEW: 2025-12)

Externalized configuration for Source/Sink definitions.
Enables project-specific customization without code changes.

Architecture:
- Domain model (no infrastructure dependencies)
- DI-friendly (inject into NodeMatcher)
- Immutable configuration
- Default built-in config

Usage:
    # Use default
    config = TaintConfig.default()

    # Custom
    config = TaintConfig(
        sources={"custom": ["my_input"]},
        sinks={"custom": ["my_execute"]}
    )

    # Inject into QueryEngine
    matcher = NodeMatcher(graph, taint_config=config)
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TaintConfig:
    """
    Taint analysis configuration

    Defines source and sink patterns for security analysis.
    Immutable for thread safety.

    Attributes:
        sources: Category → [pattern names]
        sinks: Category → [pattern names]

    Examples:
        config = TaintConfig(
            sources={
                "request": ["input", "request.get", "request.args"],
                "file": ["open", "read"],
                "env": ["os.environ", "getenv"]
            },
            sinks={
                "execute": ["eval", "exec", "os.system"],
                "sql": ["execute", "query"],
                "file": ["write", "dump"]
            }
        )
    """

    sources: dict[str, list[str]] = field(default_factory=dict)
    sinks: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "TaintConfig":
        """
        Default built-in configuration

        Returns comprehensive source/sink patterns for common vulnerabilities.

        Sources by category:
            - request: User input from HTTP requests
            - file: File system reads
            - env: Environment variables
            - socket: Network input
            - database: Database query results

        Sinks by category:
            - execute: Command execution
            - sql: SQL queries
            - file: File system writes
            - log: Logging operations
            - network: Network output
        """
        return cls(
            sources={
                "request": [
                    "input",
                    "get_input",
                    "request",
                    "request.get",
                    "request.args",
                    "request.form",
                    "request.json",
                    "request.data",
                    "flask.request",
                    "django.request",
                ],
                "file": [
                    "open",
                    "read",
                    "readline",
                    "readlines",
                    "file.read",
                    "Path.read_text",
                ],
                "env": [
                    "environ",
                    "getenv",
                    "os.environ",
                    "os.getenv",
                    "sys.argv",
                ],
                "socket": [
                    "socket",
                    "recv",
                    "recvfrom",
                    "accept",
                ],
                "database": [
                    "query",
                    "fetchone",
                    "fetchall",
                    "fetchmany",
                ],
            },
            sinks={
                "execute": [
                    "eval",
                    "exec",
                    "system",
                    "os.system",
                    "subprocess.run",
                    "subprocess.call",
                    "subprocess.Popen",
                    "subprocess.check_output",
                    "commands.getoutput",
                ],
                "sql": [
                    "execute",
                    "query",
                    "raw",
                    "executemany",
                    "executescript",
                    "cursor.execute",
                ],
                "file": [
                    "write",
                    "writelines",
                    "dump",
                    "file.write",
                    "Path.write_text",
                ],
                "log": [
                    "logger.info",
                    "logger.debug",
                    "logger.warning",
                    "logger.error",
                    "print",
                    "log",
                ],
                "network": [
                    "send",
                    "sendto",
                    "sendall",
                    "socket.send",
                ],
            },
        )

    def get_sources(self, category: str | None = None) -> list[str]:
        """
        Get source names by category

        Args:
            category: Source category (e.g., "request", "file")
                     None = all categories

        Returns:
            List of source pattern names

        Examples:
            config.get_sources("request")  # ["input", "request.get", ...]
            config.get_sources()           # All sources
        """
        if category is None:
            # Flatten all categories
            return [name for names in self.sources.values() for name in names]
        return self.sources.get(category, [])

    def get_sinks(self, category: str | None = None) -> list[str]:
        """
        Get sink names by category

        Args:
            category: Sink category (e.g., "execute", "sql")
                     None = all categories

        Returns:
            List of sink pattern names

        Examples:
            config.get_sinks("execute")  # ["eval", "exec", ...]
            config.get_sinks()           # All sinks
        """
        if category is None:
            # Flatten all categories
            return [name for names in self.sinks.values() for name in names]
        return self.sinks.get(category, [])

    def get_all_categories(self) -> dict[str, tuple[list[str], list[str]]]:
        """
        Get all categories with their sources and sinks

        Returns:
            Dict[category, (sources, sinks)]

        Example:
            categories = config.get_all_categories()
            # {"request": (["input", ...], []),
            #  "execute": ([], ["eval", "exec", ...]), ...}
        """
        all_cats = set(self.sources.keys()) | set(self.sinks.keys())
        return {cat: (self.sources.get(cat, []), self.sinks.get(cat, [])) for cat in all_cats}
