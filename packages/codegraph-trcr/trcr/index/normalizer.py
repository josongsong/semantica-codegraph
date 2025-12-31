"""Type Normalizer - Type Name Normalization.

Purpose: Handle type name variations, typos, and aliases.

Features:
    - Case normalization (lowercase by default)
    - Alias resolution (pysqlite2 → sqlite3)
    - Namespace stripping (optional)
    - Configurable strategies

Usage:
    >>> normalizer = TypeNormalizer()
    >>> normalizer.normalize("Sqlite3.Cursor")
    'sqlite3.cursor'
    >>> normalizer.normalize("pysqlite2.dbapi2.Cursor")
    'sqlite3.cursor'
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class NormalizationConfig:
    """Configuration for type normalization."""

    # Case normalization
    lowercase: bool = True

    # Alias resolution
    resolve_aliases: bool = True

    # Strip package prefixes (e.g., "foo.bar.Baz" → "Baz")
    strip_packages: bool = False

    # Custom normalization function
    custom_normalizer: Callable[[str], str] | None = None


# Default type aliases (Python ecosystem)
DEFAULT_ALIASES = {
    # SQLite aliases
    "pysqlite2.dbapi2.cursor": "sqlite3.cursor",
    "pysqlite2.cursor": "sqlite3.cursor",
    "sqlite.cursor": "sqlite3.cursor",
    # PostgreSQL aliases
    "psycopg2.extensions.cursor": "psycopg2.cursor",
    "psycopg2._psycopg.cursor": "psycopg2.cursor",
    # Flask aliases
    "werkzeug.wrappers.request": "flask.request",
    "werkzeug.wrappers.response": "flask.response",
    # Django aliases
    "django.core.handlers.wsgi.wsgiRequest": "django.http.httprequest",
}


class TypeNormalizer:
    """Type name normalizer.

    SOTA Features:
        - Configurable normalization strategies
        - Built-in Python ecosystem aliases
        - Custom alias support
        - TRUE immutability (frozen aliases)
        - Thread-safe (no mutable state)

    Thread Safety:
        - All state is immutable after construction
        - add_alias() returns NEW normalizer
        - Safe for concurrent use

    Example:
        >>> normalizer = TypeNormalizer()
        >>> normalizer.normalize("Sqlite3.Cursor")
        'sqlite3.cursor'
        >>> normalizer.normalize("pysqlite2.dbapi2.cursor")
        'sqlite3.cursor'
    """

    def __init__(
        self,
        config: NormalizationConfig | None = None,
        custom_aliases: dict[str, str] | None = None,
    ) -> None:
        """Initialize normalizer.

        Args:
            config: Normalization configuration
            custom_aliases: Custom type aliases (merged with defaults)
        """
        self.config = config or NormalizationConfig()

        # Build alias map (IMMUTABLE)
        aliases = dict(DEFAULT_ALIASES)
        if custom_aliases:
            aliases.update(custom_aliases)

        # Normalize alias keys (for case-insensitive lookup)
        if self.config.lowercase:
            aliases = {k.lower(): v.lower() for k, v in aliases.items()}

        # Store as IMMUTABLE (use types.MappingProxyType for true immutability)
        from types import MappingProxyType

        self._aliases = MappingProxyType(aliases)  # Read-only view

    def normalize(self, type_name: str) -> str:
        """Normalize type name.

        Steps:
            1. Apply custom normalizer (if configured)
            2. Case normalization
            3. Alias resolution
            4. Package stripping (if configured)

        Args:
            type_name: Type name to normalize

        Returns:
            Normalized type name

        Example:
            >>> normalizer = TypeNormalizer()
            >>> normalizer.normalize("Sqlite3.Cursor")
            'sqlite3.cursor'
        """
        if not type_name:
            return type_name

        result = type_name

        # 1. Custom normalizer
        if self.config.custom_normalizer:
            result = self.config.custom_normalizer(result)

        # 2. Case normalization
        if self.config.lowercase:
            result = result.lower()

        # 3. Alias resolution
        if self.config.resolve_aliases:
            result = self._aliases.get(result, result)

        # 4. Package stripping
        if self.config.strip_packages:
            result = self._strip_package(result)

        return result

    def add_alias(self, from_type: str, to_type: str) -> "TypeNormalizer":
        """Add custom alias and return NEW normalizer.

        IMMUTABILITY: Returns new instance instead of mutating.

        Args:
            from_type: Source type name
            to_type: Target type name

        Returns:
            New TypeNormalizer with added alias

        Example:
            >>> normalizer = TypeNormalizer()
            >>> new_normalizer = normalizer.add_alias("MyDB.Cursor", "sqlite3.Cursor")
            >>> # Original normalizer unchanged
        """
        key = from_type.lower() if self.config.lowercase else from_type
        value = to_type.lower() if self.config.lowercase else to_type

        # Create new aliases dict (merge current aliases with new one)
        new_aliases = dict(self._aliases)
        new_aliases[key] = value

        # Return new normalizer with pre-normalized aliases
        return TypeNormalizer._from_aliases(self.config, new_aliases)

    @classmethod
    def _from_aliases(cls, config: NormalizationConfig, aliases: dict[str, str]) -> "TypeNormalizer":
        """Create normalizer from pre-normalized aliases (internal).

        Args:
            config: Normalization config
            aliases: Pre-normalized aliases dict

        Returns:
            New TypeNormalizer
        """
        instance = cls.__new__(cls)
        instance.config = config

        from types import MappingProxyType

        instance._aliases = MappingProxyType(aliases)
        return instance

    def _strip_package(self, type_name: str) -> str:
        """Strip package prefix.

        Args:
            type_name: Type name with package

        Returns:
            Type name without package

        Example:
            >>> _strip_package("foo.bar.Baz")
            'Baz'
        """
        if "." not in type_name:
            return type_name

        return type_name.split(".")[-1]

    def get_aliases(self) -> dict[str, str]:
        """Get all configured aliases.

        Returns:
            Copy of aliases dictionary (immutable view)
        """
        return dict(self._aliases)


# Singleton instances for common use cases
default_normalizer = TypeNormalizer()
case_sensitive_normalizer = TypeNormalizer(config=NormalizationConfig(lowercase=False))
strict_normalizer = TypeNormalizer(config=NormalizationConfig(lowercase=True, resolve_aliases=False))
