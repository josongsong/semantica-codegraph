"""Security pattern definitions.

YAML-based patterns for detecting security vulnerabilities:
- crypto.yaml: Weak cryptography (L22)
- auth.yaml: Authentication/Authorization issues (L23)
- injection.yaml: Injection vulnerabilities (L24)
"""

import os
from pathlib import Path
from typing import Any

import yaml


def load_pattern(pattern_name: str) -> dict[str, Any]:
    """Load a security pattern from YAML file.

    Args:
        pattern_name: Name of pattern file (without .yaml extension)

    Returns:
        Dictionary containing pattern definitions

    Example:
        >>> crypto_patterns = load_pattern("crypto")
        >>> print(crypto_patterns["patterns"]["weak_hash"])
    """
    pattern_dir = Path(__file__).parent
    pattern_file = pattern_dir / f"{pattern_name}.yaml"

    if not pattern_file.exists():
        raise FileNotFoundError(f"Pattern file not found: {pattern_file}")

    with open(pattern_file, "r") as f:
        return yaml.safe_load(f)


def load_all_patterns() -> dict[str, dict[str, Any]]:
    """Load all security patterns.

    Returns:
        Dictionary mapping pattern names to their definitions

    Example:
        >>> all_patterns = load_all_patterns()
        >>> print(all_patterns.keys())  # ['crypto', 'auth', 'injection']
    """
    pattern_dir = Path(__file__).parent
    patterns = {}

    for yaml_file in pattern_dir.glob("*.yaml"):
        pattern_name = yaml_file.stem
        patterns[pattern_name] = load_pattern(pattern_name)

    return patterns


__all__ = [
    "load_pattern",
    "load_all_patterns",
]
