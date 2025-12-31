"""Pattern Subsumption Utilities - RFC-035.

Determines if one pattern subsumes (fully covers) another.

Key Concepts:
    - pattern_subsumes(a, b): Does pattern 'a' match everything 'b' matches?
    - wildcard_to_regex: Convert glob patterns to regex
    - generate_samples: Generate test samples for pattern coverage

Subsumption Examples:
    - "*" subsumes "*.Cursor" (any matches all cursors)
    - "*.Cursor" subsumes "sqlite3.Cursor" (wildcard prefix)
    - "sqlite3.*" subsumes "sqlite3.Cursor" (wildcard suffix)
    - "*sql*" subsumes "sqlite3" (contains)
"""

import re
from dataclasses import dataclass


@dataclass
class PatternInfo:
    """Parsed pattern information."""

    original: str
    regex: re.Pattern[str]
    is_literal: bool  # No wildcards
    prefix: str | None  # For prefix patterns (*.Cursor -> Cursor)
    suffix: str | None  # For suffix patterns (sqlite3.* -> sqlite3)
    contains: str | None  # For contains patterns (*sql* -> sql)
    wildcard_count: int
    literal_length: int


def wildcard_to_regex(pattern: str) -> re.Pattern[str]:
    """Convert glob-style pattern to regex.

    Supports:
        - * : Any characters (zero or more)
        - ? : Single character
        - Literal: Exact match

    Args:
        pattern: Glob pattern (e.g., "*.Cursor", "sqlite3.*")

    Returns:
        Compiled regex pattern

    Examples:
        >>> wildcard_to_regex("*.Cursor").match("sqlite3.Cursor")
        <re.Match object; ...>
        >>> wildcard_to_regex("sqlite3.*").match("sqlite3.Connection")
        <re.Match object; ...>
    """
    # Escape special regex chars except * and ?
    escaped = ""
    for char in pattern:
        if char == "*":
            escaped += ".*"
        elif char == "?":
            escaped += "."
        elif char in r"\.^$+{}[]|()":
            escaped += "\\" + char
        else:
            escaped += char

    # Anchor the pattern
    return re.compile(f"^{escaped}$", re.IGNORECASE)


def parse_pattern(pattern: str) -> PatternInfo:
    """Parse pattern into structured info.

    Args:
        pattern: Glob pattern

    Returns:
        PatternInfo with parsed details
    """
    regex = wildcard_to_regex(pattern)
    wildcard_count = pattern.count("*") + pattern.count("?")
    literal_length = len(pattern) - wildcard_count

    # Determine pattern type
    prefix = None
    suffix = None
    contains = None

    if "*" not in pattern and "?" not in pattern:
        is_literal = True
    else:
        is_literal = False

        # Check for prefix pattern (*.Suffix)
        if pattern.startswith("*") and not pattern[1:].startswith("*"):
            suffix_part = pattern.lstrip("*")
            if "*" not in suffix_part and "?" not in suffix_part:
                prefix = suffix_part  # The pattern matches things ending with this

        # Check for suffix pattern (Prefix.*)
        if pattern.endswith("*") and not pattern[:-1].endswith("*"):
            prefix_part = pattern.rstrip("*")
            if "*" not in prefix_part and "?" not in prefix_part:
                suffix = prefix_part  # The pattern matches things starting with this

        # Check for contains pattern (*middle*)
        if pattern.startswith("*") and pattern.endswith("*"):
            middle = pattern[1:-1]
            if "*" not in middle and "?" not in middle:
                contains = middle

    return PatternInfo(
        original=pattern,
        regex=regex,
        is_literal=is_literal,
        prefix=prefix,  # What the pattern ends with
        suffix=suffix,  # What the pattern starts with
        contains=contains,
        wildcard_count=wildcard_count,
        literal_length=literal_length,
    )


def pattern_subsumes(broader: str, narrower: str) -> bool:
    """Check if broader pattern subsumes narrower pattern.

    Pattern A subsumes B if everything B matches, A also matches.
    (A is more general than B)

    Args:
        broader: Potentially broader pattern
        narrower: Potentially narrower pattern

    Returns:
        True if broader subsumes narrower

    Examples:
        >>> pattern_subsumes("*", "*.Cursor")  # * matches everything
        True
        >>> pattern_subsumes("*.Cursor", "sqlite3.Cursor")  # wildcard is broader
        True
        >>> pattern_subsumes("sqlite3.Cursor", "*.Cursor")  # literal is narrower
        False
    """
    # Same pattern - subsumes itself
    if broader == narrower:
        return True

    broader_info = parse_pattern(broader)
    narrower_info = parse_pattern(narrower)

    # Universal pattern subsumes everything
    if broader == "*":
        return True

    # Narrower is universal - nothing subsumes it except itself
    if narrower == "*":
        return False

    # Literal pattern only subsumes itself (already checked)
    if broader_info.is_literal:
        return False

    # If narrower is literal, check if broader's regex matches it
    if narrower_info.is_literal:
        return bool(broader_info.regex.match(narrower))

    # Both have wildcards - use structural analysis + sampling
    return _structural_subsumes(broader_info, narrower_info) or _sample_subsumes(broader_info, narrower_info)


