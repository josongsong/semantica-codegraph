"""Pattern Matcher - Wildcard Support.

RFC-032: Generic Atoms with Wildcard Matching.

Supports:
    - Exact matching: "sqlite3.Cursor"
    - Suffix matching: "*.Cursor"
    - Prefix matching: "subprocess.*"
    - Contains matching: "*mongo*"
"""

import re
from functools import lru_cache


@lru_cache(maxsize=1000)
def compile_wildcard_pattern(pattern: str, case_sensitive: bool = False) -> re.Pattern[str]:
    """Compile wildcard pattern to regex.

    RFC-032: Wildcard → Regex conversion.

    Wildcards:
        * = zero or more characters (any)

    Args:
        pattern: Wildcard pattern
        case_sensitive: Whether to compile case-sensitive regex

    Returns:
        Compiled regex pattern

    Examples:
        >>> compile_wildcard_pattern("*.Cursor")
        re.compile('^.*\\.Cursor$')

        >>> compile_wildcard_pattern("*mongo*")
        re.compile('^.*mongo.*$')
    """
    # Escape regex special chars except *
    escaped = re.escape(pattern)

    # Replace escaped \* with .*
    regex_pattern = escaped.replace(r"\*", ".*")

    # Anchor to start and end
    regex_pattern = f"^{regex_pattern}$"

    # Compile with appropriate flags
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(regex_pattern, flags=flags)


def wildcard_match(
    pattern: str,
    text: str,
    case_sensitive: bool = False,
) -> bool:
    """Match text against wildcard pattern.

    RFC-032: Wildcard matching implementation.

    Args:
        pattern: Wildcard pattern (with *)
        text: Text to match
        case_sensitive: Whether to do case-sensitive matching (default: False)

    Returns:
        True if matches, False otherwise

    Examples:
        >>> wildcard_match("*.Cursor", "sqlite3.Cursor")
        True

        >>> wildcard_match("*.Cursor", "psycopg2.extensions.cursor")
        True  # Case-insensitive by default

        >>> wildcard_match("*mongo*", "pymongo.collection.Collection")
        True

        >>> wildcard_match("subprocess.*", "subprocess.Popen")
        True

        >>> wildcard_match("sqlite3.Cursor", "sqlite3.Cursor")
        True

        >>> wildcard_match("*.Cursor", "sqlite3.Connection")
        False
    """
    if not pattern:
        return False

    if not text:
        return False

    # Normalize case if not case-sensitive
    if not case_sensitive:
        pattern = pattern.lower()
        text = text.lower()

    # Exact match (no wildcards)
    if "*" not in pattern:
        if case_sensitive:
            return pattern == text
        else:
            return pattern.lower() == text.lower()

    # Wildcard match
    regex = compile_wildcard_pattern(pattern, case_sensitive=case_sensitive)
    return bool(regex.match(text))


def is_suffix_pattern(pattern: str) -> bool:
    """Check if pattern is a simple suffix pattern.

    Args:
        pattern: Pattern to check

    Returns:
        True if simple suffix (e.g., "*.Cursor")

    Examples:
        >>> is_suffix_pattern("*.Cursor")
        True

        >>> is_suffix_pattern("*mongo*")
        False
    """
    return pattern.startswith("*") and "*" not in pattern[1:]


def is_prefix_pattern(pattern: str) -> bool:
    """Check if pattern is a simple prefix pattern.

    Args:
        pattern: Pattern to check

    Returns:
        True if simple prefix (e.g., "subprocess.*")

    Examples:
        >>> is_prefix_pattern("subprocess.*")
        True

        >>> is_prefix_pattern("*subprocess*")
        False
    """
    return pattern.endswith("*") and "*" not in pattern[:-1]


def is_contains_pattern(pattern: str) -> bool:
    """Check if pattern is a contains pattern.

    Args:
        pattern: Pattern to check

    Returns:
        True if contains pattern (e.g., "*mongo*")

    Examples:
        >>> is_contains_pattern("*mongo*")
        True

        >>> is_contains_pattern("*.Cursor")
        False
    """
    return pattern.startswith("*") and pattern.endswith("*") and len(pattern) > 2


def extract_suffix(pattern: str) -> str:
    """Extract suffix from suffix pattern.

    Args:
        pattern: Suffix pattern (e.g., "*.Cursor")

    Returns:
        Suffix (e.g., ".Cursor")

    Examples:
        >>> extract_suffix("*.Cursor")
        '.Cursor'
    """
    if not is_suffix_pattern(pattern):
        raise ValueError(f"Not a suffix pattern: {pattern}")

    return pattern[1:]  # Remove leading *


def extract_prefix(pattern: str) -> str:
    """Extract prefix from prefix pattern.

    Args:
        pattern: Prefix pattern (e.g., "subprocess.*")

    Returns:
        Prefix (e.g., "subprocess.")

    Examples:
        >>> extract_prefix("subprocess.*")
        'subprocess.'
    """
    if not is_prefix_pattern(pattern):
        raise ValueError(f"Not a prefix pattern: {pattern}")

    return pattern[:-1]  # Remove trailing *


def extract_substring(pattern: str) -> str:
    """Extract substring from contains pattern.

    Args:
        pattern: Contains pattern (e.g., "*mongo*")

    Returns:
        Substring (e.g., "mongo")

    Examples:
        >>> extract_substring("*mongo*")
        'mongo'
    """
    if not is_contains_pattern(pattern):
        raise ValueError(f"Not a contains pattern: {pattern}")

    return pattern[1:-1]  # Remove leading and trailing *
