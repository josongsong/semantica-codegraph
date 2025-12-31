"""
TOML Control Parser

Parses semantica.toml configuration file.
Strict validation with Pydantic.
"""

from pathlib import Path

import tomli  # Python 3.11+ has tomllib built-in

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.taint.control import ControlConfig, IgnoreConfig, RuleControl

logger = get_logger(__name__)


class TOMLControlParser:
    """
    TOML Control Configuration Parser.

    Parses semantica.toml and validates with Pydantic.

    File Format:
        ```toml
        [rules]
        enabled = ["sql-injection", "xss"]
        disabled = []

        [rules.severity_override]
        "sql-injection" = "high"

        [ignore]
        patterns = ["tests/**", "*_test.py"]
        files = ["examples/unsafe.py"]
        directories = ["vendor/", "node_modules/"]
        ```

    Example:
        ```python
        parser = TOMLControlParser()
        config = parser.parse(Path("semantica.toml"))
        # → ControlConfig(...)

        if config.rules.is_enabled("sql-injection"):
            # Run analysis
        ```

    Error Handling:
    - FileNotFoundError: Config file not found
    - ValueError: Invalid TOML or schema violation
    - tomli.TOMLDecodeError: TOML syntax error
    """

    def __init__(self):
        """Initialize parser"""
        self._cache: dict[Path, ControlConfig] = {}

    def parse(self, config_path: Path) -> ControlConfig:
        """
        Parse semantica.toml.

        Args:
            config_path: Path to semantica.toml

        Returns:
            ControlConfig

        Raises:
            FileNotFoundError: If file not found
            ValueError: If validation fails
            tomli.TOMLDecodeError: If TOML syntax error

        Note:
            Results are cached. Call parse with force=True to reload.
        """
        # Check cache
        if config_path in self._cache:
            logger.debug("control_config_from_cache", path=str(config_path))
            return self._cache[config_path]

        # Check file exists
        if not config_path.exists():
            raise FileNotFoundError(f"Control configuration file not found: {config_path}")

        logger.info("parsing_control_config", path=str(config_path))

        # Parse TOML
        try:
            with open(config_path, "rb") as f:
                data = tomli.load(f)
        except tomli.TOMLDecodeError as e:
            raise ValueError(f"Invalid TOML in {config_path}: {e}") from e

        # Validate structure
        if not isinstance(data, dict):
            raise ValueError(f"Expected dict at root of {config_path}, got {type(data).__name__}")

        # Parse sections
        try:
            # Rules section
            rules_data = data.get("rules", {})
            if not isinstance(rules_data, dict):
                raise ValueError("'rules' must be dict")

            rules = RuleControl(**rules_data)

            # Ignore section
            ignore_data = data.get("ignore", {})
            if not isinstance(ignore_data, dict):
                raise ValueError("'ignore' must be dict")

            ignore = IgnoreConfig(**ignore_data)

            # Build config
            config = ControlConfig(
                rules=rules,
                ignore=ignore,
                metadata=data.get("metadata", {}),
            )

            logger.info(
                "control_config_parsed",
                enabled=len(config.rules.enabled),
                disabled=len(config.rules.disabled),
                ignore_patterns=len(config.ignore.patterns),
            )

            # Cache
            self._cache[config_path] = config

            return config

        except Exception as e:
            raise ValueError(f"Invalid control configuration in {config_path}: {e}") from e

    def parse_or_default(self, config_path: Path) -> ControlConfig:
        """
        Parse config or return default if not found.

        Args:
            config_path: Path to semantica.toml

        Returns:
            ControlConfig (default if file not found)

        Note:
            Default config enables all rules, ignores nothing.
        """
        if not config_path.exists():
            logger.info("control_config_not_found_using_default", path=str(config_path))
            return ControlConfig()

        try:
            return self.parse(config_path)
        except Exception as e:
            logger.warning("control_config_parse_failed_using_default", error=str(e))
            return ControlConfig()

    def clear_cache(self) -> None:
        """Clear cached configs"""
        self._cache.clear()
        logger.debug("control_config_cache_cleared")