def _structural_subsumes(broader: PatternInfo, narrower: PatternInfo) -> bool:
    """Structural subsumption check for wildcard patterns.

    Fast path for common cases.
    """
    # *.X subsumes *.X.Y (if X is suffix of X.Y)
    if broader.prefix and narrower.prefix:
        if narrower.prefix.endswith(broader.prefix):
            return True

    # X.* subsumes X.Y.* (if X is prefix of X.Y)
    if broader.suffix and narrower.suffix:
        if narrower.suffix.startswith(broader.suffix):
            return True

    # *X* subsumes *Y* if X is substring of Y... wait, opposite
    # *X* subsumes anything containing X, including *XY*
    if broader.contains and narrower.contains:
        if broader.contains in narrower.contains:
            return True

    # *X* subsumes *.X or X.*
    if broader.contains:
        if narrower.prefix and broader.contains in narrower.prefix:
            return True
        if narrower.suffix and broader.contains in narrower.suffix:
            return True

    return False


def _sample_subsumes(broader: PatternInfo, narrower: PatternInfo, samples: int = 50) -> bool:
    """Sample-based subsumption check.

    Generate samples from narrower pattern, verify broader matches all.

    Args:
        broader: Broader pattern info
        narrower: Narrower pattern info
        samples: Number of samples to generate

    Returns:
        True if broader matches all samples (probabilistic)
    """
    generated = generate_samples(narrower.original, samples)

    return all(broader.regex.match(sample) for sample in generated)


def generate_samples(pattern: str, count: int = 50) -> list[str]:
    """Generate sample strings matching a pattern.

    Used for probabilistic subsumption testing.

    Args:
        pattern: Glob pattern
        count: Number of samples to generate

    Returns:
        List of sample strings matching the pattern

    Examples:
        >>> samples = generate_samples("*.Cursor", 10)
        >>> all("Cursor" in s for s in samples)
        True
    """
    samples: list[str] = []

    # Component parts for sample generation
    prefixes = [
        "sqlite3",
        "psycopg2",
        "pymongo",
        "redis",
        "flask",
        "django",
        "requests",
        "urllib",
        "subprocess",
        "os",
        "io",
        "sys",
        "http.client",
        "xmlrpc.client",
        "ftplib",
        "smtplib",
        "paramiko",
        "boto3",
        "azure.storage",
        "google.cloud",
    ]

    suffixes = [
        "Cursor",
        "Connection",
        "Session",
        "Client",
        "Request",
        "Response",
        "Handler",
        "Manager",
        "Service",
        "Pool",
        "execute",
        "query",
        "fetch",
        "send",
        "read",
        "write",
        "open",
        "connect",
        "call",
        "run",
    ]

    # Parse pattern to understand structure
    info = parse_pattern(pattern)

    # Generate based on pattern type
    if info.is_literal:
        # Literal pattern only matches itself
        return [pattern]

    if info.prefix:  # Pattern like *.Cursor
        # Generate prefix.SUFFIX samples
        for prefix in prefixes[: min(count, len(prefixes))]:
            sample = f"{prefix}{info.prefix}"
            if info.regex.match(sample):
                samples.append(sample)
            if len(samples) >= count:
                break

    elif info.suffix:  # Pattern like sqlite3.*
        # Generate PREFIX.suffix samples
        for suffix in suffixes[: min(count, len(suffixes))]:
            sample = f"{info.suffix}{suffix}"
            if info.regex.match(sample):
                samples.append(sample)
            if len(samples) >= count:
                break

    elif info.contains:  # Pattern like *sql*
        # Generate prefix.CONTAINS.suffix samples
        for prefix in prefixes[:5]:
            for suffix in suffixes[:5]:
                sample = f"{prefix}.{info.contains}.{suffix}"
                if info.regex.match(sample):
                    samples.append(sample)
                if len(samples) >= count:
                    break
            if len(samples) >= count:
                break

    else:
        # General wildcard - try combinations
        for prefix in prefixes[: min(count // 2, len(prefixes))]:
            for suffix in suffixes[: min(2, len(suffixes))]:
                sample = f"{prefix}.{suffix}"
                if info.regex.match(sample):
                    samples.append(sample)
                if len(samples) >= count:
                    break
            if len(samples) >= count:
                break

    return samples[:count]


def compute_overlap_percentage(pattern_a: str, pattern_b: str, samples: int = 100) -> float:
    """Compute overlap percentage between two patterns.

    Uses sampling to estimate what percentage of pattern_b's
    matches are also matched by pattern_a.

    Args:
        pattern_a: First pattern
        pattern_b: Second pattern
        samples: Number of samples to generate

    Returns:
        Percentage [0.0, 1.0] of overlap

    Examples:
        >>> compute_overlap_percentage("*", "*.Cursor")
        1.0  # * matches everything Cursor matches
        >>> compute_overlap_percentage("sqlite3.*", "psycopg2.*")
        0.0  # No overlap
    """
    if pattern_a == pattern_b:
        return 1.0

    info_a = parse_pattern(pattern_a)
    samples_b = generate_samples(pattern_b, samples)

    if not samples_b:
        return 0.0

    matches = sum(1 for s in samples_b if info_a.regex.match(s))
    return matches / len(samples_b)
